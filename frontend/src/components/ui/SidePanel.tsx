import { ApplicationDetail, ApplicationStatus } from '@/types';
import { format } from 'date-fns';
import { X, Trash2, CheckCircle2, Loader2, FileText, RotateCcw, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { submitReviewDecision, getResumeUrl, updateApplicationStatus, rerunApplicationPipeline } from '@/lib/api';
import { mutate } from 'swr';

interface SidePanelProps {
  detail: ApplicationDetail | null;
  onClose: () => void;
}

const StatusBadge = ({ status }: { status: string }) => {
  const statusConfig: Record<string, string> = {
    discovered: 'bg-zinc-800 text-zinc-400',
    researching: 'bg-purple-900/60 text-purple-300',
    resume_editing: 'bg-sky-900/60 text-sky-300',
    flagged_human: 'bg-amber-900/60 text-amber-300',
    applying: 'bg-cyan-900/60 text-cyan-300',
    applied: 'bg-blue-900/60 text-blue-300',
    email_received: 'bg-indigo-900/60 text-indigo-300',
    interview: 'bg-green-900/60 text-green-300',
    rejected: 'bg-red-900/60 text-red-300',
    withdrawn: 'bg-zinc-800 text-zinc-500',
  };

  const className = statusConfig[status] || 'bg-zinc-800 text-zinc-500';

  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium shrink-0 ${className}`}>
      {status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
    </span>
  );
};

const ClassificationBadge = ({ classification }: { classification: string }) => {
  const config: Record<string, string> = {
    interview_invite: 'bg-green-900/60 text-green-300',
    rejection: 'bg-red-900/60 text-red-300',
    assessment: 'bg-blue-900/60 text-blue-300',
    follow_up_needed: 'bg-amber-900/60 text-amber-300',
    other: 'bg-zinc-800 text-zinc-500',
  };

  const className = config[classification] || 'bg-zinc-800 text-zinc-500';

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${className}`}>
      {classification.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
    </span>
  );
};

