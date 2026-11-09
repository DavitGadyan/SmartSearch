"""Build the product knowledge graph (GraphRAG substrate): typed nodes, behavioural + semantic edges, Louvain communities
with short summaries (Claude when a key is set, otherwise category-based names). Output: artifacts/graph.pkl."""

import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations

import networkx as nx
import numpy as np
from pydantic import BaseModel

from app.core.config import settings
from app.core.db import asyncpg_connect, engine
from app.graph.kg import KnowledgeGraph, save_graph
from app.ml.catalog_cache import load_catalog
from app.ml.retrieval.embedder import get_embedder

ATTRS = ("style", "material", "color")
MIN_COMMUNITY = 25
MAX_SUMMARIES = 40


class Summary(BaseModel):
    name: str
    summary: str
    who_buys: str


async def behavioural_pairs() -> tuple[Counter, Counter]:
    conn = await asyncpg_connect()
    try:
        views = await conn.fetch(
            "SELECT session_id, product_id FROM events WHERE event_type = 'click' AND product_id IS NOT NULL"
        )
        buys = await conn.fetch(
            "SELECT user_id, product_id FROM events WHERE event_type = 'purchase' AND product_id IS NOT NULL"
        )
    finally:
        await conn.close()
    co_view, co_buy = Counter(), Counter()
    by_session: dict[str, set[int]] = defaultdict(set)
    for r in views:
        by_session[r["session_id"]].add(r["product_id"])
    for items in by_session.values():
        if 2 <= len(items) <= 12:
            for a, b in combinations(sorted(items), 2):
                co_view[(a, b)] += 1
    by_user: dict[str, set[int]] = defaultdict(set)
    for r in buys:
        by_user[r["user_id"]].add(r["product_id"])
    for items in by_user.values():
        if 2 <= len(items) <= 20:
            for a, b in combinations(sorted(items), 2):
                co_buy[(a, b)] += 1
    return co_view, co_buy


async def summarise(communities: dict[int, dict]) -> None:
    if not settings.anthropic_api_key:
        for c in communities.values():
            c["name"] = " / ".join(k for k, _ in c["top_classes"][:2])
            c["summary"] = f"{c['size']} products, mostly {', '.join(k for k, _ in c['top_classes'][:3])}."
        return
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    for c in list(communities.values())[:MAX_SUMMARIES]:
        prompt = (
            "Name and describe this cluster of home products in a furniture store. Return a short name (max 5 words), a one-sentence summary of what "
            "these products have in common, and who typically buys them.\n"
            f"Top categories: {c['top_classes']}\nTop brands: {c['top_brands']}\nSample products: {c['sample_names'][:12]}"
        )
        try:
            resp = await client.messages.parse(
                model=settings.bulk_model,
                max_tokens=1024,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
                output_format=Summary,
            )
            s = resp.parsed_output
            c.update(
                {"name": s.name, "summary": s.summary, "who_buys": s.who_buys, "summary_source": "claude"}
            )
        except Exception as e:  # keep going with heuristic names
            c.update(
                {
                    "name": " / ".join(k for k, _ in c["top_classes"][:2]),
                    "summary": str(e)[:120],
                    "summary_source": "fallback",
                }
            )
    for c in list(communities.values())[MAX_SUMMARIES:]:
        c["name"] = " / ".join(k for k, _ in c["top_classes"][:2])
        c["summary"] = f"{c['size']} products, mostly {', '.join(k for k, _ in c['top_classes'][:3])}."


