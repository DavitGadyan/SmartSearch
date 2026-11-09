"""Read models for the merchant console. All queries run against the marts (materialized views) + small dims."""

import json
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def _rows(db: AsyncSession, sql: str, **p) -> list[dict]:
    """Rows as dicts; Postgres NUMERIC sums come back as Decimal, which breaks float arithmetic and JSON."""
    return [
        {k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()}
        for r in (await db.execute(text(sql), p)).mappings().all()
    ]


async def latest_day(db: AsyncSession) -> date | None:
    return await db.scalar(text("SELECT max(day) FROM mart_funnel_daily"))


async def window(db: AsyncSession, days: int) -> tuple[date, date]:
    end = await latest_day(db) or date.today()
    return end - timedelta(days=days - 1), end


def _kpis(rows: list[dict]) -> dict:
    s = {
        k: float(sum(r[k] or 0 for r in rows))
        for k in (
            "visitors",
            "sessions",
            "searches",
            "zero_result_searches",
            "impressions",
            "clicks",
            "carts",
            "purchases",
            "buyers",
            "orders",
            "revenue",
        )
    }
    return {
        **s,
        "conversion_rate": s["buyers"] / s["visitors"] if s["visitors"] else 0,
        "revenue_per_visitor": s["revenue"] / s["visitors"] if s["visitors"] else 0,
        "aov": s["revenue"] / s["orders"] if s["orders"] else 0,
        "search_ctr": s["clicks"] / s["impressions"] if s["impressions"] else 0,
        "add_to_cart_rate": s["carts"] / s["clicks"] if s["clicks"] else 0,
        "zero_result_rate": s["zero_result_searches"] / s["searches"] if s["searches"] else 0,
        "purchases_per_search": s["purchases"] / s["searches"] if s["searches"] else 0,
    }


async def overview(db: AsyncSession, days: int = 28) -> dict:
    start, end = await window(db, days)
    prev_start = start - timedelta(days=days)
    cur = await _rows(
        db, "SELECT * FROM mart_funnel_daily WHERE day BETWEEN :s AND :e ORDER BY day", s=start, e=end
    )
    prev = await _rows(
        db, "SELECT * FROM mart_funnel_daily WHERE day >= :s AND day < :e", s=prev_start, e=start
    )
    k_cur, k_prev = _kpis(cur), _kpis(prev)
    deltas = {k: ((k_cur[k] - k_prev[k]) / k_prev[k] if k_prev.get(k) else None) for k in k_cur}
    for r in cur:
        r["day"] = r["day"].isoformat()
        r["conversion_rate"] = r["buyers"] / r["visitors"] if r["visitors"] else 0
        r["search_ctr"] = r["clicks"] / r["impressions"] if r["impressions"] else 0
        r["revenue_per_visitor"] = r["revenue"] / r["visitors"] if r["visitors"] else 0
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "kpis": k_cur,
        "previous": k_prev,
        "deltas": deltas,
        "daily": cur,
    }


async def search_terms(
    db: AsyncSession, days: int = 28, limit: int = 50, sort: str = "searches", q: str | None = None
) -> list[dict]:
    start, end = await window(db, days)
    sort = (
        sort
        if sort in ("searches", "clicks", "purchases", "revenue", "ctr", "conversion", "zero_result_rate")
        else "searches"
    )
    return await _rows(
        db,
        f"""
        SELECT query, sum(searches) AS searches, sum(searchers) AS searchers, sum(zero_result_searches) AS zero_result_searches,
               sum(impressions) AS impressions, sum(clicks) AS clicks, sum(carts) AS carts, sum(purchases) AS purchases, sum(revenue) AS revenue,
               sum(clicks)::float / nullif(sum(impressions), 0) AS ctr,
               sum(purchases)::float / nullif(sum(searches), 0) AS conversion,
               sum(zero_result_searches)::float / nullif(sum(searches), 0) AS zero_result_rate,
               avg(avg_click_position) AS avg_click_position
        FROM mart_search_terms_daily WHERE day BETWEEN :s AND :e {"AND query ILIKE :q" if q else ""}
        GROUP BY query ORDER BY {sort} DESC NULLS LAST LIMIT :lim
        """,
        s=start,
        e=end,
        lim=limit,
        q=f"%{q}%" if q else None,
    )


async def search_term_trend(db: AsyncSession, query: str, days: int = 28) -> list[dict]:
    start, end = await window(db, days)
    rows = await _rows(
        db,
        "SELECT day, searches, zero_result_searches, clicks, impressions, purchases, revenue FROM mart_search_terms_daily WHERE query = :q AND day BETWEEN :s AND :e ORDER BY day",
        q=query.lower(),
        s=start,
        e=end,
    )
    for r in rows:
        r["day"] = r["day"].isoformat()
    return rows


