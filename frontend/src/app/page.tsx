"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getStats, Stats } from "@/lib/api";
import { RefreshCw, TriangleAlert } from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStats();
      setStats(data);
    } catch (err: any) {
      setError(err.message || "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Pipeline overview — RJS";
    fetchStats();
  }, []);

  const total = stats?.total_jobs || 0;
  const scored = stats?.counts_by_status?.["scored"] || 0;
  const approved =
    (stats?.counts_by_status?.["approved"] || 0) +
    (stats?.counts_by_status?.["materials_ready"] || 0);
  const readyToApply = stats?.counts_by_status?.["ready_to_apply"] || 0;
  const applied = stats?.counts_by_status?.["applied"] || 0;
  const newJobs = stats?.counts_by_status?.["new"] || 0;
  const skipped = stats?.counts_by_status?.["skipped"] || 0;
  const avgFitVal = stats?.average_fit_score;
  const avgFitStr = avgFitVal !== null && avgFitVal !== undefined ? `${avgFitVal}` : "—";
  const isHighFit = avgFitVal !== null && avgFitVal !== undefined && avgFitVal >= 70;

  const pipelineSteps = [
    { label: "New", count: newJobs, href: null },
    { label: "Scored", count: scored, href: "/review", action: "Review" },
    { label: "Approved", count: approved, href: "/materials", action: "Draft" },
    { label: "Ready to apply", count: readyToApply, href: "/applied", action: "Apply" },
    { label: "Applied", count: applied, href: "/applied", action: "Track" },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink font-sans">
            Pipeline overview
          </h1>
          <p className="text-xs text-muted mt-0.5 font-sans">
            Job search metrics and status tracking.
          </p>
        </div>
        <button
          onClick={fetchStats}
          disabled={loading}
          className="rounded border border-line bg-paper px-3 py-1.5 text-xs text-ink hover:border-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition disabled:opacity-50 flex items-center gap-1.5 font-sans cursor-pointer"
          aria-label="Refresh pipeline statistics"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="border border-warn bg-paper p-4 text-xs text-warn flex items-start gap-2.5" role="alert">
          <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5 text-warn" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-ink">Backend connection error</p>
            <p className="text-muted leading-relaxed">{error}</p>
          </div>
        </div>
      )}

      {/* Horizontal Stat Strip */}
      <div className="border border-line bg-paper">
        <div className="grid grid-cols-3 divide-x divide-line sm:grid-cols-6">
          <div className="p-4 text-center">
            <div className="font-mono text-2xl font-bold text-ink sm:text-3xl">
              {loading ? "..." : total}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Total sourced</div>
          </div>

          <div className="p-4 text-center">
            <div
              className={`font-mono text-2xl font-bold sm:text-3xl ${
                isHighFit ? "text-accent" : "text-ink"
              }`}
            >
              {loading ? "..." : avgFitStr}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Average fit</div>
          </div>

          <div className="p-4 text-center">
            <div className="font-mono text-2xl font-bold text-ink sm:text-3xl">
              {loading ? "..." : scored}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Needs review</div>
          </div>

          <div className="p-4 text-center">
            <div className="font-mono text-2xl font-bold text-ink sm:text-3xl">
              {loading ? "..." : approved}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Approved</div>
          </div>

          <div className="p-4 text-center">
            <div className="font-mono text-2xl font-bold text-ink sm:text-3xl">
              {loading ? "..." : readyToApply}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Ready to apply</div>
          </div>

          <div className="p-4 text-center">
            <div className="font-mono text-2xl font-bold text-ink sm:text-3xl">
              {loading ? "..." : applied}
            </div>
            <div className="mt-1 text-xs text-muted font-sans">Applied</div>
          </div>
        </div>
      </div>

      {/* Pipeline Sequence */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-ink font-sans">Pipeline sequence</h2>
        <div className="border border-line bg-paper divide-y divide-line">
          {pipelineSteps.map((step, index) => (
            <div
              key={step.label}
              className="flex items-center justify-between p-3.5 sm:px-4"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-muted">
                  {index + 1}
                </span>
                <span className="text-sm font-medium text-ink font-sans">
                  {step.label}
                </span>
              </div>

              <div className="flex items-center gap-4">
                <span className="font-mono text-sm font-semibold text-ink">
                  {loading ? "..." : step.count}
                </span>

                {step.href ? (
                  <Link
                    href={step.href}
                    className="rounded border border-line bg-paper px-2.5 py-1 text-xs font-medium text-ink hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent transition font-sans"
                    aria-label={`${step.action} ${step.label} jobs`}
                  >
                    {step.action}
                  </Link>
                ) : (
                  <span className="w-16"></span>
                )}
              </div>
            </div>
          ))}

          {/* Skipped */}
          <div className="flex items-center justify-between p-3.5 sm:px-4 bg-line/20 text-muted">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-muted">—</span>
              <span className="text-xs font-sans">Skipped / Filtered</span>
            </div>
            <span className="font-mono text-xs text-muted">
              {loading ? "..." : skipped}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
