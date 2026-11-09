"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { CheckCircle, PaperPlaneRight, ShoppingCart, Sparkle } from "@phosphor-icons/react";
import { api, type AgentAction, type ChatResponse, type Product } from "@/lib/api";
import { useAddToCart, useCart } from "@/lib/cart";
import { fmt } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Badge, Button, Card, Chip, Disclosure, cn } from "@/components/ui";
import { ProductCard } from "@/components/shop/product-card";

type Turn = { role: "user" | "assistant"; content: string; products?: Product[]; preferences?: Record<string, unknown>; response?: ChatResponse };

const STARTERS = ["A gift for someone who loves hiking and cooking, under $100", "Modern walnut nightstand under $200, in stock", "Something to make a small balcony cozy"];

export default function AssistantPage() {
  const { userId, sessionId, ready, persona } = useSession();
  const cart = useCart();
  const addToCart = useAddToCart();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api.get<{ provider: string; model: string | null }>("/agent/status") });

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy || !ready) return;
    const next: Turn[] = [...turns, { role: "user", content: t }];
    setTurns(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<ChatResponse>("/agent/chat", {
        user_id: userId,
        session_id: sessionId,
        // assistant turns carry the ids they displayed, so the agent can refer to them without searching again
        messages: next.map((x) => ({ role: x.role, content: x.content, product_ids: x.products?.map((p) => p.id) ?? [] })),
        // the browser cart, so "check out my cart" works
        cart: cart.lines.map((l) => ({ product_id: l.product.id, quantity: l.quantity })),
      });
      // the cart lives in the browser: apply what the agent did on the shopper's request
      for (const a of res.actions ?? []) {
        if (a.type === "add_to_cart" && a.product) addToCart(a.product, { source: "agent" }, a.quantity ?? 1);
        if (a.type === "order_placed") cart.clear();
      }
      setTurns([...next, { role: "assistant", content: res.message, products: res.products, preferences: res.preferences, response: res }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl tracking-tight">Assistant</h1>
          <p className="mt-1 text-sm text-fg-2">Describe what you need. It searches the store, explains each pick, and can buy for you.</p>
        </div>
        <Badge tone={status.data?.provider === "claude" ? "info" : "neutral"}>{status.data?.provider === "claude" ? "Claude" : "Rule-based"}</Badge>
      </div>

      <div className="mt-8 space-y-4">
        {turns.length === 0 && (
          <div>
            <ul className="flex flex-wrap gap-2">
              {STARTERS.map((s) => (
                <li key={s}>
                  <Chip onClick={() => send(s)}>{s}</Chip>
                </li>
              ))}
            </ul>
            {persona && <p className="mt-3 text-xs text-muted">Shopping as {fmt.title(persona)}: picks are personalized to that history.</p>}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn("rise max-w-[85%]", t.role === "user" ? "rounded-card bg-accent px-4 py-2.5 text-sm text-accent-fg" : "w-full")}>
              {t.role === "user" ? (
                t.content
              ) : (
                <Card className="p-4">
                  <div className="flex items-start gap-2">
                    <Sparkle size={16} weight="fill" className="mt-0.5 shrink-0 text-fg-2" />
                    <p className="text-sm leading-relaxed">{t.content}</p>
                  </div>
                  {t.response?.actions?.map((a, j) => (
                    <ActionLine key={j} action={a} />
                  ))}
                  {t.preferences && Object.values(t.preferences).some((v) => (Array.isArray(v) ? v.length : v)) && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {t.preferences.budget_max != null && <Badge>budget ≤ {fmt.money0(Number(t.preferences.budget_max))}</Badge>}
                      {(["categories", "styles", "materials", "colors"] as const).flatMap((k) =>
                        ((t.preferences?.[k] as string[] | undefined) ?? []).map((v) => (
                          <Badge key={`${k}-${v}`} tone="info">
                            {v}
                          </Badge>
                        )),
                      )}
                    </div>
                  )}
                  {t.products && t.products.length > 0 && (
                    <div className="stagger mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {t.products.map((p) => (
                        <div key={p.id} className="flex flex-col">
                          <ProductCard product={p} compact ctx={{ source: "recs:agent" }} className="h-auto" />
                          {p.explanation?.reason && <p className="mt-1.5 px-1 text-xs leading-snug text-fg-2">{p.explanation.reason}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  {t.response && t.response.trace.length > 0 && (
                    <Disclosure className="mt-3 text-xs" summary={`Trace · ${t.response.trace.length} call${t.response.trace.length > 1 ? "s" : ""} · ${t.response.provider} · ${Math.round(t.response.latency_ms)} ms`}>
                      <ul className="space-y-1 font-mono text-[11px] text-muted">
                        {t.response.decisions?.route && (
                          <li>
                            route → {t.response.decisions.route.route} ({fmt.pct(t.response.decisions.route.p, 0)}, {t.response.decisions.route.source})
                          </li>
                        )}
                        {t.response.trace.map((x, j) => (
                          <li key={j}>
                            {x.tool}({Object.entries(x.input).filter(([, v]) => v !== null && v !== false).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}) → {x.summary}
                          </li>
                        ))}
                      </ul>
                    </Disclosure>
                  )}
                </Card>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <Card className="w-fit px-4 py-2.5 text-sm text-fg-2">
            <span className="inline-flex gap-1">
              <span className="animate-pulse">●</span>
              <span className="animate-pulse [animation-delay:150ms]">●</span>
              <span className="animate-pulse [animation-delay:300ms]">●</span>
            </span>
          </Card>
        )}
        {error && <p className="text-sm text-critical">{error}</p>}
        <div ref={end} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="glass-strong sticky bottom-4 mt-8 flex gap-2 rounded-card p-2"
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="What are you looking for?" aria-label="Message" className="h-10 flex-1 bg-transparent px-2 text-sm outline-none placeholder:text-muted" disabled={busy} />
        <Button type="submit" disabled={busy || !input.trim()} aria-label="Send">
          <PaperPlaneRight size={16} weight="fill" />
        </Button>
      </form>
    </div>
  );
}

function ActionLine({ action: a }: { action: AgentAction }) {
  if (a.type === "order_placed")
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-tile border border-border bg-good-soft px-3 py-2 text-xs text-good">
        <CheckCircle size={14} weight="fill" className="shrink-0" />
        <span>
          Order <span className="font-mono">{a.order_id}</span> placed · {fmt.money(a.total)} · Agentic Commerce Protocol
        </span>
      </div>
    );
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-tile border border-border bg-surface-2 px-3 py-2 text-xs text-fg-2">
      <ShoppingCart size={14} weight="fill" className="shrink-0" />
      <span>
        Added to cart: <span className="capitalize text-fg">{a.product?.name}</span>
        {a.quantity && a.quantity > 1 ? ` × ${a.quantity}` : ""}
      </span>
      <Link href="/cart" className="ml-auto font-medium text-link hover:underline">
        View cart
      </Link>
    </div>
  );
}
