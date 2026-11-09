"""Download the WANDS dataset (Wayfair) — ~43k products, 480 queries, 233k relevance judgments."""

import sys
import urllib.request
from pathlib import Path

from app.core.config import settings

BASE = "https://github.com/wayfair/WANDS/raw/main/dataset/"
FILES = ("product.csv", "query.csv", "label.csv")


def main() -> None:
    out = settings.raw_dir / "wands"
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest: Path = out / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"✓ {name} already present ({dest.stat().st_size / 1e6:.1f} MB)")
            continue
        print(f"↓ {name} ...", end=" ", flush=True)
        urllib.request.urlretrieve(BASE + name, dest)
        print(f"{dest.stat().st_size / 1e6:.1f} MB")
    print(f"WANDS ready in {out}")


if __name__ == "__main__":
    sys.exit(main())
