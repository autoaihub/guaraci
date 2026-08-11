import { useEffect, useRef, useState } from "react";
import { ops } from "../api/operations";
import { HealthBadge } from "./HealthBadge";
import "./operations.css";

interface Props {
  pollMs?: number;
}

const ACTIVE = new Set(["running", "pending", "queued"]);

// Tira de status no topo: estado global do processamento (quantos jobs em
// andamento) + saúde/versão da API. Cobre "titulação/estado do projeto".
export function OperationHeader({ pollMs = 5000 }: Props) {
  const [running, setRunning] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;

    async function tick() {
      try {
        const jobs = await ops.listJobs(50);
        if (!alive) return;
        const n = jobs.filter((j) =>
          ACTIVE.has(String(j.status || "").toLowerCase())
        ).length;
        setRunning(n);
      } catch {
        /* o HealthBadge já sinaliza queda da API; não derrubar o header */
      }
    }

    tick();
    timer.current = window.setInterval(tick, pollMs);
    return () => {
      alive = false;
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [pollMs]);

  const stateTone = running > 0 ? "info" : "ok";
  const stateLabel =
    running > 0
      ? `${running} job${running > 1 ? "s" : ""} em andamento`
      : "Ocioso";

  return (
    <header className="op-header">
      <span className="op-header__brand">Painel de operação</span>
      <div className="op-header__meta">
        <span className="op-pill" title="Estado do processamento">
          <span className={`op-dot op-dot--${stateTone}`} />
          {stateLabel}
        </span>
        <HealthBadge />
      </div>
    </header>
  );
}
