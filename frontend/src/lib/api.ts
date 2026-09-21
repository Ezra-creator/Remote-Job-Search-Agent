/**
 * lib/api.ts - Typed API Client for Local Job Search Tool Backend
 *
 * All API calls use the base URL from NEXT_PUBLIC_API_BASE (e.g. over Tailscale or localhost).
 */

export interface Job {
  id: string;
  source: string;
  external_id: string;
  title: string | null;
  company: string | null;
  url: string | null;
  apply_url: string | null;
  location: string | null;
  tags: string | null;
  salary: string | null;
  description: string | null;
  posted_at: string | null;
  fetched_at: string | null;
  fit_score: number | null;
  fit_reasoning: string | null;
  fit_flags: string | null;
  status:
    | "new"
    | "scored"
    | "skipped"
    | "approved"
    | "materials_ready"
    | "ready_to_apply"
    | "applied";
  materials_resume_bullets: string | null;
  materials_cover_letter: string | null;
  applied_at: string | null;
  follow_up_sent_at: string | null;
  notes: string | null;
}

export interface Stats {
  total_jobs: number;
  counts_by_status: Record<string, number>;
  average_fit_score: number | null;
}

export interface ResumeBullet {
  id: string;
  text: string;
}

export interface DraftMaterialsResponse {
  job: Job;
  resume_bullets: ResumeBullet[];
  cover_letter: string;
}

export interface MaterialsPatchRequest {
  resume_bullets?: ResumeBullet[] | string;
  cover_letter?: string;
  notes?: string;
}

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err: any) {
    throw new Error(
      `Could not reach backend at ${API_BASE}. Make sure the FastAPI backend is running.`
    );
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    try {
      const errorData = await res.json();
      if (errorData.detail) {
        errorDetail = errorData.detail;
      }
    } catch {
      // Non-JSON error payload
    }
    throw new Error(errorDetail);
  }
  return res.json() as Promise<T>;
}

/**
 * Fetch aggregate job stats and counts
 */
export async function getStats(): Promise<Stats> {
  const res = await apiFetch(`${API_BASE}/stats`, { cache: "no-store" });
  return handleResponse<Stats>(res);
}

/**
 * List jobs optionally filtered by status
 */
export async function getJobs(status?: string, limit = 100, offset = 0): Promise<Job[]> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  params.append("limit", limit.toString());
  params.append("offset", offset.toString());

  const res = await apiFetch(`${API_BASE}/jobs?${params.toString()}`, {
    cache: "no-store",
  });
  return handleResponse<Job[]>(res);
}

/**
 * Get full details for a single job
 */
export async function getJob(id: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  return handleResponse<Job>(res);
}

/**
 * Transition status: scored -> approved
 */
export async function approveJob(id: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(id)}/approve`, {
    method: "POST",
  });
  return handleResponse<Job>(res);
}

/**
 * Transition status: scored -> skipped
 */
export async function skipJob(id: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(id)}/skip`, {
    method: "POST",
  });
  return handleResponse<Job>(res);
}

/**
 * Generate tailored resume bullets & cover letter using Ollama
 */
export async function draftMaterials(id: string): Promise<DraftMaterialsResponse> {
  const res = await apiFetch(
    `${API_BASE}/jobs/${encodeURIComponent(id)}/draft-materials`,
    {
      method: "POST",
    }
  );
  return handleResponse<DraftMaterialsResponse>(res);
}

/**
 * Save manual edits to resume bullets or cover letter without changing status
 */
export async function updateMaterials(
  id: string,
  payload: MaterialsPatchRequest
): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(id)}/materials`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<Job>(res);
}

/**
 * Transition status: materials_ready -> ready_to_apply
 */
export async function approveMaterials(id: string): Promise<Job> {
  const res = await apiFetch(
    `${API_BASE}/jobs/${encodeURIComponent(id)}/approve-materials`,
    {
      method: "POST",
    }
  );
  return handleResponse<Job>(res);
}

/**
 * Transition status: ready_to_apply -> applied (timestamps applied_at)
 */
export async function markApplied(id: string): Promise<Job> {
  const res = await apiFetch(
    `${API_BASE}/jobs/${encodeURIComponent(id)}/mark-applied`,
    {
      method: "POST",
    }
  );
  return handleResponse<Job>(res);
}

/**
 * Get jobs applied > 7 days ago without follow-up
 */
export async function getFollowups(): Promise<Job[]> {
  const res = await apiFetch(`${API_BASE}/jobs/followups`, { cache: "no-store" });
  return handleResponse<Job[]>(res);
}

/**
 * Mark follow up as sent (timestamps follow_up_sent_at)
 */
export async function markFollowedUp(id: string): Promise<Job> {
  const res = await apiFetch(
    `${API_BASE}/jobs/${encodeURIComponent(id)}/mark-followed-up`,
    {
      method: "POST",
    }
  );
  return handleResponse<Job>(res);
}
