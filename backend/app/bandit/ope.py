"""Off-policy evaluation of a target policy from logged (context, action, propensity, reward) tuples:
IPS, self-normalised IPS, and doubly robust (ridge reward model per action). Bootstrap CIs over users/rows."""

import numpy as np


def _target_probs(policy, X: np.ndarray, actions: list[str]) -> np.ndarray:
    return np.array([[policy.action_probs(x)[a] for a in actions] for x in X])


def fit_reward_models(
    X: np.ndarray, a_idx: np.ndarray, r: np.ndarray, n_actions: int, lam: float = 1.0
) -> list[np.ndarray]:
    d = X.shape[1]
    models = []
    for k in range(n_actions):
        m = a_idx == k
        if m.sum() < 5:
            models.append(np.zeros(d))
            continue
        Xa, ra = X[m], r[m]
        models.append(np.linalg.solve(Xa.T @ Xa + lam * np.eye(d), Xa.T @ ra))
    return models


def estimate(
    policy,
    X: np.ndarray,
    a_idx: np.ndarray,
    p_log: np.ndarray,
    r: np.ndarray,
    actions: list[str],
    reward_models=None,
    n_boot: int = 400,
    seed: int = 0,
) -> dict:
    pi = _target_probs(policy, X, actions)  # (n, K)
    pi_a = pi[np.arange(len(X)), a_idx]
    w = pi_a / np.clip(p_log, 1e-3, None)
    w = np.minimum(w, 50.0)  # clip extreme weights
    ips = w * r
    snips_den = w.mean() or 1.0
    if reward_models is None:
        reward_models = fit_reward_models(X, a_idx, r, len(actions))
    q = np.column_stack([X @ reward_models[k] for k in range(len(actions))])  # (n, K) predicted rewards
    dm = (pi * q).sum(1)
    q_a = q[np.arange(len(X)), a_idx]
    dr = dm + w * (r - q_a)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(X), size=(n_boot, len(X)))
    boots = {
        "ips": ips[idx].mean(1),
        "snips": (ips[idx].sum(1) / np.clip(w[idx].sum(1), 1e-9, None)),
        "dr": dr[idx].mean(1),
    }
    out = {
        "ips": float(ips.mean()),
        "snips": float(ips.sum() / (w.sum() or 1)),
        "dm": float(dm.mean()),
        "dr": float(dr.mean()),
        "ess": float(w.sum() ** 2 / ((w**2).sum() or 1)),
        "mean_weight": float(w.mean()),
    }
    for k, b in boots.items():
        out[f"{k}_ci95"] = [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
    out["action_share"] = {a: float(pi[:, i].mean()) for i, a in enumerate(actions)}
    del snips_den
    return out
