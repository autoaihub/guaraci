import type { ReactNode } from "react";
import type { FieldValue, SourceParam } from "../types";
import { CheckboxDropdown } from "./CheckboxDropdown";

type SchemaFieldProps = {
  param: SourceParam;
  value: FieldValue;
  onChange: (next: FieldValue) => void;
};

export function SchemaField({ param, value, onChange }: SchemaFieldProps) {
  const label = param.label ?? prettyLabel(param.name);
  const help = param.description?.trim();
  const required = param.required;

  if (param.allowed_values && param.allowed_values.length > 0) {
    const isList = param.type.toLowerCase().includes("list") || Array.isArray(value);
    if (isList) {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <FieldShell label={label} help={help} required={required}>
          <CheckboxDropdown
            label=""
            options={param.allowed_values.map((v) => ({ key: v, label: v }))}
            selectedKeys={selected}
            onChange={(next) => onChange(next)}
          />
        </FieldShell>
      );
    }
    return (
      <FieldShell label={label} help={help} required={required}>
        <select
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">— selecionar —</option>
          {param.allowed_values.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </FieldShell>
    );
  }

  if (param.type.toLowerCase() === "bool" || typeof value === "boolean") {
    return (
      <FieldShell label={label} help={help} required={required} inline>
        <label className="switch">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{Boolean(value) ? "Sim" : "Não"}</span>
        </label>
      </FieldShell>
    );
  }

  if (param.type.toLowerCase().includes("int") || param.type.toLowerCase().includes("number")) {
    return (
      <FieldShell label={label} help={help} required={required}>
        <input
          type="number"
          value={value == null ? "" : String(value)}
          min={param.minimum ?? undefined}
          max={param.maximum ?? undefined}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(raw === "" ? null : Number(raw));
          }}
        />
      </FieldShell>
    );
  }

  return (
    <FieldShell label={label} help={help} required={required}>
      <input
        type="text"
        value={value == null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldShell>
  );
}

function FieldShell({
  label,
  help,
  required,
  inline,
  children,
}: {
  label: string;
  help?: string;
  required: boolean;
  inline?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`field${inline ? " field-inline" : ""}`}>
      <div className="field-header">
        <span className="field-label">
          {label}
          {required ? <span className="field-required" aria-label="obrigatório">*</span> : null}
        </span>
      </div>
      {children}
      {help ? <p className="field-help">{help}</p> : null}
    </div>
  );
}

function prettyLabel(name: string) {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
