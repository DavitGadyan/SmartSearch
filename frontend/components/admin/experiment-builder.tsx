"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PaperPlaneRight, Sparkle } from "@phosphor-icons/react";
import { api, DEFAULT_UI, type Experiment, type ExperimentDraft, type Proposal, type UiConfig } from "@/lib/api";
import { fmt } from "@/lib/format";
import { Badge, Button, Card, Chip, Input, Label, Rows, Select, cn } from "@/components/ui";
import { UiPreview } from "./ui-preview";

type Msg = { role: "user" | "assistant"; content: string };
const EXAMPLES = ["Make the add-to-cart button green and call it Add to bag", "Add a cart icon to the button and hide ratings on cards", "Change the hero title to Furniture that fits your home, assume a 3% lift"];
const EFFECT_KEYS = ["add_to_cart_rate", "conversion_rate", "ctr"] as const;

/** Console assistant + form: describe a storefront change, review both arms, launch, simulate traffic, read the verdict. */
export function ExperimentBuilder() {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal>({ name: "", hypothesis: "", summary: "", control: DEFAULT_UI, treatment: DEFAULT_UI, assumed_effect: {}, changes: [] });
  const [experimentKey, setExperimentKey] = useState<string | null>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [last, setLast] = useState<ExperimentDraft | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // poll the experiment while traffic is being simulated
  useEffect(() => {
    if (!experimentKey) return;
    let stop = false;
    const tick = async () => {
      try {
        const e = await api.admin.get<Experiment>(`/experiments/${experimentKey}`);
        if (!stop) setExperiment(e);
        if (!stop && e.config.simulated_traffic?.status === "running") setTimeout(tick, 3000);
      } catch {}
    };
    tick();
    return () => {
      stop = true;
    };
  }, [experimentKey, last]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    const next = [...messages, { role: "user" as const, content: t }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.admin.post<ExperimentDraft>("/experiments/draft", { messages: next, proposal: proposal.name ? proposal : null, experiment_key: experimentKey });
      setMessages([...next, { role: "assistant", content: res.message }]);
      if (res.proposal) setProposal(res.proposal);
      if (res.experiment_key) setExperimentKey(res.experiment_key);
      setLast(res);
      qc.invalidateQueries({ queryKey: ["admin", "/experiments"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const setArm = (arm: "control" | "treatment", patch: Partial<UiConfig>) => setProposal((p) => ({ ...p, [arm]: { ...p[arm], ...patch } }));

  const launch = async () => {
    setBusy(true);
    setError(null);
    try {
      const key = `${proposal.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "ui_test"}_${Math.random().toString(36).slice(2, 8)}`;
      await api.admin.post<Experiment>("/experiments", {
        key,
        name: proposal.name || "UI test",
        hypothesis: proposal.hypothesis || null,
        surface: "ui",
        variants: [
          { key: "control", name: "Current storefront", description: "What shoppers see today", ui: proposal.control, weight: 0.5 },
          { key: "treatment", name: proposal.name || "Treatment", description: proposal.summary, ui: proposal.treatment, effect: proposal.assumed_effect, weight: 0.5 },
        ],
        guardrail_metrics: ["no_click_rate"],
        config: { alpha: 0.05, power: 0.8, mde_rel: 0.05, pre_period_days: 7, summary: proposal.summary, created_by: "console-form" },
      });
      const e = await api.admin.patch<Experiment>(`/experiments/${key}/status`, { status: "running" });
      setExperimentKey(key);
      setExperiment(e);
      qc.invalidateQueries({ queryKey: ["admin", "/experiments"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const simulate = async () => {
    if (!experimentKey) return;
    setBusy(true);
    setError(null);
    try {
      await api.admin.post(`/experiments/${experimentKey}/simulate`, { users: Math.min(12000, 2 * (last?.plan?.users_per_arm ?? 3000)), days: 7 });
      setLast((l) => (l ? { ...l } : l));
      setExperiment((e) => (e ? { ...e, config: { ...e.config, simulated_traffic: { status: "running", users: 0, days: 7 } } } : e));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sim = experiment?.config.simulated_traffic;
  const armFields = (arm: "control" | "treatment") => {
    const u = proposal[arm];
    return (
      <div className="grid gap-2 text-xs">
        <div className="grid grid-cols-[1fr_120px] gap-2">
          <div className="grid gap-1">
            <Label>Button label</Label>
            <Input value={u.cta_label} onChange={(e) => setArm(arm, { cta_label: e.target.value })} className="h-8 text-xs" />
          </div>
          <div className="grid gap-1">
            <Label>Style</Label>
            <Select value={u.cta_style} onChange={(e) => setArm(arm, { cta_style: e.target.value as UiConfig["cta_style"] })} className="h-8 text-xs">
              <option value="dark">dark</option>
              <option value="glass">glass</option>
              <option value="accent">accent</option>
            </Select>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {(["cta_icon", "show_ratings", "card_badges"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1.5 text-fg-2">
              <input type="checkbox" checked={u[k]} onChange={(e) => setArm(arm, { [k]: e.target.checked })} className="accent-[var(--fg)]" /> {fmt.title(k)}
            </label>
          ))}
        </div>
        <div className="grid gap-1">
          <Label>Hero title</Label>
          <Input value={u.hero_title} onChange={(e) => setArm(arm, { hero_title: e.target.value })} className="h-8 text-xs" />
        </div>
        <div className="grid gap-1">
          <Label>Banner</Label>
          <Input value={u.banner ?? ""} placeholder="none" onChange={(e) => setArm(arm, { banner: e.target.value || null })} className="h-8 text-xs" />
        </div>
      </div>
    );
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      {/* chat */}
      <Card className="flex min-h-[560px] flex-col p-4">
        <div className="flex items-center gap-2">
          <Sparkle size={16} weight="fill" className="text-fg-2" />
          <p className="text-sm font-medium">Describe the change</p>
          <Badge tone={last?.provider === "claude" ? "info" : "neutral"} className="ml-auto">
            {last?.provider === "rule_based" ? "rule-based" : "Claude"}
          </Badge>
        </div>
        <div className="mt-3 flex-1 space-y-3 overflow-y-auto">
          {messages.length === 0 && (
            <ul className="flex flex-wrap gap-2">
              {EXAMPLES.map((s) => (
                <li key={s}>
                  <Chip onClick={() => send(s)}>{s}</Chip>
                </li>
              ))}
            </ul>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <p className={cn("rise max-w-[90%] rounded-card px-3 py-2 text-sm leading-relaxed", m.role === "user" ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg")}>{m.content}</p>
            </div>
          ))}
          {busy && <p className="text-xs text-muted">Working… launching and simulating can take a minute.</p>}
          {error && <p className="text-xs text-critical">{error}</p>}
          <div ref={end} />
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="mt-3 flex gap-2 rounded-control border border-border bg-surface p-1.5"
        >
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={experimentKey ? "Ask for the results, or describe another change" : "Make the add-to-cart button green…"} aria-label="Message" className="h-9 flex-1 bg-transparent px-2 text-sm outline-none placeholder:text-muted" disabled={busy} />
          <Button type="submit" size="sm" disabled={busy || !input.trim()} aria-label="Send">
            <PaperPlaneRight size={14} weight="fill" />
          </Button>
        </form>
      </Card>

      {/* form + preview */}
      <div className="grid gap-4">
        <Card className="p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1">
              <Label>Name</Label>
              <Input value={proposal.name} onChange={(e) => setProposal({ ...proposal, name: e.target.value })} className="h-9 text-sm" placeholder="Green add-to-bag button" />
            </div>
            <div className="grid gap-1">
              <Label>Assumed effect (simulation only)</Label>
              <div className="grid grid-cols-3 gap-2">
                {EFFECT_KEYS.map((k) => (
                  <Input key={k} type="number" step="0.01" title={fmt.title(k)} value={proposal.assumed_effect[k] ?? 0} onChange={(e) => setProposal({ ...proposal, assumed_effect: { ...proposal.assumed_effect, [k]: Number(e.target.value) } })} className="tnum h-9 text-xs" />
                ))}
              </div>
            </div>
          </div>
          <div className="mt-3 grid gap-1">
            <Label>Hypothesis</Label>
            <Input value={proposal.hypothesis} onChange={(e) => setProposal({ ...proposal, hypothesis: e.target.value })} className="h-9 text-sm" placeholder="Changing X will raise conversion because Y" />
          </div>
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          {(["control", "treatment"] as const).map((arm) => (
            <Card key={arm} className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{arm}</p>
              <div className="mt-3">
                <UiPreview ui={proposal[arm]} />
              </div>
              <div className="mt-4">{armFields(arm)}</div>
            </Card>
          ))}
        </div>
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            {!experimentKey ? (
              <Button onClick={launch} disabled={busy || !proposal.name}>
                Create and deploy
              </Button>
            ) : (
              <>
                <Badge tone="good">running · {experimentKey}</Badge>
                <Button variant="secondary" onClick={simulate} disabled={busy || sim?.status === "running"}>
                  {sim?.status === "running" ? "Simulating…" : "Simulate traffic"}
                </Button>
                <Link href={`/admin/experiments/${experimentKey}`} className="text-sm text-link hover:underline">
                  View results
                </Link>
              </>
            )}
            {last?.plan && <span className="tnum ml-auto text-xs text-muted">Plan: {fmt.num(last.plan.users_per_arm)} users per arm for a {fmt.pct(last.plan.mde_rel, 0)} lift on {fmt.pct(last.plan.baseline_conversion, 2)}</span>}
          </div>
          {sim && (
            <Rows
              dense
              className="mt-3"
              items={[
                ["Simulated traffic", `${sim.status}${sim.counters ? ` · ${fmt.num(sim.counters.searches)} searches · ${fmt.num(sim.counters.purchases)} purchases` : ""}`],
                ["Assigned users", fmt.num(experiment?.assigned_users)],
              ]}
            />
          )}
          {last?.results && (
            <p className="mt-3 text-sm text-fg-2">
              {last.results.hypothesis} Conversion {fmt.pct(last.results.control, 2)} → {fmt.pct(last.results.treatment, 2)} ({fmt.signedPct(last.results.rel_lift)}); {fmt.num(last.results.n_control)} vs {fmt.num(last.results.n_treatment)} users. Verdict: {last.results.decision}.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
