"""Build the product catalog from WANDS and load products, queries and relevance labels into Postgres."""

import asyncio
import csv
import json
import re
import sys
from decimal import Decimal

import mmh3
import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.db import asyncpg_connect

csv.field_size_limit(10**8)
RAW = settings.raw_dir / "wands"
SEED = 42

# Price band (USD, median) by top-level category; per-class and per-product noise applied on top.
CATEGORY_MEDIAN_PRICE = {
    "furniture": 420,
    "outdoor": 310,
    "rugs": 160,
    "lighting": 140,
    "home improvement": 90,
    "décor & pillows": 60,
    "decor & pillows": 60,
    "bed & bath": 70,
    "kitchen & tabletop": 55,
    "storage & organization": 85,
    "baby & kids": 180,
    "pet": 60,
    "appliances": 480,
    "renovation": 120,
    "holiday décor": 40,
    "school furniture and supplies": 260,
}
DEFAULT_MEDIAN_PRICE = 120

BRANDS = [
    "Northwick",
    "Halden & Co",
    "Linea Casa",
    "Oakridge",
    "Maren Home",
    "Verve Living",
    "Stonebridge",
    "Loft & Ember",
    "Cedar Lane",
    "Atelier Nord",
    "Brightwater",
    "Ellery",
    "Foxcroft",
    "Granite Bay",
    "Harlow Studio",
    "Ironwood",
    "Juniper & Vale",
    "Kessler",
    "Lumen",
    "Marlow",
    "Nova Terra",
    "Orchard House",
    "Pembroke",
    "Quill & Oak",
    "Rowan",
    "Sable & Fern",
    "Tidewater",
    "Umber",
    "Vantage Home",
    "Willowmere",
    "Ashby",
    "Beacon Hill",
    "Cobalt Studio",
    "Driftwood Co",
    "Everly",
    "Finch & Co",
    "Greyson",
    "Hearthstone",
    "Indigo Loft",
    "Jasper Lane",
]

STYLE_MAP = {
    "modern & contemporary": "modern",
    "modern": "modern",
    "ultra-modern": "modern",
    "transitional modern": "modern",
    "mid-century modern": "mid-century",
    "traditional": "traditional",
    "transitional traditional": "traditional",
    "farmhouse / country": "farmhouse",
    "country / farmhouse": "farmhouse",
    "rustic": "rustic",
    "lodge": "rustic",
    "coastal": "coastal",
    "glam": "glam",
    "industrial": "industrial",
    "boho": "boho",
    "eclectic": "eclectic",
}


def clean_text(t: str) -> str:
    """Undo WANDS tokenizer artifacts: `28 '' wide` → `28" wide`, `women 's` → `women's`, ` , ` → `, `."""
    t = re.sub(r"\s*''", '"', t)
    t = re.sub(r"\s+'s\b", "'s", t)
    t = re.sub(r"\s+([,.;:!?)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_features(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for kv in (raw or "").split("|"):
        if ":" in kv:
            k, v = kv.split(":", 1)
            k, v = k.strip().lower(), v.strip().lower()
            if k and v and k not in out:
                out[k] = v
    return out


def first(f: dict, *keys: str) -> str | None:
    for k in keys:
        if f.get(k):
            return f[k]
    return None


def to_float(v: str | None) -> float | None:
    if not v:
        return None
    m = re.search(r"\d+(\.\d+)?", v)
    return float(m.group()) if m else None


def h(*parts: object) -> float:
    """Deterministic uniform [0,1) from any key."""
    return (mmh3.hash(":".join(map(str, parts)), SEED, signed=False) % 10_000_000) / 10_000_000


def build_products() -> pd.DataFrame:
    df = pd.read_csv(RAW / "product.csv", sep="\t", quoting=csv.QUOTE_NONE, dtype=str, keep_default_na=False)
    rows = []
    for r in df.itertuples(index=False):
        pid = int(r.product_id)
        feats = parse_features(r.product_features)
        cat = r[3]  # "category hierarchy" (column name has a space)
        top = cat.split("/")[0].strip().lower() if cat else ""
        pclass = (
            r.product_class.strip()
            or (cat.split("/")[-1].strip() if cat else "")
            or (feats.get("producttype") or "Other").title()
        )

        style_raw = first(feats, "style", "dsprimaryproductstyle", "dssecondaryproductstyle")
        attrs = {
            "color": first(feats, "color"),
            "style": STYLE_MAP.get(style_raw or "", style_raw),
            "material": first(feats, "material", "primarymaterial", "framematerial", "topmaterial"),
            "shape": first(feats, "shape"),
            "pattern": first(feats, "pattern"),
            "product_type": first(feats, "producttype"),
            "wood_tone": first(feats, "dswoodtone"),
            "country_of_origin": first(feats, "countryoforigin"),
            "upholstered": feats.get("upholstered"),
            "assembly_required": feats.get("adultassemblyrequired"),
            "width_in": to_float(feats.get("overallwidth-sidetoside")),
            "height_in": to_float(feats.get("overallheight-toptobottom")),
            "depth_in": to_float(feats.get("overalldepth-fronttoback")),
            "weight_capacity_lb": to_float(feats.get("weightcapacity")),
        }
        attrs = {k: v for k, v in attrs.items() if v not in (None, "", "no")}

        # --- synthetic commerce fields -------------------------------------------------------------
        median = CATEGORY_MEDIAN_PRICE.get(top, DEFAULT_MEDIAN_PRICE)
        class_mult = 0.55 + 1.4 * h("class", pclass)  # each class sits at a stable point in its category band
        noise = float(np.exp(0.45 * _norm(h("price", pid))))
        quality = 1.0 + 0.15 * ((to_float(r.average_rating) or 4.0) - 4.0)
        price = max(4.99, median * class_mult * noise * quality)
        price = round(price, 2) if price < 100 else round(price) - 0.01  # charm pricing above $100

        brand_pool = sorted(BRANDS, key=lambda b: h("brandpool", pclass, b))[:6]  # ~6 brands per class
        brand = brand_pool[min(5, int(h("brand", pid) ** 1.8 * 6))]  # skewed: 1–2 dominant brands per class
        attrs["brand"] = brand
        attrs["_synthetic"] = ["price", "brand", "in_stock", "is_new"]

        rows.append(
            dict(
                id=pid,
                name=clean_text(r.product_name),
                product_class=pclass[:128],
                category_hierarchy=cat or None,
                description=clean_text(r.product_description) if r.product_description else None,
                features_text=r.product_features or None,
                brand=brand,
                price=Decimal(f"{price:.2f}"),
                price_source="synthetic",
                rating=to_float(r.average_rating),
                review_count=int(to_float(r.review_count) or 0),
                in_stock=h("stock", pid) < 0.92,
                is_new=h("new", pid) < 0.05,
                attributes=json.dumps(attrs),
                image_url=None,
            )
        )
    return pd.DataFrame(rows)


def _norm(u: float) -> float:
    """Uniform → standard normal via inverse CDF (Acklam approximation is overkill; use scipy-free erfinv)."""
    from statistics import NormalDist

    return NormalDist().inv_cdf(min(max(u, 1e-9), 1 - 1e-9))


def build_queries() -> pd.DataFrame:
    q = pd.read_csv(RAW / "query.csv", sep="\t", dtype=str, keep_default_na=False)
    q["id"] = q["query_id"].astype(int)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(q))
    split = np.array(["train"] * len(q), dtype=object)
    n_test, n_val = int(0.2 * len(q)), int(0.1 * len(q))
    split[perm[:n_test]] = "test"
    split[perm[n_test : n_test + n_val]] = "val"
    q["split"] = split
    rank = np.empty(len(q))
    rank[rng.permutation(len(q))] = np.arange(1, len(q) + 1)
    q["popularity_weight"] = 1.0 / rank**0.8  # Zipf-like query demand for the simulator
    return q.rename(columns={"query": "text"})[["id", "text", "query_class", "split", "popularity_weight"]]


