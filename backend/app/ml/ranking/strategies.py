"""Ranking strategies = the arms of our experiments."""

from dataclasses import dataclass, field

import numpy as np

from app.ml.catalog_cache import CatalogCache
from app.ml.query import ClassIndex, ParsedQuery
from app.ml.ranking.features import build_features
from app.ml.ranking.ltr import Ranker
from app.ml.recs.cold_start import apply_exploration_slot
from app.ml.retrieval.hybrid import Candidates, rrf_fuse

STRATEGIES = ("control_bm25_pop", "hybrid_rrf", "hybrid_ltr", "hybrid_ltr_personalized")
PERSONALIZATION_WEIGHT = 0.6
OUT_OF_STOCK_PENALTY = 3.0


@dataclass
class UserProfile:
    """Affinity weights in [0,1] per attribute value, plus a log-price preference. Empty profile = no boost."""

    brand: dict[str, float] = field(default_factory=dict)
    product_class: dict[str, float] = field(default_factory=dict)
    style: dict[str, float] = field(default_factory=dict)
    material: dict[str, float] = field(default_factory=dict)
    color: dict[str, float] = field(default_factory=dict)
    log_price_mean: float | None = None
    log_price_sd: float = 0.6
    n_events: int = 0

    def is_empty(self) -> bool:
        return self.n_events == 0


@dataclass
class RankedResult:
    positions: np.ndarray  # catalog positions in final order
    scores: np.ndarray
    strategy: str
    candidates: Candidates | None
    features: np.ndarray | None  # aligned with candidates.positions (pre-sort)
    ltr_scores: np.ndarray | None  # aligned with candidates.positions
    personal_boost: np.ndarray | None  # aligned with candidates.positions
    explored_position: int | None = None
    retrieval: dict = field(default_factory=dict)


def retrieve_hybrid(pq: ParsedQuery, qvec: np.ndarray, cache: CatalogCache, top_k: int) -> Candidates:
    b_idx, b_sc = cache.bm25.search(pq.text, top_k)
    s_idx, s_sc = cache.semantic.search(qvec, top_k)
    return rrf_fuse(b_idx, b_sc, s_idx, s_sc, lambda p: cache.semantic.sims_for(qvec, p))


def affinity_boost(profile: UserProfile, pos: np.ndarray, cache: CatalogCache) -> np.ndarray:
    """Explicit, inspectable personalisation term in [-1, 1]."""
    if profile.is_empty():
        return np.zeros(len(pos), np.float32)
    parts = []
    for weights, values in (
        (profile.brand, cache.brand[pos]),
        (profile.product_class, cache.product_class[pos]),
        (profile.style, cache.style[pos]),
        (profile.material, cache.material[pos]),
        (profile.color, cache.color[pos]),
    ):
        if weights:
            parts.append(np.fromiter((weights.get(v, 0.0) for v in values), dtype=np.float32, count=len(pos)))
    aff = np.mean(parts, axis=0) if parts else np.zeros(len(pos), np.float32)
    if profile.log_price_mean is not None:
        z = (cache.log_price[pos] - profile.log_price_mean) / max(profile.log_price_sd, 0.2)
        aff = aff + 0.5 * (np.exp(-0.5 * z * z) - 0.5)  # price fit in [-0.25, 0.25]
    return np.clip(aff, -1, 1).astype(np.float32)


def _zscore(x: np.ndarray) -> np.ndarray:
    if len(x) < 2:
        return np.zeros_like(x)
    sd = float(x.std()) or 1.0
    return ((x - x.mean()) / sd).astype(np.float32)


def rank(
    strategy: str,
    pq: ParsedQuery,
    qvec: np.ndarray,
    cache: CatalogCache,
    classes: ClassIndex,
    ranker: Ranker | None,
    profile: UserProfile | None = None,
    top_k: int = 200,
    explore: bool = False,
    rng: np.random.Generator | None = None,
) -> RankedResult:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")

    if strategy == "control_bm25_pop":
        idx, sc = cache.bm25.search(pq.text, top_k)
        if len(idx) == 0:
            return RankedResult(idx, sc, strategy, None, None, None, None, retrieval={"bm25": 0})
        pop = cache.popularity[idx]
        score = sc / (sc.max() or 1.0) + 0.5 * pop / (pop.max() or 1.0)
        score -= OUT_OF_STOCK_PENALTY * (1 - cache.in_stock[idx])
        order = np.argsort(-score, kind="stable")
        res = RankedResult(
            idx[order],
            score[order].astype(np.float32),
            strategy,
            None,
            None,
            None,
            None,
            retrieval={"bm25": len(idx)},
        )
    else:
        cand = retrieve_hybrid(pq, qvec, cache, top_k)
        if len(cand) == 0:
            return RankedResult(
                cand.positions, cand.rrf, strategy, cand, None, None, None, retrieval=cand.sources
            )
        X = build_features(pq, cand, cache, classes)
        if strategy == "hybrid_rrf" or ranker is None:
            base = _zscore(cand.rrf)
            ltr = None
        else:
            ltr = ranker.predict(X)
            base = _zscore(ltr)
        boost = None
        score = base.copy()
        if strategy == "hybrid_ltr_personalized":
            boost = affinity_boost(profile or UserProfile(), cand.positions, cache)
            score = score + PERSONALIZATION_WEIGHT * boost
        score -= OUT_OF_STOCK_PENALTY * (1 - cache.in_stock[cand.positions])
        if pq.price_max is not None:
            score -= 1.5 * (cache.price[cand.positions] > pq.price_max)
        order = np.argsort(-score, kind="stable")
        res = RankedResult(
            cand.positions[order],
            score[order].astype(np.float32),
            strategy,
            cand,
            X,
            ltr,
            boost,
            retrieval=cand.sources,
        )

    if explore and rng is not None:
        res.positions, res.scores, res.explored_position = apply_exploration_slot(
            res.positions, res.scores, cache, rng
        )
    return res
