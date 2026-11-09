"""User affinity profile derived from the user's own behavioral events (recency- and intent-weighted)."""

import json
from collections import defaultdict

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.ml.catalog_cache import CatalogCache
from app.ml.ranking.strategies import UserProfile

EVENT_WEIGHT = {"product_view": 1.0, "click": 1.0, "add_to_cart": 3.0, "purchase": 6.0, "rec_click": 1.0}
DECAY = 0.985  # per event, most recent first
TTL_S = 120


async def build_profile(
    db: AsyncSession, user_id: str, cache: CatalogCache, use_cache: bool = True
) -> UserProfile:
    redis = get_redis()
    key = f"profile:{user_id}"
    if use_cache:
        try:
            if raw := await redis.get(key):
                return UserProfile(**json.loads(raw))
        except Exception:
            pass
    rows = (
        await db.execute(
            text(
                "SELECT event_type, product_id FROM events WHERE user_id = :u AND product_id IS NOT NULL "
                "AND event_type IN ('product_view','click','add_to_cart','purchase','rec_click') ORDER BY ts DESC LIMIT 300"
            ),
            {"u": user_id},
        )
    ).all()
    profile = profile_from_interactions([(r[0], r[1]) for r in rows], cache)
    if use_cache:
        try:
            await redis.set(key, json.dumps(profile.__dict__), ex=TTL_S)
        except Exception:
            pass
    return profile


def profile_from_interactions(rows: list[tuple[str, int]], cache: CatalogCache) -> UserProfile:
    acc: dict[str, dict[str, float]] = {
        k: defaultdict(float) for k in ("brand", "product_class", "style", "material", "color")
    }
    lp, lw = 0.0, 0.0
    n = 0
    for i, (etype, pid) in enumerate(rows):
        pos = cache.id_to_pos.get(int(pid))
        if pos is None:
            continue
        w = EVENT_WEIGHT.get(etype, 1.0) * DECAY**i
        n += 1
        for k, arr in (
            ("brand", cache.brand),
            ("product_class", cache.product_class),
            ("style", cache.style),
            ("material", cache.material),
            ("color", cache.color),
        ):
            if arr[pos]:
                acc[k][arr[pos]] += w
        lp += w * cache.log_price[pos]
        lw += w
    if n == 0:
        return UserProfile()
    norm = {
        k: {v: round(x / max(d.values()), 3) for v, x in sorted(d.items(), key=lambda t: -t[1])[:8]}
        for k, d in acc.items()
        if d
    }
    return UserProfile(
        brand=norm.get("brand", {}),
        product_class=norm.get("product_class", {}),
        style=norm.get("style", {}),
        material=norm.get("material", {}),
        color=norm.get("color", {}),
        log_price_mean=float(lp / lw) if lw else None,
        log_price_sd=float(np.clip(0.6, 0.3, 1.0)),
        n_events=n,
    )
