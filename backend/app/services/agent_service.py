"""AI Shopping Agent: a Claude tool-use loop over our own search/ranking APIs."""

import json
import re
import time
from datetime import UTC, datetime

import anthropic
import numpy as np
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.decision.policies import farewell, grade_relevance, route_agent, small_talk
from app.models import Event
from app.schemas.acp import Item
from app.schemas.agent import CartAction, CartLine, ChatMessage, ChatResponse, ToolTrace
from app.schemas.catalog import ProductOut
from app.services import acp_service, search_service
from app.services.events_service import ensure_user_session
from app.services.runtime import runtime

log = get_logger("agent")
MAX_TURNS = 6

SYSTEM_PROMPT = """You are the shopping assistant for SmartSearch, a home and furniture store.

How you work:
- Use search_products to find items. Our ranker already personalizes results for this shopper; trust its order.
- Only ever recommend products returned by a tool in this conversation. Never invent products, prices or attributes.
- Extract the shopper's constraints (budget, room, style, material, color, size, use) and pass them as filters.
- If the request is too vague to search well, ask ONE short clarifying question instead of searching.
- Greetings, thanks and small talk are not product requests: reply in one or two friendly sentences, say what
  you can do (search the store, compare options, add to the cart, check out) and ask what they are looking for.
  Never call search_products for a message that names nothing to buy.
- When you have good options, call present_results with 3 to 6 products and a one-sentence reason each that cites
  real attributes from the tool output (price, style, material, rating). Keep the message under 80 words.
- Mention the budget explicitly when one was given. Prefer in-stock items.
- graph_topic finds themed product clusters; graph_complements finds items that go with a product (bundles, gifts).
- add_to_cart puts an item in the shopper's cart. Use it only when the shopper explicitly asks to add, buy or take an
  item, and only for a product a tool returned in this conversation or one listed under [Shown: ...] in an earlier
  turn. Never add anything unasked. Confirm what you added in the message, then call present_results as usual.
- Checkout runs over the Agentic Commerce Protocol. start_checkout prices the items the shopper wants (or their
  whole cart with use_cart=true) and returns line items, shipping options and totals in cents; show the summary in
  dollars and ask the shopper to confirm. Call complete_checkout only when the shopper's latest message explicitly
  confirms the order (for example "yes, place the order"). Never start or complete a checkout unasked."""

_CART_INTENT = re.compile(r"\b(cart|basket|buy|purchase|checkout|check out|order)\b", re.I)


def cart_intent(text: str) -> bool:
    """Messages about the cart always go to the LLM: the direct-search shortcut cannot act on them."""
    return bool(_CART_INTENT.search(text))


TOOLS: list[dict] = [
    {
        "name": "search_products",
        "description": "Search the store catalog with our personalized ranker. Returns ranked products with id, name, category, brand, price, rating, review count, stock status and key attributes.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query, e.g. 'mid-century walnut nightstand'",
                },
                "price_max": {"type": ["number", "null"], "description": "Maximum price in USD, or null"},
                "price_min": {"type": ["number", "null"], "description": "Minimum price in USD, or null"},
                "in_stock_only": {"type": "boolean"},
                "limit": {"type": "integer", "description": "1 to 12"},
            },
            "required": ["query", "price_max", "price_min", "in_stock_only", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_product",
        "description": "Full details for one product id: description excerpt and all attributes.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "integer"}},
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "similar_products",
        "description": "Products similar to a given product id (embedding nearest neighbours).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "limit": {"type": "integer", "description": "1 to 12"},
            },
            "required": ["product_id", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "graph_complements",
        "description": "Products that go with a given product according to the store knowledge graph (co-purchase, co-view, category adjacency). Use for 'what else would I need' and gift bundles.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "limit": {"type": "integer", "description": "1 to 8"},
            },
            "required": ["product_id", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "graph_topic",
        "description": "Explore the knowledge graph by theme: returns product communities (name, summary, sample products) closest to a topic such as 'cozy balcony' or 'camping cookware'. Use before searching when the request is thematic.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a product to the shopper's cart, only when the shopper explicitly asked for it. The product id must come from a tool result in this conversation or from a [Shown: ...] list in an earlier turn.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "quantity": {"type": "integer", "description": "1 to 10"},
            },
            "required": ["product_id", "quantity"],
            "additionalProperties": False,
        },
    },
    {
        "name": "start_checkout",
        "description": "Start an Agentic Commerce Protocol checkout for the items the shopper wants to buy, or for their whole cart (use_cart=true). Returns the priced checkout session: line items, shipping options and totals in cents. Only when the shopper asks to buy or check out; then summarise and ask for confirmation.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "properties": {"product_id": {"type": "integer"}, "quantity": {"type": "integer"}},
                        "required": ["product_id", "quantity"],
                        "additionalProperties": False,
                    },
                },
                "use_cart": {"type": "boolean"},
            },
            "required": ["items", "use_cart"],
            "additionalProperties": False,
        },
    },
    {
        "name": "complete_checkout",
        "description": "Place the order for a checkout session the shopper has explicitly confirmed in their latest message. Picks the shipping option, obtains a delegated payment token and completes the Agentic Commerce Protocol session.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "checkout_session_id": {"type": "string"},
                "fulfillment_option_id": {"type": "string", "description": "standard or express"},
            },
            "required": ["checkout_session_id", "fulfillment_option_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "present_results",
        "description": "Finish the turn: show the shopper a short message plus the recommended products. Call this exactly once when you are ready to recommend (or with an empty products list to ask a clarifying question).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"product_id": {"type": "integer"}, "reason": {"type": "string"}},
                        "required": ["product_id", "reason"],
                        "additionalProperties": False,
                    },
                },
                "preferences": {
                    "type": "object",
                    "description": "Constraints extracted from the conversation so far",
                    "properties": {
                        "budget_max": {"type": ["number", "null"]},
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "styles": {"type": "array", "items": {"type": "string"}},
                        "materials": {"type": "array", "items": {"type": "string"}},
                        "colors": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": ["string", "null"]},
                    },
                    "required": ["budget_max", "categories", "styles", "materials", "colors", "notes"],
                    "additionalProperties": False,
                },
            },
            "required": ["message", "products", "preferences"],
            "additionalProperties": False,
        },
    },
]


