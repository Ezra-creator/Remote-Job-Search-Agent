"""
score_jobs.py - Local LLM Job Scoring Tool

Scores remote job postings stored in jobs.db with status = 'new' against a
user profile (profile.json) using a local LLM via Ollama.
No cloud APIs, no external cost.
"""

import datetime
import json
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 45  # seconds per request
DB_FILENAME = "jobs.db"
PROFILE_FILENAME = "profile.json"

DEFAULT_PROFILE_TEMPLATE = {
    "candidate": {
        "name": "",
        "email": "",
        "timezone": "",
        "current_role": "",
        "years_experience": 0,
    },
    "target": {
        "roles": [],
        "seniority": [],
        "salary_floor_usd": 0,
        "remote_only": True,
        "timezone_overlap_required": "",
        "visa_sponsorship_needed": False,
    },
    "must_haves": [],
    "nice_to_haves": [],
    "dealbreakers": [],
    "excluded_companies": [],
    "skills": {"core": [], "familiar": []},
    "fact_bank": [{"id": "f001", "tags": [], "text": ""}],
}

# Structured JSON schema for Ollama responses
SCORING_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Fit score between 0 and 100",
        },
        "reasoning": {
            "type": "string",
            "description": "1 to 3 sentences explaining fit and potential gaps specifically for this job",
        },
        "flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Array of flags e.g. wrong_seniority, visa_mismatch, timezone_mismatch, missing_must_have:<name>, or empty array",
        },
    },
    "required": ["fit_score", "reasoning", "flags"],
}


