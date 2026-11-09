"""Agentic Commerce Protocol merchant side: checkout sessions an AI agent can create, price, complete and cancel.

The pure functions (`price_items`, `fulfillment_options`, `build_session`, `check_allowance`) hold every rule of
the Agentic Checkout Specification 2025-09-29 that this store implements and are unit-tested without a database.
The async functions persist sessions, issue mock delegated-payment tokens and turn a completed session into a
regular store order (orders, order_items, purchase events with source "acp")."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.acp import AcpCheckoutSession, AcpIdempotencyKey, AcpPaymentToken
from app.schemas.acp import Address, Allowance, Buyer, DelegatePaymentIn, Item, PaymentMethod
from app.schemas.events import PurchaseIn
from app.services import events_service
from app.services.runtime import runtime

log = get_logger("acp")

CURRENCY = "usd"
TAX_RATE = 0.08  # demo flat tax
FREE_SHIPPING_FROM = 7500  # cents
SHIPPING = [  # (id, title, subtitle, carrier, days, price in cents)
    ("standard", "Standard shipping", "Free over $75", "SmartSearch Ground", (4, 7), 999),
    ("express", "Express shipping", None, "SmartSearch Air", (1, 2), 1999),
]
TEST_CARDS = {"4242424242424242": ("visa", "credit"), "5555555555554444": ("mastercard", "debit")}
PROVIDER = {"provider": "smartsearch_mock", "supported_payment_methods": ["card"]}
LINKS = [{"type": "terms_of_use", "url": "https://github.com/wayfair/WANDS"}]


class AcpError(Exception):
    """Spec error object: {type, code, message, param} with an HTTP status."""

    def __init__(self, status: int, type_: str, code: str, message: str, param: str | None = None) -> None:
        super().__init__(message)
        self.status, self.type, self.code, self.message, self.param = status, type_, code, message, param

    def body(self) -> dict:
        out = {"type": self.type, "code": self.code, "message": self.message}
        if self.param:
            out["param"] = self.param
        return out


# ---------------------------------------------------------------- pure pricing / state rules


def cents(price: float) -> int:
    return int(round(price * 100))


def price_items(items: list[dict], lookup: dict[int, tuple[int, bool, str]]) -> tuple[list[dict], list[dict]]:
    """Return (line_items, messages). `lookup` maps product id -> (unit price in cents, in_stock, name).
    Unknown or out-of-stock products become error messages pointing at the offending line item."""
    lines, messages = [], []
    for i, it in enumerate(items):
        pid = int(it["id"])
        qty = int(it.get("quantity", 1))
        hit = lookup.get(pid)
        if hit is None:
            messages.append(
                {
                    "type": "error",
                    "code": "invalid",
                    "param": f"$.items[{i}].id",
                    "content_type": "plain",
                    "content": f"Unknown product {pid}",
                }
            )
            continue
        unit, in_stock, name = hit
        base = unit * qty
        tax = int(round(base * TAX_RATE))
        lines.append(
            {
                "id": f"li_{pid}",
                "item": {"id": str(pid), "quantity": qty},
                "base_amount": base,
                "discount": 0,
                "subtotal": base,
                "tax": tax,
                "total": base + tax,
            }
        )
        if not in_stock:
            messages.append(
                {
                    "type": "error",
                    "code": "out_of_stock",
                    "param": f"$.line_items[{len(lines) - 1}]",
                    "content_type": "plain",
                    "content": f"{name} is out of stock",
                }
            )
    return lines, messages


def fulfillment_options(items_subtotal: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    out = []
    for oid, title, subtitle, carrier, (d0, d1), price in SHIPPING:
        amount = 0 if (oid == "standard" and items_subtotal >= FREE_SHIPPING_FROM) else price
        out.append(
            {
                "type": "shipping",
                "id": oid,
                "title": title,
                "subtitle": subtitle,
                "carrier": carrier,
                "earliest_delivery_time": (now + timedelta(days=d0)).isoformat(),
                "latest_delivery_time": (now + timedelta(days=d1)).isoformat(),
                "subtotal": amount,
                "tax": 0,
                "total": amount,
            }
        )
    return out


def build_session(
    *,
    session_id: str,
    status: str | None,
    items: list[dict],
    lookup: dict[int, tuple[int, bool, str]],
    fulfillment_address: dict | None,
    fulfillment_option_id: str | None,
    buyer: dict | None = None,
    order: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Price everything and derive the status. Terminal statuses (completed / canceled) are kept as given."""
    lines, messages = price_items(items, lookup)
    items_base = sum(li["base_amount"] for li in lines)
    tax = sum(li["tax"] for li in lines)
    options = fulfillment_options(items_base, now)
    option = next((o for o in options if o["id"] == fulfillment_option_id), None)
    if fulfillment_option_id and option is None:
        messages.append(
            {
                "type": "error",
                "code": "invalid",
                "param": "$.fulfillment_option_id",
                "content_type": "plain",
                "content": "Unknown fulfillment option",
            }
        )
    shipping = option["total"] if option else 0
    total = items_base + tax + shipping
    totals = [
        {"type": "items_base_amount", "display_text": "Items", "amount": items_base},
        {"type": "subtotal", "display_text": "Subtotal", "amount": items_base},
        {"type": "fulfillment", "display_text": "Shipping", "amount": shipping},
        {"type": "tax", "display_text": "Tax", "amount": tax},
        {"type": "total", "display_text": "Total", "amount": total},
    ]
    if status not in ("completed", "canceled"):
        has_errors = any(m["type"] == "error" for m in messages)
        ready = bool(lines) and not has_errors and fulfillment_address is not None and option is not None
        status = "ready_for_payment" if ready else "not_ready_for_payment"
    out = {
        "id": session_id,
        "payment_provider": PROVIDER,
        "status": status,
        "currency": CURRENCY,
        "line_items": lines,
        "fulfillment_address": fulfillment_address,
        "fulfillment_options": options,
        "fulfillment_option_id": option["id"] if option else None,
        "totals": totals,
        "messages": messages,
        "links": LINKS,
    }
    if buyer:
        out["buyer"] = buyer
    if order:
        out["order"] = order
    return out


