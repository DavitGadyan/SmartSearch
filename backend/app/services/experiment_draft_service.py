"""The console's experimentation assistant: describe a storefront change in plain language, get a drafted UI
experiment, a sample-size plan, and (after an explicit yes) a launched test with simulated traffic and a verdict in
hypothesis-test language. Claude (Haiku) drives a small tool loop; without an API key a rule-based fallback covers
the same steps."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.experiments import power as pw
from app.experiments.analysis import analyze
from app.models import Experiment
from app.schemas.experiments import DraftMessage, UiConfig
from app.services import analytics_service, experiment_service

log = get_logger("experiment-draft")
MAX_TURNS = 8
DEFAULT_MDE = 0.05

SYSTEM = """You are the experimentation assistant inside the SmartSearch merchant console.
The merchant describes a change to the storefront: button label, button style (dark, glass, accent), button icon,
ratings on cards, badges on cards, hero title/subtitle, or a banner. You turn it into an A/B test and run it.

Steps:
1. Call propose_ui_experiment with the treatment = the current storefront plus the change (the current storefront
   is: label "Add to cart", style dark, no icon, ratings shown, badges shown, hero "Search that learns what sells.",
   no banner; control is always that, you do not describe it). Short name, one-sentence hypothesis of the form
   "Changing X will raise conversion because Y". Put an assumed_effect only when the merchant states one; otherwise
   0. Then call plan_sample_size (5% relative MDE unless told otherwise).
2. Show the merchant: what changes, the users per arm the plan requires, and ask for a yes to launch.
3. Only after an explicit yes: call launch_experiment, then simulate_traffic (users = 2 × users per arm, capped at
   12000; days 7), then read_results.
4. Report in hypothesis-test language. H0: the change does not alter conversion rate. Reject H0 when p < alpha,
   otherwise fail to reject. Always give control and treatment rates, relative lift, 95% CI, p, users per arm, and
   say that the traffic was simulated with the stated assumed effect.
