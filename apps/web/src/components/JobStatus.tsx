import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { JobStatus } from "../types";

type JobStatusViewProps = {
  jobId: string;
  onClose?: () => void;
};

export function JobStatusView({ jobId, onClose }: JobStatusViewProps) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function tick() {
      try {
        const status = await api.getJob(jobId);
        if (cancelled) return;
        setJob(status);
        if (status.status === "running" || status.status === "pending") {
          timer = window.setTimeout(tick, 1500);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }
    tick();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId]);

  if (error) {
    return (
      <div className="job-status job-status-fail">
        <strong>Erro ao acompanhar job:</strong> {error}
        {onClose ? <button type="button" onClick={onClose}>Fechar</button> : null}
      </div>
    );
  }

  if (!job) {
    return <div className="job-status">Carregando job {jobId}…</div>;
  }

  const pct = Math.round((job.progress ?? 0) * 100);
  const tone =
    job.status === "completed"
      ? "ok"
      : job.status === "failed"
      ? "fail"
      : job.status === "cancelled"
      ? "warn"
      : "info";

  return (
    <div className={`job-status job-status-${tone}`}>
      <div className="job-status-header">
        <div>
          <strong>Job {job.job_id.slice(0, 8)}</strong>
          <span className="job-source">· {job.source}</span>
        </div>
        <span className="job-state">{job.status}</span>
      </div>
      <div className="job-progress">
        <div className="job-progress-bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="job-meta">
        <span>{job.files_completed} / {job.files_total} arquivos</span>
        <span>{formatBytes(job.bytes_downloaded)} baixados</span>
        {job.eta_seconds != null ? <span>ETA {Math.round(job.eta_seconds)}s</span> : null}
      </div>
      {job.current_file ? <div className="job-current">→ {job.current_file}</div> : null}
      {job.error ? <div className="job-error">{job.error}</div> : null}
      {job.output_dir ? <div className="job-output">Saída: <code>{job.output_dir}</code></div> : null}
      <div className="job-actions">
        {(job.status === "running" || job.status === "pending") ? (
          <button type="button" onClick={() => api.cancelJob(jobId)}>Cancelar</button>
        ) : null}
        {onClose ? <button type="button" onClick={onClose}>Fechar</button> : null}
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}
