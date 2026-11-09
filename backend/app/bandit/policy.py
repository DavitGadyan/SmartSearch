"""Contextual bandit policies. LinTS = linear Thompson sampling with a ridge-Gaussian posterior per action."""

import json
from pathlib import Path

import numpy as np

from app.bandit.context import ACTIONS, DIM


class LinTS:
    def __init__(
        self, actions: list[str] = ACTIONS, dim: int = DIM, lam: float = 1.0, v: float = 0.25, seed: int = 0
    ) -> None:
        self.actions, self.dim, self.lam, self.v = list(actions), dim, lam, v
        self.A = {a: np.eye(dim) * lam for a in self.actions}
        self.b = {a: np.zeros(dim) for a in self.actions}
        self.n = dict.fromkeys(self.actions, 0)
        self.rng = np.random.default_rng(seed)

    def _mean_cov(self, a: str) -> tuple[np.ndarray, np.ndarray]:
        A_inv = np.linalg.inv(self.A[a])
        return A_inv @ self.b[a], self.v**2 * A_inv

    def select(self, x: np.ndarray) -> tuple[str, float]:
        """Thompson draw per action; propensity ≈ Monte-Carlo frequency of the chosen arm (for off-policy logging)."""
        draws = {a: self.rng.multivariate_normal(*self._mean_cov(a)) @ x for a in self.actions}
        a = max(draws, key=draws.get)
        return a, self.action_probs(x)[a]

    def action_probs(self, x: np.ndarray, n_samples: int = 256) -> dict[str, float]:
        scores = np.column_stack(
            [self.rng.multivariate_normal(*self._mean_cov(a), size=n_samples) @ x for a in self.actions]
        )
        counts = np.bincount(scores.argmax(1), minlength=len(self.actions)) / n_samples
        return {a: float(max(c, 1e-3)) for a, c in zip(self.actions, counts, strict=True)}

    def greedy_probs(self, x: np.ndarray) -> dict[str, float]:
        means = {a: float((np.linalg.solve(self.A[a], self.b[a])) @ x) for a in self.actions}
        best = max(means, key=means.get)
        return {a: 1.0 if a == best else 0.0 for a in self.actions}

    def update(self, a: str, x: np.ndarray, r: float) -> None:
        self.A[a] += np.outer(x, x)
        self.b[a] += r * x
        self.n[a] += 1

    def to_json(self) -> dict:
        return {
            "actions": self.actions,
            "dim": self.dim,
            "lam": self.lam,
            "v": self.v,
            "A": {a: self.A[a].tolist() for a in self.actions},
            "b": {a: self.b[a].tolist() for a in self.actions},
            "n": self.n,
        }

    @classmethod
    def from_json(cls, d: dict, seed: int = 0) -> "LinTS":
        p = cls(d["actions"], d["dim"], d["lam"], d["v"], seed)
        p.A = {a: np.array(v) for a, v in d["A"].items()}
        p.b = {a: np.array(v) for a, v in d["b"].items()}
        p.n = d.get("n", p.n)
        return p

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json()))

    @classmethod
    def load(cls, path: Path) -> "LinTS":
        return cls.from_json(json.loads(path.read_text()))


class FixedPolicy:
    def __init__(self, action: str, actions: list[str] = ACTIONS) -> None:
        self.action, self.actions = action, actions

    def action_probs(self, x: np.ndarray) -> dict[str, float]:
        return {a: 1.0 if a == self.action else 0.0 for a in self.actions}


class EpsilonGreedy:
    def __init__(self, base: LinTS, eps: float = 0.1) -> None:
        self.base, self.eps = base, eps

    def action_probs(self, x: np.ndarray) -> dict[str, float]:
        g = self.base.greedy_probs(x)
        k = len(g)
        return {a: (1 - self.eps) * p + self.eps / k for a, p in g.items()}
