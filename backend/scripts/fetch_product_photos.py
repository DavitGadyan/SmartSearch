"""A representative photo for every product, from the Amazon Berkeley Objects dataset (CC BY 4.0).

WANDS ships product text only. ABO ships 147k Amazon home-goods listings with catalog photos. For each product we take
the photo of the most similar ABO item by text embedding (name + type, the same model2vec embedder the search uses),
with a similarity floor and a cap on how many products may share one photo, so grids stay varied. Products that find
nothing above the floor keep the category tile. Generated photos (`make images`) are never overwritten.

    make photos                      # download (~3.3 GB, once), match, extract, update the database
    make photos ARGS="--dry-run"     # match only; writes the parquet and a contact sheet to inspect the threshold
    make photos ARGS="--threshold 0.5 --cap 2"

Outputs: data/processed/photos/<product_id>.jpg (served by the API at /static/photos), photo_matches.parquet,
photos/_sheet.html (40 random matches). Images are data, not repository content.
"""

import argparse
import asyncio
import csv
import gzip
import json
import re
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.db import asyncpg_connect
from app.ml.retrieval.embedder import get_embedder

BASE = "https://amazon-berkeley-objects.s3.amazonaws.com/archives/"
ARCHIVES = ("abo-listings.tar", "abo-images-small.tar")
RAW = settings.raw_dir / "abo"
OUT = settings.processed_dir / "photos"
URL_PREFIX = "/img/photos/"

# ABO spans every Amazon category; these product types cannot be a furniture or decor match
BLOCKED = re.compile(
    r"SHOE|BOOT|SANDAL|APPAREL|SHIRT|PANTS|DRESS|JACKET|SOCK|UNDERWEAR|BRA\b|SWIMWEAR|HAT|GLOVE|SCARF|BELT|WALLET|HANDBAG|"
    r"BACKPACK|LUGGAGE|WATCH|JEWELRY|RING|NECKLACE|EARRING|SUNGLASS|EYEWEAR|"
    r"CELLULAR|PHONE|HEADPHONE|EARBUD|SPEAKER|CABLE|CHARGER|BATTERY|ADAPTER|COMPUTER|LAPTOP|TABLET|KEYBOARD|MOUSE|MONITOR|"
    r"CAMERA|PRINTER|TELEVISION|ELECTRONIC|VIDEO_GAME|SOFTWARE|MEMORY|DRIVE|ROUTER|"
    r"FOOD|GROCERY|BEVERAGE|COFFEE|TEA\b|SNACK|SUPPLEMENT|VITAMIN|HEALTH|MEDICAL|BEAUTY|SKIN|HAIR|SHAMPOO|COSMETIC|"
    r"TOOTH|RAZOR|DEODORANT|BABY_PRODUCT|DIAPER|PET_FOOD|PET_SUPPL|TOY|GAME\b|PUZZLE|BOOK|MUSIC|DVD|"
    r"AUTO|VEHICLE|TIRE|MOTOR|BIKE|BICYCLE|SPORTING|FITNESS|OFFICE_PRODUCTS|PAPER|PEN\b|INK|CARTRIDGE|LABEL|"
    r"POWER_TOOL|HARDWARE|FASTENER|ABIS_|WIRELESS|SECURITY|SURVEILLANCE|GIFT_CARD|SUBSCRIPTION"
)
ENGLISH = ("en_US", "en_GB", "en_CA", "en_AU", "en_IN", "en_SG", "en_AE")


# ---------------------------------------------------------------- download


