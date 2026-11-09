"""Agentic Commerce Protocol tables

Revision ID: b7c1d2e3f4a5
Revises: ffc594e5b7b8
Create Date: 2026-11-09 03:30:00+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "ffc594e5b7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "acp_checkout_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("buyer", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fulfillment_address", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fulfillment_option_id", sa.String(length=64), nullable=True),
        sa.Column("payment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "acp_payment_tokens",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("allowance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "acp_idempotency_keys",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("acp_idempotency_keys")
    op.drop_table("acp_payment_tokens")
    op.drop_table("acp_checkout_sessions")
