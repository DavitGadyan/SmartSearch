"""Runs the SQL models in analytics/sql. Multi-statement files use '-- @@' separators; marts are materialized views."""

import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

log = get_logger("marts")
SQL_DIR = Path(__file__).parent / "sql"

# Order matters: later marts may read earlier ones.
MODELS = [
    "product_stats.sql",
    "mart_funnel_daily.sql",
    "mart_search_terms_daily.sql",
    "mart_product_daily.sql",
    "mart_experiment_user.sql",
    "mart_cohort_retention.sql",
]


async def run_sql_file(engine: AsyncEngine, name: str, params: dict | None = None) -> float:
    path = SQL_DIR / name
    if not path.exists():
        log.warning("skipping %s (not found)", name)
        return 0.0
    t0 = time.perf_counter()
    async with engine.begin() as conn:
        for stmt in [s for s in path.read_text().split("\n-- @@\n") if s.strip()]:
            await conn.execute(text(stmt), params or {})
    dt = time.perf_counter() - t0
    log.info("%s ok (%.1fs)", name, dt)
    return dt


async def refresh_all(
    engine: AsyncEngine, as_of: datetime | None = None, only: list[str] | None = None
) -> dict[str, float]:
    params = {"as_of": as_of or datetime.now(UTC)}  # asyncpg needs a real datetime for ::timestamptz
    out = {}
    for name in MODELS:
        if only and name not in only:
            continue
        out[name] = await run_sql_file(engine, name, params)
    return out
