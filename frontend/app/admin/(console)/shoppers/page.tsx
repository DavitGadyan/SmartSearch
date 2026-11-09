"use client";

import { useState } from "react";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { CohortGrid, type Cohort } from "@/components/admin/cohort-grid";
import { DataTable } from "@/components/admin/table";
import { WindowSelect } from "@/components/admin/window-select";
import { Card, ErrorBox, PageHeader, Section, Skeleton } from "@/components/ui";

type Segment = { persona: string; segment: string; users: number; searches: number; clicks: number; impressions: number; buyers: number; revenue: number };
type Rail = { source: string; impressions: number; clicks: number; ctr: number | null; carts: number; purchases: number; revenue: number };
type Offline = { dataset: string; n_users_test?: number; n_items?: number; n_events?: number; split?: string; models: Record<string, Record<string, number>>; funnel?: Record<string, number> } | null;
type Recs = { rails: Rail[]; offline_eval: Offline };

export default function ShoppersPage() {
  const [days, setDays] = useState(28);
  const seg = useAdmin<Segment[]>("/analytics/segments", { days });
  const coh = useAdmin<Cohort[]>("/analytics/cohorts");
  const recs = useAdmin<Recs>("/analytics/recommendations");
  if (seg.error) return <ErrorBox error={seg.error} />;
  const off = recs.data?.offline_eval;
  const offRows = off ? Object.entries(off.models).map(([model, m]) => ({ model, ...m })) : [];
  const metricKeys = offRows[0] ? Object.keys(offRows[0]).filter((k) => k !== "model") : [];

  return (
    <>
      <PageHeader title="Shoppers & recommendations" action={<WindowSelect value={days} onChange={setDays} />} />
      <Section title="Personas" description="Behaviour by simulated shopper type.">
        {seg.data ? (
          <DataTable<Segment>
            rows={seg.data}
            rowKey={(r) => r.persona}
            dense
            columns={[
              { key: "p", header: "Persona", render: (r) => <span className="font-medium">{fmt.title(r.persona)}</span> },
              { key: "s", header: "Segment", render: (r) => r.segment },
              { key: "u", header: "Users", align: "right", render: (r) => fmt.num(r.users) },
              { key: "q", header: "Searches / user", align: "right", render: (r) => (r.searches / r.users).toFixed(2) },
              { key: "ctr", header: "CTR", align: "right", render: (r) => fmt.pct(r.clicks / r.impressions, 2) },
              { key: "conv", header: "Conversion", align: "right", render: (r) => fmt.pct(r.buyers / r.users, 2) },
              { key: "rpv", header: "Revenue / user", align: "right", render: (r) => fmt.money(r.revenue / r.users) },
            ]}
          />
        ) : (
          <Skeleton className="h-48" />
        )}
      </Section>
      <Section title="Weekly retention" description="Share of each acquisition cohort active N weeks after the first visit.">
        {coh.data ? <CohortGrid rows={coh.data} /> : <Skeleton className="h-32" />}
      </Section>
      <Section title="Recommendation rails" description="Impressions and clicks on the storefront rails.">
        {recs.data ? (
          <DataTable<Rail>
            rows={recs.data.rails}
            rowKey={(r) => r.source}
            dense
            empty="No rail impressions yet."
            columns={[
              { key: "s", header: "Rail", render: (r) => <span className="font-mono text-xs">{r.source}</span> },
              { key: "i", header: "Impressions", align: "right", render: (r) => fmt.num(r.impressions) },
              { key: "c", header: "Clicks", align: "right", render: (r) => fmt.num(r.clicks) },
              { key: "ctr", header: "CTR", align: "right", render: (r) => fmt.pct(r.ctr, 2) },
              { key: "p", header: "Purchases", align: "right", render: (r) => fmt.num(r.purchases) },
              { key: "rev", header: "Revenue", align: "right", render: (r) => fmt.money0(r.revenue) },
            ]}
          />
        ) : (
          <Skeleton className="h-32" />
        )}
      </Section>
      <Section title="Offline evaluation" description={off ? `${off.dataset} · ${off.split} · ${fmt.num(off.n_events)} events · next-item prediction on held-out time` : "Retailrocket clickstream"}>
        {off ? (
          <DataTable rows={offRows} rowKey={(r) => r.model} dense columns={[{ key: "m", header: "Model", render: (r) => <span className="font-medium">{r.model}</span> }, ...metricKeys.map((k) => ({ key: k, header: k, align: "right" as const, render: (r: Record<string, number | string>) => Number(r[k]).toFixed(4) }))]} />
        ) : (
          <Card className="p-5 text-sm text-fg-2">
            Needs Kaggle credentials: <span className="font-mono text-xs">make retailrocket</span>.
          </Card>
        )}
      </Section>
    </>
  );
}
