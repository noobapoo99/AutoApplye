"use client";

import { useState } from "react";
import useSWR from "swr";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, CheckCircle2, Loader2, SkipForward } from "lucide-react";

import { StatusBadge } from "@/components/ui/status-badge";
import { getFlagged, submitReviewDecision } from "@/lib/api";

export default function FlaggedPage() {
  const { data: jobs = [], isLoading, mutate } = useSWR("flagged", getFlagged);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  async function handleDecision(jobId: string, decision: "proceed" | "skip") {
    setActiveJobId(jobId);
    try {
      await submitReviewDecision(jobId, decision);
      await mutate();
    } finally {
      setActiveJobId(null);
    }
  }

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Human Review Queue
            </p>
            <h2 className="text-2xl font-semibold text-slate-950 dark:text-white">
              Flagged applications waiting on a decision
            </h2>
          </div>
          <div className="inline-flex items-center gap-2 rounded-2xl border border-status-flagged/25 bg-status-flagged/10 px-4 py-2 text-sm font-medium text-status-flagged">
            <AlertTriangle className="h-4 w-4" />
            Manual checkpoint
          </div>
        </div>
      </section>

      <section className="space-y-4">
        {isLoading ? (
          <div className="panel p-6 text-sm text-slate-500 dark:text-slate-400">
            Loading flagged applications...
          </div>
        ) : jobs.length === 0 ? (
          <div className="panel p-6 text-sm text-slate-500 dark:text-slate-400">
            No flagged reviews are waiting right now.
          </div>
        ) : (
          jobs.map((job) => {
            const busy = activeJobId === job.job_id;

            return (
              <article key={job.id} className="panel p-6">
                <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <StatusBadge status={job.status} />
                      <span className="text-sm text-slate-500 dark:text-slate-400">
                        Updated{" "}
                        {job.last_updated
                          ? formatDistanceToNow(new Date(job.last_updated), {
                              addSuffix: true,
                            })
                          : "recently"}
                      </span>
                    </div>
                    <div>
                      <h3 className="text-2xl font-semibold text-slate-950 dark:text-white">
                        {job.role_title}
                      </h3>
                      <p className="text-base text-slate-600 dark:text-slate-300">
                        {job.company_name}
                      </p>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="panel-muted p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                          Match Score
                        </p>
                        <p className="mt-2 text-xl font-semibold text-slate-950 dark:text-white">
                          {job.match_score !== null
                            ? `${Math.round(job.match_score * 100)}%`
                            : "Pending"}
                        </p>
                      </div>
                      <div className="panel-muted p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                          Hallucination Score
                        </p>
                        <p className="mt-2 text-xl font-semibold text-slate-950 dark:text-white">
                          {job.hallucination_score ?? 0}/6
                        </p>
                      </div>
                    </div>
                    <div className="panel-muted p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                        Flag Reason
                      </p>
                      <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
                        {job.flagged_reason || "No explicit reason provided."}
                      </p>
                    </div>
                  </div>

                  <div className="flex min-w-[240px] flex-col gap-3">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleDecision(job.job_id, "proceed")}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70 dark:bg-status-interview dark:text-slate-950 dark:hover:bg-status-interview/90"
                    >
                      {busy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4" />
                      )}
                      Approve and Continue
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleDecision(job.job_id, "skip")}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-300 bg-white/80 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-200 dark:hover:bg-slate-900"
                    >
                      <SkipForward className="h-4 w-4" />
                      Skip Application
                    </button>
                  </div>
                </div>
              </article>
            );
          })
        )}
      </section>
    </div>
  );
}
