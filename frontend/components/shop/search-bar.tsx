"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MagnifyingGlass, Microphone, Package, Tag } from "@phosphor-icons/react";
import { api, type Suggestion } from "@/lib/api";
import { cn } from "@/components/ui";

/* Web Speech API (Chrome, Safari, Edge). Typed minimally so the build does not depend on lib.dom declaring it. */
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};
const recognitionCtor = (): (new () => Recognition) | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

export function SearchBar({ initial = "", autoFocus = false, size = "md" }: { initial?: string; autoFocus?: boolean; size?: "md" | "lg" }) {
  const router = useRouter();
  const [value, setValue] = useState(initial);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [debounced, setDebounced] = useState(initial);
  const [canDictate, setCanDictate] = useState(false);
  const [listening, setListening] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const recognition = useRef<Recognition | null>(null);

  useEffect(() => {
    setValue(initial);
  }, [initial]);
  useEffect(() => {
    setCanDictate(recognitionCtor() !== null);
    return () => recognition.current?.stop();
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), 120);
    return () => clearTimeout(t);
  }, [value]);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const { data } = useQuery({
    queryKey: ["suggest", debounced],
    queryFn: () => api.get<{ suggestions: Suggestion[] }>("/autosuggest", { q: debounced, limit: 8 }),
    enabled: debounced.trim().length >= 2 && open,
  });
  const suggestions = data?.suggestions ?? [];

  const go = (q: string) => {
    const t = q.trim();
    if (!t) return;
    setOpen(false);
    router.push(`/search?q=${encodeURIComponent(t)}`);
  };

  /** Dictation: live transcript fills the field, the final result searches. */
  const dictate = () => {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      let text = "";
      let final = false;
      for (const res of Array.from(e.results)) {
        text += res[0]?.transcript ?? "";
        if (res.isFinal) final = true;
      }
      setValue(text);
      setOpen(false);
      if (final) go(text);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognition.current = r;
    setListening(true);
    r.start();
  };

  return (
    <div ref={box} className="relative w-full">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          go(active >= 0 && suggestions[active] ? suggestions[active].text : value);
        }}
        role="search"
      >
        <MagnifyingGlass size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <input
          aria-label="Search products"
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, suggestions.length - 1));
            else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, -1));
            else if (e.key === "Escape") setOpen(false);
          }}
          placeholder={listening ? "Listening…" : "Search furniture, decor, lighting…"}
          className={cn(
            "w-full rounded-control border border-border bg-white/70 pl-11 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,.8)] backdrop-blur-md transition-[background-color,box-shadow] placeholder:text-muted focus-visible:bg-white/85 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent",
            canDictate ? "pr-13" : "pr-5",
            size === "lg" ? "h-13 text-base" : "h-10 text-sm",
          )}
        />
        {canDictate && (
          <button
            type="button"
            onClick={dictate}
            aria-pressed={listening}
            aria-label={listening ? "Stop listening" : "Search by voice"}
            title={listening ? "Stop" : "Search by voice"}
            className={cn(
              "absolute right-2 top-1/2 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-full transition-colors",
              listening ? "bg-critical-soft text-critical" : "text-muted hover:bg-white/80 hover:text-fg",
            )}
          >
            <Microphone size={18} weight={listening ? "fill" : "regular"} className={listening ? "animate-pulse" : undefined} />
          </button>
        )}
      </form>
      {open && suggestions.length > 0 && (
        <ul role="listbox" className="rise absolute z-30 mt-1 w-full overflow-hidden rounded-card border border-border bg-surface shadow-[var(--shadow-card)] backdrop-blur-xl [animation-duration:250ms]">
          {suggestions.map((s, i) => (
            <li key={`${s.kind}-${s.text}`} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => go(s.text)}
                className={cn("flex w-full items-center gap-3 px-3 py-2 text-left text-sm capitalize", i === active ? "bg-surface-2" : "hover:bg-surface-2")}
              >
                {s.kind === "category" ? <Tag size={14} className="text-accent" /> : <Package size={14} className="text-muted" />}
                <span className="truncate">{s.text}</span>
                {s.kind === "category" && <span className="ml-auto text-[11px] text-muted">Category</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
