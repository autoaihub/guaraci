import { useEffect, useId, useRef, useState } from "react";

type DateRangeDropdownProps = {
  label: string;
  startDate: string;
  endDate: string;
  onStartChange: (next: string) => void;
  onEndChange: (next: string) => void;
  presets?: Array<{ label: string; months: number }>;
};

const DEFAULT_PRESETS = [
  { label: "1 mês", months: 1 },
  { label: "3 meses", months: 3 },
  { label: "12 meses", months: 12 },
];

export function DateRangeDropdown({
  label,
  startDate,
  endDate,
  onStartChange,
  onEndChange,
  presets = DEFAULT_PRESETS,
}: DateRangeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const labelId = useId();

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  function applyPreset(months: number) {
    const end = new Date();
    const start = addMonths(end, -months);
    onStartChange(toInputDate(start));
    onEndChange(toInputDate(end));
  }

  return (
    <div className="date-range-filter" ref={containerRef}>
      <span id={labelId} className="filter-title">
        {label}
      </span>
      <button
        type="button"
        className="dropdown-trigger"
        aria-labelledby={labelId}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((c) => !c)}
      >
        <span>{startDate && endDate ? `${formatDate(startDate)} → ${formatDate(endDate)}` : "Selecionar período"}</span>
        <span aria-hidden className="dropdown-caret">▾</span>
      </button>
      {isOpen ? (
        <div className="dropdown-menu">
          <div className="date-presets" aria-label="Atalhos de período">
            {presets.map((preset) => (
              <button
                key={preset.months}
                type="button"
                onClick={() => applyPreset(preset.months)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="date-range-fields">
            <label>
              <span>Início</span>
              <input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(e) => onStartChange(e.target.value)}
              />
            </label>
            <label>
              <span>Fim</span>
              <input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(e) => onEndChange(e.target.value)}
              />
            </label>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatDate(value: string) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function toInputDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function addMonths(value: Date, months: number) {
  const next = new Date(value);
  next.setMonth(next.getMonth() + months);
  return next;
}
