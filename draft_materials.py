"""
draft_materials.py - Tailored Resume Bullets & Cover Letter Generator

For every job in jobs.db with status = 'approved', drafts tailored resume
bullets and a personalized cover letter using ONLY real accomplishments
from the candidate's fact_bank in profile.json.
No cloud APIs, no invented experience, local Ollama LLM execution.
"""

import datetime
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------
# Default model: qwen3:8b. Swap to "llama3.2:3b" for lighter hardware.
MODEL_NAME = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 60  # seconds per generation call
DB_FILENAME = "jobs.db"
PROFILE_FILENAME = "profile.json"

# Structured JSON Schema for Step 1: Bullet Selection & Ranking
BULLET_SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The exact ID of the selected fact_bank entry",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One-line reason why this accomplishment is relevant to this specific job",
                    },
                },
                "required": ["id", "reason"],
            },
            "description": "4 to 6 most relevant fact_bank IDs, ranked in order of relevance",
        }
    },
    "required": ["selected_bullets"],
}

# Structured JSON Schema for Step 2: Cover Letter Generation
COVER_LETTER_SCHEMA = {
    "type": "object",
    "properties": {
        "cover_letter": {
            "type": "string",
            "description": "A tailored 250-350 word cover letter adhering strictly to constraints",
        },
        "relevance_note": {
            "type": "string",
            "description": "Optional note if fewer than 3 fact_bank entries were genuinely relevant, otherwise empty string",
        },
    },
    "required": ["cover_letter"],
}


# ---------------------------------------------------------------------------
# Profile & Fact Bank Validation
# ---------------------------------------------------------------------------
def load_and_validate_profile(profile_path: str = PROFILE_FILENAME) -> Optional[Dict[str, Any]]:
    """
    Loads profile.json and validates that fact_bank exists and contains real entries.
    Exits if profile is missing or fact_bank is empty.
    """
    if not os.path.exists(profile_path):
        print("=" * 65)
        print(f"[ERROR] '{profile_path}' not found.")
        print("        Run score_jobs.py or create profile.json before drafting materials.")
        print("=" * 65)
        return None

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to parse '{profile_path}': {e}")
        return None

    fact_bank = profile.get("fact_bank", [])
    if not isinstance(fact_bank, list):
        print(f"[ERROR] 'fact_bank' in {profile_path} must be a list.")
        return None

    # Filter out empty or placeholder entries
    valid_facts = [
        f
        for f in fact_bank
        if isinstance(f, dict) and f.get("id", "").strip() and f.get("text", "").strip()
    ]

    if not valid_facts:
        print("=" * 65)
        print("[ERROR] 'fact_bank' in profile.json is empty or contains only blank entries.")
        print("        Please add your real career accomplishments to 'fact_bank' in")
        print(f"        {profile_path} before drafting materials.")
        print("=" * 65)
        return None

    return profile


