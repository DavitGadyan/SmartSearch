"""Run the shopper simulation."""

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.bandit.policy import LinTS
from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.ml.catalog_cache import load_catalog
from app.ml.eval.offline_eval import load_judgments
from app.ml.query import ClassIndex
from app.ml.ranking.ltr import Ranker
from app.ml.retrieval.embedder import get_embedder
from app.models import RankingModel
from app.simulation.personas import generate_users
from app.simulation.reset import reset_experiment_phase, reset_simulation
from app.simulation.simulator import SIM_DAYS, ExperimentSpec, SimPlan, Simulator, simulation_start

DAYS = SIM_DAYS
RANKING_EXPERIMENT = ExperimentSpec(
    key="ranking_hybrid_ltr_v1",
    name="Hybrid retrieval + personalized LTR vs. BM25 + popularity",
    hypothesis="Fusing semantic retrieval with BM25 and re-ranking with a LambdaRank model plus user affinity surfaces more relevant products, lifting search conversion and revenue per visitor without hurting CTR or zero-result rate.",
    day_from=7,
    day_to=20,
    salt="rk-2026-11-a",
    variants=[
        {
            "key": "control",
            "name": "BM25 + popularity",
            "description": "Keyword match, ranked by text score and popularity",
            "strategy": "control_bm25_pop",
            "weight": 0.5,
        },
        {
            "key": "treatment",
            "name": "Hybrid + LTR + personalization",
            "description": "Keyword + semantic retrieval, learned ranker, personalized to the shopper",
            "strategy": "hybrid_ltr_personalized",
            "weight": 0.5,
        },
    ],
    primary_metric="conversion_rate",
    summary="Half of the shoppers get a new ranking of the same search results; we measure who buys more.",
)
AA_EXPERIMENT = ExperimentSpec(
    key="aa_sanity_check",
    name="A/A sanity check (layered on the ranking test)",
    hypothesis="Two identically treated random halves should show no significant difference on any metric. Used to validate the assignment hash and the statistics engine.",
    day_from=7,
    day_to=20,
    salt="aa-2026-11-a",
    variants=[
        {
            "key": "a1",
            "name": "A (first half)",
            "description": "Same ranking as the other half",
            "weight": 0.5,
        },
        {
            "key": "a2",
            "name": "A (second half)",
            "description": "Same ranking as the other half",
            "weight": 0.5,
        },
    ],
    decides_strategy=False,
    summary="Nothing changes between the two halves; any significant difference would mean the engine is broken.",
)
EXPLORATION_EXPERIMENT = ExperimentSpec(
    key="exploration_slot",
    name="Thompson-sampling exploration slot for cold-start products",
    hypothesis="Reserving result position 5 for a Thompson-sampled cold product gives new items impressions without measurably hurting conversion or revenue per visitor.",
    day_from=21,
    day_to=27,
    salt="xp-2026-11-a",
    variants=[
        {
            "key": "off",
            "name": "No exploration",
            "description": "The learned ranking as is",
            "strategy": "hybrid_ltr_personalized",
            "explore": False,
            "weight": 0.5,
        },
        {
            "key": "on",
            "name": "Exploration slot at #5",
            "description": "Position 5 reserved for a product with under 50 impressions, picked by Thompson sampling",
            "strategy": "hybrid_ltr_personalized",
            "explore": True,
            "weight": 0.5,
        },
    ],
    primary_metric="conversion_rate",
    status_after="completed",
    summary="One result slot is given to a new product so it can earn clicks; we check that sales do not drop.",
)
BANDIT_EXPERIMENT = ExperimentSpec(
    key="bandit_policy_v1",
    name="Contextual-bandit policy vs. fixed treatment ranker",
    hypothesis="A LinTS policy that picks the ranking strategy per request from query intent, constraints, shopper history, segment and device (trained off-policy on the earlier experiments, learning online from purchases) converts at least as well as the fixed treatment ranker.",
    day_from=28,
    day_to=34,
    salt="bd-2026-11-a",
    variants=[
        {
            "key": "fixed",
            "name": "Fixed treatment ranker",
            "description": "The winning ranker from the ranking test, for everyone",
            "strategy": "hybrid_ltr_personalized",
            "weight": 0.5,
        },
        {
            "key": "bandit",
            "name": "LinTS contextual bandit",
            "description": "Picks a ranker per search from the shopper's context and keeps learning from purchases",
            "strategy": "bandit",
            "weight": 0.5,
        },
    ],
    primary_metric="conversion_rate",
    status_after="running",
    summary="A policy chooses the ranker per search instead of one ranker for all; we measure conversion against the fixed ranker.",
)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["warmup", "experiment", "bandit"], required=True)
    ap.add_argument("--users", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scale", type=float, default=1.0, help="multiply sessions per user")
    ap.add_argument("--reset", action="store_true", help="wipe all simulated events/users/experiments first")
    a = ap.parse_args()

    if a.reset and a.phase == "warmup":
        await reset_simulation()
        print("simulated data cleared")
    elif a.reset:
        cut = 7 if a.phase == "experiment" else 28
        await reset_experiment_phase(
            simulation_start(DAYS) + timedelta(days=cut), rebuild_similarity=a.phase == "experiment"
        )
        print(f"simulated data from day {cut} on cleared")
    cache = await load_catalog(engine)
    embedder = get_embedder()
    classes = ClassIndex(cache.class_names, embedder)
    queries, labels = await load_judgments(engine)
    async with SessionLocal() as db:
        champ = await db.scalar(select(RankingModel).where(RankingModel.is_champion.is_(True)))
    ranker = (
        Ranker.load(Path(champ.artifact_path), champ.version)
        if champ and Path(champ.artifact_path).exists()
        else None
    )
    start = simulation_start(DAYS)

    users = generate_users(
        a.users, cache, np.random.default_rng(a.seed), prefix="sim"
    )  # deterministic → same population in both phases
    sim = Simulator(
        cache,
        classes,
        embedder,
        ranker,
        queries,
        labels,
        start,
        seed=a.seed + {"warmup": 0, "experiment": 1, "bandit": 2}[a.phase],
    )

    if a.phase == "warmup":
        plan = SimPlan(
            0, 6, dict.fromkeys(range(0, 7), "control_bm25_pop"), [], query_splits=("train", "val")
        )
    elif a.phase == "bandit":
        policy_path = settings.artifacts_dir / "bandit_policy.json"
        if not policy_path.exists():
            sys.exit("no bandit policy - run scripts/train_bandit.py first")
        sim.bandit = LinTS.load(policy_path)
        sim.bandit.rng = np.random.default_rng(a.seed + 2)
        plan = SimPlan(28, 34, dict.fromkeys(range(28, 35), "hybrid_ltr_personalized"), [BANDIT_EXPERIMENT])
    else:
        if ranker is None:
            sys.exit("no champion ranker - run scripts/train_ranker.py first")
        base = {
            **dict.fromkeys(range(7, 21), "control_bm25_pop"),
            **dict.fromkeys(range(21, 28), "hybrid_ltr_personalized"),
        }
        plan = SimPlan(7, 27, base, [RANKING_EXPERIMENT, AA_EXPERIMENT, EXPLORATION_EXPERIMENT])
    if a.phase != "warmup":
        n_hist = await sim.load_history([u.id for u in users])
        print(f"loaded {n_hist:,} prior interactions for personalisation")

    print(
        f"phase={a.phase} users={len(users):,} days={plan.day_from}-{plan.day_to} ranker={sim.model_version} start={start.date()}"
    )
    stats = sim.run(plan, users, days_scale=a.scale)
    print("persisting ...", flush=True)
    await sim.persist(users, plan)
    stats["phase"] = a.phase
    if sim.bandit is not None:
        sim.bandit.save(settings.artifacts_dir / "bandit_policy.json")
        stats["bandit_updates"] = dict(sim.bandit.n)
    (settings.artifacts_dir / f"simulation_{a.phase}.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats))
    if stats["searches"]:
        print(
            f"funnel: ctr={stats['clicks'] / stats['impressions']:.3%} cart/click={stats['carts'] / max(stats['clicks'], 1):.1%} "
            f"buy/cart={stats['purchases'] / max(stats['carts'], 1):.1%} purchases/search={stats['purchases'] / stats['searches']:.2%} "
            f"zero-result={stats['zero_results'] / stats['searches']:.2%}"
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
