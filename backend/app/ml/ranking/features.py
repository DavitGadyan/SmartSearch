"""Ranking features for a (query, candidate set). Same code path for training and serving."""

import numpy as np

from app.ml.catalog_cache import CatalogCache
from app.ml.query import ClassIndex, ParsedQuery
from app.ml.retrieval.hybrid import Candidates

FEATURE_NAMES = [
    "bm25_score",
    "bm25_rr",
    "bm25_title",
    "sem_score",
    "sem_rr",
    "rrf",
    "class_sim",
    "class_exact",
    "title_overlap",
    "title_len",
    "price",
    "log_price",
    "price_z_class",
    "price_cap_ok",
    "rating",
    "log_reviews",
    "popularity",
    "ctr_30d",
    "cart_rate_30d",
    "conversion_30d",
    "log_impressions_30d",
    "in_stock",
    "is_new",
]


def build_features(pq: ParsedQuery, cand: Candidates, cache: CatalogCache, classes: ClassIndex) -> np.ndarray:
    pos = cand.positions
    n = len(pos)
    qtok = set(pq.tokens)
    names = cache.names[pos]
    overlap = np.fromiter(
        ((len(qtok & set(nm.split())) / len(qtok)) if qtok else 0.0 for nm in names),
        dtype=np.float32,
        count=n,
    )
    title_len = np.fromiter((len(nm.split()) for nm in names), dtype=np.float32, count=n)
    price = cache.price[pos]
    cap_ok = np.ones(n, np.float32)
    if pq.price_max is not None:
        cap_ok *= (price <= pq.price_max).astype(np.float32)
    if pq.price_min is not None:
        cap_ok *= (price >= pq.price_min).astype(np.float32)
    classes_of = cache.product_class[pos]
    class_exact = (classes_of == (pq.top_class or "\0")).astype(np.float32)
    st = cache.stat
    cols = [
        cand.bm25_score,
        np.where(cand.bm25_rank > 0, 1.0 / np.maximum(cand.bm25_rank, 1), 0.0),
        cache.bm25_title.scores_for(pq.text, pos),
        cand.sem_score,
        np.where(cand.sem_rank > 0, 1.0 / np.maximum(cand.sem_rank, 1), 0.0),
        cand.rrf,
        classes.sims_for_classes(pq, classes_of),
        class_exact,
        overlap,
        title_len,
        price,
        cache.log_price[pos],
        cache.price_z[pos],
        cap_ok,
        cache.rating[pos],
        cache.log_reviews[pos],
        st["popularity"][pos],
        st["ctr_30d"][pos],
        st["cart_rate_30d"][pos],
        st["conversion_30d"][pos],
        np.log1p(st["impressions_30d"][pos]),
        cache.in_stock[pos],
        cache.is_new[pos],
    ]
    X = np.column_stack(cols).astype(np.float32)
    assert X.shape[1] == len(FEATURE_NAMES)
    return X
