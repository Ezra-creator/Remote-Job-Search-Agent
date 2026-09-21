"""
github_facts.py - On-Demand GitHub Repository Fact Bank Generator

Reads a candidate's public GitHub repositories (unauthenticated, read-only),
analyzes real README files using a local Ollama LLM, and drafts candidate
fact_bank entries in jobs.db for manual user review.
Never writes to profile.json directly.
"""

import base64
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
OLLAMA_TIMEOUT = 45  # seconds per generation call
DB_FILENAME = "jobs.db"
PROFILE_FILENAME = "profile.json"

GITHUB_API_BASE = "https://api.github.com"
GITHUB_USER_AGENT = "job-agent-github-facts/1.0"
REQUEST_TIMEOUT = 15  # seconds

# Structured JSON Schema for Repository Fact Evaluation
GITHUB_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "worth_including": {
            "type": "boolean",
            "description": "True if this repo represents substantial, independent project work worthy of a career fact_bank",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills and technologies actually evidenced in the repository",
        },
        "text": {
            "type": "string",
            "description": "A single fact_bank-style accomplishment sentence describing what was technically built, or empty string if worth_including is false",
        },
    },
    "required": ["worth_including", "tags", "text"],
}

CREATE_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS github_repo_cache (
    repo_name TEXT PRIMARY KEY,
    pushed_at TEXT,
    last_processed_at TEXT
);
"""

CREATE_CANDIDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS github_fact_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT,
    repo_url TEXT,
    language TEXT,
    tags TEXT,
    text TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT
);
"""


# ---------------------------------------------------------------------------
# Database Management
# ---------------------------------------------------------------------------
def init_github_tables(conn: sqlite3.Connection):
    """Creates the cache and fact candidate tables if they do not exist."""
    with conn:
        conn.execute(CREATE_CACHE_TABLE_SQL)
        conn.execute(CREATE_CANDIDATES_TABLE_SQL)


