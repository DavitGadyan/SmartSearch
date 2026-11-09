"""Microsoft-Decision-1 client: typed decisions (noul / choice / score) with calibrated probabilities.

Backends: Foundry (`/providers/microsoft/v1/systemone`), OpenRouter (`/api/alpha/decisions`), or `local`, where the
caller supplies a fallback so every decision point keeps working without credentials. Responses are cached in Redis.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger("decision")
Questions = dict[str, dict]
Answers = dict[str, dict]


@dataclass
class Decision:
    answers: Answers
    backend: str
    latency_ms: float
    cached: bool = False
    usage: dict = field(default_factory=dict)


def backend_name() -> str:
    b = settings.decision_backend
    if b != "auto":
        return b
    if settings.openrouter_api_key:
        return "openrouter"
    if settings.decision1_endpoint and settings.decision1_api_key:
        return "foundry"
    return "local"


def _normalise(answers: dict) -> Answers:
    """Accept both {option: p} dicts and [{value, probability}] lists for probabilities."""
    out: Answers = {}
    for name, a in (answers or {}).items():
        a = dict(a)
        probs = a.get("probabilities")
        if isinstance(probs, list):
            a["probabilities"] = {
                str(x.get("value", x.get("option"))): float(x.get("probability", 0)) for x in probs
            }
        elif isinstance(probs, dict):
            a["probabilities"] = {str(k): float(v) for k, v in probs.items()}
        out[name] = a
    return out


class DecisionClient:
    def __init__(self) -> None:
        self.backend = backend_name()
        self._http = httpx.AsyncClient(timeout=12.0)

    def _request(self, state, questions: Questions) -> tuple[str, dict, dict]:
        if self.backend == "openrouter":
            return (
                "https://openrouter.ai/api/alpha/decisions",
                {
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                {"model": settings.decision_model, "state": state, "questions": questions},
            )
        return (
            f"{settings.decision1_endpoint.rstrip('/')}/providers/microsoft/v1/systemone",
            {"api-key": settings.decision1_api_key or "", "Content-Type": "application/json"},
            {"model": settings.decision1_deployment, "state": state, "questions": questions},
        )

    async def decide(
        self, state, questions: Questions, local: Callable[[], Answers] | None = None, ttl: int = 3600
    ) -> Decision:
        t0 = time.perf_counter()
        if self.backend == "local":
            return Decision(local() if local else {}, "local", (time.perf_counter() - t0) * 1000)
        key = (
            "d1:"
            + hashlib.sha256(json.dumps([state, questions], sort_keys=True, default=str).encode()).hexdigest()
        )
        redis = get_redis()
        try:
            if raw := await redis.get(key):
                return Decision(json.loads(raw), self.backend, (time.perf_counter() - t0) * 1000, cached=True)
        except Exception:
            pass
        url, headers, body = self._request(state, questions)
        try:
            r = await self._http.post(url, headers=headers, json=body)
            r.raise_for_status()
            payload = r.json()
            answers = _normalise(payload.get("answers", {}))
            try:
                await redis.set(key, json.dumps(answers), ex=ttl)
            except Exception:
                pass
            return Decision(
                answers, self.backend, (time.perf_counter() - t0) * 1000, usage=payload.get("usage") or {}
            )
        except Exception as e:  # never let a decision call break the request path
            log.warning("decision backend %s failed (%s); using local fallback", self.backend, e)
            return Decision(
                local() if local else {}, f"{self.backend}->local", (time.perf_counter() - t0) * 1000
            )


_client: DecisionClient | None = None


def get_decision_client() -> DecisionClient:
    global _client
    if _client is None:
        _client = DecisionClient()
    return _client
