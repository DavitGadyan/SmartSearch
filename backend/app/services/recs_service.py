"""Recommendation rails: similar (content), bought-together (co-purchase), for-you (CF + profile), trending (popularity).

Two cross-cutting rules live here:
- caching: per-product and global rails are pure functions of the loaded catalog, so their results are memoised for a
  short time (the router still logs an impression per request);
- display preference: within a rail's top candidates, products with a photo fill the visible slots first. Scores are
  untouched; the preference only decides which of the already-ranked candidates are shown (`_photo_first`).
"""

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RAILS_GLOBAL, RAILS_ITEM
from app.ml.personalization.profile import build_profile
from app.ml.ranking.strategies import affinity_boost
from app.models import Event
from app.schemas.catalog import ProductOut
from app.services.events_service import ensure_user_session
from app.services.runtime import runtime

POOL = 3  # candidates considered per visible slot before the photo preference is applied


def _photo_first(has_image: np.ndarray, k: int) -> np.ndarray:
    """Index order into an already score-sorted pool: imaged items first (stable), then the rest, cut to k."""
    has = np.asarray(has_image, dtype=bool)
    if has.size == 0:
        return np.array([], dtype=np.int64)
    return np.concatenate([np.flatnonzero(has), np.flatnonzero(~has)])[:k]


async def _neighbors(
    db: AsyncSession, product_ids: list[int], method: str, limit: int = 60
) -> list[tuple[int, int, float]]:
    if not product_ids:
        return []
    rows = await db.execute(
        text(
            "SELECT product_id, neighbor_id, score FROM item_similarity WHERE method = :m AND product_id = ANY(:ids) ORDER BY score DESC LIMIT :lim"
        ),
        {"m": method, "ids": product_ids, "lim": limit},
    )
    return [(r[0], r[1], float(r[2])) for r in rows]


def _items(
    positions: np.ndarray, scores: np.ndarray | None = None, reasons: list[str] | None = None
) -> list[ProductOut]:
    c = runtime.catalog
    out = []
    for i, p in enumerate(positions):
        rec = c.record(int(p))
        out.append(
            ProductOut(
                **rec,
                position=i + 1,
                score=None if scores is None else float(scores[i]),
                explanation={"reason": reasons[i]} if reasons else None,
            )
        )
    return out


async def similar(product_id: int, k: int = 12) -> list[ProductOut]:
    key = ("similar", product_id, k)
    if (hit := RAILS_ITEM.get(key)) is not None:
        return hit
    c = runtime.catalog
    pos = c.id_to_pos.get(product_id)
    if pos is None:
        return []
    idx, sims = c.semantic.neighbors(pos, k * POOL)
    keep = c.in_stock[idx] > 0
    idx, sims = idx[keep], sims[keep]
    order = _photo_first(c.has_image[idx], k)
    items = _items(idx[order], sims[order], ["Similar style and category"] * len(order))
    RAILS_ITEM.set(key, items)
    return items


async def bought_together(db: AsyncSession, product_id: int, k: int = 8) -> list[ProductOut]:
    key = ("bought_together", product_id, k)
    if (hit := RAILS_ITEM.get(key)) is not None:
        return hit
    c = runtime.catalog
    pairs = await _neighbors(db, [product_id], "copurchase", k * POOL) or await _neighbors(
        db, [product_id], "cooccurrence", k * POOL
    )
    pairs = [(a, n, s) for a, n, s in pairs if n in c.id_to_pos]
    if not pairs:
        return []
    pos = np.array([c.id_to_pos[n] for _, n, _ in pairs], dtype=np.int64)
    scores = np.array([s for _, _, s in pairs], dtype=np.float32)
    keep = c.in_stock[pos] > 0
    pos, scores = pos[keep], scores[keep]
    order = _photo_first(c.has_image[pos], k)
    items = _items(pos[order], scores[order], ["Shoppers who bought this also bought"] * len(order))
    RAILS_ITEM.set(key, items)
    return items


async def goes_with(db: AsyncSession, product_id: int, k: int = 8) -> list[ProductOut]:
    """Knowledge-graph complements (co-purchase / co-view / category adjacency); falls back to co-purchase CF."""
    kg = runtime.graph
    if kg is None:
        return await bought_together(db, product_id, k)
    key = ("goes_with", product_id, k)
    if (hit := RAILS_ITEM.get(key)) is not None:
        return hit
    c = runtime.catalog
    comps = [
        (pid, s, rel)
        for pid, s, rel in kg.complements(product_id, k * POOL)
        if pid in c.id_to_pos and c.in_stock[c.id_to_pos[pid]] > 0
    ]
    if not comps:
        return await bought_together(db, product_id, k)
    pos = np.array([c.id_to_pos[pid] for pid, _, _ in comps], dtype=np.int64)
    order = _photo_first(c.has_image[pos], k)
    items = _items(
        pos[order],
        np.array([comps[i][1] for i in order]),
        [f"Goes with it ({comps[i][2].replace('_', ' ')})" for i in order],
    )
    RAILS_ITEM.set(key, items)
    return items


