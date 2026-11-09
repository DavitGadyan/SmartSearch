from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RankingModel(Base):
    """Registry mirror of trained rankers (source of truth for metrics is MLflow; this is what the API serves)."""

    __tablename__ = "ranking_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    artifact_path: Mapped[str | None] = mapped_column(String(512))
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feature_importance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feature_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_champion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ItemSimilarity(Base):
    """Precomputed item-item neighbors (collaborative or content). method ∈ {cooccurrence, copurchase, content}."""

    __tablename__ = "item_similarity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    neighbor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_itemsim_product_method", "product_id", "method", "score"),)
