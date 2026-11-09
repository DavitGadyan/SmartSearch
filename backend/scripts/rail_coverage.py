"""How many rail cards have no photo, as a visitor to the home page sees them, for every demo persona.

Read-only against a running API (uses `log=false`, passes no user to the per-product rails, so nothing is logged).

    uv run python scripts/rail_coverage.py                 # home rails per persona
    uv run python scripts/rail_coverage.py --pages         # + the product-page rails of every home-rail product
    uv run python scripts/rail_coverage.py --json out.json # write the ids without a photo
"""

import argparse
import json
import sys

import httpx

SHOWN = 6  # cards a rail displays


def items(payload) -> list[dict]:
    return payload["items"] if isinstance(payload, dict) else payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000/api/v1")
    ap.add_argument(
        "--pages", action="store_true", help="also walk the product-page rails of the home products"
    )
    ap.add_argument("--json", help="write the ids without a photo to this file")
    a = ap.parse_args()
    http = httpx.Client(base_url=a.api, timeout=60)

    seen: dict[int, dict] = {}
    missing_by_rail: dict[str, int] = {}

    def add(rail: str, prods: list[dict]) -> None:
        for p in prods[:SHOWN]:
            seen.setdefault(p["id"], p)
            if not p.get("image_url"):
                missing_by_rail[rail] = missing_by_rail.get(rail, 0) + 1

    personas = http.get("/users/demo").json()
    for u in personas:
        r = http.get(
            "/recommendations/for-you",
            params={"user_id": u["id"], "session_id": "coverage", "k": 12, "log": "false"},
        )
        add(f"for_you:{u['persona']}", items(r.json()))
    add("trending", items(http.get("/recommendations/trending").json()))
    add("new_arrivals", items(http.get("/recommendations/new-arrivals").json()))
    home = dict(seen)

    if a.pages:
        for pid in list(home):
            for rail in ("similar", "goes-with", "bought-together"):
                add(f"{rail}", items(http.get(f"/recommendations/{rail}/{pid}").json()))

    missing = sorted(i for i, p in seen.items() if not p.get("image_url"))
    print(f"{'rail':<32}{'cards without photo':>20}")
    for rail, n in sorted(missing_by_rail.items()):
        print(f"{rail:<32}{n:>20}")
    print(
        f"\nhome rails: {len(home)} distinct products, {sum(1 for p in home.values() if not p.get('image_url'))} without a photo"
    )
    if a.pages:
        print(f"with product-page rails: {len(seen)} distinct products, {len(missing)} without a photo")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(missing, f)
        print(f"wrote {len(missing)} ids to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
