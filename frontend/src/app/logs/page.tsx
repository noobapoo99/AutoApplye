"use client";

import { Activity, Wifi, WifiOff } from "lucide-react";

import { useAgentLogs } from "@/lib/websocket";

export default function LogsPage() {
  const { logs, connected } = useAgentLogs();

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Live Agent Feed
            </p>
            <h2 className="text-2xl font-semibold text-slate-950 dark:text-white">
              Pipeline events streaming from the backend
            </h2>
          </div>
          <div
            className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-medium ${
              connected
                ? "border-status-interview/25 bg-status-interview/10 text-status-interview"
                : "border-status-withdrawn/25 bg-status-withdrawn/10 text-status-withdrawn"
            }`}
          >
            {connected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
            {connected ? "Connected" : "Disconnected"}
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="flex items-center gap-2 border-b border-slate-200/70 px-6 py-4 text-sm font-medium text-slate-700 dark:border-slate-800 dark:text-slate-200">
          <Activity className="h-4 w-4" />
          Event Stream
        </div>
        <div className="max-h-[70vh] overflow-y-auto">
          {logs.length === 0 ? (
            <div className="p-6 text-sm text-slate-500 dark:text-slate-400">
              Waiting for pipeline events. Start a search or review action to see logs
              appear here.
            </div>
          ) : (
            <div className="divide-y divide-slate-200/70 dark:divide-slate-800">
              {logs
                .slice()
                .reverse()
                .map((log, index) => (
                  <article key={`${log.timestamp}-${index}`} className="p-6">
                    <div className="mb-3 flex flex-wrap items-center gap-3">
                      <span className="rounded-full border border-sky-400/25 bg-sky-400/10 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-300">
                        {log.event}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
                      {JSON.stringify(log, null, 2)}
                    </pre>
                  </article>
                ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