export default function SidePanel({ detail, onClose }: SidePanelProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);

  if (!detail) return null;

  const { application, email_threads } = detail;
  const { id: application_id, job_id, company_name, role_title, status, match_score, hallucination_score, flagged_reason, applied_at } = application;

  const handleAction = async (decision: 'proceed' | 'skip') => {
    if (!job_id) return;
    setIsActionLoading(true);
    try {
      await submitReviewDecision(job_id, decision);
      await mutate('/api/applications');
      await mutate('/api/flagged');
      onClose();
    } catch (error) {
      console.error('Failed to submit review decision:', error);
      alert('Action failed. Please try again.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleManualStatus = async (newStatus: string) => {
    if (!application_id) return;
    setIsActionLoading(true);
    try {
      await updateApplicationStatus(application_id, newStatus);
      await mutate('/api/applications');
      await mutate('/api/flagged');
      onClose();
    } catch (error) {
      console.error('Failed to update status:', error);
      alert('Failed to update status.');
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRerun = async () => {
    if (!application_id) return;
    setIsActionLoading(true);
    try {
      await rerunApplicationPipeline(application_id);
      await mutate('/api/applications');
      await mutate('/api/flagged');
      onClose();
    } catch (error) {
      console.error('Failed to rerun pipeline:', error);
      alert('Failed to re-run pipeline.');
    } finally {
      setIsActionLoading(false);
    }
  };

  let scoreColor = 'text-red-500';
  if (match_score !== null) {
    if (match_score >= 0.8) scoreColor = 'text-green-500';
    else if (match_score >= 0.65) scoreColor = 'text-amber-500';
  }

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-screen w-96 bg-zinc-900 border-l border-zinc-800 z-50 overflow-y-auto flex flex-col transition-transform duration-200 ease-out translate-x-0">
        {/* SECTION 1 */}
        <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 p-4 z-10 flex flex-col">
          <div className="flex">
            <button onClick={onClose} className="text-zinc-400 hover:text-white mb-2">
              <X size={20} />
            </button>
          </div>
          <h2 className="text-white text-lg font-semibold mt-2">{company_name}</h2>
          <p className="text-zinc-400 text-sm">{role_title}</p>
          <div className="mt-2 inline-flex items-center">
             <StatusBadge status={status} />
          </div>

          {(status === ApplicationStatus.discovered || status === ApplicationStatus.flagged_human) && (
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                disabled={isActionLoading}
                onClick={() => handleAction('skip')}
                className="flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-300 text-sm font-medium py-2 px-3 rounded-lg border border-zinc-700 transition-colors"
              >
                {isActionLoading ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                Discard
              </button>
              <button
                disabled={isActionLoading}
                onClick={() => handleAction('proceed')}
                className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-80 text-white text-sm font-medium py-2 px-3 rounded-lg transition-colors shadow-lg shadow-blue-900/20"
              >
                {isActionLoading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                Apply Anyways
              </button>
            </div>
          )}
        </div>

        {/* SECTION 2 */}
        <div className="p-4 border-b border-zinc-800">
          <div className="flex justify-between items-start">
            {match_score !== null && (
              <div>
                <p className={`text-4xl font-bold ${scoreColor}`}>
                  {(match_score * 100).toFixed(0)}%
                </p>
                <p className="text-zinc-500 text-xs uppercase tracking-wider mt-1">
                  Resume Match Score
                </p>
              </div>
            )}
            
            {application.resume_version_id && (
              <a 
                href={getResumeUrl(application.resume_version_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 text-xs font-medium bg-blue-400/10 px-2 py-1.5 rounded border border-blue-400/20 transition-colors"
              >
                <FileText size={14} />
                View Resume
                <ExternalLink size={12} />
              </a>
            )}
          </div>

          <p className="text-zinc-500 text-xs mt-3">
            Fact Check: {hallucination_score ?? 0}/6 criteria passed
          </p>
          
          {flagged_reason && (
            <div className="bg-amber-950/40 border border-amber-800/40 rounded-lg p-3 mt-3">
              <p className="flex gap-2 text-amber-300 text-sm">
                <span className="shrink-0 pt-0.5 text-amber-400">⚠</span>
                {flagged_reason}
              </p>
              
              {status === ApplicationStatus.flagged_human && (
                <div className="mt-3 flex flex-col gap-2">
                  <p className="text-[10px] text-amber-500 uppercase font-semibold tracking-wider">Advanced Actions</p>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={handleRerun}
                      disabled={isActionLoading}
                      className="flex items-center justify-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] py-1.5 px-2 rounded border border-zinc-700 transition-colors"
                    >
                      <RotateCcw size={12} />
                      Re-run AI Edit
                    </button>
                    <button
                      onClick={() => handleManualStatus('applied')}
                      disabled={isActionLoading}
                      className="flex items-center justify-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] py-1.5 px-2 rounded border border-zinc-700 transition-colors"
                    >
                      <CheckCircle2 size={12} />
                      Mark Applied
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* SECTION 3 */}
        <div className="p-4 border-b border-zinc-800">
          <h3 className="text-zinc-400 text-xs uppercase tracking-wider mb-3">Timeline</h3>
          <div className="relative before:absolute before:left-1 before:top-0 before:h-full before:w-px before:bg-zinc-800">
            {applied_at && (
              <div className="pl-6 relative mb-3">
                <div className="absolute left-[3px] top-1.5 w-2 h-2 rounded-full bg-blue-500 -ml-1" />
                <p className="text-sm text-zinc-300">Applied</p>
                <p className="text-xs text-zinc-500">{format(new Date(applied_at), 'MMM d, yyyy h:mm a')}</p>
              </div>
            )}
             {email_threads && email_threads.map((thread) => (
              <div key={thread.id} className="pl-6 relative mb-3">
                <div className="absolute left-[3px] top-1.5 w-2 h-2 rounded-full bg-indigo-400 -ml-1" />
                <p className="text-sm text-zinc-300">{thread.sender}</p>
                <p className="text-xs text-zinc-500 capitalize">{thread.classification.replace(/_/g, ' ')}</p>
              </div>
            ))}
            <div className="pl-6 relative mb-3">
              <div className={`absolute left-[3px] top-1.5 w-2 h-2 rounded-full -ml-1 ${status === 'interview' ? 'bg-green-500' : status === 'rejected' ? 'bg-red-500' : 'bg-zinc-600'}`} />
              <p className="text-sm text-zinc-300 capitalize">{status.replace(/_/g, ' ')}</p>
              <p className="text-xs text-zinc-500">Current Status</p>
            </div>
          </div>
        </div>

        {/* SECTION 4 */}
        <div className="p-4">
          <h3 className="text-zinc-400 text-xs uppercase tracking-wider mb-3">Communications</h3>
          {(!email_threads || email_threads.length === 0) ? (
            <p className="text-zinc-600 text-sm">No emails tracked yet</p>
          ) : (
            email_threads.map((thread) => (
              <div key={thread.id} className="bg-zinc-800/60 rounded-lg p-3 mb-2">
                <div className="flex justify-between items-start">
                  <ClassificationBadge classification={thread.classification} />
                  {thread.received_at && (
                    <span className="text-zinc-500 text-xs">
                      {format(new Date(thread.received_at), 'MMM d, h:mm a')}
                    </span>
                  )}
                </div>
                <p className="text-zinc-300 text-sm truncate mt-1">{thread.sender}</p>
                {thread.ai_summary && (
                  <details className="mt-1">
                    <summary className="text-zinc-500 text-xs cursor-pointer hover:text-zinc-400">
                      View AI Summary
                    </summary>
                    <p className="text-zinc-400 text-xs mt-1">{thread.ai_summary}</p>
                  </details>
                )}
                {thread.draft_followup && (
                  <div className="mt-2">
                    <p className="text-xs text-blue-400 mt-1">Draft Reply</p>
                    <div className="bg-zinc-900 rounded p-2 mt-1 text-zinc-300 text-xs font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {thread.draft_followup}
                    </div>
                    <button
                      onClick={() => handleCopy(thread.draft_followup || '', thread.id)}
                      className="text-xs bg-zinc-700 hover:bg-zinc-600 transition-colors px-2 py-1 rounded mt-2 text-white"
                    >
                      {copiedId === thread.id ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
