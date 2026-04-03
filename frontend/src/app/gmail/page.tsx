"use client";

import useSWR from "swr";
import { format } from "date-fns";
import { Inbox, MailSearch, Reply } from "lucide-react";

import { getEmailThreads } from "@/lib/api";
import { cn } from "@/lib/utils";

const classificationStyles: Record<string, string> = {
  interview_invite: "border-status-interview/25 bg-status-interview/15 text-status-interview",
  rejection: "border-status-rejected/25 bg-status-rejected/15 text-status-rejected",
  assessment: "border-status-applied/25 bg-status-applied/15 text-status-applied",
  follow_up_needed: "border-status-flagged/25 bg-status-flagged/15 text-status-flagged",
  other: "border-status-withdrawn/25 bg-status-withdrawn/15 text-status-withdrawn",
};

export default function GmailPage() {
  const { data: emails = [], isLoading } = useSWR("emails", getEmailThreads);

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Gmail Tracker
            </p>
            <h2 className="text-2xl font-semibold text-slate-950 dark:text-white">
              Recent email threads tied to applications
            </h2>
          </div>
          <div className="rounded-2xl border border-sky-400/25 bg-sky-400/10 p-3 text-sky-700 dark:text-sky-300">
            <Inbox className="h-5 w-5" />
          </div>
        </div>
      </section>

      <section className="space-y-4">
        {isLoading ? (
          <div className="panel p-6 text-sm text-slate-500 dark:text-slate-400">
            Loading recent Gmail activity...
          </div>
        ) : emails.length === 0 ? (
          <div className="panel p-6 text-sm text-slate-500 dark:text-slate-400">
            No tracked email threads yet.
          </div>
        ) : (
          emails.map((email) => (
            <article key={email.id} className="panel p-6">
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide",
                      classificationStyles[email.classification] ??
                        classificationStyles.other,
                    )}
                  >
                    {email.classification.replace(/_/g, " ")}
                  </span>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    {email.received_at
                      ? format(new Date(email.received_at), "PPP p")
                      : "Unknown received time"}
                  </span>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    DLQ attempts: {email.dlq_attempts}
                  </span>
                </div>

                <div>
                  <h3 className="text-xl font-semibold text-slate-950 dark:text-white">
                    {email.subject}
                  </h3>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                    From {email.sender}
                  </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
                  <div className="panel-muted p-4">
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                      <MailSearch className="h-4 w-4" />
                      AI Summary
                    </div>
                    <p className="text-sm leading-6 text-slate-700 dark:text-slate-300">
                      {email.ai_summary || "No summary was generated for this thread."}
                    </p>
                  </div>
                  <div className="panel-muted p-4">
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                      <Reply className="h-4 w-4" />
                      Draft Follow-up
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-slate-300">
                      {email.draft_followup || "No follow-up draft needed."}
                    </p>
                  </div>
                </div>
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  );
}