def check_allowance(allowance: dict, total: int, now: datetime | None = None) -> None:
    """Raise the spec error when a delegated token cannot pay for `total` (minor units)."""
    now = now or datetime.now(UTC)
    if allowance.get("currency", "").lower() != CURRENCY:
        raise AcpError(
            400,
            "invalid_request",
            "currency_mismatch",
            "Token currency does not match the session",
            "$.payment_data.token",
        )
    expires = datetime.fromisoformat(allowance["expires_at"].replace("Z", "+00:00"))
    if expires <= now:
        raise AcpError(
            400,
            "invalid_request",
            "token_expired",
            "Delegated payment token has expired",
            "$.payment_data.token",
        )
    if int(allowance["max_amount"]) < total:
        raise AcpError(
            402,
            "processing_error",
            "payment_declined",
            f"Token allows {allowance['max_amount']} but the order totals {total}",
            "$.payment_data.token",
        )


def request_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- persistence


def _lookup(items: list[dict]) -> dict[int, tuple[int, bool, str]]:
    c = runtime.catalog
    out: dict[int, tuple[int, bool, str]] = {}
    if c is None:
        return out
    for it in items:
        pos = c.id_to_pos.get(int(it["id"]))
        if pos is not None:
            rec = c.record(pos)
            out[rec["id"]] = (cents(rec["price"]), bool(rec["in_stock"]), rec["name"])
    return out


def _view(row: AcpCheckoutSession) -> dict:
    order = (
        {
            "id": row.order_id,
            "checkout_session_id": row.id,
            "permalink_url": f"{settings.public_web_url}/cart?order={row.order_id}",
        }
        if row.order_id
        else None
    )
    return build_session(
        session_id=row.id,
        status=row.status,
        items=row.items,
        lookup=_lookup(row.items),
        fulfillment_address=row.fulfillment_address,
        fulfillment_option_id=row.fulfillment_option_id,
        buyer=row.buyer,
        order=order,
    )


