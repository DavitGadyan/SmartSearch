"""Offline recommendation evaluation on Retailrocket's real clickstream (next-item prediction, temporal split)."""

import argparse
import json
import sys
import time
from collections import defaultdict

import duckdb
import numpy as np
import pandas as pd

from app.core.config import settings
from app.ml.recs.item_item import build_cooccurrence

RAW = settings.raw_dir / "retailrocket"
K_RECALL, K_HIT, K_NDCG = 20, 10, 20


def load_events(path) -> pd.DataFrame:
    q = f"""
        SELECT visitorid::BIGINT AS visitor, itemid::BIGINT AS item,
               CASE event WHEN 'view' THEN 'click' WHEN 'addtocart' THEN 'add_to_cart' WHEN 'transaction' THEN 'purchase' END AS event_type,
               to_timestamp(timestamp / 1000) AS ts
        FROM read_csv_auto('{path}')
        WHERE event IN ('view', 'addtocart', 'transaction')
    """
    return duckdb.query(q).to_df()


def metrics(ranked: list[int], truth: set[int]) -> dict:
    hits = [1 if i in truth else 0 for i in ranked[:K_RECALL]]
    dcg = sum(h / np.log2(r + 2) for r, h in enumerate(hits[:K_NDCG]))
    idcg = sum(1 / np.log2(r + 2) for r in range(min(len(truth), K_NDCG)))
    return {
        f"hit@{K_HIT}": float(any(hits[:K_HIT])),
        f"recall@{K_RECALL}": sum(hits) / len(truth),
        f"ndcg@{K_NDCG}": dcg / idcg if idcg else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=str(RAW / "events.csv"))
    ap.add_argument("--test-days", type=int, default=14)
    ap.add_argument("--max-test-users", type=int, default=20_000)
    a = ap.parse_args()
    if not (p := __import__("pathlib").Path(a.events)).exists():
        print(f"{p} not found - run scripts/download_retailrocket.py first")
        return 0

    t0 = time.perf_counter()
    ev = load_events(a.events)
    n_events = len(ev)
    views = (ev.event_type == "click").sum()
    carts = (ev.event_type == "add_to_cart").sum()
    buys = (ev.event_type == "purchase").sum()
    funnel = {
        "views": int(views),
        "add_to_carts": int(carts),
        "transactions": int(buys),
        "view_to_cart": float(carts / views),
        "cart_to_transaction": float(buys / carts),
    }
    print(
        f"{n_events:,} events · funnel view→cart {funnel['view_to_cart']:.2%}, cart→transaction {funnel['cart_to_transaction']:.1%}"
    )

    cutoff = ev.ts.max() - pd.Timedelta(days=a.test_days)
    train, test = ev[ev.ts < cutoff], ev[ev.ts >= cutoff]
    train = train.assign(session_id=train.visitor.astype(str) + "_" + train.ts.dt.strftime("%Y%m%d"))
    sim = build_cooccurrence(
        train.rename(columns={"item": "product_id"}), min_support=2, top_k=50, by="session_id"
    )
    neighbors: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r in sim.itertuples(index=False):
        neighbors[r.product_id].append((r.neighbor_id, r.score))
    pop = train.groupby("item").size().sort_values(ascending=False)
    pop_list = pop.index.tolist()[:K_RECALL]
    print(
        f"train {len(train):,} / test {len(test):,} · {sim.product_id.nunique():,} items with neighbours ({time.perf_counter() - t0:.0f}s)"
    )

    hist = train.sort_values("ts").groupby("visitor").item.apply(lambda s: s.tolist()[-10:])
    truth = test.groupby("visitor").item.apply(set)
    users = [u for u in truth.index if u in hist.index][: a.max_test_users]
    agg = {"popularity": defaultdict(list), "item_item_cf": defaultdict(list)}
    covered = 0
    for u in users:
        seen = hist[u]
        t = truth[u] - set(seen)
        if not t:
            continue
        scores: dict[int, float] = defaultdict(float)
        for w, item in enumerate(reversed(seen)):
            for nb, s in neighbors.get(item, []):
                if nb not in seen:
                    scores[nb] += s * 0.85**w
        cf = [i for i, _ in sorted(scores.items(), key=lambda x: -x[1])[:K_RECALL]]
        if cf:
            covered += 1
        cf = (cf + [i for i in pop_list if i not in cf and i not in seen])[:K_RECALL]
        for name, ranked in (
            ("popularity", [i for i in pop_list if i not in seen][:K_RECALL]),
            ("item_item_cf", cf),
        ):
            for k, v in metrics(ranked, t).items():
                agg[name][k].append(v)
    n_eval = len(agg["popularity"][f"hit@{K_HIT}"])
    out = {
        "dataset": "Retailrocket (Kaggle retailrocket/ecommerce-dataset)",
        "split": f"temporal: last {a.test_days} days held out",
        "n_events": int(n_events),
        "n_items": int(ev.item.nunique()),
        "n_users_test": int(n_eval),
        "cf_coverage": round(covered / max(n_eval, 1), 4),
        "models": {m: {k: round(float(np.mean(v)), 4) for k, v in d.items()} for m, d in agg.items()},
        "funnel": funnel,
    }
    (settings.artifacts_dir / "retailrocket_eval.json").write_text(json.dumps(out, indent=1))
    for m, d in out["models"].items():
        print(f"  {m:14s} {d}")
    print(f"saved {settings.artifacts_dir / 'retailrocket_eval.json'} ({time.perf_counter() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
