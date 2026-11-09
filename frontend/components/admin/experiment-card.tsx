"use client";

import Link from "next/link";
import type { Experiment, ExperimentAnalysis } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Badge, Card, Skeleton, type Tone } from "@/components/ui";

export const STATUS_TONE: Record<string, Tone> = { running: "good", completed: "info", draft: "neutral", archived: "neutral" };
export const DECISION_TONE: Record<string, Tone> = { ship: "good", reject: "critical", continue: "neutral", iterate: "warning", investigate: "critical" };

const MONEY = new Set(["revenue_per_visitor", "aov"]);
export const metricValue = (metric: string, v: number) => (MONEY.has(metric) ? fmt.money(v) : fmt.pct(v, 2));

/** What changed, what happened, what we decided: one experiment in one card. */
export function ExperimentCard({ experiment: e }: { experiment: Experiment }) {
  const { data } = useAdmin<ExperimentAnalysis>(`/experiments/${e.key}/analysis`);
  const c = data?.status === "ok" ? data.comparisons[0] : null;
  const primary = c ? c.metrics[c.primary_metric] : null;
  const [control, treatment] = [e.variants[0], e.variants[1]];
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href={`/admin/experiments/${e.key}`} className="font-serif text-xl tracking-tight hover:underline">
            {e.name}
          </Link>
          <p className="mt-1 text-xs text-muted">
            {e.start_at ? `${fmt.date(e.start_at)} to ${e.end_at ? fmt.date(e.end_at) : "now"}` : "not started"}
            {c ? ` · ${fmt.num(c.n_control)} vs ${fmt.num(c.n_treatment)} users` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {e.surface === "ui" && <Badge tone="neutral">storefront UI</Badge>}
          {e.config.simulated_traffic && <Badge tone="warning">simulated traffic</Badge>}
          <Badge tone={STATUS_TONE[e.status]}>{e.status}</Badge>
        </div>
      </div>
      {e.config.summary && <p className="mt-3 text-sm text-fg-2">{e.config.summary}</p>}
      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        {[control, treatment].map((v, i) => (
          <div key={v.key} className="rounded-tile bg-white/45 p-3">
            <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">{i === 0 ? "Control" : "Treatment"} · {v.name ?? v.key}</dt>
            <dd className="mt-1 text-fg-2">
              {v.description ?? v.strategy ?? "—"}
              {v.ui && <span className="ml-1 text-muted">· button “{v.ui.cta_label}”, {v.ui.cta_style}</span>}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-border pt-4">
        {!data ? (
          <Skeleton className="h-10 w-72" />
        ) : !c || !primary ? (
          <p className="text-sm text-muted">No analysis yet.</p>
        ) : (
          <>
            <div>
              <p className="text-xs text-muted">{data.metric_labels[primary.metric] ?? primary.metric}</p>
              <p className="tnum mt-0.5 text-lg">
                <span className="text-fg-2">{metricValue(primary.metric, primary.control)}</span>
                <span className="mx-2 text-muted">→</span>
                <span className="font-semibold">{metricValue(primary.metric, primary.treatment)}</span>
                <span className={`ml-3 text-sm font-medium ${primary.significant ? (primary.rel_lift! > 0 ? "text-good" : "text-critical") : "text-muted"}`}>
                  {fmt.signedPct(primary.rel_lift)} · p {fmt.p(primary.p_value)}
                </span>
              </p>
            </div>
            <Badge tone={DECISION_TONE[c.decision.recommendation] ?? "neutral"}>{c.decision.label}</Badge>
          </>
        )}
      </div>
    </Card>
  );
}
