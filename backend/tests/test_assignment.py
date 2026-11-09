from collections import Counter

from app.experiments.assignment import assign_variant, bucket_of

VARIANTS = [{"key": "control", "weight": 0.5}, {"key": "treatment", "weight": 0.5}]


def test_assignment_is_deterministic_and_salt_dependent():
    assert assign_variant("s1", "user_42", VARIANTS) == assign_variant("s1", "user_42", VARIANTS)
    diff = sum(
        assign_variant("s1", f"u{i}", VARIANTS) != assign_variant("s2", f"u{i}", VARIANTS)
        for i in range(2000)
    )
    assert 800 < diff < 1200  # independent salts → ~50% of users land in a different arm


def test_split_is_balanced_at_scale():
    c = Counter(assign_variant("salt", f"user_{i}", VARIANTS) for i in range(100_000))
    assert abs(c["control"] / 100_000 - 0.5) < 0.005


def test_traffic_allocation_and_weights():
    c = Counter(
        assign_variant(
            "salt",
            f"user_{i}",
            [{"key": "a", "weight": 0.2}, {"key": "b", "weight": 0.8}],
            traffic_allocation=0.5,
        )
        for i in range(100_000)
    )
    assert abs(c[None] / 100_000 - 0.5) < 0.01
    assert abs(c["b"] / (c["a"] + c["b"]) - 0.8) < 0.01


def test_bucket_range():
    assert all(0 <= bucket_of("x", f"u{i}") < 10_000 for i in range(1000))
