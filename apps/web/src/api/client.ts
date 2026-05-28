import type {
  DiscoveryResult,
  JobStatus,
  SourceSchema,
  SourceSummary,
} from "../types";

const API_BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return (await response.json()) as T;
}

export const api = {
  listSources: () => request<SourceSummary[]>("/sources"),
  getSchema: (source: string) =>
    request<SourceSchema>(`/sources/${encodeURIComponent(source)}/schema`),
  discover: (source: string, params: Record<string, unknown>) =>
    request<DiscoveryResult>(
      `/sources/${encodeURIComponent(source)}/discovery`,
      { method: "POST", body: JSON.stringify({ params }) }
    ),
  createJob: (source: string, params: Record<string, unknown>) =>
    request<JobStatus>("/jobs", {
      method: "POST",
      body: JSON.stringify({ source, params }),
    }),
  getJob: (jobId: string) => request<JobStatus>(`/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) =>
    request<JobStatus>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" }),
  listJobs: (limit = 20) => request<JobStatus[]>(`/jobs?limit=${limit}`),
};
