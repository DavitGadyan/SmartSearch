"""Behavioral product stats *as of* a timestamp - the same aggregation as product_stats.sql, but as a SELECT."""

from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ml.catalog_cache import STAT_COLS

SQL = """
WITH agg AS (
    SELECT product_id,
           count(*) FILTER (WHERE event_type = 'impression' AND ts >= CAST(:as_of AS timestamptz) - interval '7 days') AS impressions_7d,
           count(*) FILTER (WHERE event_type = 'click'      AND ts >= CAST(:as_of AS timestamptz) - interval '7 days') AS clicks_7d,
           count(*) FILTER (WHERE event_type = 'impression')  AS impressions_30d,
           count(*) FILTER (WHERE event_type = 'click')       AS clicks_30d,
           count(*) FILTER (WHERE event_type = 'add_to_cart') AS carts_30d,
           count(*) FILTER (WHERE event_type = 'purchase')    AS purchases_30d,
           coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)::float AS revenue_30d
    FROM events
    WHERE product_id IS NOT NULL AND ts > CAST(:as_of AS timestamptz) - interval '30 days' AND ts <= CAST(:as_of AS timestamptz)
    GROUP BY product_id
)
SELECT p.id AS product_id,
       coalesce(a.impressions_7d, 0) AS impressions_7d, coalesce(a.clicks_7d, 0) AS clicks_7d,
       coalesce(a.impressions_30d, 0) AS impressions_30d, coalesce(a.clicks_30d, 0) AS clicks_30d,
       coalesce(a.carts_30d, 0) AS carts_30d, coalesce(a.purchases_30d, 0) AS purchases_30d, coalesce(a.revenue_30d, 0) AS revenue_30d,
       (coalesce(a.clicks_30d, 0) + 0.5)    / (coalesce(a.impressions_30d, 0) + 20.0) AS ctr_30d,
       (coalesce(a.carts_30d, 0) + 0.2)     / (coalesce(a.clicks_30d, 0) + 10.0)      AS cart_rate_30d,
       (coalesce(a.purchases_30d, 0) + 0.1) / (coalesce(a.clicks_30d, 0) + 10.0)      AS conversion_30d,
       ln(1 + coalesce(a.clicks_30d, 0) + 3 * coalesce(a.carts_30d, 0) + 10 * coalesce(a.purchases_30d, 0)) AS popularity
FROM products p LEFT JOIN agg a ON a.product_id = p.id
ORDER BY p.id
"""


async def product_stats_as_of(engine: AsyncEngine, as_of: datetime) -> pd.DataFrame:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(SQL), {"as_of": as_of})).mappings().all()
    df = pd.DataFrame(rows)
    for c in STAT_COLS:
        df[c] = df[c].astype(float)
    return df.drop(columns=["product_id"])


def apply_snapshot(cache, df: pd.DataFrame) -> None:
    cache.stats = df.reset_index(drop=True)
    cache.refresh_stat_arrays()
