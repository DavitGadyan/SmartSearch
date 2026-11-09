"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Product, type UiConfig } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ProductCard } from "@/components/shop/product-card";
import { Skeleton } from "@/components/ui";

/** What shoppers in an arm see: the hero copy and a real product card rendered with that arm's config. */
export function UiPreview({ ui, products }: { ui: UiConfig; products?: Product[] }) {
  const { userId, sessionId, ready } = useSession();
  const { data } = useQuery({
    queryKey: ["ui-preview-products"],
    queryFn: () => api.get<Product[]>("/recommendations/trending", { user_id: userId, session_id: sessionId }),
    enabled: ready && !products,
    staleTime: 10 * 60_000,
  });
  const items = (products ?? data ?? []).slice(0, 2);
  return (
    <div className="rounded-card border border-border bg-bg/70 p-3">
      {ui.banner && <div className="mb-3 rounded-tile bg-surface-2 py-1.5 text-center text-[11px] text-fg-2">{ui.banner}</div>}
      <p className="font-serif text-lg leading-tight tracking-tight">{ui.hero_title}</p>
      <p className="mt-1 text-xs text-fg-2">{ui.hero_subtitle}</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {items.length ? items.map((p) => <ProductCard key={p.id} product={p} compact ui={ui} ctx={{ source: "recs:preview" }} className="pointer-events-none" />) : [0, 1].map((i) => <Skeleton key={i} className="aspect-[3/4.4]" />)}
      </div>
    </div>
  );
}
