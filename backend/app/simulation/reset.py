"""Remove simulated behavioral data so a simulation phase can be re-run from scratch."""

from datetime import datetime

from app.core.db import asyncpg_connect


async def reset_simulation(include_experiments: bool = True) -> None:
    """Wipe everything simulated (warm-up + experiment phases)."""
    conn = await asyncpg_connect()
    try:
        async with conn.transaction():
            await conn.execute(
                "TRUNCATE events, sessions, order_items, orders, experiment_assignments, item_similarity RESTART IDENTITY"
            )
            await conn.execute("DELETE FROM users WHERE is_simulated")
            if include_experiments:
                await conn.execute("DELETE FROM experiments WHERE (config->>'simulated')::boolean IS TRUE")
            await conn.execute(
                "UPDATE product_stats SET impressions_7d = 0, clicks_7d = 0, impressions_30d = 0, clicks_30d = 0, "
                "carts_30d = 0, purchases_30d = 0, revenue_30d = 0, ctr_30d = 0, cart_rate_30d = 0, conversion_30d = 0, popularity = 0"
            )
    finally:
        await conn.close()


async def reset_experiment_phase(cutoff: datetime, rebuild_similarity: bool = False) -> None:
    """Drop everything simulated from `cutoff` on (events, orders, sessions, assignments and the experiments that
    start then) so that phase can be re-run. Earlier phases, their experiments and their assignments are kept, so a
    later phase (the bandit test) never erases the ranking, A/A and exploration tests that precede it."""
    conn = await asyncpg_connect()
    try:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE ts >= $1 AND user_id LIKE 'sim_%')",
                cutoff,
            )
            await conn.execute("DELETE FROM orders WHERE ts >= $1 AND user_id LIKE 'sim_%'", cutoff)
            await conn.execute("DELETE FROM events WHERE ts >= $1 AND user_id LIKE 'sim_%'", cutoff)
            await conn.execute("DELETE FROM sessions WHERE started_at >= $1 AND user_id LIKE 'sim_%'", cutoff)
            await conn.execute("DELETE FROM experiment_assignments WHERE assigned_at >= $1", cutoff)
            await conn.execute(
                "DELETE FROM experiments WHERE (config->>'simulated')::boolean IS TRUE AND start_at >= $1",
                cutoff,
            )
            if rebuild_similarity:  # item-item similarity is rebuilt from scratch after the experiment phase
                await conn.execute("TRUNCATE item_similarity RESTART IDENTITY")
    finally:
        await conn.close()
