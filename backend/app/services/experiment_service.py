import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import ANALYTICS
from app.experiments.assignment import assign_variant
from app.models import Experiment, ExperimentAssignment

_CACHE: dict[str, tuple[float, list[Experiment]]] = {}
_TTL = 30.0


@dataclass
class Exposure:
    experiment_key: str
    variant: str
    strategy: str
    explore: bool


async def running_experiments(db: AsyncSession, surface: str) -> list[Experiment]:
    now = time.monotonic()
    hit = _CACHE.get(surface)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    rows = (
        await db.scalars(
            select(Experiment)
            .where(Experiment.status == "running", Experiment.surface == surface)
            .order_by(Experiment.id)
        )
    ).all()
    _CACHE[surface] = (now, list(rows))
    return list(rows)


def invalidate_cache() -> None:
    _CACHE.clear()
    ANALYTICS.clear()


async def expose(
    db: AsyncSession, user_id: str, surface: str = "search", persist: bool = True
) -> Exposure | None:
    """Assign the user to the first running experiment on this surface (one experiment per surface at a time)."""
    for exp in await running_experiments(db, surface):
        variant = assign_variant(exp.salt, user_id, exp.variants, exp.traffic_allocation)
        if variant is None:
            continue
        vcfg = next(v for v in exp.variants if v["key"] == variant)
        if persist:
            await db.execute(
                insert(ExperimentAssignment)
                .values(experiment_key=exp.key, user_id=user_id, variant=variant)
                .on_conflict_do_nothing(constraint="uq_assignment_experiment_user")
            )
        return Exposure(
            exp.key,
            variant,
            vcfg.get("strategy", "hybrid_ltr_personalized"),
            bool(vcfg.get("explore", False)),
        )
    return None


async def expose_ui(db: AsyncSession, user_id: str, surface: str = "ui") -> dict:
    """Assign (and persist) the shopper to the running UI experiment and return the arm's storefront config."""
    exp = await expose(db, user_id, surface, persist=True)
    if exp is None:
        return {}
    e = next((x for x in await running_experiments(db, surface) if x.key == exp.experiment_key), None)
    vcfg = next((v for v in (e.variants if e else []) if v["key"] == exp.variant), {})
    await db.commit()
    return {"experiment_key": exp.experiment_key, "variant": exp.variant, "ui": vcfg.get("ui")}


async def set_status(db: AsyncSession, key: str, status: str) -> Experiment:
    """draft → running → completed/archived. One running experiment per surface (raises RuntimeError)."""
    e = await db.scalar(select(Experiment).where(Experiment.key == key))
    if e is None:
        raise LookupError(key)
    now = datetime.now(UTC)
    if status == "running":
        running = await db.scalar(
            select(Experiment).where(
                Experiment.status == "running", Experiment.surface == e.surface, Experiment.key != key
            )
        )
        if running:
            raise RuntimeError(
                f"another experiment is already running on surface '{e.surface}': {running.key}"
            )
        e.start_at, e.end_at = e.start_at or now, None
    elif status in ("completed", "archived") and e.end_at is None:
        e.end_at = now
    e.status = status
    await db.commit()
    invalidate_cache()
    return e