def get_fact_bank_map(profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Returns a dictionary mapping fact_bank ID to entry dict."""
    fact_bank = profile.get("fact_bank", [])
    mapping = {}
    for item in fact_bank:
        if isinstance(item, dict) and item.get("id"):
            mapping[str(item["id"]).strip()] = item
    return mapping


# ---------------------------------------------------------------------------
# Ollama Request Helper
# ---------------------------------------------------------------------------
def call_ollama(
    system_prompt: str,
    user_prompt: str,
    json_schema: Dict[str, Any],
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
    timeout: int = OLLAMA_TIMEOUT,
) -> Dict[str, Any]:
    """Sends a chat request to local Ollama API with structured JSON output enforcement."""
    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": json_schema,
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Could not connect to Ollama at {ollama_url}. "
            f"Run `ollama serve`, then `ollama pull {model_name}`."
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Ollama request timed out after {timeout} seconds.")

    if response.status_code == 404:
        raise RuntimeError(
            f"Model '{model_name}' not found in Ollama. "
            f"Run `ollama pull {model_name}` to download it."
        )

    response.raise_for_status()
    resp_json = response.json()
    raw_content = resp_json.get("message", {}).get("content", "")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM structured output: {e}\nRaw content: {raw_content}")


# ---------------------------------------------------------------------------
# Core Drafting Logic
# ---------------------------------------------------------------------------
def select_ranked_bullets(
    job: Dict[str, Any],
    profile: Dict[str, Any],
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> List[Dict[str, str]]:
    """
    Step 1: Asks the model to select and rank 4-6 most relevant entries from fact_bank.
    Enforces that only existing fact_bank IDs are accepted.
    """
    fact_bank_map = get_fact_bank_map(profile)
    fact_bank_list = [
        {"id": k, "tags": v.get("tags", []), "text": v.get("text", "")}
        for k, v in fact_bank_map.items()
    ]

    job_title = job.get("title") or "Untitled Position"
    job_company = job.get("company") or "Unknown Company"
    job_tags = job.get("tags") or ""
    raw_desc = job.get("description") or ""
    # Provide enough context while keeping prompt token-efficient
    job_desc = raw_desc[:2500].rstrip() + ("..." if len(raw_desc) > 2500 else "")

    system_prompt = (
        "You are an expert technical resume strategist. "
        "Your job is to select and rank the 4 to 6 most relevant accomplishments from the candidate's FACT BANK for a specific job posting. "
        "CRITICAL RULES:\n"
        "1. You MUST ONLY select existing IDs from the CANDIDATE FACT BANK provided.\n"
        "2. NEVER invent, rewrite, or fabricate accomplishments or bullet points.\n"
        "3. Provide a concise, one-line reason explaining why each chosen bullet directly connects to this job."
    )

    user_prompt = f"""[JOB POSTING]
Title: {job_title}
Company: {job_company}
Tags: {job_tags}
Description:
{job_desc}

[CANDIDATE FACT BANK]
{json.dumps(fact_bank_list, indent=2)}

Select the 4 to 6 most relevant fact_bank IDs for this role, ranked from most relevant to least relevant."""

    result = call_ollama(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=BULLET_SELECTION_SCHEMA,
        model_name=model_name,
        ollama_url=ollama_url,
    )

    raw_selections = result.get("selected_bullets", [])
    valid_bullets: List[Dict[str, str]] = []
    seen_ids = set()

    for item in raw_selections:
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("id", "")).strip()
        if fact_id in fact_bank_map and fact_id not in seen_ids:
            seen_ids.add(fact_id)
            valid_bullets.append({
                "id": fact_id,
                "text": fact_bank_map[fact_id].get("text", "").strip(),
            })

    # If model failed to return valid IDs or returned fewer than available, fill with top available facts
    if not valid_bullets:
        for fact_id, fact_data in list(fact_bank_map.items())[:5]:
            valid_bullets.append({
                "id": fact_id,
                "text": fact_data.get("text", "").strip(),
            })

    return valid_bullets


def generate_cover_letter(
    job: Dict[str, Any],
    profile: Dict[str, Any],
    selected_bullets: List[Dict[str, str]],
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> str:
    """
    Step 2: Drafts a tailored 250-350 word cover letter referencing genuine company
    specifics and weaving in selected accomplishments.
    """
    candidate = profile.get("candidate", {})
    candidate_name = candidate.get("name") or "Candidate"
    current_role = candidate.get("current_role") or "Software Professional"

    job_title = job.get("title") or "Position"
    job_company = job.get("company") or "the company"
    raw_desc = job.get("description") or ""
    job_desc = raw_desc[:2500].rstrip() + ("..." if len(raw_desc) > 2500 else "")

    bullets_text = "\n".join(
        f"- [ID: {b['id']}] {b['text']}" for b in selected_bullets
    )

    system_prompt = (
        "You are an experienced software engineer drafting a direct, authentic note/cover letter to a hiring manager.\n\n"
        "STRICT VOICE & STYLE GUIDELINES:\n"
        "1. Direct Engineer Voice: Write like a competent engineer messaging a hiring manager directly, not like a formal cover letter template. "
        "Keep it plain, direct, and specific. Do NOT use superlatives about the opportunity itself.\n"
        "2. FORBIDDEN PHRASES (DO NOT USE ANY OF THESE OR CLOSE VARIANTS):\n"
        "   - 'I am excited to apply'\n"
        "   - 'passionate about'\n"
        "   - 'proven track record'\n"
        "   - 'hit the ground running'\n"
        "   - 'dynamic environment'\n"
        "   - 'fast-paced environment'\n"
        "   - 'leverage my skills'\n"
        "   - 'seamlessly'\n"
        "   - 'furthermore'\n"
        "   - 'moreover'\n"
        "   - 'not only... but also'\n"
        "   - 'I look forward to hearing from you'\n"
        "   - 'thrilled'\n"
        "   - 'incredible opportunity'\n"
        "3. DYNAMIC STRUCTURE & RHYTHM:\n"
        "   - Do NOT use a formulaic structure (enthusiastic opener, exactly three strengths, generic closer).\n"
        "   - Vary the opening structure: lead with the most relevant project, or why the role specifically caught your attention, or a direct statement of what you would do in the role.\n"
        "   - Vary paragraph and sentence length noticeably. Do not make every sentence roughly the same length.\n"
        "4. PUNCTUATION RULE:\n"
        "   - Do NOT use em-dashes (—). Use periods or commas instead.\n"
        "5. REAL SPECIFICS & FACTS ONLY:\n"
        "   - Reference 1-2 concrete specifics pulled directly from the job description text below (product, stated mission, tech stack, team). NEVER invent company facts.\n"
        "   - Weave in 2-3 of the selected accomplishments naturally. Do not format them as bullet points.\n"
        "   - If fewer than 3 fact_bank entries are genuinely relevant to this job, state so honestly in a short note rather than padding.\n"
        "6. LENGTH: 250-350 words."
    )

    user_prompt = f"""[CANDIDATE INFO]
Name: {candidate_name}
Current Role: {current_role}

[JOB DETAILS]
Title: {job_title}
Company: {job_company}
Description:
{job_desc}

[SELECTED ACCOMPLISHMENTS FROM CANDIDATE FACT BANK]
{bullets_text}

Draft the cover letter now adhering strictly to the constraints, dynamic rhythm, and forbidden phrase rules."""

    result = call_ollama(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=COVER_LETTER_SCHEMA,
        model_name=model_name,
        ollama_url=ollama_url,
    )

    cover_letter = result.get("cover_letter", "").strip()
    # Replace any accidental em-dashes to guarantee strict compliance
    cover_letter = (
        cover_letter.replace("—", ", ")
        .replace(" – ", ", ")
        .replace(" -- ", ", ")
    )
    relevance_note = result.get("relevance_note", "").strip()

    if relevance_note and relevance_note.lower() not in cover_letter.lower():
        cover_letter = f"{cover_letter}\n\n[Note: {relevance_note}]"

    return cover_letter


def draft_materials(
    job: Dict[str, Any],
    profile: Dict[str, Any],
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> Dict[str, Any]:
    """
    Core function: Generates tailored resume bullets and cover letter for a single job.
    Returns:
      {
        "resume_bullets": [{"id": ..., "text": ...}, ...],
        "cover_letter": "..."
      }
    """
    # 1. Bullet selection
    selected_bullets = select_ranked_bullets(
        job=job,
        profile=profile,
        model_name=model_name,
        ollama_url=ollama_url,
    )

    # 2. Cover letter generation
    cover_letter = generate_cover_letter(
        job=job,
        profile=profile,
        selected_bullets=selected_bullets,
        model_name=model_name,
        ollama_url=ollama_url,
    )

    return {
        "resume_bullets": selected_bullets,
        "cover_letter": cover_letter,
    }


# ---------------------------------------------------------------------------
# CLI Execution Loop
# ---------------------------------------------------------------------------
def run_cli():
    print("=" * 65)
    print("  Application Materials Drafter - Bullets & Cover Letter")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_path = os.path.join(base_dir, PROFILE_FILENAME)
    db_path = os.path.join(base_dir, DB_FILENAME)

    profile = load_and_validate_profile(profile_path)
    if profile is None:
        sys.exit(1)

    if not os.path.exists(db_path):
        print(f"[ERROR] Database '{db_path}' not found. Run source_jobs.py first.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'approved' ORDER BY fetched_at ASC")
    approved_jobs = cursor.fetchall()

    if not approved_jobs:
        print("\nNo jobs with status = 'approved' found.")
        print("To approve jobs for drafting, update status in jobs.db:")
        print("  sqlite3 jobs.db \"UPDATE jobs SET status = 'approved' WHERE source = 'remotive' AND external_id = '...';\"")
        conn.close()
        return

    print(f"Target Database : {db_path}")
    print(f"Model Name      : {MODEL_NAME}")
    print(f"Approved Jobs   : {len(approved_jobs)}\n")

    drafted_count = 0
    error_count = 0

    for idx, row in enumerate(approved_jobs, start=1):
        job_dict = dict(row)
        title = job_dict.get("title") or "Untitled"
        company = job_dict.get("company") or "Unknown"
        source = job_dict.get("source")
        ext_id = job_dict.get("external_id")

        print(f"[{idx}/{len(approved_jobs)}] Drafting for: {title[:35]} @ {company[:20]}... ", end="", flush=True)

        try:
            materials = draft_materials(job_dict, profile, model_name=MODEL_NAME)
            bullets_json = json.dumps(materials["resume_bullets"])
            cover_letter_text = materials["cover_letter"]

            with conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET materials_resume_bullets = ?,
                        materials_cover_letter = ?,
                        status = 'materials_ready'
                    WHERE source = ? AND external_id = ?
                    """,
                    (bullets_json, cover_letter_text, source, ext_id),
                )

            drafted_count += 1
            print(f"[READY: {len(materials['resume_bullets'])} bullets, {len(cover_letter_text.split())} words]")

        except (ConnectionError, TimeoutError, RuntimeError) as conn_err:
            error_count += 1
            print("\n" + "!" * 65)
            print(f"[OLLAMA CONNECTION ERROR] {conn_err}")
            print("Stopping remaining drafting run. Once Ollama is ready, re-run draft_materials.py.")
            print("!" * 65)
            break
        except Exception as e:
            error_count += 1
            print(f"[ERROR] {e}")

    conn.close()

    print("\n" + "=" * 65)
    print("Materials Drafting Summary:")
    print(f"  - Materials Ready : {drafted_count}")
    print(f"  - Errors/Halted   : {error_count}")
    print("=" * 65)
    print("\nSample sqlite3 query to inspect drafted materials:")
    print(
        f'sqlite3 "{DB_FILENAME}" '
        f'"SELECT company, title, materials_resume_bullets, substr(materials_cover_letter, 1, 150) FROM jobs WHERE status = \'materials_ready\' LIMIT 5;"'
    )
    print()


if __name__ == "__main__":
    run_cli()
