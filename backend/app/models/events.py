from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

EVENT_TYPES = (
    "search",
    "impression",
    "click",
    "product_view",
    "add_to_cart",
    "purchase",
    "rec_impression",
    "rec_click",
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona: Mapped[str | None] = mapped_column(String(64), index=True)
    segment: Mapped[str | None] = mapped_column(String(64), index=True)
    traits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_simulated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device: Mapped[str | None] = mapped_column(String(32))


class Event(Base):
    """Append-only behavioral event log. No FKs on purpose: bulk COPY speed and tolerance for anonymous visitors."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    query: Mapped[str | None] = mapped_column(Text)
    query_id: Mapped[int | None] = mapped_column(Integer)
    product_id: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)
    result_count: Mapped[int | None] = mapped_column(Integer)
    experiment_key: Mapped[str | None] = mapped_column(String(64))
    variant: Mapped[str | None] = mapped_column(String(64))
    ranking_model_version: Mapped[str | None] = mapped_column(String(64))
    strategy: Mapped[str | None] = mapped_column(String(64))
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Numeric(8, 2))
    source: Mapped[str | None] = mapped_column(String(32))  # search | recs:<rail> | agent | direct
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        Index("ix_events_ts", "ts"),
        Index("ix_events_user_ts", "user_id", "ts"),
        Index("ix_events_type_ts", "event_type", "ts"),
        Index("ix_events_experiment_variant", "experiment_key", "variant"),
        Index("ix_events_product", "product_id"),
        Index("ix_events_query", "query"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    experiment_key: Mapped[str | None] = mapped_column(String(64))
    variant: Mapped[str | None] = mapped_column(String(64))


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
