"""Decision points backed by Microsoft-Decision-1 (with local approximations when no backend is configured).

1. classify_intent   - which catalog category does this query want?       (choice)
2. route_agent       - direct search, clarifying question, or full agent?  (choice)
3. grade_relevance   - how relevant is each product to the query?          (score: Irrelevant / Partial / Exact)
"""

import re

import numpy as np

from app.core.config import settings
from app.decision.client import Decision, get_decision_client
from app.ml.catalog_cache import CatalogCache
from app.ml.query import ClassIndex, ParsedQuery

GRADES = ["Irrelevant", "Partial match", "Exact match"]
ROUTES = {
    "chat": "A greeting, thanks or small talk that names nothing to buy (e.g. 'hi', 'thanks!'); reply briefly, do not search",
    "direct_search": "A concrete product request that a search box can answer as is (e.g. 'walnut nightstand under 200')",
    "clarify": "Too vague to search well; one clarifying question is needed (e.g. 'something nice for the living room')",
    "assistant": "Needs reasoning across constraints, comparisons or gift ideas (e.g. 'gift for a hiker who cooks, $100')",
}


_TALK_TOKEN = (
    r"(?:hi|hii+|hey|heya|hello|hallo|hola|yo|sup|good\s+(?:morning|afternoon|evening|day|night)|greetings|"
    r"thanks?|thank\s+you|thx|ty|cheers|ok(?:ay)?|k|cool|great|nice|awesome|perfect|got\s+it|sounds\s+good|"
    r"bye|goodbye|see\s+you|later|how\s+are\s+you|how'?s\s+it\s+going|what'?s\s+up|who\s+are\s+you|"
    r"what\s+can\s+you\s+do|what\s+do\s+you\s+do|can\s+you\s+help(?:\s+me)?|help|test|testing|"
    r"there|you|again|a\s+lot|so\s+much|very\s+much|please|pls|bot|assistant|smartsearch)"
)
_SMALL_TALK = re.compile(rf"^\W*(?:{_TALK_TOKEN}[\s,!.?]*)+$", re.I)
_FAREWELL = re.compile(r"\b(thank|thanks|thx|ty|cheers|bye|goodbye|see\s+you|later)\b", re.I)


def small_talk(text: str) -> bool:
    """True for greetings, thanks, goodbyes and 'what can you do' with no product request in them."""
    return bool(_SMALL_TALK.match(text.strip()))


def farewell(text: str) -> bool:
    return bool(_FAREWELL.search(text))


def _softmax(x: np.ndarray, temp: float = 0.05) -> np.ndarray:
    z = (x - x.max()) / temp
    e = np.exp(z)
    return e / e.sum()


async def classify_intent(pq: ParsedQuery, classes: ClassIndex, top_k: int = 6) -> dict:
    """Pick the query's category among the top-k embedding candidates (+ 'other'). Returns {class, p, source, candidates}."""
    if pq.class_sims is None or len(classes.names) == 0:
        return {"class": None, "p": 0.0, "source": "none", "candidates": {}}
    idx = np.argsort(-pq.class_sims)[:top_k]
    cands = {classes.names[i]: float(pq.class_sims[i]) for i in idx}
    criteria = {c: f"Products in the '{c}' category" for c in cands} | {"other": "None of these categories"}

    def local() -> dict:
        p = _softmax(np.array(list(cands.values())))
        probs = {c: float(x) for c, x in zip(cands, p, strict=True)} | {"other": 0.0}
        return {"intent": {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs}}

    d: Decision = await get_decision_client().decide(
        {"query": pq.raw},
        {
            "intent": {
                "type": "choice",
                "instructions": "Which product category is the shopper looking for?",
                "criteria": criteria,
            }
        },
        local=local,
    )
    a = d.answers.get("intent", {})
    probs = a.get("probabilities") or {}
    choice = a.get("choice") or (max(probs, key=probs.get) if probs else None)
    p = float(probs.get(choice, 0.0)) if choice else 0.0
    return {
        "class": None if choice in (None, "other") else choice,
        "p": round(p, 4),
        "source": d.backend,
        "candidates": {k: round(v, 3) for k, v in probs.items()},
        "latency_ms": round(d.latency_ms, 1),
    }


