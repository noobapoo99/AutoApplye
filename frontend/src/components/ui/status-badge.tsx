import { ApplicationStatus } from "@/types";
import { cn } from "@/lib/utils";

const statusStyles: Record<string, string> = {
  [ApplicationStatus.applied]:
    "border-status-applied/25 bg-status-applied/15 text-status-applied",
  [ApplicationStatus.interview]:
    "border-status-interview/25 bg-status-interview/15 text-status-interview",
  [ApplicationStatus.rejected]:
    "border-status-rejected/25 bg-status-rejected/15 text-status-rejected",
  [ApplicationStatus.flagged_human]:
    "border-status-flagged/25 bg-status-flagged/15 text-status-flagged",
  [ApplicationStatus.withdrawn]:
    "border-status-withdrawn/25 bg-status-withdrawn/15 text-status-withdrawn",
  [ApplicationStatus.discovered]:
    "border-slate-400/20 bg-slate-400/10 text-slate-600 dark:text-slate-300",
  [ApplicationStatus.researching]:
    "border-cyan-400/20 bg-cyan-400/10 text-cyan-700 dark:text-cyan-300",
  [ApplicationStatus.resume_editing]:
    "border-violet-400/20 bg-violet-400/10 text-violet-700 dark:text-violet-300",
  [ApplicationStatus.applying]:
    "border-orange-400/20 bg-orange-400/10 text-orange-700 dark:text-orange-300",
  [ApplicationStatus.email_received]:
    "border-sky-400/20 bg-sky-400/10 text-sky-700 dark:text-sky-300",
};

const statusLabels: Record<string, string> = {
  [ApplicationStatus.flagged_human]: "Flagged",
  [ApplicationStatus.resume_editing]: "Resume Editing",
  [ApplicationStatus.email_received]: "Email Received",
};

interface StatusBadgeProps {
  status: ApplicationStatus | string;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const label =
    statusLabels[status] ??
    String(status)
      .replace(/_/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold tracking-wide",
        statusStyles[status] ??
          "border-slate-400/20 bg-slate-400/10 text-slate-700 dark:text-slate-300",
        className,
      )}
    >
      {label}
    </span>
  );
}
