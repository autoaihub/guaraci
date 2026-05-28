import { useEffect, useMemo, useState } from "react";
import type { Options } from "highcharts";
import { api } from "../api/client";
import { HighchartsView } from "../components/HighchartsView";
import type { JobStatus } from "../types";

export function DashboardPage() {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listJobs(50)
      .then(setJobs)
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => buildStats(jobs), [jobs]);

  if (loading) {
    return (
      <div className="page">
        <div className="panel">
          <p className="muted">Carregando histórico de jobs…</p>
        </div>
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="page">
        <div className="panel">
          <div className="dashboard-empty">
            <h2>Sem coletas ainda</h2>
            <p>Execute uma coleta na aba <strong>Coleta</strong> para ver visualizações aqui.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Visualização</h1>
          <p>Resumo das coletas executadas. Esqueleto inicial — em breve, gráficos sobre os dados baixados.</p>
        </div>
      </header>
      <div className="dashboard">
        <HighchartsView options={stats.bySourceChart} />
        <HighchartsView options={stats.byStatusChart} />
        <HighchartsView options={stats.timelineChart} />
      </div>
    </div>
  );
}

function buildStats(jobs: JobStatus[]) {
  const bySource: Record<string, number> = {};
  const byStatus: Record<string, number> = {};
  const timeline: Array<[number, number]> = [];

  for (const job of jobs) {
    bySource[job.source] = (bySource[job.source] ?? 0) + 1;
    byStatus[job.status] = (byStatus[job.status] ?? 0) + 1;
    const created = Date.parse(job.created_at);
    if (!Number.isNaN(created)) {
      timeline.push([created, job.bytes_downloaded || 0]);
    }
  }
  timeline.sort((a, b) => a[0] - b[0]);

  const bySourceChart: Options = {
    chart: { type: "column", backgroundColor: "transparent" },
    title: { text: "Coletas por fonte" },
    xAxis: { categories: Object.keys(bySource), title: { text: undefined } },
    yAxis: { title: { text: "Quantidade" }, allowDecimals: false },
    legend: { enabled: false },
    credits: { enabled: false },
    series: [
      {
        type: "column",
        name: "Jobs",
        data: Object.values(bySource),
        color: "#c84a02",
      },
    ],
  };

  const byStatusChart: Options = {
    chart: { type: "pie", backgroundColor: "transparent" },
    title: { text: "Distribuição por status" },
    credits: { enabled: false },
    series: [
      {
        type: "pie",
        name: "Jobs",
        data: Object.entries(byStatus).map(([name, y]) => ({ name, y })),
      },
    ],
  };

  const timelineChart: Options = {
    chart: { type: "areaspline", backgroundColor: "transparent" },
    title: { text: "Volume baixado ao longo do tempo" },
    xAxis: { type: "datetime" },
    yAxis: { title: { text: "Bytes" } },
    credits: { enabled: false },
    legend: { enabled: false },
    series: [
      {
        type: "areaspline",
        name: "Bytes",
        data: timeline,
        color: "#0a7a70",
        fillOpacity: 0.3,
      },
    ],
  };

  return { bySourceChart, byStatusChart, timelineChart };
}
