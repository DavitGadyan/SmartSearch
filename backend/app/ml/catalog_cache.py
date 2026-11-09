"""In-memory catalog snapshot used by retrieval, ranking, recommendations and the simulator."""

import json
import time

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bandit.context import category_group
from app.core.config import settings
from app.core.logging import get_logger
from app.ml.retrieval.bm25 import BM25Index
from app.ml.retrieval.embedder import product_text
from app.ml.retrieval.semantic import SemanticIndex

log = get_logger("catalog")

STAT_COLS = [
    "impressions_7d",
    "clicks_7d",
    "impressions_30d",
    "clicks_30d",
    "carts_30d",
    "purchases_30d",
    "revenue_30d",
    "ctr_30d",
    "cart_rate_30d",
    "conversion_30d",
    "popularity",
]


class CatalogCache:
    def __init__(self, df: pd.DataFrame, emb: np.ndarray, stats: pd.DataFrame) -> None:
        self.df = df.reset_index(drop=True)
        self.ids = self.df["id"].to_numpy(dtype=np.int64)
        self.id_to_pos = {int(i): p for p, i in enumerate(self.ids)}
        self.emb = emb
        self.stats = stats.reset_index(drop=True)
        self.n = len(self.df)
        self.semantic = SemanticIndex(emb)
        self.names = self.df["name"].fillna("").astype(str).to_numpy()
        docs = [
            product_text(r.name, r.product_class, r.attributes) + " . " + (r.brand or "")
            for r in self.df.itertuples(index=False)
        ]
        self.bm25 = BM25Index(docs)  # title + class + attributes + brand
        self.bm25_title = BM25Index(
            list(self.names)
        )  # title only: sharper "is this literally the thing" signal
        # Pre-extracted arrays for fast feature building
        self.price = self.df["price"].to_numpy(dtype=np.float32)
        self.log_price = np.log1p(self.price)
        self.rating = self.df["rating"].fillna(0).to_numpy(dtype=np.float32)
        self.log_reviews = np.log1p(self.df["review_count"].fillna(0).to_numpy(dtype=np.float32))
        self.in_stock = self.df["in_stock"].to_numpy(dtype=np.float32)
        self.is_new = self.df["is_new"].to_numpy(dtype=np.float32)
        self.product_class = self.df["product_class"].fillna("").to_numpy()
        self.brand = self.df["brand"].fillna("").to_numpy()
        self.top_category = self.df["top_category"].fillna("").str.strip().to_numpy()
        self.class_group = {
            c: category_group(t) for c, t in zip(self.product_class, self.top_category, strict=True)
        }
        self.style = np.array([(a or {}).get("style") or "" for a in self.df["attributes"]])
        self.material = np.array([(a or {}).get("material") or "" for a in self.df["attributes"]])
        self.color = np.array([(a or {}).get("color") or "" for a in self.df["attributes"]])
        cls_series = pd.Series(self.price).groupby(self.product_class)
        self.price_z = (
            (self.price - cls_series.transform("mean").to_numpy())
            / (cls_series.transform("std").fillna(1).replace(0, 1).to_numpy())
        ).astype(np.float32)
        self.class_names = sorted({c for c in self.product_class if c})
        self.has_image = self.df["image_url"].notna().to_numpy()  # display preference in the rails
        self.refresh_stat_arrays()

    def refresh_stat_arrays(self) -> None:
        s = self.stats
        self.stat = {c: s[c].fillna(0).to_numpy(dtype=np.float32) for c in STAT_COLS}
        self.popularity = self.stat["popularity"]

    def positions(self, product_ids: list[int]) -> np.ndarray:
        return np.array([self.id_to_pos[i] for i in product_ids if i in self.id_to_pos], dtype=np.int64)

    def record(self, pos: int) -> dict:
        r = self.df.iloc[pos]
        return {
            "id": int(r.id),
            "name": r["name"],
            "product_class": r.product_class,
            "brand": r.brand,
            "price": float(r.price),
            "rating": None if pd.isna(r.rating) else float(r.rating),
            "review_count": int(r.review_count),
            "in_stock": bool(r.in_stock),
            "is_new": bool(r.is_new),
            "attributes": r.attributes or {},
            "image_url": r.image_url,
        }


async def load_catalog(engine: AsyncEngine) -> CatalogCache:
    t0 = time.perf_counter()
    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT id, name, product_class, brand, price::float AS price, rating, review_count, in_stock, is_new, "
                        "attributes::text AS attributes, image_url, "
                        "split_part(coalesce(category_hierarchy, ''), '/', 1) AS top_category FROM products ORDER BY id"
                    )
                )
            )
            .mappings()
            .all()
        )
        df = pd.DataFrame(rows)
        df["attributes"] = df["attributes"].map(lambda s: json.loads(s) if s else {})
        stats = pd.DataFrame(
            (
                await conn.execute(
                    text(f"SELECT product_id, {', '.join(STAT_COLS)} FROM product_stats ORDER BY product_id")
                )
            )
            .mappings()
            .all()
        )
        stats = (
            df[["id"]]
            .merge(stats, left_on="id", right_on="product_id", how="left")
            .drop(columns=["product_id"])
        )
        for c in STAT_COLS:
            stats[c] = stats[c].astype(float).fillna(0)

        emb_path = settings.artifacts_dir / "product_embeddings.npy"
        ids_path = settings.artifacts_dir / "product_ids.npy"
        if emb_path.exists() and ids_path.exists() and np.array_equal(np.load(ids_path), df["id"].to_numpy()):
            emb = np.load(emb_path).astype(np.float32)
        else:
            log.warning("embedding artifact missing/stale - loading vectors from Postgres")
            vec_rows = (
                (await conn.execute(text("SELECT embedding::text FROM products ORDER BY id"))).scalars().all()
            )
            emb = np.array(
                [json.loads(v) if v else np.zeros(settings.embedding_dim) for v in vec_rows], dtype=np.float32
            )
    cache = CatalogCache(df, emb, stats)
    log.info("catalog loaded: %d products, emb %s, %.1fs", cache.n, emb.shape, time.perf_counter() - t0)
    return cache