def is_repo_cached(conn: sqlite3.Connection, repo_name: str, pushed_at: str) -> bool:
    """Checks if a repo has already been processed at its current pushed_at timestamp."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT pushed_at FROM github_repo_cache WHERE repo_name = ?",
        (repo_name,),
    )
    row = cursor.fetchone()
    if row and row[0] == pushed_at:
        return True
    return False


def update_repo_cache(conn: sqlite3.Connection, repo_name: str, pushed_at: str):
    """Updates or inserts the cache record for a repo."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO github_repo_cache (repo_name, pushed_at, last_processed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                pushed_at = excluded.pushed_at,
                last_processed_at = excluded.last_processed_at
            """,
            (repo_name, pushed_at, now_utc),
        )


def save_fact_candidate(
    conn: sqlite3.Connection,
    repo_name: str,
    repo_url: str,
    language: str,
    tags: str,
    text: str,
) -> int:
    """Inserts a proposed fact candidate into github_fact_candidates."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = conn.cursor()
    with conn:
        cursor.execute(
            """
            INSERT INTO github_fact_candidates (repo_name, repo_url, language, tags, text, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (repo_name, repo_url, language, tags, text, now_utc),
        )
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# GitHub Public API Integration (Unauthenticated)
# ---------------------------------------------------------------------------
def fetch_public_repos(username: str) -> List[Dict[str, Any]]:
    """
    Fetches all public repositories for a username via GitHub REST API with pagination.
    Unauthenticated and read-only.
    """
    headers = {
        "User-Agent": GITHUB_USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }
    all_repos: List[Dict[str, Any]] = []
    page = 1

    while True:
        url = f"{GITHUB_API_BASE}/users/{username}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == 404:
            raise ValueError(f"GitHub user '{username}' was not found.")
        elif response.status_code == 403:
            # Rate limit notice
            reset_time = response.headers.get("X-RateLimit-Reset", "")
            raise RuntimeError(
                f"GitHub API rate limit reached. Reset timestamp: {reset_time}. Please try again later."
            )
        response.raise_for_status()

        repos_page = response.json()
        if not isinstance(repos_page, list) or len(repos_page) == 0:
            break

        all_repos.extend(repos_page)
        if len(repos_page) < 100:
            break
        page += 1

    return all_repos


def fetch_repo_readme(username: str, repo_name: str) -> Optional[str]:
    """
    Fetches the README file for a repository and base64-decodes it to plain text.
    Returns None if the repo has no README (HTTP 404).
    """
    headers = {
        "User-Agent": GITHUB_USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/readme"
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

    if response.status_code == 404:
        return None
    response.raise_for_status()

    data = response.json()
    content_b64 = data.get("content", "")
    if not content_b64:
        return None

    try:
        decoded_bytes = base64.b64decode(content_b64)
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Local LLM Fact Extraction (Ollama)
# ---------------------------------------------------------------------------
def evaluate_repo_for_facts(
    repo: Dict[str, Any],
    readme_text: str,
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> Dict[str, Any]:
    """
    Evaluates a repository using Ollama structured output.
    Returns: {"worth_including": bool, "tags": list[str], "text": str}
    """
    # Truncate README text to ~3000 chars to keep context tight and fast
    truncated_readme = (
        readme_text[:3000].rstrip() + "..." if len(readme_text) > 3000 else readme_text
    )

    repo_context = {
        "name": repo.get("name", ""),
        "description": repo.get("description", "") or "",
        "language": repo.get("language", "") or "",
        "topics": repo.get("topics", []) or [],
        "stargazers_count": repo.get("stargazers_count", 0),
        "readme_content": truncated_readme,
    }

    system_prompt = (
        "You are an expert technical resume architect. Evaluate public GitHub repositories and extract authentic, "
        "verifiable technical accomplishment sentences for a candidate's career fact_bank.\n\n"
        "STRICT EVALUATION INSTRUCTIONS:\n"
        "1. Set worth_including to false if this looks like a tutorial follow-along, a course exercise, or a near-empty scaffold with no real independent work -- judge from the README content and depth, not just the repo name.\n"
        "2. Never state a metric, user count, performance number, or impact claim that is not explicitly written in the README. If the README doesn't state scale or impact, describe what was technically built instead -- do not estimate or invent numbers.\n"
        "3. Write text in the same voice as a resume bullet: specific and concrete, not marketing language.\n"
        "4. In tags, include only programming languages, frameworks, libraries, tools, and technical concepts actually evidenced in the repository."
    )

    user_prompt = f"""[REPOSITORY DATA]
{json.dumps(repo_context, indent=2)}

Evaluate this repository and provide structured JSON output adhering to the schema."""

    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": GITHUB_FACT_SCHEMA,
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
# Core Generation Function
# ---------------------------------------------------------------------------
def generate_repo_facts(
    username: str,
    profile: Dict[str, Any],
    db_path: str = DB_FILENAME,
    model_name: str = MODEL_NAME,
    ollama_url: str = OLLAMA_URL,
) -> List[Dict[str, Any]]:
    """
    Main function to process public GitHub repos and generate candidate facts.
    Returns list of newly created candidate entries.
    """
    if not username or not username.strip():
        raise ValueError("GitHub username is empty or missing.")

    conn = sqlite3.connect(db_path)
    init_github_tables(conn)

    print(f"Fetching public repositories for GitHub user: @{username}...")
    repos = fetch_public_repos(username.strip())
    print(f"Found {len(repos)} total public repositories.\n")

    created_candidates: List[Dict[str, Any]] = []
    skipped_hard_filters = 0
    skipped_cached = 0
    skipped_model = 0

    for idx, repo in enumerate(repos, start=1):
        name = repo.get("name", "")
        pushed_at = repo.get("pushed_at", "")
        html_url = repo.get("html_url", "")
        language = repo.get("language") or ""
        is_fork = repo.get("fork", False)
        is_archived = repo.get("archived", False)

        print(f"[{idx}/{len(repos)}] Processing repo: {name} ... ", end="", flush=True)

        # 1. Hard filters
        if is_fork:
            skipped_hard_filters += 1
            print("[SKIPPED] (forked repository)")
            continue

        if is_archived:
            skipped_hard_filters += 1
            print("[SKIPPED] (archived repository)")
            continue

        # 2. Cache check
        if pushed_at and is_repo_cached(conn, name, pushed_at):
            skipped_cached += 1
            print("[CACHED] (unchanged since last run)")
            continue

        # 3. Fetch README
        readme_text = fetch_repo_readme(username.strip(), name)
        if not readme_text or not readme_text.strip():
            skipped_hard_filters += 1
            update_repo_cache(conn, name, pushed_at)
            print("[SKIPPED] (no README found)")
            continue

        # 4. Model Evaluation
        try:
            eval_result = evaluate_repo_for_facts(
                repo=repo,
                readme_text=readme_text,
                model_name=model_name,
                ollama_url=ollama_url,
            )
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            print("\n" + "!" * 65)
            print(f"[OLLAMA CONNECTION ERROR] {e}")
            print("Stopping remaining repository processing.")
            print("!" * 65)
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            continue

        # Update cache for this repo
        update_repo_cache(conn, name, pushed_at)

        worth_including = eval_result.get("worth_including", False)
        fact_text = (eval_result.get("text") or "").strip()
        tags_list = eval_result.get("tags") or []
        tags_str = ", ".join(str(t).strip() for t in tags_list if str(t).strip())

        if not worth_including or not fact_text:
            skipped_model += 1
            print("[SKIPPED by model] (classified as tutorial/scaffold/insubstantial)")
            continue

        # 5. Save candidate fact
        row_id = save_fact_candidate(
            conn=conn,
            repo_name=name,
            repo_url=html_url,
            language=language,
            tags=tags_str,
            text=fact_text,
        )

        candidate_item = {
            "id": row_id,
            "repo_name": name,
            "repo_url": html_url,
            "language": language,
            "tags": tags_str,
            "text": fact_text,
        }
        created_candidates.append(candidate_item)
        print(f"[CANDIDATE CREATED: ID #{row_id}]")
        print(f"    Tags: {tags_str}")
        print(f"    Text: \"{fact_text}\"\n")

    conn.close()

    return created_candidates


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------
def run_cli():
    print("=" * 65)
    print("  GitHub Repository Fact Extractor (Unauthenticated / Read-Only)")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_path = os.path.join(base_dir, PROFILE_FILENAME)
    db_path = os.path.join(base_dir, DB_FILENAME)

    if not os.path.exists(profile_path):
        print(f"[ERROR] '{profile_path}' not found. Run score_jobs.py or create profile.json first.")
        sys.exit(1)

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read {profile_path}: {e}")
        sys.exit(1)

    candidate_info = profile.get("candidate", {})
    github_username = candidate_info.get("github_username", "") or ""

    if not github_username.strip():
        print("=" * 65)
        print("[ERROR] 'candidate.github_username' is missing or empty in profile.json.")
        print(f"        Please add your GitHub username to '{profile_path}':")
        print('        "candidate": { "github_username": "your-username", ... }')
        print("=" * 65)
        sys.exit(1)

    print(f"Target Database : {db_path}")
    print(f"Model Name      : {MODEL_NAME}")
    print(f"GitHub Username : @{github_username}\n")

    try:
        candidates = generate_repo_facts(
            username=github_username,
            profile=profile,
            db_path=db_path,
            model_name=MODEL_NAME,
        )
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        sys.exit(1)

    print("=" * 65)
    print(f"Execution Summary: {len(candidates)} candidate fact(s) generated.")
    print("=" * 65)
    print("\nTo inspect pending fact candidates in SQLite, run:")
    print(
        f'sqlite3 "{DB_FILENAME}" '
        f'"SELECT id, repo_name, tags, text FROM github_fact_candidates WHERE status = \'pending\';"'
    )
    print(
        "\nNote: Review this list and manually copy your chosen entries into\n"
        "profile.json's 'fact_bank' (e.g. assigning IDs like f002, f003) --\n"
        "this script only proposes facts, it never modifies profile.json directly.\n"
    )


if __name__ == "__main__":
    run_cli()
