import { useEffect, useId, useRef, useState } from "react";

export type CheckboxOption = {
  key: string;
  label: string;
};

type CheckboxDropdownProps = {
  label: string;
  options: CheckboxOption[];
  selectedKeys: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
};

export function CheckboxDropdown({
  label,
  options,
  selectedKeys,
  onChange,
  placeholder = "Todos",
}: CheckboxDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const labelId = useId();
  const summary = buildSummary(options, selectedKeys, placeholder);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  return (
    <div className="dropdown-filter" ref={containerRef}>
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
        <span>{summary}</span>
        <span aria-hidden className="dropdown-caret">▾</span>
      </button>
      {isOpen ? (
        <div className="dropdown-menu" role="group" aria-labelledby={labelId}>
          <div className="dropdown-actions">
            <button
              type="button"
              onClick={() => onChange(options.map((o) => o.key))}
            >
              Todos
            </button>
            <button type="button" onClick={() => onChange([])}>
              Limpar
            </button>
          </div>
          <div className="dropdown-options">
            {options.map((option) => {
              const checked = selectedKeys.includes(option.key);
              return (
                <label key={option.key} className="dropdown-option">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked
                        ? selectedKeys.filter((k) => k !== option.key)
                        : [...selectedKeys, option.key];
                      onChange(next);
                    }}
                  />
                  <span>{option.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function buildSummary(
  options: CheckboxOption[],
  selectedKeys: string[],
  placeholder: string
): string {
  if (selectedKeys.length === 0 || selectedKeys.length === options.length) {
    return placeholder;
  }
  if (selectedKeys.length === 1) {
    return options.find((o) => o.key === selectedKeys[0])?.label ?? "1 selecionado";
  }
  return `${selectedKeys.length} selecionados`;
}
