import { Stats } from '@/types';
import { Briefcase, Target, Calendar, XCircle } from 'lucide-react';

interface StatsBarProps {
  stats: Stats | undefined;
}

export default function StatsBar({ stats }: StatsBarProps) {
  const cards = [
    {
      icon: <Briefcase size={18} className="text-zinc-500 mb-2" />,
      value: stats?.total_applications ?? "—",
      label: "Total Applied",
    },
    {
      icon: <Target size={18} className="text-zinc-500 mb-2" />,
      value: stats ? `${(stats.avg_match_score * 100).toFixed(0)}%` : "—",
      label: "Avg Match",
    },
    {
      icon: <Calendar size={18} className="text-zinc-500 mb-2" />,
      value: stats?.status_breakdown?.interview ?? 0,
      label: "Interviews",
    },
    {
      icon: <XCircle size={18} className="text-zinc-500 mb-2" />,
      value: stats?.status_breakdown?.rejected ?? 0,
      label: "Rejected",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 px-6 py-4">
      {cards.map((card, i) => (
        <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col justify-between">
          <div>{card.icon}</div>
          {stats === undefined ? (
            <div className="bg-zinc-800 animate-pulse h-7 w-12 rounded my-1" />
          ) : (
            <p className="text-white text-2xl font-bold font-mono">{card.value}</p>
          )}
          <p className="text-zinc-500 text-xs uppercase tracking-wider mt-0.5">{card.label}</p>
        </div>
      ))}
    </div>
  );
}
