import { useEffect, useRef, useState } from "react";
import { ops, type JobLog } from "../api/operations";
import "./operations.css";

interface Props {
  jobId: string | null;
  active?: boolean;
  pollMs?: number;
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

// Normaliza o timestamp do log para "YYYY-MM-DD HH:mm:ss" em UTC, espelhando o
// formato da UI legada.
function fmtTs(raw?: string | null): string {
  if (!raw) return "--";
  const text = String(raw);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) return text;
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) {
    return text
      .replace("T", " ")
      .replace(/\.\d+/, "")
      .replace("Z", "")
      .replace("+00:00", "");
  }
  return (
    `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ` +
    `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`
  );
}

// Console de logs ao vivo de um job: faz poll de /jobs/{id}/logs, terminal
// escuro com auto-scroll e botão pausar. Cobre "visualização de logs".
export function LogConsole({ jobId, active = true, pollMs = 1500 }: Props) {
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [paused, setPaused] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    setLogs([]);
  }, [jobId]);

  useEffect(() => {
    if (!jobId || paused) return;
    const id = jobId;
    let alive = true;

    async function pull() {
      try {
        const data = await ops.getJobLogs(id, 200);
        if (alive) setLogs(data);
      } catch {
        /* silencioso: o HealthBadge sinaliza queda da API */
      }
    }

    pull();
    if (active) timer.current = window.setInterval(pull, pollMs);
    return () => {
      alive = false;
      if (timer.current !== null) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [jobId, paused, active, pollMs]);

  useEffect(() => {
    const box = boxRef.current;
    if (box && !paused) box.scrollTop = box.scrollHeight;
  }, [logs, paused]);

  if (!jobId) {
    return (
      <section className="op-logs">
        <div className="op-logs__bar">
          <h3>Logs</h3>
        </div>
        <div className="op-logbox op-empty">
          Selecione um job no histórico para ver os logs.
        </div>
      </section>
    );
  }

  return (
    <section className="op-logs">
      <div className="op-logs__bar">
        <h3>Logs · job {jobId.slice(0, 8)}</h3>
        <div className="op-logs__actions">
          <button
            type="button"
            className="op-btn op-btn--ghost"
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? "Retomar" : "Pausar"}
          </button>
        </div>
      </div>
      <div className="op-logbox" ref={boxRef}>
        {logs.length === 0
          ? "Sem logs para exibir."
          : logs.map((l, i) => {
              const lvl = String(l.level || "info").toLowerCase();
              return (
                <span className={`op-logline op-logline--${lvl}`} key={i}>
                  <span className="op-logline__ts">[{fmtTs(l.timestamp_utc)}]</span>{" "}
                  [{String(l.level || "info").toUpperCase()}] {String(l.message || "")}
                </span>
              );
            })}
      </div>
    </section>
  );
}
