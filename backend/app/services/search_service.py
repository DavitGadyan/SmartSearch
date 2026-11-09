import time
import uuid
from bisect import bisect_left
from collections import Counter
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bandit.context import action_to_strategy, build_context
from app.core.config import settings
from app.decision.policies import classify_intent
from app.ml.personalization.profile import build_profile
from app.ml.ranking.explain import explain as explain_ranking
from app.ml.ranking.strategies import UserProfile, rank
from app.models import Event
from app.schemas.catalog import Facet, FacetValue, ProductOut, SearchResponse, Suggestion, SuggestResponse
from app.services import experiment_service
from app.services.events_service import ensure_user_session
from app.services.runtime import runtime

DEFAULT_STRATEGY = "hybrid_ltr_personalized"
PRICE_BUCKETS = [(0, 50), (50, 100), (100, 250), (250, 500), (500, 1000), (1000, 10**9)]


def _apply_filters(pos: np.ndarray, f: dict) -> np.ndarray:
    c = runtime.catalog
    mask = np.ones(len(pos), bool)
    if f.get("product_class"):
        mask &= np.isin(c.product_class[pos], f["product_class"])
    if f.get("brand"):
        mask &= np.isin(c.brand[pos], f["brand"])
    if f.get("style"):
        mask &= np.isin(c.style[pos], f["style"])
    if f.get("material"):
        mask &= np.isin(c.material[pos], f["material"])
    if f.get("color"):
        mask &= np.isin(c.color[pos], f["color"])
    if f.get("price_min") is not None:
        mask &= c.price[pos] >= f["price_min"]
    if f.get("price_max") is not None:
        mask &= c.price[pos] <= f["price_max"]
    if f.get("in_stock"):
        mask &= c.in_stock[pos] > 0
    if f.get("min_rating") is not None:
        mask &= c.rating[pos] >= f["min_rating"]
    return mask


async def _bandit_action(
    db: AsyncSession, user_id: str, pq, device: str, history: int
) -> tuple[str, bool, dict | None]:
    """Contextual-bandit meta-strategy: the policy picks which ranking strategy serves this request."""
    policy = runtime.bandit
    if policy is None:
        return DEFAULT_STRATEGY, False, None
    segment = await db.scalar(text("SELECT segment FROM users WHERE id = :u"), {"u": user_id})
    group = runtime.catalog.class_group.get(pq.top_class or "", "other")
    x = build_context(group, pq.price_max is not None, len(pq.tokens), history, segment, device)
    action, prop = policy.select(x)
    base, explore = action_to_strategy(action)
    return (
        base,
        explore,
        {
            "action": action,
            "propensity": round(float(prop), 4),
            "group": group,
            "segment": segment or "unknown",
            "device": device,
        },
    )


def _facets(pos: np.ndarray) -> list[Facet]:
    c = runtime.catalog
    out = []
    for name, arr, top in (
        ("product_class", c.product_class, 12),
        ("brand", c.brand, 10),
        ("style", c.style, 8),
        ("material", c.material, 8),
        ("color", c.color, 8),
    ):
        cnt = Counter(v for v in arr[pos] if v)
        out.append(Facet(name=name, values=[FacetValue(value=v, count=n) for v, n in cnt.most_common(top)]))
    prices = c.price[pos]
    out.append(
        Facet(
            name="price",
            values=[
                FacetValue(
                    value=f"{lo}-{hi if hi < 10**9 else ''}",
                    count=int(((prices >= lo) & (prices < hi)).sum()),
                )
                for lo, hi in PRICE_BUCKETS
            ],
        )
    )
    out.append(Facet(name="in_stock", values=[FacetValue(value="true", count=int(c.in_stock[pos].sum()))]))
    return out


