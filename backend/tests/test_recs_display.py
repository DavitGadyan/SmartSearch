"""The rails' photo-first display preference: imaged items fill the visible slots first, scores untouched."""

import numpy as np

from app.services.recs_service import _photo_first


def test_imaged_items_come_first_in_score_order():
    has = np.array([False, True, False, True, True, False])
    assert _photo_first(has, 3).tolist() == [1, 3, 4]


def test_falls_back_to_unimaged_items_when_photos_run_out():
    has = np.array([False, True, False])
    assert _photo_first(has, 3).tolist() == [1, 0, 2]


def test_pool_smaller_than_k_returns_everything():
    assert _photo_first(np.array([True, False]), 5).tolist() == [0, 1]


def test_empty_pool():
    assert _photo_first(np.array([], dtype=bool), 6).tolist() == []
