import { FlaggedJob } from '@/types';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useState } from 'react';

interface FlaggedJobCardProps {
  job: FlaggedJob;
  onDecision: (job_id: string, decision: "proceed" | "skip", appId: string) => Promise<void>;
}

export default function FlaggedJobCard({ job, onDecision }: FlaggedJobCardProps) {
  const [loading, setLoading] = useState<"proceed" | "skip" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDecision = async (decision: "proceed" | "skip") => {
    setLoading(decision);
    setError(null);
    try {
      await onDecision(job.job_id, decision, job.id);
    } catch (e: any) {
      setError(e.message || "An error occurred");
    } finally {
      setLoading(null);
    }
  };

  const criteria = [
    ["company_name_match", "Company"],
    ["role_title_match", "Role"],
    ["skills_grounded", "Skills"],
    ["resume_consistency", "Resume"],
    ["contact_accuracy", "Contact"],
    ["score_range_valid", "Score"]
  ];

  const getMatchBadgeClasses = (score: number | null) => {
    if (score === null) return 'bg-zinc-800 text-zinc-400';
    if (score < 0.65) return 'bg-red-900/60 text-red-300';
    if (score < 0.8) return 'bg-amber-900/60 text-amber-300';
    return 'bg-green-900/60 text-green-300';
  };

  return (
    <div className="bg-zinc-900 border border-amber-800/30 rounded-xl p-5">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-white font-semibold text-base">{job.company_name}</h3>
          <p className="text-zinc-400 text-sm mt-0.5">{job.role_title}</p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium shrink-0 ${getMatchBadgeClasses(job.match_score)}`}>
          {job.match_score === null ? "No score" : `${(job.match_score * 100).toFixed(0)}%`}
        </span>
      </div>

      {job.flagged_reason && (
        <div className="flex items-start gap-2 bg-zinc-800/60 rounded-lg p-3 mt-3">
          <AlertCircle size={14} className="text-amber-400 shrink-0 mt-0.5" />
          <p className="text-zinc-300 text-sm">{job.flagged_reason}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        {criteria.map((c, i) => {
          const isPassed = i < (job.hallucination_score ?? 0);
          return (
            <span
              key={c[0]}
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isPassed
                  ? 'bg-green-900/50 text-green-300 border border-green-800/50'
                  : 'bg-red-900/50 text-red-300 border border-red-800/50'
              }`}
            >
              {c[1]}
            </span>
          );
        })}
      </div>

      <div className="flex gap-3 mt-4">
        <button
          onClick={() => handleDecision("proceed")}
          disabled={loading !== null}
          className="bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2"
        >
          {loading === "proceed" && <Loader2 size={14} className="animate-spin" />}
          ✓ Proceed
        </button>
        <button
          onClick={() => handleDecision("skip")}
          disabled={loading !== null}
          className="bg-zinc-800 hover:bg-red-900/40 border border-zinc-700 hover:border-red-800 text-zinc-300 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2"
        >
          {loading === "skip" && <Loader2 size={14} className="animate-spin" />}
          ✕ Skip
        </button>
      </div>
      
      {error && <p className="text-red-400 text-xs mt-1">{error}</p>}
    </div>
  );
}
