"""Agent cart actions: only explicitly surfaced, in-stock products can be added, and cart talk never takes the
direct-search shortcut."""

import json

from app.schemas.catalog import ProductOut
from app.services.agent_service import _Tools, cart_intent

NIGHTSTAND = ProductOut(
    id=39786, name="larson 2 - drawer nightstand", product_class="Nightstands", price=198.99
)
SOLD_OUT = ProductOut(id=5008, name="bertold 2 drawer nightstand", price=150.0, in_stock=False)


async def test_add_to_cart_requires_a_surfaced_product() -> None:
    tools = _Tools(db=None, user_id="u", session_id="s")  # type: ignore[arg-type]
    content, is_error = await tools.run("add_to_cart", {"product_id": 39786, "quantity": 1})
    assert is_error and "unknown product" in content
    assert tools.actions == []


async def test_add_to_cart_records_an_action_and_clamps_quantity() -> None:
    tools = _Tools(db=None, user_id="u", session_id="s")  # type: ignore[arg-type]
    tools.seen[NIGHTSTAND.id] = NIGHTSTAND
    content, is_error = await tools.run("add_to_cart", {"product_id": 39786, "quantity": 99})
    assert not is_error
    assert json.loads(content)["quantity"] == 10
    assert [(a.product_id, a.quantity, a.product.name) for a in tools.actions] == [
        (39786, 10, NIGHTSTAND.name)
    ]
    assert tools.trace[-1].tool == "add_to_cart"


async def test_add_to_cart_refuses_out_of_stock() -> None:
    tools = _Tools(db=None, user_id="u", session_id="s")  # type: ignore[arg-type]
    tools.seen[SOLD_OUT.id] = SOLD_OUT
    content, is_error = await tools.run("add_to_cart", {"product_id": 5008, "quantity": 1})
    assert is_error and "out of stock" in content
    assert tools.actions == []


def test_cart_intent_routes_to_the_assistant() -> None:
    assert cart_intent("add the Larson nightstand to my cart")
    assert cart_intent("I want to buy the walnut lamp")
    assert not cart_intent("modern walnut nightstand under $200")


# --- greetings are not queries ---------------------------------------------------------------------------------
from app.decision.policies import farewell, small_talk  # noqa: E402


def test_small_talk_detects_greetings_thanks_and_goodbyes():
    for m in (
        "hi",
        "Hi!",
        "hello there",
        "hey, how are you?",
        "thanks!",
        "ok thanks",
        "thank you so much",
        "bye",
        "what can you do?",
        "help",
    ):
        assert small_talk(m), m


def test_small_talk_leaves_product_requests_alone():
    for m in (
        "sofa",
        "hi, I need a walnut nightstand under 200",
        "great sofa",
        "farmhouse dining table",
        "something cozy for a balcony",
        "add it to my cart",
    ):
        assert not small_talk(m), m


def test_farewell_picks_the_goodbye_reply():
    assert farewell("thanks a lot") and farewell("bye!") and not farewell("hello there")