Replies under 90 words, plain language, no markdown headings. Never invent numbers: use tool outputs."""

UI_SCHEMA = {
    "type": "object",
    "properties": {
        "cta_label": {"type": "string"},
        "cta_style": {"type": "string", "enum": ["dark", "glass", "accent"]},
        "cta_icon": {"type": "boolean"},
        "show_ratings": {"type": "boolean"},
        "card_badges": {"type": "boolean"},
        "hero_title": {"type": "string"},
        "hero_subtitle": {"type": "string"},
        "banner": {"type": ["string", "null"]},
    },
    "required": [
        "cta_label",
        "cta_style",
        "cta_icon",
        "show_ratings",
        "card_badges",
        "hero_title",
        "hero_subtitle",
        "banner",
    ],
    "additionalProperties": False,
}
EFFECT_SCHEMA = {
    "type": "object",
    "properties": {
        "ctr": {"type": "number"},
        "add_to_cart_rate": {"type": "number"},
        "conversion_rate": {"type": "number"},
    },
    "required": ["ctr", "add_to_cart_rate", "conversion_rate"],
    "additionalProperties": False,
}
TOOLS: list[dict] = [
    {
        "name": "propose_ui_experiment",
        "description": "Draft the test: treatment = the current storefront with the change applied (control is always the current storefront). assumed_effect are relative lifts used only to simulate traffic (0 = no effect).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "hypothesis": {"type": "string"},
                "summary": {"type": "string", "description": "One plain sentence: what changes for shoppers"},
                "treatment": UI_SCHEMA,
                "assumed_effect": EFFECT_SCHEMA,
            },
            "required": ["name", "hypothesis", "summary", "treatment", "assumed_effect"],
            "additionalProperties": False,
        },
    },
    {
        "name": "plan_sample_size",
        "description": "Users per arm needed to detect a relative lift on the store's conversion rate (alpha 0.05, power 0.8), and the days that takes at current traffic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mde_rel": {"type": "number", "description": "relative lift to detect, e.g. 0.05"}
            },
            "required": ["mde_rel"],
            "additionalProperties": False,
        },
    },
    {
        "name": "launch_experiment",
        "description": "Create the drafted experiment and set it running on the storefront. Only after the merchant explicitly agreed.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "simulate_traffic",
        "description": "Send simulated shoppers through the running test (uses the assumed effect). Blocks until done (about a minute).",
        "input_schema": {
            "type": "object",
            "properties": {"users": {"type": "integer"}, "days": {"type": "integer"}},
            "required": ["users", "days"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_results",
        "description": "Analyse the experiment: rates per arm, lift, CI, p-value, power, the engine's verdict.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

YES = re.compile(r"\b(yes|launch|deploy|go ahead|do it|run it|start it|ship it|ok(ay)?)\b", re.I)


def slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "ui_test"
    return f"{base}_{hashlib.sha1(f'{name}{time.time()}'.encode()).hexdigest()[:6]}"


def hypothesis_verdict(primary: dict, alpha: float = 0.05) -> str:
    p = primary["p_value"]
    direction = "higher" if primary["treatment"] > primary["control"] else "lower"
    if p < alpha:
        return f"Reject H0 at alpha {alpha}: conversion is {direction} in treatment (p = {p:.4f})."
    return f"Fail to reject H0 at alpha {alpha}: no significant difference in conversion (p = {p:.4f})."


class _Session:
    """Tool implementations with the state of one conversation."""

    def __init__(self, db: AsyncSession, proposal: dict | None, experiment_key: str | None) -> None:
        self.db = db
        self.proposal = proposal
        self.experiment_key = experiment_key
        self.plan: dict | None = None
        self.results: dict | None = None
        self.trace: list[dict] = []

    async def run(self, name: str, inp: dict) -> tuple[str, bool]:
        try:
            out, err = await self._run(name, inp)
            self.trace.append({"tool": name, "input": inp, "summary": out[:120]})
            return out, err
        except Exception as ex:  # tool errors go back to the model
            log.exception("draft tool %s failed", name)
            self.trace.append({"tool": name, "input": inp, "summary": f"error: {ex}"})
            return f"Error: {ex}", True

    async def _run(self, name: str, inp: dict) -> tuple[str, bool]:
        if name == "propose_ui_experiment":
            control = UiConfig().model_dump()  # the current storefront, by definition
            treatment = UiConfig(**inp["treatment"]).model_dump()
            self.proposal = {
                "name": inp["name"][:120],
                "hypothesis": inp["hypothesis"][:400],
                "summary": inp["summary"][:200],
                "control": control,
                "treatment": treatment,
                "assumed_effect": {k: float(v) for k, v in (inp.get("assumed_effect") or {}).items()},
                "changes": [k for k in control if control[k] != treatment[k]],
            }
            return json.dumps(self.proposal), False
        if name == "plan_sample_size":
            ov = await analytics_service.overview(self.db, 28)
            k = ov["kpis"]
            p0 = float(k.get("conversion_rate") or 0.03)
            daily = float(k.get("visitors") or 0) / 28
            mde = float(inp.get("mde_rel") or DEFAULT_MDE)
            n = pw.sample_size_proportion(p0, mde)
            self.plan = {
                "baseline_conversion": round(p0, 4),
                "mde_rel": mde,
                "alpha": 0.05,
                "power": 0.8,
                "users_per_arm": n,
                "total_users": 2 * n,
                "days_at_current_traffic": round(pw.duration_days(n, daily), 1) if daily else None,
            }
            return json.dumps(self.plan), False
        if name == "launch_experiment":
            if not self.proposal:
                return "Error: nothing proposed yet", True
            if self.experiment_key:
                return json.dumps({"key": self.experiment_key, "status": "already launched"}), False
            key = slug(self.proposal["name"])
            prop = self.proposal
            e = Experiment(
                key=key,
                name=prop["name"],
                hypothesis=prop["hypothesis"],
                status="draft",
                surface="ui",
                variants=[
                    {
                        "key": "control",
                        "name": "Current storefront",
                        "description": "What shoppers see today",
                        "ui": prop["control"],
                        "weight": 0.5,
                    },
                    {
                        "key": "treatment",
                        "name": prop["name"],
                        "description": prop["summary"],
                        "ui": prop["treatment"],
                        "effect": prop.get("assumed_effect") or {},
                        "weight": 0.5,
                    },
                ],
                traffic_allocation=1.0,
                salt=hashlib.sha256(key.encode()).hexdigest()[:16],
                primary_metric="conversion_rate",
                secondary_metrics=["search_ctr", "add_to_cart_rate", "revenue_per_visitor", "aov"],
                guardrail_metrics=["no_click_rate"],
                config={
                    "alpha": 0.05,
                    "power": 0.8,
                    "mde_rel": (self.plan or {}).get("mde_rel", DEFAULT_MDE),
                    "pre_period_days": 7,
                    "summary": prop["summary"],
                    "created_by": "console-assistant",
                },
            )
            self.db.add(e)
            await self.db.commit()
            try:
                await experiment_service.set_status(self.db, key, "running")
            except RuntimeError as ex:
                return f"Created as draft but not started: {ex}. Complete the other test first.", True
            self.experiment_key = key
            return json.dumps({"key": key, "status": "running"}), False
        if name == "simulate_traffic":
            if not self.experiment_key:
                return "Error: launch the experiment first", True
            from app.simulation.ui_traffic import simulate_ui_experiment  # heavy import, local

            users = int(min(max(inp.get("users") or 3000, 200), 12000))
            days = int(min(max(inp.get("days") or 7, 1), 28))
            counters = await simulate_ui_experiment(self.experiment_key, users, days)
            return json.dumps(
                {
                    "simulated": True,
                    "users": users,
                    "days": days,
                    **{k: counters[k] for k in ("searches", "clicks", "carts", "purchases")},
                }
            ), False
        if name == "read_results":
            if not self.experiment_key:
                return "Error: no experiment yet", True
            a = await analyze(self.db, self.experiment_key)
            if a.get("status") != "ok":
                return json.dumps({"status": a.get("status", "no_data")}), False
            c = a["comparisons"][0]
            primary = c["metrics"][c["primary_metric"]]
            self.results = {
                "metric": c["primary_metric"],
                "control": primary["control"],
                "treatment": primary["treatment"],
                "rel_lift": primary["rel_lift"],
                "ci": [primary["ci_low"], primary["ci_high"]],
                "p_value": primary["p_value"],
                "n_control": c["n_control"],
                "n_treatment": c["n_treatment"],
                "power": c["power"],
                "decision": c["decision"]["label"],
                "hypothesis": hypothesis_verdict(primary),
                "srm_ok": not a["srm"]["srm_detected"],
            }
            return json.dumps(self.results), False
        return f"Error: unknown tool {name}", True


def _history(messages: list[DraftMessage], proposal: dict | None, experiment_key: str | None) -> list[dict]:
    out = [{"role": m.role, "content": m.content} for m in messages]
    ctx = []
    if proposal:
        ctx.append("Current draft: " + json.dumps(proposal))
    if experiment_key:
        ctx.append(f"Current experiment key: {experiment_key}")
    if ctx and out:
        out[-1] = {"role": out[-1]["role"], "content": out[-1]["content"] + "\n\n[" + " · ".join(ctx) + "]"}
    return out


async def draft(
    db: AsyncSession, messages: list[DraftMessage], proposal: dict | None, experiment_key: str | None
) -> dict:
    t0 = time.perf_counter()
    s = _Session(db, proposal, experiment_key)
    if not settings.anthropic_api_key:
        text = await _rule_based(s, messages[-1].content)
        provider = "rule_based"
    else:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        convo: list[Any] = _history(messages, proposal, experiment_key)
        text = ""
        for _ in range(MAX_TURNS):
            resp = await client.messages.create(
                model=settings.bulk_model, max_tokens=1500, system=SYSTEM, tools=TOOLS, messages=convo
            )
            text = " ".join(b.text for b in resp.content if b.type == "text").strip() or text
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                break
            convo.append({"role": "assistant", "content": resp.content})
            results = []
            for tu in uses:
                content, is_error = await s.run(tu.name, dict(tu.input))
                results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": content, "is_error": is_error}
                )
            convo.append({"role": "user", "content": results})
        provider = "claude"
    return {
        "message": text or "Done.",
        "proposal": s.proposal,
        "experiment_key": s.experiment_key,
        "plan": s.plan,
        "results": s.results,
        "trace": s.trace,
        "provider": provider,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }


async def _rule_based(s: _Session, message: str) -> str:
    """No API key: keywords → proposal; an explicit yes → launch, simulate, read."""
    m = message.lower()
    if s.proposal and not s.experiment_key and YES.search(m):
        out, err = await s.run("launch_experiment", {})
        if err:
            return out
        plan = s.plan or json.loads((await s.run("plan_sample_size", {"mde_rel": DEFAULT_MDE}))[0])
        await s.run("simulate_traffic", {"users": min(12000, 2 * plan["users_per_arm"]), "days": 7})
        res, _ = await s.run("read_results", {})
        r = json.loads(res)
        if r.get("status"):
            return "Launched and simulated, but the analysis has no data yet."
        return (
            f"Launched {s.experiment_key} and ran simulated traffic. Conversion {r['control']:.2%} → {r['treatment']:.2%} "
            f"({r['rel_lift']:+.1%}, p = {r['p_value']:.4f}, {r['n_control']:,} vs {r['n_treatment']:,} users). {r['hypothesis']} "
            f"Verdict: {r['decision']}. Traffic was simulated with the assumed effect."
        )
    if s.experiment_key and re.search(r"result|how did|verdict|outcome", m):
        res, _ = await s.run("read_results", {})
        r = json.loads(res)
        return r.get("hypothesis", "No data yet.")
    treatment = UiConfig().model_dump()
    label = re.search(r"(?:say|label|text|call(?:ed)?|read|named?)\s+[\"“']?([^\"”'.,]{2,30})", message, re.I)
    if label:
        treatment["cta_label"] = label.group(1).strip().capitalize()
    if re.search(r"green|accent|colou?r", m):
        treatment["cta_style"] = "accent"
    elif re.search(r"glass|transparent|outline", m):
        treatment["cta_style"] = "glass"
    if re.search(r"icon", m):
        treatment["cta_icon"] = True
    if re.search(r"hide (the )?ratings|without ratings|no ratings", m):
        treatment["show_ratings"] = False
    if re.search(r"hide (the )?badges|no badges", m):
        treatment["card_badges"] = False
    banner = re.search(r"banner\s+(?:saying|that says|with)?\s*[\"“']?([^\"”']{3,80})", message, re.I)
    if banner:
        treatment["banner"] = banner.group(1).strip()
    effect = re.search(r"(\d+(?:\.\d+)?)\s*%", m)
    lift = float(effect.group(1)) / 100 if effect else 0.0
    control = UiConfig().model_dump()
    changes = [k for k in control if control[k] != treatment[k]]
    name = "Button test" if any(c.startswith("cta") for c in changes) else "Storefront test"
    await s.run(
        "propose_ui_experiment",
        {
            "name": name,
            "hypothesis": f"Changing {', '.join(changes) or 'the storefront'} will raise conversion.",
            "summary": f"Treatment changes {', '.join(changes) or 'nothing'}; control keeps the current storefront.",
            "treatment": treatment,
            "assumed_effect": {"ctr": 0.0, "add_to_cart_rate": lift, "conversion_rate": 0.0},
        },
    )
    plan_out, _ = await s.run("plan_sample_size", {"mde_rel": DEFAULT_MDE})
    plan = json.loads(plan_out)
    return (
        f"Draft ready: treatment changes {', '.join(changes) or 'nothing'}. To detect a 5% relative lift on a "
        f"{plan['baseline_conversion']:.2%} baseline you need {plan['users_per_arm']:,} users per arm. "
        f"Say yes to launch it and run simulated traffic."
    )


async def experiment_exists(db: AsyncSession, key: str) -> bool:
    return (await db.scalar(select(Experiment.id).where(Experiment.key == key))) is not None
