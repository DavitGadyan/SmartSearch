from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.ml.ranking.strategies import STRATEGIES
from app.schemas.catalog import SearchResponse, SuggestResponse
from app.services import search_service
from app.services.runtime import runtime

router = APIRouter(tags=["search"])


def _require_ready() -> None:
    if not runtime.ready or runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded - run `make data`")


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=200),
    user_id: str = Query(min_length=1, max_length=64),
    session_id: str = Query(min_length=1, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    product_class: list[str] | None = Query(None),
    brand: list[str] | None = Query(None),
    style: list[str] | None = Query(None),
    material: list[str] | None = Query(None),
    color: list[str] | None = Query(None),
    price_min: float | None = None,
    price_max: float | None = None,
    in_stock: bool = False,
    min_rating: float | None = None,
    strategy: str | None = Query(
        None, description=f"Force a strategy (debug/offline): {', '.join((*STRATEGIES, 'bandit'))}"
    ),
    explore: bool | None = Query(None, description="Force the exploration slot on/off (debug/preview)"),
    explain: bool = False,
    log: bool = True,
    device: str = Query("desktop", pattern="^(desktop|mobile|tablet)$"),
    db: AsyncSession = Depends(get_db),
):
    _require_ready()
    if strategy and strategy not in (*STRATEGIES, "bandit"):
        raise HTTPException(422, f"strategy must be one of {(*STRATEGIES, 'bandit')}")
    filters = {
        k: v
        for k, v in dict(
            product_class=product_class,
            brand=brand,
            style=style,
            material=material,
            color=color,
            price_min=price_min,
            price_max=price_max,
            in_stock=in_stock or None,
            min_rating=min_rating,
        ).items()
        if v
    }
    return await search_service.search(
        db,
        q,
        user_id,
        session_id,
        page,
        page_size,
        filters,
        strategy,
        explain,
        log,
        device=device,
        explore_override=explore,
    )


@router.get("/autosuggest", response_model=SuggestResponse)
async def autosuggest(q: str = Query(min_length=1, max_length=100), limit: int = Query(8, ge=1, le=20)):
    _require_ready()
    return search_service.suggest(q, limit)
