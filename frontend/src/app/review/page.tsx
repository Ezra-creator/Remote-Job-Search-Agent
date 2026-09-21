"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getJobs, approveJob, skipJob, Job } from "@/lib/api";
import { Check, X, TriangleAlert, RefreshCw, ExternalLink } from "lucide-react";

export default function ReviewPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [animatingId, setAnimatingId] = useState<string | null>(null);
  const [animationClass, setAnimationClass] = useState<string>("");
  const [flashColor, setFlashColor] = useState<string>("");
  const [showFullDesc, setShowFullDesc] = useState(false);

  const fetchScoredJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJobs("scored");
      setJobs(data);
    } catch (err: any) {
      setError(err.message || "Failed to load scored jobs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Review queue — RJS";
    fetchScoredJobs();
  }, []);

  const handleApprove = async (job: Job) => {
    if (animatingId) return;
    setAnimatingId(job.id);
    setAnimationClass("slide-out-right");
    setFlashColor("bg-accent/15");

    try {
      await approveJob(job.id);
      setTimeout(() => {
        setJobs((prev) => prev.filter((j) => j.id !== job.id));
        setAnimatingId(null);
        setAnimationClass("");
        setFlashColor("");
        setShowFullDesc(false);
      }, 200);
    } catch (err: any) {
      alert(`Error approving job: ${err.message}`);
      setAnimatingId(null);
      setAnimationClass("");
      setFlashColor("");
    }
  };

  const handleSkip = async (job: Job) => {
    if (animatingId) return;
    setAnimatingId(job.id);
    setAnimationClass("slide-out-left");
    setFlashColor("bg-warn/15");

    try {
      await skipJob(job.id);
      setTimeout(() => {
        setJobs((prev) => prev.filter((j) => j.id !== job.id));
        setAnimatingId(null);
        setAnimationClass("");
        setFlashColor("");
        setShowFullDesc(false);
      }, 200);
    } catch (err: any) {
      alert(`Error skipping job: ${err.message}`);
      setAnimatingId(null);
      setAnimationClass("");
      setFlashColor("");
    }
  };

  const currentJob = jobs[0];

  const isHighFit =
    currentJob?.fit_score !== null &&
    currentJob?.fit_score !== undefined &&
    currentJob.fit_score >= 70;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink font-sans">
            Review queue
          </h1>
          <p className="font-mono text-xs text-muted mt-0.5">
            {jobs.length > 0 ? `${jobs.length} remaining in queue` : "Queue clear"}
          </p>
        </div>
        <button
          onClick={fetchScoredJobs}
          disabled={loading}
          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
          aria-label="Refresh review queue"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="border border-warn bg-paper p-4 text-xs text-warn flex items-start gap-2.5" role="alert">
          <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5 text-warn" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-ink">Could not load review queue</p>
            <p className="text-muted leading-relaxed">{error}</p>
          </div>
        </div>
      )}

      {loading ? (
        <div className="border border-line bg-paper p-12 text-center text-xs text-muted font-mono">
          Loading scored jobs...
        </div>
      ) : jobs.length === 0 ? (
        <div className="border border-line bg-paper p-10 text-center space-y-3">
          <div className="font-mono text-sm font-semibold text-ink">
            No jobs scored yet.
          </div>
          <p className="text-xs text-muted max-w-sm mx-auto font-sans">
            Run score_jobs.py to evaluate new postings against your profile.
          </p>
          <div className="flex justify-center gap-3 pt-2">
            <Link
              href="/materials"
              className="rounded border border-accent bg-accent text-paper px-4 py-2 text-xs font-medium hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition font-sans"
            >
              Application materials
            </Link>
            <Link
              href="/"
              className="rounded border border-line bg-paper text-ink px-4 py-2 text-xs font-medium hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition font-sans"
            >
              Dashboard
            </Link>
          </div>
        </div>
      ) : (
        <div className="relative overflow-hidden">
          {/* Background flash layer for swipe animation */}
          {flashColor && (
            <div className={`absolute inset-0 z-0 transition-colors ${flashColor}`} />
          )}

          {/* Job Card (Single bordered block with left accent if fit >= 70) */}
          <div
            className={`relative z-10 border border-line bg-paper p-6 sm:p-8 space-y-5 border-l-4 ${
              isHighFit ? "border-l-accent" : "border-l-line"
            } ${animationClass}`}
          >
            {/* Title & Metadata */}
            <div className="space-y-2">
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-ink font-sans">
                {currentJob.title || "Untitled Position"}
              </h2>

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink">
                <span className="font-medium">
                  {currentJob.company || "Unknown Company"}
                </span>
                <span className="text-muted">•</span>
                <span className={isHighFit ? "text-accent font-semibold" : "text-ink"}>
                  Fit score: {currentJob.fit_score !== null ? `${currentJob.fit_score}/100` : "N/A"}
                </span>

                {currentJob.location && (
                  <>
                    <span className="text-muted">•</span>
                    <span className="text-muted">{currentJob.location}</span>
                  </>
                )}

                {currentJob.salary && (
                  <>
                    <span className="text-muted">•</span>
                    <span className="text-ink font-medium">{currentJob.salary}</span>
                  </>
                )}

                {currentJob.url && (
                  <>
                    <span className="text-muted">•</span>
                    <a
                      href={currentJob.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 underline text-accent hover:text-accent/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded"
                      aria-label="Open job posting in new tab"
                    >
                      <span>Posting</span>
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  </>
                )}
              </div>

              {/* Dealbreaker Flags */}
              {currentJob.fit_flags && (
                <div className="flex flex-wrap gap-1.5 pt-1" aria-label="Dealbreaker flags">
                  {currentJob.fit_flags
                    .split(",")
                    .map((flag) => flag.trim())
                    .filter(Boolean)
                    .map((flag, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1 font-mono text-xs border border-warn/40 px-1.5 py-0.5 bg-warn/5 text-warn"
                      >
                        <TriangleAlert className="h-3 w-3" aria-hidden="true" />
                        <span>{flag}</span>
                      </span>
                    ))}
                </div>
              )}
            </div>

            {/* AI Reasoning */}
            {currentJob.fit_reasoning && (
              <div className="border-t border-line pt-4 space-y-1">
                <div className="font-mono text-xs text-muted">Evaluation reasoning:</div>
                <p className="text-sm text-ink leading-relaxed font-sans">
                  {currentJob.fit_reasoning}
                </p>
              </div>
            )}

            {/* Description toggle */}
            {currentJob.description && (
              <div className="border-t border-line pt-4 space-y-2">
                <button
                  onClick={() => setShowFullDesc(!showFullDesc)}
                  className="font-mono text-xs text-muted hover:text-ink underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded cursor-pointer"
                  aria-label={showFullDesc ? "Hide full position description" : "Show full position description"}
                  aria-expanded={showFullDesc}
                >
                  {showFullDesc ? "Hide description" : "Show full description"}
                </button>
                {showFullDesc && (
                  <div className="border border-line bg-paper p-4 text-xs font-sans leading-relaxed text-ink whitespace-pre-line max-h-80 overflow-y-auto">
                    {currentJob.description}
                  </div>
                )}
              </div>
            )}

            {/* Desktop Action Buttons */}
            <div className="hidden sm:grid sm:grid-cols-2 gap-3 pt-4 border-t border-line">
              <button
                onClick={() => handleSkip(currentJob)}
                disabled={Boolean(animatingId)}
                className="rounded border border-line bg-paper py-2.5 px-4 text-xs font-semibold text-warn hover:border-warn hover:bg-warn/5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-warn transition active:scale-98 disabled:opacity-50 flex items-center justify-center gap-1.5 cursor-pointer"
                aria-label="Skip position"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                <span>Skip</span>
              </button>

              <button
                onClick={() => handleApprove(currentJob)}
                disabled={Boolean(animatingId)}
                className="rounded border border-accent bg-accent py-2.5 px-4 text-xs font-semibold text-paper hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition active:scale-98 disabled:opacity-50 flex items-center justify-center gap-1.5 cursor-pointer"
                aria-label="Approve position"
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                <span>Approve</span>
              </button>
            </div>
          </div>

          {/* Mobile Pinned Bottom Actions */}
          <div className="fixed bottom-14 left-0 right-0 z-40 sm:hidden border-t border-line bg-paper p-3">
            <div className="grid grid-cols-2 gap-2 max-w-md mx-auto">
              <button
                onClick={() => handleSkip(currentJob)}
                disabled={Boolean(animatingId)}
                className="rounded border border-line bg-paper py-3 text-xs font-semibold text-warn hover:border-warn hover:bg-warn/5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-warn transition active:scale-98 disabled:opacity-50 flex items-center justify-center gap-1.5 cursor-pointer"
                aria-label="Skip position"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                <span>Skip</span>
              </button>

              <button
                onClick={() => handleApprove(currentJob)}
                disabled={Boolean(animatingId)}
                className="rounded border border-accent bg-accent py-3 text-xs font-semibold text-paper hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition active:scale-98 disabled:opacity-50 flex items-center justify-center gap-1.5 cursor-pointer"
                aria-label="Approve position"
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                <span>Approve</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
