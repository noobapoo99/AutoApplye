"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";
import { formatDistanceToNow } from "date-fns";
import { BarChart3, Loader2, Search, Sparkles } from "lucide-react";

import { StatusBadge } from "@/components/ui/status-badge";
import { getApplications, getStats, triggerJobSearch } from "@/lib/api";

const strategyOptions = [
  { value: "keyword_injection", label: "Keyword Injection" },
  { value: "summary_rewrite", label: "Summary Rewrite" },
  { value: "skills_reorder", label: "Skills Reorder" },
];

export default function DashboardPage() {
  const { data: applications = [], isLoading: appsLoading } = useSWR(
    "applications",
    getApplications,
  );
  const { data: stats, isLoading: statsLoading } = useSWR("stats", getStats);
  const [query, setQuery] = useState("");
  const [maxJobs, setMaxJobs] = useState(5);
  const [strategy, setStrategy] = useState("keyword_injection");
  const [submitting, setSubmitting] = useState(false);
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const result = await triggerJobSearch(query.trim(), maxJobs, strategy);
      setPipelineId(result.pipeline_id);
      setQuery("");
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Unable to start the scout pipeline.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="panel p-6">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                Launch Job Discovery
              </p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">
                Kick off a fresh scouting run
              </h2>
            </div>
            <div className="rounded-2xl border border-sky-400/25 bg-sky-400/10 p-3 text-sky-700 dark:text-sky-300">
              <Sparkles className="h-5 w-5" />
            </div>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-4 lg:grid-cols-[1.6fr_0.5fr_0.7fr]">
              <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                Search Query
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Senior backend engineer, data platform, ML ops..."
                  className="w-full rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-sky-400 dark:border-slate-700 dark:bg-slate-950/70 dark:text-white"
                />
              </label>

              <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                Max Jobs
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxJobs}
                  onChange={(event) => setMaxJobs(Number(event.target.value))}
                  className="w-full rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-950 outline-none transition focus:border-sky-400 dark:border-slate-700 dark:bg-slate-950/70 dark:text-white"
                />
              </label>

              <label className="space-y-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                Resume Strategy
                <select
                  value={strategy}
                  onChange={(event) => setStrategy(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-950 outline-none transition focus:border-sky-400 dark:border-slate-700 dark:bg-slate-950/70 dark:text-white"
                >
                  {strategyOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                Start Pipeline
              </button>
              {pipelineId ? (
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  Active pipeline: <span className="font-mono">{pipelineId}</span>
                </p>
              ) : null}
              {submitError ? (
                <p className="text-sm text-red-600 dark:text-red-300">{submitError}</p>
              ) : null}
            </div>
          </form>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          <div className="panel p-5">
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Total Applications
            </p>
            <div className="mt-3 text-4xl font-semibold text-slate-950 dark:text-white">
              {statsLoading ? "..." : stats?.total_applications ?? 0}
            </div>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Active records across the pipeline.
            </p>
          </div>
          <div className="panel p-5">
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Avg Match Score
            </p>
            <div className="mt-3 text-4xl font-semibold text-slate-950 dark:text-white">
              {statsLoading ? "..." : `${Math.round((stats?.avg_match_score ?? 0) * 100)}%`}
            </div>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Redis cache: {stats?.cache_connected ? "connected" : "offline"}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="panel p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                Recent Applications
              </p>
              <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
                Latest pipeline activity
              </h2>
            </div>
            <BarChart3 className="h-5 w-5 text-slate-400" />
          </div>

          <div className="space-y-3">
            {appsLoading ? (
              <div className="panel-muted p-4 text-sm text-slate-500 dark:text-slate-400">
                Loading applications...
              </div>
            ) : applications.length === 0 ? (
              <div className="panel-muted p-4 text-sm text-slate-500 dark:text-slate-400">
                No applications yet. Start a scouting run to seed the dashboard.
              </div>
            ) : (
              applications.slice(0, 8).map((application) => (
                <article
                  key={application.id}
                  className="panel-muted flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between"
                >
                  <div>
                    <h3 className="text-lg font-semibold text-slate-950 dark:text-white">
                      {application.role_title}
                    </h3>
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      {application.company_name}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                    <StatusBadge status={application.status} />
                    <span>
                      Match:{" "}
                      {application.match_score !== null
                        ? `${Math.round(application.match_score * 100)}%`
                        : "Pending"}
                    </span>
                    <span>
                      Updated{" "}
                      {application.last_updated
                        ? formatDistanceToNow(new Date(application.last_updated), {
                            addSuffix: true,
                          })
                        : "recently"}
                    </span>
                  </div>
                </article>
              ))
            )}
          </div>
        </div>

        <div className="panel p-6">
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
            Status Breakdown
          </p>
          <h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">
            Pipeline composition
          </h2>

          <div className="mt-5 space-y-3">
            {statsLoading ? (
              <div className="panel-muted p-4 text-sm text-slate-500 dark:text-slate-400">
                Loading status metrics...
              </div>
            ) : Object.entries(stats?.status_breakdown ?? {}).length === 0 ? (
              <div className="panel-muted p-4 text-sm text-slate-500 dark:text-slate-400">
                Status counts will appear here after the first applications land.
              </div>
            ) : (
              Object.entries(stats?.status_breakdown ?? {}).map(([status, count]) => (
                <div
                  key={status}
                  className="panel-muted flex items-center justify-between px-4 py-3"
                >
                  <StatusBadge status={status} />
                  <span className="text-lg font-semibold text-slate-950 dark:text-white">
                    {count}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