async def create_session(
    db: AsyncSession,
    items: list[Item],
    buyer: Buyer | None,
    address: Address | None,
    user_id: str,
    session_id: str,
) -> dict:
    row = AcpCheckoutSession(
        id=f"cs_{uuid.uuid4().hex[:16]}",
        status="not_ready_for_payment",
        currency=CURRENCY,
        items=[i.model_dump() for i in items],
        buyer=buyer.model_dump(exclude_none=True) if buyer else None,
        fulfillment_address=address.model_dump(exclude_none=True) if address else None,
        user_id=user_id,
        session_id=session_id,
    )
    view = _view(row)
    row.status = view["status"]
    db.add(row)
    await db.commit()
    return view


async def get_session(db: AsyncSession, sid: str) -> AcpCheckoutSession:
    row = await db.get(AcpCheckoutSession, sid)
    if row is None:
        raise AcpError(404, "invalid_request", "not_found", "Checkout session not found")
    return row


async def view_session(db: AsyncSession, sid: str) -> dict:
    return _view(await get_session(db, sid))


async def update_session(
    db: AsyncSession,
    sid: str,
    items: list[Item] | None,
    buyer: Buyer | None,
    address: Address | None,
    fulfillment_option_id: str | None,
) -> dict:
    row = await get_session(db, sid)
    if row.status in ("completed", "canceled"):
        raise AcpError(405, "invalid_request", "session_closed", f"Session is {row.status}")
    if items is not None:
        row.items = [i.model_dump() for i in items]
    if buyer is not None:
        row.buyer = buyer.model_dump(exclude_none=True)
    if address is not None:
        row.fulfillment_address = address.model_dump(exclude_none=True)
    if fulfillment_option_id is not None:
        row.fulfillment_option_id = fulfillment_option_id
    view = _view(row)
    row.status = view["status"]
    await db.commit()
    return view


async def cancel_session(db: AsyncSession, sid: str) -> dict:
    row = await get_session(db, sid)
    if row.status in ("completed", "canceled"):
        raise AcpError(405, "invalid_request", "session_closed", f"Session is already {row.status}")
    row.status = "canceled"
    await db.commit()
    return _view(row)


async def complete_session(db: AsyncSession, sid: str, token_id: str, buyer: Buyer | None) -> dict:
    row = await get_session(db, sid)
    if row.status in ("completed", "canceled"):
        raise AcpError(405, "invalid_request", "session_closed", f"Session is already {row.status}")
    view = _view(row)
    if view["status"] != "ready_for_payment":
        raise AcpError(400, "invalid_request", "not_ready", "Session is not ready for payment", "$.status")
    token = await db.get(AcpPaymentToken, token_id)
    if token is None:
        raise AcpError(
            400, "invalid_request", "invalid_token", "Unknown delegated payment token", "$.payment_data.token"
        )
    if token.used_at is not None:
        raise AcpError(
            400,
            "invalid_request",
            "token_used",
            "Delegated payment token was already used",
            "$.payment_data.token",
        )
    if token.allowance.get("checkout_session_id") not in (None, "", sid):
        raise AcpError(
            400,
            "invalid_request",
            "token_session_mismatch",
            "Token was issued for another session",
            "$.payment_data.token",
        )
    total = next(t["amount"] for t in view["totals"] if t["type"] == "total")
    check_allowance(token.allowance, total)

    prices = {
        int(li["item"]["id"]): li["base_amount"] / 100 / li["item"]["quantity"] for li in view["line_items"]
    }
    order = await events_service.purchase(
        db,
        PurchaseIn(
            user_id=row.user_id,
            session_id=row.session_id,
            items=[
                {"product_id": int(li["item"]["id"]), "quantity": li["item"]["quantity"]}
                for li in view["line_items"]
            ],
            source=f"acp:{token.meta.get('source') or 'agent'}",  # acp:storefront | acp:assistant | acp:agent
        ),
        prices,
    )
    token.used_at = datetime.now(UTC)
    row.status = "completed"
    row.order_id = order["order_id"]
    row.payment = {"token": token_id, "provider": PROVIDER["provider"], "display": token.card}
    if buyer is not None:
        row.buyer = buyer.model_dump(exclude_none=True)
    await db.commit()
    out = _view(row)
    asyncio.create_task(send_webhook("order_create", out))
    return out


