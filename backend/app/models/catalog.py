from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.db import Base


class Product(Base):
    """Catalog item. Sourced from WANDS; price/stock/is_new are synthesized (price_source='synthetic')."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # WANDS product_id
    name: Mapped[str] = mapped_column(Text, nullable=False)
    product_class: Mapped[str | None] = mapped_column(String(128), index=True)
    category_hierarchy: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    features_text: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(128), index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price_source: Mapped[str] = mapped_column(String(16), nullable=False, default="synthetic")
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    image_url: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    tsv = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_products_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_products_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_products_price", "price"),
    )


class Query(Base):
    """WANDS search queries with human relevance judgments (see RelevanceLabel)."""

    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # WANDS query_id
    text: Mapped[str] = mapped_column(Text, nullable=False)
    query_class: Mapped[str | None] = mapped_column(String(128))
    split: Mapped[str] = mapped_column(String(8), nullable=False, default="train")  # train/val/test
    popularity_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class RelevanceLabel(Base):
    """Editorial relevance grade: 2=Exact, 1=Partial, 0=Irrelevant."""

    __tablename__ = "relevance_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (UniqueConstraint("query_id", "product_id", name="uq_label_query_product"),)


class ProductStats(Base):
    """Rolling behavioral aggregates per product; refreshed by analytics/marts.py and used as ranking features."""

    __tablename__ = "product_stats"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    impressions_7d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks_7d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    impressions_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    carts_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    purchases_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revenue_30d: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    ctr_30d: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    cart_rate_30d: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    conversion_30d: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    popularity: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )  # smoothed engagement score
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
