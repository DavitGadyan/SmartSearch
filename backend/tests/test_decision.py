import numpy as np
import pytest

from app.decision import policies
from app.ml.query import ParsedQuery


class _Classes:
    names = ["Accent Chairs", "Dining Chairs", "Office Chairs", "Bar Stools", "Beds", "Area Rugs", "Desks"]


@pytest.mark.asyncio
async def test_local_intent_classification_uses_embedding_candidates(monkeypatch):
    monkeypatch.setattr(policies.settings, "decision_backend", "local")
    policies.get_decision_client().backend = "local"
    pq = ParsedQuery(
        raw="leather accent chair", text="leather accent chair", tokens=["leather", "accent", "chair"]
    )
    pq.class_sims = np.array([0.8, 0.6, 0.5, 0.3, 0.1, 0.05, 0.2], np.float32)
    out = await policies.classify_intent(pq, _Classes())
    assert out["class"] == "Accent Chairs" and 0 < out["p"] <= 1 and out["source"] == "local"
    assert abs(sum(out["candidates"].values()) - 1) < 0.01


@pytest.mark.asyncio
async def test_local_route_and_relevance_fallbacks():
    policies.get_decision_client().backend = "local"
    r = await policies.route_agent("walnut nightstand under 200")
    assert r["route"] == "direct_search"
    r2 = await policies.route_agent("I need a gift idea for someone who loves hiking")
    assert r2["route"] == "assistant"
    judged = await policies.grade_relevance(
        "sofa", [{"id": 1, "name": "sofa"}, {"id": 2, "name": "lamp"}], None, np.array([0.8, 0.2])
    )
    assert judged[0]["expected_grade"] > judged[1]["expected_grade"]
    assert 0 <= judged[0]["p_irrelevant"] <= 1
