"""Why did this product rank here? Per-item feature contributions from the ranker + personalisation term."""

import numpy as np

from app.ml.ranking.features import FEATURE_NAMES
from app.ml.ranking.ltr import Ranker
from app.ml.ranking.strategies import PERSONALIZATION_WEIGHT, RankedResult

LABELS = {
    "bm25_score": "Keyword match (BM25)",
    "bm25_rr": "Keyword rank",
    "bm25_title": "Keyword match in title",
    "sem_score": "Semantic similarity",
    "sem_rr": "Semantic rank",
    "rrf": "Fused retrieval rank",
    "class_sim": "Category intent match",
    "class_exact": "Exact category intent",
    "title_overlap": "Query terms in title",
    "title_len": "Title length",
    "price": "Price",
    "log_price": "Price (log)",
    "price_z_class": "Price vs. category",
    "price_cap_ok": "Within price constraint",
    "rating": "Customer rating",
    "log_reviews": "Review volume",
    "popularity": "Popularity",
    "ctr_30d": "Click-through rate (30d)",
    "cart_rate_30d": "Add-to-cart rate (30d)",
    "conversion_30d": "Conversion rate (30d)",
    "log_impressions_30d": "Impression volume (30d)",
    "in_stock": "In stock",
    "is_new": "New arrival",
}


def explain(res: RankedResult, ranker: Ranker | None, top_n: int = 24, per_item: int = 5) -> list[dict]:
    """Explanations for the first `top_n` ranked items, in display order."""
    if res.candidates is None or res.features is None:
        return [
            {"strategy": res.strategy, "note": "control strategy: BM25 keyword score + popularity"}
            for _ in res.positions[:top_n]
        ]
    cand_pos = {int(p): i for i, p in enumerate(res.candidates.positions)}
    contrib = (
        ranker.contributions(res.features) if (ranker is not None and res.ltr_scores is not None) else None
    )
    out = []
    for p in res.positions[:top_n]:
        i = cand_pos[int(p)]
        item = {
            "strategy": res.strategy,
            "retrieved_by": [
                s
                for s, r in (("bm25", res.candidates.bm25_rank[i]), ("semantic", res.candidates.sem_rank[i]))
                if r > 0
            ],
            "bm25_rank": int(res.candidates.bm25_rank[i]) or None,
            "semantic_rank": int(res.candidates.sem_rank[i]) or None,
            "ltr_score": None if res.ltr_scores is None else round(float(res.ltr_scores[i]), 4),
            "personal_boost": None
            if res.personal_boost is None
            else round(float(PERSONALIZATION_WEIGHT * res.personal_boost[i]), 4),
            "explored": res.explored_position is not None and int(p) == res.explored_position,
            "factors": [],
        }
        if contrib is not None:
            c = contrib[i][:-1]
            top = np.argsort(-np.abs(c))[:per_item]
            item["factors"] = [
                {
                    "feature": FEATURE_NAMES[j],
                    "label": LABELS[FEATURE_NAMES[j]],
                    "value": round(float(res.features[i, j]), 4),
                    "contribution": round(float(c[j]), 4),
                }
                for j in top
                if abs(c[j]) > 1e-6
            ]
        out.append(item)
    return out
