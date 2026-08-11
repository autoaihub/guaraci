import { useMemo, useState } from "react";
import type { FieldValue, FormValues, SourceParam, SourceSchema } from "../types";
import { SchemaField } from "./SchemaField";

type SchemaFormProps = {
  schema: SourceSchema;
  values: FormValues;
  onChange: (next: FormValues) => void;
};

function isBasic(param: SourceParam): boolean {
  if (param.ui_group) return param.ui_group === "basic";
  return param.phase === "basico" || param.phase === "coleta";
}

export function SchemaForm({ schema, values, onChange }: SchemaFormProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [basicParams, advancedParams] = useMemo(() => {
    const basic: SourceParam[] = [];
    const advanced: SourceParam[] = [];
    for (const p of schema.params) {
      (isBasic(p) ? basic : advanced).push(p);
    }
    return [basic, advanced] as const;
  }, [schema.params]);

  function setField(name: string, next: FieldValue) {
    onChange({ ...values, [name]: next });
  }

  return (
    <div className="schema-form">
      <section>
        <h3>Filtros essenciais</h3>
        {basicParams.length === 0 ? (
          <p className="muted">Nenhum filtro essencial para esta fonte.</p>
        ) : (
          <div className="fields-grid">
            {basicParams.map((p) => (
              <SchemaField
                key={p.name}
                param={p}
                value={(values[p.name] ?? (p.default as FieldValue) ?? null) as FieldValue}
                onChange={(v) => setField(p.name, v)}
              />
            ))}
          </div>
        )}
      </section>
      {advancedParams.length > 0 ? (
        <section className="advanced-section">
          <button
            type="button"
            className="advanced-toggle"
            onClick={() => setShowAdvanced((s) => !s)}
            aria-expanded={showAdvanced}
          >
            <span>Avançado ({advancedParams.length})</span>
            <span aria-hidden>{showAdvanced ? "▲" : "▼"}</span>
          </button>
          {showAdvanced ? (
            <div className="fields-grid advanced-grid">
              {advancedParams.map((p) => (
                <SchemaField
                  key={p.name}
                  param={p}
                  value={(values[p.name] ?? (p.default as FieldValue) ?? null) as FieldValue}
                  onChange={(v) => setField(p.name, v)}
                />
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
