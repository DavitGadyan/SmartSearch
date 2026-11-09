"""Reciprocal Rank Fusion of keyword and semantic candidate lists."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Candidates:
    """Candidate set with per-source ranks/scores aligned to `positions` (catalog row positions)."""

    positions: np.ndarray
    bm25_score: np.ndarray
    bm25_rank: np.ndarray  # 1-based; 0 = not retrieved by BM25
    sem_score: np.ndarray
    sem_rank: np.ndarray  # 1-based; 0 = not retrieved semantically
    rrf: np.ndarray
    sources: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.positions)


def rrf_fuse(
    bm25_idx: np.ndarray,
    bm25_scores: np.ndarray,
    sem_idx: np.ndarray,
    sem_scores: np.ndarray,
    sem_all_fn,
    k: int = 60,
) -> Candidates:
    """Union both lists; RRF = Σ 1/(k+rank). `sem_all_fn(positions)` fills semantic sims for BM25-only docs."""
    union = np.unique(np.concatenate([bm25_idx, sem_idx])).astype(np.int64)
    pos_to_i = {int(p): i for i, p in enumerate(union)}
    n = len(union)
    b_score, b_rank = np.zeros(n, np.float32), np.zeros(n, np.int32)
    s_score, s_rank = np.zeros(n, np.float32), np.zeros(n, np.int32)
    for r, (p, s) in enumerate(zip(bm25_idx, bm25_scores, strict=True), start=1):
        i = pos_to_i[int(p)]
        b_score[i], b_rank[i] = s, r
    for r, (p, s) in enumerate(zip(sem_idx, sem_scores, strict=True), start=1):
        i = pos_to_i[int(p)]
        s_score[i], s_rank[i] = s, r
    missing = s_rank == 0
    if missing.any():
        s_score[missing] = sem_all_fn(union[missing])
    rrf = np.where(b_rank > 0, 1.0 / (k + b_rank), 0.0) + np.where(s_rank > 0, 1.0 / (k + s_rank), 0.0)
    order = np.argsort(-rrf, kind="stable")
    return Candidates(
        positions=union[order],
        bm25_score=b_score[order],
        bm25_rank=b_rank[order],
        sem_score=s_score[order],
        sem_rank=s_rank[order],
        rrf=rrf[order].astype(np.float32),
        sources={"bm25": int(len(bm25_idx)), "semantic": int(len(sem_idx)), "union": n},
    )