def download(name: str) -> Path:
    """Resumable download; verified against the server's Content-Length."""
    dest = RAW / name
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(BASE + name, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers["Content-Length"])
    have = dest.stat().st_size if dest.exists() else 0
    if have == total:
        return dest
    if have > total:
        dest.unlink()
        have = 0
    print(f"downloading {name}: {have / 1e9:.2f} / {total / 1e9:.2f} GB")
    req = urllib.request.Request(BASE + name, headers={"Range": f"bytes={have}-"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "ab") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
            have += len(chunk)
            if have % (200 << 20) < (1 << 20):
                rate = (have / 1e6) / max(time.time() - t0, 1e-6)
                print(f"  {have / 1e9:.2f} GB  ({rate:.1f} MB/s)", flush=True)
    if dest.stat().st_size != total:
        raise RuntimeError(f"{name}: incomplete download")
    return dest


# ---------------------------------------------------------------- listings


def load_listings(tar_path: Path) -> pd.DataFrame:
    """One row per ABO item with photos and an English name: item_id, image_ids (main first, up to 4), text."""
    rows = []
    with tarfile.open(tar_path) as tar:
        for m in tar.getmembers():
            if not m.name.endswith(".json.gz"):
                continue
            with gzip.open(tar.extractfile(m)) as f:  # type: ignore[arg-type]
                for line in f:
                    d = json.loads(line)
                    img = d.get("main_image_id")
                    if not img:
                        continue
                    names = {n["language_tag"]: n["value"] for n in d.get("item_name", []) if "value" in n}
                    name = next((names[t] for t in ENGLISH if t in names), None)
                    if not name:
                        continue
                    ptype = (d.get("product_type") or [{}])[0].get("value", "")
                    if BLOCKED.search(ptype):
                        continue
                    kind = ptype.lower().replace("_", " ")
                    images = [img] + [i for i in d.get("other_image_id", []) if i != img][:3]
                    rows.append((d["item_id"], images, f"{name} . {kind}", ptype))
    df = pd.DataFrame(rows, columns=["item_id", "image_ids", "text", "product_type"]).drop_duplicates(
        "item_id"
    )
    print(
        f"ABO listings usable: {len(df):,} ({df.product_type.nunique()} product types, "
        f"{int(df.image_ids.map(len).sum()):,} photos)"
    )
    return df


def load_image_paths(tar_path: Path) -> dict[str, str]:
    with tarfile.open(tar_path) as tar:
        member = tar.getmember("images/metadata/images.csv.gz")
        with gzip.open(tar.extractfile(member), "rt") as f:  # type: ignore[arg-type]
            return {r["image_id"]: r["path"] for r in csv.DictReader(f)}


# ---------------------------------------------------------------- matching


def match(wands: pd.DataFrame, abo: pd.DataFrame, threshold: float, cap: int, top: int = 5) -> pd.DataFrame:
    """Greedy best-first assignment: highest similarities first, at most `cap` products per ABO photo; an item hands
    out its least-used photo first, so products matched to the same item get different angles."""
    emb = get_embedder()
    t0 = time.time()
    a = emb.encode(abo["text"].tolist())
    w = emb.encode(wands["text"].tolist())
    print(f"embedded {len(a):,} + {len(w):,} texts in {time.time() - t0:.0f}s")

    cand_idx = np.empty((len(w), top), dtype=np.int64)
    cand_sim = np.empty((len(w), top), dtype=np.float32)
    for s in range(0, len(w), 512):
        sims = w[s : s + 512] @ a.T
        part = np.argpartition(-sims, top, axis=1)[:, :top]
        cand_idx[s : s + 512] = part
        cand_sim[s : s + 512] = np.take_along_axis(sims, part, axis=1)

    pairs = [(float(cand_sim[i, j]), i, int(cand_idx[i, j])) for i in range(len(w)) for j in range(top)]
    pairs.sort(reverse=True)
    used: dict[str, int] = {}
    chosen: dict[int, tuple[int, float, str]] = {}
    image_lists = abo["image_ids"].tolist()
    for sim, i, j in pairs:
        if sim < threshold:
            break
        if i in chosen:
            continue
        img = min(image_lists[j], key=lambda x: used.get(x, 0))
        if used.get(img, 0) >= cap:
            continue
        used[img] = used.get(img, 0) + 1
        chosen[i] = (j, sim, img)

    out = pd.DataFrame(
        {
            "product_id": wands["id"].to_numpy(),
            "best_sim": cand_sim.max(axis=1),
            "abo_item_id": [abo["item_id"].iat[chosen[i][0]] if i in chosen else None for i in range(len(w))],
            "image_id": [chosen[i][2] if i in chosen else None for i in range(len(w))],
            "abo_text": [abo["text"].iat[chosen[i][0]] if i in chosen else None for i in range(len(w))],
            "score": [chosen[i][1] if i in chosen else np.nan for i in range(len(w))],
        }
    )
    print(
        f"matched {out.image_id.notna().sum():,} / {len(out):,} products at threshold {threshold} "
        f"(cap {cap}); median similarity {np.nanmedian(out.score):.3f}"
    )
    return out


# ---------------------------------------------------------------- extraction


def extract(tar_path: Path, matches: pd.DataFrame, paths: dict[str, str]) -> int:
    """One pass over the images tar; each needed image is written once per product that uses it."""
    OUT.mkdir(parents=True, exist_ok=True)
    wanted: dict[str, list[int]] = {}
    for pid, img in zip(matches["product_id"], matches["image_id"], strict=True):
        if img and (OUT / f"{pid}.jpg").exists() is False:
            wanted.setdefault("images/small/" + paths[img], []).append(int(pid))
    written = 0
    with tarfile.open(tar_path) as tar:
        for m in tar:
            targets = wanted.get(m.name)
            if not targets:
                continue
            data = tar.extractfile(m).read()  # type: ignore[union-attr]
            for pid in targets:
                (OUT / f"{pid}.jpg").write_bytes(data)
                written += 1
    print(f"wrote {written:,} photos to {OUT}")
    return written


def contact_sheet(matches: pd.DataFrame, wands: pd.DataFrame, n: int = 40, seed: int = 7) -> Path:
    ok = matches[matches.image_id.notna()].merge(
        wands[["id", "name", "product_class"]], left_on="product_id", right_on="id"
    )
    sample = ok.sample(min(n, len(ok)), random_state=seed).sort_values("score")
    cells = "".join(
        f'<figure><img src="{int(r.product_id)}.jpg" loading="lazy"><figcaption><b>{r.name}</b><br>'
        f"<small>{r.product_class}</small><br><i>{r.abo_text}</i><br>sim {r.score:.2f}</figcaption></figure>"
        for r in sample.itertuples()
    )
    html = (
        "<!doctype html><meta charset=utf-8><title>photo matches</title><style>body{font:13px system-ui;margin:16px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}figure{margin:0;border:1px solid #ddd;"
        "border-radius:8px;padding:8px}img{width:100%;aspect-ratio:1;object-fit:contain;background:#f6f6f6;border-radius:6px}"
        f"figcaption{{margin-top:6px;line-height:1.35}}</style><p>{len(sample)} random matches, lowest similarity first</p><div class=g>{cells}</div>"
    )
    dest = OUT / "_sheet.html"
    dest.write_text(html)
    return dest


# ---------------------------------------------------------------- main


async def load_wands(conn) -> pd.DataFrame:
    rows = await conn.fetch("SELECT id, name, product_class, image_url FROM products ORDER BY id")
    df = pd.DataFrame([dict(r) for r in rows])
    cls = df["product_class"].fillna("").str.replace("|", " ", regex=False).str.strip()
    df["text"] = df["name"].str.strip() + " . " + cls.str.lower()
    return df


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--threshold", type=float, default=0.5, help="cosine floor below which a product keeps its tile"
    )
    ap.add_argument(
        "--cap", type=int, default=3, help="max products sharing one ABO photo (items have up to 4 photos)"
    )
    ap.add_argument("--dry-run", action="store_true", help="download + match + sheet; no database change")
    ap.add_argument("--delete-archives", action="store_true", help="remove the 3.3 GB image tar afterwards")
    a = ap.parse_args()

    listings_tar, images_tar = (download(n) for n in ARCHIVES)
    conn = await asyncpg_connect()
    try:
        wands = await load_wands(conn)
        abo = load_listings(listings_tar)
        matches = match(wands, abo, a.threshold, a.cap)
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        matches.to_parquet(settings.processed_dir / "photo_matches.parquet", index=False)
        paths = load_image_paths(images_tar)
        extract(images_tar, matches, paths)
        sheet = contact_sheet(matches, wands)
        print(f"contact sheet: {sheet} (served at /static/photos/_sheet.html)")
        if not a.dry_run:
            ids = [int(p) for p, img in zip(matches.product_id, matches.image_id, strict=True) if img]
            n = await conn.execute(
                "UPDATE products SET image_url = $2 || id::text || '.jpg' WHERE id = ANY($1::int[]) AND image_url IS NULL",
                ids,
                URL_PREFIX,
            )
            print(f"database: {n} (generated photos kept). Restart the API to reload the catalog.")
    finally:
        await conn.close()
    if a.delete_archives:
        images_tar.unlink()
        print("removed", images_tar)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