async def main() -> None:
    t0 = time.perf_counter()
    cache = await load_catalog(engine)
    co_view, co_buy = await behavioural_pairs()
    g = nx.Graph()
    for pos in range(cache.n):
        pid = int(cache.ids[pos])
        g.add_node(("p", pid), name=cache.names[pos], price=float(cache.price[pos]))
        if cache.product_class[pos]:
            g.add_edge(("p", pid), ("c", cache.product_class[pos]), rel="in_category")
        if cache.brand[pos]:
            g.add_edge(("p", pid), ("b", cache.brand[pos]), rel="brand")
        for attr, arr in zip(ATTRS, (cache.style, cache.material, cache.color), strict=True):
            if arr[pos]:
                g.add_edge(("p", pid), ("a", f"{attr}={arr[pos]}"), rel="attribute")
    for (a, b), w in co_view.items():
        g.add_edge(("p", a), ("p", b), rel="co_view", weight=float(w))
    cat_pairs: Counter = Counter()
    for (a, b), w in co_buy.items():
        g.add_edge(("p", a), ("p", b), rel="co_purchase", weight=float(w))
        ca, cb = cache.product_class[cache.id_to_pos[a]], cache.product_class[cache.id_to_pos[b]]
        if ca and cb and ca != cb:
            cat_pairs[tuple(sorted((ca, cb)))] += w
    for (ca, cb), w in cat_pairs.items():
        g.add_edge(("c", ca), ("c", cb), rel="co_purchase", weight=float(w))
    # semantic neighbours (top-5) so every product has at least some product-product edges
    sims = cache.emb @ cache.emb.T if cache.n <= 8000 else None
    for pos in range(cache.n):
        if sims is None:
            idx, sc = cache.semantic.neighbors(pos, 5)
        else:
            row = sims[pos].copy()
            row[pos] = -1
            idx = np.argpartition(-row, 5)[:5]
            sc = row[idx]
        for j, s in zip(idx, sc, strict=True):
            a, b = int(cache.ids[pos]), int(cache.ids[j])
            if not g.has_edge(("p", a), ("p", b)):
                g.add_edge(("p", a), ("p", b), rel="similar", weight=float(s))
    print(
        f"graph: {g.number_of_nodes():,} nodes, {g.number_of_edges():,} edges · co_view pairs {len(co_view):,} · co_purchase pairs {len(co_buy):,} ({time.perf_counter() - t0:.0f}s)"
    )

    pp = g.edge_subgraph(
        [
            (u, v)
            for u, v, d in g.edges(data=True)
            if u[0] == "p" and v[0] == "p" and d.get("rel") in ("co_view", "co_purchase", "similar")
        ]
    ).copy()
    comms = nx.community.louvain_communities(pp, weight="weight", resolution=1.0, seed=42)
    communities: dict[int, dict] = {}
    product_community: dict[int, int] = {}
    for cid, members in enumerate(
        sorted((c for c in comms if len(c) >= MIN_COMMUNITY), key=len, reverse=True)
    ):
        pids = [n[1] for n in members]
        poss = [cache.id_to_pos[p] for p in pids]
        classes = Counter(cache.product_class[p] for p in poss if cache.product_class[p]).most_common(5)
        brands = Counter(cache.brand[p] for p in poss if cache.brand[p]).most_common(3)
        communities[cid] = {
            "size": len(pids),
            "top_classes": classes,
            "top_brands": brands,
            "sample_names": [cache.names[p] for p in poss[:12]],
            "products": pids[:60],
            "median_price": float(np.median(cache.price[poss])),
        }
        for p in pids:
            product_community[p] = cid
    print(
        f"communities: {len(comms)} total, {len(communities)} with ≥{MIN_COMMUNITY} products; summarising ...",
        flush=True,
    )
    await summarise(communities)
    emb = get_embedder()
    ids = sorted(communities)
    summary_emb = (
        emb.encode([f"{communities[i]['name']}. {communities[i]['summary']}" for i in ids]) if ids else None
    )
    kg = KnowledgeGraph(
        g=g, communities=communities, product_community=product_community, summary_emb=summary_emb
    )
    save_graph(kg, settings.artifacts_dir / "graph.pkl")
    print(f"saved {settings.artifacts_dir / 'graph.pkl'} ({time.perf_counter() - t0:.0f}s)")
    print(
        json.dumps(
            [{k: v for k, v in communities[i].items() if k in ("name", "size", "summary")} for i in ids[:5]],
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
