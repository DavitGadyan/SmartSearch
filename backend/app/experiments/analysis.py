"""Experiment analysis: user-level metrics from mart_experiment_user → tests, CIs, validity checks, power, narrative."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.experiments import power as pw
from app.experiments.decision import decide
from app.experiments.stats import (
    TestResult,
    benjamini_hochberg,
    bootstrap_diff,
    cuped,
    msprt_proportions,
    ratio_metric_ztest,
    srm_check,
    two_proportion_ztest,
    welch_ttest,
)
from app.models import Experiment

METRIC_LABELS = {
    "conversion_rate": "Conversion rate (buyers / assigned users)",
    "revenue_per_visitor": "Revenue per assigned user",
    "purchases_per_visitor": "Purchases per assigned user",
    "aov": "Average order value",
    "search_ctr": "Search CTR (clicks / impressions)",
    "click_rate": "Users with ≥1 click",
    "add_to_cart_rate": "Add-to-cart rate (carts / clicks)",
    "zero_result_rate": "Zero-result rate",
    "no_click_rate": "Searchers with no click",
}
GUARDRAIL_HIGHER_IS_WORSE = {"zero_result_rate", "no_click_rate"}


def _metric(name: str, c: pd.DataFrame, t: pd.DataFrame, alpha: float) -> TestResult:
    if name == "conversion_rate":
        return two_proportion_ztest(
            int(c.converted.sum()), len(c), int(t.converted.sum()), len(t), name, alpha
        )
    if name == "click_rate":
        return two_proportion_ztest(int(c.clicked.sum()), len(c), int(t.clicked.sum()), len(t), name, alpha)
    if name == "no_click_rate":
        cs, ts_ = c[c.searches > 0], t[t.searches > 0]
        return two_proportion_ztest(
            int((cs.clicked == 0).sum()), len(cs), int((ts_.clicked == 0).sum()), len(ts_), name, alpha
        )
    if name == "revenue_per_visitor":
        return welch_ttest(c.revenue.to_numpy(), t.revenue.to_numpy(), name, alpha)
    if name == "purchases_per_visitor":
        return welch_ttest(c.purchases.to_numpy(), t.purchases.to_numpy(), name, alpha)
    if name == "aov":
        return ratio_metric_ztest(c.revenue, c.purchases, t.revenue, t.purchases, name, alpha)
    if name == "search_ctr":
        return ratio_metric_ztest(c.clicks, c.impressions, t.clicks, t.impressions, name, alpha)
    if name == "add_to_cart_rate":
        return ratio_metric_ztest(c.carts, c.clicks, t.carts, t.clicks, name, alpha)
    if name == "zero_result_rate":
        return ratio_metric_ztest(
            c.zero_result_searches, c.searches, t.zero_result_searches, t.searches, name, alpha
        )
    raise ValueError(f"unknown metric {name}")


async def load_experiment_frame(db: AsyncSession, key: str) -> pd.DataFrame:
    rows = (
        (await db.execute(text("SELECT * FROM mart_experiment_user WHERE experiment_key = :k"), {"k": key}))
        .mappings()
        .all()
    )
    return pd.DataFrame(rows)


async def load_daily(db: AsyncSession, key: str) -> list[dict]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT variant, day, new_users, searches, impressions, clicks, carts, purchases, buyers, revenue "
                    "FROM mart_experiment_daily WHERE experiment_key = :k ORDER BY day"
                ),
                {"k": key},
            )
        )
        .mappings()
        .all()
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    out = []
    for v, g in df.groupby("variant"):
        g = g.sort_values("day")
        cum_users = g.new_users.cumsum().replace(0, np.nan)
        out.append(
            {
                "variant": v,
                "days": [d.isoformat() for d in g.day],
                "cum_users": g.new_users.cumsum().tolist(),
                "cum_rpv": (g.revenue.cumsum() / cum_users).round(4).fillna(0).tolist(),
                "cum_purchases_per_user": (g.purchases.cumsum() / cum_users).round(5).fillna(0).tolist(),
                "daily_ctr": (g.clicks / g.impressions.replace(0, np.nan)).round(4).fillna(0).tolist(),
                "daily_revenue": g.revenue.round(2).tolist(),
            }
        )
    return out


async def analyze(db: AsyncSession, key: str) -> dict:
    exp = await db.scalar(select(Experiment).where(Experiment.key == key))
    if exp is None:
        raise KeyError(key)
    cfg = {"alpha": 0.05, "power": 0.8, "mde_rel": 0.05, **(exp.config or {})}
    alpha = float(cfg["alpha"])
    df = await load_experiment_frame(db, key)
    variants = [v["key"] for v in exp.variants]
    weights = {v["key"]: float(v.get("weight", 1)) for v in exp.variants}
    if df.empty:
        return {"experiment": _exp_dict(exp), "status": "no_data", "variants": variants}

    control_key = variants[0]
    counts = df.groupby("variant").size().to_dict()
    srm = srm_check({v: int(counts.get(v, 0)) for v in variants}, weights)
    c = df[df.variant == control_key]
    now = datetime.now(UTC)
    days_running = (
        max(1, ((min(exp.end_at, now) if exp.end_at else now) - exp.start_at).days) if exp.start_at else None
    )

    comparisons = []
    for vkey in variants[1:]:
        t = df[df.variant == vkey]
        metrics: dict[str, dict] = {}
        primary = _metric(exp.primary_metric, c, t, alpha)
        metrics[exp.primary_metric] = primary.to_dict()
        secondaries = [m for m in exp.secondary_metrics if m != exp.primary_metric and m in METRIC_LABELS]
        sec_results = [_metric(m, c, t, alpha) for m in secondaries]
        rejected, adj = benjamini_hochberg([r.p_value for r in sec_results], alpha)
        for r, rej, pa in zip(sec_results, rejected, adj, strict=True):
            metrics[r.metric] = r.to_dict() | {"p_value_bh": pa, "significant_bh": rej}
        guardrails = {}
        for m in exp.guardrail_metrics:
            if m in METRIC_LABELS:
                r = _metric(m, c, t, alpha)
                worse = (r.abs_diff > 0) if m in GUARDRAIL_HIGHER_IS_WORSE else (r.abs_diff < 0)
                guardrails[m] = r.to_dict() | {"breached": bool(r.significant and worse)}

        # revenue: robust CI + CUPED variance reduction using pre-period revenue
        boot = bootstrap_diff(c.revenue.to_numpy(), t.revenue.to_numpy(), "revenue_per_visitor", n_boot=4000)
        adj_c, adj_t, theta, vr = cuped(
            c.revenue.to_numpy(), c.pre_revenue.to_numpy(), t.revenue.to_numpy(), t.pre_revenue.to_numpy()
        )
        cuped_res = welch_ttest(adj_c, adj_t, "revenue_per_visitor_cuped", alpha)
        revenue_extra = {
            "bootstrap": boot.to_dict(),
            "cuped": cuped_res.to_dict() | {"theta": theta, "variance_reduction": vr},
        }

        # power / sample size for the primary metric (proportion metrics only)
        p0 = primary.control
        pwr = {}
        if primary.method == "two_proportion_ztest" and 0 < p0 < 1:
            n_req = pw.sample_size_proportion(p0, float(cfg["mde_rel"]), alpha, float(cfg["power"]))
            pwr = {
                "baseline_rate": p0,
                "mde_rel_planned": float(cfg["mde_rel"]),
                "required_n_per_arm": n_req,
                "current_n_per_arm": int(min(len(c), len(t))),
                "progress": round(min(len(c), len(t)) / n_req, 3),
                "mde_rel_at_current_n": round(
                    pw.mde_proportion(p0, int(min(len(c), len(t))), alpha, float(cfg["power"])), 4
                ),
                "achieved_power_for_observed_effect": round(
                    pw.achieved_power_proportion(p0, primary.treatment, len(c), len(t), alpha), 3
                ),
                "days_to_required_n": round(n_req / max(len(c) / days_running, 1e-9) - days_running, 1)
                if days_running
                else None,
            }
            seq = msprt_proportions(
                int(c.converted.sum()),
                len(c),
                int(t.converted.sum()),
                len(t),
                tau=max(p0 * float(cfg["mde_rel"]), 1e-4),
            )
        else:
            seq = {}

        decision = decide(exp, primary, metrics, guardrails, srm, pwr, revenue_extra, control_key, vkey)
        comparisons.append(
            {
                "control": control_key,
                "treatment": vkey,
                "n_control": int(len(c)),
                "n_treatment": int(len(t)),
                "primary_metric": exp.primary_metric,
                "metrics": metrics,
                "guardrails": guardrails,
                "revenue": revenue_extra,
                "power": pwr,
                "sequential": seq,
                "decision": decision,
            }
        )

    summary = (
        df.groupby("variant")
        .agg(
            users=("user_id", "size"),
            searchers=("searches", lambda s: int((s > 0).sum())),
            searches=("searches", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            carts=("carts", "sum"),
            purchases=("purchases", "sum"),
            buyers=("converted", "sum"),
            revenue=("revenue", "sum"),
        )
        .reset_index()
    )
    summary["conversion_rate"] = summary.buyers / summary.users
    summary["revenue_per_visitor"] = summary.revenue / summary.users
    summary["search_ctr"] = summary.clicks / summary.impressions.replace(0, np.nan)
    summary["add_to_cart_rate"] = summary.carts / summary.clicks.replace(0, np.nan)
    summary["aov"] = summary.revenue / summary.purchases.replace(0, np.nan)
    return {
        "experiment": _exp_dict(exp),
        "status": "ok",
        "days_running": days_running,
        "srm": srm,
        "variants": summary.fillna(0).round(5).to_dict(orient="records"),
        "comparisons": comparisons,
        "daily": await load_daily(db, key),
        "metric_labels": METRIC_LABELS,
        "generated_at": now.isoformat(),
    }


def _exp_dict(exp: Experiment) -> dict:
    return {
        "key": exp.key,
        "name": exp.name,
        "hypothesis": exp.hypothesis,
        "status": exp.status,
        "surface": exp.surface,
        "variants": exp.variants,
        "traffic_allocation": exp.traffic_allocation,
        "primary_metric": exp.primary_metric,
        "secondary_metrics": exp.secondary_metrics,
        "guardrail_metrics": exp.guardrail_metrics,
        "config": exp.config,
        "start_at": exp.start_at.isoformat() if exp.start_at else None,
        "end_at": exp.end_at.isoformat() if exp.end_at else None,
    }
