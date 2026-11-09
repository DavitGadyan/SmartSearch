const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const money0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmt = {
  money: (v: number | null | undefined) => (v == null ? "n/a" : money.format(v)),
  money0: (v: number | null | undefined) => (v == null ? "n/a" : money0.format(v)),
  num: (v: number | null | undefined) => (v == null ? "n/a" : num.format(v)),
  compact: (v: number | null | undefined) => (v == null ? "n/a" : compact.format(v)),
  pct: (v: number | null | undefined, digits = 1) => (v == null || Number.isNaN(v) ? "n/a" : `${(v * 100).toFixed(digits)}%`),
  signedPct: (v: number | null | undefined, digits = 1) => (v == null || Number.isNaN(v) ? "n/a" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`),
  p: (v: number | null | undefined) => (v == null ? "n/a" : v < 0.0001 ? "< 0.0001" : v.toFixed(4)),
  date: (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  dateTime: (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
  title: (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
};

/** Deterministic hue for a category tile (products without a photo). */
export function classHue(s: string | null | undefined): number {
  let h = 0;
  for (const c of s ?? "x") h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
