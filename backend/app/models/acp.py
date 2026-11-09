"""Agentic Commerce Protocol (ACP) merchant state: checkout sessions, delegated payment tokens, idempotency keys."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AcpCheckoutSession(Base):
    """One agent-driven checkout. JSON columns hold the spec objects verbatim (line_items, totals, messages ...)."""

    __tablename__ = "acp_checkout_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{id, quantity}] as requested
    buyer: Mapped[dict | None] = mapped_column(JSONB)
    fulfillment_address: Mapped[dict | None] = mapped_column(JSONB)
    fulfillment_option_id: Mapped[str | None] = mapped_column(String(64))
    payment: Mapped[dict | None] = mapped_column(JSONB)  # {token, provider} once completed
    order_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AcpPaymentToken(Base):
    """Delegated payment token issued by the mock PSP. Only display fields of the card are kept, never the PAN."""

    __tablename__ = "acp_payment_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    allowance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    card: Mapped[dict] = mapped_column(JSONB, nullable=False)  # display_brand, display_last4, funding type
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcpIdempotencyKey(Base):
    """Replay protection: the same key with the same body returns the stored response, a different body is a 409."""

    __tablename__ = "acp_idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