async def route_agent(message: str) -> dict:
    def local() -> dict:
        m = message.lower()
        vague = any(
            w in m
            for w in ("gift", "idea", "something", "help", "recommend", "what should", "cozy", "nice", "?")
        )
        short = len(m.split()) <= 7
        if small_talk(m):
            choice = "chat"
        else:
            choice = "assistant" if vague else ("direct_search" if short else "assistant")
        probs = {
            "chat": 0.9 if choice == "chat" else 0.0,
            "direct_search": 0.75 if choice == "direct_search" else (0.05 if choice == "chat" else 0.15),
            "clarify": 0.1 if choice != "chat" else 0.0,
            "assistant": 0.75 if choice == "assistant" else (0.05 if choice == "chat" else 0.15),
        }
        return {"route": {"type": "choice", "choice": choice, "probabilities": probs}}

    d = await get_decision_client().decide(
        {"shopper_message": message},
        {
            "route": {
                "type": "choice",
                "instructions": "How should a furniture store handle this shopper message?",
                "criteria": ROUTES,
            }
        },
        local=local,
    )
    a = d.answers.get("route", {})
    probs = a.get("probabilities") or {}
    choice = a.get("choice") or (max(probs, key=probs.get) if probs else "assistant")
    return {
        "route": choice,
        "p": round(float(probs.get(choice, 0.0)), 4),
        "probabilities": probs,
        "source": d.backend,
        "latency_ms": round(d.latency_ms, 1),
    }


async def grade_relevance(
    query: str, products: list[dict], cache: CatalogCache | None = None, sims: np.ndarray | None = None
) -> list[dict]:
    """Expected relevance grade (0-2) per product with per-level probabilities. Batched: one state, one score question per product."""
    if not products:
        return []
    state = {
        "query": query,
        "products": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p.get("product_class"),
                "attributes": {
                    k: p.get("attributes", {}).get(k)
                    for k in ("style", "material", "color")
                    if p.get("attributes", {}).get(k)
                },
            }
            for p in products
        ],
    }
    questions = {
        f"rel_{i}": {
            "type": "score",
            "instructions": f"How relevant is product #{i + 1} ({p['name']}) to the query?",
            "criteria": GRADES,
        }
        for i, p in enumerate(products)
    }

    def local() -> dict:
        out = {}
        for i, _ in enumerate(products):
            s = float(sims[i]) if sims is not None else 0.5
            p2 = float(np.clip((s - 0.45) / 0.3, 0.02, 0.96))
            p1 = float(np.clip((s - 0.25) / 0.4, 0.02, 0.96)) * (1 - p2)
            p0 = max(0.0, 1 - p1 - p2)
            out[f"rel_{i}"] = {
                "type": "score",
                "score": p1 + 2 * p2,
                "probabilities": {GRADES[0]: p0, GRADES[1]: p1, GRADES[2]: p2},
            }
        return out

    d = await get_decision_client().decide(state, questions, local=local)
    res = []
    for i, p in enumerate(products):
        a = d.answers.get(f"rel_{i}", {})
        probs = a.get("probabilities") or {}
        plist = [float(probs.get(g, 0.0)) for g in GRADES]
        expected = a.get("score")
        if expected is None:
            expected = sum(k * v for k, v in enumerate(plist)) / (sum(plist) or 1)
        res.append(
            {
                "product_id": p["id"],
                "expected_grade": round(float(expected), 3),
                "p_irrelevant": round(plist[0], 3),
                "p_exact": round(plist[2], 3),
                "source": d.backend,
            }
        )
    return res


def intent_enabled() -> bool:
    return settings.decision_intent_threshold > 0
