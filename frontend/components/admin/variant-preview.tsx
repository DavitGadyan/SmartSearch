"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Experiment, type SearchResponse } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useSession } from "@/lib/session";
import { ProductVisual } from "@/components/shop/product-visual";
import { Badge, Skeleton } from "@/components/ui";

type Variant = Experiment["variants"][number];

/** The same query ranked the way this variant ranks it: what the shopper in this arm actually saw. */
export function VariantPreview({ variant, query, n = 4 }: { variant: Variant; query: string; n?: number }) {
  const { userId, sessionId, ready } = useSession();
  const { data, isLoading } = useQuery({
    queryKey: ["variant-preview", variant.key, variant.strategy, variant.explore, query, userId],
    queryFn: () =>
      api.get<SearchResponse>("/search", {
        q: query,
        user_id: userId,
        session_id: sessionId,
        strategy: variant.strategy ?? "hybrid_ltr_personalized",
        explore: variant.explore ?? false,
        page_size: n,
        log: false,
        explain: true,
      }),
    enabled: ready && !!query,
  });
  if (isLoading || !data) return <Skeleton className="h-28" />;
  return (
    <ol className="grid grid-cols-4 gap-2">
      {data.items.slice(0, n).map((p, i) => (
        <li key={p.id} className="min-w-0">
          <ProductVisual productClass={p.product_class} name={p.name} imageUrl={p.image_url} size="sm" />
          <p className="mt-1 truncate text-[11px] capitalize" title={p.name}>
            <span className="text-muted">{i + 1}.</span> {p.name}
          </p>
          <p className="tnum text-[11px] text-muted">
            {fmt.money(p.price)}
            {p.explanation?.explored && (
              <Badge tone="warning" className="ml-1">
                slot
              </Badge>
            )}
          </p>
        </li>
      ))}
    </ol>
  );
}
