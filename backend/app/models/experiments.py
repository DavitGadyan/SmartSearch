from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Experiment(Base):
    """An A/B test. `variants` is a list of {key, name, strategy, weight}; weights sum to 1."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )  # draft|running|completed|archived
    surface: Mapped[str] = mapped_column(String(32), nullable=False, default="search")  # search|recs|agent
    variants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    traffic_allocation: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_metric: Mapped[str] = mapped_column(String(64), nullable=False, default="conversion_rate")
    secondary_metrics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    guardrail_metrics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # mde, alpha, power, pre_period_days...
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    experiment_key: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("experiment_key", "user_id", name="uq_assignment_experiment_user"),
        Index("ix_assignments_experiment_variant", "experiment_key", "variant"),
    )