async def search(
    db: AsyncSession,
    q: str,
    user_id: str,
    session_id: str,
    page: int = 1,
    page_size: int | None = None,
    filters: dict | None = None,
    strategy_override: str | None = None,
    with_explanations: bool = False,
    log_events: bool = True,
    source: str = "search",
    device: str = "desktop",
    explore_override: bool | None = None,
) -> SearchResponse:
    t0 = time.perf_counter()
    page_size = page_size or settings.results_page_size
    filters = filters or {}
    request_id = uuid.uuid4().hex[:16]

    exposure = await experiment_service.expose(db, user_id, "search")
    strategy = strategy_override or (exposure.strategy if exposure else DEFAULT_STRATEGY)
    if explore_override is not None:  # debug/preview: show a variant exactly, slot included
        explore = explore_override
    else:
        explore = bool(exposure and exposure.explore) if not strategy_override else False

    pq, qvec = runtime.parse(q)
    intent = None
    if (
        log_events
    ):  # live traffic: typed category decision (Decision-1 or local softmax) refines the embedding intent
        intent = await classify_intent(pq, runtime.classes)
        if intent["class"] and intent["p"] >= settings.decision_intent_threshold:
            pq.top_class, pq.top_class_sim = intent["class"], max(pq.top_class_sim, intent["p"])
    profile = UserProfile()
    if strategy in ("hybrid_ltr_personalized", "bandit"):
        profile = await build_profile(db, user_id, runtime.catalog)
    bandit = None
    if strategy == "bandit":
        strategy, explore, bandit = await _bandit_action(db, user_id, pq, device, profile.n_events)
    res = rank(
        strategy,
        pq,
        qvec,
        runtime.catalog,
        runtime.classes,
        runtime.ranker,
        profile,
        settings.retrieval_top_k,
        explore,
        runtime.rng,
    )

    # an explicit "under $300" / "over $50" in the query is a hard constraint for the shopper
    if pq.price_max is not None and "price_max" not in filters:
        filters = {**filters, "price_max": pq.price_max}
    if pq.price_min is not None and "price_min" not in filters:
        filters = {**filters, "price_min": pq.price_min}
    mask = _apply_filters(res.positions, filters) if filters else np.ones(len(res.positions), bool)
    pos_f, scores_f = res.positions[mask], res.scores[mask]
    total = int(len(pos_f))
    start = (page - 1) * page_size
    page_pos = pos_f[start : start + page_size]
    page_scores = scores_f[start : start + page_size]

    explanations = (
        explain_ranking(res, runtime.ranker, top_n=len(res.positions)) if with_explanations else None
    )
    expl_by_pos = (
        {int(p): e for p, e in zip(res.positions, explanations, strict=False)} if explanations else {}
    )

    items = []
    for i, (p, s) in enumerate(zip(page_pos, page_scores, strict=True)):
        rec = runtime.catalog.record(int(p))
        items.append(
            ProductOut(**rec, position=start + i + 1, score=float(s), explanation=expl_by_pos.get(int(p)))
        )

    latency_ms = (time.perf_counter() - t0) * 1000
    explored_id = (
        int(runtime.catalog.ids[res.explored_position]) if res.explored_position is not None else None
    )

    if log_events:
        now = datetime.now(UTC)
        await ensure_user_session(db, user_id, session_id, now)
        base = dict(
            ts=now,
            user_id=user_id,
            session_id=session_id,
            query=pq.raw,
            experiment_key=exposure.experiment_key if exposure else None,
            variant=exposure.variant if exposure else None,
            ranking_model_version=runtime.model_version,
            strategy=strategy,
            source=source,
        )
        rows = [
            dict(
                base,
                event_type="search",
                result_count=total,
                latency_ms=round(latency_ms, 2),
                meta={
                    "request_id": request_id,
                    "page": page,
                    "filters": filters,
                    "parsed": {"price_max": pq.price_max, "top_class": pq.top_class},
                    "intent": intent,
                    "bandit": bandit,
                },
            )
        ]
        rows += [
            dict(
                base,
                event_type="impression",
                product_id=it.id,
                position=it.position,
                meta={"request_id": request_id, "explored": it.id == explored_id},
            )
            for it in items
        ]
        await db.execute(insert(Event), rows)
        await db.commit()

    return SearchResponse(
        request_id=request_id,
        query=q,
        parsed={
            "text": pq.text,
            "price_min": pq.price_min,
            "price_max": pq.price_max,
            "top_class": pq.top_class,
            "top_class_sim": round(pq.top_class_sim, 3),
            "intent": intent,
            "bandit": bandit,
        },
        total=total,
        page=page,
        page_size=page_size,
        items=items,
        facets=_facets(pos_f[:500]),
        strategy=strategy,
        variant=exposure.variant if exposure else None,
        experiment_key=exposure.experiment_key if exposure else None,
        ranking_model_version=runtime.model_version,
        retrieval=res.retrieval,
        latency_ms=round(latency_ms, 1),
        explored_product_id=explored_id,
    )


def suggest(prefix: str, limit: int = 8) -> SuggestResponse:
    p = prefix.strip().lower()
    if len(p) < 2 or not runtime.suggest_terms:
        return SuggestResponse(prefix=prefix, suggestions=[])
    terms = runtime.suggest_terms
    i = bisect_left(terms, (p, ""))
    out: list[Suggestion] = []
    cats, prods = [], []
    while i < len(terms) and terms[i][0].startswith(p) and len(cats) + len(prods) < 200:
        (cats if terms[i][1] == "category" else prods).append(terms[i])
        i += 1
    for t, k in cats[:4] + prods[: max(0, limit - min(4, len(cats)))]:
        out.append(Suggestion(text=t, kind=k))
    return SuggestResponse(prefix=prefix, suggestions=out[:limit])


def similar_products(product_id: int, k: int = 12) -> list[ProductOut]:
    c = runtime.catalog
    pos = c.id_to_pos.get(product_id)
    if pos is None:
        return []
    idx, sims = c.semantic.neighbors(pos, k)
    return [ProductOut(**c.record(int(p)), score=float(s)) for p, s in zip(idx, sims, strict=True)]
