from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import Product
from app.schemas.catalog import ProductDetail, ProductOut
from app.services import search_service
from app.services.runtime import runtime

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(ids: str = Query(description="comma-separated product ids")):
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")
    out = []
    for raw in ids.split(",")[:100]:
        if raw.strip().isdigit() and (pos := runtime.catalog.id_to_pos.get(int(raw))) is not None:
            out.append(ProductOut(**runtime.catalog.record(pos)))
    return out


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, response: Response, db: AsyncSession = Depends(get_db)):
    p = await db.scalar(select(Product).where(Product.id == product_id))
    if p is None:
        raise HTTPException(404, "product not found")
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return ProductDetail(
        id=p.id,
        name=p.name,
        product_class=p.product_class,
        brand=p.brand,
        price=float(p.price),
        rating=p.rating,
        review_count=p.review_count,
        in_stock=p.in_stock,
        is_new=p.is_new,
        attributes=p.attributes or {},
        image_url=p.image_url,
        description=p.description,
        category_hierarchy=p.category_hierarchy,
        similar=search_service.similar_products(product_id, 12) if runtime.catalog else [],
    )


@router.get("/{product_id}/similar", response_model=list[ProductOut])
async def similar(product_id: int, k: int = Query(12, ge=1, le=50)):
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")
    return search_service.similar_products(product_id, k)
