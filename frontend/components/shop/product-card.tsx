"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ShoppingCartSimple, Star } from "@phosphor-icons/react";
import { api, type Product, type ProductDetail, type UiConfig } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useAddToCart } from "@/lib/cart";
import { useSession } from "@/lib/session";
import { ctxFields, track, type TrackContext } from "@/lib/tracking";
import { useUi } from "@/lib/ui-config";
import { Badge, Button, cn } from "@/components/ui";
import { ProductVisual } from "./product-visual";

export type ClickContext = TrackContext;

const CTA_VARIANT = { dark: "primary", glass: "secondary", accent: "accent" } as const;

type Props = { product: Product; ctx: TrackContext; onExplain?: (p: Product) => void; compact?: boolean; priority?: boolean; className?: string; ui?: UiConfig };

/** A product in a grid. `ui` overrides the shopper's UI-experiment config (used by console previews).
 *  Hovering prefetches the product page so the click paints instantly. */
export function ProductCard({ product, ctx, onExplain, compact, priority, className, ui: uiOverride }: Props) {
  const { userId, sessionId } = useSession();
  const exposure = useUi();
  const ui = uiOverride ?? exposure.ui;
  const addToCart = useAddToCart();
  const queryClient = useQueryClient();
  const isRec = ctx.source.startsWith("recs:");
  // a running UI experiment tags clicks and carts with its arm when no ranking test already did
  const tctx: TrackContext = { ...ctx, experiment_key: ctx.experiment_key ?? exposure.experiment_key, variant: ctx.variant ?? exposure.variant };

  const logClick = () =>
    track({ event_type: isRec ? "rec_click" : "click", user_id: userId, session_id: sessionId, product_id: product.id, position: product.position ?? null, ...ctxFields(tctx) });
  const prefetch = () => queryClient.prefetchQuery({ queryKey: ["product", product.id], queryFn: () => api.get<ProductDetail>(`/products/${product.id}`), staleTime: 300_000 });

  return (
    <div className={cn("glass-clear group relative flex h-full flex-col rounded-card p-3 transition-[transform,background-color,box-shadow] duration-300 hover:-translate-y-0.5", compact && "p-2", className)}>
      <Link href={`/product/${product.id}`} onClick={logClick} onMouseEnter={prefetch} onFocus={prefetch} className="block">
        <ProductVisual productClass={product.product_class} name={product.name} imageUrl={product.image_url} priority={priority} />
        {/* fixed two-line title and a reserved badge row keep the price and buttons aligned across a grid row */}
        <p className={cn("mt-3 line-clamp-2 min-h-[2.45rem] text-sm font-medium leading-snug capitalize", compact && "min-h-[2.1rem] text-xs")}>{product.name}</p>
        <p className="mt-1 truncate text-xs text-muted">
          {product.brand}
          {product.product_class ? ` · ${product.product_class}` : ""}
        </p>
      </Link>
      <div className="mt-2 flex items-center justify-between">
        <span className="tnum text-sm font-semibold">{fmt.money(product.price)}</span>
        {ui.show_ratings && product.rating ? (
          <span className="tnum inline-flex items-center gap-1 text-xs text-fg-2">
            <Star size={12} weight="fill" className="text-warning" />
            {product.rating.toFixed(1)}
            <span className="text-muted">({fmt.compact(product.review_count)})</span>
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex min-h-5 flex-wrap gap-1">
        {!product.in_stock && <Badge tone="critical">Out of stock</Badge>}
        {ui.card_badges && product.is_new && <Badge tone="info">New</Badge>}
      </div>
      <div className="mt-auto flex gap-2 pt-3">
        <Button
          size="sm"
          variant={CTA_VARIANT[ui.cta_style]}
          className="flex-1"
          disabled={!product.in_stock}
          onClick={(e) => {
            e.preventDefault();
            addToCart(product, tctx);
          }}
        >
          {ui.cta_icon && <ShoppingCartSimple size={14} weight="bold" />}
          {ui.cta_label}
        </Button>
        {onExplain && product.explanation && (
          <Button size="sm" variant="secondary" onClick={() => onExplain(product)} aria-label="Why this ranking?">
            Why?
          </Button>
        )}
      </div>
    </div>
  );
}
