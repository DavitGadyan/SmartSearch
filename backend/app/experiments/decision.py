"""Turn test results into a recommendation + plain-language narrative. Everything is computed from the data."""

from app.experiments.stats import TestResult


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:+.{digits}f}%"


def _fmt(metric: str, v: float) -> str:
    if metric in ("revenue_per_visitor", "aov", "revenue_per_visitor_cuped"):
        return f"${v:,.2f}"
    if metric == "purchases_per_visitor":
        return f"{v:.4f}"
    return f"{v * 100:.2f}%"


def decide(
    exp,
    primary: TestResult,
    metrics: dict,
    guardrails: dict,
    srm: dict,
    power: dict,
    revenue: dict,
    control: str,
    treatment: str,
) -> dict:
    alpha = primary.alpha
    breached = [m for m, g in guardrails.items() if g.get("breached")]
    lines = []
    name = exp.primary_metric.replace("_", " ")
    lines.append(
        f"{treatment} vs {control}: {name} {_fmt(primary.metric, primary.control)} → {_fmt(primary.metric, primary.treatment)} "
        f"({_pct(primary.rel_lift)} relative; 95% CI for the absolute difference {_fmt(primary.metric, primary.ci_low)} to {_fmt(primary.metric, primary.ci_high)}; p = {primary.p_value:.4f})."
    )
    rpv = metrics.get("revenue_per_visitor")
    if rpv:
        boot = revenue["bootstrap"]
        cu = revenue["cuped"]
        lines.append(
            f"Revenue per visitor ${rpv['control']:.2f} → ${rpv['treatment']:.2f} ({_pct(rpv['rel_lift'])}; Welch p = {rpv['p_value']:.4f}; "
            f"bootstrap 95% CI ${boot['ci_low']:.2f} to ${boot['ci_high']:.2f}). CUPED with pre-period revenue removed "
            f"{cu['variance_reduction'] * 100:.0f}% of variance (adjusted p = {cu['p_value']:.4f})."
        )
    if srm["srm_detected"]:
        lines.append(
            f"⚠ Sample ratio mismatch: observed split {srm['observed']} vs expected {{k: round(v) for k, v in srm['expected'].items()}} (χ² p = {srm['p_value']:.2e}). Results are not trustworthy until the assignment pipeline is fixed."
        )
        rec, label = "investigate", "Invalid: sample ratio mismatch"
    elif primary.significant and primary.abs_diff > 0 and not breached:
        rec, label = "ship", "Ship treatment"
        lines.append("Primary metric improved significantly and no guardrail degraded significantly.")
    elif primary.significant and primary.abs_diff < 0:
        rec, label = "reject", "Reject treatment"
        lines.append("Primary metric degraded significantly.")
    elif primary.significant and breached:
        rec, label = "iterate", "Primary up, guardrail breached"
        lines.append(
            f"Primary metric improved but guardrail(s) degraded significantly: {', '.join(breached)}."
        )
    else:
        prog = power.get("progress")
        if prog is not None and prog < 1:
            rec, label = "continue", "Inconclusive, keep running"
            lines.append(
                f"Not significant at alpha = {alpha}. The test has {power['current_n_per_arm']:,} users per arm vs {power['required_n_per_arm']:,} required to detect "
                f"a {power['mde_rel_planned'] * 100:.0f}% relative lift with {int(0.8 * 100)}% power; the smallest effect detectable right now is "
                f"{power['mde_rel_at_current_n'] * 100:.1f}%. Estimated {power['days_to_required_n']} more days at current traffic."
            )
        else:
            rec, label = "reject", "No detectable effect"
            lines.append(
                f"Not significant at α = {alpha} with adequate power - the treatment most likely has no effect of the planned size ({_pct(power.get('mde_rel_planned'), 0)})."
            )
    if breached and rec == "ship":
        rec = "iterate"
    return {
        "recommendation": rec,
        "label": label,
        "guardrails_breached": breached,
        "narrative": " ".join(lines),
    }
