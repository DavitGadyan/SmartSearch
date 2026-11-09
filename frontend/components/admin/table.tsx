import { cn } from "@/components/ui";

export type Column<T> = { key: string; header: string; align?: "left" | "right"; render: (row: T) => React.ReactNode; width?: string };

export function DataTable<T>({ rows, columns, rowKey, empty = "No data", dense }: { rows: T[]; columns: Column<T>[]; rowKey: (r: T) => string | number; empty?: string; dense?: boolean }) {
  return (
    <div className="glass overflow-x-auto rounded-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-strong/40 bg-white/30 text-left text-xs text-muted">
            {columns.map((c) => (
              <th key={c.key} className={cn("px-3 py-2 font-medium", c.align === "right" && "text-right", dense ? "py-1.5" : "py-2.5")} style={{ width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-sm text-muted">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={rowKey(r)} className="border-b border-border-strong/20 last:border-0 hover:bg-white/40">
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-3", dense ? "py-1.5" : "py-2.5", c.align === "right" && "tnum text-right")}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
