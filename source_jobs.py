"""
source_jobs.py - Personal Local-Only Job Search Sourcing Tool

Fetches remote job postings from 6 public APIs / RSS feeds, normalizes them
into a unified schema, and stores them in a local SQLite database (jobs.db).
Deduplicates strictly on (source, external_id) so existing records are never
overwritten or duplicated.
"""

import datetime
import html
from html.parser import HTMLParser
import logging
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import requests

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
DB_FILENAME = "jobs.db"
REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 JobSearchTool/1.0"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html, application/xml, text/xml, */*",
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    company TEXT,
    url TEXT,
    apply_url TEXT,
    location TEXT,
    tags TEXT,
    salary TEXT,
    description TEXT,
    posted_at TEXT,
    fetched_at TEXT,
    fit_score INTEGER,
    fit_reasoning TEXT,
    fit_flags TEXT,
    status TEXT DEFAULT 'new',
    materials_resume_bullets TEXT,
    materials_cover_letter TEXT,
    applied_at TEXT,
    follow_up_sent_at TEXT,
    notes TEXT,
    PRIMARY KEY (source, external_id)
);
"""

INSERT_JOB_SQL = """
INSERT OR IGNORE INTO jobs (
    source,
    external_id,
    title,
    company,
    url,
    apply_url,
    location,
    tags,
    salary,
    description,
    posted_at,
    fetched_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""


# ---------------------------------------------------------------------------
# Text & HTML Helper Utilities
# ---------------------------------------------------------------------------
class HTMLTextExtractor(HTMLParser):
    """HTML parser that extracts text while preserving reasonable spacing/breaks."""

    def __init__(self):
        super().__init__()
        self.result: List[str] = []

    def handle_data(self, data: str):
        self.result.append(data)

    def handle_starttag(self, tag: str, attrs: list):
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "hr"):
            self.result.append("\n")

    def handle_endtag(self, tag: str):
        if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self.result.append("\n")

    def get_text(self) -> str:
        raw = "".join(self.result)
        # Normalize whitespace while preserving paragraphs
        raw = html.unescape(raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def strip_html(raw_html: Optional[str], max_length: int = 3000) -> str:
    """Strips HTML tags, decodes HTML entities, and truncates to max_length."""
    if not raw_html or not isinstance(raw_html, str):
        return ""
    try:
        parser = HTMLTextExtractor()
        parser.feed(raw_html)
        text = parser.get_text()
    except Exception:
        # Fallback to regex stripping if HTMLParser encounters malformed input
        text = re.sub(r"<[^>]+>", " ", raw_html)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."
    return text


def format_tags(tags: Any) -> str:
    """Converts various tag formats (list of strings/dicts or string) into a clean comma-joined string."""
    if not tags:
        return ""
    if isinstance(tags, str):
        return tags.strip()
    if isinstance(tags, (list, tuple, set)):
        cleaned = []
        for t in tags:
            if isinstance(t, str) and t.strip():
                cleaned.append(t.strip())
            elif isinstance(t, dict):
                # e.g., feedparser tag dicts: {'term': 'python'}
                term = t.get("term") or t.get("name") or ""
                if term and str(term).strip():
                    cleaned.append(str(term).strip())
        return ", ".join(cleaned)
    return str(tags)


def format_location(loc: Any) -> str:
    """Formats location list or string."""
    if not loc:
        return ""
    if isinstance(loc, (list, tuple)):
        return ", ".join(str(item).strip() for item in loc if str(item).strip())
    return str(loc).strip()


def format_salary(
    min_sal: Any = None,
    max_sal: Any = None,
    currency: Optional[str] = None,
    period: Optional[str] = None,
    raw_salary: Optional[str] = None,
) -> str:
    """Normalizes and formats salary fields into a readable string."""
    if raw_salary and str(raw_salary).strip():
        return str(raw_salary).strip()

    curr = currency.strip() if currency else "$"
    per = f"/{period.strip()}" if period else ""

    try:
        min_val = int(float(min_sal)) if min_sal is not None and str(min_sal).strip() != "" else None
        if min_val == 0:
            min_val = None
    except (ValueError, TypeError):
        min_val = None

    try:
        max_val = int(float(max_sal)) if max_sal is not None and str(max_sal).strip() != "" else None
        if max_val == 0:
            max_val = None
    except (ValueError, TypeError):
        max_val = None

    if min_val is not None and max_val is not None:
        if min_val == max_val:
            return f"{curr}{min_val:,}{per}"
        return f"{curr}{min_val:,} - {curr}{max_val:,}{per}"
    elif min_val is not None:
        return f"{curr}{min_val:,}+{per}"
    elif max_val is not None:
        return f"Up to {curr}{max_val:,}{per}"

    return ""


# ---------------------------------------------------------------------------
# Database Management
# ---------------------------------------------------------------------------
def init_db(db_path: str = DB_FILENAME) -> sqlite3.Connection:
    """Initializes SQLite database and creates the jobs table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(CREATE_TABLE_SQL)
    return conn


def save_job(conn: sqlite3.Connection, job: Dict[str, Any]) -> bool:
    """
    Inserts a job into the database if (source, external_id) is not already present.
    Returns True if a new row was inserted, False if it was ignored (already exists).
    """
    cursor = conn.cursor()
    cursor.execute(
        INSERT_JOB_SQL,
        (
            job.get("source"),
            str(job.get("external_id")),
            job.get("title"),
            job.get("company"),
            job.get("url"),
            job.get("apply_url") or job.get("url"),
            job.get("location"),
            job.get("tags"),
            job.get("salary"),
            job.get("description"),
            job.get("posted_at"),
            job.get("fetched_at"),
        ),
    )
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Source Fetchers
# ---------------------------------------------------------------------------
def fetch_remotive(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 1: Remotive (https://remotive.com/api/remote-jobs)
    """
    source_name = "remotive"
    url = "https://remotive.com/api/remote-jobs"
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    raw_jobs = data.get("jobs", [])
    fetched_count = len(raw_jobs)
    new_count = 0

    with conn:
        for item in raw_jobs:
            ext_id = item.get("id")
            if not ext_id:
                continue

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": item.get("title") or "",
                "company": item.get("company_name") or "",
                "url": item.get("url") or "",
                "apply_url": item.get("url") or "",
                "location": item.get("candidate_required_location") or "",
                "tags": format_tags(item.get("tags")),
                "salary": format_salary(raw_salary=item.get("salary")),
                "description": strip_html(item.get("description")),
                "posted_at": item.get("publication_date") or "",
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


def fetch_remoteok(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 2: RemoteOK (https://remoteok.com/api)
    Note: First element is a legal disclaimer and must be skipped.
    """
    source_name = "remoteok"
    url = "https://remoteok.com/api"
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        return 0, 0

    # Skip first element if it's the legal notice / disclaimer
    raw_jobs = data[1:] if len(data) > 1 else []
    fetched_count = len(raw_jobs)
    new_count = 0

    with conn:
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue

            ext_id = item.get("id") or item.get("slug")
            if not ext_id:
                continue

            job_url = item.get("url") or ""
            apply_url = item.get("apply_url") or job_url

            salary_str = format_salary(
                min_sal=item.get("salary_min"),
                max_sal=item.get("salary_max"),
            )

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": item.get("position") or item.get("title") or "",
                "company": item.get("company") or "",
                "url": job_url,
                "apply_url": apply_url,
                "location": item.get("location") or "",
                "tags": format_tags(item.get("tags")),
                "salary": salary_str,
                "description": strip_html(item.get("description")),
                "posted_at": item.get("date") or "",
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


def fetch_arbeitnow(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 3: Arbeitnow (https://www.arbeitnow.com/api/job-board-api)
    Note: Must skip any jobs where remote is False.
    """
    source_name = "arbeitnow"
    url = "https://www.arbeitnow.com/api/job-board-api"
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    raw_jobs = data.get("data", [])
    fetched_count = 0
    new_count = 0

    with conn:
        for item in raw_jobs:
            # Skip non-remote jobs
            if not item.get("remote", False):
                continue

            fetched_count += 1
            ext_id = item.get("slug")
            if not ext_id:
                continue

            posted_at = str(item.get("created_at") or "")
            # Convert epoch integer to ISO string if applicable
            if posted_at.isdigit():
                try:
                    posted_at = datetime.datetime.fromtimestamp(
                        int(posted_at), tz=datetime.timezone.utc
                    ).isoformat()
                except Exception:
                    pass

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": item.get("title") or "",
                "company": item.get("company_name") or "",
                "url": item.get("url") or "",
                "apply_url": item.get("url") or "",
                "location": item.get("location") or "Remote",
                "tags": format_tags(item.get("tags")),
                "salary": "",
                "description": strip_html(item.get("description")),
                "posted_at": posted_at,
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


def fetch_himalayas(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 4: Himalayas (https://himalayas.app/jobs/api)
    """
    source_name = "himalayas"
    url = "https://himalayas.app/jobs/api"
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
    fetched_count = len(raw_jobs)
    new_count = 0

    with conn:
        for item in raw_jobs:
            ext_id = item.get("guid") or item.get("applicationLink") or item.get("id")
            if not ext_id:
                continue

            job_url = item.get("guid") or item.get("applicationLink") or ""
            apply_url = item.get("applicationLink") or job_url

            # Salary parsing
            salary_str = format_salary(
                min_sal=item.get("minSalary"),
                max_sal=item.get("maxSalary"),
                currency=item.get("currency"),
                period=item.get("salaryPeriod"),
            )

            # Tags combine categories and seniority if present
            tags_list = []
            if item.get("categories"):
                tags_list.extend(item.get("categories") if isinstance(item.get("categories"), list) else [item.get("categories")])
            if item.get("seniority"):
                tags_list.extend(item.get("seniority") if isinstance(item.get("seniority"), list) else [item.get("seniority")])

            # Description fallback
            raw_desc = item.get("description") or item.get("excerpt") or ""

            posted_at = str(item.get("pubDate") or "")
            if posted_at.isdigit():
                try:
                    posted_at = datetime.datetime.fromtimestamp(
                        int(posted_at), tz=datetime.timezone.utc
                    ).isoformat()
                except Exception:
                    pass

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": item.get("title") or "",
                "company": item.get("companyName") or "",
                "url": job_url,
                "apply_url": apply_url,
                "location": format_location(item.get("locationRestrictions")),
                "tags": format_tags(tags_list),
                "salary": salary_str,
                "description": strip_html(raw_desc),
                "posted_at": posted_at,
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


def fetch_jobicy(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 5: Jobicy (https://jobicy.com/api/v2/remote-jobs?count=50)
    """
    source_name = "jobicy"
    url = "https://jobicy.com/api/v2/remote-jobs?count=50"
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
    fetched_count = len(raw_jobs)
    new_count = 0

    with conn:
        for item in raw_jobs:
            ext_id = item.get("id") or item.get("jobSlug")
            if not ext_id:
                continue

            job_url = item.get("url") or ""

            salary_str = format_salary(
                min_sal=item.get("annualSalaryMin"),
                max_sal=item.get("annualSalaryMax"),
                currency=item.get("salaryCurrency"),
                period="annual" if item.get("annualSalaryMin") or item.get("annualSalaryMax") else None,
            )

            # Tags combine industry, type, level
            tags_list = []
            if item.get("jobIndustry"):
                tags_list.extend(item["jobIndustry"] if isinstance(item["jobIndustry"], list) else [item["jobIndustry"]])
            if item.get("jobType"):
                tags_list.extend(item["jobType"] if isinstance(item["jobType"], list) else [item["jobType"]])
            if item.get("jobLevel"):
                tags_list.append(item["jobLevel"])

            raw_desc = item.get("jobDescription") or item.get("jobExcerpt") or ""

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": item.get("jobTitle") or "",
                "company": item.get("companyName") or "",
                "url": job_url,
                "apply_url": job_url,
                "location": format_location(item.get("jobGeo")),
                "tags": format_tags(tags_list),
                "salary": salary_str,
                "description": strip_html(raw_desc),
                "posted_at": item.get("pubDate") or "",
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


def fetch_weworkremotely(conn: sqlite3.Connection, fetched_at: str) -> Tuple[int, int]:
    """
    Source 6: We Work Remotely RSS Feed
    (https://weworkremotely.com/categories/remote-programming-jobs.rss)
    """
    source_name = "weworkremotely"
    rss_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

    feed = feedparser.parse(rss_url, request_headers=REQUEST_HEADERS)
    raw_entries = getattr(feed, "entries", [])
    fetched_count = len(raw_entries)
    new_count = 0

    with conn:
        for entry in raw_entries:
            ext_id = entry.get("id") or entry.get("guid") or entry.get("link")
            if not ext_id:
                continue

            raw_title = entry.get("title", "")
            company = ""
            title = raw_title
            # WWR titles are usually formatted as "Company: Job Title"
            if ": " in raw_title:
                parts = raw_title.split(": ", 1)
                company = parts[0].strip()
                title = parts[1].strip()

            job_url = entry.get("link") or ""
            location = entry.get("region") or ""
            tags = format_tags(entry.get("tags"))
            raw_desc = entry.get("summary") or entry.get("description") or ""

            job_dict = {
                "source": source_name,
                "external_id": str(ext_id),
                "title": title,
                "company": company,
                "url": job_url,
                "apply_url": job_url,
                "location": location,
                "tags": tags,
                "salary": "",
                "description": strip_html(raw_desc),
                "posted_at": entry.get("published") or "",
                "fetched_at": fetched_at,
            }

            if save_job(conn, job_dict):
                new_count += 1

    return fetched_count, new_count


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print("  Remote Job Sourcing Tool - Sourcing Jobs to Local SQLite")
    print("=" * 65)

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_FILENAME)
    conn = init_db(db_path)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    sources = [
        ("Remotive", fetch_remotive),
        ("RemoteOK", fetch_remoteok),
        ("Arbeitnow", fetch_arbeitnow),
        ("Himalayas", fetch_himalayas),
        ("Jobicy", fetch_jobicy),
        ("We Work Remotely", fetch_weworkremotely),
    ]

    total_fetched = 0
    total_new = 0

    print(f"Target Database : {db_path}")
    print(f"Fetch Timestamp : {fetched_at}\n")

    for name, fetch_func in sources:
        try:
            fetched, new = fetch_func(conn, fetched_at)
            total_fetched += fetched
            total_new += new
            print(f"[{name:<17}] Fetched: {fetched:>4} | New inserted: {new:>4}")
        except Exception as e:
            print(f"[{name:<17}] ERROR: Failed to fetch ({e})")

    conn.close()

    print("\n" + "=" * 65)
    print(f"Summary: {total_fetched} total postings processed | {total_new} new jobs saved.")
    print("=" * 65)
    print("\nSample sqlite3 query to inspect newly sourced postings:")
    print(
        f'sqlite3 "{DB_FILENAME}" '
        f'"SELECT source, company, title, location, salary FROM jobs WHERE status = \'new\' LIMIT 10;"'
    )
    print()


if __name__ == "__main__":
    main()
