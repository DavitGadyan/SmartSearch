"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Product } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Reveal } from "@/components/motion";
import { Skeleton } from "@/components/ui";
import { ProductCard } from "./product-card";

type RailProps = { title: string; endpoint: string; rail: string; needsUser?: boolean; hideOnFallback?: boolean; eager?: boolean };

/** A recommendation rail; every render logs rec_impression server-side, every click logs rec_click.
 *  `eager` marks a rail that is above the fold, so its photos load with priority. */
export function Rail({ title, endpoint, rail, needsUser, hideOnFallback, eager }: RailProps) {
  const { userId, sessionId, ready } = useSession();
  const { data, isLoading } = useQuery({
    queryKey: ["rail", endpoint, needsUser ? userId : null],
    queryFn: () => api.get<Product[] | { items: Product[]; meta: Record<string, unknown> }>(endpoint, { user_id: userId, session_id: sessionId }),
    enabled: ready && (!needsUser || !!userId),
    staleTime: needsUser ? 60_000 : undefined,
  });
  const items = Array.isArray(data) ? data : (data?.items ?? []);
  const meta = !Array.isArray(data) ? data?.meta : undefined;
  if (!isLoading && (items.length === 0 || (hideOnFallback && meta?.strategy === "popularity_fallback"))) return null;
  return (
    <Reveal as="section" className="mt-14">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {meta?.strategy ? <span className="font-mono text-[11px] text-muted">{String(meta.strategy)}</span> : null}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-[3/4]" />)
          : items.slice(0, 6).map((p, i) => (
              <Reveal key={p.id} index={i} className="min-w-0">
                <ProductCard product={{ ...p, position: i + 1 }} compact priority={eager} ctx={{ source: `recs:${rail}` }} />
              </Reveal>
            ))}
      </div>
    </Reveal>
  );
}
