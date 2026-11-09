"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Product } from "./api";
import { useSession } from "./session";
import { ctxFields, track, type TrackContext } from "./tracking";

export type CartLine = { product: Product; quantity: number; source?: string };

type Cart = {
  lines: CartLine[];
  count: number;
  total: number;
  add: (product: Product, source?: string, quantity?: number) => void;
  remove: (id: number) => void;
  setQuantity: (id: number, quantity: number) => void;
  clear: () => void;
};

const Ctx = createContext<Cart>({ lines: [], count: 0, total: 0, add: () => {}, remove: () => {}, setQuantity: () => {}, clear: () => {} });
const KEY = "ss_cart";

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) setLines(JSON.parse(raw));
    } catch {}
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(KEY, JSON.stringify(lines));
    } catch {}
  }, [lines, loaded]);

  const add = useCallback((product: Product, source?: string, quantity = 1) => {
    setLines((prev) => {
      const i = prev.findIndex((l) => l.product.id === product.id);
      if (i >= 0) return prev.map((l, j) => (j === i ? { ...l, quantity: l.quantity + quantity } : l));
      return [...prev, { product, quantity, source }];
    });
  }, []);
  const remove = useCallback((id: number) => setLines((prev) => prev.filter((l) => l.product.id !== id)), []);
  const setQuantity = useCallback(
    (id: number, quantity: number) =>
      setLines((prev) => (quantity <= 0 ? prev.filter((l) => l.product.id !== id) : prev.map((l) => (l.product.id === id ? { ...l, quantity } : l)))),
    [],
  );
  const clear = useCallback(() => setLines([]), []);

  const value = useMemo(
    () => ({
      lines,
      count: lines.reduce((n, l) => n + l.quantity, 0),
      total: lines.reduce((n, l) => n + l.quantity * l.product.price, 0),
      add,
      remove,
      setQuantity,
      clear,
    }),
    [lines, add, remove, setQuantity, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useCart = () => useContext(Ctx);

/** Add to the cart and log the add_to_cart event in one call (cards, product page and the assistant all use it). */
export function useAddToCart() {
  const cart = useCart();
  const { userId, sessionId } = useSession();
  return useCallback(
    (product: Product, ctx: TrackContext, quantity = 1) => {
      cart.add(product, ctx.source, quantity);
      track({ event_type: "add_to_cart", user_id: userId, session_id: sessionId, product_id: product.id, position: product.position ?? null, ...ctxFields(ctx) });
    },
    [cart, userId, sessionId],
  );
}
