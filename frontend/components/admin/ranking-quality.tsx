"use client";

import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Bars } from "@/components/admin/charts";
import { DataTable } from "@/components/admin/table";
import { Badge, Card, Disclosure, ErrorBox, Section, Skeleton } from "@/components/ui";

type Model = { version: string; algorithm: string; mlflow_run_id: string | null; params: Record<string, unknown>; metrics: Record<string, number | Record<string, unknown>>; feature_importance: Record<string, number>; is_champion: boolean; trained_at: string };
type Eval = { summary: Record<string, Record<string, number | number[]>>; baseline: string; ranker_version: string | null; protocol?: string; stats_frozen_at?: string; test_split?: Record<string, Record<string, number>> };
type Ranking = { models: Model[]; offline_eval: Eval | null; mlflow_ui: string | null };
type EvalRow = { strategy: string } & Record<string, number | number[] | string>;

const STRATEGY_LABEL: Record<string, string> = { control_bm25_pop: "A · BM25 + popularity", hybrid_rrf: "B · Hybrid (RRF)", hybrid_ltr: "C · Hybrid + LambdaRank" };

/** Offline ranking quality on human judgments, feature importance and the model registry. */
export function RankingQuality() {
  const { data, isLoading, error } = useAdmin<Ranking>("/analytics/ranking");
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !data) return <Skeleton className="h-96" />;
  const ev = data.offline_eval;
  const champ = data.models.find((m) => m.is_champion);
  const rows: EvalRow[] = ev ? Object.entries(ev.summary).map(([s, m]) => ({ strategy: s, ...m }) as EvalRow) : [];
  const importance = champ
    ? Object.entries(champ.feature_importance)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 12)
        .map(([feature, gain]) => ({ feature, gain }))
    : [];

  return (
    <Section
      title="Ranking quality"
      description={ev ? `${rows[0]?.n_queries ?? 0} judged queries · ${ev.protocol ?? "5-fold cross-validation"}` : "Not evaluated yet"}
      action={data.mlflow_ui ? <a href={data.mlflow_ui} target="_blank" rel="noreferrer" className="text-sm text-link hover:underline">MLflow</a> : null}
    >
      <div className="grid gap-4 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <DataTable
            rows={rows}
            rowKey={(r) => r.strategy}
            columns={[
              { key: "s", header: "Strategy", render: (r) => <span className="font-medium">{STRATEGY_LABEL[r.strategy] ?? r.strategy}</span> },
              { key: "ndcg", header: "NDCG@10", align: "right", render: (r) => Number(r["ndcg@10"]).toFixed(3) },
              { key: "mrr", header: "MRR", align: "right", render: (r) => Number(r.mrr).toFixed(3) },
              { key: "rec", header: "Recall@50", align: "right", render: (r) => Number(r["recall@50"]).toFixed(3) },
              { key: "lift", header: "Lift vs A (95% CI)", align: "right", render: (r) => {
                  const lift = r["ndcg@10_lift_vs_baseline"] as number | undefined;
                  const ci = r["ndcg@10_lift_ci95"] as number[] | undefined;
                  if (lift == null) return <span className="text-muted">baseline</span>;
                  const sig = ci && (ci[0] > 0 || ci[1] < 0);
                  return (
                    <span className={sig ? (lift > 0 ? "text-good" : "text-critical") : ""}>
                      {lift >= 0 ? "+" : ""}
                      {lift.toFixed(3)} <span className="text-muted">[{ci?.[0].toFixed(3)}, {ci?.[1].toFixed(3)}]</span>
                    </span>
                  );
                } },
            ]}
          />
        </div>
        <Card className="p-4 xl:col-span-2">
          <p className="text-xs text-muted">Feature importance · {champ?.version ?? "no champion"}</p>
          {importance.length ? <Bars data={importance} x="feature" series={[{ key: "gain", name: "Gain share" }]} horizontal height={280} format={(v) => fmt.pct(v)} yFormat={(v) => fmt.pct(v, 0)} /> : <Skeleton className="h-64" />}
        </Card>
      </div>
      <Disclosure summary="Model registry" className="mt-4">
        <DataTable<Model>
          rows={data.models}
          rowKey={(m) => m.version}
          dense
          columns={[
            { key: "v", header: "Version", render: (m) => (
                <span className="flex items-center gap-2 font-mono text-xs">
                  {m.version} {m.is_champion && <Badge tone="good">champion</Badge>}
                </span>
              ) },
            { key: "algo", header: "Algorithm", render: (m) => m.algorithm },
            { key: "val", header: "Val NDCG@10", align: "right", render: (m) => Number(m.metrics["val_ndcg@10"] ?? 0).toFixed(3) },
            { key: "iters", header: "Trees", align: "right", render: (m) => String(m.metrics.best_iteration ?? "") },
            { key: "run", header: "MLflow run", render: (m) => <span className="font-mono text-xs text-muted">{m.mlflow_run_id?.slice(0, 8) ?? "n/a"}</span> },
            { key: "t", header: "Trained", render: (m) => fmt.dateTime(m.trained_at) },
          ]}
        />
      </Disclosure>
    </Section>
  );
}
