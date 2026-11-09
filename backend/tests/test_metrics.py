import numpy as np
import pytest

from app.ml.eval.metrics import average_precision, mrr, ndcg_at_k, recall_at_k


def test_ndcg_perfect_and_worst_orderings():
    grades = np.array([2, 2, 1, 0, 0])
    assert ndcg_at_k(np.array([2, 2, 1, 0, 0]), grades, 10) == pytest.approx(1.0)
    assert ndcg_at_k(np.array([0, 0, 1, 2, 2]), grades, 10) < 0.75


def test_ndcg_hand_computed():
    # ranked grades [1, 2]; ideal [2, 1]; gains 2^g - 1 → [1, 3] vs [3, 1]
    dcg = 1 / np.log2(2) + 3 / np.log2(3)
    idcg = 3 / np.log2(2) + 1 / np.log2(3)
    assert ndcg_at_k(np.array([1, 2]), np.array([1, 2]), 10) == pytest.approx(dcg / idcg)


def test_mrr_recall_map():
    ranked = np.array([0, 0, 2, 1, 0])
    assert mrr(ranked) == pytest.approx(1 / 3)
    assert mrr(ranked, rel_threshold=2) == pytest.approx(1 / 3)
    assert recall_at_k(ranked, np.array([2, 1, 1, 0]), k=5) == pytest.approx(2 / 3)
    assert average_precision(ranked, np.array([2, 1]), k=5) == pytest.approx((1 / 3 + 2 / 4) / 2)
