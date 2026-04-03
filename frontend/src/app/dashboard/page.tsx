"use client";
import { useState } from 'react';
import useSWR from 'swr';
import { getApplications, getStats, getApplicationDetail } from '@/lib/api';
import JobCard from '@/components/ui/JobCard';
import SidePanel from '@/components/ui/SidePanel';
import SearchModal from '@/components/ui/SearchModal';
import StatsBar from '@/components/ui/StatsBar';

export default function DashboardPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);

  const { data: applications, isLoading: appsLoading } = useSWR('applications', getApplications, { refreshInterval: 15000 });
  const { data: stats } = useSWR('stats', getStats, { refreshInterval: 30000 });
  const { data: detail } = useSWR(
    selectedId ? `detail-${selectedId}` : null,
    () => selectedId ? getApplicationDetail(selectedId) : null
  );

  return (
    <div className="bg-zinc-950 min-h-screen text-white flex flex-col">
      <div className="flex justify-between items-center px-6 py-4 border-b border-zinc-800">
        <h1 className="text-xl font-bold">Applied Jobs</h1>
        <button
          onClick={() => setSearchOpen(true)}
          className="bg-blue-600 hover:bg-blue-500 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
        >
          Search Jobs
        </button>
      </div>

      <StatsBar stats={stats} />

      <div className="flex flex-1 overflow-hidden relative">
        <div className="flex-1 p-6 overflow-y-auto">
          {appsLoading ? (
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-zinc-900 animate-pulse rounded-xl h-36" />
              ))}
            </div>
          ) : applications && applications.length > 0 ? (
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {applications.map((app) => (
                <JobCard
                  key={app.id}
                  application={app}
                  isSelected={selectedId === app.id}
                  onSelect={setSelectedId}
                />
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-48 mt-10">
              <p className="text-zinc-500">No applications yet. Start a search.</p>
            </div>
          )}
        </div>

        <SidePanel
          detail={detail || null}
          onClose={() => setSelectedId(null)}
        />
      </div>

      <SearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
      />
    </div>
  );
}
