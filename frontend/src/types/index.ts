export enum ApplicationStatus {
  discovered = "discovered",
  researching = "researching",
  resume_editing = "resume_editing",
  flagged_human = "flagged_human",
  applying = "applying",
  applied = "applied",
  email_received = "email_received",
  interview = "interview",
  rejected = "rejected",
  withdrawn = "withdrawn",
}

export interface EmailThread {
  id: string;
  application_id: string;
  gmail_thread_id: string;
  subject: string;
  sender: string;
  classification:
    | "interview_invite"
    | "rejection"
    | "assessment"
    | "follow_up_needed"
    | "other";
  ai_summary: string | null;
  draft_followup: string | null;
  received_at: string | null;
  dlq_attempts: number;
}

export interface Application {
  id: string;
  job_id: string;
  company_name: string;
  role_title: string;
  status: ApplicationStatus;
  match_score: number | null;
  applied_at: string | null;
  last_updated: string | null;
  resume_version_id?: string | null;
  flagged_reason?: string | null;
  hallucination_score?: number | null;
  notes?: string | null;
  form_fill_result?: Record<string, unknown> | null;
  email_threads?: EmailThread[];
}

export interface FlaggedJob {
  id: string;
  job_id: string;
  company_name: string;
  role_title: string;
  status: ApplicationStatus;
  match_score: number | null;
  flagged_reason: string | null;
  hallucination_score: number | null;
  last_updated: string | null;
}

export interface ApplicationDetail {
  application: Application;
  email_threads: EmailThread[];
}

export interface Stats {
  total_applications: number;
  status_breakdown: Record<string, number>;
  avg_match_score: number;
  cache_connected: boolean;
}

export interface LogEvent {
  event: string;
  timestamp: string;
  pipeline_id?: string;
  query?: string;
  max_jobs?: number;
  strategy?: string;
  jobs_found?: number;
  error?: string;
  job_id?: string;
  application_id?: string;
  status?: string;
  [key: string]: unknown;
}
