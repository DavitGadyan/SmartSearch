"use client";

import Link from "next/link";
import { useState } from "react";
import { Trash } from "@phosphor-icons/react";
import { acp, type AcpAddress, type AcpSession } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useCart } from "@/lib/cart";
import { Button, Card, Empty, Input, Label, Rows } from "@/components/ui";
import { ProductVisual } from "@/components/shop/product-visual";

const START_ADDRESS: AcpAddress = { name: "", line_one: "1 Market Street", city: "San Francisco", state: "CA", country: "US", postal_code: "94105" };
const cents = (v: number) => fmt.money(v / 100);

/** Checkout runs through the store's own Agentic Commerce Protocol endpoints: create a session, pick shipping,
 *  obtain a delegated payment token from the mock PSP, complete. The same flow an AI agent uses. */
export default function CartPage() {
  const cart = useCart();
  const [session, setSession] = useState<AcpSession | null>(null);
  const [address, setAddress] = useState<AcpAddress>(START_ADDRESS);
  const [option, setOption] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const start = () =>
    run(async () => {
      // the session is priced before the shopper types a name; the real name goes in with the order
      const s = await acp.create(
        cart.lines.map((l) => ({ id: String(l.product.id), quantity: l.quantity })),
        { ...address, name: address.name.trim() || "Guest" },
      );
      setSession(await acp.update(s.id, { fulfillment_option_id: option }));
    });
  const place = () =>
    run(async () => {
      if (!session) return;
      const s = await acp.update(session.id, { fulfillment_address: address, fulfillment_option_id: option });
      if (s.status !== "ready_for_payment") {
        setSession(s);
        setError(s.messages.find((m) => m.type === "error")?.content ?? "Session is not ready for payment");
        return;
      }
      const total = s.totals.find((t) => t.type === "total")!.amount;
      const token = await acp.delegatePayment(s.id, total, address.name);
      const done = await acp.complete(s.id, token.id);
      setSession(done);
      cart.clear();
    });

  if (session?.status === "completed")
    return (
      <Card className="mx-auto max-w-lg p-8 text-center">
        <p className="text-xs uppercase tracking-wide text-muted">Order placed</p>
        <h1 className="mt-2 font-serif text-3xl tracking-tight">Thank you</h1>
        <p className="mt-3 text-sm text-fg-2">
          Order <span className="font-mono">{session.order?.id}</span> · <span className="tnum">{cents(session.totals.find((t) => t.type === "total")!.amount)}</span>
        </p>
        <p className="mt-1 text-xs text-muted">Completed through the Agentic Commerce Protocol.</p>
        <Link href="/" className="mt-6 inline-flex h-10 items-center rounded-control bg-accent px-4 text-sm font-medium text-accent-fg hover:bg-fg-2">
          Continue shopping
        </Link>
      </Card>
    );

  if (cart.lines.length === 0) return <Empty title="Your cart is empty" />;

  const field = (k: keyof AcpAddress, label: string) => (
    <div className="grid gap-1">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} value={address[k] ?? ""} placeholder={k === "name" ? "Full name" : undefined} onChange={(e) => setAddress({ ...address, [k]: e.target.value })} className="h-9 text-sm" />
    </div>
  );

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <ul className="glass divide-y divide-border-strong/20 rounded-card">
        {cart.lines.map((l) => (
          <li key={l.product.id} className="flex items-center gap-4 p-4">
            <div className="w-16 shrink-0">
              <ProductVisual productClass={l.product.product_class} name={l.product.name} imageUrl={l.product.image_url} size="sm" />
            </div>
            <div className="min-w-0 flex-1">
              <Link href={`/product/${l.product.id}`} className="line-clamp-1 text-sm font-medium capitalize hover:underline">
                {l.product.name}
              </Link>
              <p className="text-xs text-muted">
                {l.product.brand} · {fmt.money(l.product.price)}
              </p>
            </div>
            <input type="number" min={1} value={l.quantity} onChange={(e) => cart.setQuantity(l.product.id, Number(e.target.value))} className="tnum h-9 w-16 rounded-control border border-border-strong bg-surface px-2 text-sm" aria-label="Quantity" />
            <span className="tnum w-24 text-right text-sm font-semibold">{fmt.money(l.product.price * l.quantity)}</span>
            <Button variant="ghost" size="sm" onClick={() => cart.remove(l.product.id)} aria-label="Remove">
              <Trash size={16} />
            </Button>
          </li>
        ))}
      </ul>

      <Card className="h-fit p-5">
        {!session ? (
          <>
            <h2 className="font-semibold">Summary</h2>
            <Rows
              className="mt-3"
              items={[
                ["Items", cart.count],
                ["Subtotal", fmt.money(cart.total)],
              ]}
            />
            <p className="mt-2 text-xs text-muted">Shipping and tax are added at checkout.</p>
            <Button className="mt-5 w-full" size="lg" onClick={start} disabled={busy}>
              {busy ? "Preparing…" : "Checkout"}
            </Button>
          </>
        ) : (
          <>
            <h2 className="font-semibold">Checkout</h2>
            <div className="mt-3 grid gap-3">
              {field("name", "Name")}
              {field("line_one", "Address")}
              <div className="grid grid-cols-[1fr_72px_96px] gap-2">
                {field("city", "City")}
                {field("state", "State")}
                {field("postal_code", "Postal code")}
              </div>
            </div>
            <fieldset className="mt-4">
              <legend className="text-xs font-medium text-fg-2">Shipping</legend>
              <div className="mt-1.5 grid gap-1.5">
                {session.fulfillment_options.map((o) => (
                  <label key={o.id} className="flex cursor-pointer items-center justify-between gap-2 rounded-tile border border-border px-3 py-2 text-sm has-[:checked]:border-fg">
                    <span className="flex items-center gap-2">
                      <input type="radio" name="shipping" value={o.id} checked={option === o.id} onChange={() => setOption(o.id)} className="accent-[var(--fg)]" />
                      {o.title}
                    </span>
                    <span className="tnum text-fg-2">{o.total === 0 ? "Free" : cents(o.total)}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <Rows className="mt-4" items={session.totals.filter((t) => t.type !== "items_base_amount").map((t) => [t.display_text, cents(t.type === "fulfillment" ? (session.fulfillment_options.find((o) => o.id === option)?.total ?? t.amount) : t.amount)])} />
            <p className="mt-2 text-xs text-muted">Test card 4242 · payment tokens are issued by a mock provider.</p>
            {error && <p className="mt-2 text-xs text-critical">{error}</p>}
            <Button className="mt-4 w-full" size="lg" onClick={place} disabled={busy || !address.name.trim()}>
              {busy ? "Placing order…" : "Place order"}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
