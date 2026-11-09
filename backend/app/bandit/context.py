"""Context features for the ranking-policy bandit: query intent, constraints, shopper history, segment, device."""

import numpy as np

ACTIONS = [
    "control_bm25_pop",
    "hybrid_rrf",
    "hybrid_ltr",
    "hybrid_ltr_personalized",
    "hybrid_ltr_personalized+explore",
]
GROUPS = [
    "furniture",
    "outdoor",
    "rugs",
    "lighting",
    "decor",
    "bed & bath",
    "kitchen",
    "storage",
    "kids",
    "other",
]
SEGMENTS = ["value", "premium", "family", "style-led", "new", "unknown"]
DEVICES = ["desktop", "mobile", "tablet"]
DIM = 1 + len(GROUPS) + 1 + 3 + 3 + len(SEGMENTS) + len(DEVICES)


def category_group(top_category: str | None) -> str:
    t = (top_category or "").lower()
    for g in GROUPS[:-1]:
        if g.split(" ")[0] in t:
            return g
    if "décor" in t or "pillow" in t:
        return "decor"
    if "baby" in t or "school" in t:
        return "kids"
    return "other"


def build_context(
    group: str | None,
    has_price_cap: bool,
    n_tokens: int,
    history: int,
    segment: str | None,
    device: str | None,
) -> np.ndarray:
    x = np.zeros(DIM, np.float32)
    x[0] = 1.0
    i = 1
    x[i + GROUPS.index(group if group in GROUPS else "other")] = 1.0
    i += len(GROUPS)
    x[i] = float(has_price_cap)
    i += 1
    x[i + min(max(n_tokens, 1), 3) - 1] = 1.0
    i += 3
    x[i + (0 if history == 0 else 1 if history <= 5 else 2)] = 1.0
    i += 3
    x[i + SEGMENTS.index(segment if segment in SEGMENTS else "unknown")] = 1.0
    i += len(SEGMENTS)
    x[i + DEVICES.index(device if device in DEVICES else "desktop")] = 1.0
    return x


def action_to_strategy(action: str) -> tuple[str, bool]:
    base, _, flag = action.partition("+")
    return base, flag == "explore"
