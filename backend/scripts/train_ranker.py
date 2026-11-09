"""Train the LightGBM LambdaRank ranker on WANDS judgments; log to MLflow; register (and maybe promote) the model."""

import asyncio
import json
import sys
import time

import mlflow
import numpy as np

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.ml import registry
from app.ml.catalog_cache import load_catalog
from app.ml.eval.freeze import freeze_warmup_stats
from app.ml.eval.offline_eval import cross_validate, evaluate_strategies, grades_for, load_judgments
from app.ml.query import ClassIndex, parse_query
from app.ml.ranking.features import FEATURE_NAMES, build_features
from app.ml.ranking.ltr import DEFAULT_PARAMS, Ranker
from app.ml.ranking.strategies import retrieve_hybrid
from app.ml.retrieval.embedder import get_embedder

CV_ROUNDS = 300


def build_split(split: str, queries, labels, cache, classes, embedder, top_k: int):
    Xs, ys, groups = [], [], []
    for q in queries:
        if q["split"] != split:
            continue
        qlabels = labels.get(q["id"], {})
        pq = parse_query(q["text"])
        qvec = embedder.encode_one(pq.text)
        classes.annotate(pq, qvec)
        cand = retrieve_hybrid(pq, qvec, cache, top_k)
        if len(cand) == 0:
            continue
        y = grades_for(cache, cand.positions, qlabels)
        if y.max() == 0:
            continue  # no relevant candidate retrieved → no ranking signal for LambdaRank
        Xs.append(build_features(pq, cand, cache, classes))
        ys.append(y)
        groups.append(len(y))
    return np.vstack(Xs), np.concatenate(ys), np.array(groups)


def _flat(prefix: str, summary: dict) -> dict:
    return {
        f"{prefix}_{s}_{k}": v for s, m in summary.items() for k, v in m.items() if isinstance(v, int | float)
    }


async def main() -> None:
    t0 = time.perf_counter()
    cache = await load_catalog(engine)
    cutoff = await freeze_warmup_stats(engine, cache)
    embedder = get_embedder()
    classes = ClassIndex(cache.class_names, embedder)
    queries, labels = await load_judgments(engine)
    top_k = settings.retrieval_top_k

    X_tr, y_tr, g_tr = build_split("train", queries, labels, cache, classes, embedder, top_k)
    X_va, y_va, g_va = build_split("val", queries, labels, cache, classes, embedder, top_k)
    print(
        f"train: {len(g_tr)} queries / {len(y_tr):,} rows   val: {len(g_va)} queries / {len(y_va):,} rows   "
        f"positives(train)={int((y_tr > 0).sum()):,}  features={len(FEATURE_NAMES)}  ({time.perf_counter() - t0:.0f}s)"
    )

    async with SessionLocal() as db:
        version = await registry.next_version(db)
    ranker, info = Ranker.train(X_tr, y_tr, g_tr, X_va, y_va, g_va, version)
    print(f"trained {version}: best_iter={info['best_iteration']} val ndcg@10={info['val_ndcg10_best']:.4f}")

    test_q = [q for q in queries if q["split"] == "test"]
    ev_test = evaluate_strategies(cache, classes, embedder, ranker, test_q, labels)
    for s, m in ev_test["summary"].items():
        print(f"  test {s:22s} ndcg@10={m['ndcg@10']:.4f} mrr={m['mrr']:.4f} recall@50={m['recall@50']:.4f}")
    print("5-fold cross-validation (clean content-only, then full features) ...", flush=True)
    cv = cross_validate(
        cache, classes, embedder, queries, labels, k=5, num_rounds=CV_ROUNDS, behavioral=False
    )
    cv_full = cross_validate(cache, classes, embedder, queries, labels, k=5, num_rounds=CV_ROUNDS)
    for s, m in cv["summary"].items():
        lift = m.get("ndcg@10_lift_vs_baseline")
        print(
            f"  cv   {s:22s} ndcg@10={m['ndcg@10']:.4f} mrr={m['mrr']:.4f}"
            + (f"  lift vs control {lift:+.4f} {m.get('ndcg@10_lift_ci95')}" if lift is not None else "")
        )

    model_path = settings.artifacts_dir / "rankers" / f"{version}.txt"
    ranker.save(model_path)
    importance = ranker.feature_importance()
    metrics = {
        "val_ndcg@10": info["val_ndcg10_best"],
        "best_iteration": info["best_iteration"],
        **_flat("test", ev_test["summary"]),
        **_flat("cv", cv["summary"]),
        **_flat("cv_full", cv_full["summary"]),
        "test_comparison": ev_test["summary"],
        "cv_comparison": cv["summary"],
        "cv_full_comparison": cv_full["summary"],
        "stats_frozen_at": cutoff,
    }

    uri = registry.mlflow_setup()
    run_id = None
    try:
        with mlflow.start_run(run_name=version) as run:
            run_id = run.info.run_id
            mlflow.log_params(
                {
                    **DEFAULT_PARAMS,
                    "top_k": top_k,
                    "n_train_queries": len(g_tr),
                    "n_train_rows": len(y_tr),
                    "features": len(FEATURE_NAMES),
                    "stats_frozen_at": cutoff,
                }
            )
            mlflow.log_metrics(
                {k.replace("@", "_at_"): v for k, v in metrics.items() if isinstance(v, int | float)}
            )
            mlflow.log_dict(importance, "feature_importance.json")
            mlflow.log_dict(ev_test["summary"], "test_comparison.json")
            mlflow.log_dict(cv["summary"], "cv_comparison.json")
            mlflow.log_dict({"val_ndcg10_history": info["val_ndcg10_history"]}, "training_curve.json")
            mlflow.log_artifact(str(model_path), artifact_path="model")
            mlflow.set_tags(
                {
                    "algorithm": "lightgbm-lambdarank",
                    "dataset": "WANDS",
                    "embedding_model": settings.embedding_model,
                }
            )
    except Exception as e:  # MLflow must never block training
        print(f"mlflow logging failed: {e}")
    print(f"mlflow: {uri} run={run_id}")

    async with SessionLocal() as db:
        await registry.register(
            db,
            version=version,
            algorithm="lightgbm-lambdarank",
            run_id=run_id,
            artifact_path=str(model_path),
            params={**DEFAULT_PARAMS, "top_k": top_k},
            metrics=metrics,
            feature_importance=importance,
            feature_names=FEATURE_NAMES,
        )
    cv["ranker_version"] = version
    cv["test_split"] = ev_test["summary"]
    cv["summary_full_features"] = cv_full["summary"]
    cv["protocol_full_features"] = cv_full["protocol"]
    cv["stats_frozen_at"] = cutoff
    cv.pop("per_query", None)
    (settings.artifacts_dir / "offline_eval.json").write_text(json.dumps(cv, indent=1, default=float))
    print(f"done in {time.perf_counter() - t0:.0f}s → {model_path}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