def _compact(p: ProductOut) -> dict:
    a = p.attributes or {}
    return {
        "id": p.id,
        "name": p.name,
        "category": p.product_class,
        "brand": p.brand,
        "price": p.price,
        "rating": p.rating,
        "reviews": p.review_count,
        "in_stock": p.in_stock,
        **{
            k: a[k]
            for k in ("style", "material", "color", "shape", "width_in", "height_in", "depth_in")
            if a.get(k) is not None
        },
    }


class _Tools:
    def __init__(
        self, db: AsyncSession, user_id: str, session_id: str, cart: list[CartLine] | None = None
    ) -> None:
        self.db, self.user_id, self.session_id = db, user_id, session_id
        self.cart = cart or []
        self.seen: dict[int, ProductOut] = {}
        self.trace: list[ToolTrace] = []
        self.actions: list[CartAction] = []

    async def run(self, name: str, inp: dict) -> tuple[str, bool]:
        try:
            if name == "search_products":
                filters = {
                    k: v
                    for k, v in {
                        "price_max": inp.get("price_max"),
                        "price_min": inp.get("price_min"),
                        "in_stock": inp.get("in_stock_only") or None,
                    }.items()
                    if v
                }
                res = await search_service.search(
                    self.db,
                    inp["query"],
                    self.user_id,
                    self.session_id,
                    1,
                    min(12, max(1, int(inp.get("limit") or 8))),
                    filters,
                    None,
                    False,
                    True,
                    source="agent",
                )
                for it in res.items:
                    self.seen[it.id] = it
                self.trace.append(
                    ToolTrace(
                        tool=name,
                        input=inp,
                        summary=f"{res.total} results · {res.strategy} · {res.latency_ms} ms",
                    )
                )
                return json.dumps(
                    {
                        "total": res.total,
                        "intent": res.parsed.get("top_class"),
                        "results": [_compact(i) for i in res.items],
                    }
                ), False
            if name == "get_product":
                pos = runtime.catalog.id_to_pos.get(int(inp["product_id"]))
                if pos is None:
                    return "Error: unknown product id", True
                rec = runtime.catalog.record(pos)
                self.seen[rec["id"]] = ProductOut(**rec)
                self.trace.append(ToolTrace(tool=name, input=inp, summary=rec["name"][:60]))
                return json.dumps(_compact(ProductOut(**rec)) | {"attributes": rec["attributes"]}), False
            if name == "similar_products":
                items = search_service.similar_products(
                    int(inp["product_id"]), min(12, max(1, int(inp.get("limit") or 6)))
                )
                for it in items:
                    self.seen[it.id] = it
                self.trace.append(ToolTrace(tool=name, input=inp, summary=f"{len(items)} neighbours"))
                return json.dumps([_compact(i) for i in items]), False
            if name == "graph_complements":
                kg = runtime.graph
                if kg is None:
                    return "Error: knowledge graph not built", True
                out = []
                for pid, score, rel in kg.complements(
                    int(inp["product_id"]), min(8, max(1, int(inp.get("limit") or 6)))
                ):
                    pos = runtime.catalog.id_to_pos.get(pid)
                    if pos is None:
                        continue
                    rec = runtime.catalog.record(pos)
                    self.seen[pid] = ProductOut(**rec)
                    out.append(_compact(ProductOut(**rec)) | {"relation": rel, "strength": round(score, 3)})
                self.trace.append(ToolTrace(tool=name, input=inp, summary=f"{len(out)} complements"))
                return json.dumps(out), False
            if name == "graph_topic":
                kg = runtime.graph
                if kg is None:
                    return "Error: knowledge graph not built", True
                hits = kg.topic_search(runtime.embedder.encode_one(inp["topic"]), k=3)
                for h in hits:
                    h["sample_products"] = []
                    for pid in h.get("products", [])[:6]:
                        pos = runtime.catalog.id_to_pos.get(pid)
                        if pos is not None:
                            rec = runtime.catalog.record(pos)
                            self.seen[pid] = ProductOut(**rec)
                            h["sample_products"].append(_compact(ProductOut(**rec)))
                    h.pop("products", None)
                    h.pop("sample_names", None)
                self.trace.append(
                    ToolTrace(tool=name, input=inp, summary=", ".join(h.get("name", "?") for h in hits))
                )
                return json.dumps(hits, default=str), False
            if name == "add_to_cart":
                pid = int(inp["product_id"])
                it = self.seen.get(pid)
                if it is None:
                    return (
                        "Error: unknown product id; only products a tool returned or that were shown earlier can be added",
                        True,
                    )
                if not it.in_stock:
                    return f"Error: {it.name} is out of stock and cannot be added", True
                qty = min(10, max(1, int(inp.get("quantity") or 1)))
                self.actions.append(CartAction(product_id=pid, quantity=qty, product=it))
                self.trace.append(ToolTrace(tool=name, input=inp, summary=f"{it.name[:50]} × {qty}"))
                return json.dumps(
                    {
                        "added": _compact(it),
                        "quantity": qty,
                        "note": "It appears in the shopper's cart with this turn.",
                    }
                ), False
            if name == "start_checkout":
                if inp.get("use_cart"):
                    wanted = [{"id": str(c.product_id), "quantity": c.quantity} for c in self.cart]
                else:
                    wanted = [
                        {"id": str(int(i["product_id"])), "quantity": int(i.get("quantity") or 1)}
                        for i in (inp.get("items") or [])
                    ]
                if not wanted:
                    return "Error: nothing to check out (empty cart and no items given)", True
                for w in wanted:
                    pos = runtime.catalog.id_to_pos.get(int(w["id"]))
                    if pos is not None:
                        rec = runtime.catalog.record(pos)
                        self.seen.setdefault(rec["id"], ProductOut(**rec))
                items = [Item(**w) for w in wanted]
                view = await acp_service.create_session(
                    self.db, items, None, acp_service.demo_address(), self.user_id, self.session_id
                )
                self.trace.append(
                    ToolTrace(
                        tool=name,
                        input=inp,
                        summary=f"{view['id']} · {view['status']} · {len(view['line_items'])} lines",
                    )
                )
                return json.dumps(_checkout_summary(view, self.seen)), False
            if name == "complete_checkout":
                view = await acp_service.agent_checkout(
                    self.db,
                    inp["checkout_session_id"],
                    inp.get("fulfillment_option_id") or "standard",
                    "Demo Shopper",
                )
                self.trace.append(ToolTrace(tool=name, input=inp, summary=f"{view['id']} · {view['status']}"))
                if view["status"] != "completed":
                    return json.dumps({"status": view["status"], "messages": view["messages"]}), True
                total = next(t["amount"] for t in view["totals"] if t["type"] == "total") / 100
                self.actions.append(
                    CartAction(
                        type="order_placed",
                        order_id=view["order"]["id"],
                        checkout_session_id=view["id"],
                        total=total,
                    )
                )
                return json.dumps(
                    {"status": "completed", "order_id": view["order"]["id"], "total_usd": total}
                ), False
            return f"Error: unknown tool {name}", True
        except Exception as e:  # tool failures go back to the model, never crash the turn
            log.exception("tool %s failed", name)
            return f"Error: {e}", True


