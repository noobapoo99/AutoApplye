import { FlaggedJob, ApplicationStatus } from '@/types';
import { AlertCircle, Loader2, RefreshCw, CheckCircle, FileText } from 'lucide-react';
import { useState } from 'react';
import { rerunApplicationPipeline, updateApplicationStatus, getResumeUrl } from '@/lib/api';

interface FlaggedJobCardProps {
  job: FlaggedJob;
  onDecision: (job_id: string, decision: "proceed" | "skip", appId: string) => Promise<void>;
}

export default function FlaggedJobCard({ job, onDecision }: FlaggedJobCardProps) {
  const [loading, setLoading] = useState<"proceed" | "skip" | "rerun" | "manual_apply" | null>(null);
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

  const handleRerun = async () => {
    setLoading("rerun");
    setError(null);
    try {
      await rerunApplicationPipeline(job.id);
      // We could use onDecision here with a special "rerun" status if the page handles it,
      // but the page currently expects "proceed" or "skip" to dismiss the card.
      // For now, let's just trigger it and let the user know.
      // Usually, rerun should also dismiss the card from "flagged" because it's back in pipeline.
      await onDecision(job.job_id, "skip", job.id); // Hack to dismiss it since it's now in resume_editing
    } catch (e: any) {
      setError(e.message || "Failed to rerun pipeline");
    } finally {
      setLoading(null);
    }
  };

  const handleManualApply = async () => {
    setLoading("manual_apply");
    setError(null);
    try {
      await updateApplicationStatus(job.id, ApplicationStatus.applied);
      await onDecision(job.job_id, "skip", job.id); // Dismiss card
    } catch (e: any) {
      setError(e.message || "Failed to mark as applied");
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
    <div className="bg-zinc-900 border border-amber-800/30 rounded-xl p-5 shadow-lg">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-white font-semibold text-lg">{job.company_name}</h3>
            {job.id && (
              <span className="text-[10px] font-mono text-zinc-600 bg-zinc-800/50 px-1.5 py-0.5 rounded truncate max-w-[100px]">
                {job.id.slice(0, 8)}
              </span>
            )}
          </div>
          <p className="text-zinc-400 text-sm mt-0.5">{job.role_title}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold shrink-0 ${getMatchBadgeClasses(job.match_score)}`}>
            {job.match_score === null ? "No score" : `${(job.match_score * 100).toFixed(0)}%`}
          </span>
          <p className="text-[10px] text-zinc-500 font-mono">
            {job.last_updated ? new Date(job.last_updated).toLocaleTimeString() : "--:--"}
          </p>
        </div>
      </div>

      {job.flagged_reason && (
        <div className="flex items-start gap-2 bg-amber-950/20 border border-amber-900/20 rounded-lg p-3 mt-4">
          <AlertCircle size={16} className="text-amber-500 shrink-0 mt-0.5" />
          <p className="text-amber-200/80 text-sm leading-relaxed">{job.flagged_reason}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-4">
        {criteria.map((c, i) => {
          const isPassed = i < (job.hallucination_score ?? 0);
          return (
            <span
              key={c[0]}
              className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold ${
                isPassed
                  ? 'bg-green-900/30 text-green-400 border border-green-800/30'
                  : 'bg-red-900/30 text-red-400 border border-red-800/30'
              }`}
            >
              {c[1]}
            </span>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 mt-6 pt-4 border-t border-zinc-800">
        <div className="flex gap-2">
          <button
            onClick={() => handleDecision("proceed")}
            disabled={loading !== null}
            className="bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 transition-all active:scale-95"
          >
            {loading === "proceed" ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
            Proceed
          </button>
          
          <button
            onClick={handleRerun}
            disabled={loading !== null}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 transition-all active:scale-95"
            title="Rerun the AI editing pipeline for this job"
          >
            {loading === "rerun" ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Rerun AI
          </button>

          <button
            onClick={handleManualApply}
            disabled={loading !== null}
            className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed text-zinc-300 rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 transition-all border border-zinc-700"
          >
            {loading === "manual_apply" ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} className="text-zinc-500" />}
            Mark Applied
          </button>
        </div>

        <div className="flex gap-2">
          {job.resume_version_id && (
            <a
              href={getResumeUrl(job.resume_version_id)}
              // Wait, FlaggedJob should probably have resume_version_id. Let's check the type again.
              target="_blank"
              rel="noopener noreferrer"
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 transition-all border border-zinc-700"
            >
              <FileText size={16} className="text-amber-500" />
              Resume
            </a>
          )}
          
          <button
            onClick={() => handleDecision("skip")}
            disabled={loading !== null}
            className="bg-zinc-900 hover:bg-red-900/20 border border-zinc-700 hover:border-red-900/50 text-zinc-400 hover:text-red-400 rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 transition-all active:scale-95"
          >
            {loading === "skip" && <Loader2 size={16} className="animate-spin" />}
            ✕ Skip
          </button>
        </div>
      </div>
      
      {error && <p className="text-red-400 text-xs mt-3 bg-red-900/10 border border-red-900/20 p-2 rounded-lg">{error}</p>}
    </div>
  );
}
