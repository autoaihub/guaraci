import { useEffect, useState } from "react";
import { api } from "../api/client";
import { JobStatusView } from "../components/JobStatus";
import { SchemaForm } from "../components/SchemaForm";
import { SourcePicker } from "../components/SourcePicker";
import type { FormValues, SourceSchema, SourceSummary } from "../types";

export function DownloadPage() {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [schema, setSchema] = useState<SourceSchema | null>(null);
  const [values, setValues] = useState<FormValues>({});
  const [submitting, setSubmitting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSources().then(setSources).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) {
      setSchema(null);
      return;
    }
    setSchema(null);
    api
      .getSchema(selected)
      .then((s) => {
        setSchema(s);
        const defaults: FormValues = {};
        for (const p of s.params) {
          if (p.default !== undefined && p.default !== null) {
            defaults[p.name] = p.default as FormValues[string];
          }
        }
        setValues(defaults);
      })
      .catch((e) => setError(String(e)));
  }, [selected]);

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      const cleaned = stripEmpty(values);
      const job = await api.createJob(selected, cleaned);
      setActiveJobId(job.job_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <h1>Guaraci</h1>
        <p>Coleta de dados públicos de saúde do Brasil.</p>
      </header>

      {error ? <div className="notice notice-fail">{error}</div> : null}

      <section className="panel">
        <h2>1. Escolha a fonte</h2>
        <SourcePicker sources={sources} selected={selected} onSelect={setSelected} />
      </section>

      {selected ? (
        <section className="panel">
          <h2>2. Configure os filtros</h2>
          {schema ? (
            <>
              <SchemaForm schema={schema} values={values} onChange={setValues} />
              <div className="page-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={submitting}
                  onClick={submit}
                >
                  {submitting ? "Enviando…" : "Iniciar download"}
                </button>
              </div>
            </>
          ) : (
            <p className="muted">Carregando schema…</p>
          )}
        </section>
      ) : null}

      {activeJobId ? (
        <section className="panel">
          <h2>3. Acompanhamento</h2>
          <JobStatusView
            jobId={activeJobId}
            onClose={() => setActiveJobId(null)}
          />
        </section>
      ) : null}
    </>
  );
}

function stripEmpty(values: FormValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) {
    if (v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = v;
  }
  return out;
}
