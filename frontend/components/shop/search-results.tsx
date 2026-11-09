"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, type Product, type SearchResponse } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Reveal } from "@/components/motion";
import { Button, Empty, ErrorBox, Skeleton } from "@/components/ui";
import { ProductCard } from "./product-card";
import { Facets, type ActiveFilters } from "./facets";
import { ExplainDrawer } from "./explain-drawer";

const FILTER_KEYS = ["product_class", "brand", "style", "material", "color", "price", "in_stock"] as const;

export function SearchResults() {
  const router = useRouter();
  const sp = useSearchParams();
  const { userId, sessionId, ready } = useSession();
  const q = sp.get("q") ?? "";
  const page = Number(sp.get("page") ?? 1);
  const strategy = sp.get("strategy") ?? ""; // kept for console deep links; no UI on the storefront
  const [explain, setExplain] = useState<Product | null>(null);

  const active = useMemo<ActiveFilters>(() => Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.getAll(k)])), [sp]);
  const priceBounds = useMemo(() => {
    const b = active.price?.[0];
    if (!b) return {};
    const [lo, hi] = b.split("-");
    return { price_min: Number(lo), price_max: hi ? Number(hi) : undefined };
  }, [active.price]);

  const params = {
    q,
    user_id: userId,
    session_id: sessionId,
    page,
    page_size: 24,
    explain: true,
    strategy: strategy || undefined,
    product_class: active.product_class,
    brand: active.brand,
    style: active.style,
    material: active.material,
    color: active.color,
    in_stock: active.in_stock?.length ? true : undefined,
    ...priceBounds,
  };
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["search", params],
    queryFn: () => api.get<SearchResponse>("/search", params),
    enabled: ready && q.trim().length > 0,
    placeholderData: keepPreviousData,
  });

  const update = useCallback(
    (mutate: (u: URLSearchParams) => void) => {
      const u = new URLSearchParams(sp.toString());
      mutate(u);
      router.push(`/search?${u.toString()}`);
    },
    [router, sp],
  );
  const toggle = (name: string, value: string) =>
    update((u) => {
      const vals = u.getAll(name);
      u.delete(name);
      const next = name === "price" ? (vals.includes(value) ? [] : [value]) : vals.includes(value) ? vals.filter((v) => v !== value) : [...vals, value];
      next.forEach((v) => u.append(name, v));
      u.delete("page");
    });

  if (!q) return <Empty title="Search the catalog" hint="Try “farmhouse dining table”." />;
  if (error) return <ErrorBox error={error} />;

  const ctx = data ? { query: q, experiment_key: data.experiment_key, variant: data.variant, ranking_model_version: data.ranking_model_version, strategy: data.strategy, source: "search" } : { query: q, source: "search" };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
      <div className="hidden lg:block">{data ? <Facets facets={data.facets} active={active} onToggle={toggle} onClear={() => router.push(`/search?q=${encodeURIComponent(q)}`)} /> : <Skeleton className="h-96" />}</div>
      <div>
        <h1 className="font-serif text-2xl tracking-tight">
          {data ? <span className="tnum">{data.total.toLocaleString()}</span> : "…"} results for “{q}”
        </h1>
        {isLoading ? (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[3/4.4]" />
            ))}
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="mt-6">
            <Empty title="No results" hint="Try fewer words." />
          </div>
        ) : (
          <div className={`mt-6 grid grid-cols-2 gap-3 transition-opacity sm:grid-cols-3 xl:grid-cols-4 ${isFetching ? "opacity-60" : ""}`}>{data?.items.map((p, i) => (
            <Reveal key={p.id} index={i} className="min-w-0">
              <ProductCard product={p} ctx={ctx} onExplain={setExplain} priority={i < 4} />
            </Reveal>
          ))}</div>
        )}

        {data && pages > 1 && (
          <nav className="mt-8 flex items-center justify-center gap-2" aria-label="Pagination">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => update((u) => u.set("page", String(page - 1)))}>
              Previous
            </Button>
            <span className="tnum text-sm text-fg-2">
              Page {page} of {pages}
            </span>
            <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => update((u) => u.set("page", String(page + 1)))}>
              Next
            </Button>
          </nav>
        )}
      </div>
      {data && <ExplainDrawer product={explain} response={data} onClose={() => setExplain(null)} />}
    </div>
  );
}
