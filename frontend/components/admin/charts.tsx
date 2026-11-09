"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)"];

type Row = Record<string, string | number | null | undefined>;
type TipProps = {
  active?: boolean;
  label?: string | number;
  payload?: { dataKey?: string | number; name?: string | number; value?: number | string; color?: string }[];
  format?: (v: number, key: string) => string;
};

function Tip({ active, payload, label, format }: TipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-tile border border-border bg-surface px-3 py-2 text-xs shadow-[var(--shadow-card)]">
      <p className="mb-1 font-medium text-fg">{label}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-fg-2">
          <span className="inline-block size-2 rounded-full" style={{ background: p.color }} />
          {p.name}: <span className="tnum text-fg">{format ? format(Number(p.value), String(p.dataKey)) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

export function TimeSeries({ data, series, x = "day", height = 220, format, yFormat }: { data: Row[]; series: { key: string; name: string; color?: string }[]; x?: string; height?: number; format?: (v: number, key: string) => string; yFormat?: (v: number) => string }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="0" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} minTickGap={32} tickFormatter={(v) => (typeof v === "string" && v.length === 10 ? v.slice(5) : v)} />
        <YAxis tickLine={false} axisLine={false} width={48} tickFormatter={yFormat} />
        <Tooltip content={<Tip format={format} />} cursor={{ stroke: "var(--border-strong)" }} />
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color ?? SERIES[i % SERIES.length]} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} animationDuration={700} animationEasing="ease-out" />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Bars({ data, series, x, height = 220, format, yFormat, horizontal }: { data: Row[]; series: { key: string; name: string; color?: string }[]; x: string; height?: number; format?: (v: number, key: string) => string; yFormat?: (v: number) => string; horizontal?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={horizontal ? 4 : 8}>
        <CartesianGrid vertical={!!horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={yFormat} />
            <YAxis type="category" dataKey={x} tickLine={false} axisLine={false} width={120} />
          </>
        ) : (
          <>
            <XAxis dataKey={x} tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} width={48} tickFormatter={yFormat} />
          </>
        )}
        <Tooltip content={<Tip format={format} />} cursor={{ fill: "var(--surface-2)" }} />
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color ?? SERIES[i % SERIES.length]} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} animationDuration={700} animationEasing="ease-out" />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Legend({ series }: { series: { name: string; color?: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-2">
      {series.map((s, i) => (
        <li key={s.name} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color ?? SERIES[i % SERIES.length] }} /> {s.name}
        </li>
      ))}
    </ul>
  );
}
