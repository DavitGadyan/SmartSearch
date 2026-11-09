"""Statistical tests for A/B analysis. Pure functions over summary statistics / arrays; unit-tested against scipy/statsmodels."""

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import stats


@dataclass
class TestResult:
    metric: str
    method: str
    control: float
    treatment: float
    abs_diff: float
    rel_lift: float | None
    ci_low: float
    ci_high: float
    p_value: float
    statistic: float | None
    n_control: int
    n_treatment: int
    alpha: float = 0.05
    extra: dict = field(default_factory=dict)

    @property
    def significant(self) -> bool:
        return self.p_value < self.alpha

    def to_dict(self) -> dict:
        d = asdict(self)
        d["significant"] = self.significant
        return d


def _rel(c: float, t: float) -> float | None:
    return (t - c) / c if c else None


# ---------------------------------------------------------------- proportions (conversion, CTR, cart rate)
def wilson_interval(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = stats.norm.ppf(1 - alpha / 2)
    p = x / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (centre - half, centre + half)


def two_proportion_ztest(
    x_c: int, n_c: int, x_t: int, n_t: int, metric: str = "conversion_rate", alpha: float = 0.05
) -> TestResult:
    """Pooled two-sample z-test; CI for the difference uses Newcombe's hybrid Wilson score method (robust at low rates)."""
    p_c, p_t = (x_c / n_c if n_c else 0.0), (x_t / n_t if n_t else 0.0)
    pooled = (x_c + x_t) / (n_c + n_t) if (n_c + n_t) else 0.0
    se = np.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_t)) if n_c and n_t and 0 < pooled < 1 else 0.0
    z = (p_t - p_c) / se if se else 0.0
    p = 2 * stats.norm.sf(abs(z)) if se else 1.0
    l1, u1 = wilson_interval(x_c, n_c, alpha)
    l2, u2 = wilson_interval(x_t, n_t, alpha)
    diff = p_t - p_c
    lo = diff - np.sqrt((p_c - l1) ** 2 + (u2 - p_t) ** 2)
    hi = diff + np.sqrt((u1 - p_c) ** 2 + (p_t - l2) ** 2)
    return TestResult(
        metric,
        "two_proportion_ztest",
        p_c,
        p_t,
        diff,
        _rel(p_c, p_t),
        float(lo),
        float(hi),
        float(p),
        float(z),
        n_c,
        n_t,
        alpha,
    )


# ---------------------------------------------------------------- means (revenue per visitor, AOV)
def welch_ttest(
    a: np.ndarray, b: np.ndarray, metric: str = "revenue_per_visitor", alpha: float = 0.05
) -> TestResult:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return TestResult(
            metric,
            "welch_ttest",
            float(a.mean()) if len(a) else 0,
            float(b.mean()) if len(b) else 0,
            0,
            None,
            0,
            0,
            1.0,
            None,
            len(a),
            len(b),
            alpha,
        )
    t, p = stats.ttest_ind(b, a, equal_var=False)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1)) if (va + vb) > 0 else 1
    se = np.sqrt(va + vb)
    diff = b.mean() - a.mean()
    h = stats.t.ppf(1 - alpha / 2, df) * se
    return TestResult(
        metric,
        "welch_ttest",
        float(a.mean()),
        float(b.mean()),
        float(diff),
        _rel(a.mean(), b.mean()),
        float(diff - h),
        float(diff + h),
        float(p),
        float(t),
        len(a),
        len(b),
        alpha,
        {"df": float(df)},
    )


