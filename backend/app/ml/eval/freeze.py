"""Freeze behavioral features at the end of the warm-up period for training and offline evaluation."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from app.analytics.snapshot import apply_snapshot, product_stats_as_of
from app.core.logging import get_logger
from app.ml.catalog_cache import CatalogCache
from app.simulation.simulator import simulation_start

log = get_logger("freeze")
WARMUP_DAYS = 7


async def freeze_warmup_stats(engine: AsyncEngine, cache: CatalogCache) -> str:
    """Replace cache.stats with stats as of the warm-up cutoff (simulation day 7, 00:00 UTC). Returns the cutoff ISO string."""
    cutoff = simulation_start() + timedelta(days=WARMUP_DAYS)
    apply_snapshot(cache, await product_stats_as_of(engine, cutoff))
    log.info("behavioral features frozen as of %s (end of warm-up)", cutoff.date())
    return cutoff.isoformat()
