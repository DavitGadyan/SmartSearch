"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Code, Flask, Gauge, MagnifyingGlass, SignOut, Storefront, UsersThree } from "@phosphor-icons/react";
import { cn } from "@/components/ui";

const ITEMS = [
  { href: "/admin", label: "Overview", icon: Gauge },
  { href: "/admin/experiments", label: "Experiments", icon: Flask },
  { href: "/admin/search", label: "Search & ranking", icon: MagnifyingGlass },
  { href: "/admin/shoppers", label: "Shoppers & recommendations", icon: UsersThree },
];
const API_DOCS = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/docs`;
const ITEM = "flex items-center gap-2.5 rounded-control px-2.5 py-2 text-sm text-fg-2 transition-colors hover:bg-white/50 hover:text-fg";

const isActive = (path: string, href: string) => (href === "/admin" ? path === href : path.startsWith(href));

function useSignOut() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return async () => {
    await fetch("/api/admin/logout", { method: "POST" });
    queryClient.removeQueries({ queryKey: ["admin"] });
    router.replace("/admin/login");
    router.refresh();
  };
}

export function AdminNav() {
  const path = usePathname();
  const signOut = useSignOut();
  return (
    <nav className="flex h-full flex-col">
      <Link href="/admin" className="px-4 py-5 font-serif text-xl tracking-tight">
        SmartSearch <span className="font-sans text-sm text-muted">Console</span>
      </Link>
      <ul className="stagger space-y-0.5 px-2">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(path, href);
          return (
            <li key={href} className="rise">
              <Link href={href} className={cn(ITEM, active && "bg-white/70 font-medium text-fg")}>
                <Icon size={17} weight={active ? "fill" : "regular"} /> {label}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto space-y-0.5 border-t border-border p-2">
        <Link href="/" className={ITEM}>
          <Storefront size={17} /> Storefront
        </Link>
        <a href={API_DOCS} target="_blank" rel="noreferrer" className={ITEM}>
          <Code size={17} /> API docs
        </a>
        <button type="button" onClick={signOut} className={cn(ITEM, "w-full")}>
          <SignOut size={17} /> Sign out
        </button>
      </div>
    </nav>
  );
}

/** Small screens: wordmark + a scrolling tab strip instead of the sidebar. */
export function AdminTopBar() {
  const path = usePathname();
  const signOut = useSignOut();
  return (
    <div className="glass-strong sticky top-0 z-20 border-x-0 border-t-0 lg:hidden">
      <div className="flex items-center gap-3 px-4 py-2">
        <Link href="/admin" className="shrink-0 font-serif text-lg tracking-tight" aria-label="Console home">
          SmartSearch
        </Link>
        <nav className="flex gap-1 overflow-x-auto" aria-label="Console">
          {ITEMS.map(({ href, label }) => (
            <Link key={href} href={href} className={cn("whitespace-nowrap rounded-control px-2.5 py-1.5 text-xs", isActive(path, href) ? "bg-white/70 font-medium text-fg" : "text-fg-2")}>
              {label}
            </Link>
          ))}
          <Link href="/" className="whitespace-nowrap rounded-control px-2.5 py-1.5 text-xs text-fg-2">
            Storefront
          </Link>
          <button type="button" onClick={signOut} className="whitespace-nowrap rounded-control px-2.5 py-1.5 text-xs text-fg-2">
            Sign out
          </button>
        </nav>
      </div>
    </div>
  );
}
