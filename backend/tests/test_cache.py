from app.core.cache import TTLCache


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_entries_expire_after_ttl():
    clock = Clock()
    cache = TTLCache(maxsize=10, ttl=5.0, clock=clock)
    cache.set("a", 1)
    assert cache.get("a") == 1
    clock.t = 4.9
    assert cache.get("a") == 1
    clock.t = 5.0
    assert cache.get("a") is None
    assert len(cache) == 0  # expired entries are dropped on read


def test_fifo_eviction_at_capacity():
    cache = TTLCache(maxsize=2, ttl=60.0, clock=Clock())
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2 and cache.get("c") == 3


def test_overwrite_does_not_evict():
    cache = TTLCache(maxsize=2, ttl=60.0, clock=Clock())
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("a", 10)
    assert cache.get("a") == 10 and cache.get("b") == 2


def test_clear():
    cache = TTLCache(clock=Clock())
    cache.set("a", 1)
    cache.clear()
    assert cache.get("a") is None
