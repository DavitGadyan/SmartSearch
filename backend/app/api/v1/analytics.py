import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.cache import ANALYTICS
from app.core.config import settings
from app.core.db import get_db
from app.decision.client import backend_name
from app.services import analytics_service as svc
from app.services import opportunity_service

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_admin)])


def _guard(e: Exception):
    if "does not exist" in str(e) and "mart_" in str(e):
        raise HTTPException(503, "analytics marts not built - run `make marts`") from None
    raise e


@router.get("/overview")
async def overview(days: int = Query(28, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    if (hit := ANALYTICS.get(("overview", days))) is not None:
        return hit
    try:
        result = await svc.overview(db, days)
        ANALYTICS.set(("overview", days), result)
        return result
    except Exception as e:
        _guard(e)


@router.get("/search-terms")
async def search_terms(
    days: int = 28,
    limit: int = Query(50, le=500),
    sort: str = "searches",
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.search_terms(db, days, limit, sort, q)
    except Exception as e:
        _guard(e)


@router.get("/search-terms/trend")
async def search_term_trend(query: str, days: int = 28, db: AsyncSession = Depends(get_db)):
    return await svc.search_term_trend(db, query, days)


@router.get("/products")
async def products(
    days: int = 28, limit: int = Query(50, le=500), sort: str = "revenue", db: AsyncSession = Depends(get_db)
):
    try:
        return await svc.products(db, days, limit, sort)
    except Exception as e:
        _guard(e)


@router.get("/segments")
async def segments(days: int = 28, db: AsyncSession = Depends(get_db)):
    return await svc.segments(db, days)


@router.get("/cohorts")
async def cohorts(db: AsyncSession = Depends(get_db)):
    try:
        return await svc.cohorts(db)
    except Exception as e:
        _guard(e)


@router.get("/position-bias")
async def position_bias(days: int = 28, db: AsyncSession = Depends(get_db)):
    return await svc.position_bias(db, days)


@router.get("/ranking")
async def ranking(db: AsyncSession = Depends(get_db)):
    return await svc.ranking(db)


@router.get("/recommendations")
async def recommendations(days: int = 28, db: AsyncSession = Depends(get_db)):
    return await svc.recommendations(db, days)


@router.get("/bandit")
async def bandit():
    path = settings.artifacts_dir / "bandit_eval.json"
    return json.loads(path.read_text()) if path.exists() else {"status": "not_trained"}


@router.get("/decisions")
async def decisions():
    path = settings.artifacts_dir / "decision_eval.json"
    return {
        "backend": backend_name(),
        "model": settings.decision_model,
        "evaluation": json.loads(path.read_text()) if path.exists() else None,
    }


@router.get("/opportunities")
async def opportunities(days: int = 28, limit: int = Query(40, le=200), db: AsyncSession = Depends(get_db)):
    try:
        return await opportunity_service.detect(db, days, limit)
    except Exception as e:
        _guard(e)
