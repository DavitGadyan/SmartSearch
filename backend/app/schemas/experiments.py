from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UiConfig(BaseModel):
    """Storefront knobs a UI experiment can change. Defaults are what the store shows today."""

    cta_label: str = Field("Add to cart", min_length=1, max_length=32)
    cta_style: Literal["dark", "glass", "accent"] = "dark"
    cta_icon: bool = False
    show_ratings: bool = True
    card_badges: bool = True
    hero_title: str = Field("Search that learns what sells.", max_length=80)
    hero_subtitle: str = Field(
        "Hybrid retrieval, a learned ranker and real A/B tests on a real catalog.", max_length=160
    )
    banner: str | None = Field(None, max_length=120)

    @field_validator("cta_label", "hero_title", "hero_subtitle", mode="before")
    @classmethod
    def blank_means_default(cls, v, info):
        if isinstance(v, str) and not v.strip():
            return cls.model_fields[info.field_name].default
        return v


class VariantIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    name: str | None = None
    description: str | None = None
    strategy: str | None = None
    explore: bool = False
    ui: UiConfig | None = None  # surface "ui": what this arm shows
    effect: dict[str, float] | None = (
        None  # simulation only: assumed relative lifts, e.g. {"add_to_cart_rate": 0.05}
    )
    weight: float = Field(gt=0, le=1)


class ExperimentCreate(BaseModel):
    key: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str
    hypothesis: str | None = None
    surface: Literal["search", "recs", "agent", "ui"] = "search"
    variants: list[VariantIn] = Field(min_length=2)
    traffic_allocation: float = Field(1.0, gt=0, le=1)
    primary_metric: str = "conversion_rate"
    secondary_metrics: list[str] = Field(
        default_factory=lambda: ["search_ctr", "add_to_cart_rate", "revenue_per_visitor", "aov"]
    )
    guardrail_metrics: list[str] = Field(default_factory=lambda: ["zero_result_rate", "no_click_rate"])
    config: dict = Field(
        default_factory=lambda: {"alpha": 0.05, "power": 0.8, "mde_rel": 0.05, "pre_period_days": 7}
    )

    @field_validator("variants")
    @classmethod
    def weights_sum_to_one(cls, v: list[VariantIn]) -> list[VariantIn]:
        if abs(sum(x.weight for x in v) - 1.0) > 1e-6:
            raise ValueError("variant weights must sum to 1")
        return v


class StatusUpdate(BaseModel):
    status: Literal["draft", "running", "completed", "archived"]


class ExperimentOut(BaseModel):
    key: str
    name: str
    hypothesis: str | None
    status: str
    surface: str
    variants: list[dict]
    traffic_allocation: float
    primary_metric: str
    secondary_metrics: list
    guardrail_metrics: list
    config: dict
    start_at: datetime | None
    end_at: datetime | None
    created_at: datetime
    assigned_users: int = 0


class ExposeIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    surface: Literal["ui"] = "ui"


class SimulateIn(BaseModel):
    users: int = Field(3000, ge=200, le=20000)
    days: int = Field(7, ge=1, le=28)
    seed: int = 11


class DraftMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class DraftIn(BaseModel):
    messages: list[DraftMessage] = Field(min_length=1, max_length=40)
    experiment_key: str | None = None  # the test this conversation is about, once created
    proposal: dict | None = None  # the draft shown in the form, so the assistant continues from it