async def _log_presented(db: AsyncSession, user_id: str, session_id: str, items: list[ProductOut]) -> None:
    if not items:
        return
    now = datetime.now(UTC)
    await ensure_user_session(db, user_id, session_id, now)
    await db.execute(
        insert(Event),
        [
            dict(
                ts=now,
                user_id=user_id,
                session_id=session_id,
                event_type="rec_impression",
                product_id=it.id,
                position=i + 1,
                source="agent",
            )
            for i, it in enumerate(items)
        ],
    )
    await db.commit()


def history_messages(history: list[ChatMessage], tools: _Tools) -> list[dict]:
    """Replay the conversation for the model. Assistant turns get a [Shown: ...] line with the products they
    displayed, so the model can refer to them (and add_to_cart can trust them) without searching again."""
    out = []
    for m in history:
        content = m.content
        if m.role == "assistant" and m.product_ids:
            shown = []
            for pid in m.product_ids:
                pos = runtime.catalog.id_to_pos.get(pid)
                if pos is None:
                    continue
                rec = runtime.catalog.record(pos)
                tools.seen.setdefault(pid, ProductOut(**rec))
                stock = "" if rec["in_stock"] else ", out of stock"
                shown.append(f"#{pid} {rec['name'][:60]} (${rec['price']:.2f}{stock})")
            if shown:
                content += "\n\n[Shown: " + "; ".join(shown) + "]"
        out.append({"role": m.role, "content": content})
    return out


