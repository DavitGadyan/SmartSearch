"""Lightweight query understanding: normalisation, price constraints, product-class intent."""

import re
from dataclasses import dataclass, field

import numpy as np

_PRICE_MAX = re.compile(
    r"\b(?:under|below|less than|max(?:imum)?|up to|cheaper than)\s*\$?\s*(\d{2,5})\b|\$?(\d{2,5})\s*(?:or less|and under|max)\b",
    re.I,
)
_PRICE_MIN = re.compile(r"\b(?:over|above|more than|at least|min(?:imum)?)\s*\$?\s*(\d{2,5})\b", re.I)
_PRICE_RANGE = re.compile(r"\$?\s*(\d{2,5})\s*(?:-|to)\s*\$?\s*(\d{2,5})\b")
_NOISE = re.compile(r"\b(?:dollars?|bucks|usd|price|cheap|affordable|budget)\b", re.I)


@dataclass
class ParsedQuery:
    raw: str
    text: str  # cleaned text used for retrieval
    price_min: float | None = None
    price_max: float | None = None
    tokens: list[str] = field(default_factory=list)
    class_sims: np.ndarray | None = (
        None  # cosine sim to every catalog class name (aligned with ClassIndex.names)
    )
    top_class: str | None = None
    top_class_sim: float = 0.0


def parse_query(raw: str) -> ParsedQuery:
    q = raw.strip().lower()
    pmin = pmax = None
    if m := _PRICE_RANGE.search(q):
        pmin, pmax = float(m.group(1)), float(m.group(2))
        q = q.replace(m.group(0), " ")
    if m := _PRICE_MAX.search(q):
        pmax = float(m.group(1) or m.group(2))
        q = q.replace(m.group(0), " ")
    if m := _PRICE_MIN.search(q):
        pmin = float(m.group(1))
        q = q.replace(m.group(0), " ")
    q = _NOISE.sub(" ", q)
    q = re.sub(r"[^a-z0-9&'\- ]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    tokens = [t for t in q.split() if len(t) > 1]
    return ParsedQuery(raw=raw, text=q or raw.lower(), price_min=pmin, price_max=pmax, tokens=tokens)


class ClassIndex:
    """Embeds catalog class names once so a query can be softly mapped to product classes."""

    def __init__(self, names: list[str], embedder) -> None:
        self.names = names
        self.name_to_i = {n: i for i, n in enumerate(names)}
        self.emb = embedder.encode(names) if names else np.zeros((0, embedder.dim), np.float32)

    def annotate(self, pq: ParsedQuery, qvec: np.ndarray) -> ParsedQuery:
        if len(self.names) == 0:
            return pq
        sims = self.emb @ qvec
        i = int(np.argmax(sims))
        pq.class_sims, pq.top_class, pq.top_class_sim = sims.astype(np.float32), self.names[i], float(sims[i])
        return pq

    def sims_for_classes(self, pq: ParsedQuery, classes: np.ndarray) -> np.ndarray:
        if pq.class_sims is None:
            return np.zeros(len(classes), np.float32)
        idx = np.array([self.name_to_i.get(c, -1) for c in classes])
        out = np.where(idx >= 0, pq.class_sims[np.clip(idx, 0, None)], 0.0)
        return out.astype(np.float32)
