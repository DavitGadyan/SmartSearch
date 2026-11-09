"use client";

import { useState } from "react";
import Link from "next/link";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Bars, TimeSeries } from "@/components/admin/charts";
import { JudgeCard } from "@/components/admin/judge-card";
import { RankingQuality } from "@/components/admin/ranking-quality";
import { DataTable } from "@/components/admin/table";
import { WindowSelect } from "@/components/admin/window-select";
import { Card, ErrorBox, Input, PageHeader, Section, Select, Skeleton } from "@/components/ui";

type Term = { query: string; searches: number; searchers: number; zero_result_searches: number; impressions: number; clicks: number; carts: number; purchases: number; revenue: number; ctr: number | null; conversion: number | null; zero_result_rate: number | null; avg_click_position: number | null };
type Pos = { position: number; impressions: number; clicks: number; ctr: number | null };

export default function SearchAndRankingPage() {
  const [days, setDays] = useState(28);
  const [sort, setSort] = useState("searches");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const terms = useAdmin<Term[]>("/analytics/search-terms", { days, sort, limit: 100, q: q || undefined });
  const bias = useAdmin<Pos[]>("/analytics/position-bias", { days });
  const trend = useAdmin<Record<string, number | string>[]>("/analytics/search-terms/trend", { query: selected ?? "", days }, !!selected);
  if (terms.error) return <ErrorBox error={terms.error} />;

  return (
    <>
      <PageHeader title="Search & ranking" action={<WindowSelect value={days} onChange={setDays} />} />
      <div className="stagger grid gap-4 xl:grid-cols-3">
        <Card className="p-4 xl:col-span-2">
          <p className="mb-2 text-xs font-medium">CTR by result position</p>
          {bias.data ? <Bars data={bias.data} x="position" series={[{ key: "ctr", name: "CTR" }]} height={170} format={(v) => fmt.pct(v, 2)} yFormat={(v) => fmt.pct(v, 0)} /> : <Skeleton className="h-44" />}
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium">{selected ? `“${selected}”` : "Query trend"}</p>
          <p className="mb-2 text-xs text-muted">{selected ? "Daily searches and purchases" : "Select a query below"}</p>
          {selected && trend.data ? <TimeSeries data={trend.data} series={[{ key: "searches", name: "Searches" }, { key: "purchases", name: "Purchases", color: "var(--series-3)" }]} height={150} format={(v) => fmt.num(v)} /> : <div className="h-[150px] rounded-tile bg-surface-2" />}
        </Card>
      </div>

      <Section
        title="Search terms"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Input placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 w-44 text-xs" aria-label="Filter queries" />
            <Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by" className="h-8 text-xs">
              {["searches", "revenue", "purchases", "clicks", "ctr", "conversion", "zero_result_rate"].map((s) => (
                <option key={s} value={s}>
                  Sort: {fmt.title(s)}
                </option>
              ))}
            </Select>
          </div>
        }
      >
        <DataTable<Term>
          rows={terms.data ?? []}
          rowKey={(r) => r.query}
          dense
          columns={[
            { key: "query", header: "Query", render: (r) => (
                <button onClick={() => setSelected(r.query)} className="capitalize hover:underline">
                  {r.query}
                </button>
              ) },
            { key: "searches", header: "Searches", align: "right", render: (r) => fmt.num(r.searches) },
            { key: "ctr", header: "CTR", align: "right", render: (r) => fmt.pct(r.ctr, 2) },
            { key: "pos", header: "Avg click pos.", align: "right", render: (r) => (r.avg_click_position ? Number(r.avg_click_position).toFixed(1) : "n/a") },
            { key: "purchases", header: "Purchases", align: "right", render: (r) => fmt.num(r.purchases) },
            { key: "conversion", header: "Conv. / search", align: "right", render: (r) => fmt.pct(r.conversion, 2) },
            { key: "revenue", header: "Revenue", align: "right", render: (r) => fmt.money0(r.revenue) },
            { key: "zero", header: "Zero results", align: "right", render: (r) => <span className={r.zero_result_searches > 0 ? "text-critical" : ""}>{fmt.num(r.zero_result_searches)}</span> },
            { key: "open", header: "", align: "right", render: (r) => (
                <Link href={`/search?q=${encodeURIComponent(r.query)}`} className="text-xs text-link hover:underline">
                  Open
                </Link>
              ) },
          ]}
        />
      </Section>

      <RankingQuality />

      <div className="mt-10">
        <JudgeCard />
      </div>
    </>
  );
}
