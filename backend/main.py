"""
backend/main.py - FastAPI Application for Local Job Search Tool

Reads and writes jobs.db, integrates with local Ollama scoring and drafting pipelines,
and provides job lifecycle tracking and status management.

Note on Network Exposure:
The server binds to 0.0.0.0:8000 so it can be reached across private Tailscale network
devices. Exposure is gated by Tailscale's private network (tailnet), not by anything in
this app -- no public internet exposure is expected or supported here.
"""

import datetime
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Add parent directory to sys.path to allow importing root modules directly
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Direct module imports -- no subprocess or shell-outs
from score_jobs import score_job
from draft_materials import draft_materials, load_and_validate_profile

# ---------------------------------------------------------------------------
# Configuration & Environment
# ---------------------------------------------------------------------------
JOBS_DB_PATH = os.environ.get(
    "JOBS_DB_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "jobs.db")),
)
PROFILE_PATH = os.environ.get(
    "PROFILE_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "profile.json")),
)
FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN",
    "http://localhost:3000,http://127.0.0.1:3000",
)

# Parse origins for CORS (supports comma-separated list or wildcard)
if FRONTEND_ORIGIN.strip() == "*":
    CORS_ORIGINS = ["*"]
else:
    CORS_ORIGINS = [o.strip() for o in FRONTEND_ORIGIN.split(",") if o.strip()]

app = FastAPI(
    title="Local Job Search Tool API",
    description="Personal local-only job sourcing, Ollama scoring, material drafting, and tracking API.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    """Creates a connection to SQLite jobs.db with Row factory."""
    if not os.path.exists(JOBS_DB_PATH):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database file not found at '{JOBS_DB_PATH}'. Run source_jobs.py first.",
        )
    conn = sqlite3.connect(JOBS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_job_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts a SQLite Row into a dictionary with a synthesized unified 'id'."""
    d = dict(row)
    d["id"] = f"{d['source']}:{d['external_id']}"
    return d


def find_job_or_404(conn: sqlite3.Connection, job_id: str) -> Dict[str, Any]:
    """
    Finds a job by composite id ('source:external_id') or by external_id.
    Raises 404 if not found.
    """
    cursor = conn.cursor()
    if ":" in job_id:
        source, ext_id = job_id.split(":", 1)
        cursor.execute(
            "SELECT * FROM jobs WHERE source = ? AND external_id = ?",
            (source, ext_id),
        )
    else:
        cursor.execute(
            "SELECT * FROM jobs WHERE external_id = ? OR (source || ':' || external_id) = ?",
            (job_id, job_id),
        )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' was not found.",
        )
    return row_to_job_dict(row)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class JobResponse(BaseModel):
    id: str
    source: str
    external_id: str
    title: Optional[str] = None
    company: Optional[str] = None
    url: Optional[str] = None
    apply_url: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[str] = None
    fetched_at: Optional[str] = None
    fit_score: Optional[int] = None
    fit_reasoning: Optional[str] = None
    fit_flags: Optional[str] = None
    status: str
    materials_resume_bullets: Optional[str] = None
    materials_cover_letter: Optional[str] = None
    applied_at: Optional[str] = None
    follow_up_sent_at: Optional[str] = None
    notes: Optional[str] = None


class MaterialsPatchRequest(BaseModel):
    resume_bullets: Optional[Union[List[Dict[str, Any]], str]] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None


class DraftMaterialsResponse(BaseModel):
    job: JobResponse
    resume_bullets: List[Dict[str, Any]]
    cover_letter: str


class StatsResponse(BaseModel):
    total_jobs: int
    counts_by_status: Dict[str, int]
    average_fit_score: Optional[float] = None


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "db_path": JOBS_DB_PATH}


@app.get("/stats", response_model=StatsResponse, tags=["Analytics"])
def get_stats():
    """
    Returns aggregate counts of jobs per status, plus the average fit_score
    of scored jobs.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Count total jobs
        cursor.execute("SELECT COUNT(*) FROM jobs")
        total_jobs = cursor.fetchone()[0] or 0

        # Counts by status
        cursor.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        rows = cursor.fetchall()
        counts_by_status = {r[0]: r[1] for r in rows}

        # Average fit_score for scored jobs
        cursor.execute(
            "SELECT AVG(fit_score) FROM jobs WHERE fit_score IS NOT NULL AND status != 'skipped'"
        )
        avg_row = cursor.fetchone()
        avg_fit_score = round(float(avg_row[0]), 2) if avg_row and avg_row[0] is not None else None

        return StatsResponse(
            total_jobs=total_jobs,
            counts_by_status=counts_by_status,
            average_fit_score=avg_fit_score,
        )
    finally:
        conn.close()


@app.get("/jobs/followups", response_model=List[JobResponse], tags=["Tracking"])
def get_followups():
    """
    Lists jobs where status = 'applied', applied_at is older than 7 days,
    and follow_up_sent_at IS NULL.
    """
    conn = get_db_connection()
    try:
        cutoff_date = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        ).isoformat()

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'applied'
              AND applied_at IS NOT NULL
              AND applied_at <= ?
              AND follow_up_sent_at IS NULL
            ORDER BY applied_at ASC
            """,
            (cutoff_date,),
        )
        rows = cursor.fetchall()
        return [row_to_job_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/jobs", response_model=List[JobResponse], tags=["Jobs"])
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter jobs by status"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
):
    """
    Lists jobs optionally filtered by status, ordered by fit_score DESC and fetched_at DESC.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END, fit_score DESC, fetched_at DESC
                LIMIT ? OFFSET ?
                """,
                (status_filter, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM jobs
                ORDER BY CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END, fit_score DESC, fetched_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        rows = cursor.fetchall()
        return [row_to_job_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/jobs/{id:path}", response_model=JobResponse, tags=["Jobs"])
def get_job(id: str):
    """Returns the full row for one job."""
    conn = get_db_connection()
    try:
        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/approve", response_model=JobResponse, tags=["Review"])
def approve_job(id: str):
    """
    Transitions job status: scored -> approved.
    Returns 409 if status is not 'scored'.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] != "scored":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve job with status '{job['status']}'. Job status must be 'scored'.",
            )

        with conn:
            conn.execute(
                "UPDATE jobs SET status = 'approved' WHERE source = ? AND external_id = ?",
                (job["source"], job["external_id"]),
            )

        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/skip", response_model=JobResponse, tags=["Review"])
def skip_job(id: str):
    """
    Transitions job status: scored -> skipped.
    Returns 409 if status is not 'scored'.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] != "scored":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot skip job with status '{job['status']}'. Job status must be 'scored'.",
            )

        with conn:
            conn.execute(
                "UPDATE jobs SET status = 'skipped' WHERE source = ? AND external_id = ?",
                (job["source"], job["external_id"]),
            )

        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/draft-materials", response_model=DraftMaterialsResponse, tags=["Materials"])
