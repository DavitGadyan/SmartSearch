"""Position-based click model with persona fit, calibrated so control-arm funnel rates land near real ecommerce ranges."""

import numpy as np

from app.ml.catalog_cache import CatalogCache
from app.simulation.personas import SimUser

EXAMINE_DECAY = 0.65  # examine(p) = (1 + p)^-decay, p 0-based → 1.00, 0.64, 0.49, 0.41, 0.35 ...
ATTRACT_BY_GRADE = {2: 0.42, 1: 0.16, 0: 0.025}
CART_GIVEN_CLICK = 0.13
CART_GRADE_FACTOR = {2: 1.4, 1: 0.9, 0: 0.35}
BUY_GIVEN_CART = 0.32  # Retailrocket: 22,457 transactions / 69,332 add-to-carts ≈ 0.32
OUT_OF_STOCK_ATTRACT = 0.6


def persona_fit(user: SimUser, pos: np.ndarray, cache: CatalogCache) -> np.ndarray:
    """Multiplicative fit in ~[0.55, 1.9]: style + brand + class affinity + price proximity to the user's taste."""
    style = np.fromiter((user.style.get(s, 0.0) for s in cache.style[pos]), float, len(pos))
    brand = np.fromiter((user.brands.get(b, 0.0) for b in cache.brand[pos]), float, len(pos))
    klass = np.fromiter((user.classes.get(c, 0.0) for c in cache.product_class[pos]), float, len(pos))
    # price taste: the user's preferred log-price sits at class mean + offset; z is in class-sd units
    z = cache.price_z[pos] - user.log_price_offset / 0.45
    price = np.exp(-0.5 * z**2)  # 1 at the sweet spot, → 0 far away
    return 0.55 + 0.5 * style + 0.35 * brand + 0.2 * klass + 0.5 * price


def relevance_grades(
    pos: np.ndarray, cache: CatalogCache, judged: dict[int, int], query_class: str | None
) -> np.ndarray:
    ids = cache.ids[pos]
    out = np.fromiter((judged.get(int(i), -1) for i in ids), dtype=np.int8, count=len(pos))
    if query_class:
        proxy = (cache.product_class[pos] == query_class).astype(np.int8)
        out = np.where(out < 0, proxy, out)
    return np.maximum(out, 0)


def simulate_interactions(
    user: SimUser,
    pos: np.ndarray,
    grades: np.ndarray,
    cache: CatalogCache,
    rng: np.random.Generator,
    effects: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return boolean arrays (clicked, carted, purchased) aligned with `pos` (the displayed list).
    `effects` are assumed relative lifts for a UI experiment arm (simulation only): keys `ctr`,
    `add_to_cart_rate`, `conversion_rate`; 0.05 means +5% on that step."""
    eff = effects or {}
    n = min(len(pos), user.patience)
    full_len = len(grades)
    pos, grades = pos[:n], grades[:n]
    fit = persona_fit(user, pos, cache)
    examine = (1 + np.arange(n)) ** -EXAMINE_DECAY
    attract = np.array([ATTRACT_BY_GRADE[int(g)] for g in grades]) * fit * (1 + eff.get("ctr", 0.0))
    attract = np.where(cache.in_stock[pos] > 0, attract, attract * OUT_OF_STOCK_ATTRACT)
    clicked = rng.random(n) < np.clip(examine * attract, 0, 0.95)
    cart_p = (
        CART_GIVEN_CLICK
        * fit
        * np.array([CART_GRADE_FACTOR[int(g)] for g in grades])
        * (1 + eff.get("add_to_cart_rate", 0.0))
    )
    carted = clicked & (cache.in_stock[pos] > 0) & (rng.random(n) < np.clip(cart_p, 0, 0.9))
    z = cache.price_z[pos] - user.log_price_offset / 0.45
    buy_p = BUY_GIVEN_CART * (0.6 + 0.8 * np.exp(-0.5 * z**2)) * (1 + eff.get("conversion_rate", 0.0))
    purchased = carted & (rng.random(n) < np.clip(buy_p, 0, 0.9))
    tail = np.zeros(full_len - n, bool)  # results beyond the user's patience are never examined
    return np.concatenate([clicked, tail]), np.concatenate([carted, tail]), np.concatenate([purchased, tail])
