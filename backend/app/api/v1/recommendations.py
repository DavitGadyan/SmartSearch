from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.catalog import ProductOut
from app.services import recs_service as svc
from app.services.runtime import runtime

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

# Browser caching. Global rails may be served stale while revalidating; per-product rails must not, because a
# background revalidation carrying user_id/session_id would log an impression nobody saw.
PUBLIC_SWR = "public, max-age=60, stale-while-revalidate=300"
PUBLIC = "public, max-age=60"
PRIVATE = "private, max-age=30"


def _ready():
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")


@router.get("/for-you")
async def for_you(
    response: Response,
    user_id: str,
    session_id: str,
    k: int = Query(12, le=48),
    log: bool = True,
    db: AsyncSession = Depends(get_db),
):
    _ready()
    items, meta = await svc.for_you(db, user_id, k)
    if log:
        await svc.log_rail(db, "for_you", user_id, session_id, items)
    response.headers["Cache-Control"] = PRIVATE
    return {"rail": "for_you", "items": items, "meta": meta}


@router.get("/similar/{product_id}", response_model=list[ProductOut])
async def similar(
    response: Response,
    product_id: int,
    user_id: str | None = None,
    session_id: str | None = None,
    k: int = Query(12, le=48),
    db: AsyncSession = Depends(get_db),
):
    _ready()
    items = await svc.similar(product_id, k)
    if user_id and session_id:
        await svc.log_rail(db, "similar", user_id, session_id, items, anchor=product_id)
    response.headers["Cache-Control"] = PUBLIC
    return items


@router.get("/bought-together/{product_id}", response_model=list[ProductOut])
async def bought_together(
    response: Response,
    product_id: int,
    user_id: str | None = None,
    session_id: str | None = None,
    k: int = Query(8, le=24),
    db: AsyncSession = Depends(get_db),
):
    _ready()
    items = await svc.bought_together(db, product_id, k)
    if user_id and session_id:
        await svc.log_rail(db, "bought_together", user_id, session_id, items, anchor=product_id)
    response.headers["Cache-Control"] = PUBLIC
    return items


@router.get("/trending", response_model=list[ProductOut])
async def trending(response: Response, k: int = Query(12, le=48), product_class: str | None = None):
    _ready()
    response.headers["Cache-Control"] = PUBLIC_SWR
    return await svc.trending(k, product_class)


@router.get("/new-arrivals", response_model=list[ProductOut])
async def new_arrivals(response: Response, k: int = Query(12, le=48)):
    _ready()
    response.headers["Cache-Control"] = PUBLIC_SWR
    return await svc.new_arrivals(k)


@router.get("/goes-with/{product_id}", response_model=list[ProductOut])
async def goes_with(
    response: Response,
    product_id: int,
    user_id: str | None = None,
    session_id: str | None = None,
    k: int = Query(8, le=24),
    db: AsyncSession = Depends(get_db),
):
    _ready()
    items = await svc.goes_with(db, product_id, k)
    if user_id and session_id:
        await svc.log_rail(db, "goes_with", user_id, session_id, items, anchor=product_id)
    response.headers["Cache-Control"] = PUBLIC
    return items