async def delegate_payment(db: AsyncSession, body: DelegatePaymentIn) -> dict:
    """Mock PSP: accepts the two test cards, stores only display data and the allowance, returns a vt_ token."""
    pm: PaymentMethod = body.payment_method
    brand_funding = TEST_CARDS.get(pm.number)
    if brand_funding is None:
        raise AcpError(
            400,
            "invalid_request",
            "invalid_card",
            "Only the test cards 4242… and 5555… are accepted",
            "$.payment_method.number",
        )
    al: Allowance = body.allowance
    if al.merchant_id != settings.acp_merchant_id:
        raise AcpError(
            400, "invalid_request", "invalid_merchant", "Unknown merchant_id", "$.allowance.merchant_id"
        )
    token = AcpPaymentToken(
        id=f"vt_{uuid.uuid4().hex[:20]}",
        allowance=al.model_dump(),
        card={
            "display_brand": pm.display_brand or brand_funding[0],
            "display_last4": pm.display_last4 or pm.number[-4:],
            "display_card_funding_type": pm.display_card_funding_type or brand_funding[1],
        },
        meta=body.metadata,
    )
    db.add(token)
    await db.commit()
    return {
        "id": token.id,
        "created": token.created_at.isoformat() if token.created_at else datetime.now(UTC).isoformat(),
        "metadata": {**body.metadata, "merchant_id": al.merchant_id},
    }


async def idempotent(
    db: AsyncSession, key: str | None, body: Any, note: str
) -> tuple[AcpIdempotencyKey | None, dict | None]:
    """Return (None, stored_response) for a replay, raise on a conflicting reuse, else (row to fill, None)."""
    if not key:
        return None, None
    h = request_hash(body)
    row = await db.get(AcpIdempotencyKey, key)
    if row is not None:
        if row.request_hash != h:
            raise AcpError(
                409,
                "request_not_idempotent",
                "idempotency_conflict",
                "Idempotency-Key reused with different parameters",
            )
        return None, row.response
    return AcpIdempotencyKey(key=key, request_hash=h, status_code=0, response={}, note=note), None


async def remember(db: AsyncSession, row: AcpIdempotencyKey | None, status_code: int, response: dict) -> None:
    if row is None:
        return
    row.status_code, row.response = status_code, response
    db.add(row)
    await db.commit()


async def send_webhook(event: str, session: dict) -> None:
    """order_create / order_update to the configured URL, signed with HMAC-SHA256 (Merchant-Signature). Best effort."""
    if not settings.acp_webhook_url:
        return
    payload = json.dumps(
        {
            "type": event,
            "data": {
                "checkout_session_id": session["id"],
                "order": session.get("order"),
                "status": session["status"],
            },
        }
    ).encode()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                settings.acp_webhook_url,
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "Merchant-Signature": sign(payload, settings.acp_webhook_secret),
                },
            )
    except Exception:  # webhooks must never break checkout
        log.warning("acp webhook %s failed", event, exc_info=True)


# ---------------------------------------------------------------- agent helper (the store acting as the buyer's agent)


def demo_address(name: str = "Demo Shopper") -> Address:
    return Address(
        name=name,
        line_one="1 Market Street",
        city="San Francisco",
        state="CA",
        country="US",
        postal_code="94105",
    )


async def agent_checkout(db: AsyncSession, sid: str, fulfillment_option_id: str, buyer_name: str) -> dict:
    """Finish a session the way an agent would: pick shipping, obtain a delegated token for the exact total, complete."""
    view = await update_session(db, sid, None, None, None, fulfillment_option_id)
    if view["status"] != "ready_for_payment":
        return view
    total = next(t["amount"] for t in view["totals"] if t["type"] == "total")
    token = await delegate_payment(
        db,
        DelegatePaymentIn(
            payment_method=PaymentMethod(
                type="card", number="4242424242424242", exp_month="12", exp_year="2030", name=buyer_name
            ),
            allowance=Allowance(
                reason="one_time",
                max_amount=total,
                currency=CURRENCY,
                checkout_session_id=sid,
                merchant_id=settings.acp_merchant_id,
                expires_at=(datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
            ),
            metadata={"source": "assistant"},
        ),
    )
    return await complete_session(db, sid, token["id"], None)
