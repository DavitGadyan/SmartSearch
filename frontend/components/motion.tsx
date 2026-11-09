"use client";

import { createElement, useEffect, useRef, useState, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";

/* Motion system. Three primitives, all transform/opacity only, all off under prefers-reduced-motion:
   - `Reveal`: a block fades up the first time it scrolls into view (optional stagger `index`);
   - `CountUp`: a number fills from its previous value to the new one once visible;
   - CSS in globals.css: `.rise` (fade up on mount), `.stagger > *` (nth-child delays), `.page-in` (route change). */

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let observer: IntersectionObserver | null = null;
const callbacks = new WeakMap<Element, () => void>();

function observe(el: Element, cb: () => void) {
  observer ??= new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        callbacks.get(e.target)?.();
        observer?.unobserve(e.target);
      }
    },
    { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
  );
  callbacks.set(el, cb);
  observer.observe(el);
  return () => {
    callbacks.delete(el);
    observer?.unobserve(el);
  };
}

/** True once the element has been on screen (sticky: never flips back). */
export function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return;
    if (reducedMotion()) {
      setInView(true);
      return;
    }
    return observe(el, () => setInView(true));
  }, [inView]);
  return [ref, inView] as const;
}

type RevealProps = HTMLAttributes<HTMLElement> & { as?: "div" | "section" | "li" | "article"; index?: number; children?: ReactNode };

/** Fades its content up when it first enters the viewport. `index` staggers siblings (60 ms steps, capped). */
export function Reveal({ as = "div", index = 0, className, style, children, ...rest }: RevealProps) {
  const [ref, inView] = useInView<HTMLElement>();
  return createElement(
    as,
    { ref, className: cx("reveal", inView && "in", className), style: { ...style, "--i": Math.min(index, 11) } as CSSProperties, ...rest },
    children,
  );
}

/** Animates a number from the previous value to `value` once visible; integers stay integers while moving. */
export function CountUp({ value, format = (n) => String(Math.round(n)), duration = 900, className }: { value: number; format?: (n: number) => string; duration?: number; className?: string }) {
  const [ref, inView] = useInView<HTMLSpanElement>();
  const [shown, setShown] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    if (!inView) return;
    if (!Number.isFinite(value) || reducedMotion()) {
      from.current = value;
      setShown(value);
      return;
    }
    const a = from.current;
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(a + (value - a) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, inView, duration]);

  const v = Number.isInteger(value) ? Math.round(shown) : shown;
  return (
    <span ref={ref} className={className}>
      {format(inView ? v : 0)}
    </span>
  );
}
