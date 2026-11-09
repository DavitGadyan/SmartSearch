/** Client-side behavioral event SDK: batches events and flushes them to POST /api/v1/events. */
import { API_URL } from "./api";

export type TrackEvent = {
  event_type: "click" | "product_view" | "add_to_cart" | "rec_click" | "search" | "impression" | "rec_impression";
  user_id: string;
  session_id: string;
  query?: string | null;
  product_id?: number | null;
  position?: number | null;
  experiment_key?: string | null;
  variant?: string | null;
  ranking_model_version?: string | null;
  strategy?: string | null;
  source?: string | null;
  metadata?: Record<string, unknown> | null;
};

const queue: TrackEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

async function flush(useBeacon = false) {
  if (queue.length === 0) return;
  const batch = queue.splice(0, 200);
  const body = JSON.stringify({ events: batch });
  const url = `${API_URL}/api/v1/events`;
  try {
    if (useBeacon && typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    } else {
      await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
    }
  } catch {
    // tracking must never break the shopping experience
  }
}

export function track(event: TrackEvent) {
  if (!event.user_id || !event.session_id) return;
  queue.push(event);
  if (queue.length >= 20) void flush();
  else if (!timer)
    timer = setTimeout(() => {
      timer = null;
      void flush();
    }, 1500);
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => void flush(true));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") void flush(true);
  });
}

/** Where a click / add-to-cart happened; copied onto the event so analyses can slice by experiment and strategy. */
export type TrackContext = {
  query?: string | null;
  experiment_key?: string | null;
  variant?: string | null;
  ranking_model_version?: string | null;
  strategy?: string | null;
  source: string; // "search" | "recs:<rail>" | "pdp" | "agent"
};

export const ctxFields = (c: TrackContext) => ({
  query: c.query ?? null,
  experiment_key: c.experiment_key ?? null,
  variant: c.variant ?? null,
  ranking_model_version: c.ranking_model_version ?? null,
  strategy: c.strategy ?? null,
  source: c.source,
});
