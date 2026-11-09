import numpy as np
import pytest
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_ztest

from app.experiments import power as pw
from app.experiments.stats import (
    benjamini_hochberg,
    bootstrap_diff,
    cuped,
    msprt_proportions,
    ratio_metric_ztest,
    srm_check,
    two_proportion_ztest,
    welch_ttest,
)


def test_two_proportion_ztest_matches_statsmodels():
    r = two_proportion_ztest(3000, 100_000, 3180, 100_000)
    z, p = proportions_ztest([3180, 3000], [100_000, 100_000])
    assert r.statistic == pytest.approx(z, rel=1e-9)
    assert r.p_value == pytest.approx(p, rel=1e-9)
    assert r.ci_low < r.abs_diff < r.ci_high
    assert r.rel_lift == pytest.approx(0.06)
    assert r.significant


def test_two_proportion_ztest_null_not_significant():
    r = two_proportion_ztest(500, 10_000, 505, 10_000)
    assert not r.significant and r.ci_low < 0 < r.ci_high


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.exponential(8.5, 5000), rng.exponential(9.0, 5000)
    r = welch_ttest(a, b)
    t, p = sps.ttest_ind(b, a, equal_var=False)
    assert r.statistic == pytest.approx(t) and r.p_value == pytest.approx(p)
    assert r.ci_low < (b.mean() - a.mean()) < r.ci_high


def test_bootstrap_ci_covers_true_difference():
    rng = np.random.default_rng(2)
    a = np.where(rng.random(20_000) < 0.03, rng.lognormal(4.5, 0.6, 20_000), 0.0)
    b = np.where(rng.random(20_000) < 0.034, rng.lognormal(4.5, 0.6, 20_000), 0.0)
    r = bootstrap_diff(a, b, n_boot=2000)
    assert r.ci_low < (b.mean() - a.mean()) < r.ci_high
    assert 0 <= r.p_value <= 1


def test_cuped_reduces_variance_and_keeps_means():
    rng = np.random.default_rng(3)
    x_c, x_t = rng.gamma(2, 5, 10_000), rng.gamma(2, 5, 10_000)
    y_c = 0.8 * x_c + rng.normal(0, 3, 10_000)
    y_t = 0.8 * x_t + rng.normal(0, 3, 10_000) + 0.5
    adj_c, adj_t, theta, vr = cuped(y_c, x_c, y_t, x_t)
    assert 0.6 < theta < 1.0 and vr > 0.4
    assert (adj_t.mean() - adj_c.mean()) == pytest.approx(0.5, abs=0.15)
    assert np.concatenate([adj_c, adj_t]).var() < np.concatenate([y_c, y_t]).var()


def test_srm_detects_imbalance_and_passes_balance():
    assert srm_check({"a": 55_000, "b": 45_000}, {"a": 0.5, "b": 0.5})["srm_detected"]
    assert not srm_check({"a": 50_100, "b": 49_900}, {"a": 0.5, "b": 0.5})["srm_detected"]


def test_benjamini_hochberg_matches_statsmodels():
    p = [0.001, 0.02, 0.04, 0.2, 0.5]
    rej, adj = benjamini_hochberg(p, 0.05)
    sm_rej, sm_adj, *_ = multipletests(p, alpha=0.05, method="fdr_bh")
    assert rej == list(sm_rej) and np.allclose(adj, sm_adj)


def test_ratio_metric_reduces_to_proportion_test_when_denominator_is_one():
    rng = np.random.default_rng(4)
    c, t = (rng.random(20_000) < 0.03).astype(float), (rng.random(20_000) < 0.033).astype(float)
    r = ratio_metric_ztest(c, np.ones_like(c), t, np.ones_like(t))
    z, p = proportions_ztest([t.sum(), c.sum()], [len(t), len(c)])
    assert r.control == pytest.approx(c.mean()) and r.treatment == pytest.approx(t.mean())
    assert r.p_value == pytest.approx(p, abs=0.01)


def test_msprt_is_valid_and_monotone_in_effect():
    small = msprt_proportions(3000, 100_000, 3050, 100_000, tau=0.002)
    large = msprt_proportions(3000, 100_000, 3400, 100_000, tau=0.002)
    assert 0 < large["always_valid_p"] < small["always_valid_p"] <= 1


def test_sample_size_close_to_statsmodels():
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    n = pw.sample_size_proportion(0.03, 0.10, alpha=0.05, power=0.8)
    es = proportion_effectsize(0.033, 0.03)
    n_sm = NormalIndPower().solve_power(effect_size=es, alpha=0.05, power=0.8, ratio=1.0)
    assert n == pytest.approx(n_sm, rel=0.05)
    assert 0.09 < pw.mde_proportion(0.03, n) < 0.11
    assert pw.achieved_power_proportion(0.03, 0.033, n, n) == pytest.approx(0.8, abs=0.03)
