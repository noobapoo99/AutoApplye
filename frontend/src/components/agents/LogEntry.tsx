import { LogEvent } from '@/types';

interface LogEntryProps {
  event: LogEvent;
}

const formatTime = (iso: string) => {
  return new Date(iso).toTimeString().slice(0, 8);
};

const getBadgeClass = (eventType: string) => {
  switch (eventType) {
    case 'pipeline_started':
      return 'bg-blue-900/60 text-blue-300';
    case 'scout_complete':
      return 'bg-teal-900/60 text-teal-300';
    case 'pipeline_error':
      return 'bg-red-900/60 text-red-300';
    case 'human_approved':
      return 'bg-green-900/60 text-green-300';
    case 'human_skipped':
      return 'bg-zinc-800 text-zinc-500';
    default:
      return 'bg-zinc-800 text-zinc-600';
  }
};

const getDetail = (event: LogEvent) => {
  switch (event.event) {
    case 'pipeline_started':
      return `Query: ${event.query}`;
    case 'scout_complete':
      return `${event.jobs_found} jobs discovered`;
    case 'pipeline_error':
      return `Error: ${event.error}`;
    case 'human_approved':
      return `Approved job ${event.job_id?.slice(0, 8)}`;
    case 'human_skipped':
      return `Skipped job ${event.job_id?.slice(0, 8)}`;
    default:
      const { event: e, pipeline_id, job_id, timestamp, ...rest } = event;
      const str = JSON.stringify(rest);
      return str.length > 120 ? str.slice(0, 117) + "..." : str;
  }
};

export default function LogEntry({ event }: LogEntryProps) {
  const showJobId = event.job_id && event.event !== "human_approved" && event.event !== "human_skipped";

  return (
    <div className="flex items-start gap-3 py-2 px-6 border-b border-zinc-900/60 hover:bg-zinc-900/30 transition-colors">
      <span className="text-zinc-600 text-xs font-mono shrink-0 w-20 pt-0.5">
        {formatTime(event.timestamp)}
      </span>

      <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium font-mono ${getBadgeClass(event.event)}`}>
        {event.event}
      </span>

      <span className="flex-1 min-w-0 text-zinc-400 text-xs">
        {getDetail(event)}
      </span>

      {showJobId && (
        <span className="bg-zinc-800 text-zinc-600 rounded px-1.5 py-0.5 text-xs font-mono shrink-0">
          {event.job_id!.slice(0, 8)}…
        </span>
      )}
    </div>
  );
}
