"use client";

import { fmt } from "@/lib/format";

export type Cohort = { cohort_week: string; weeks_since: number; active_users: number; buyers: number; cohort_size: number; retention: number };

/** Weekly retention by acquisition cohort; shade = share of the cohort active that week. */
export function CohortGrid({ rows }: { rows: Cohort[] }) {
  const weeks = Array.from(new Set(rows.map((c) => c.cohort_week))).sort();
  const maxW = Math.max(0, ...rows.map((c) => c.weeks_since));
  const cell = (w: string, k: number) => rows.find((c) => c.cohort_week === w && c.weeks_since === k);
  return (
    <div className="glass overflow-x-auto rounded-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            <th className="px-3 py-2 text-left font-medium">Cohort week</th>
            <th className="px-3 py-2 text-right font-medium">Size</th>
            {Array.from({ length: maxW + 1 }).map((_, k) => (
              <th key={k} className="px-2 py-2 text-right font-medium">
                W{k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w} className="border-b border-border last:border-0">
              <td className="px-3 py-1.5">{w}</td>
              <td className="tnum px-3 py-1.5 text-right text-fg-2">{fmt.num(cell(w, 0)?.cohort_size)}</td>
              {Array.from({ length: maxW + 1 }).map((_, k) => {
                const c = cell(w, k);
                return (
                  <td key={k} className="px-1 py-1">
                    {c ? (
                      <div className="tnum rounded-[4px] px-2 py-1 text-right text-xs" style={{ background: `color-mix(in oklab, var(--fg) ${Math.round(c.retention * 80)}%, var(--surface-2))`, color: c.retention > 0.5 ? "var(--bg)" : "var(--fg)" }}>
                        {fmt.pct(c.retention, 0)}
                      </div>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
