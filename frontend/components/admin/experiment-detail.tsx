"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ExperimentAnalysis, TestResult } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Legend, TimeSeries } from "@/components/admin/charts";
import { DataTable } from "@/components/admin/table";
import { DECISION_TONE, STATUS_TONE, metricValue } from "@/components/admin/experiment-card";
import { PolicyCard } from "@/components/admin/policy-card";
import { UiPreview } from "@/components/admin/ui-preview";
import { VariantPreview } from "@/components/admin/variant-preview";
import { Badge, Button, Card, Disclosure, ErrorBox, Input, PageHeader, Rows, Section, Skeleton, cn } from "@/components/ui";

const DEFAULT_QUERY = "mid-century nightstand";
/** First two sentences of the engine's narrative; the full text is in the report. */
const lead = (text: string) => text.split(/(?<=\.)\s+(?=[A-Z])/).slice(0, 2).join(" ");

/** One experiment: what changed for shoppers, what happened to the metrics, what the engine decided. */
export function ExperimentDetail({ experimentKey }: { experimentKey: string }) {
  const { data, isLoading, error } = useAdmin<ExperimentAnalysis>(`/experiments/${experimentKey}/analysis`);
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const qc = useQueryClient();
  const complete = async () => {
    await api.admin.patch(`/experiments/${experimentKey}/status`, { status: "completed" });
    qc.invalidateQueries({ queryKey: ["admin"] });
  };
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !data) return <Skeleton className="h-96" />;
  const e = data.experiment;
  const label = (m: TestResult) => data.metric_labels[m.metric] ?? m.metric;
  const header = (
    <PageHeader
      title={e.name}
      description={e.config.summary}
      action={
        <div className="flex items-center gap-2 text-xs text-muted">
          {e.config.simulated_traffic && <Badge tone="warning">simulated traffic · assumed effect {Object.entries(e.config.simulated_traffic.assumed_effect?.treatment ?? {}).filter(([, v]) => v).map(([k, v]) => `${fmt.title(k)} ${fmt.signedPct(v, 0)}`).join(", ") || "none"}</Badge>}
          <Badge tone={STATUS_TONE[e.status]}>{e.status}</Badge>
          {e.status === "running" && e.surface === "ui" && (
            <Button size="sm" variant="secondary" onClick={complete}>
              Mark completed
            </Button>
          )}
          {e.start_at && (
            <span>
              {fmt.date(e.start_at)} to {e.end_at ? fmt.date(e.end_at) : "now"}
            </span>
          )}
        </div>
      }
    />
  );
  if (data.status === "no_data")
    return (
      <>
        {header}
        <Card className="p-8 text-center text-sm text-fg-2">No users assigned yet.</Card>
      </>
    );

  const c = data.comparisons[0];
  const primary = c.metrics[c.primary_metric];
  const secondary = Object.values(c.metrics).filter((m) => m.metric !== c.primary_metric);
  const guardrails = Object.values(c.guardrails);
  const control = e.variants.find((v) => v.key === c.control) ?? e.variants[0];
  const treatment = e.variants.find((v) => v.key === c.treatment) ?? e.variants[1];
  const daily = data.daily;
  const days = daily[0]?.days ?? [];
  const rpvSeries = days.map((d, i) => Object.fromEntries([["day", d], ...daily.map((v) => [v.variant, v.cum_rpv[i]])]));
  const ctrSeries = days.map((d, i) => Object.fromEntries([["day", d], ...daily.map((v) => [v.variant, v.daily_ctr[i]])]));
  const liftClass = (m: TestResult) => (m.significant ? (Number(m.rel_lift) > 0 ? "text-good" : "text-critical") : "text-muted");

  return (
    <>
      {header}

      <Section
        title="What changed"
        description={e.surface === "ui" ? "What shoppers in each arm see." : "The same search, ranked the way each arm ranked it for the current shopper."}
        action={
          e.surface === "ui" ? null : (
            <label className="flex items-center gap-2 text-xs text-muted">
              Preview query
              <Input value={query} onChange={(ev) => setQuery(ev.target.value)} className="h-8 w-56 text-xs" aria-label="Preview query" />
            </label>
          )
        }
      >
        <div className="stagger grid gap-4 md:grid-cols-2">
          {(
            [
              ["Control", control],
              ["Treatment", treatment],
            ] as const
          ).map(([role, v]) => (
            <Card key={v.key} className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                {role} · {v.name ?? v.key}
              </p>
              <p className="mt-1 text-sm text-fg-2">{v.description ?? v.strategy ?? "Same ranking"}</p>
              <div className="mt-4">{e.surface === "ui" && v.ui ? <UiPreview ui={v.ui} /> : <VariantPreview variant={v} query={query} />}</div>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Result" description={`${fmt.num(c.n_control)} vs ${fmt.num(c.n_treatment)} users · ${data.days_running} days · sample ratio ${data.srm.srm_detected ? "mismatch" : "balanced"}`}>
        <div className="stagger grid gap-4 lg:grid-cols-[1.1fr_1fr]">
          <Card className="p-5">
            <p className="text-xs text-muted">{label(primary)} · primary metric</p>
            <div className="mt-2 flex flex-wrap items-baseline gap-3">
              <span className="tnum text-3xl font-semibold">{metricValue(primary.metric, primary.treatment)}</span>
              <span className="tnum text-base text-muted">vs {metricValue(primary.metric, primary.control)}</span>
              <span className={cn("tnum text-base font-medium", primary.significant ? liftClass(primary) : "text-fg-2")}>{fmt.signedPct(primary.rel_lift)}</span>
            </div>
            <p className="tnum mt-2 text-xs text-muted">
              95% CI {metricValue(primary.metric, primary.ci_low)} to {metricValue(primary.metric, primary.ci_high)} · p = {fmt.p(primary.p_value)} · {primary.significant ? "significant" : "not significant"}
            </p>
            <p className="mt-1 text-xs text-fg-2">
              H0: the change does not alter {label(primary).toLowerCase()}. {primary.p_value < primary.alpha ? `Rejected at α = ${primary.alpha}.` : `Not rejected at α = ${primary.alpha} (fail to reject).`}
            </p>
            <div className="mt-5">
              <Badge tone={DECISION_TONE[c.decision.recommendation] ?? "neutral"}>{c.decision.label}</Badge>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-fg-2">{lead(c.decision.narrative)}</p>
          </Card>
          <div>
            <DataTable<TestResult>
              rows={secondary}
              rowKey={(m) => m.metric}
              dense
              columns={[
                { key: "m", header: "Metric", render: (m) => label(m) },
                { key: "c", header: control.key, align: "right", render: (m) => metricValue(m.metric, m.control) },
                { key: "t", header: treatment.key, align: "right", render: (m) => metricValue(m.metric, m.treatment) },
                { key: "l", header: "Lift", align: "right", render: (m) => <span className={liftClass(m)}>{fmt.signedPct(m.rel_lift)}</span> },
                { key: "p", header: "p", align: "right", render: (m) => fmt.p(m.p_value) },
              ]}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {guardrails.map((g) => (
                <Badge key={g.metric} tone={g.breached ? "critical" : "good"}>
                  {label(g)} · {g.breached ? "breached" : "ok"} · {fmt.signedPct(g.rel_lift)}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <Disclosure summary="Details: full narrative, power, robustness, arms, daily charts" className="mt-10">
        <p className="mb-4 text-sm leading-relaxed text-fg-2">{c.decision.narrative}</p>
        <div className="stagger grid gap-4 xl:grid-cols-3">
          <Card className="p-4">
            <p className="text-xs font-medium">Power and sample size</p>
            {c.power.required_n_per_arm ? (
              <Rows
                dense
                className="mt-2"
                items={[
                  ["Users per arm", `${fmt.num(c.power.current_n_per_arm)} / ${fmt.num(c.power.required_n_per_arm)}`],
                  ["Planned MDE", fmt.pct(c.power.mde_rel_planned, 0)],
                  ["Detectable now", fmt.pct(c.power.mde_rel_at_current_n)],
                  ["Power for observed effect", fmt.pct(c.power.achieved_power_for_observed_effect, 0)],
                  ["Always-valid p (mSPRT)", fmt.p(c.sequential.always_valid_p)],
                ]}
              />
            ) : (
              <p className="mt-2 text-sm text-fg-2">Applies to proportion metrics.</p>
            )}
          </Card>
          <Card className="p-4">
            <p className="text-xs font-medium">Revenue per user, robustness</p>
            <Rows
              dense
              className="mt-2"
              items={[
                ["Bootstrap 95% CI (diff)", `${fmt.money(c.revenue.bootstrap.ci_low)} to ${fmt.money(c.revenue.bootstrap.ci_high)}`],
                ["CUPED θ · variance removed", `${c.revenue.cuped.theta.toFixed(3)} · ${fmt.pct(c.revenue.cuped.variance_reduction, 0)}`],
                ["Welch p · CUPED p", `${fmt.p(c.metrics.revenue_per_visitor?.p_value)} · ${fmt.p(c.revenue.cuped.p_value)}`],
                ["Sample ratio χ² p", fmt.p(data.srm.p_value)],
              ]}
            />
          </Card>
          <Card className="p-4">
            <p className="text-xs font-medium">Arms</p>
            <Rows dense className="mt-2" items={data.variants.map((v) => [String(v.variant), `${fmt.num(Number(v.users))} users · ${fmt.pct(Number(v.conversion_rate), 2)} · ${fmt.money(Number(v.revenue_per_visitor))}`])} />
          </Card>
        </div>
        {days.length > 0 && (
          <div className="stagger mt-4 grid gap-4 xl:grid-cols-2">
            <Card className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium">Cumulative revenue per assigned user</p>
                <Legend series={daily.map((v) => ({ name: v.variant }))} />
              </div>
              <TimeSeries data={rpvSeries} series={daily.map((v) => ({ key: v.variant, name: v.variant }))} height={200} format={(v) => fmt.money(v)} yFormat={(v) => fmt.money0(v)} />
            </Card>
            <Card className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium">Daily search CTR</p>
                <Legend series={daily.map((v) => ({ name: v.variant }))} />
              </div>
              <TimeSeries data={ctrSeries} series={daily.map((v) => ({ key: v.variant, name: v.variant }))} height={200} format={(v) => fmt.pct(v, 2)} yFormat={(v) => fmt.pct(v, 0)} />
            </Card>
          </div>
        )}
        {e.key === "bandit_policy_v1" && (
          <div className="mt-4">
            <PolicyCard />
          </div>
        )}
      </Disclosure>
    </>
  );
}
