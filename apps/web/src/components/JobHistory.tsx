import { useEffect, useRef, useState } from "react";
import {
  ops,
  statusTone,
  isTerminal,
  type JobSummary,
} from "../api/operations";
import "./operations.css";

interface Props {
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
  pollMs?: number;
}

function pct(p?: number | null): string {
  // progress já vem em escala 0..100 do backend (guaraci/services/jobs.py).
  const v = Math.max(0, Math.min(100, Math.round(Number(p ?? 0))));
  return `${v}%`;
}

function summary(job: JobSummary): string {
  if (job.error) return job.error;
  if (!job.result) return "—";
  const d = job.result.downloaded_count ?? 0;
  const s = job.result.skipped_count ?? 0;
  const f = job.result.failed_count ?? 0;
  return `down=${d} · skip=${s} · fail=${f}`;
}

const RETRYABLE = new Set(["failed", "canceled", "cancelled"]);

// Tabela de todos os jobs (poll de /jobs) com seleção, retry e abrir pasta.
// Restaura o painel de histórico que existia na UI legada.
export function JobHistory({ selectedJobId, onSelect, pollMs = 5000 }: Props) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  async function refresh() {
    try {
      const data = await ops.listJobs(40);
      setJobs(data);
    } catch {
      /* silencioso: o HealthBadge sinaliza queda da API */
    }
  }

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, pollMs);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [pollMs]);

  async function onRetry(jobId: string) {
    setNote(null);
    try {
      const job = await ops.retryJob(jobId);
      setNote(`Retry criado: ${job.job_id.slice(0, 8)}`);
      onSelect(job.job_id);
      refresh();
    } catch (e) {
      setNote(String(e));
    }
  }

  async function onOpen(jobId: string) {
    setNote(null);
    try {
      const res = await ops.openOutput(jobId);
      if (res.opened) {
        setNote(res.message || "Pasta de saída aberta.");
      } else {
        const path = res.host_output_dir || res.output_dir || "";
        setNote(
          res.message ||
            (path ? `Abra manualmente: ${path}` : "Pasta indisponível.")
        );
      }
    } catch (e) {
      setNote(String(e));
    }
  }

  return (
    <section className="op-jobs">
      <div className="op-jobs__bar">
        <h3>Histórico de jobs</h3>
        <button type="button" className="op-btn op-btn--ghost" onClick={refresh}>
          Atualizar
        </button>
      </div>
      {note ? <div className="op-note">{note}</div> : null}
      <div className="op-table-wrap">
        <table className="op-table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Fonte</th>
              <th>Tent.</th>
              <th>Resumo</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={6} className="op-empty">
                  Nenhum job ainda.
                </td>
              </tr>
            ) : (
              jobs.map((job) => {
                const tone = statusTone(job.status);
                const canRetry = RETRYABLE.has(
                  String(job.status || "").toLowerCase()
                );
                const selected = selectedJobId === job.job_id;
                return (
                  <tr
                    key={job.job_id}
                    className={selected ? "op-row--selected" : ""}
                  >
                    <td className="op-mono">{job.job_id.slice(0, 8)}</td>
                    <td>
                      <span className={`op-status--${tone}`}>{job.status}</span>{" "}
                      ({pct(job.progress)})
                    </td>
                    <td>{job.source}</td>
                    <td>{job.attempt ?? 1}</td>
                    <td>{summary(job)}</td>
                    <td>
                      <div className="op-actions">
                        <button
                          type="button"
                          className="op-btn"
                          onClick={() => onSelect(job.job_id)}
                        >
                          Ver
                        </button>
                        <button
                          type="button"
                          className="op-btn op-btn--warn"
                          disabled={!canRetry}
                          onClick={() => onRetry(job.job_id)}
                        >
                          Retry
                        </button>
                        <button
                          type="button"
                          className="op-btn op-btn--accent"
                          disabled={!isTerminal(job.status)}
                          onClick={() => onOpen(job.job_id)}
                        >
                          Abrir
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
