import type { SourceSummary } from "../types";

type SourcePickerProps = {
  sources: SourceSummary[];
  selected: string | null;
  onSelect: (source: string) => void;
};

export function SourcePicker({ sources, selected, onSelect }: SourcePickerProps) {
  if (sources.length === 0) {
    return <p className="muted">Nenhuma fonte disponível.</p>;
  }

  const byGroup = sources.reduce<Record<string, SourceSummary[]>>((acc, src) => {
    const key = guessGroup(src);
    acc[key] = acc[key] ?? [];
    acc[key].push(src);
    return acc;
  }, {});

  return (
    <div className="source-picker">
      {Object.entries(byGroup).map(([group, items]) => (
        <div key={group} className="source-group">
          <h3>{group}</h3>
          <div className="source-grid">
            {items.map((src) => (
              <button
                key={src.source}
                type="button"
                className={`source-card${selected === src.source ? " is-selected" : ""}`}
                onClick={() => onSelect(src.source)}
              >
                <span className="source-mode">{src.mode}</span>
                <span className="source-title">{src.title}</span>
                <span className="source-id">{src.source}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function guessGroup(src: SourceSummary): string {
  const id = src.source.toLowerCase();
  if (id.startsWith("snis") || id.startsWith("sinisa")) return "Saneamento";
  if (id.startsWith("sim") || id.startsWith("sih") || id.startsWith("sinan")) return "DataSUS";
  return "OpenDataSUS";
}
