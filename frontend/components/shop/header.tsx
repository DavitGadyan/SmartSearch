"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Brain, Gauge, ShoppingCart } from "@phosphor-icons/react";
import { useCart } from "@/lib/cart";
import { useSearchDock } from "@/lib/search-dock";
import { cn } from "@/components/ui";
import { SearchBar } from "./search-bar";
import { PersonaSwitcher } from "./persona-switcher";

const ICON_LINK = "relative inline-flex size-9 items-center justify-center rounded-control text-fg-2 transition-colors hover:bg-white/60 hover:text-fg";

function HeaderSearch() {
  const q = useSearchParams().get("q") ?? "";
  return <SearchBar initial={q} />;
}

/** Top bar. The search bar lives in the home hero; it docks here once the hero scrolls away and on every other page. */
export function ShopHeader() {
  const cart = useCart();
  const path = usePathname();
  const { heroVisible } = useSearchDock();
  const docked = !heroVisible;
  const active = (href: string) => path === href || path.startsWith(`${href}/`);
  return (
    <header className="glass-strong sticky top-0 z-20 border-x-0 border-t-0">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4 lg:px-6">
        <Link href="/" className="shrink-0 font-serif text-lg tracking-tight text-fg sm:text-xl">
          SmartSearch
        </Link>
        <div
          className={cn("hidden min-w-0 flex-1 transition-[opacity,transform] duration-300 ease-out md:block", docked ? "translate-y-0 opacity-100" : "pointer-events-none -translate-y-1.5 opacity-0")}
          aria-hidden={!docked}
          inert={!docked}
        >
          <Suspense fallback={null}>
            <HeaderSearch />
          </Suspense>
        </div>
        <nav className="ml-auto flex items-center gap-1" aria-label="Primary">
          <PersonaSwitcher />
          <Link href="/assistant" className={cn(ICON_LINK, active("/assistant") && "bg-white/70 text-fg")} aria-label="Shopping assistant" title="Assistant">
            <Brain size={20} weight={active("/assistant") ? "fill" : "regular"} />
          </Link>
          <Link href="/admin" className={cn(ICON_LINK, "hidden sm:inline-flex")} aria-label="Merchant console" title="Console">
            <Gauge size={20} />
          </Link>
          <Link href="/cart" className={cn(ICON_LINK, active("/cart") && "bg-white/70 text-fg")} aria-label={`Cart, ${cart.count} items`} title="Cart">
            <ShoppingCart size={20} weight={active("/cart") ? "fill" : "regular"} />
            {cart.count > 0 && (
              <span className="tnum absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-accent px-1 text-center text-[10px] font-semibold leading-4 text-accent-fg">{cart.count}</span>
            )}
          </Link>
        </nav>
      </div>
      <div className={cn("grid transition-[grid-template-rows,opacity] duration-300 ease-out md:hidden", docked ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")} aria-hidden={!docked} inert={!docked}>
        <div className="overflow-hidden px-4">
          <div className="pb-3">
            <Suspense fallback={null}>
              <HeaderSearch />
            </Suspense>
          </div>
        </div>
      </div>
    </header>
  );
}
