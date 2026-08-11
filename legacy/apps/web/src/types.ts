export type SourceMode = "ftp" | "api" | "crawler" | "legacy" | string;

export type SourcePhase = "basico" | "coleta" | "refinamento" | "avancado" | string;

export type SourceSummary = {
  source: string;
  title: string;
  mode: SourceMode;
};

export type SourceParam = {
  name: string;
  type: string;
  description: string;
  phase: SourcePhase;
  required: boolean;
  default?: unknown;
  allowed_values?: string[] | null;
  minimum?: number | null;
  maximum?: number | null;
  label?: string;
  ui_group?: "basic" | "advanced";
};

export type SourceSchema = {
  source: string;
  title: string;
  mode: SourceMode;
  params: SourceParam[];
};

export type JobStatus = {
  job_id: string;
  source: string;
  params: Record<string, unknown>;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | string;
  progress: number;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  files_total: number;
  files_completed: number;
  bytes_downloaded: number;
  bytes_total?: number | null;
  elapsed_seconds: number;
  eta_seconds?: number | null;
  output_dir?: string | null;
  current_file?: string | null;
};

export type DiscoveryResult = {
  source: string;
  documents_found: number;
  total_size_bytes: number;
  by_group: Record<string, number>;
  by_state: Record<string, number>;
  sample: Array<Record<string, unknown>>;
  filters: Record<string, unknown>;
};

export type FieldValue = string | number | boolean | string[] | null;
export type FormValues = Record<string, FieldValue>;
