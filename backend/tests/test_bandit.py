import numpy as np

from app.bandit.context import ACTIONS, DIM, action_to_strategy, build_context
from app.bandit.ope import estimate
from app.bandit.policy import EpsilonGreedy, FixedPolicy, LinTS


def _logs(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    X, A, P, R = [], [], [], []
    for i in range(n):
        group = "furniture" if i % 2 else "kitchen"
        x = build_context(group, False, 2, 0, "value", "desktop")
        a = int(rng.integers(len(ACTIONS)))
        best = 3 if group == "furniture" else 0
        r = float(rng.random() < (0.2 if a == best else 0.1))
        X.append(x), A.append(a), P.append(1 / len(ACTIONS)), R.append(r)
    return np.array(X), np.array(A), np.array(P), np.array(R)


def test_context_shape_and_action_mapping():
    assert build_context("rugs", True, 3, 7, "premium", "mobile").shape == (DIM,)
    assert action_to_strategy("hybrid_ltr_personalized+explore") == ("hybrid_ltr_personalized", True)
    assert action_to_strategy("control_bm25_pop") == ("control_bm25_pop", False)


def test_lints_learns_context_dependent_best_arm():
    X, A, P, R = _logs()
    p = LinTS(seed=1)
    for x, a, r in zip(X, A, R, strict=True):
        p.update(ACTIONS[a], x, r)
    g_f = p.greedy_probs(build_context("furniture", False, 2, 0, "value", "desktop"))
    g_k = p.greedy_probs(build_context("kitchen", False, 2, 0, "value", "desktop"))
    assert max(g_f, key=g_f.get) == ACTIONS[3] and max(g_k, key=g_k.get) == ACTIONS[0]
    probs = p.action_probs(X[0])
    assert abs(sum(probs.values()) - 1) < 0.05 and all(v > 0 for v in probs.values())


def test_ope_recovers_fixed_policy_value():
    X, A, P, R = _logs(n=20000, seed=3)
    fixed = FixedPolicy(ACTIONS[3])
    est = estimate(fixed, X, A, P, R, ACTIONS, n_boot=100)
    truth = 0.5 * 0.2 + 0.5 * 0.1  # best for furniture half, baseline for kitchen half
    assert abs(est["ips"] - truth) < 0.02 and abs(est["dr"] - truth) < 0.02
    assert (
        est["ips_ci95"][0] < est["ips"] < est["ips_ci95"][1]
        and est["ips_ci95"][1] - est["ips_ci95"][0] < 0.05
    )
    eps = EpsilonGreedy(LinTS(seed=0), 0.1)
    assert abs(sum(eps.action_probs(X[0]).values()) - 1) < 1e-6
