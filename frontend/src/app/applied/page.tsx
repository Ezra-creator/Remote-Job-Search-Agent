"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getJobs,
  getFollowups,
  markApplied,
  markFollowedUp,
  Job,
} from "@/lib/api";
import {
  Check,
  Clock,
  ExternalLink,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";

export default function AppliedPage() {
  const [readyJobs, setReadyJobs] = useState<Job[]>([]);
  const [followupJobs, setFollowupJobs] = useState<Job[]>([]);
  const [appliedJobs, setAppliedJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ready, followups, applied] = await Promise.all([
        getJobs("ready_to_apply"),
        getFollowups(),
        getJobs("applied"),
      ]);
      setReadyJobs(ready);
      setFollowupJobs(followups);
      setAppliedJobs(applied);
    } catch (err: any) {
      setError(err.message || "Failed to load tracking data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Application tracking — RJS";
    fetchData();
  }, []);

  const handleMarkApplied = async (job: Job) => {
    setActionLoading(job.id);
    try {
      const updated = await markApplied(job.id);
      setReadyJobs((prev) => prev.filter((j) => j.id !== job.id));
      setAppliedJobs((prev) => [updated, ...prev]);
    } catch (err: any) {
      alert(`Error marking applied: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkFollowedUp = async (job: Job) => {
    setActionLoading(job.id);
    try {
      const updated = await markFollowedUp(job.id);
      setFollowupJobs((prev) => prev.filter((j) => j.id !== job.id));
      setAppliedJobs((prev) =>
        prev.map((j) => (j.id === job.id ? updated : j))
      );
    } catch (err: any) {
      alert(`Error marking followed up: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const getDaysSince = (dateStr: string | null): number => {
    if (!dateStr) return 0;
    const appliedTime = new Date(dateStr).getTime();
    const nowTime = Date.now();
    const diffDays = Math.floor((nowTime - appliedTime) / (1000 * 60 * 60 * 24));
    return Math.max(0, diffDays);
  };

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return "N/A";
    try {
      return new Date(dateStr).toISOString().split("T")[0];
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink font-sans">
            Application tracking
          </h1>
          <p className="font-mono text-xs text-muted mt-0.5">
            Ready submissions, follow-up schedule, and application log.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
          aria-label="Refresh application tracking"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="border border-warn bg-paper p-4 text-xs text-warn flex items-start gap-2.5" role="alert">
          <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5 text-warn" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-ink">Could not load application tracking</p>
            <p className="text-muted leading-relaxed">{error}</p>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Section 1: Ready to Apply                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink font-sans">
            Ready to apply ({readyJobs.length})
          </h2>
        </div>

        {loading ? (
          <div className="border border-line bg-paper p-6 text-center text-xs font-mono text-muted">
            Loading ready applications...
          </div>
        ) : readyJobs.length === 0 ? (
          <div className="border border-line bg-paper p-6 text-center text-xs text-muted font-sans">
            No applications ready to apply. Approve drafted materials in Application materials.
          </div>
        ) : (
          <div className="border border-line bg-paper divide-y divide-line">
            {readyJobs.map((job) => {
              const isExpanded = expandedJobId === job.id;
              const applyLink = job.apply_url || job.url || "#";

              return (
                <div key={job.id} className="p-4 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <div className="font-mono text-xs text-muted">
                        {job.company || "Unknown Company"}
                        {job.location ? ` • ${job.location}` : ""}
                      </div>
                      <div className="text-base font-semibold text-ink font-sans">
                        {job.title}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <a
                        href={applyLink}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded border border-line bg-paper px-3 py-1.5 text-xs font-medium text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded transition font-sans inline-flex items-center gap-1 cursor-pointer"
                        aria-label="Open job posting in new tab"
                      >
                        <span>Open listing</span>
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>

                      <button
                        onClick={() => handleMarkApplied(job)}
                        disabled={actionLoading === job.id}
                        className="rounded border border-accent bg-accent px-3 py-1.5 text-xs font-semibold text-paper hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition active:scale-98 disabled:opacity-50 font-sans inline-flex items-center gap-1 cursor-pointer"
                        aria-label="Mark job as applied"
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{actionLoading === job.id ? "Saving..." : "Mark applied"}</span>
                      </button>
                    </div>
                  </div>

                  {/* Materials Preview Accordion */}
                  <div className="pt-1">
                    <button
                      onClick={() =>
                        setExpandedJobId(isExpanded ? null : job.id)
                      }
                      className="font-mono text-xs text-muted hover:text-ink underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded cursor-pointer"
                      aria-label={isExpanded ? "Hide application text" : "View application text"}
                      aria-expanded={isExpanded}
                    >
                      {isExpanded ? "Hide application text" : "View application text"}
                    </button>

                    {isExpanded && (
                      <div className="mt-3 space-y-3 border-t border-line pt-3">
                        {job.materials_resume_bullets && (
                          <div>
                            <div className="font-mono text-xs text-muted mb-1">
                              Resume bullets:
                            </div>
                            <div className="border border-line bg-paper p-3 font-mono text-xs leading-relaxed whitespace-pre-line text-ink">
                              {job.materials_resume_bullets}
                            </div>
                          </div>
                        )}

                        {job.materials_cover_letter && (
                          <div>
                            <div className="font-mono text-xs text-muted mb-1">
                              Cover letter:
                            </div>
                            <div className="border border-line bg-paper p-3 font-sans text-xs leading-relaxed whitespace-pre-line text-ink max-h-56 overflow-y-auto">
                              {job.materials_cover_letter}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section 2: Follow-ups Needed                                      */}
      {/* ------------------------------------------------------------------ */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink font-sans">
            Follow-ups needed ({followupJobs.length})
          </h2>
          <span className="font-mono text-xs text-muted">Applied &gt; 7 days ago</span>
        </div>

        {followupJobs.length === 0 ? (
          <div className="border border-line bg-paper p-4 text-center text-xs text-muted font-mono">
            No follow-ups currently due.
          </div>
        ) : (
          <div className="border border-line bg-paper divide-y divide-line">
            {followupJobs.map((job) => {
              const daysAgo = getDaysSince(job.applied_at);
              return (
                <div
                  key={job.id}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-l-4 border-l-warn"
                >
                  <div>
                    <div className="font-mono text-xs text-ink flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-ink">{job.company}</span>
                      <span className="text-muted">•</span>
                      <span className="text-muted">Applied {formatDate(job.applied_at)}</span>
                      <span className="text-muted">•</span>
                      <span className="font-mono text-warn font-semibold inline-flex items-center gap-1">
                        <Clock className="h-3 w-3" aria-hidden="true" />
                        <span>{daysAgo}d ago</span>
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-ink font-sans mt-0.5">
                      {job.title}
                    </div>
                  </div>

                  <button
                    onClick={() => handleMarkFollowedUp(job)}
                    disabled={actionLoading === job.id}
                    className="rounded border border-line bg-paper px-3 py-1.5 text-xs font-semibold text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition active:scale-98 disabled:opacity-50 shrink-0 font-sans flex items-center gap-1 cursor-pointer"
                    aria-label="Mark follow-up as sent"
                  >
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>{actionLoading === job.id ? "Saving..." : "Mark followed up"}</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section 3: History (Plain Bordered Rows)                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink font-sans">
            Application history ({appliedJobs.length})
          </h2>
        </div>

        {appliedJobs.length === 0 ? (
          <div className="border border-line bg-paper p-4 text-center text-xs text-muted font-mono">
            No submitted applications recorded yet.
          </div>
        ) : (
          <div className="border border-line bg-paper divide-y divide-line">
            {appliedJobs.map((job) => (
              <div
                key={job.id}
                className="p-3.5 sm:px-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
              >
                <div>
                  <div className="font-mono text-xs text-muted">
                    {job.company} • Applied: {formatDate(job.applied_at)}
                  </div>
                  <div className="text-xs font-medium text-ink font-sans">
                    {job.title}
                  </div>
                </div>

                <div className="font-mono text-xs text-muted">
                  {job.follow_up_sent_at ? (
                    <span className="text-accent inline-flex items-center gap-1">
                      <Check className="h-3 w-3" aria-hidden="true" />
                      <span>Followed up {formatDate(job.follow_up_sent_at)}</span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      <span>Pending response</span>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
