"use client";

import { createContext, useContext, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DEFAULT_UI, type UiConfig, type UiExposure } from "./api";
import { useSession } from "./session";

/** The storefront knobs a console-created UI experiment can change, resolved for this shopper. */
export type UiState = { ui: UiConfig; experiment_key: string | null; variant: string | null };

const Ctx = createContext<UiState>({ ui: DEFAULT_UI, experiment_key: null, variant: null });

export function UiProvider({ children }: { children: React.ReactNode }) {
  const { userId, sessionId, ready } = useSession();
  const { data } = useQuery({
    queryKey: ["ui-exposure", userId],
    queryFn: () => api.post<UiExposure>("/experiments/expose", { user_id: userId, session_id: sessionId, surface: "ui" }),
    enabled: ready && !!userId,
    staleTime: 5 * 60_000,
  });
  const value = useMemo<UiState>(() => {
    // an arm may leave a text field blank; blank means "unchanged"
    const given = Object.fromEntries(Object.entries(data?.ui ?? {}).filter(([, v]) => v !== "" && v !== undefined));
    return { ui: { ...DEFAULT_UI, ...given }, experiment_key: data?.experiment_key ?? null, variant: data?.variant ?? null };
  }, [data]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useUi = () => useContext(Ctx);
