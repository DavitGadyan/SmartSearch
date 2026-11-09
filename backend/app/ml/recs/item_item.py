"""Item-item collaborative filtering from session co-occurrence (clicks/carts/purchases), with lift normalisation."""

import numpy as np
import pandas as pd
from scipy import sparse

INTERACTION_WEIGHT = {
    "click": 1.0,
    "product_view": 0.0,
    "add_to_cart": 2.0,
    "purchase": 3.0,
    "rec_click": 1.0,
}


def build_cooccurrence(
    events: pd.DataFrame, min_support: int = 2, top_k: int = 20, by: str = "session_id"
) -> pd.DataFrame:
    """events: columns [by, product_id, event_type]. Returns rows (product_id, neighbor_id, score) with cosine-normalised
    co-occurrence counts (so hugely popular items don't dominate every neighbor list)."""
    e = events[events.event_type.isin(INTERACTION_WEIGHT)].copy()
    e["w"] = e.event_type.map(INTERACTION_WEIGHT)
    e = e[e.w > 0].groupby([by, "product_id"], as_index=False).w.max()
    if e.empty:
        return pd.DataFrame(columns=["product_id", "neighbor_id", "score"])
    sess_codes, sess_idx = pd.factorize(e[by])
    item_codes, item_idx = pd.factorize(e.product_id)
    m = sparse.csr_matrix((e.w.to_numpy(), (sess_codes, item_codes)), shape=(len(sess_idx), len(item_idx)))
    co = (m.T @ m).tocsr()  # item × item weighted co-occurrence
    co.setdiag(0)
    co.eliminate_zeros()
    norms = np.sqrt(np.asarray(m.multiply(m).sum(axis=0)).ravel()) + 1e-9
    co = co.multiply(1 / norms[:, None]).multiply(1 / norms[None, :]).tocsr()
    support = (m.T @ m).tocsr()
    rows = []
    for i in range(co.shape[0]):
        start, end = co.indptr[i], co.indptr[i + 1]
        if start == end:
            continue
        cols, vals = co.indices[start:end], co.data[start:end]
        sup = np.asarray(support[i, cols].todense()).ravel()
        keep = sup >= min_support
        cols, vals = cols[keep], vals[keep]
        if len(cols) == 0:
            continue
        top = np.argsort(-vals)[:top_k]
        rows.extend(
            (int(item_idx[i]), int(item_idx[c]), float(v)) for c, v in zip(cols[top], vals[top], strict=True)
        )
    return pd.DataFrame(rows, columns=["product_id", "neighbor_id", "score"])
