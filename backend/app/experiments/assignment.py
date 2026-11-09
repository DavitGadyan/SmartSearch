"""Deterministic, sticky experiment assignment via hashing."""

import mmh3

BUCKETS = 10_000


def bucket_of(salt: str, user_id: str) -> int:
    return mmh3.hash(f"{salt}:{user_id}", signed=False) % BUCKETS


def assign_variant(
    salt: str, user_id: str, variants: list[dict], traffic_allocation: float = 1.0
) -> str | None:
    """variants: [{"key": "control", "weight": 0.5}, ...]; returns variant key or None if not enrolled."""
    b = bucket_of(salt, user_id)
    enrolled = int(round(traffic_allocation * BUCKETS))
    if b >= enrolled:
        return None
    total = sum(float(v.get("weight", 0)) for v in variants) or 1.0
    edge = 0.0
    for v in variants:
        edge += float(v.get("weight", 0)) / total * enrolled
        if b < edge:
            return v["key"]
    return variants[-1]["key"]
