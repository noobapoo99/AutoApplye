"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  Inbox,
  LayoutDashboard,
} from "lucide-react";

import { cn } from "@/lib/utils";

const tabs = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/flagged", label: "Flagged Reviews", icon: AlertTriangle },
  { href: "/gmail", label: "Gmail Inbox", icon: Inbox },
  { href: "/logs", label: "Agent Logs", icon: Activity },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="rounded-3xl border border-white/50 bg-white/75 p-2 shadow-panel backdrop-blur dark:border-white/10 dark:bg-slate-900/70">
      <div className="grid gap-2 md:grid-cols-4">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = pathname === tab.href;

          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition",
                active
                  ? "bg-slate-950 text-white dark:bg-sky-500 dark:text-slate-950"
                  : "text-slate-700 hover:bg-slate-950/5 dark:text-slate-200 dark:hover:bg-white/5",
              )}
            >
              <span
                className={cn(
                  "rounded-xl p-2 transition",
                  active
                    ? "bg-white/10 dark:bg-slate-950/20"
                    : "bg-slate-950/5 group-hover:bg-slate-950/10 dark:bg-white/5 dark:group-hover:bg-white/10",
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
