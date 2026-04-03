"use client";
import { useState, useEffect, useRef } from 'react';
import { useAgentLogs } from '@/lib/websocket';
import { LogEvent } from '@/types';
import LogEntry from '@/components/agents/LogEntry';

const formatTime = (iso: string) => {
  return new Date(iso).toTimeString().slice(0, 8);
};

export default function LogsPage() {
  const { logs, connected } = useAgentLogs();
  const [localLogs, setLocalLogs] = useState<LogEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLocalLogs(logs);
  }, [logs]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localLogs]);

  const handleClear = () => {
    setLocalLogs([]);
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(localLogs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'autoapply-logs.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const uniquePipelines = new Set(localLogs.map(l => l.pipeline_id).filter(Boolean)).size;

  return (
    <div className="bg-zinc-950 min-h-screen flex flex-col text-white">
      {/* HEADER */}
      <div className="flex justify-between items-center px-6 py-4 border-b border-zinc-800 shrink-0">
        <h1 className="text-white text-xl font-bold font-mono">Agent Logs</h1>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-500'}`} />
          <span className={`text-xs font-mono ${connected ? 'text-green-400' : 'text-red-400'}`}>
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="flex gap-2">
          <button onClick={handleClear} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 text-xs rounded px-3 py-1.5 transition-colors">
            Clear
          </button>
          <button onClick={handleExport} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 text-xs rounded px-3 py-1.5 transition-colors">
            Export
          </button>
        </div>
      </div>

      {/* STATS ROW */}
      <div className="grid grid-cols-3 gap-4 px-6 py-4 border-b border-zinc-800 shrink-0">
        <div>
          <p className="text-zinc-500 text-xs uppercase tracking-wider">Events</p>
          <p className="text-white text-xl font-mono font-bold">{localLogs.length}</p>
        </div>
        <div>
          <p className="text-zinc-500 text-xs uppercase tracking-wider">Pipelines</p>
          <p className="text-white text-xl font-mono font-bold">{uniquePipelines}</p>
        </div>
        <div>
          <p className="text-zinc-500 text-xs uppercase tracking-wider">Last event</p>
          <p className="text-white text-xl font-mono font-bold">
            {localLogs.length > 0 && localLogs[0] ? formatTime(localLogs[0].timestamp) : "—"}
          </p>
        </div>
      </div>

      {/* LOG FEED */}
      <div className="flex-1 overflow-y-auto px-0 py-2">
        {localLogs.length === 0 ? (
          <div className="py-20 text-center text-zinc-600 text-sm font-mono">
            Waiting for agent events...<span className="animate-pulse text-zinc-400">█</span>
          </div>
        ) : (
          localLogs.map((e, i) => (
            <LogEntry event={e} key={`${e.timestamp}-${i}`} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
