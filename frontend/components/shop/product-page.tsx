"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Star } from "@phosphor-icons/react";
import { api, type ProductDetail } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useAddToCart } from "@/lib/cart";
import { useSession } from "@/lib/session";
import { useUi } from "@/lib/ui-config";
import { track } from "@/lib/tracking";
import { Badge, Button, ErrorBox, Skeleton } from "@/components/ui";
import { photoSource, ProductVisual } from "./product-visual";
import { Rail } from "./rail";

const SHOWN_ATTRS = ["style", "material", "color", "shape", "pattern", "wood_tone", "width_in", "height_in", "depth_in", "weight_capacity_lb", "country_of_origin"];
const attrLabel = (k: string) => fmt.title(k).replace(/ In$/, " (in)").replace(/ Lb$/, " (lb)");

export function ProductPage({ id }: { id: number }) {
  const { userId, sessionId, ready } = useSession();
  const addToCart = useAddToCart();
  const { ui, experiment_key, variant } = useUi();
  const { data, isLoading, error } = useQuery({ queryKey: ["product", id], queryFn: () => api.get<ProductDetail>(`/products/${id}`) });

  useEffect(() => {
    if (ready && data) track({ event_type: "product_view", user_id: userId, session_id: sessionId, product_id: id, source: "direct" });
  }, [ready, data, id, userId, sessionId]);

  if (error) return <ErrorBox error={error} />;
  if (isLoading || !data) return <Skeleton className="h-[480px]" />;
  const attrs = SHOWN_ATTRS.filter((k) => data.attributes[k] != null);

  return (
    <>
      <nav className="text-xs text-muted">{data.category_hierarchy?.split("/").map((s) => s.trim()).join(" › ")}</nav>
      <div className="mt-4 grid gap-10 lg:grid-cols-12">
        <div className="rise lg:col-span-5">
          <ProductVisual productClass={data.product_class} name={data.name} imageUrl={data.image_url} size="lg" className="rounded-card" priority />
          {photoSource(data.image_url) === "photo" && <p className="mt-2 text-[11px] text-muted">Representative photo · Amazon Berkeley Objects</p>}
          {photoSource(data.image_url) === "generated" && <p className="mt-2 text-[11px] text-muted">Generated visualization</p>}
        </div>
        <div className="rise lg:col-span-7 [animation-delay:120ms]">
          <p className="text-sm text-muted">{data.brand}</p>
          <h1 className="mt-1 font-serif text-3xl tracking-tight capitalize md:text-4xl">{data.name}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="tnum text-2xl font-semibold">{fmt.money(data.price)}</span>
            {data.rating ? (
              <span className="tnum inline-flex items-center gap-1 text-sm text-fg-2">
                <Star size={14} weight="fill" className="text-warning" /> {data.rating.toFixed(1)} <span className="text-muted">({fmt.num(data.review_count)})</span>
              </span>
            ) : null}
            {data.in_stock ? <Badge tone="good">In stock</Badge> : <Badge tone="critical">Out of stock</Badge>}
            {data.is_new && <Badge tone="info">New</Badge>}
          </div>
          <div className="mt-6">
            <Button size="lg" variant={{ dark: "primary", glass: "secondary", accent: "accent" }[ui.cta_style] as "primary" | "secondary" | "accent"} disabled={!data.in_stock} onClick={() => addToCart(data, { source: "pdp", experiment_key, variant })}>
              {ui.cta_label}
            </Button>
          </div>
          {attrs.length > 0 && (
            <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
              {attrs.map((k) => (
                <div key={k}>
                  <dt className="text-xs text-muted">{attrLabel(k)}</dt>
                  <dd className="mt-0.5 capitalize">{String(data.attributes[k])}</dd>
                </div>
              ))}
            </dl>
          )}
          {data.description && <p className="mt-8 max-w-[70ch] text-sm leading-relaxed text-fg-2">{data.description.slice(0, 700)}</p>}
        </div>
      </div>
      <Rail title="Goes with it" endpoint={`/recommendations/goes-with/${id}`} rail="goes_with" />
      <Rail title="Similar items" endpoint={`/recommendations/similar/${id}`} rail="similar" />
      <Rail title="Bought together" endpoint={`/recommendations/bought-together/${id}`} rail="bought_together" />
    </>
  );
}