def _assemble(
    tools: _Tools, presented: dict | None, fallback_text: str
) -> tuple[str, list[ProductOut], dict]:
    if presented:
        items = []
        for i, p in enumerate(presented.get("products", [])[:6]):
            it = tools.seen.get(int(p.get("product_id", -1)))
            if it is not None:  # ids the model did not get from a tool are dropped
                items.append(
                    it.model_copy(update={"position": i + 1, "explanation": {"reason": p.get("reason", "")}})
                )
        return (
            presented.get("message", "").strip() or fallback_text,
            items,
            presented.get("preferences") or {},
        )
    return fallback_text, [], {}


def _checkout_summary(view: dict, seen: dict[int, ProductOut]) -> dict:
    """What the model needs to summarise a priced session: names, quantities and dollar amounts."""
    return {
        "checkout_session_id": view["id"],
        "status": view["status"],
        "line_items": [
            {
                "product_id": int(li["item"]["id"]),
                "name": seen[int(li["item"]["id"])].name if int(li["item"]["id"]) in seen else None,
                "quantity": li["item"]["quantity"],
                "total_usd": li["total"] / 100,
            }
            for li in view["line_items"]
        ],
        "fulfillment_options": [
            {"id": o["id"], "title": o["title"], "price_usd": o["total"] / 100}
            for o in view["fulfillment_options"]
        ],
        "totals_usd": {t["type"]: t["amount"] / 100 for t in view["totals"]},
        "messages": view["messages"],
        "note": "Summarise this to the shopper and ask them to confirm before calling complete_checkout.",
    }


