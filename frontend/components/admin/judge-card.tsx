"use client";

import { fmt } from "@/lib/format";
import { useAdmin } from "@/lib/admin";
import { Badge, Card, Skeleton } from "@/components/ui";

type Judge = { backend: string; model: string; evaluation: { backend: string; model: string; n: number; accuracy: number; mae_expected_grade: number; spearman: number; exact_recall: number; confusion: number[][]; grades: string[] } | null };

/** The decision model that judges relevance, scored against WANDS human grades. */
export function JudgeCard() {
  const { data, isLoading } = useAdmin<Judge>("/analytics/decisions");
  if (isLoading) return <Skeleton className="h-48" />;
  if (!data) return null;
  const e = data.evaluation;
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium">Relevance judge vs. human labels</p>
          <p className="text-xs text-muted">Also routes assistant messages and classifies query intent.</p>
        </div>
        <Badge tone={data.backend === "local" ? "neutral" : "info"}>{data.backend === "local" ? "local fallback" : data.model}</Badge>
      </div>
      {e ? (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {[
              ["Accuracy", fmt.pct(e.accuracy)],
              ["MAE (grade)", e.mae_expected_grade.toFixed(3)],
              ["Spearman", e.spearman.toFixed(3)],
              ["Exact recall", fmt.pct(e.exact_recall)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="tnum text-lg font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          <table className="tnum mt-3 w-full text-xs">
            <thead>
              <tr className="text-muted">
                <th className="text-left font-medium">human \ judge</th>
                {e.grades.map((g) => (
                  <th key={g} className="text-right font-medium">
                    {g}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {e.confusion.map((row, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-1">{e.grades[i]}</td>
                  {row.map((v, j) => (
                    <td key={j} className={`py-1 text-right ${i === j ? "font-semibold" : "text-fg-2"}`}>
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-muted">{fmt.num(e.n)} labelled pairs</p>
        </>
      ) : (
        <p className="mt-3 text-sm text-fg-2">Not evaluated yet (make decisions).</p>
      )}
    </Card>
  );
}
