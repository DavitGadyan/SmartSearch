"""Generate product photos with Higgsfield for the products shoppers see most (home rails, head queries, most-shown),
store them as frontend/public/img/products/<id>.webp, record prompt + model + status per product in manifest.json
(provenance of every generated image) and set products.image_url. Idempotent: existing files are kept and registered.
Without HF_API_KEY_ID/HF_API_KEY_SECRET (or with --dry-run) it prints the prompts instead of calling the API."""

import argparse
import asyncio
import json
import sys
import time

from app.core.config import settings
from app.core.db import asyncpg_connect
from app.imagery import Higgsfield, HiggsfieldError, fetch, product_prompt, save_image

HOME_QUERIES = [  # the storefront's suggested searches + common heads
    "modern leather accent chair under 300",
    "farmhouse dining table",
    "outdoor patio umbrella",
    "mid-century nightstand",
    "boho area rug 8x10",
    "industrial bar stools",
    "bunk bed",
    "platform bed",
    "sofa",
    "desk lamp",
    "bar cart",
    "bookcase",
    "coffee table",
    "office chair",
    "kitchen island",
    "bathroom vanity",
    # the assistant's starter prompts, as the search queries the agent issues for them
    "camping cookware for hiking",
    "modern walnut nightstand",
    "nightstand bedside table",
    "wood nightstand with drawer",
    "cozy small balcony furniture decor",
]
WAVE = 8  # requests in flight per wave


async def select_ids(
    conn, limit: int, queries: list[str], rails_k: int = 12, per_query: int = 6
) -> list[int]:
    ids: list[int] = []
    ids += [
        r["id"]
        for r in await conn.fetch(
            "SELECT p.id FROM products p JOIN product_stats s ON s.product_id = p.id WHERE p.in_stock "
            "ORDER BY s.popularity DESC LIMIT $1",
            rails_k,
        )
    ]
    ids += [
        r["id"]
        for r in await conn.fetch(
            "SELECT p.id FROM products p JOIN product_stats s ON s.product_id = p.id WHERE p.in_stock AND p.is_new "
            "ORDER BY s.popularity + 1e-3 * coalesce(p.rating, 0) DESC LIMIT $1",
            rails_k,
        )
    ]
    if queries:  # same ranking code the API uses, no personalisation, nothing logged
        from app.ml.ranking.strategies import rank
        from app.services.runtime import runtime

        await runtime.load()
        for q in queries:
            pq, qvec = runtime.parse(q)
            res = rank(
                "hybrid_ltr",
                pq,
                qvec,
                runtime.catalog,
                runtime.classes,
                runtime.ranker,
                None,
                settings.retrieval_top_k,
            )
            ids += [int(runtime.catalog.ids[p]) for p in res.positions[:per_query]]
    ids += [
        r["product_id"]
        for r in await conn.fetch(
            "SELECT product_id FROM product_stats ORDER BY impressions_30d DESC LIMIT $1", limit
        )
    ]
    return list(dict.fromkeys(ids))[:limit]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated product ids (skips selection)")
    ap.add_argument("--limit", type=int, default=96)
    ap.add_argument(
        "--queries", nargs="*", default=HOME_QUERIES, help="head queries whose top results get photos"
    )
    ap.add_argument("--model", default=settings.image_model, help="qwen | soul | z-image | <api path>")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    args = ap.parse_args()

    out_dir = settings.images_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest: dict[str, dict] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    conn = await asyncpg_connect()
    try:
        ids = (
            [int(x) for x in args.ids.split(",")]
            if args.ids
            else await select_ids(conn, args.limit, args.queries)
        )
        rows = await conn.fetch(
            "SELECT id, name, product_class, category_hierarchy, attributes::text AS attributes, description "
            "FROM products WHERE id = ANY($1::int[])",
            ids,
        )
        prods = {r["id"]: {**dict(r), "attributes": json.loads(r["attributes"] or "{}")} for r in rows}
        prods = {i: prods[i] for i in ids if i in prods}

        client = None if args.dry_run else Higgsfield.from_settings()
        pending = [i for i in prods if not (out_dir / f"{i}.webp").exists()]
        for i, p in prods.items():  # a generated image keeps the prompt it was made with
            m = manifest.setdefault(str(i), {})
            m["name"] = p["name"]
            if i in pending:
                m["prompt"] = product_prompt(p)
        print(
            f"{len(prods)} products selected, {len(prods) - len(pending)} already have a photo, {len(pending)} pending"
        )

        if client is None:
            why = "dry run" if args.dry_run else "no HF_API_KEY_ID/HF_API_KEY_SECRET"
            for i in pending:
                manifest[str(i)].update(status="prompt-only")
                print(f"\n[{i}] {manifest[str(i)]['prompt']}")
            print(f"\nprompt-only ({why}); nothing generated", file=sys.stderr)
        else:
            t0, done, failed = time.perf_counter(), 0, 0
            for w in range(0, len(pending), WAVE):
                wave = pending[w : w + WAVE]
                reqs: dict[int, str] = {}
                for i in wave:
                    try:
                        reqs[i] = client.submit(manifest[str(i)]["prompt"], args.model)
                    except HiggsfieldError as e:
                        manifest[str(i)].update(status="failed", error=str(e))
                        failed += 1
                for i, rid in reqs.items():
                    try:
                        url = client.result_url(rid)
                        save_image(fetch(url), out_dir / f"{i}.webp")
                        manifest[str(i)].update(
                            status="generated", model=args.model, request_id=rid, via="rest"
                        )
                        manifest[str(i)].pop("error", None)
                        done += 1
                    except HiggsfieldError as e:
                        manifest[str(i)].update(status="failed", error=str(e), request_id=rid)
                        failed += 1
                print(
                    f"wave {w // WAVE + 1}: {done} generated, {failed} failed, {time.perf_counter() - t0:.0f}s"
                )

        present = {int(f.stem) for f in out_dir.glob("*.webp") if f.stem.isdigit()}
        await conn.executemany(
            "UPDATE products SET image_url = $2 WHERE id = $1",
            [(i, f"/img/products/{i}.webp") for i in present],
        )
        await conn.execute(
            "UPDATE products SET image_url = NULL WHERE image_url IS NOT NULL AND NOT (id = ANY($1::int[]))",
            list(present),
        )
        for i in present:
            manifest.setdefault(str(i), {}).setdefault("status", "generated")
        manifest_path.write_text(
            json.dumps(dict(sorted(manifest.items(), key=lambda kv: int(kv[0]))), indent=1)
        )
        print(
            f"{len(present)} products have image_url set; manifest: {manifest_path}. Restart the API to reload the catalog."
        )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
