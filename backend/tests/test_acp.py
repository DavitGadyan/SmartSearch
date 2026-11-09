"""Agentic Checkout rules: pricing, readiness, shipping threshold, allowance checks, idempotency hashing."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.acp_service import (
    AcpError,
    build_session,
    check_allowance,
    fulfillment_options,
    price_items,
    request_hash,
)

LOOKUP = {
    39786: (19899, True, "larson 2 - drawer nightstand"),
    5008: (15000, False, "bertold 2 drawer nightstand"),
    523: (4999, True, "360 cookware slow cooker base"),
}
ADDRESS = {
    "name": "Demo Shopper",
    "line_one": "1 Market Street",
    "city": "San Francisco",
    "state": "CA",
    "country": "US",
    "postal_code": "94105",
}


def total_of(session: dict) -> int:
    return next(t["amount"] for t in session["totals"] if t["type"] == "total")


def test_line_items_carry_tax_and_minor_units() -> None:
    lines, messages = price_items([{"id": "39786", "quantity": 2}], LOOKUP)
    assert messages == []
    (li,) = lines
    assert li["item"] == {"id": "39786", "quantity": 2}
    assert li["base_amount"] == 39798 and li["tax"] == 3184 and li["total"] == 42982


def test_unknown_and_out_of_stock_items_become_error_messages() -> None:
    lines, messages = price_items([{"id": "5008", "quantity": 1}, {"id": "999999", "quantity": 1}], LOOKUP)
    assert len(lines) == 1
    assert [m["code"] for m in messages] == ["out_of_stock", "invalid"]
    assert messages[0]["param"] == "$.line_items[0]"


def test_standard_shipping_is_free_over_threshold() -> None:
    cheap = {o["id"]: o["total"] for o in fulfillment_options(4999)}
    pricey = {o["id"]: o["total"] for o in fulfillment_options(19899)}
    assert cheap == {"standard": 999, "express": 1999}
    assert pricey == {"standard": 0, "express": 1999}


def test_session_is_ready_only_with_address_and_option() -> None:
    base = dict(session_id="cs_1", status=None, items=[{"id": "523", "quantity": 1}], lookup=LOOKUP)
    assert (
        build_session(**base, fulfillment_address=None, fulfillment_option_id=None)["status"]
        == "not_ready_for_payment"
    )
    assert (
        build_session(**base, fulfillment_address=ADDRESS, fulfillment_option_id=None)["status"]
        == "not_ready_for_payment"
    )
    ready = build_session(**base, fulfillment_address=ADDRESS, fulfillment_option_id="standard")
    assert ready["status"] == "ready_for_payment"
    assert total_of(ready) == 4999 + 400 + 999  # items + 8% tax + standard shipping under $75


def test_out_of_stock_blocks_readiness_and_terminal_status_is_kept() -> None:
    s = build_session(
        session_id="cs_2",
        status=None,
        items=[{"id": "5008", "quantity": 1}],
        lookup=LOOKUP,
        fulfillment_address=ADDRESS,
        fulfillment_option_id="express",
    )
    assert s["status"] == "not_ready_for_payment"
    done = build_session(
        session_id="cs_3",
        status="completed",
        items=[{"id": "523", "quantity": 1}],
        lookup=LOOKUP,
        fulfillment_address=ADDRESS,
        fulfillment_option_id="standard",
    )
    assert done["status"] == "completed"


def test_allowance_rules() -> None:
    later = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    earlier = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    check_allowance({"currency": "usd", "max_amount": 5000, "expires_at": later}, 5000)
    with pytest.raises(AcpError) as e:
        check_allowance({"currency": "usd", "max_amount": 4999, "expires_at": later}, 5000)
    assert e.value.status == 402 and e.value.code == "payment_declined"
    with pytest.raises(AcpError) as e:
        check_allowance({"currency": "usd", "max_amount": 9000, "expires_at": earlier}, 5000)
    assert e.value.code == "token_expired"
    with pytest.raises(AcpError) as e:
        check_allowance({"currency": "eur", "max_amount": 9000, "expires_at": later}, 5000)
    assert e.value.code == "currency_mismatch"


def test_request_hash_ignores_key_order() -> None:
    assert request_hash({"a": 1, "b": [1, 2]}) == request_hash({"b": [1, 2], "a": 1})
    assert request_hash({"a": 1}) != request_hash({"a": 2})
