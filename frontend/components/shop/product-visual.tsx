"use client";

import { useState } from "react";
import Image from "next/image";
import { Armchair, Bathtub, Bed, Couch, Desk, Lamp, Package, Plant, Rug, Sun, Table } from "@phosphor-icons/react/dist/ssr";
import { classHue } from "@/lib/format";
import { cn } from "@/components/ui";

const ICONS: [RegExp, React.ElementType][] = [
  [/bed|headboard|mattress/i, Bed],
  [/sofa|loveseat|sectional|couch|futon/i, Couch],
  [/chair|stool|bench|ottoman|seat/i, Armchair],
  [/table|desk|console|nightstand|dresser|cabinet|bookcase|shelf|shelving|stand/i, Table],
  [/desk/i, Desk],
  [/lamp|light|chandelier|sconce|pendant|lighting/i, Lamp],
  [/rug|carpet|mat\b|runner/i, Rug],
  [/bath|shower|towel|vanity|faucet|sink/i, Bathtub],
  [/plant|planter|garden|outdoor|patio|umbrella/i, Plant],
  [/mirror|wall art|canvas|frame|decor|pillow|throw|vase|clock/i, Sun],
];

const SIZES = { sm: "80px", md: "(min-width: 1024px) 200px, 45vw", lg: "(min-width: 1024px) 480px, 100vw" };

/** Where a product image came from: a generated visualization, a representative catalog photo, or none. */
export function photoSource(url: string | null | undefined): "generated" | "photo" | null {
  if (!url) return null;
  return url.startsWith("/img/photos/") ? "photo" : "generated";
}

type Props = { productClass: string | null; name: string; imageUrl?: string | null; className?: string; size?: "sm" | "md" | "lg"; priority?: boolean };

/** Product image when one exists (generated or representative photo), otherwise a deterministic category tile.
 *  Representative photos are 256 px: on the product page they sit on a blurred copy of themselves instead of being
 *  stretched. `priority` is for above-the-fold cards. */
export function ProductVisual({ productClass, name, imageUrl, className, size = "md", priority }: Props) {
  const [broken, setBroken] = useState(false);
  const shell = cn("relative aspect-square w-full overflow-hidden rounded-tile", className);
  if (imageUrl && !broken) {
    if (size === "lg" && photoSource(imageUrl) === "photo") {
      return (
        <div className={cn(shell, "bg-white/40")}>
          <Image src={imageUrl} alt="" aria-hidden fill sizes="16px" className="scale-125 object-cover opacity-60 blur-2xl" />
          <Image src={imageUrl} alt={name} fill sizes="(min-width: 1024px) 384px, 90vw" className="object-contain p-8" priority={priority} onError={() => setBroken(true)} />
        </div>
      );
    }
    return (
      <div className={cn(shell, "bg-white/30")}>
        <Image src={imageUrl} alt={name} fill sizes={SIZES[size]} className="object-cover" priority={priority} unoptimized={/^https?:/.test(imageUrl)} onError={() => setBroken(true)} />
      </div>
    );
  }
  const key = `${productClass ?? ""} ${name}`;
  const Icon = ICONS.find(([re]) => re.test(key))?.[1] ?? Package;
  const hue = classHue(productClass ?? name);
  const px = { sm: 20, md: 40, lg: 72 }[size];
  return (
    <div
      aria-hidden
      className={cn(shell, "flex items-center justify-center")}
      style={{
        background: `linear-gradient(135deg, oklch(0.94 0.035 ${hue}) 0%, oklch(0.86 0.06 ${hue}) 100%)`,
        color: `oklch(0.42 0.1 ${hue})`,
      }}
    >
      <Icon size={px} weight="duotone" />
    </div>
  );
}
