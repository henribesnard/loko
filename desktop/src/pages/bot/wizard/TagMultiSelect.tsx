import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export interface TagOption {
  id: string;
  label: string;
  group?: string;
}

interface TagMultiSelectProps {
  label: string;
  options: TagOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
  disabled?: boolean;
}

export function TagMultiSelect({
  label,
  options,
  selected,
  onChange,
  disabled,
}: TagMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [focusIdx, setFocusIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Group options for rendering
  const grouped = useMemo(() => {
    const map = new Map<string, TagOption[]>();
    for (const opt of options) {
      const g = opt.group || "";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(opt);
    }
    return map;
  }, [options]);

  // Flat list for keyboard navigation
  const flatList = useMemo(() => {
    const result: TagOption[] = [];
    for (const [, opts] of grouped) result.push(...opts);
    return result;
  }, [grouped]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Scroll focused item into view
  useEffect(() => {
    if (!open || focusIdx < 0 || !listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-option]");
    items[focusIdx]?.scrollIntoView({ block: "nearest" });
  }, [focusIdx, open]);

  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((s) => s !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setOpen(true);
        setFocusIdx(0);
      }
      return;
    }
    switch (e.key) {
      case "Escape":
        e.preventDefault();
        setOpen(false);
        break;
      case "ArrowDown":
        e.preventDefault();
        setFocusIdx((prev) => Math.min(prev + 1, flatList.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusIdx((prev) => Math.max(prev - 1, 0));
        break;
      case " ":
      case "Enter":
        e.preventDefault();
        if (focusIdx >= 0 && focusIdx < flatList.length) {
          toggle(flatList[focusIdx].id);
        }
        break;
    }
  };

  let optIdx = -1;

  return (
    <div
      ref={containerRef}
      className="relative inline-block"
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-[var(--radius-sm)]",
          "border border-[var(--border-default)] bg-[var(--surface-card)]",
          "text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {label}
        {selected.length > 0 && (
          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-brand-500 text-white">
            {selected.length}
          </span>
        )}
        <ChevronDown size={12} />
      </button>

      {open && (
        <div
          ref={listRef}
          className={cn(
            "absolute z-50 mt-1 min-w-[200px] max-h-[240px] overflow-y-auto",
            "rounded-[var(--radius-md)] border border-[var(--border-default)]",
            "bg-[var(--surface-card)] shadow-lg",
          )}
          role="listbox"
          aria-multiselectable="true"
        >
          {[...grouped.entries()].map(([group, opts]) => (
            <div key={group || "__none"}>
              {group && (
                <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)] border-b border-[var(--border-subtle)]">
                  {group}
                </div>
              )}
              {opts.map((opt) => {
                optIdx++;
                const idx = optIdx;
                const checked = selected.includes(opt.id);
                return (
                  <label
                    key={opt.id}
                    data-option
                    className={cn(
                      "flex items-center gap-2 px-3 py-2 text-xs cursor-pointer",
                      "hover:bg-[var(--surface-sunken)]",
                      idx === focusIdx && "bg-[var(--surface-sunken)]",
                    )}
                    role="option"
                    aria-selected={checked}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(opt.id)}
                      className="accent-[var(--brand-primary)]"
                      tabIndex={-1}
                    />
                    <span className="text-[var(--text-primary)]">
                      {opt.label}
                    </span>
                  </label>
                );
              })}
            </div>
          ))}
          {options.length === 0 && (
            <div className="px-3 py-2 text-xs text-[var(--text-tertiary)]">
              —
            </div>
          )}
        </div>
      )}
    </div>
  );
}
