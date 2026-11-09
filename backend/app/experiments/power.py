"""Sample size, minimum detectable effect, achieved power and duration estimates (normal approximation)."""

import math

from scipy import stats


def _z(alpha: float, power: float, two_sided: bool = True) -> tuple[float, float]:
    return stats.norm.ppf(1 - alpha / (2 if two_sided else 1)), stats.norm.ppf(power)


def sample_size_proportion(
    p0: float, mde_rel: float, alpha: float = 0.05, power: float = 0.8, two_sided: bool = True
) -> int:
    """Per-arm sample size to detect a relative lift `mde_rel` on baseline rate p0 (pooled-variance formula)."""
    p1 = p0 * (1 + mde_rel)
    za, zb = _z(alpha, power, two_sided)
    pbar = (p0 + p1) / 2
    n = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2 / (
        p1 - p0
    ) ** 2
    return int(math.ceil(n))


def sample_size_mean(
    sd: float, mde_abs: float, alpha: float = 0.05, power: float = 0.8, two_sided: bool = True
) -> int:
    za, zb = _z(alpha, power, two_sided)
    return int(math.ceil(2 * ((za + zb) * sd / mde_abs) ** 2))


def mde_proportion(
    p0: float, n_per_arm: int, alpha: float = 0.05, power: float = 0.8, two_sided: bool = True
) -> float:
    """Smallest relative lift detectable with n per arm (inverts the pooled formula approximately)."""
    za, zb = _z(alpha, power, two_sided)
    abs_mde = (za + zb) * math.sqrt(2 * p0 * (1 - p0) / n_per_arm)
    return abs_mde / p0 if p0 else float("inf")


def achieved_power_proportion(
    p0: float, p1: float, n_c: int, n_t: int, alpha: float = 0.05, two_sided: bool = True
) -> float:
    if n_c == 0 or n_t == 0 or p0 == p1:
        return alpha if p0 == p1 else 0.0
    za, _ = _z(alpha, 0.8, two_sided)
    se = math.sqrt(p0 * (1 - p0) / n_c + p1 * (1 - p1) / n_t)
    z_eff = abs(p1 - p0) / se
    return float(stats.norm.cdf(z_eff - za) + (stats.norm.cdf(-z_eff - za) if two_sided else 0.0))


def achieved_power_mean(
    diff: float, sd_c: float, sd_t: float, n_c: int, n_t: int, alpha: float = 0.05
) -> float:
    if n_c == 0 or n_t == 0:
        return 0.0
    se = math.sqrt(sd_c**2 / n_c + sd_t**2 / n_t)
    if se == 0:
        return 1.0 if diff else alpha
    za = stats.norm.ppf(1 - alpha / 2)
    z_eff = abs(diff) / se
    return float(stats.norm.cdf(z_eff - za) + stats.norm.cdf(-z_eff - za))


def duration_days(
    n_per_arm: int, daily_eligible_users: float, allocation: float = 1.0, n_variants: int = 2
) -> float:
    if daily_eligible_users <= 0:
        return float("inf")
    return n_per_arm * n_variants / (daily_eligible_users * allocation)
