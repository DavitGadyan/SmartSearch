from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import ProductOut


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    product_ids: list[int] = Field(
        default_factory=list, max_length=12
    )  # products an assistant turn displayed


class CartLine(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    cart: list[CartLine] = Field(
        default_factory=list, max_length=50
    )  # the browser cart, so "check out my cart" works


class ToolTrace(BaseModel):
    tool: str
    input: dict
    summary: str


class CartAction(BaseModel):
    """Something the agent did on the shopper's request. `add_to_cart` is applied by the storefront to the browser
    cart; `order_placed` means an Agentic Commerce Protocol checkout completed and the cart should be cleared."""

    type: Literal["add_to_cart", "order_placed"] = "add_to_cart"
    product_id: int | None = None
    quantity: int | None = Field(default=None, ge=1, le=99)
    product: ProductOut | None = None
    order_id: str | None = None
    checkout_session_id: str | None = None
    total: float | None = None  # dollars


class ChatResponse(BaseModel):
    message: str
    products: list[ProductOut]
    preferences: dict
    trace: list[ToolTrace]
    provider: Literal["claude", "rule_based"]
    model: str | None
    latency_ms: float
    stop_reason: str | None = None
    decisions: dict = Field(default_factory=dict)
    actions: list[CartAction] = Field(default_factory=list)
