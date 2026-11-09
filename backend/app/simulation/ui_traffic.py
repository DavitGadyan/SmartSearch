"""Simulated shoppers for a console-created UI experiment.

The same simulator that produced the store's history runs one more time with a single experiment (the UI test) and
a fresh batch of shoppers. The arm's `effect` (assumed relative lifts, chosen by the merchant and shown as such) is
the only thing that differs between arms, so the test reads exactly like the engine would read real traffic."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select

from app.analytics.marts import run_sql_file
from app.core.db import SessionLocal, engine
from app.core.logging import get_logger
from app.ml.eval.offline_eval import load_judgments
from app.models import Experiment
from app.services import experiment_service
from app.services.runtime import runtime
from app.simulation.personas import generate_users
from app.simulation.simulator import ExperimentSpec, SimPlan, Simulator

log = get_logger("ui-traffic")


async def _set_sim_state(key: str, **fields) -> Experiment:
    async with SessionLocal() as db:
        e = await db.scalar(select(Experiment).where(Experiment.key == key))
        if e is None:
            raise LookupError(key)
        cfg = dict(e.config or {})
        cfg["simulated_traffic"] = {**cfg.get("simulated_traffic", {}), **fields}
        e.config = cfg  # new dict → SQLAlchemy sees the change
        await db.commit()
        await db.refresh(e)
        return e


async def simulate_ui_experiment(key: str, users: int = 3000, days: int = 7, seed: int = 11) -> dict:
    """Run `users` simulated shoppers over the last `days` days through experiment `key`, persist everything,
    refresh the experiment marts. Returns the simulator counters."""
    now = datetime.now(UTC)
    e = await _set_sim_state(
        key, status="running", users=users, days=days, seed=seed, started_at=now.isoformat()
    )
    try:
        if runtime.catalog is None or runtime.classes is None or runtime.embedder is None:
            raise RuntimeError("ML runtime not loaded")
        queries, labels = await load_judgments(engine)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
        base = "hybrid_ltr_personalized" if runtime.ranker is not None else "hybrid_rrf"
        spec = ExperimentSpec(
            key=e.key,
            name=e.name,
            hypothesis=e.hypothesis or "",
            day_from=0,
            day_to=days - 1,
            variants=list(e.variants),
            salt=e.salt,
            decides_strategy=False,
            status_after=e.status,
            surface=e.surface,
            primary_metric=e.primary_metric,
            secondary_metrics=list(e.secondary_metrics or []),
            guardrail_metrics=list(e.guardrail_metrics or []),
            summary=str((e.config or {}).get("summary", "")),
        )
        plan = SimPlan(0, days - 1, dict.fromkeys(range(days), base), [spec])
        rng = np.random.default_rng(seed)
        sim_users = generate_users(users, runtime.catalog, rng, prefix=f"sim_ui_{key[:16]}")
        sim = Simulator(
            runtime.catalog,
            runtime.classes,
            runtime.embedder,
            runtime.ranker,
            queries,
            labels,
            start,
            seed=seed,
        )
        counters = await asyncio.to_thread(sim.run, plan, sim_users, 1.0, 0)
        counters["exposed_users"] = len(sim.assignments)  # shoppers who visited and were assigned
        await sim.persist(sim_users, plan)
        # persist() upserts the experiment row like a scripted phase; restore the console-owned fields
        async with SessionLocal() as db:
            row = await db.scalar(select(Experiment).where(Experiment.key == key))
            row.status = e.status
            row.start_at = min(e.start_at, start) if e.start_at else start
            row.end_at = e.end_at
            row.config = {
                **(e.config or {}),
                "simulated_traffic": {
                    **((e.config or {}).get("simulated_traffic") or {}),
                    "status": "done",
                    "users": users,
                    "days": days,
                    "seed": seed,
                    "assumed_effect": {v["key"]: v.get("effect") or {} for v in e.variants},
                    "counters": {
                        k: (round(v, 2) if isinstance(v, float) else v) for k, v in counters.items()
                    },
                    "finished_at": datetime.now(UTC).isoformat(),
                },
            }
            await db.commit()
        await run_sql_file(engine, "mart_experiment_user.sql", {"as_of": datetime.now(UTC)})
        experiment_service.invalidate_cache()
        log.info("ui traffic for %s: %s", key, counters)
        return counters
    except Exception as ex:
        log.exception("ui traffic for %s failed", key)
        await _set_sim_state(key, status="error", error=str(ex)[:300])
        raise