# ---------------------------------------------------------------------------
# Profile Management
# ---------------------------------------------------------------------------
def load_or_create_profile(profile_path: str = PROFILE_FILENAME) -> Optional[Dict[str, Any]]:
    """
    Loads profile.json. If it does not exist, creates the exact template,
    prints an instructional message, and returns None.
    """
    if not os.path.exists(profile_path):
        template_str = json.dumps(DEFAULT_PROFILE_TEMPLATE, indent=2)
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(template_str)
        print("=" * 65)
        print(f"[!] Created template '{profile_path}'.")
        print("    Please fill in your profile, target roles, skills, and")
        print("    preferences in profile.json, then re-run score_jobs.py.")
        print("=" * 65)
        return None

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read {profile_path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Pre-filter Helpers
# ---------------------------------------------------------------------------
def parse_salary_max_usd(salary_str: Optional[str]) -> Optional[float]:
    """
    Extracts the maximum annual salary in USD from a salary string.
    Returns None if salary is not parseable or in a non-USD currency.
    """
    if not salary_str or not isinstance(salary_str, str):
        return None
    s = salary_str.strip()
    if not s or s == "$0":
        return None

    # Skip non-USD foreign currencies
    if any(c in s for c in ["€", "£", "¥", "₹", "EUR", "GBP", "CAD", "AUD"]):
        return None

    is_hourly = bool(re.search(r"/(?:hour|hr)\b", s, re.IGNORECASE))
    matches = re.findall(r"(\d+(?:[,\.]\d+)?)\s*(k|thousand)?", s, re.IGNORECASE)
    if not matches:
        return None

    values = []
    for num_str, k_suffix in matches:
        try:
            num = float(num_str.replace(",", ""))
            if k_suffix:
                num *= 1000
            elif num < 1000 and not is_hourly:
                if 30 < num < 500:
                    num *= 1000
            if is_hourly:
                num *= 2080  # standard full-time annual hours
            values.append(num)
        except ValueError:
            continue

    return max(values) if values else None


def check_pre_filters(job: Dict[str, Any], profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Applies fast, deterministic pre-filters before invoking the LLM:
    1. Excluded company check (case-insensitive)
    2. Salary floor check (when salary is cleanly parseable in USD)
    Returns a result dict if filtered out, or None if it should proceed to LLM.
    """
    # 1. Company exclusion
    excluded_companies = profile.get("excluded_companies", []) or []
    target_excluded = profile.get("target", {}).get("excluded_companies", []) or []
    all_excluded = set(c.strip().lower() for c in (excluded_companies + target_excluded) if isinstance(c, str) and c.strip())

    job_company = (job.get("company") or "").strip().lower()
    if job_company and job_company in all_excluded:
        return {
            "fit_score": 0,
            "fit_reasoning": f"Company '{job.get('company')}' is in excluded_companies.",
            "fit_flags": "excluded_company",
            "status": "skipped",
        }

    # 2. Salary floor check
    salary_floor = profile.get("target", {}).get("salary_floor_usd", 0) or 0
    try:
        salary_floor = float(salary_floor)
    except (ValueError, TypeError):
        salary_floor = 0

    if salary_floor > 0:
        max_salary = parse_salary_max_usd(job.get("salary"))
        if max_salary is not None and max_salary < salary_floor:
            return {
                "fit_score": 0,
                "fit_reasoning": f"Maximum salary (${max_salary:,.0f}) is below target floor (${salary_floor:,.0f}).",
                "fit_flags": "below_salary_floor",
                "status": "skipped",
            }

    return None


# ---------------------------------------------------------------------------
# Core Scoring Function
# ---------------------------------------------------------------------------
def build_scoring_prompt(job: Dict[str, Any], profile: Dict[str, Any]) -> str:
    """
    Constructs the prompt containing candidate profile and job details.
    Omits fact_bank to keep prompt lightweight.
    """
    candidate = profile.get("candidate", {})
    target = profile.get("target", {})
    must_haves = profile.get("must_haves", [])
    nice_to_haves = profile.get("nice_to_haves", [])
    dealbreakers = profile.get("dealbreakers", [])
    skills = profile.get("skills", {})

    profile_context = {
        "candidate": {
            "current_role": candidate.get("current_role", ""),
            "years_experience": candidate.get("years_experience", 0),
            "timezone": candidate.get("timezone", ""),
        },
        "target": {
            "roles": target.get("roles", []),
            "seniority": target.get("seniority", []),
            "remote_only": target.get("remote_only", True),
            "timezone_overlap_required": target.get("timezone_overlap_required", ""),
            "visa_sponsorship_needed": target.get("visa_sponsorship_needed", False),
        },
        "must_haves": must_haves,
        "nice_to_haves": nice_to_haves,
        "dealbreakers": dealbreakers,
        "skills": {
            "core": skills.get("core", []),
            "familiar": skills.get("familiar", []),
        },
    }

    # Truncate description to ~1500 characters
    raw_desc = job.get("description") or ""
    if len(raw_desc) > 1500:
        desc = raw_desc[:1500].rstrip() + "..."
    else:
        desc = raw_desc

    job_context = {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "salary": job.get("salary", ""),
        "tags": job.get("tags", ""),
        "description": desc,
    }

    prompt = f"""Evaluate this job posting against the candidate's profile:

[CANDIDATE PROFILE]
{json.dumps(profile_context, indent=2)}

[JOB POSTING]
{json.dumps(job_context, indent=2)}

Instructions:
1. Assess role relevance, seniority level, core skills match, remote/location fit, and candidate dealbreakers/must-haves.
2. Only flag concerns you can actually verify from the job text given. Do not guess at unstated requirements.
3. Return fit_score (0-100), reasoning (1-3 sentences specific to this job), and flags list."""

    return prompt


def score_job(
    job: Dict[str, Any],
    profile: Dict[str, Any],
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> Dict[str, Any]:
    """
    Evaluates a single job against the profile.
    Checks pre-filters first; if passed, calls Ollama LLM with structured output schema.
    Returns a dictionary with keys:
      fit_score (int | None), fit_reasoning (str), fit_flags (str), status ('scored' | 'skipped')
    """
    # 1. Check pre-filters
    pre_filtered = check_pre_filters(job, profile)
    if pre_filtered:
        return pre_filtered

    # 2. Build LLM prompt
    prompt = build_scoring_prompt(job, profile)

    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert technical recruiter evaluating job fit for a candidate. "
                    "Provide an objective, calibrated assessment adhering strictly to the JSON schema. "
                    "Only flag concerns you can actually verify from the job text given. Do not guess at unstated requirements."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "format": SCORING_JSON_SCHEMA,
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=OLLAMA_TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Could not connect to Ollama at {ollama_url}. "
            f"Run `ollama serve`, then `ollama pull {model_name}`."
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Ollama request timed out after {OLLAMA_TIMEOUT} seconds.")

    if response.status_code == 404:
        raise RuntimeError(
            f"Ollama returned 404. Make sure model '{model_name}' is downloaded by running `ollama pull {model_name}`."
        )

    response.raise_for_status()
    resp_data = response.json()

    message_content = resp_data.get("message", {}).get("content", "")
    try:
        parsed_result = json.loads(message_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM JSON output: {e}\nRaw output: {message_content}")

    fit_score = int(parsed_result.get("fit_score", 0))
    # Clamp fit_score between 0 and 100
    fit_score = max(0, min(100, fit_score))

    reasoning = str(parsed_result.get("reasoning", "")).strip()
    raw_flags = parsed_result.get("flags", [])
    if isinstance(raw_flags, list):
        flags_str = ", ".join(str(f).strip() for f in raw_flags if str(f).strip())
    else:
        flags_str = str(raw_flags).strip()

    return {
        "fit_score": fit_score,
        "fit_reasoning": reasoning,
        "fit_flags": flags_str,
        "status": "scored",
    }


# ---------------------------------------------------------------------------
# CLI Execution Loop
# ---------------------------------------------------------------------------
def run_cli():
    print("=" * 65)
    print("  Job Scoring Tool - Local LLM Evaluation via Ollama")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_path = os.path.join(base_dir, PROFILE_FILENAME)
    db_path = os.path.join(base_dir, DB_FILENAME)

    profile = load_or_create_profile(profile_path)
    if profile is None:
        sys.exit(0)

    if not os.path.exists(db_path):
        print(f"[ERROR] Database file '{db_path}' not found. Run source_jobs.py first.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch all jobs with status = 'new'
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'new' ORDER BY fetched_at ASC")
    new_jobs = cursor.fetchall()

    if not new_jobs:
        print("\nNo jobs with status = 'new' found to score.")
        conn.close()
        return

    print(f"Target Database : {db_path}")
    print(f"Model Name      : {MODEL_NAME}")
    print(f"Unscored Jobs   : {len(new_jobs)}\n")

    scored_count = 0
    skipped_count = 0
    error_count = 0

    for idx, row in enumerate(new_jobs, start=1):
        job_dict = dict(row)
        title = job_dict.get("title") or "Untitled"
        company = job_dict.get("company") or "Unknown"
        source = job_dict.get("source")
        ext_id = job_dict.get("external_id")

        print(f"[{idx}/{len(new_jobs)}] Processing: {title[:40]} @ {company[:25]}... ", end="", flush=True)

        try:
            score_result = score_job(job_dict, profile, model_name=MODEL_NAME)
            status = score_result.get("status", "scored")
            fit_score = score_result.get("fit_score")
            reasoning = score_result.get("fit_reasoning", "")
            flags = score_result.get("fit_flags", "")

            with conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET fit_score = ?,
                        fit_reasoning = ?,
                        fit_flags = ?,
                        status = ?
                    WHERE source = ? AND external_id = ?
                    """,
                    (fit_score, reasoning, flags, status, source, ext_id),
                )

            if status == "skipped":
                skipped_count += 1
                print(f"[SKIPPED] ({flags})")
            else:
                scored_count += 1
                flag_preview = f" | Flags: {flags}" if flags else ""
                print(f"[SCORED: {fit_score}/100]{flag_preview}")

        except (ConnectionError, TimeoutError, RuntimeError) as conn_err:
            error_count += 1
            print("\n" + "!" * 65)
            print(f"[OLLAMA CONNECTION ERROR] {conn_err}")
            print("Stopping remaining scoring run. Once Ollama is ready, re-run score_jobs.py.")
            print("!" * 65)
            break
        except Exception as e:
            error_count += 1
            print(f"[ERROR] {e}")

    conn.close()

    print("\n" + "=" * 65)
    print("Scoring Summary:")
    print(f"  - Scored by LLM : {scored_count}")
    print(f"  - Pre-filtered  : {skipped_count}")
    print(f"  - Errors/Halted : {error_count}")
    print("=" * 65)
    print("\nSample sqlite3 query to view top-fitting scored postings:")
    print(
        f'sqlite3 "{DB_FILENAME}" '
        f'"SELECT fit_score, company, title, fit_reasoning, fit_flags FROM jobs WHERE status = \'scored\' ORDER BY fit_score DESC LIMIT 10;"'
    )
    print()


if __name__ == "__main__":
    run_cli()
