"use client";

import { QueryClient, type Query } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { SessionProvider } from "@/lib/session";
import { CartProvider } from "@/lib/cart";
import { UiProvider } from "@/lib/ui-config";
import { SearchDockProvider } from "@/lib/search-dock";

/* Catalog data (product pages, global rails) is persisted in localStorage for an hour so a returning visitor paints
   instantly; anything personal (for-you, UI-experiment arm, search) or admin-only stays in memory. */
const PERSISTED = new Set(["product", "rail"]);

function makeClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) => count < 1 && !(error instanceof ApiError && (error.status === 401 || error.status === 404)),
      },
    },
  });
  client.setQueryDefaults(["product"], { staleTime: 300_000, gcTime: 3_600_000 });
  client.setQueryDefaults(["rail"], { staleTime: 300_000, gcTime: 3_600_000 });
  client.setQueryDefaults(["admin"], { staleTime: 60_000 });
  return client;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeClient);
  const [persister] = useState(() =>
    createSyncStoragePersister({ storage: typeof window === "undefined" ? undefined : window.localStorage, key: "ss-q", throttleTime: 1000 }),
  );
  return (
    <PersistQueryClientProvider
      client={client}
      persistOptions={{
        persister,
        maxAge: 3_600_000,
        buster: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA ?? "dev",
        dehydrateOptions: {
          // global rails only: key[2] carries the user id for the personalised rail
          shouldDehydrateQuery: (q: Query) => q.state.status === "success" && PERSISTED.has(String(q.queryKey[0])) && !(q.queryKey[0] === "rail" && q.queryKey[2]),
        },
      }}
    >
      <SessionProvider>
        <CartProvider>
          <UiProvider>
            <SearchDockProvider>{children}</SearchDockProvider>
          </UiProvider>
        </CartProvider>
      </SessionProvider>
    </PersistQueryClientProvider>
  );
}
