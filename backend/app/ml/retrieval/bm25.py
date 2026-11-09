"""Keyword retrieval: BM25 (Lucene variant) over product title + class + brand + attributes, in memory."""

import numpy as np

try:
    import Stemmer  # PyStemmer

    _STEMMER = Stemmer.Stemmer("english")
except Exception:  # pragma: no cover
    _STEMMER = None

import bm25s


class BM25Index:
    def __init__(self, docs: list[str]) -> None:
        tokens = bm25s.tokenize(docs, stopwords="en", stemmer=_STEMMER, show_progress=False)
        self.retriever = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
        self.retriever.index(tokens, show_progress=False)
        self.n = len(docs)

    def search(self, query: str, k: int = 200) -> tuple[np.ndarray, np.ndarray]:
        """Return (doc positions, scores) sorted by score desc; only docs with score > 0."""
        q = bm25s.tokenize([query], stopwords="en", stemmer=_STEMMER, return_ids=False, show_progress=False)
        if not q[0]:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32)
        k = min(k, self.n)
        idx, scores = self.retriever.retrieve(q, k=k, show_progress=False)
        idx, scores = idx[0].astype(np.int64), scores[0].astype(np.float32)
        keep = scores > 0
        return idx[keep], scores[keep]

    def scores_for(self, query: str, positions: np.ndarray) -> np.ndarray:
        """BM25 score of the query against specific docs (0 for non-matching)."""
        q = bm25s.tokenize([query], stopwords="en", stemmer=_STEMMER, return_ids=False, show_progress=False)
        if not q[0]:
            return np.zeros(len(positions), dtype=np.float32)
        all_scores = self.retriever.get_scores(q[0])
        return all_scores[positions].astype(np.float32)
