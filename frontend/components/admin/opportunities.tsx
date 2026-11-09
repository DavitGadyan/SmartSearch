"use client";

import Link from "next/link";
import { useState } from "react";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Badge, Card, Chip, Empty, Skeleton } from "@/components/ui";

type Opp = { type: string; severity: "high" | "medium" | "low"; title: string; detail: string; entity: string | number | null; impact: number | null; actions: string[] };
type Resp = { window: { start: string; end: string }; site: Record<string, number>; count: number; opportunities: Opp[] };

const TONE = { high: "critical", medium: "warning", low: "neutral" } as const;
const TYPE: Record<string, string> = {
  low_conversion_query: "Low-converting query",
  high_ctr_low_conversion_query: "Clicks without purchases",
  zero_results_query: "Zero results",
  out_of_stock_demand: "Out-of-stock demand",
  low_ctr_product: "Low-CTR product",
  cold_start_inventory: "Cold-start inventory",
};

/** Rule-based scans over the marts, ranked by estimated revenue at stake. */
export function OpportunityList({ days, limit = 12 }: { days: number; limit?: number }) {
  const [type, setType] = useState<string | null>(null);
  const { data, isLoading } = useAdmin<Resp>("/analytics/opportunities", { days, limit });
  if (isLoading || !data) return <Skeleton className="h-64" />;
  const types = Array.from(new Set(data.opportunities.map((o) => o.type)));
  const list = data.opportunities.filter((o) => !type || o.type === type);
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        <Chip active={!type} onClick={() => setType(null)}>
          All · {data.count}
        </Chip>
        {types.map((t) => (
          <Chip key={t} active={type === t} onClick={() => setType(t)}>
            {TYPE[t] ?? t} · {data.opportunities.filter((o) => o.type === t).length}
          </Chip>
        ))}
      </div>
      {list.length === 0 ? (
        <Empty title="Nothing flagged" />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.map((o, i) => {
            const href = typeof o.entity === "string" && o.type.includes("query") ? `/search?q=${encodeURIComponent(o.entity)}` : typeof o.entity === "number" ? `/product/${o.entity}` : null;
            return (
              <li key={`${o.type}-${o.entity}-${i}`}>
                <Card className="flex h-full flex-col p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-xs text-muted">{TYPE[o.type] ?? o.type}</p>
                    <Badge tone={TONE[o.severity]}>{o.severity}</Badge>
                  </div>
                  <h3 className="mt-1 font-medium leading-snug">{href ? <Link href={href} className="hover:underline">{o.title}</Link> : o.title}</h3>
                  <p className="mt-1 text-sm text-fg-2">{o.detail}</p>
                  <div className="mt-auto flex items-baseline justify-between pt-3 text-xs">
                    <span className="text-muted">{o.actions[0]}</span>
                    <span className="tnum font-semibold">{o.impact != null ? fmt.money0(o.impact) : ""}</span>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