async def trending(k: int = 12, product_class: str | None = None) -> list[ProductOut]:
    key = ("trending", k, product_class)
    if (hit := RAILS_GLOBAL.get(key)) is not None:
        return hit
    c = runtime.catalog
    pop = c.popularity.copy()
    pop[c.in_stock == 0] = -1
    if product_class:
        pop[c.product_class != product_class] = -1
    idx = np.argsort(-pop)[: k * POOL]
    idx = idx[pop[idx] >= 0]
    order = _photo_first(c.has_image[idx], k)
    items = _items(idx[order], pop[idx[order]], ["Trending now"] * len(order))
    RAILS_GLOBAL.set(key, items)
    return items


async def new_arrivals(k: int = 12) -> list[ProductOut]:
    key = ("new_arrivals", k)
    if (hit := RAILS_GLOBAL.get(key)) is not None:
        return hit
    c = runtime.catalog
    score = c.popularity + 1e-3 * c.rating
    score = np.where((c.is_new > 0) & (c.in_stock > 0), score, -1)
    idx = np.argsort(-score)[: k * POOL]
    idx = idx[score[idx] >= 0]
    order = _photo_first(c.has_image[idx], k)
    items = _items(idx[order], score[idx[order]], ["New arrival"] * len(order))
    RAILS_GLOBAL.set(key, items)
    return items


async def for_you(db: AsyncSession, user_id: str, k: int = 12) -> tuple[list[ProductOut], dict]:
    c = runtime.catalog
    profile = await build_profile(db, user_id, c)
    hist = (
        await db.execute(
            text(
                "SELECT product_id, event_type FROM events WHERE user_id = :u AND product_id IS NOT NULL AND event_type IN ('click','add_to_cart','purchase') ORDER BY ts DESC LIMIT 30"
            ),
            {"u": user_id},
        )
    ).all()
    seen = {int(r[0]) for r in hist}
    bought = {int(r[0]) for r in hist if r[1] == "purchase"}
    if not hist:
        items = await trending(k)
        return items, {"strategy": "popularity_fallback", "reason": "new visitor - no history yet"}

    scores: dict[int, float] = {}
    reasons: dict[int, str] = {}
    recent = [int(r[0]) for r in hist[:10]]
    for src, nb, s in await _neighbors(db, recent, "cooccurrence", 200):
        if nb not in bought:
            scores[nb] = scores.get(nb, 0) + s
            reasons.setdefault(
                nb,
                f"Because you viewed {c.df['name'].iloc[c.id_to_pos[src]][:40]}"
                if src in c.id_to_pos
                else "Based on your browsing",
            )
    for pid in recent[:5]:  # content-based neighbours of recent items (covers cold items with no CF signal)
        pos = c.id_to_pos.get(pid)
        if pos is None:
            continue
        idx, sims = c.semantic.neighbors(pos, 8)
        for p, s in zip(idx, sims, strict=True):
            nid = int(c.ids[p])
            if nid not in bought:
                scores[nid] = scores.get(nid, 0) + 0.5 * float(s)
                reasons.setdefault(nid, f"Similar to {c.df['name'].iloc[pos][:40]}")
    if not scores:
        items = await trending(k)
        return items, {"strategy": "popularity_fallback", "reason": "no neighbours yet"}
    cand = np.array(list(scores))
    pos = c.positions(cand.tolist())
    base = np.array([scores[int(c.ids[p])] for p in pos])
    base = base / (base.max() or 1)
    final = base + 0.6 * affinity_boost(profile, pos, c) + 0.1 * c.popularity[pos] / (c.popularity.max() or 1)
    final[c.in_stock[pos] == 0] -= 5
    pool = np.argsort(-final)[: k * POOL]
    order = pool[_photo_first(c.has_image[pos[pool]], k)]
    ids_ordered = [int(c.ids[p]) for p in pos[order]]
    return _items(pos[order], final[order], [reasons.get(i, "Picked for you") for i in ids_ordered]), {
        "strategy": "item_cf+content+affinity",
        "display": "photo_first",
        "profile_events": profile.n_events,
        "seen": len(seen),
    }


async def log_rail(
    db: AsyncSession,
    rail: str,
    user_id: str,
    session_id: str,
    items: list[ProductOut],
    anchor: int | None = None,
) -> None:
    if not items:
        return
    now = datetime.now(UTC)
    await ensure_user_session(db, user_id, session_id, now)
    await db.execute(
        insert(Event),
        [
            dict(
                ts=now,
                user_id=user_id,
                session_id=session_id,
                event_type="rec_impression",
                product_id=it.id,
                position=it.position,
                source=f"recs:{rail}",
                meta={"anchor": anchor} if anchor else None,
            )
            for it in items
        ],
    )
    await db.commit()
