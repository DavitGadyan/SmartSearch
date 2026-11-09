"""How good is the relevance judge? Grade a stratified sample of WANDS-labelled (query, product) pairs with the
configured decision backend (Microsoft-Decision-1 or the local similarity fallback) and compare to the human grade."""

import asyncio
import json
import sys
import time
from collections import defaultdict

import numpy as np
from scipy import stats
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.decision.client import backend_name
from app.decision.policies import GRADES, grade_relevance
from app.ml.catalog_cache import load_catalog
from app.ml.retrieval.embedder import get_embedder

PER_GRADE = 100
BATCH = 6


async def main() -> None:
    t0 = time.perf_counter()
    cache = await load_catalog(engine)
    emb = get_embedder()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
            WITH s AS (SELECT l.query_id, l.product_id, l.grade, row_number() OVER (PARTITION BY l.grade ORDER BY md5(l.id::text)) AS rn
                       FROM relevance_labels l)
            SELECT s.grade, q.text AS query, s.product_id FROM s JOIN queries q ON q.id = s.query_id WHERE s.rn <= :n ORDER BY q.text
            """
                ),
                {"n": PER_GRADE},
            )
        ).all()
    by_query: dict[str, list] = defaultdict(list)
    for g, q, pid in rows:
        by_query[q].append((int(pid), int(g)))
    y_true, y_exp, y_pred = [], [], []
    for q, pairs in by_query.items():
        qvec = emb.encode_one(q)
        for i in range(0, len(pairs), BATCH):
            chunk = pairs[i : i + BATCH]
            prods = [cache.record(cache.id_to_pos[pid]) for pid, _ in chunk]
            sims = np.array([float(cache.emb[cache.id_to_pos[pid]] @ qvec) for pid, _ in chunk])
            judged = await grade_relevance(q, prods, cache, sims)
            for (_, g), j in zip(chunk, judged, strict=True):
                y_true.append(g)
                y_exp.append(j["expected_grade"])
                probs = [1 - j["p_irrelevant"] - j["p_exact"], 0, j["p_exact"]]
                probs[1] = max(0.0, 1 - j["p_irrelevant"] - j["p_exact"])
                probs[0] = j["p_irrelevant"]
                y_pred.append(int(np.argmax(probs)))
    y_true, y_exp, y_pred = np.array(y_true), np.array(y_exp), np.array(y_pred)
    conf = [[int(((y_true == t) & (y_pred == p)).sum()) for p in range(3)] for t in range(3)]
    out = {
        "backend": backend_name(),
        "model": settings.decision_model if backend_name() != "local" else "semantic-similarity fallback",
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()),
        "mae_expected_grade": float(np.abs(y_true - y_exp).mean()),
        "spearman": float(stats.spearmanr(y_true, y_exp).statistic),
        "exact_recall": float(((y_true == 2) & (y_pred == 2)).sum() / max((y_true == 2).sum(), 1)),
        "confusion": conf,
        "grades": GRADES,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    (settings.artifacts_dir / "decision_eval.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
