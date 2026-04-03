import axios from "axios";

import type { Application, EmailThread, FlaggedJob, Stats } from "@/types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "",
});

type ReviewDecision = "proceed" | "skip";
type StrategyName =
  | "keyword_injection"
  | "summary_rewrite"
  | "skills_reorder"
  | (string & {});

export async function getApplications(): Promise<Application[]> {
  const { data } = await api.get<Application[]>("/api/applications");
  return data;
}

export async function getApplicationDetail(
  id: string,
): Promise<{ application: Application; email_threads: EmailThread[] }> {
  const { data } = await api.get<Application & { email_threads?: EmailThread[] }>(
    `/api/applications/${id}`,
  );
  const { email_threads = [], ...application } = data;
  return {
    application,
    email_threads,
  };
}

export async function getFlagged(): Promise<FlaggedJob[]> {
  const { data } = await api.get<FlaggedJob[]>("/api/flagged");
  return data;
}

export async function getEmailThreads(): Promise<EmailThread[]> {
  const { data } = await api.get<EmailThread[]>("/api/emails");
  return data;
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get<Stats>("/api/stats");
  return data;
}

export async function submitReviewDecision(
  job_id: string,
  decision: ReviewDecision,
): Promise<void> {
  await api.post(`/api/review/${job_id}`, {
    job_id,
    decision,
  });
}

export async function triggerJobSearch(
  query: string,
  max_jobs = 5,
  strategy: StrategyName = "keyword_injection",
): Promise<{ pipeline_id: string }> {
  const { data } = await api.post<{
    pipeline_id: string;
    status: string;
    query: string;
  }>("/api/jobs/search", {
    query,
    max_jobs,
    strategy,
  });

  return { pipeline_id: data.pipeline_id };
}
