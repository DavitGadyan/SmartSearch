"""Shopper personas: latent preferences that drive simulated behaviour (never visible to the ranker directly)."""

from dataclasses import dataclass, field

import numpy as np

from app.ml.catalog_cache import CatalogCache

# name: (mix weight, style affinities, log-price offset vs class mean, sessions/28d (Poisson λ), patience)
PERSONAS = {
    "budget_minimalist": (0.22, {"modern": 0.9, "mid-century": 0.4}, -0.45, 3.2, 10),
    "luxury_traditional": (0.14, {"traditional": 0.9, "glam": 0.6}, +0.55, 3.0, 8),
    "farmhouse_family": (0.18, {"farmhouse": 0.9, "rustic": 0.6}, 0.0, 3.5, 12),
    "coastal_boho": (0.14, {"coastal": 0.8, "boho": 0.8}, -0.1, 2.8, 10),
    "industrial_loft": (0.12, {"industrial": 0.9, "mid-century": 0.5, "modern": 0.3}, +0.2, 2.6, 9),
    "new_visitor": (0.20, {}, 0.0, 1.2, 6),
}
SEGMENTS = {
    "budget_minimalist": "value",
    "luxury_traditional": "premium",
    "farmhouse_family": "family",
    "coastal_boho": "style-led",
    "industrial_loft": "style-led",
    "new_visitor": "new",
}


@dataclass
class SimUser:
    id: str
    persona: str
    segment: str
    style: dict[str, float]
    brands: dict[str, float]
    classes: dict[str, float]
    log_price_offset: float
    sessions_lambda: float
    patience: int  # max results examined per search
    traits: dict = field(default_factory=dict)


def generate_users(
    n: int, cache: CatalogCache, rng: np.random.Generator, prefix: str = "sim"
) -> list[SimUser]:
    names = list(PERSONAS)
    weights = np.array([PERSONAS[p][0] for p in names])
    weights /= weights.sum()
    brands = np.unique(cache.brand[cache.brand != ""])
    classes, counts = np.unique(cache.product_class[cache.product_class != ""], return_counts=True)
    class_p = counts / counts.sum()
    users = []
    for i in range(n):
        p = names[rng.choice(len(names), p=weights)]
        _, style, lp_off, lam, patience = PERSONAS[p]
        n_brands = 0 if p == "new_visitor" else rng.integers(1, 3)
        fav_brands = {
            str(b): float(w)
            for b, w in zip(
                rng.choice(brands, n_brands, replace=False), rng.uniform(0.5, 1.0, n_brands), strict=True
            )
        }
        n_classes = rng.integers(2, 5)
        fav_classes = {
            str(c): float(w)
            for c, w in zip(
                rng.choice(classes, n_classes, replace=False, p=class_p),
                rng.uniform(0.4, 1.0, n_classes),
                strict=True,
            )
        }
        offset = float(rng.normal(lp_off, 0.25))
        users.append(
            SimUser(
                id=f"{prefix}_{i:06d}",
                persona=p,
                segment=SEGMENTS[p],
                style=dict(style),
                brands=fav_brands,
                classes=fav_classes,
                log_price_offset=offset,
                sessions_lambda=lam,
                patience=int(patience),
                traits={
                    "style": style,
                    "brands": fav_brands,
                    "classes": fav_classes,
                    "log_price_offset": round(offset, 3),
                },
            )
        )
    return users
