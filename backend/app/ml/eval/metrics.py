"""Offline ranking metrics on graded relevance (0/1/2). `relevant` means grade >= rel_threshold."""

import numpy as np


def dcg(grades: np.ndarray, k: int) -> float:
    g = np.asarray(grades, dtype=float)[:k]
    if g.size == 0:
        return 0.0
    gains = 2.0**g - 1.0
    return float((gains / np.log2(np.arange(2, g.size + 2))).sum())


def ndcg_at_k(ranked_grades: np.ndarray, all_grades: np.ndarray, k: int = 10) -> float:
    """all_grades = every judged grade for the query (ideal ordering is computed from these)."""
    ideal = dcg(np.sort(np.asarray(all_grades))[::-1], k)
    return dcg(ranked_grades, k) / ideal if ideal > 0 else 0.0


def mrr(ranked_grades: np.ndarray, rel_threshold: int = 1) -> float:
    hits = np.flatnonzero(np.asarray(ranked_grades) >= rel_threshold)
    return 1.0 / (hits[0] + 1) if hits.size else 0.0


def precision_at_k(ranked_grades: np.ndarray, k: int = 10, rel_threshold: int = 1) -> float:
    g = np.asarray(ranked_grades)[:k]
    return float((g >= rel_threshold).sum() / k) if k else 0.0


def recall_at_k(
    ranked_grades: np.ndarray, all_grades: np.ndarray, k: int = 50, rel_threshold: int = 1
) -> float:
    total = int((np.asarray(all_grades) >= rel_threshold).sum())
    if total == 0:
        return 0.0
    return float((np.asarray(ranked_grades)[:k] >= rel_threshold).sum() / total)


def average_precision(
    ranked_grades: np.ndarray, all_grades: np.ndarray, k: int = 10, rel_threshold: int = 1
) -> float:
    g = np.asarray(ranked_grades)[:k] >= rel_threshold
    total = int((np.asarray(all_grades) >= rel_threshold).sum())
    if total == 0:
        return 0.0
    hits = np.cumsum(g)
    precisions = hits / np.arange(1, g.size + 1)
    return float((precisions * g).sum() / min(total, k))


def evaluate_ranking(ranked_grades: np.ndarray, all_grades: np.ndarray) -> dict[str, float]:
    return {
        "ndcg@10": ndcg_at_k(ranked_grades, all_grades, 10),
        "ndcg@20": ndcg_at_k(ranked_grades, all_grades, 20),
        "mrr": mrr(ranked_grades),
        "mrr_exact": mrr(ranked_grades, rel_threshold=2),
        "p@10": precision_at_k(ranked_grades, 10),
        "recall@50": recall_at_k(ranked_grades, all_grades, 50),
        "map@10": average_precision(ranked_grades, all_grades, 10),
    }
