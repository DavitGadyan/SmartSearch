from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import DEMO_USERS
from app.core.db import get_db
from app.ml.personalization.profile import build_profile
from app.services.runtime import runtime

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/demo", summary="One simulated shopper per persona, for the storefront's 'shop as' switcher")
async def demo_users(db: AsyncSession = Depends(get_db)):
    if (hit := DEMO_USERS.get("demo")) is not None:
        return hit
    rows = (
        (
            await db.execute(
                text(
                    """
                WITH ranked AS (
                    SELECT u.id, u.persona, u.segment, u.traits,
                           count(e.*) FILTER (WHERE e.event_type IN ('click','add_to_cart','purchase')) AS interactions,
                           row_number() OVER (PARTITION BY u.persona ORDER BY count(e.*) FILTER (WHERE e.event_type = 'purchase') DESC, u.id) AS rn
                    FROM users u LEFT JOIN events e ON e.user_id = u.id
                    WHERE u.is_simulated GROUP BY u.id
                )
                SELECT id, persona, segment, traits, interactions FROM ranked WHERE rn = 1 ORDER BY persona
                """
                )
            )
        )
        .mappings()
        .all()
    )
    result = [dict(r) for r in rows]
    DEMO_USERS.set("demo", result)
    return result


@router.get(
    "/{user_id}/profile", summary="Behaviour-derived affinity profile used by the personalized ranker"
)
async def profile(user_id: str, db: AsyncSession = Depends(get_db)):
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")
    p = await build_profile(db, user_id, runtime.catalog, use_cache=False)
    return asdict(p)
