"use client";

import { useState } from "react";
import type { Overview } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Bars, Legend, TimeSeries } from "@/components/admin/charts";
import { OpportunityList } from "@/components/admin/opportunities";
import { WindowSelect } from "@/components/admin/window-select";
import { Card, ErrorBox, PageHeader, Rows, Section, Skeleton, Stat } from "@/components/ui";

export default function OverviewPage() {
  const [days, setDays] = useState(28);
  const { data, isLoading, error } = useAdmin<Overview>("/analytics/overview", { days });
  if (error) return <ErrorBox error={error} />;
  const k = data?.kpis;
  const d = data?.deltas ?? {};
  const funnel = k
    ? [
        { stage: "Searches", value: k.searches },
        { stage: "Clicks", value: k.clicks },
        { stage: "Carts", value: k.carts },
        { stage: "Purchases", value: k.purchases },
      ]
    : [];
  return (
    <>
      <PageHeader title="Overview" description={data ? `${data.window.start} to ${data.window.end}` : undefined} action={<WindowSelect value={days} onChange={setDays} />} />
      {isLoading || !k || !data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <>
          <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat size="lg" label="Revenue" value={k.revenue} format={fmt.money0} delta={d.revenue} />
            <Stat size="lg" label="Revenue per visitor" value={k.revenue_per_visitor} format={fmt.money} delta={d.revenue_per_visitor} />
            <Stat size="lg" label="Conversion rate" value={k.conversion_rate} format={(n) => fmt.pct(n, 2)} delta={d.conversion_rate} />
            <Stat size="lg" label="Search CTR" value={k.search_ctr} format={(n) => fmt.pct(n, 2)} delta={d.search_ctr} />
            <Stat label="Visitors" value={k.visitors} format={fmt.num} delta={d.visitors} />
            <Stat label="Searches" value={k.searches} format={fmt.num} delta={d.searches} />
            <Stat label="Average order value" value={k.aov} format={fmt.money} delta={d.aov} />
            <Stat label="Zero-result rate" value={k.zero_result_rate} format={(n) => fmt.pct(n, 2)} delta={d.zero_result_rate} invert />
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Card className="p-4 xl:col-span-2">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium">Revenue and visitors</p>
                <Legend series={[{ name: "Revenue" }, { name: "Visitors", color: "var(--series-2)" }]} />
              </div>
              <TimeSeries data={data.daily} series={[{ key: "revenue", name: "Revenue" }]} height={170} format={(v) => fmt.money0(v)} yFormat={(v) => fmt.compact(v)} />
              <TimeSeries data={data.daily} series={[{ key: "visitors", name: "Visitors", color: "var(--series-2)" }]} height={120} format={(v) => fmt.num(v)} yFormat={(v) => fmt.compact(v)} />
            </Card>
            <Card className="p-4">
              <p className="mb-2 text-xs font-medium">Search funnel</p>
              <Bars data={funnel} x="stage" series={[{ key: "value", name: "Events" }]} horizontal height={170} format={(v) => fmt.num(v)} yFormat={(v) => fmt.compact(v)} />
              <Rows
                dense
                className="mt-3"
                items={[
                  ["Click / search", fmt.pct(k.clicks / k.searches)],
                  ["Cart / click", fmt.pct(k.add_to_cart_rate)],
                  ["Buy / cart", fmt.pct(k.purchases / k.carts)],
                ]}
              />
            </Card>
          </div>
          <Card className="mt-4 p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium">Conversion and CTR</p>
              <Legend series={[{ name: "Conversion rate" }, { name: "Search CTR", color: "var(--series-3)" }]} />
            </div>
            <TimeSeries data={data.daily} series={[{ key: "conversion_rate", name: "Conversion rate" }, { key: "search_ctr", name: "Search CTR", color: "var(--series-3)" }]} height={180} format={(v) => fmt.pct(v, 2)} yFormat={(v) => fmt.pct(v, 0)} />
          </Card>
          <Section title="Revenue at stake" description="Rule-based scans of the marts, ranked by estimated impact.">
            <OpportunityList days={days} limit={12} />
          </Section>
        </>
      )}
    </>
  );
}
