"use client";

import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Card, Skeleton } from "@/components/ui";
import { DataTable } from "./table";

type Est = { ips?: number; snips?: number; dr?: number; ess?: number; value?: number; n?: number; ips_ci95?: number[]; dr_ci95?: number[]; action_share?: Record<string, number> };
type Bandit = { status?: string; reward: string; n_logs: number; logging_value: number; actions: string[]; action_counts: Record<string, number>; policies: Record<string, Est>; context_dim: number };

/** Off-policy estimates of each ranking policy from logged experiment traffic, before it went live. */
export function PolicyCard() {
  const { data, isLoading } = useAdmin<Bandit>("/analytics/bandit");
  if (isLoading) return <Skeleton className="h-64" />;
  if (!data || data.status === "not_trained") return null;
  const rows = Object.entries(data.policies).map(([policy, e]) => ({ policy, ...e }));
  return (
    <Card className="p-4">
      <p className="text-xs font-medium">How the policy was chosen</p>
      <p className="mb-3 text-xs text-muted">
        Off-policy estimates from {fmt.num(data.n_logs)} logged searches · reward: {data.reward} · IPS, self-normalised IPS and doubly robust; ESS = effective sample size.
      </p>
      <DataTable
        rows={rows}
        rowKey={(r) => r.policy}
        dense
        columns={[
          { key: "p", header: "Policy", render: (r) => <span className="font-medium">{r.policy}</span> },
          { key: "v", header: "Logged", align: "right", render: (r) => (r.value != null ? fmt.pct(r.value, 2) : "") },
          { key: "ips", header: "IPS", align: "right", render: (r) => (r.ips != null ? fmt.pct(r.ips, 2) : "") },
          { key: "snips", header: "SNIPS", align: "right", render: (r) => (r.snips != null ? fmt.pct(r.snips, 2) : "") },
          { key: "dr", header: "Doubly robust", align: "right", render: (r) => (r.dr != null ? `${fmt.pct(r.dr, 2)} [${fmt.pct(r.dr_ci95?.[0], 1)}, ${fmt.pct(r.dr_ci95?.[1], 1)}]` : "") },
          { key: "ess", header: "ESS", align: "right", render: (r) => (r.ess != null ? fmt.num(Math.round(r.ess)) : "") },
          { key: "share", header: "Top action", render: (r) => {
              if (!r.action_share) return "";
              const [a, s] = Object.entries(r.action_share).sort((x, y) => y[1] - x[1])[0];
              return <span className="font-mono text-xs">{a} {fmt.pct(s, 0)}</span>;
            } },
        ]}
      />
    </Card>
  );
}
