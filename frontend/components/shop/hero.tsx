"use client";

import { useUi } from "@/lib/ui-config";
import { HeroSearchAnchor } from "@/lib/search-dock";
import { Chip } from "@/components/ui";
import { SearchBar } from "./search-bar";

const POPULAR = ["modern leather accent chair under 300", "farmhouse dining table", "outdoor patio umbrella", "mid-century nightstand", "boho area rug 8x10", "industrial bar stools"];

/** Home hero; title and subtitle can be changed by a console UI experiment. Its search bar is the storefront's primary
 *  one: when it scrolls out of view the header shows a docked copy. */
export function Hero() {
  const { ui } = useUi();
  return (
    <section className="stagger mx-auto max-w-3xl pt-10 text-center lg:pt-20">
      <h1 className="rise font-serif text-5xl tracking-tight md:text-6xl">{ui.hero_title}</h1>
      <p className="rise mt-4 text-base text-fg-2">{ui.hero_subtitle}</p>
      <div className="rise mx-auto mt-8 max-w-2xl">
        <HeroSearchAnchor>
          <SearchBar size="lg" />
        </HeroSearchAnchor>
      </div>
      <ul className="rise mt-4 flex flex-wrap justify-center gap-2">
        {POPULAR.map((q) => (
          <li key={q}>
            <Chip href={`/search?q=${encodeURIComponent(q)}`}>{q}</Chip>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Optional storefront banner from a UI experiment. */
export function UiBanner() {
  const { ui } = useUi();
  if (!ui.banner) return null;
  return <div className="border-b border-border bg-surface-2 py-2 text-center text-xs text-fg-2">{ui.banner}</div>;
}
