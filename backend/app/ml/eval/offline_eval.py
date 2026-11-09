"""Offline evaluation of ranking strategies on WANDS human relevance judgments."""

from collections import defaultdict

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ml.catalog_cache import STAT_COLS, CatalogCache
from app.ml.eval.metrics import evaluate_ranking
from app.ml.query import ClassIndex, parse_query
from app.ml.ranking.features import build_features
from app.ml.ranking.ltr import Ranker
from app.ml.ranking.strategies import rank, retrieve_hybrid
from app.ml.retrieval.embedder import Embedder

STRATEGIES_DEFAULT = ("control_bm25_pop", "hybrid_rrf", "hybrid_ltr")


async def load_judgments(engine: AsyncEngine) -> tuple[list[dict], dict[int, dict[int, int]]]:
    """Returns (queries[{id,text,split,query_class,popularity_weight}], labels{query_id: {product_id: grade}})."""
    async with engine.connect() as conn:
        queries = [
            dict(r)
            for r in (
                await conn.execute(
                    text("SELECT id, text, split, query_class, popularity_weight FROM queries ORDER BY id")
                )
            ).mappings()
        ]
        labels: dict[int, dict[int, int]] = defaultdict(dict)
        for qid, pid, g in (
            await conn.execute(text("SELECT query_id, product_id, grade FROM relevance_labels"))
        ).all():
            labels[qid][pid] = g
    return queries, labels


def grades_for(cache: CatalogCache, positions: np.ndarray, qlabels: dict[int, int]) -> np.ndarray:
    return np.array([qlabels.get(int(cache.ids[p]), 0) for p in positions], dtype=np.int8)


def prepare(
    queries: list[dict], labels, cache: CatalogCache, classes: ClassIndex, embedder: Embedder, top_k: int
):
    """Parse + retrieve + featurize every query once; reused across folds and strategies."""
    out = []
    for q in queries:
        qlabels = labels.get(q["id"], {})
        if not any(g > 0 for g in qlabels.values()):
            continue
        pq = parse_query(q["text"])
        qvec = embedder.encode_one(pq.text)
        classes.annotate(pq, qvec)
        cand = retrieve_hybrid(pq, qvec, cache, top_k)
        if len(cand) == 0:
            continue
        X = build_features(pq, cand, cache, classes)
        y = grades_for(cache, cand.positions, qlabels)
        out.append({"q": q, "pq": pq, "qvec": qvec, "cand": cand, "X": X, "y": y, "labels": qlabels})
    return out


def _summarise(per_query: list[dict], strategies: tuple[str, ...]) -> dict:
    summary: dict[str, dict] = {}
    for s in strategies:
        rows = [r for r in per_query if r["strategy"] == s]
        if not rows:
            continue
        keys = [k for k in rows[0] if k not in ("query_id", "query", "split", "strategy", "fold")]
        summary[s] = {k: round(float(np.mean([r[k] for r in rows])), 4) for k in keys} | {
            "n_queries": len(rows)
        }
    base = strategies[0]
    base_map = {r["query_id"]: r["ndcg@10"] for r in per_query if r["strategy"] == base}
    rng = np.random.default_rng(0)
    for s in strategies[1:]:
        diffs = np.array(
            [
                r["ndcg@10"] - base_map[r["query_id"]]
                for r in per_query
                if r["strategy"] == s and r["query_id"] in base_map
            ]
        )
        if len(diffs):
            boots = rng.choice(diffs, size=(2000, len(diffs)), replace=True).mean(axis=1)
            summary[s]["ndcg@10_lift_vs_baseline"] = round(float(diffs.mean()), 4)
            summary[s]["ndcg@10_lift_ci95"] = [
                round(float(np.percentile(boots, 2.5)), 4),
                round(float(np.percentile(boots, 97.5)), 4),
            ]
            summary[s]["ndcg@10_win_rate"] = round(float((diffs > 0).mean()), 3)
            summary[s]["ndcg@10_paired_p"] = round(
                float(2 * min((boots <= 0).mean(), (boots >= 0).mean())), 4
            )
    return {"summary": summary, "per_query": per_query, "baseline": base}


def evaluate_strategies(
    cache: CatalogCache,
    classes: ClassIndex,
    embedder: Embedder,
    ranker: Ranker | None,
    queries: list[dict],
    labels: dict[int, dict[int, int]],
    strategies: tuple[str, ...] = STRATEGIES_DEFAULT,
    top_k: int = 200,
) -> dict:
    per_query: list[dict] = []
    for q in queries:
        qlabels = labels.get(q["id"], {})
        if not any(g > 0 for g in qlabels.values()):
            continue
        all_grades = np.array(list(qlabels.values()), dtype=np.int8)
        pq = parse_query(q["text"])
        qvec = embedder.encode_one(pq.text)
        classes.annotate(pq, qvec)
        for s in strategies:
            res = rank(s, pq, qvec, cache, classes, ranker, None, top_k)
            m = evaluate_ranking(grades_for(cache, res.positions, qlabels), all_grades)
            per_query.append(
                {"query_id": q["id"], "query": q["text"], "split": q["split"], "strategy": s, **m}
            )
    return _summarise(per_query, strategies)


def cross_validate(
    cache: CatalogCache,
    classes: ClassIndex,
    embedder: Embedder,
    queries: list[dict],
    labels: dict[int, dict[int, int]],
    k: int = 5,
    params: dict | None = None,
    num_rounds: int = 300,
    strategies: tuple[str, ...] = STRATEGIES_DEFAULT,
    top_k: int = 200,
    seed: int = 42,
    behavioral: bool = True,
) -> dict:
    """k-fold CV: train the ranker on k-1 folds (fixed rounds, no peeking), score the held-out fold with every strategy.
    behavioral=False zeroes every behavioral feature → a content-only ranker that no warm-up click can leak into."""
    saved = None
    if not behavioral:
        saved = cache.stats
        cache.stats = cache.stats.copy()
        for c in STAT_COLS:
            cache.stats[c] = 0.0
        cache.refresh_stat_arrays()
    data = prepare(queries, labels, cache, classes, embedder, top_k)
    rng = np.random.default_rng(seed)
    folds = rng.permutation(len(data)) % k
    per_query: list[dict] = []
    for f in range(k):
        tr = [d for d, ff in zip(data, folds, strict=True) if ff != f and d["y"].max() > 0]
        te = [d for d, ff in zip(data, folds, strict=True) if ff == f]
        X = np.vstack([d["X"] for d in tr])
        y = np.concatenate([d["y"] for d in tr])
        g = np.array([len(d["y"]) for d in tr])
        ranker = Ranker.fit(X, y, g, params=params, num_rounds=num_rounds, version=f"cv{f}")
        for d in te:
            all_grades = np.array(list(d["labels"].values()), dtype=np.int8)
            for s in strategies:
                res = rank(s, d["pq"], d["qvec"], cache, classes, ranker, None, top_k)
                m = evaluate_ranking(grades_for(cache, res.positions, d["labels"]), all_grades)
                per_query.append(
                    {
                        "query_id": d["q"]["id"],
                        "query": d["q"]["text"],
                        "split": d["q"]["split"],
                        "fold": f,
                        "strategy": s,
                        **m,
                    }
                )
    if saved is not None:
        cache.stats = saved
        cache.refresh_stat_arrays()
    out = _summarise(per_query, strategies)
    out["protocol"] = (
        f"{k}-fold cross-validation over {len(data)} judged queries, ranker retrained per fold ({num_rounds} rounds), "
        + (
            "content + behavioral features"
            if behavioral
            else "content features only (behavioral features zeroed)"
        )
    )
    return out
