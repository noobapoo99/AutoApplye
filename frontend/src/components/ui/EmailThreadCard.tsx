import { EmailThread } from '@/types';
import { ChevronDown, ChevronUp, Copy } from 'lucide-react';
import { useState } from 'react';
import { format } from 'date-fns';

interface EmailThreadCardProps {
  thread: EmailThread;
  isExpanded: boolean;
  onToggle: () => void;
}

const ClassificationBadge = ({ classification }: { classification: string }) => {
  const badgeConfig: Record<string, { className: string; label: string }> = {
    interview_invite: { className: 'bg-green-900/60 text-green-300', label: 'Interview' },
    rejection: { className: 'bg-red-900/60 text-red-300', label: 'Rejected' },
    assessment: { className: 'bg-blue-900/60 text-blue-300', label: 'Assessment' },
    follow_up_needed: { className: 'bg-amber-900/60 text-amber-300', label: 'Follow-up' },
    other: { className: 'bg-zinc-800 text-zinc-400', label: 'Other' },
  };

  const config = badgeConfig[classification] || badgeConfig.other;

  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  );
};

export default function EmailThreadCard({ thread, isExpanded, onToggle }: EmailThreadCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (thread.draft_followup) {
      navigator.clipboard.writeText(thread.draft_followup);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <div
        className="p-4 cursor-pointer hover:bg-zinc-800/40 transition-colors"
        onClick={onToggle}
      >
        <div className="flex justify-between items-center">
          <ClassificationBadge classification={thread.classification} />
          <div className="flex items-center gap-2">
            {thread.received_at && (
              <span className="text-zinc-500 text-xs text-right">
                {format(new Date(thread.received_at), 'MMM d, h:mm a')}
              </span>
            )}
            {isExpanded ? (
              <ChevronUp size={14} className="text-zinc-600 ml-2" />
            ) : (
              <ChevronDown size={14} className="text-zinc-600 ml-2" />
            )}
          </div>
        </div>
        <p className="text-zinc-300 text-sm font-medium truncate mt-1">{thread.sender}</p>
        <p className="text-zinc-500 text-sm truncate mt-0.5">{thread.subject}</p>
      </div>

      {isExpanded && (
        <div className="border-t border-zinc-800 p-4">
          <h4 className="text-zinc-500 text-xs uppercase tracking-wider mb-2">AI Summary</h4>
          {thread.ai_summary ? (
            <p className="text-zinc-300 text-sm leading-relaxed">{thread.ai_summary}</p>
          ) : (
            <p className="text-zinc-600 text-sm leading-relaxed">No summary available</p>
          )}

          {thread.draft_followup && (
            <div className="mt-4">
              <h4 className="text-zinc-500 text-xs uppercase tracking-wider mb-2">Draft Reply</h4>
              <div className="bg-zinc-800 rounded-lg p-3 text-zinc-300 text-xs font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                {thread.draft_followup}
              </div>
              <button
                onClick={handleCopy}
                className="mt-2 flex items-center gap-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded px-3 py-1.5 transition-colors"
              >
                <Copy size={12} />
                {copied ? "Copied!" : "Copy Reply"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
