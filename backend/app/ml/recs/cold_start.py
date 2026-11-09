"""Thompson-sampling exploration slot for products with little behavioral data."""

import numpy as np

from app.ml.catalog_cache import CatalogCache

COLD_IMPRESSIONS = 50
SLOT_POSITION = 4  # 0-based → 5th result
MAX_POOL_RANK = 60  # only explore items the retriever already considered reasonably relevant


def apply_exploration_slot(
    positions: np.ndarray, scores: np.ndarray, cache: CatalogCache, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, int | None]:
    """Return (positions, scores, explored_product_position) with one cold item moved into SLOT_POSITION."""
    if len(positions) <= SLOT_POSITION + 1:
        return positions, scores, None
    pool = positions[SLOT_POSITION + 1 : MAX_POOL_RANK]
    impr = cache.stat["impressions_30d"][pool]
    clicks = cache.stat["clicks_30d"][pool]
    cold = (impr < COLD_IMPRESSIONS) & (cache.in_stock[pool] > 0)
    if not cold.any():
        return positions, scores, None
    draws = rng.beta(1 + clicks[cold], 1 + np.maximum(impr[cold] - clicks[cold], 0))
    chosen = pool[cold][int(np.argmax(draws))]
    src = int(np.flatnonzero(positions == chosen)[0])
    order = np.arange(len(positions))
    order = np.insert(np.delete(order, src), SLOT_POSITION, src)
    return positions[order], scores[order], int(chosen)
