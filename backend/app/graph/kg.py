"""Product knowledge graph for GraphRAG-style retrieval: products, categories, brands, attribute values, and
behavioural edges (co-purchase, co-view) plus embedding neighbours. Louvain communities get short summaries."""

import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np


@dataclass
class KnowledgeGraph:
    g: nx.Graph
    communities: dict[int, dict] = field(
        default_factory=dict
    )  # id -> {size, products, top_classes, summary, name}
    product_community: dict[int, int] = field(default_factory=dict)
    summary_emb: np.ndarray | None = (
        None  # embeddings of community summaries, aligned with sorted community ids
    )

    def complements(self, product_id: int, k: int = 8) -> list[tuple[int, float, str]]:
        """Items that go with this one: co-purchase first, then co-view, then same-category-adjacent."""
        node = ("p", product_id)
        if node not in self.g:
            return []
        scored: dict[int, tuple[float, str]] = {}
        for nb, data in self.g[node].items():
            if nb[0] != "p":
                continue
            w = float(data.get("weight", 1.0))
            rel = data.get("rel", "")
            boost = {"co_purchase": 3.0, "co_view": 1.0, "similar": 0.3}.get(rel, 0.5)
            s = w * boost
            if nb[1] not in scored or scored[nb[1]][0] < s:
                scored[nb[1]] = (s, rel)
        # category adjacency: other categories often bought with this product's category
        cls = next((nb for nb in self.g[node] if nb[0] == "c"), None)
        if cls is not None:
            for nb, data in self.g[cls].items():
                if nb[0] == "c" and data.get("rel") == "co_purchase":
                    for prod in list(self.g[nb])[:200]:
                        if prod[0] == "p" and prod[1] != product_id and prod[1] not in scored:
                            scored[prod[1]] = (0.2 * float(data.get("weight", 1.0)), f"bought with {cls[1]}")
        ranked = sorted(scored.items(), key=lambda t: -t[1][0])[:k]
        return [(pid, s, rel) for pid, (s, rel) in ranked]

    def same_attribute(self, product_id: int, attribute: str, k: int = 8) -> list[int]:
        node = ("p", product_id)
        if node not in self.g:
            return []
        vals = [nb for nb in self.g[node] if nb[0] == "a" and nb[1].startswith(f"{attribute}=")]
        out: list[int] = []
        for v in vals:
            out += [nb[1] for nb in self.g[v] if nb[0] == "p" and nb[1] != product_id]
        return out[:k]

    def community_of(self, product_id: int) -> dict | None:
        cid = self.product_community.get(product_id)
        return None if cid is None else {"id": cid, **self.communities[cid]}

    def topic_search(self, qvec: np.ndarray, k: int = 3) -> list[dict]:
        if self.summary_emb is None or not self.communities:
            return []
        ids = sorted(self.communities)
        sims = self.summary_emb @ qvec
        top = np.argsort(-sims)[:k]
        return [{"id": ids[i], "similarity": float(sims[i]), **self.communities[ids[i]]} for i in top]


def save_graph(kg: KnowledgeGraph, path: Path) -> None:
    path.write_bytes(pickle.dumps(kg))
    (path.with_name("graph_communities.json")).write_text(json.dumps(kg.communities, indent=1, default=str))


def load_graph(path: Path) -> KnowledgeGraph:
    return pickle.loads(path.read_bytes())
