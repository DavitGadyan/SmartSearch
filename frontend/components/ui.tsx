import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, CaretRight } from "@phosphor-icons/react/dist/ssr";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, LabelHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { fmt } from "@/lib/format";
import { CountUp } from "@/components/motion";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

/* Shape system: cards 12px, controls 6px, badges and chips small. Flat surfaces, 1px borders, no shadows. */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "accent";
  size?: "sm" | "md" | "lg";
};

export function Button({ className, variant = "primary", size = "md", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium backdrop-blur-md transition-[background-color,transform,opacity] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg",
        {
          primary: "bg-accent text-accent-fg hover:bg-fg-2",
          secondary: "border border-border bg-white/60 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,.8)] hover:bg-white/80",
          ghost: "text-fg-2 hover:bg-white/50 hover:text-fg",
          accent: "bg-[#3f9a66] text-white hover:bg-[#368a5a]",
        }[variant],
        { sm: "h-8 px-3.5 text-xs", md: "h-10 px-5 text-sm", lg: "h-12 px-7 text-base" }[size],
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rise rounded-card", className)} {...props} />;
}

export type Tone = "neutral" | "info" | "good" | "warning" | "critical";
const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-fg-2",
  info: "bg-info-soft text-info",
  good: "bg-good-soft text-good",
  warning: "bg-warning-soft text-warning",
  critical: "bg-critical-soft text-critical",
};

export function Badge({ className, tone = "neutral", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone | "accent" }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase leading-4 tracking-wide", TONE[tone === "accent" ? "info" : tone], className)} {...props} />;
}

/** Small selectable label: filters, suggested queries, starters. */
export function Chip({ active, href, className, children, ...props }: { active?: boolean; href?: string; className?: string; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = cn(
    "inline-flex items-center gap-1.5 rounded-control border px-3.5 py-1 text-xs transition-colors",
    active ? "border-fg bg-fg text-white" : "border-border bg-white/55 text-fg-2 backdrop-blur-md hover:bg-white/80 hover:text-fg",
    className,
  );
  if (href) {
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={cls} aria-pressed={active} {...props}>
      {children}
    </button>
  );
}

/** One number with a label; `delta` is a relative change (0.12 = +12%). A numeric `value` counts up when it appears. */
export function Stat({ label, value, format, delta, hint, invert, size = "md", className }: { label: string; value: ReactNode; format?: (n: number) => string; delta?: number | null; hint?: string; invert?: boolean; size?: "md" | "lg"; className?: string }) {
  const good = delta == null ? null : invert ? delta < 0 : delta > 0;
  return (
    <Card className={cn(size === "lg" ? "p-5" : "p-4", className)}>
      <p className="text-xs text-muted">{label}</p>
      <p className={cn("tnum mt-1 font-semibold tracking-tight", size === "lg" ? "text-3xl" : "text-2xl")}>{typeof value === "number" ? <CountUp value={value} format={format ?? fmt.num} /> : value}</p>
      {(delta != null || hint) && (
        <p className="mt-1 flex items-center gap-1 text-xs">
          {delta != null && Number.isFinite(delta) ? (
            <span className={cn("tnum inline-flex items-center gap-0.5 font-medium", good ? "text-good" : "text-critical")}>
              {good ? <ArrowUpRight size={12} weight="bold" /> : <ArrowDownRight size={12} weight="bold" />}
              {fmt.signedPct(delta)}
            </span>
          ) : null}
          <span className="text-muted">{hint ?? (delta != null ? "vs previous period" : "")}</span>
        </p>
      )}
    </Card>
  );
}

/** Label / value rows. */
export function Rows({ items, dense, className }: { items: [string, ReactNode][]; dense?: boolean; className?: string }) {
  return (
    <dl className={cn("divide-y divide-border", className)}>
      {items.map(([k, v]) => (
        <div key={k} className={cn("flex items-baseline justify-between gap-4", dense ? "py-1 text-xs" : "py-1.5 text-sm")}>
          <dt className="text-fg-2">{k}</dt>
          <dd className="tnum text-right font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Collapsed detail, native <details>. */
export function Disclosure({ summary, children, defaultOpen, className }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string }) {
  return (
    <details className={cn("group", className)} open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-fg-2 hover:text-fg [&::-webkit-details-marker]:hidden">
        <CaretRight size={14} weight="bold" className="transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

export function Section({ title, description, action, children, className }: { title: string; description?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("mt-10 first:mt-0", className)}>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function PageHeader({ title, description, action, className }: { title: string; description?: string; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-8 flex flex-wrap items-end justify-between gap-3", className)}>
      <div>
        <h1 className="font-serif text-3xl font-normal tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-fg-2">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("shimmer rounded-tile", className)} {...props} />;
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-10 w-full rounded-control border border-border bg-white/60 px-4 text-sm text-fg backdrop-blur-md placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-fg", className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-10 rounded-control border border-border bg-white/60 px-4 text-sm text-fg backdrop-blur-md focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-fg", className)} {...props} />;
}

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-xs font-medium text-fg-2", className)} {...props} />;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="glass rounded-card border-dashed p-10 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-fg-2">{hint}</p>}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-card border border-critical/30 bg-critical-soft p-4 text-sm backdrop-blur-md">
      <p className="font-medium text-critical">Request failed</p>
      <p className="mt-1 text-fg-2">{msg}</p>
    </div>
  );
}
