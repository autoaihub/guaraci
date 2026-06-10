import { useEffect, useRef, useState } from "react";
import { ops, type HealthResponse } from "../api/operations";
import "./operations.css";

interface Props {
  pollMs?: number;
}

// Badge de saúde local: faz poll de /health, mostra ponto verde/vermelho e a
// versão do backend. Cobre "saúde local" + "versionamento".
export function HealthBadge({ pollMs = 10000 }: Props) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;

    async function check() {
      try {
        const data = await ops.health();
        if (!alive) return;
        setHealth(data);
        setOnline(true);
      } catch {
        if (alive) setOnline(false);
      }
    }

    check();
    timer.current = window.setInterval(check, pollMs);
    return () => {
      alive = false;
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [pollMs]);

  const tone = online === null ? "warn" : online ? "ok" : "fail";
  const mod = online === null ? "" : online ? " op-pill--ok" : " op-pill--fail";
  const label =
    online === null ? "Conectando…" : online ? "API online" : "API offline";

  return (
    <span className={`op-pill${mod}`} title="Saúde da API">
      <span className={`op-dot op-dot--${tone}`} />
      {label}
      {health?.version ? <span className="op-version">v{health.version}</span> : null}
    </span>
  );
}
