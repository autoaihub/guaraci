import { useMemo, useState } from "react";
import type { SourceSummary } from "../types";

type SourcePickerProps = {
  sources: SourceSummary[];
  selected: string | null;
  onSelect: (source: string) => void;
};

type Category = {
  id: string;
  label: string;
  matches: (mode: string) => boolean;
};

const CATEGORIES: Category[] = [
  { id: "opendatasus", label: "OpenDataSUS", matches: (m) => m.includes("opendatasus") },
  { id: "datasus", label: "DataSUS FTP", matches: (m) => m.includes("pysus") || m.includes("ftp") },
  { id: "saneamento", label: "Saneamento", matches: (m) => m.includes("crawl") || m.includes("gov.br") },
];

function categoryOf(mode: string): Category | undefined {
  const m = mode.toLowerCase();
  return CATEGORIES.find((c) => c.matches(m));
}

function normalize(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

export function SourcePicker({ sources, selected, onSelect }: SourcePickerProps) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const normalizedQuery = normalize(query.trim());

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const src of sources) {
      const cat = categoryOf(src.mode);
      if (cat) out[cat.id] = (out[cat.id] ?? 0) + 1;
    }
    return out;
  }, [sources]);

  const filtered = useMemo(() => {
    let list = sources;
    if (activeCategory) {
      const cat = CATEGORIES.find((c) => c.id === activeCategory);
      if (cat) list = list.filter((s) => cat.matches(s.mode.toLowerCase()));
    }
    if (normalizedQuery) {
      list = list.filter((s) => {
        const haystack = `${normalize(s.title)} ${normalize(s.source)} ${normalize(s.mode)}`;
        return haystack.includes(normalizedQuery);
      });
    }
    return [...list].sort((a, b) => a.title.localeCompare(b.title, "pt-BR"));
  }, [sources, activeCategory, normalizedQuery]);

  const grouped = useMemo(() => {
    const map = new Map<string, { category: Category; items: SourceSummary[] }>();
    for (const src of filtered) {
      const cat = categoryOf(src.mode);
      if (!cat) continue;
      if (!map.has(cat.id)) map.set(cat.id, { category: cat, items: [] });
      map.get(cat.id)!.items.push(src);
    }
    return [...map.values()];
  }, [filtered]);

  if (sources.length === 0) {
    return <p className="muted">Nenhuma fonte disponível.</p>;
  }

  return (
    <div className="source-picker">
      <div className="source-toolbar">
        <input
          type="search"
          className="source-search"
          placeholder="Buscar fonte…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="source-filters" role="tablist">
          <button
            type="button"
            role="tab"
            className={`source-filter${activeCategory === null ? " is-active" : ""}`}
            onClick={() => setActiveCategory(null)}
            aria-selected={activeCategory === null}
          >
            Todas <span className="source-filter-count">{sources.length}</span>
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              role="tab"
              className={`source-filter${activeCategory === cat.id ? " is-active" : ""}`}
              onClick={() => setActiveCategory(cat.id)}
              aria-selected={activeCategory === cat.id}
              disabled={!counts[cat.id]}
            >
              {cat.label} <span className="source-filter-count">{counts[cat.id] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="muted source-empty">
          Nenhuma fonte combina com <strong>"{query}"</strong>.
        </p>
      ) : (
        <div className="source-results">
          {grouped.map(({ category, items }) => (
            <div key={category.id} className="source-group">
              <h3>
                {category.label}
                <span className="source-group-count">{items.length}</span>
              </h3>
              <ul className="source-list">
                {items.map((src) => (
                  <li key={src.source}>
                    <button
                      type="button"
                      className={`source-row${selected === src.source ? " is-selected" : ""}`}
                      onClick={() => onSelect(src.source)}
                    >
                      <span className="source-row-title">
                        {highlight(src.title, normalizedQuery)}
                      </span>
                      <span className="source-row-id">
                        {highlight(src.source, normalizedQuery)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function highlight(text: string, normalizedQuery: string) {
  if (!normalizedQuery) return text;
  const normalized = normalize(text);
  const idx = normalized.indexOf(normalizedQuery);
  if (idx === -1) return text;
  const end = idx + normalizedQuery.length;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, end)}</mark>
      {text.slice(end)}
    </>
  );
}
