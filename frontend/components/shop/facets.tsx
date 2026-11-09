"use client";

import type { Facet } from "@/lib/api";
import { fmt } from "@/lib/format";
import { cn } from "@/components/ui";

const LABELS: Record<string, string> = { product_class: "Category", brand: "Brand", style: "Style", material: "Material", color: "Color", price: "Price", in_stock: "Availability" };

export type ActiveFilters = Record<string, string[]>;

export function Facets({ facets, active, onToggle, onClear }: { facets: Facet[]; active: ActiveFilters; onToggle: (name: string, value: string) => void; onClear: () => void }) {
  const count = Object.values(active).reduce((n, v) => n + v.length, 0);
  return (
    <aside className="space-y-6 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        {count > 0 && (
          <button onClick={onClear} className="text-xs text-accent hover:underline">
            Clear all ({count})
          </button>
        )}
      </div>
      {facets
        .filter((f) => f.values.length > 0 && f.name !== "in_stock")
        .map((f) => (
          <div key={f.name}>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{LABELS[f.name] ?? fmt.title(f.name)}</h3>
            <ul className="space-y-1">
              {f.values.map((v) => {
                const checked = active[f.name]?.includes(v.value) ?? false;
                return (
                  <li key={v.value}>
                    <label className={cn("flex cursor-pointer items-center justify-between gap-2 rounded-[6px] px-1.5 py-1 capitalize hover:bg-surface-2", checked && "bg-accent-soft text-accent")}>
                      <span className="flex items-center gap-2 truncate">
                        <input type="checkbox" className="accent-[var(--accent)]" checked={checked} onChange={() => onToggle(f.name, v.value)} />
                        <span className="truncate">{f.name === "price" ? priceLabel(v.value) : v.value}</span>
                      </span>
                      <span className="tnum text-xs text-muted">{v.count}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      <label className="flex cursor-pointer items-center gap-2 rounded-[6px] px-1.5 py-1 hover:bg-surface-2">
        <input type="checkbox" className="accent-[var(--accent)]" checked={active.in_stock?.includes("true") ?? false} onChange={() => onToggle("in_stock", "true")} />
        In stock only
      </label>
    </aside>
  );
}

function priceLabel(bucket: string) {
  const [lo, hi] = bucket.split("-");
  return hi ? `$${lo} to $${hi}` : `$${lo}+`;
}
