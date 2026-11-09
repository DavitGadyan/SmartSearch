"""LLM attribute enrichment: fill missing style / material / color for products whose WANDS features lack them."""

import argparse
import asyncio
import json
import sys

import anthropic
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db import asyncpg_connect

STYLES = [
    "modern",
    "mid-century",
    "traditional",
    "farmhouse",
    "rustic",
    "coastal",
    "glam",
    "industrial",
    "boho",
    "eclectic",
]


class Enriched(BaseModel):
    product_id: int
    style: str | None = Field(description=f"one of {STYLES} or null if not inferable")
    material: str | None = Field(description="primary material in lowercase, or null")
    color: str | None = Field(description="dominant color in lowercase, or null")


class Batch(BaseModel):
    items: list[Enriched]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--batch", type=int, default=10)
    a = ap.parse_args()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY not set - skipping enrichment")
        return 0
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    conn = await asyncpg_connect()
    try:
        rows = await conn.fetch(
            """
            SELECT id, name, product_class, left(coalesce(description, ''), 400) AS description, left(coalesce(features_text, ''), 400) AS features
            FROM products p JOIN product_stats s ON s.product_id = p.id
            WHERE NOT (attributes ? 'style') OR NOT (attributes ? 'material') OR NOT (attributes ? 'color')
            ORDER BY s.impressions_30d DESC, id LIMIT $1
            """,
            a.limit,
        )
        print(f"enriching {len(rows)} products with {settings.bulk_model} ...")
        done = 0
        for i in range(0, len(rows), a.batch):
            chunk = rows[i : i + a.batch]
            prompt = (
                "Infer missing attributes for these furniture/home products. Use only the text given; return null when unsure.\n\n"
                + "\n".join(
                    f"- product_id {r['id']}: {r['name']} | class: {r['product_class']} | features: {r['features']} | description: {r['description']}"
                    for r in chunk
                )
            )
            resp = await client.messages.parse(
                model=settings.bulk_model,
                max_tokens=4096,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
                output_format=Batch,
            )
            for e in resp.parsed_output.items:
                patch = {
                    k: v for k, v in {"style": e.style, "material": e.material, "color": e.color}.items() if v
                }
                if not patch:
                    continue
                await conn.execute(
                    "UPDATE products SET attributes = jsonb_build_object('_enriched', true) || $2::jsonb || attributes WHERE id = $1",
                    e.product_id,
                    json.dumps(patch),
                )
                done += 1
            print(f"  {min(i + a.batch, len(rows))}/{len(rows)}", flush=True)
        print(
            f"enriched {done} products (catalog values always win over LLM values; restart the API to reload)"
        )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