def bootstrap_diff(
    a: np.ndarray,
    b: np.ndarray,
    metric: str = "revenue_per_visitor",
    stat=np.mean,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> TestResult:
    """Percentile bootstrap CI for stat(b) - stat(a); heavy-tailed revenue makes this safer than t-based CIs."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    sa = stat(rng.choice(a, size=(n_boot, len(a)), replace=True), axis=1)
    sb = stat(rng.choice(b, size=(n_boot, len(b)), replace=True), axis=1)
    d = sb - sa
    lo, hi = np.percentile(d, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    p = float(2 * min((d <= 0).mean(), (d >= 0).mean()))
    c, t = float(stat(a)), float(stat(b))
    rel = (d / np.where(sa == 0, np.nan, sa)) if c else None
    extra = (
        {
            "rel_lift_ci": [
                float(np.nanpercentile(rel, 100 * alpha / 2)),
                float(np.nanpercentile(rel, 100 * (1 - alpha / 2))),
            ]
        }
        if rel is not None
        else {}
    )
    return TestResult(
        metric,
        "bootstrap_percentile",
        c,
        t,
        t - c,
        _rel(c, t),
        float(lo),
        float(hi),
        min(1.0, p),
        None,
        len(a),
        len(b),
        alpha,
        extra,
    )


def ratio_metric_ztest(
    num_c: np.ndarray,
    den_c: np.ndarray,
    num_t: np.ndarray,
    den_t: np.ndarray,
    metric: str = "ctr",
    alpha: float = 0.05,
) -> TestResult:
    """Ratio-of-sums metric (CTR = Σclicks/Σimpressions, AOV = Σrevenue/Σorders) where the randomisation unit is the user.
    Variance via the delta method (Deng et al. 2018) so per-user correlation between numerator and denominator is respected."""

    def ratio_and_var(num, den):
        num, den = np.asarray(num, float), np.asarray(den, float)
        n = len(num)
        sd = den.sum()
        if n < 2 or sd == 0:
            return 0.0, 0.0
        r = num.sum() / sd
        mu_d = den.mean()
        cov = np.cov(num, den, ddof=1)
        var = (cov[0, 0] - 2 * r * cov[0, 1] + r * r * cov[1, 1]) / (n * mu_d**2)
        return float(r), float(max(var, 0.0))

    rc, vc = ratio_and_var(num_c, den_c)
    rt, vt = ratio_and_var(num_t, den_t)
    se = np.sqrt(vc + vt)
    z = (rt - rc) / se if se > 0 else 0.0
    p = 2 * stats.norm.sf(abs(z)) if se > 0 else 1.0
    h = stats.norm.ppf(1 - alpha / 2) * se
    return TestResult(
        metric,
        "delta_method_ztest",
        rc,
        rt,
        rt - rc,
        _rel(rc, rt),
        float(rt - rc - h),
        float(rt - rc + h),
        float(p),
        float(z),
        len(num_c),
        len(num_t),
        alpha,
    )


# ---------------------------------------------------------------- variance reduction
def cuped(
    y_c: np.ndarray, x_c: np.ndarray, y_t: np.ndarray, x_t: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """CUPED (Deng et al. 2013): y_adj = y - θ(x - x̄) with θ = cov(y,x)/var(x) fitted on all units.
    Returns adjusted control, adjusted treatment, θ and the fraction of variance removed."""
    y = np.concatenate([y_c, y_t]).astype(float)
    x = np.concatenate([x_c, x_t]).astype(float)
    vx = x.var()
    if vx == 0 or len(y) < 3:
        return np.asarray(y_c, float), np.asarray(y_t, float), 0.0, 0.0
    theta = float(np.cov(y, x, ddof=0)[0, 1] / vx)
    xbar = x.mean()
    adj_c = np.asarray(y_c, float) - theta * (np.asarray(x_c, float) - xbar)
    adj_t = np.asarray(y_t, float) - theta * (np.asarray(x_t, float) - xbar)
    vr = 1 - np.concatenate([adj_c, adj_t]).var() / y.var() if y.var() > 0 else 0.0
    return adj_c, adj_t, theta, float(max(vr, 0.0))


# ---------------------------------------------------------------- validity checks
def srm_check(observed: dict[str, int], expected_weights: dict[str, float], threshold: float = 0.001) -> dict:
    """Sample-ratio mismatch via chi-square goodness of fit; p < 0.001 is the conventional alarm."""
    keys = list(observed)
    obs = np.array([observed[k] for k in keys], float)
    w = np.array([expected_weights.get(k, 0) for k in keys], float)
    w = w / w.sum() if w.sum() else np.full(len(keys), 1 / len(keys))
    exp = obs.sum() * w
    chi2, p = stats.chisquare(obs, exp) if obs.sum() > 0 else (0.0, 1.0)
    return {
        "chi2": float(chi2),
        "p_value": float(p),
        "srm_detected": bool(p < threshold),
        "observed": {k: int(observed[k]) for k in keys},
        "expected": {k: float(e) for k, e in zip(keys, exp, strict=True)},
    }


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> tuple[list[bool], list[float]]:
    p = np.asarray(p_values, float)
    m = len(p)
    if m == 0:
        return [], []
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    adj_full = np.empty(m)
    adj_full[order] = np.minimum(adj, 1.0)
    return [bool(v <= alpha) for v in adj_full], [float(v) for v in adj_full]


# ---------------------------------------------------------------- sequential monitoring
def msprt_proportions(x_c: int, n_c: int, x_t: int, n_t: int, tau: float = 0.01) -> dict:
    """Always-valid p-value for a difference in proportions via the mixture SPRT (Johari, Pekelis & Walsh 2017)
    with a N(0, τ²) mixing prior on the effect. Safe to inspect continuously ("peeking")."""
    if n_c == 0 or n_t == 0:
        return {"lambda": 1.0, "always_valid_p": 1.0, "tau": tau}
    p_c, p_t = x_c / n_c, x_t / n_t
    pooled = (x_c + x_t) / (n_c + n_t)
    v = pooled * (1 - pooled) * (1 / n_c + 1 / n_t)
    if v <= 0:
        return {"lambda": 1.0, "always_valid_p": 1.0, "tau": tau}
    delta = p_t - p_c
    lam = np.sqrt(v / (v + tau**2)) * np.exp(tau**2 * delta**2 / (2 * v * (v + tau**2)))
    return {"lambda": float(lam), "always_valid_p": float(min(1.0, 1.0 / lam)), "tau": tau}
