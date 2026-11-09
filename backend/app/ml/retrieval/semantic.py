"""Semantic retrieval: cosine similarity between the query embedding and the in-memory product matrix."""

import numpy as np


class SemanticIndex:
    def __init__(self, emb: np.ndarray) -> None:
        self.emb = emb  # (n, dim), L2-normalised
        self.n = emb.shape[0]

    def search(self, qvec: np.ndarray, k: int = 200) -> tuple[np.ndarray, np.ndarray]:
        sims = self.emb @ qvec
        k = min(k, self.n)
        top = np.argpartition(-sims, k - 1)[:k]
        order = np.argsort(-sims[top])
        idx = top[order]
        return idx.astype(np.int64), sims[idx].astype(np.float32)

    def sims_for(self, qvec: np.ndarray, positions: np.ndarray) -> np.ndarray:
        return (self.emb[positions] @ qvec).astype(np.float32)

    def neighbors(self, position: int, k: int = 12) -> tuple[np.ndarray, np.ndarray]:
        idx, sims = self.search(self.emb[position], k + 1)
        keep = idx != position
        return idx[keep][:k], sims[keep][:k]
