"""Refresh product_stats and the analytics marts. Usage: refresh_marts.py [--only product_stats.sql,...] [--as-of ISO]"""

import argparse
import asyncio
import sys
from datetime import datetime

from app.analytics.marts import refresh_all
from app.core.db import engine


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--as-of", default=None)
    a = ap.parse_args()
    as_of = datetime.fromisoformat(a.as_of) if a.as_of else None
    res = await refresh_all(engine, as_of=as_of, only=a.only.split(",") if a.only else None)
    for k, v in res.items():
        print(f"{k:32s} {v:6.1f}s")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
