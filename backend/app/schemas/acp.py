"""Request bodies of the Agentic Checkout Specification (2025-09-29) and the Delegated Payment Specification.
Responses are built as plain dicts in `acp_service` so they match the spec objects field for field."""

from typing import Literal

from pydantic import BaseModel, Field

API_VERSION = "2025-09-29"


class Item(BaseModel):
    id: str = Field(min_length=1, max_length=32)  # product id as a string, as feeds publish it
    quantity: int = Field(ge=1, le=99)


class Address(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    line_one: str = Field(min_length=1, max_length=200)
    line_two: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=50)
    country: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=20)


class Buyer(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None


class CreateSessionIn(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=50)
    buyer: Buyer | None = None
    fulfillment_address: Address | None = None


class UpdateSessionIn(BaseModel):
    items: list[Item] | None = Field(default=None, max_length=50)
    buyer: Buyer | None = None
    fulfillment_address: Address | None = None
    fulfillment_option_id: str | None = None


class PaymentData(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    provider: str = "smartsearch_mock"
    billing_address: Address | None = None


class CompleteSessionIn(BaseModel):
    payment_data: PaymentData
    buyer: Buyer | None = None


class PaymentMethod(BaseModel):
    type: Literal["card"]
    card_number_type: Literal["fpan", "network_token"] = "fpan"
    number: str = Field(min_length=12, max_length=19)
    exp_month: str = Field(min_length=1, max_length=2)
    exp_year: str = Field(min_length=2, max_length=4)
    name: str | None = None
    cvc: str | None = None
    display_card_funding_type: Literal["credit", "debit", "prepaid"] = "credit"
    display_brand: str | None = None
    display_last4: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class Allowance(BaseModel):
    reason: Literal["one_time"]
    max_amount: int = Field(ge=1)  # minor units
    currency: str = Field(min_length=3, max_length=3)
    checkout_session_id: str
    merchant_id: str
    expires_at: str  # RFC 3339


class DelegatePaymentIn(BaseModel):
    payment_method: PaymentMethod
    allowance: Allowance
    billing_address: Address | None = None
    risk_signals: list[dict] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
