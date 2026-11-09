"""Precompute item-item neighbors: session co-occurrence (cooccurrence) and co-purchase (copurchase) → item_similarity."""

import asyncio
import sys
import time

import pandas as pd

from app.core.db import asyncpg_connect
from app.ml.recs.item_item import build_cooccurrence


async def main() -> None:
    t0 = time.perf_counter()
    conn = await asyncpg_connect()
    try:
        rows = await conn.fetch(
            "SELECT session_id, user_id, product_id, event_type FROM events WHERE product_id IS NOT NULL "
            "AND event_type IN ('click','add_to_cart','purchase','rec_click')"
        )
        ev = pd.DataFrame([dict(r) for r in rows])
        print(f"{len(ev):,} interactions")
        co = build_cooccurrence(ev, min_support=2, top_k=20, by="session_id")
        co["method"] = "cooccurrence"
        buys = ev[ev.event_type == "purchase"]
        cp = build_cooccurrence(buys, min_support=1, top_k=20, by="user_id")
        cp["method"] = "copurchase"
        out = pd.concat([co, cp], ignore_index=True)
        async with conn.transaction():
            await conn.execute("TRUNCATE item_similarity RESTART IDENTITY")
            await conn.copy_records_to_table(
                "item_similarity",
                columns=["product_id", "neighbor_id", "score", "method"],
                records=out[["product_id", "neighbor_id", "score", "method"]].itertuples(index=False),
            )
            await conn.execute("ANALYZE item_similarity")
        print(
            f"cooccurrence pairs={len(co):,} items={co.product_id.nunique():,} | copurchase pairs={len(cp):,} ({time.perf_counter() - t0:.0f}s)"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