def draft_job_materials(id: str):
    """
    Calls draft_materials() using profile.json and Ollama, stores the result,
    sets status = 'materials_ready', and returns the draft.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] not in ("approved", "materials_ready"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot draft materials for job with status '{job['status']}'. Job must be 'approved' or 'materials_ready'.",
            )

        profile = load_and_validate_profile(PROFILE_PATH)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Profile file '{PROFILE_PATH}' is missing or contains an empty fact_bank.",
            )

        try:
            materials = draft_materials(job, profile)
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ollama service error: {e}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to draft materials: {e}",
            )

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
                (bullets_json, cover_letter_text, job["source"], job["external_id"]),
            )

        updated_job = find_job_or_404(conn, id)
        return DraftMaterialsResponse(
            job=JobResponse(**updated_job),
            resume_bullets=materials["resume_bullets"],
            cover_letter=cover_letter_text,
        )
    finally:
        conn.close()


@app.patch("/jobs/{id:path}/materials", response_model=JobResponse, tags=["Materials"])
def update_job_materials(id: str, payload: MaterialsPatchRequest):
    """
    Overwrites stored materials_resume_bullets and/or materials_cover_letter with user edits.
    Status remains unchanged.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)

        updates = []
        params = []

        if payload.resume_bullets is not None:
            if isinstance(payload.resume_bullets, str):
                bullets_str = payload.resume_bullets
            else:
                bullets_str = json.dumps(payload.resume_bullets)
            updates.append("materials_resume_bullets = ?")
            params.append(bullets_str)

        if payload.cover_letter is not None:
            updates.append("materials_cover_letter = ?")
            params.append(payload.cover_letter)

        if payload.notes is not None:
            updates.append("notes = ?")
            params.append(payload.notes)

        if updates:
            params.extend([job["source"], job["external_id"]])
            query = f"UPDATE jobs SET {', '.join(updates)} WHERE source = ? AND external_id = ?"
            with conn:
                conn.execute(query, tuple(params))

        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/approve-materials", response_model=JobResponse, tags=["Materials"])
def approve_materials(id: str):
    """
    Transitions job status: materials_ready -> ready_to_apply.
    Returns 409 if status is not 'materials_ready'.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] != "materials_ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve materials for job with status '{job['status']}'. Status must be 'materials_ready'.",
            )

        with conn:
            conn.execute(
                "UPDATE jobs SET status = 'ready_to_apply' WHERE source = ? AND external_id = ?",
                (job["source"], job["external_id"]),
            )

        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/mark-applied", response_model=JobResponse, tags=["Tracking"])
def mark_applied(id: str):
    """
    Transitions job status: ready_to_apply -> applied, setting applied_at = now (UTC).
    Returns 409 if status is not 'ready_to_apply'.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] != "ready_to_apply":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot mark job as applied with status '{job['status']}'. Status must be 'ready_to_apply'.",
            )

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            conn.execute(
                "UPDATE jobs SET status = 'applied', applied_at = ? WHERE source = ? AND external_id = ?",
                (now_utc, job["source"], job["external_id"]),
            )

        return find_job_or_404(conn, id)
    finally:
        conn.close()


@app.post("/jobs/{id:path}/mark-followed-up", response_model=JobResponse, tags=["Tracking"])
def mark_followed_up(id: str):
    """
    Sets follow_up_sent_at = now (UTC) for an applied job.
    Returns 409 if status is not 'applied'.
    """
    conn = get_db_connection()
    try:
        job = find_job_or_404(conn, id)
        if job["status"] != "applied":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot mark follow-up for job with status '{job['status']}'. Status must be 'applied'.",
            )

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            conn.execute(
                "UPDATE jobs SET follow_up_sent_at = ? WHERE source = ? AND external_id = ?",
                (now_utc, job["source"], job["external_id"]),
            )

        return find_job_or_404(conn, id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Binds to 0.0.0.0 for Tailscale private network accessibility
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
