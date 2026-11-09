"""Small in-process TTL caches for results that are expensive to compute and change slowly.

One process, no eviction policy beyond FIFO; good enough for a single API instance. Anything that mutates the
underlying data (simulated traffic, status changes, a catalog reload) calls `clear()` on the affected cache.
"""

import time
from collections.abc import Callable, Hashable
from typing import Any


class TTLCache:
    def __init__(
        self, maxsize: int = 1024, ttl: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.maxsize, self.ttl, self._clock = maxsize, ttl, clock
        self._d: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any | None:
        hit = self._d.get(key)
        if hit is not None and self._clock() - hit[0] < self.ttl:
            return hit[1]
        self._d.pop(key, None)
        return None

    def set(self, key: Hashable, value: Any) -> None:
        if key not in self._d and len(self._d) >= self.maxsize:
            self._d.pop(next(iter(self._d)))  # FIFO: dicts keep insertion order
        self._d[key] = (self._clock(), value)

    def clear(self) -> None:
        self._d.clear()

    def __len__(self) -> int:
        return len(self._d)


RAILS_GLOBAL = TTLCache(maxsize=64, ttl=60.0)  # trending / new arrivals: same for everyone
RAILS_ITEM = TTLCache(maxsize=4096, ttl=600.0)  # similar / goes-with / bought-together per product
ANALYTICS = TTLCache(maxsize=256, ttl=60.0)  # console overview and experiment analyses
DEMO_USERS = TTLCache(maxsize=4, ttl=600.0)  # the persona switcher's shopper list
