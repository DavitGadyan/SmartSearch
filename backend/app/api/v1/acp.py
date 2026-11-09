"""Agentic Commerce Protocol merchant endpoints (Agentic Checkout Specification 2025-09-29 + Product Feed +
Delegated Payment mock). Mounted at /acp so the paths match the spec relative to the merchant base URL."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models import Product
from app.schemas.acp import (
    API_VERSION,
    CompleteSessionIn,
    CreateSessionIn,
    DelegatePaymentIn,
    UpdateSessionIn,
)
from app.services import acp_service
from app.services.acp_service import AcpError

router = APIRouter(tags=["acp"])


async def require_acp(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
    api_version: Annotated[str | None, Header(alias="API-Version")] = None,
    request_id: Annotated[str | None, Header(alias="Request-Id")] = None,
) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, settings.acp_api_key):
        raise AcpError(401, "invalid_request", "unauthorized", "Missing or invalid bearer token")
    if api_version != API_VERSION:
        raise AcpError(
            400, "invalid_request", "unsupported_version", f"API-Version must be {API_VERSION}", "API-Version"
        )
    if request_id:
        response.headers["Request-Id"] = request_id


Auth = Depends(require_acp)
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _actor(request: Request) -> tuple[str, str]:
    """Agents are anonymous shoppers from the store's point of view; one synthetic user/session per agent token."""
    agent = request.headers.get("User-Agent", "agent")[:40].replace(" ", "_")
    return f"acp_{agent}", f"acp_{request.headers.get('Request-Id') or 'session'}"[:64]


@router.post("/checkout_sessions", status_code=201, dependencies=[Auth])
async def create_session(
    body: CreateSessionIn,
    request: Request,
    response: Response,
    idempotency_key: IdemKey = None,
    db: AsyncSession = Depends(get_db),
):
    pending, replay = await acp_service.idempotent(db, idempotency_key, body.model_dump(), "create")
    if replay is not None:
        response.headers["Idempotency-Key"] = idempotency_key or ""
        return replay
    user_id, session_id = _actor(request)
    out = await acp_service.create_session(
        db, body.items, body.buyer, body.fulfillment_address, user_id, session_id
    )
    await acp_service.remember(db, pending, 201, out)
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key
    return out


@router.get("/checkout_sessions/{sid}", dependencies=[Auth])
async def get_session(sid: str, db: AsyncSession = Depends(get_db)):
    return await acp_service.view_session(db, sid)


@router.post("/checkout_sessions/{sid}", dependencies=[Auth])
async def update_session(sid: str, body: UpdateSessionIn, db: AsyncSession = Depends(get_db)):
    return await acp_service.update_session(
        db, sid, body.items, body.buyer, body.fulfillment_address, body.fulfillment_option_id
    )


@router.post("/checkout_sessions/{sid}/complete", dependencies=[Auth])
async def complete_session(
    sid: str,
    body: CompleteSessionIn,
    response: Response,
    idempotency_key: IdemKey = None,
    db: AsyncSession = Depends(get_db),
):
    pending, replay = await acp_service.idempotent(
        db, idempotency_key, {"sid": sid, **body.model_dump()}, "complete"
    )
    if replay is not None:
        return replay
    out = await acp_service.complete_session(db, sid, body.payment_data.token, body.buyer)
    await acp_service.remember(db, pending, 200, out)
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key
    return out


@router.post("/checkout_sessions/{sid}/cancel", dependencies=[Auth])
async def cancel_session(sid: str, db: AsyncSession = Depends(get_db)):
    return await acp_service.cancel_session(db, sid)


@router.post("/agentic_commerce/delegate_payment", status_code=201, dependencies=[Auth])
async def delegate_payment(
    body: DelegatePaymentIn,
    response: Response,
    idempotency_key: IdemKey = None,
    db: AsyncSession = Depends(get_db),
):
    pending, replay = await acp_service.idempotent(
        db, idempotency_key, body.model_dump(exclude={"payment_method": {"number", "cvc"}}), "delegate"
    )
    if replay is not None:
        return replay
    out = await acp_service.delegate_payment(db, body)
    await acp_service.remember(db, pending, 201, out)
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key
    return out


@router.get("/feed.json", dependencies=[Auth])
async def product_feed(
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """Product Feed Specification (JSON). Paginated; `next_offset` is null on the last page."""
    rows = (
        await db.execute(
            select(
                Product.id,
                Product.name,
                Product.description,
                Product.product_class,
                Product.category_hierarchy,
                Product.brand,
                Product.price,
                Product.rating,
                Product.review_count,
                Product.in_stock,
                Product.image_url,
                Product.attributes,
            )
            .order_by(Product.id)
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    web = settings.public_web_url.rstrip("/")
    products = [
        {
            "id": str(r.id),
            "title": r.name,
            "description": (r.description or r.name)[:2000],
            "link": f"{web}/product/{r.id}",
            "image_url": f"{web}{r.image_url}"
            if r.image_url and r.image_url.startswith("/")
            else r.image_url,
            "price": f"{float(r.price):.2f}",
            "currency": acp_service.CURRENCY.upper(),
            "availability": "in_stock" if r.in_stock else "out_of_stock",
            "brand": r.brand,
            "category": (r.category_hierarchy or r.product_class or "").replace("|", " > "),
            "product_type": r.product_class,
            "material": (r.attributes or {}).get("material"),
            "color": (r.attributes or {}).get("color"),
            "reviews": {"average_rating": r.rating, "review_count": r.review_count},
            "enable_search": True,
            "enable_checkout": bool(r.in_stock),
            "seller_name": "SmartSearch demo store",
        }
        for r in rows[:limit]
    ]
    return {
        "version": API_VERSION,
        "merchant_id": settings.acp_merchant_id,
        "offset": offset,
        "limit": limit,
        "next_offset": offset + limit if len(rows) > limit else None,
        "products": products,
    }
