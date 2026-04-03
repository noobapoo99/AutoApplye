import { Application } from '@/types';
import { formatDistanceToNow } from 'date-fns';

interface JobCardProps {
  application: Application;
  isSelected: boolean;
  onSelect: (id: string) => void;
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

export default function JobCard({ application, isSelected, onSelect }: JobCardProps) {
  const { company_name, role_title, status, match_score, applied_at, hallucination_score } = application;

  let barColor = 'bg-red-500';
  if (match_score !== null) {
    if (match_score >= 0.8) barColor = 'bg-green-500';
    else if (match_score >= 0.65) barColor = 'bg-amber-500';
  }

  return (
    <div
      onClick={() => onSelect(application.id)}
      className={`bg-zinc-900 border rounded-xl p-5 cursor-pointer transition-all duration-150 hover:border-zinc-600 hover:bg-zinc-800/60 ${
        isSelected ? 'ring-2 ring-blue-500/60 border-blue-500/40' : 'border-zinc-800'
      }`}
    >
      <div className="flex justify-between items-start">
        <h3 className="text-white font-semibold text-base">{company_name}</h3>
        <StatusBadge status={status} />
      </div>

      <p className="text-zinc-400 text-sm truncate mt-0.5">{role_title}</p>

      <div className="mt-3">
        {match_score === null ? (
          <p className="text-zinc-600 text-xs">Match score pending</p>
        ) : (
          <>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-zinc-500">Match</span>
              <span className="text-zinc-300 font-medium">{(match_score * 100).toFixed(0)}%</span>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5">
              <div
                className={`h-full rounded-full ${barColor}`}
                style={{ width: `${Math.max(0, Math.min(100, match_score * 100))}%` }}
              />
            </div>
          </>
        )}
      </div>

      <div className="flex justify-between items-center mt-3">
        {applied_at ? (
          <span className="text-zinc-500 text-xs">
            {formatDistanceToNow(new Date(applied_at), { addSuffix: true })}
          </span>
        ) : (
          <span className="text-zinc-600 text-xs">Not yet applied</span>
        )}

        <div className="flex gap-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <span
              key={i}
              className={`w-1.5 h-1.5 rounded-full ${
                i < (hallucination_score ?? 0) ? 'bg-green-400' : 'bg-zinc-700'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
