"""Render the live experiment analyses + offline evaluation into docs/experiment-report.md (numbers are computed, never typed)."""

import asyncio
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import REPO_ROOT, settings
from app.core.db import SessionLocal
from app.experiments.analysis import METRIC_LABELS, analyze
from app.models import Experiment

OUT = REPO_ROOT / "docs" / "experiment-report.md"
MONEY = {"revenue_per_visitor", "aov"}


def fmt(metric: str, v: float) -> str:
    return (
        f"${v:,.2f}"
        if metric in MONEY
        else f"{v * 100:.2f}%"
        if metric != "purchases_per_visitor"
        else f"{v:.4f}"
    )


def pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def experiment_section(a: dict) -> str:
    e = a["experiment"]
    lines = [
        f"## {e['name']}",
        "",
        f"`{e['key']}` · status **{e['status']}** · {e['start_at'][:10] if e['start_at'] else ''} to {e['end_at'][:10] if e['end_at'] else 'now'} · {a.get('days_running')} days",
        "",
    ]
    if e.get("hypothesis"):
        lines += [f"> {e['hypothesis']}", ""]
    if a["status"] != "ok":
        return "\n".join(lines + ["No assigned users yet.", ""])
    srm = a["srm"]
    lines += [
        f"**Sample ratio check:** {' · '.join(f'{k} {v:,}' for k, v in srm['observed'].items())} (χ² p = {srm['p_value']:.3f}) → {'⚠ mismatch' if srm['srm_detected'] else 'balanced'}",
        "",
    ]
    for c in a["comparisons"]:
        lines += [
            f"### {c['treatment']} vs {c['control']} ({c['n_treatment']:,} vs {c['n_control']:,} users)",
            "",
            f"**Recommendation: {c['decision']['label']}**",
            "",
            c["decision"]["narrative"],
            "",
        ]
        lines += [
            "| Metric | Control | Treatment | Relative lift | 95% CI (abs.) | p-value | Test |",
            "|---|---|---|---|---|---|---|",
        ]
        rows = list(c["metrics"].values()) + list(c["guardrails"].values())
        for m in rows:
            tag = (
                " (primary)"
                if m["metric"] == c["primary_metric"]
                else (" (guardrail)" if m["metric"] in c["guardrails"] else "")
            )
            sig = "**" if m["significant"] else ""
            lines.append(
                f"| {METRIC_LABELS.get(m['metric'], m['metric'])}{tag} | {fmt(m['metric'], m['control'])} | {fmt(m['metric'], m['treatment'])} | {sig}{pct(m['rel_lift'])}{sig} | {fmt(m['metric'], m['ci_low'])} to {fmt(m['metric'], m['ci_high'])} | {m['p_value']:.4f} | {m['method'].replace('_', ' ')} |"
            )
        rv = c["revenue"]
        lines += [
            "",
            f"Revenue robustness: bootstrap 95% CI for the RPV difference ${rv['bootstrap']['ci_low']:.2f} to ${rv['bootstrap']['ci_high']:.2f}; CUPED (pre-period revenue) θ = {rv['cuped']['theta']:.3f}, variance reduction {rv['cuped']['variance_reduction'] * 100:.0f}%, adjusted p = {rv['cuped']['p_value']:.4f}.",
        ]
        if c["power"]:
            p = c["power"]
            lines += [
                f"Power: {p['current_n_per_arm']:,} users per arm of {p['required_n_per_arm']:,} required to detect a {p['mde_rel_planned'] * 100:.0f}% relative lift at 80% power; smallest detectable lift now {p['mde_rel_at_current_n'] * 100:.1f}%; always-valid (mSPRT) p = {c['sequential'].get('always_valid_p', float('nan')):.4f}."
            ]
        lines.append("")
    return "\n".join(lines)


def offline_section() -> str:
    path = settings.artifacts_dir / "offline_eval.json"
    if not path.exists():
        return "## Offline ranking evaluation\n\nNot run yet (`make eval`).\n"
    ev = json.loads(path.read_text())
    lines = [
        "## Offline ranking evaluation (WANDS human judgments)",
        "",
        f"Protocol: {ev.get('protocol', '')}. Behavioral features frozen at {ev.get('stats_frozen_at', '')[:10]} (end of warm-up, before any test query was searched).",
        "",
    ]
    lines += [
        "| Strategy | NDCG@10 | NDCG@20 | MRR | P@10 | Recall@50 | MAP@10 | NDCG@10 lift vs A | 95% CI | Win rate |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    names = {
        "control_bm25_pop": "A · BM25 + popularity",
        "hybrid_rrf": "B · Hybrid retrieval (RRF)",
        "hybrid_ltr": "C · Hybrid + LambdaRank",
    }
    for s, m in ev["summary"].items():
        lift = m.get("ndcg@10_lift_vs_baseline")
        ci = m.get("ndcg@10_lift_ci95")
        lines.append(
            f"| {names.get(s, s)} | {m['ndcg@10']:.4f} | {m['ndcg@20']:.4f} | {m['mrr']:.4f} | {m['p@10']:.3f} | {m['recall@50']:.4f} | {m['map@10']:.4f} | {'baseline' if lift is None else f'{lift:+.4f}'} | {'' if ci is None else f'[{ci[0]:.3f}, {ci[1]:.3f}]'} | {'' if lift is None else f'{m.get("ndcg@10_win_rate", 0):.0%}'} |"
        )
    if ev.get("test_split"):
        lines += [
            "",
            f"Champion `{ev.get('ranker_version')}` on the fixed 96-query test split: "
            + ", ".join(
                f"{names.get(s, s).split(' · ')[0]} NDCG@10 {m['ndcg@10']:.4f}"
                for s, m in ev["test_split"].items()
            )
            + ".",
        ]
    return "\n".join(lines) + "\n"


async def main() -> None:
    async with SessionLocal() as db:
        keys = (await db.scalars(select(Experiment.key).order_by(Experiment.start_at))).all()
        sections = [experiment_section(await analyze(db, k)) for k in keys]
    sim = {}
    for phase in ("warmup", "experiment", "bandit"):
        p = settings.artifacts_dir / f"simulation_{phase}.json"
        if p.exists():
            sim[phase] = json.loads(p.read_text())
    head = [
        "# Experiment report",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `scripts/export_report.py` from the live analysis endpoints. Every number below is computed from the event log; nothing is typed in by hand.",
        "",
        "**What is real and what is simulated.** The catalog, queries and relevance judgments are the public WANDS dataset (Wayfair). Shopper behaviour is simulated: 20,000 personas with latent taste, a position-biased click model whose relevance signal is the WANDS grade, and cart/purchase rates calibrated to Retailrocket's real funnel. The A/B results therefore validate the *experimentation pipeline and methodology*; the real-data evidence for ranking quality is the offline evaluation at the end.",
        "",
    ]
    if sim:
        head += [
            "| Phase | Searches | Impressions | Clicks | Carts | Purchases | Revenue |",
            "|---|---|---|---|---|---|---|",
        ]
        for k, s in sim.items():
            head.append(
                f"| {k} | {s['searches']:,} | {s['impressions']:,} | {s['clicks']:,} | {s['carts']:,} | {s['purchases']:,} | ${s['revenue']:,.0f} |"
            )
        head.append("")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(head) + "\n".join(sections) + "\n" + offline_section())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