def build_labels(product_ids: set[int]) -> pd.DataFrame:
    lab = pd.read_csv(RAW / "label.csv", sep="\t", dtype=str, keep_default_na=False)
    grade = {"Exact": 2, "Partial": 1, "Irrelevant": 0}
    lab["grade"] = lab["label"].map(grade).astype(int)
    lab["query_id"] = lab["query_id"].astype(int)
    lab["product_id"] = lab["product_id"].astype(int)
    lab = lab[lab["product_id"].isin(product_ids)].drop_duplicates(["query_id", "product_id"])
    return lab[["query_id", "product_id", "grade"]]


async def load(products: pd.DataFrame, queries: pd.DataFrame, labels: pd.DataFrame) -> None:
    conn = await asyncpg_connect()
    try:
        async with conn.transaction():
            await conn.execute(
                "TRUNCATE relevance_labels, product_stats, queries, products RESTART IDENTITY CASCADE"
            )
            cols = list(products.columns)
            await conn.copy_records_to_table(
                "products", records=products.itertuples(index=False), columns=cols
            )
            await conn.copy_records_to_table(
                "queries", records=queries.itertuples(index=False), columns=list(queries.columns)
            )
            await conn.copy_records_to_table(
                "relevance_labels", records=labels.itertuples(index=False), columns=list(labels.columns)
            )
            await conn.execute(
                """
                UPDATE products SET tsv =
                  setweight(to_tsvector('english', name), 'A') ||
                  setweight(to_tsvector('english', coalesce(product_class, '')), 'B') ||
                  setweight(to_tsvector('english', coalesce(brand, '')), 'B') ||
                  setweight(to_tsvector('english', left(coalesce(description, ''), 2000)), 'C')
                """
            )
            await conn.execute("INSERT INTO product_stats (product_id) SELECT id FROM products")
            await conn.execute("ANALYZE products; ANALYZE queries; ANALYZE relevance_labels;")
    finally:
        await conn.close()


def main() -> None:
    print("building products ...", flush=True)
    products = build_products()
    queries = build_queries()
    labels = build_labels(set(products["id"]))
    print(f"products={len(products):,} queries={len(queries)} labels={len(labels):,}")
    print(
        f"price: median ${products.price.astype(float).median():.0f}, p10 ${products.price.astype(float).quantile(0.1):.0f}, p90 ${products.price.astype(float).quantile(0.9):.0f}"
    )
    print("loading into Postgres ...", flush=True)
    asyncio.run(load(products, queries, labels))
    settings.processed_dir.mkdir(exist_ok=True, parents=True)
    products.drop(columns=["features_text", "description"]).to_parquet(
        settings.processed_dir / "products.parquet"
    )
    print("done")


if __name__ == "__main__":
    sys.exit(main())
