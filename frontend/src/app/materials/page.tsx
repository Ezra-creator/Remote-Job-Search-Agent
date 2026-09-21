"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getJobs,
  draftMaterials,
  updateMaterials,
  approveMaterials,
  Job,
} from "@/lib/api";
import {
  Check,
  FileText,
  RefreshCw,
  TriangleAlert,
  ExternalLink,
} from "lucide-react";

interface DraftState {
  bullets: string;
  coverLetter: string;
  isDrafting: boolean;
  isSaving: boolean;
  isApproving: boolean;
  savedMessage: string | null;
  expanded: boolean;
}

export default function MaterialsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftStates, setDraftStates] = useState<Record<string, DraftState>>({});

  const fetchJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      const [approvedList, readyList] = await Promise.all([
        getJobs("approved"),
        getJobs("materials_ready"),
      ]);
      const combined = [...approvedList, ...readyList];
      setJobs(combined);

      const initialStates: Record<string, DraftState> = {};
      combined.forEach((job) => {
        let bulletsFormatted = "";
        if (job.materials_resume_bullets) {
          try {
            const parsed = JSON.parse(job.materials_resume_bullets);
            if (Array.isArray(parsed)) {
              bulletsFormatted = parsed
                .map((b: any) => `- ${b.text || b}`)
                .join("\n\n");
            } else {
              bulletsFormatted = String(job.materials_resume_bullets);
            }
          } catch {
            bulletsFormatted = String(job.materials_resume_bullets);
          }
        }

        initialStates[job.id] = {
          bullets: bulletsFormatted,
          coverLetter: job.materials_cover_letter || "",
          isDrafting: false,
          isSaving: false,
          isApproving: false,
          savedMessage: null,
          expanded: job.status === "materials_ready",
        };
      });
      setDraftStates(initialStates);
    } catch (err: any) {
      setError(err.message || "Failed to load approved jobs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Application materials — RJS";
    fetchJobs();
  }, []);

  const handleDraftMaterials = async (job: Job) => {
    setDraftStates((prev) => ({
      ...prev,
      [job.id]: { ...prev[job.id], isDrafting: true, expanded: true },
    }));

    try {
      const response = await draftMaterials(job.id);
      const bulletsFormatted = response.resume_bullets
        .map((b) => `- ${b.text}`)
        .join("\n\n");

      setDraftStates((prev) => ({
        ...prev,
        [job.id]: {
          ...prev[job.id],
          bullets: bulletsFormatted,
          coverLetter: response.cover_letter,
          isDrafting: false,
          savedMessage: "Draft ready",
        },
      }));

      setJobs((prev) =>
        prev.map((j) =>
          j.id === job.id ? { ...j, status: "materials_ready" } : j
        )
      );
    } catch (err: any) {
      alert(`Failed to draft materials: ${err.message}`);
      setDraftStates((prev) => ({
        ...prev,
        [job.id]: { ...prev[job.id], isDrafting: false },
      }));
    }
  };

  const handleSaveMaterials = async (jobId: string) => {
    const state = draftStates[jobId];
    if (!state) return;

    setDraftStates((prev) => ({
      ...prev,
      [jobId]: { ...prev[jobId], isSaving: true, savedMessage: null },
    }));

    try {
      await updateMaterials(jobId, {
        resume_bullets: state.bullets,
        cover_letter: state.coverLetter,
      });

      setDraftStates((prev) => ({
        ...prev,
        [jobId]: {
          ...prev[jobId],
          isSaving: false,
          savedMessage: "Saved",
        },
      }));

      setTimeout(() => {
        setDraftStates((prev) => ({
          ...prev,
          [jobId]: { ...prev[jobId], savedMessage: null },
        }));
      }, 2500);
    } catch (err: any) {
      alert(`Failed to save materials: ${err.message}`);
      setDraftStates((prev) => ({
        ...prev,
        [jobId]: { ...prev[jobId], isSaving: false },
      }));
    }
  };

  const handleApproveMaterials = async (job: Job) => {
    setDraftStates((prev) => ({
      ...prev,
      [job.id]: { ...prev[job.id], isApproving: true },
    }));

    try {
      const state = draftStates[job.id];
      if (state) {
        await updateMaterials(job.id, {
          resume_bullets: state.bullets,
          cover_letter: state.coverLetter,
        });
      }

      await approveMaterials(job.id);
      setJobs((prev) => prev.filter((j) => j.id !== job.id));
    } catch (err: any) {
      alert(`Error approving materials: ${err.message}`);
      setDraftStates((prev) => ({
        ...prev,
        [job.id]: { ...prev[job.id], isApproving: false },
      }));
    }
  };

  const toggleExpand = (jobId: string) => {
    setDraftStates((prev) => ({
      ...prev,
      [jobId]: { ...prev[jobId], expanded: !prev[jobId]?.expanded },
    }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink font-sans">
            Application materials
          </h1>
          <p className="font-mono text-xs text-muted mt-0.5">
            {jobs.length > 0 ? `${jobs.length} approved jobs` : "No jobs waiting"}
          </p>
        </div>
        <button
          onClick={fetchJobs}
          disabled={loading}
          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
          aria-label="Refresh application materials"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="border border-warn bg-paper p-4 text-xs text-warn flex items-start gap-2.5" role="alert">
          <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5 text-warn" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-ink">Could not load materials</p>
            <p className="text-muted leading-relaxed">{error}</p>
          </div>
        </div>
      )}

      {loading ? (
        <div className="border border-line bg-paper p-12 text-center text-xs text-muted font-mono">
          Loading approved jobs...
        </div>
      ) : jobs.length === 0 ? (
        <div className="border border-line bg-paper p-10 text-center space-y-3">
          <div className="font-mono text-sm font-semibold text-ink">
            No approved jobs waiting for materials.
          </div>
          <p className="text-xs text-muted max-w-sm mx-auto font-sans">
            Approve scored jobs in Review queue to draft tailored resume bullets and cover letters.
          </p>
          <div className="flex justify-center gap-3 pt-2">
            <Link
              href="/review"
              className="rounded border border-accent bg-accent text-paper px-4 py-2 text-xs font-medium hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition font-sans"
            >
              Review queue
            </Link>
            <Link
              href="/applied"
              className="rounded border border-line bg-paper text-ink px-4 py-2 text-xs font-medium hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition font-sans"
            >
              Ready to apply
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {jobs.map((job) => {
            const state = draftStates[job.id] || {
              bullets: "",
              coverLetter: "",
              isDrafting: false,
              isSaving: false,
              isApproving: false,
              savedMessage: null,
              expanded: false,
            };

            const hasDraft =
              Boolean(state.bullets || state.coverLetter) ||
              job.status === "materials_ready";

            const isHighFit =
              job.fit_score !== null &&
              job.fit_score !== undefined &&
              job.fit_score >= 70;

            return (
              <div
                key={job.id}
                className="border border-line bg-paper p-5 sm:p-6 space-y-4"
              >
                {/* Row Header */}
                <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-line pb-3">
                  <div className="space-y-0.5">
                    <div className="font-mono text-xs text-ink flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-ink">
                        {job.company || "Unknown Company"}
                      </span>
                      {job.fit_score !== null && job.fit_score !== undefined && (
                        <>
                          <span className="text-muted">•</span>
                          <span className={isHighFit ? "text-accent font-semibold" : "text-ink"}>
                            Score: {job.fit_score}/100
                          </span>
                        </>
                      )}
                      {job.url && (
                        <>
                          <span className="text-muted">•</span>
                          <a
                            href={job.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 underline text-accent hover:text-accent/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded font-sans"
                            aria-label="Open job posting in new tab"
                          >
                            <span>Posting</span>
                            <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </a>
                        </>
                      )}
                    </div>
                    <h2 className="text-lg font-bold text-ink font-sans">
                      {job.title || "Untitled Position"}
                    </h2>
                  </div>

                  <div className="flex items-center gap-2">
                    {!hasDraft ? (
                      <button
                        onClick={() => handleDraftMaterials(job)}
                        disabled={state.isDrafting}
                        className="rounded border border-accent bg-accent text-paper px-3 py-1.5 text-xs font-medium hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
                        aria-label="Draft materials with Ollama"
                      >
                        <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{state.isDrafting ? "Drafting..." : "Draft materials"}</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => toggleExpand(job.id)}
                        className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition font-sans cursor-pointer"
                        aria-label={state.expanded ? "Hide application editor" : "Open application editor"}
                        aria-expanded={state.expanded}
                      >
                        {state.expanded ? "Hide editor" : "Open editor"}
                      </button>
                    )}
                  </div>
                </div>

                {/* Drafting in progress indicator */}
                {state.isDrafting && (
                  <div className="p-4 border border-line bg-paper text-xs font-mono text-muted flex items-center gap-2">
                    <RefreshCw className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden="true" />
                    <span>Generating tailored resume bullets and cover letter from fact_bank...</span>
                  </div>
                )}

                {/* Plain Document Textareas */}
                {hasDraft && state.expanded && !state.isDrafting && (
                  <div className="space-y-4 pt-1">
                    {state.savedMessage && (
                      <div className="font-mono text-xs text-accent font-medium flex items-center gap-1">
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{state.savedMessage}</span>
                      </div>
                    )}

                    {/* Resume Bullets Document Box */}
                    <div className="space-y-1">
                      <label
                        htmlFor={`bullets-${job.id}`}
                        className="block font-mono text-xs text-muted"
                      >
                        Resume bullets (fact_bank extract)
                      </label>
                      <textarea
                        id={`bullets-${job.id}`}
                        rows={5}
                        value={state.bullets}
                        onChange={(e) =>
                          setDraftStates((prev) => ({
                            ...prev,
                            [job.id]: { ...prev[job.id], bullets: e.target.value },
                          }))
                        }
                        onBlur={() => handleSaveMaterials(job.id)}
                        className="w-full rounded border border-line bg-paper p-4 text-xs font-mono leading-relaxed text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                        aria-label="Resume bullets draft"
                      />
                    </div>

                    {/* Cover Letter Document Box */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between font-mono text-xs text-muted">
                        <label htmlFor={`cover-${job.id}`} className="block">
                          Cover letter text
                        </label>
                        <span aria-live="polite">
                          {
                            state.coverLetter
                              .trim()
                              .split(/\s+/)
                              .filter(Boolean).length
                          }{" "}
                          words
                        </span>
                      </div>
                      <textarea
                        id={`cover-${job.id}`}
                        rows={10}
                        value={state.coverLetter}
                        onChange={(e) =>
                          setDraftStates((prev) => ({
                            ...prev,
                            [job.id]: {
                              ...prev[job.id],
                              coverLetter: e.target.value,
                            },
                          }))
                        }
                        onBlur={() => handleSaveMaterials(job.id)}
                        className="w-full rounded border border-line bg-paper p-4 text-xs font-sans leading-relaxed text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                        aria-label="Cover letter draft"
                      />
                    </div>

                    {/* Footer Actions */}
                    <div className="flex items-center justify-between pt-2 border-t border-line">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleSaveMaterials(job.id)}
                          disabled={state.isSaving}
                          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 font-sans cursor-pointer"
                          aria-label="Save draft changes"
                        >
                          {state.isSaving ? "Saving..." : "Save"}
                        </button>

                        <button
                          onClick={() => handleDraftMaterials(job)}
                          disabled={state.isDrafting}
                          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-muted hover:text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 font-sans flex items-center gap-1 cursor-pointer"
                          aria-label="Re-draft materials with Ollama"
                        >
                          <RefreshCw className={`h-3 w-3 ${state.isDrafting ? "animate-spin" : ""}`} aria-hidden="true" />
                          <span>Re-draft</span>
                        </button>
                      </div>

                      <button
                        onClick={() => handleApproveMaterials(job)}
                        disabled={state.isApproving}
                        className="rounded border border-accent bg-accent px-4 py-1.5 text-xs font-semibold text-paper hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition active:scale-98 disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
                        aria-label="Approve drafted materials and move to ready to apply"
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{state.isApproving ? "Approving..." : "Approve materials"}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
