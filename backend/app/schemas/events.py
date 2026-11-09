from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "search", "impression", "click", "product_view", "add_to_cart", "purchase", "rec_impression", "rec_click"
]


class EventIn(BaseModel):
    event_type: EventType
    user_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    ts: datetime | None = None
    query: str | None = None
    query_id: int | None = None
    product_id: int | None = None
    position: int | None = None
    result_count: int | None = None
    experiment_key: str | None = None
    variant: str | None = None
    ranking_model_version: str | None = None
    strategy: str | None = None
    revenue: float | None = None
    quantity: int | None = None
    latency_ms: float | None = None
    source: str | None = None
    metadata: dict | None = None


class EventsBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class PurchaseIn(BaseModel):
    user_id: str
    session_id: str
    items: list[dict]  # [{product_id, quantity}]
    experiment_key: str | None = None
    variant: str | None = None
    source: str | None = None
