"use client";
import { useState } from 'react';
import useSWR from 'swr';
import { getEmailThreads } from '@/lib/api';
import { Mail } from 'lucide-react';
import EmailThreadCard from '@/components/ui/EmailThreadCard';

type FilterType = "all" | "interview_invite" | "assessment" | "follow_up_needed" | "rejection";

export default function GmailPage() {
  const { data: threads } = useSWR('emails', getEmailThreads, { refreshInterval: 30000 });
  const [activeFilter, setActiveFilter] = useState<FilterType>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredThreads = activeFilter === "all"
    ? threads ?? []
    : (threads ?? []).filter(t => t.classification === activeFilter);

  const filterTabs: { label: string; value: FilterType }[] = [
    { label: "All", value: "all" },
    { label: "Interview", value: "interview_invite" },
    { label: "Assessment", value: "assessment" },
    { label: "Follow-up", value: "follow_up_needed" },
    { label: "Rejected", value: "rejection" }
  ];

  return (
    <div className="px-6 py-6 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-white text-2xl font-bold">Gmail Inbox</h1>
        <button
          onClick={() => window.open('/auth/gmail', '_blank')}
          className="flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 transition-colors"
        >
          <Mail size={14} /> Connect Gmail
        </button>
      </div>

      <div className="flex gap-2 mb-5 flex-wrap">
        {filterTabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveFilter(tab.value)}
            className={`rounded-full px-3 py-1 text-sm cursor-pointer transition-colors ${
              activeFilter === tab.value
                ? 'bg-blue-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {filteredThreads.length > 0 ? (
        <div className="flex flex-col gap-2">
          {filteredThreads.map((thread) => (
            <EmailThreadCard
              key={thread.id}
              thread={thread}
              isExpanded={expandedId === thread.id}
              onToggle={() => setExpandedId(expandedId === thread.id ? null : thread.id)}
            />
          ))}
        </div>
      ) : threads !== undefined ? (
        <div className="py-20 text-center">
          <Mail size={40} className="text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">No emails tracked yet</p>
        </div>
      ) : null}
    </div>
  );
}
