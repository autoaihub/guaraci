// Operações de acompanhamento de processo: saúde da API, versão, histórico de
// jobs, logs e saída. Espelha o estilo de `client.ts` (mesmo base `/api` e
// helper `request`). Mantido separado para isolar a camada de "console de
// operador"; pode ser consolidado em `client.ts` numa limpeza futura.

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

export interface HealthResponse {
  status: string;
  version: string;
}

// Espelha JobStatusResponse do backend (guaraci/api/main.py). Campos opcionais
// porque o backend só os preenche conforme o job avança.
export interface JobSummary {
  job_id: string;
  source: string;
  status: string;
  progress?: number | null;
  attempt?: number | null;
  current_file?: string | null;
  files_completed?: number | null;
  files_total?: number | null;
  bytes_downloaded?: number | null;
  bytes_total?: number | null;
  elapsed_seconds?: number | null;
  eta_seconds?: number | null;
  output_dir?: string | null;
  error?: string | null;
  result?: {
    downloaded_count?: number | null;
    failed_count?: number | null;
    skipped_count?: number | null;
  } | null;
}

// Espelha JobLogResponse.
export interface JobLog {
  timestamp_utc?: string | null;
  event?: string | null;
  level?: string | null;
  message?: string | null;
}

// Espelha JobOutputResponse.
export interface JobOutput {
  job_id: string;
  status: string;
  output_dir?: string | null;
  host_output_dir?: string | null;
  output_format?: string | null;
  exported_files?: string[] | null;
  export_warning?: string | null;
  manifest_path?: string | null;
  materialized_paths?: string[] | null;
  available?: boolean | null;
}

// Espelha OpenOutputResponse.
export interface OpenOutputResponse {
  opened?: boolean;
  message?: string | null;
  detail?: string | null;
  output_dir?: string | null;
  host_output_dir?: string | null;
}

export const ops = {
  health: () => request<HealthResponse>("/health"),
  listJobs: (limit = 40) => request<JobSummary[]>(`/jobs?limit=${limit}`),
  getJob: (jobId: string) =>
    request<JobSummary>(`/jobs/${encodeURIComponent(jobId)}`),
  getJobLogs: (jobId: string, limit = 200) =>
    request<JobLog[]>(`/jobs/${encodeURIComponent(jobId)}/logs?limit=${limit}`),
  retryJob: (jobId: string) =>
    request<JobSummary>(`/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
    }),
  cancelJob: (jobId: string) =>
    request<JobSummary>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),
  getJobOutput: (jobId: string) =>
    request<JobOutput>(`/jobs/${encodeURIComponent(jobId)}/output`),
  openOutput: (jobId: string) =>
    request<OpenOutputResponse>(
      `/jobs/${encodeURIComponent(jobId)}/open-output`,
      { method: "POST" }
    ),
};

export type StatusTone = "ok" | "fail" | "warn" | "info";

// Mapa de status -> tom visual, alinhado às classes da UI legada
// (status-queued=warn, status-running=accent, status-completed=ok, etc.).
const STATUS_TONE: Record<string, StatusTone> = {
  queued: "warn",
  pending: "warn",
  running: "info",
  cancel_requested: "warn",
  canceled: "warn",
  cancelled: "warn",
  completed: "ok",
  failed: "fail",
};

export function statusTone(status?: string | null): StatusTone {
  return STATUS_TONE[String(status || "").toLowerCase()] ?? "info";
}

const TERMINAL = new Set(["completed", "failed", "canceled", "cancelled"]);

export function isTerminal(status?: string | null): boolean {
  return TERMINAL.has(String(status || "").toLowerCase());
}
