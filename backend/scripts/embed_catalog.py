"""Embed every product and write vectors to products.embedding (pgvector). Also caches a .npy matrix for the ranker."""

import asyncio
import json
import sys

import numpy as np

from app.core.config import settings
from app.core.db import asyncpg_connect
from app.ml.retrieval.embedder import get_embedder, product_text


async def main() -> None:
    emb = get_embedder()
    assert emb.dim == settings.embedding_dim, (
        f"EMBEDDING_DIM={settings.embedding_dim} but model dim is {emb.dim}"
    )
    conn = await asyncpg_connect()
    try:
        rows = await conn.fetch("SELECT id, name, product_class, attributes FROM products ORDER BY id")
        if not rows:
            sys.exit("products table is empty — run scripts/build_catalog.py first")
        texts = [product_text(r["name"], r["product_class"], json.loads(r["attributes"])) for r in rows]
        print(f"embedding {len(texts):,} products with {emb.name} (dim={emb.dim}) ...", flush=True)
        vecs = emb.encode(texts)
        ids = np.array([r["id"] for r in rows], dtype=np.int64)

        await conn.execute("DROP INDEX IF EXISTS ix_products_embedding_hnsw")
        await conn.execute(f"CREATE TEMP TABLE tmp_emb (id int PRIMARY KEY, embedding vector({emb.dim}))")
        await conn.copy_records_to_table(
            "tmp_emb", records=zip(ids.tolist(), vecs, strict=True), columns=["id", "embedding"]
        )
        await conn.execute("UPDATE products p SET embedding = t.embedding FROM tmp_emb t WHERE t.id = p.id")
        await conn.execute(
            "CREATE INDEX ix_products_embedding_hnsw ON products USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        await conn.execute("ANALYZE products")
    finally:
        await conn.close()

    np.save(settings.artifacts_dir / "product_embeddings.npy", vecs)
    np.save(settings.artifacts_dir / "product_ids.npy", ids)
    print(f"done → {settings.artifacts_dir}/product_embeddings.npy {vecs.shape}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
