"use client";

import { createContext, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";

/* The storefront has one primary search bar. On the home page it sits in the hero; once the hero scrolls away (or on
   any other page) the bar docks into the header. `HeroSearchAnchor` reports the hero bar's visibility. */

type Dock = { heroVisible: boolean; setHeroVisible: (v: boolean) => void };
const Ctx = createContext<Dock>({ heroVisible: false, setHeroVisible: () => {} });

export function SearchDockProvider({ children }: { children: React.ReactNode }) {
  const [heroVisible, setHeroVisible] = useState(false);
  const value = useMemo(() => ({ heroVisible, setHeroVisible }), [heroVisible]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useSearchDock = () => useContext(Ctx);

/** Wraps the hero search bar. While it is on screen the header shows no bar; when it leaves, the header bar slides in. */
export function HeroSearchAnchor({ children }: { children: React.ReactNode }) {
  const { setHeroVisible } = useSearchDock();
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    setHeroVisible(true);
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setHeroVisible(e.isIntersecting), { rootMargin: "-56px 0px 0px 0px" });
    io.observe(el);
    return () => {
      io.disconnect();
      setHeroVisible(false);
    };
  }, [setHeroVisible]);
  return <div ref={ref}>{children}</div>;
}
