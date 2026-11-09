import uuid
from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Order, OrderItem, Session, User
from app.schemas.events import EventIn, PurchaseIn


async def ensure_user_session(
    db: AsyncSession, user_id: str, session_id: str, ts: datetime, simulated: bool = False
) -> None:
    await db.execute(
        pg_insert(User)
        .values(id=user_id, is_simulated=simulated, traits={})
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await db.execute(
        pg_insert(Session)
        .values(id=session_id, user_id=user_id, started_at=ts)
        .on_conflict_do_nothing(index_elements=["id"])
    )


async def record(db: AsyncSession, events: list[EventIn]) -> int:
    now = datetime.now(UTC)
    rows = []
    seen: set[tuple[str, str]] = set()
    for e in events:
        d = e.model_dump()
        d["ts"] = d["ts"] or now
        d["meta"] = d.pop("metadata")
        rows.append(d)
        seen.add((e.user_id, e.session_id))
    for user_id, session_id in seen:
        await ensure_user_session(db, user_id, session_id, now)
    await db.execute(insert(Event), rows)
    await db.commit()
    return len(rows)


async def purchase(db: AsyncSession, p: PurchaseIn, prices: dict[int, float]) -> dict:
    now = datetime.now(UTC)
    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    await ensure_user_session(db, p.user_id, p.session_id, now)
    items = [
        (int(i["product_id"]), int(i.get("quantity", 1))) for i in p.items if int(i["product_id"]) in prices
    ]
    total = sum(prices[pid] * q for pid, q in items)
    db.add(
        Order(
            id=order_id,
            user_id=p.user_id,
            session_id=p.session_id,
            ts=now,
            total=total,
            experiment_key=p.experiment_key,
            variant=p.variant,
        )
    )
    for pid, q in items:
        db.add(OrderItem(order_id=order_id, product_id=pid, quantity=q, unit_price=prices[pid]))
    await db.execute(
        insert(Event),
        [
            dict(
                ts=now,
                user_id=p.user_id,
                session_id=p.session_id,
                event_type="purchase",
                product_id=pid,
                quantity=q,
                revenue=prices[pid] * q,
                experiment_key=p.experiment_key,
                variant=p.variant,
                source=p.source,
                meta={"order_id": order_id},
            )
            for pid, q in items
        ],
    )
    await db.commit()
    return {"order_id": order_id, "total": round(total, 2), "items": len(items)}