async def chat(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    history: list[ChatMessage],
    cart: list[CartLine] | None = None,
) -> ChatResponse:
    t0 = time.perf_counter()
    last = history[-1].content
    if small_talk(last) and not cart_intent(last):
        # a greeting is not a query: answer it, never search for it
        return await _small_talk_reply(last, t0, {"route": "chat", "p": 1.0, "source": "small-talk"})
    if not settings.anthropic_api_key:
        return await rule_based(db, user_id, session_id, history, t0)
    if len(history) > 1:
        route = {"route": "assistant", "p": 1.0, "source": "multi-turn"}
    elif cart_intent(last):
        route = {"route": "assistant", "p": 1.0, "source": "cart-intent"}
    else:
        route = await route_agent(last)
    if route["route"] == "chat":
        return await _small_talk_reply(last, t0, route)
    if (
        route["route"] == "direct_search" and route["p"] >= 0.7
    ):  # cheap path: no LLM call for plain product queries
        resp = await rule_based(db, user_id, session_id, history, t0)
        resp.decisions = {"route": route}
        return resp

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tools = _Tools(db, user_id, session_id, cart)
    messages: list = history_messages(history, tools)
    presented: dict | None = None
    text_answer = ""
    stop_reason = None

    for _ in range(MAX_TURNS):
        resp = await client.beta.messages.create(
            model=settings.agent_model,
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
            output_config={"effort": settings.agent_effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        stop_reason = resp.stop_reason
        text_answer = " ".join(b.text for b in resp.content if b.type == "text").strip() or text_answer
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "refusal":
            text_answer = (
                "I can't help with that request, but I'm happy to help you find products in our store."
            )
            break
        if not tool_uses:
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for tu in tool_uses:
            if tu.name == "present_results":
                presented = dict(tu.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": "shown to the shopper"}
                )
            else:
                content, is_error = await tools.run(tu.name, dict(tu.input))
                results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": content, "is_error": is_error}
                )
        messages.append({"role": "user", "content": results})
        if presented is not None:
            break

    message, items, prefs = _assemble(tools, presented, text_answer or "Here is what I found.")
    items, judged = await _relevance_guardrail(history[-1].content, items)
    await _log_presented(db, user_id, session_id, items)
    return ChatResponse(
        message=message,
        products=items,
        preferences=prefs,
        trace=tools.trace,
        provider="claude",
        model=settings.agent_model,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        stop_reason=stop_reason,
        decisions={"route": route, "relevance": judged},
        actions=tools.actions,
    )


GREETING = (
    "Hi! I'm the SmartSearch assistant. Tell me what you're looking for, with a room, a style or a budget if you "
    "have one, and I'll search the store, compare options and add anything you like to your cart."
)
FAREWELL = "You're welcome! Come back whenever you need something for your home."


async def _small_talk_reply(message: str, t0: float, route: dict) -> ChatResponse:
    """A greeting, thanks or goodbye: a short reply and no products. Claude writes it when a key is set."""
    text = FAREWELL if farewell(message) else GREETING
    provider, model = "rule_based", None
    if settings.anthropic_api_key:
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.messages.create(
                model=settings.agent_model,
                max_tokens=160,
                system=SYSTEM_PROMPT
                + "\n\nThe shopper's message is small talk. Reply in at most two sentences, no product names, and end "
                "by asking what they are looking for (or say goodbye if they are leaving).",
                messages=[{"role": "user", "content": message}],
            )
            text = " ".join(b.text for b in resp.content if b.type == "text").strip() or text
            provider, model = "claude", settings.agent_model
        except Exception:  # the fixed line is a fine answer to "hi"
            pass
    return ChatResponse(
        message=text,
        products=[],
        preferences={},
        trace=[],
        provider=provider,
        model=model,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        decisions={"route": route},
    )


async def _relevance_guardrail(query: str, items: list[ProductOut]) -> tuple[list[ProductOut], list[dict]]:
    """Grade each presented product against the request; drop confident misses when a remote decision backend is on."""
    if not items:
        return items, []
    c = runtime.catalog
    qvec = runtime.embedder.encode_one(query)
    sims = np.array([float(c.emb[c.id_to_pos[it.id]] @ qvec) for it in items])
    judged = await grade_relevance(query, [it.model_dump() for it in items], c, sims)
    remote = bool(judged) and judged[0]["source"] in ("openrouter", "foundry")
    kept = []
    for it, j in zip(items, judged, strict=True):
        if remote and j["p_irrelevant"] > 0.6:
            continue
        kept.append(it.model_copy(update={"explanation": {**(it.explanation or {}), "relevance": j}}))
    return kept, judged


async def rule_based(
    db: AsyncSession, user_id: str, session_id: str, history: list[ChatMessage], t0: float
) -> ChatResponse:
    """No LLM available: treat the latest user message as a search query (price constraints are parsed by the engine)."""
    last = next((m.content for m in reversed(history) if m.role == "user"), "")
    res = await search_service.search(
        db, last, user_id, session_id, 1, 6, {}, None, False, True, source="agent"
    )
    items = [
        it.model_copy(
            update={"explanation": {"reason": f"Top match for “{last}” from the personalized ranker"}}
        )
        for it in res.items
    ]
    await _log_presented(db, user_id, session_id, items)
    prefs = {
        "budget_max": res.parsed.get("price_max"),
        "categories": [res.parsed["top_class"]] if res.parsed.get("top_class") else [],
    }
    msg = (
        f"Here are the top {len(items)} matches for “{last}”"
        + (f" under ${res.parsed['price_max']:.0f}" if res.parsed.get("price_max") else "")
        + (
            ". Set ANTHROPIC_API_KEY to enable the conversational assistant."
            if not settings.anthropic_api_key
            else "."
        )
    )
    return ChatResponse(
        message=msg,
        products=items,
        preferences=prefs,
        trace=[
            ToolTrace(
                tool="search_products", input={"query": last}, summary=f"{res.total} results · {res.strategy}"
            )
        ],
        provider="rule_based",
        model=None,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
