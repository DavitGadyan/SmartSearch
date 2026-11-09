"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const UID_KEY = "ss_uid";
const SID_KEY = "ss_sid";
const SID_TS_KEY = "ss_sid_ts";
const PERSONA_KEY = "ss_persona";
const SESSION_TTL_MS = 30 * 60 * 1000;

function rand(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
}

function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLocal(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {}
}

export type ShopSession = {
  userId: string;
  sessionId: string;
  /** when the visitor is "shopping as" another persona, its label */
  persona: string | null;
  ready: boolean;
  shopAs: (userId: string | null, persona: string | null) => void;
};

const Ctx = createContext<ShopSession>({ userId: "", sessionId: "", persona: null, ready: false, shopAs: () => {} });

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [persona, setPersona] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const uid = readLocal(UID_KEY) ?? rand("web");
    writeLocal(UID_KEY, uid);
    const ts = Number(readLocal(SID_TS_KEY) ?? 0);
    let sid = readLocal(SID_KEY);
    if (!sid || Date.now() - ts > SESSION_TTL_MS) sid = rand("s");
    writeLocal(SID_KEY, sid);
    writeLocal(SID_TS_KEY, String(Date.now()));
    setUserId(uid);
    setSessionId(sid);
    setPersona(readLocal(PERSONA_KEY));
    setReady(true);
    const touch = () => writeLocal(SID_TS_KEY, String(Date.now()));
    window.addEventListener("click", touch, { passive: true });
    return () => window.removeEventListener("click", touch);
  }, []);

  const shopAs = useCallback((uid: string | null, p: string | null) => {
    const next = uid ?? rand("web");
    writeLocal(UID_KEY, next);
    writeLocal(PERSONA_KEY, p);
    const sid = rand("s");
    writeLocal(SID_KEY, sid);
    writeLocal(SID_TS_KEY, String(Date.now()));
    setUserId(next);
    setSessionId(sid);
    setPersona(p);
  }, []);

  const value = useMemo(() => ({ userId, sessionId, persona, ready, shopAs }), [userId, sessionId, persona, ready, shopAs]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
