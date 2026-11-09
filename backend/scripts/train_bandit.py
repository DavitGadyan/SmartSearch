"""Train the contextual-bandit policy off-policy from the logged experiments and evaluate candidate policies (IPS / SNIPS / DR).

Logged tuple per search: context (intent group, price cap, query length, shopper history, segment, device),
action (ranking strategy [+explore]), logging propensity (A/B weights), reward (purchase in the same session within 1h).
"""

import asyncio
import json
import sys
import time
from datetime import timedelta

import numpy as np
import pandas as pd

from app.bandit.context import ACTIONS, build_context
from app.bandit.ope import estimate, fit_reward_models
from app.bandit.policy import EpsilonGreedy, FixedPolicy, LinTS
from app.core.config import settings
from app.core.db import asyncpg_connect, engine
from app.ml.catalog_cache import load_catalog
from app.ml.query import parse_query
from app.simulation.simulator import simulation_start

EXPERIMENT_PROPENSITY = {"ranking_hybrid_ltr_v1": 0.5, "exploration_slot": 0.5, "bandit_policy_v1": None}


async def load_logs(day_from: int = 7, day_to: int = 27) -> pd.DataFrame:
    start = simulation_start()
    lo, hi = start + timedelta(days=day_from), start + timedelta(days=day_to + 1)
    conn = await asyncpg_connect()
    try:
        searches = pd.DataFrame(
            [
                dict(r)
                for r in await conn.fetch(
                    "SELECT e.id, e.ts, e.user_id, e.session_id, e.query, e.experiment_key, e.variant, e.strategy, "
                    "e.metadata::text AS meta, u.segment, s.device FROM events e "
                    "JOIN users u ON u.id = e.user_id LEFT JOIN sessions s ON s.id = e.session_id "
                    "WHERE e.event_type = 'search' AND e.user_id LIKE 'sim_%' AND e.ts >= $1 AND e.ts < $2 ORDER BY e.ts",
                    lo,
                    hi,
                )
            ]
        )
        outcomes = pd.DataFrame(
            [
                dict(r)
                for r in await conn.fetch(
                    "SELECT session_id, ts, event_type FROM events WHERE event_type IN ('purchase','click') AND user_id LIKE 'sim_%' AND ts >= $1 AND ts < $2::timestamptz + interval '1 hour'",
                    lo,
                    hi,
                )
            ]
        )
        hist = pd.DataFrame(
            [
                dict(r)
                for r in await conn.fetch(
                    "SELECT user_id, ts FROM events WHERE event_type IN ('click','add_to_cart','purchase') AND user_id LIKE 'sim_%' AND ts < $1 ORDER BY ts",
                    hi,
                )
            ]
        )
    finally:
        await conn.close()
    buys = outcomes[outcomes.event_type == "purchase"]

    def reward(row) -> float:
        b = buys[buys.session_id == row.session_id]
        return float(((b.ts >= row.ts) & (b.ts < row.ts + pd.Timedelta(hours=1))).any())

    buy_sessions = set(buys.session_id)
    searches["reward"] = [reward(r) if r.session_id in buy_sessions else 0.0 for r in searches.itertuples()]
    hist = hist.sort_values("ts")
    hist["n"] = hist.groupby("user_id").cumcount()
    searches = pd.merge_asof(
        searches.sort_values("ts"),
        hist.rename(columns={"ts": "hts"}).sort_values("hts"),
        left_on="ts",
        right_on="hts",
        by="user_id",
        direction="backward",
    )
    searches["history"] = searches["n"].fillna(-1).astype(int) + 1
    meta = searches["meta"].map(lambda m: json.loads(m) if m else {})
    searches["top_class"] = meta.map(lambda m: (m.get("parsed") or {}).get("top_class"))
    searches["bandit"] = meta.map(lambda m: m.get("bandit"))
    explore = (searches.experiment_key == "exploration_slot") & (searches.variant == "on")
    searches["action"] = np.where(explore, searches.strategy + "+explore", searches.strategy)
    searches["propensity"] = [
        b["propensity"] if isinstance(b, dict) else EXPERIMENT_PROPENSITY.get(k, 1.0) or 1.0
        for b, k in zip(searches.bandit, searches.experiment_key, strict=True)
    ]
    return searches[searches.action.isin(ACTIONS)].reset_index(drop=True)


async def main() -> None:
    t0 = time.perf_counter()
    cache = await load_catalog(engine)
    logs = await load_logs()
    print(
        f"{len(logs):,} logged searches · reward rate {logs.reward.mean():.4f} · actions {logs.action.value_counts().to_dict()}"
    )
    parsed = {q: parse_query(q) for q in logs["query"].unique()}
    X = np.vstack(
        [
            build_context(
                cache.class_group.get(r.top_class or "", "other"),
                parsed[r.query].price_max is not None,
                len(parsed[r.query].tokens),
                int(r.history),
                r.segment,
                r.device,
            )
            for r in logs.itertuples()
        ]
    )
    a_idx = np.array([ACTIONS.index(a) for a in logs.action])
    p_log = logs.propensity.to_numpy(float)
    r = logs.reward.to_numpy(float)

    rng = np.random.default_rng(0)
    order = rng.permutation(len(logs))
    policy = LinTS(seed=0)
    for i in order:
        policy.update(ACTIONS[a_idx[i]], X[i], r[i])

    # OPE: fit reward models on a held-out half to keep DR honest, evaluate on the other half
    half = len(logs) // 2
    models = fit_reward_models(X[order[:half]], a_idx[order[:half]], r[order[:half]], len(ACTIONS))
    ev_idx = order[half:]
    greedy = type("Greedy", (), {"action_probs": lambda self, x: policy.greedy_probs(x)})()
    candidates = {
        "logging (A/B weights)": None,
        "fixed: " + ACTIONS[3]: FixedPolicy(ACTIONS[3]),
        "fixed: " + ACTIONS[0]: FixedPolicy(ACTIONS[0]),
        "LinTS greedy": greedy,
        "LinTS eps-greedy 0.1": EpsilonGreedy(policy, 0.1),
    }
    results = {}
    for name, pol in candidates.items():
        if pol is None:
            results[name] = {"value": float(r[ev_idx].mean()), "n": int(len(ev_idx))}
            continue
        results[name] = estimate(
            pol, X[ev_idx], a_idx[ev_idx], p_log[ev_idx], r[ev_idx], ACTIONS, reward_models=models
        )
        print(
            f"  {name:28s} ips={results[name]['ips']:.4f} snips={results[name]['snips']:.4f} dr={results[name]['dr']:.4f} ess={results[name]['ess']:.0f}"
        )
    out = {
        "reward": "purchase in the same session within 1 hour of the search",
        "n_logs": int(len(logs)),
        "logging_value": float(r.mean()),
        "actions": ACTIONS,
        "action_counts": logs.action.value_counts().to_dict(),
        "policies": results,
        "context_dim": int(X.shape[1]),
        "trained_at_days": [7, 27],
    }
    (settings.artifacts_dir / "bandit_eval.json").write_text(json.dumps(out, indent=1, default=float))
    policy.save(settings.artifacts_dir / "bandit_policy.json")
    policy.save(settings.artifacts_dir / "bandit_policy_offline.json")
    print(f"saved policy + OPE report ({time.perf_counter() - t0:.0f}s)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
