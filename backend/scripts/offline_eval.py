"""Offline ranking evaluation on WANDS judgments → artifacts/offline_eval.json (console Ranking page)."""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.ml.catalog_cache import load_catalog
from app.ml.eval.freeze import freeze_warmup_stats
from app.ml.eval.offline_eval import cross_validate, evaluate_strategies, load_judgments
from app.ml.query import ClassIndex
from app.ml.ranking.features import FEATURE_NAMES
from app.ml.ranking.ltr import Ranker
from app.ml.retrieval.embedder import get_embedder
from app.models import RankingModel


def table(title: str, summary: dict, baseline: str) -> None:
    print(f"\n{title}")
    print(
        f"{'strategy':24s} {'ndcg@10':>8s} {'ndcg@20':>8s} {'mrr':>7s} {'p@10':>6s} {'recall@50':>9s} {'map@10':>7s}  lift(ndcg@10) 95% CI"
    )
    for s, m in summary.items():
        lift = (
            "baseline"
            if s == baseline
            else f"{m['ndcg@10_lift_vs_baseline']:+.4f} {m['ndcg@10_lift_ci95']}  win-rate {m['ndcg@10_win_rate']:.0%}"
        )
        print(
            f"{s:24s} {m['ndcg@10']:8.4f} {m['ndcg@20']:8.4f} {m['mrr']:7.4f} {m['p@10']:6.3f} {m['recall@50']:9.4f} {m['map@10']:7.4f}  {lift}"
        )


async def main() -> None:
    cache = await load_catalog(engine)
    cutoff = await freeze_warmup_stats(engine, cache)
    embedder = get_embedder()
    classes = ClassIndex(cache.class_names, embedder)
    queries, labels = await load_judgments(engine)
    async with SessionLocal() as db:
        champ = await db.scalar(select(RankingModel).where(RankingModel.is_champion.is_(True)))
    ranker = None
    if champ and Path(champ.artifact_path).exists() and list(champ.feature_names or []) == FEATURE_NAMES:
        ranker = Ranker.load(Path(champ.artifact_path), champ.version)

    cv = cross_validate(cache, classes, embedder, queries, labels, k=5, behavioral=False)
    table(f"5-fold CV, clean: {cv['protocol']}", cv["summary"], cv["baseline"])
    full = cross_validate(cache, classes, embedder, queries, labels, k=5)
    table(f"5-fold CV, full features: {full['protocol']}", full["summary"], full["baseline"])
    out = {
        **cv,
        "summary_full_features": full["summary"],
        "protocol_full_features": full["protocol"],
        "stats_frozen_at": cutoff,
        "ranker_version": ranker.version if ranker else None,
    }
    out.pop("per_query", None)
    if ranker:
        test_q = [q for q in queries if q["split"] == "test"]
        ev = evaluate_strategies(cache, classes, embedder, ranker, test_q, labels)
        table(
            f"Champion {ranker.version} on the fixed test split ({len(test_q)} queries, never searched in warm-up)",
            ev["summary"],
            ev["baseline"],
        )
        out["test_split"] = ev["summary"]
    path = settings.artifacts_dir / "offline_eval.json"
    path.write_text(json.dumps(out, indent=1, default=float))
    print(f"\nsaved {path}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
