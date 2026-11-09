"use client";

import { X } from "@phosphor-icons/react";
import type { Product, SearchResponse } from "@/lib/api";
import { Badge, Button, Rows } from "@/components/ui";
import { fmt } from "@/lib/format";
import { ProductVisual } from "./product-visual";

/** "Why this ranking?" - per-item LightGBM contributions + the explicit personalization term. */
export function ExplainDrawer({ product, response, onClose }: { product: Product | null; response: SearchResponse; onClose: () => void }) {
  if (!product) return null;
  const e = product.explanation!;
  const maxAbs = Math.max(0.01, ...(e.factors ?? []).map((f) => Math.abs(f.contribution)));
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside role="dialog" aria-label="Ranking explanation" onClick={(ev) => ev.stopPropagation()} className="glass-strong h-full w-full max-w-md overflow-y-auto border-y-0 border-r-0 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Why this ranking?</p>
            <h2 className="mt-1 text-lg font-semibold leading-tight capitalize">{product.name}</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </Button>
        </div>
        <div className="mt-4 grid grid-cols-[72px_1fr] gap-3">
          <ProductVisual productClass={product.product_class} name={product.name} imageUrl={product.image_url} size="sm" />
          <Rows
            dense
            items={[
              ["Position", `#${product.position}`],
              ["Price", fmt.money(product.price)],
              ["Candidates", `${response.retrieval.union ?? response.retrieval.bm25 ?? 0}`],
            ]}
          />
        </div>

        {e.note ? (
          <p className="mt-5 rounded-tile bg-surface-2 p-3 text-sm text-fg-2">{e.note}</p>
        ) : (
          <>
            <div className="mt-5 flex flex-wrap gap-1.5">
              {e.retrieved_by?.map((s) => (
                <Badge key={s} tone="info">
                  {s === "bm25" ? `keyword #${e.bm25_rank}` : `semantic #${e.semantic_rank}`}
                </Badge>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-tile border border-border p-3">
                <p className="text-xs text-muted">Ranker score</p>
                <p className="tnum text-xl font-semibold">{e.ltr_score?.toFixed(3) ?? "n/a"}</p>
              </div>
              <div className="rounded-tile border border-border p-3">
                <p className="text-xs text-muted">Personalization</p>
                <p className="tnum text-xl font-semibold">{e.personal_boost == null ? "off" : `${e.personal_boost >= 0 ? "+" : ""}${e.personal_boost.toFixed(3)}`}</p>
              </div>
            </div>
            <h3 className="mt-6 text-sm font-semibold">Top factors</h3>
            <p className="text-xs text-muted">Model contributions. Positive pushes the item up.</p>
            <ul className="mt-3 space-y-2">
              {(e.factors ?? []).map((f) => (
                <li key={f.feature} className="text-xs">
                  <div className="flex justify-between gap-2">
                    <span>{f.label}</span>
                    <span className="tnum text-muted">
                      {formatValue(f.feature, f.value)} · <span className={f.contribution >= 0 ? "text-good" : "text-critical"}>{f.contribution >= 0 ? "+" : ""}{f.contribution.toFixed(3)}</span>
                    </span>
                  </div>
                  <div className="mt-1 flex h-1.5 items-center">
                    <div className="flex h-full w-1/2 justify-end">{f.contribution < 0 && <div className="h-full rounded-l-sm bg-critical" style={{ width: `${(Math.abs(f.contribution) / maxAbs) * 100}%` }} />}</div>
                    <div className="h-full w-px bg-border-strong" />
                    <div className="flex h-full w-1/2">{f.contribution > 0 && <div className="h-full rounded-r-sm bg-good" style={{ width: `${(f.contribution / maxAbs) * 100}%` }} />}</div>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="tnum mt-6 text-[11px] text-muted">
          {response.retrieval.bm25 ?? 0} keyword + {response.retrieval.semantic ?? 0} semantic candidates → {response.retrieval.union ?? response.retrieval.bm25 ?? 0} fused · {response.latency_ms} ms
        </p>
      </aside>
    </div>
  );
}

function formatValue(feature: string, v: number) {
  if (feature === "price") return fmt.money0(v);
  if (feature.endsWith("_rate") || feature.startsWith("ctr") || feature.startsWith("conversion")) return `${(v * 100).toFixed(1)}%`;
  if (feature === "in_stock" || feature === "is_new" || feature === "price_cap_ok") return v ? "yes" : "no";
  return v.toFixed(2);
}