async def products(db: AsyncSession, days: int = 28, limit: int = 50, sort: str = "revenue") -> list[dict]:
    start, end = await window(db, days)
    sort = sort if sort in ("impressions", "clicks", "purchases", "revenue", "ctr", "units") else "revenue"
    return await _rows(
        db,
        f"""
        SELECT m.product_id, p.name, p.product_class, p.brand, p.price::float AS price, p.in_stock, p.is_new,
               sum(m.impressions) AS impressions, sum(m.clicks) AS clicks, sum(m.carts) AS carts, sum(m.purchases) AS purchases,
               sum(m.units) AS units, sum(m.revenue) AS revenue, sum(m.clicks)::float / nullif(sum(m.impressions), 0) AS ctr,
               avg(m.avg_impression_position) AS avg_position
        FROM mart_product_daily m JOIN products p ON p.id = m.product_id
        WHERE m.day BETWEEN :s AND :e GROUP BY 1, 2, 3, 4, 5, 6, 7 ORDER BY {sort} DESC NULLS LAST LIMIT :lim
        """,
        s=start,
        e=end,
        lim=limit,
    )


async def segments(db: AsyncSession, days: int = 28) -> list[dict]:
    start, end = await window(db, days)
    return await _rows(
        db,
        """
        SELECT coalesce(u.persona, 'unknown') AS persona, coalesce(u.segment, 'unknown') AS segment,
               count(DISTINCT e.user_id) AS users,
               count(*) FILTER (WHERE e.event_type = 'search') AS searches,
               count(*) FILTER (WHERE e.event_type = 'click') AS clicks,
               count(*) FILTER (WHERE e.event_type = 'impression') AS impressions,
               count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'purchase') AS buyers,
               coalesce(sum(e.revenue) FILTER (WHERE e.event_type = 'purchase'), 0)::float AS revenue
        FROM events e LEFT JOIN users u ON u.id = e.user_id
        WHERE e.ts >= :s AND e.ts < CAST(:e AS timestamptz) + interval '1 day'
        GROUP BY 1, 2 ORDER BY users DESC
        """,
        s=start,
        e=end,
    )


async def cohorts(db: AsyncSession) -> list[dict]:
    rows = await _rows(db, "SELECT * FROM mart_cohort_retention ORDER BY cohort_week, weeks_since")
    for r in rows:
        r["cohort_week"] = r["cohort_week"].isoformat()
        r["retention"] = r["active_users"] / r["cohort_size"] if r["cohort_size"] else 0
    return rows


async def position_bias(db: AsyncSession, days: int = 28) -> list[dict]:
    start, end = await window(db, days)
    return await _rows(
        db,
        """
        SELECT position, count(*) FILTER (WHERE event_type = 'impression') AS impressions, count(*) FILTER (WHERE event_type = 'click') AS clicks,
               count(*) FILTER (WHERE event_type = 'click')::float / nullif(count(*) FILTER (WHERE event_type = 'impression'), 0) AS ctr
        FROM events WHERE source = 'search' AND position BETWEEN 1 AND 20 AND ts >= :s AND ts < CAST(:e AS timestamptz) + interval '1 day'
        GROUP BY position ORDER BY position
        """,
        s=start,
        e=end,
    )


async def ranking(db: AsyncSession) -> dict:
    models = await _rows(
        db,
        "SELECT version, algorithm, mlflow_run_id, params, metrics, feature_importance, feature_names, is_champion, trained_at FROM ranking_models ORDER BY id DESC",
    )
    for m in models:
        m["trained_at"] = m["trained_at"].isoformat()
    path = settings.artifacts_dir / "offline_eval.json"
    ev = json.loads(path.read_text()) if path.exists() else None
    if ev:
        ev.pop("per_query", None)
    return {
        "models": models,
        "offline_eval": ev,
        "mlflow_ui": settings.mlflow_tracking_uri
        if settings.mlflow_tracking_uri.startswith("http")
        else None,
    }


async def recommendations(db: AsyncSession, days: int = 28) -> dict:
    start, end = await window(db, days)
    rails = await _rows(
        db,
        """
        SELECT source, count(*) FILTER (WHERE event_type = 'rec_impression') AS impressions, count(*) FILTER (WHERE event_type = 'rec_click') AS clicks,
               count(*) FILTER (WHERE event_type = 'rec_click')::float / nullif(count(*) FILTER (WHERE event_type = 'rec_impression'), 0) AS ctr,
               count(*) FILTER (WHERE event_type = 'add_to_cart') AS carts, count(*) FILTER (WHERE event_type = 'purchase') AS purchases,
               coalesce(sum(revenue) FILTER (WHERE event_type = 'purchase'), 0)::float AS revenue
        FROM events WHERE source LIKE 'recs:%' AND ts >= :s AND ts < CAST(:e AS timestamptz) + interval '1 day' GROUP BY source ORDER BY impressions DESC
        """,
        s=start,
        e=end,
    )
    path = settings.artifacts_dir / "retailrocket_eval.json"
    return {"rails": rails, "offline_eval": json.loads(path.read_text()) if path.exists() else None}
