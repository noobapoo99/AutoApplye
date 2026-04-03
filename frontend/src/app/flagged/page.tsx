"use client";
import { useState } from 'react';
import useSWR from 'swr';
import { getFlagged, submitReviewDecision } from '@/lib/api';
import FlaggedJobCard from '@/components/ui/FlaggedJobCard';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

export default function FlaggedPage() {
  const { data: flagged, mutate } = useSWR('flagged', getFlagged, { refreshInterval: 20000 });
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  const visibleJobs = (flagged ?? []).filter(j => !dismissedIds.has(j.id));

  const handleDecision = async (job_id: string, decision: "proceed" | "skip") => {
    await submitReviewDecision(job_id, decision);
    setDismissedIds(prev => new Set([...prev, job_id]));
    mutate();
  };

  return (
    <div className="px-6 py-6 min-h-screen">
      <div className="flex items-center gap-3 mb-6">
        <h1 className="text-white text-2xl font-bold">Flagged for Review</h1>
        <span className="bg-amber-900/60 text-amber-300 rounded-full px-2.5 py-0.5 text-sm font-medium">
          {visibleJobs.length}
        </span>
      </div>

      {visibleJobs.length > 0 && (
        <div className="flex items-start gap-3 bg-amber-950/30 border border-amber-800/40 rounded-xl p-4 mb-6">
          <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
          <p className="text-amber-200 text-sm">
            These jobs scored below the match threshold or failed hallucination checks.
            Review each one to proceed with the application or skip it.
          </p>
        </div>
      )}

      {visibleJobs.length > 0 ? (
        <div className="flex flex-col gap-4">
          {visibleJobs.map((job) => (
            <FlaggedJobCard
              key={job.id}
              job={job}
              onDecision={handleDecision}
            />
          ))}
        </div>
      ) : flagged !== undefined ? (
        <div className="py-20 text-center">
          <CheckCircle2 size={48} className="text-green-400 mx-auto mb-4" />
          <p className="text-zinc-400">No jobs pending review — you're all caught up.</p>
        </div>
      ) : null}
    </div>
  );
}
