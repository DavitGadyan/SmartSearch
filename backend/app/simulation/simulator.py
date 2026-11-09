"""Behavioral simulator: shoppers with latent personas search, click, add to cart and buy through the *same* ranking code the API serves, under the experiment assignments the API would make. Produces the event log, users/sessions/orders and experiment assignments; everything is seeded and reproducible."""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from app.bandit.context import action_to_strategy, build_context
from app.bandit.policy import LinTS
from app.core.db import asyncpg_connect
from app.experiments.assignment import assign_variant
from app.ml.catalog_cache import CatalogCache
from app.ml.personalization.profile import profile_from_interactions
from app.ml.query import ClassIndex, parse_query
from app.ml.ranking.ltr import Ranker
from app.ml.ranking.strategies import PERSONALIZATION_WEIGHT, RankedResult, UserProfile, affinity_boost, rank
from app.ml.recs.cold_start import apply_exploration_slot
from app.ml.retrieval.embedder import Embedder
from app.simulation.click_model import relevance_grades, simulate_interactions
from app.simulation.personas import SimUser

EVENT_COLS = [
    "ts",
    "user_id",
    "session_id",
    "event_type",
    "query",
    "query_id",
    "product_id",
    "position",
    "result_count",
    "experiment_key",
    "variant",
    "ranking_model_version",
    "strategy",
    "revenue",
    "quantity",
    "latency_ms",
    "source",
    "metadata",
]
HOUR_WEIGHTS = np.array(
    [1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 9, 10, 10, 10, 10, 10, 11, 12, 13, 13, 12, 9, 5, 3], float
)


@dataclass
class ExperimentSpec:
    key: str
    name: str
    hypothesis: str
    day_from: int  # inclusive, 0-based simulation day
    day_to: int  # inclusive
    variants: list[dict]  # {key, name, strategy?, explore?, weight}
    primary_metric: str = "conversion_rate"
    salt: str = ""
    decides_strategy: bool = True
    status_after: str = "completed"
    surface: str = "search"
    secondary_metrics: list[str] = field(
        default_factory=lambda: ["search_ctr", "add_to_cart_rate", "revenue_per_visitor", "aov"]
    )
    guardrail_metrics: list[str] = field(default_factory=lambda: ["zero_result_rate", "no_click_rate"])
    summary: str = ""  # one plain-language line: what changed for shoppers

    def active(self, day: int) -> bool:
        return self.day_from <= day <= self.day_to


@dataclass
class SimPlan:
    day_from: int
    day_to: int
    base_strategy_by_day: dict[int, str]  # default strategy when no strategy-deciding experiment is active
    experiments: list[ExperimentSpec]
    query_splits: tuple[str, ...] = ("train", "val", "test")
    page_size: int = 20


class Simulator:
    def __init__(
        self,
        cache: CatalogCache,
        classes: ClassIndex,
        embedder: Embedder,
        ranker: Ranker | None,
        queries: list[dict],
        labels: dict[int, dict[int, int]],
        start: datetime,
        seed: int = 7,
    ) -> None:
        self.cache, self.classes, self.embedder, self.ranker = cache, classes, embedder, ranker
        self.queries = queries
        self.labels = labels
        self.start = start
        self.rng = np.random.default_rng(seed)
        self.model_version = ranker.version if ranker else "none"
        self.bandit: LinTS | None = None  # set for the bandit phase; learns online from purchases
        self._parsed: dict[int, tuple] = {}
        self._base: dict[tuple[int, str], RankedResult] = {}
        self.history: dict[
            str, list[tuple[str, int]]
        ] = {}  # user_id -> [(event_type, product_id)] newest first
        self._profiles: dict[str, UserProfile] = {}
        self._dirty: set[str] = set()
        self.events: list[tuple] = []
        self.sessions: list[tuple] = []
        self.orders: list[tuple] = []
        self.order_items: list[tuple] = []
        self.assignments: dict[tuple[str, str], tuple[str, datetime]] = {}
        self.counters = {
            "searches": 0,
            "impressions": 0,
            "clicks": 0,
            "carts": 0,
            "purchases": 0,
            "zero_results": 0,
            "revenue": 0.0,
        }

    # ------------------------------------------------------------------ ranking (cached base + per-user terms)
    def _parse(self, q: dict):
        if q["id"] not in self._parsed:
            pq = parse_query(q["text"])
            qvec = self.embedder.encode_one(pq.text)
            self.classes.annotate(pq, qvec)
            self._parsed[q["id"]] = (pq, qvec)
        return self._parsed[q["id"]]

    def _base_ranking(self, q: dict, strategy: str) -> RankedResult:
        key = (q["id"], strategy)
        if key not in self._base:
            pq, qvec = self._parse(q)
            self._base[key] = rank(strategy, pq, qvec, self.cache, self.classes, self.ranker, None, 200)
        return self._base[key]

    def _profile(self, user_id: str) -> UserProfile:
        if user_id in self._dirty or user_id not in self._profiles:
            self._profiles[user_id] = profile_from_interactions(
                self.history.get(user_id, [])[:300], self.cache
            )
            self._dirty.discard(user_id)
        return self._profiles[user_id]

    def rank_for(self, q: dict, strategy: str, user: SimUser, explore: bool) -> tuple[np.ndarray, int | None]:
        base = self._base_ranking(q, strategy)
        pos, scores = base.positions, base.scores
        if strategy == "hybrid_ltr_personalized" and len(pos):
            prof = self._profile(user.id)
            if not prof.is_empty():
                scores = scores + PERSONALIZATION_WEIGHT * affinity_boost(prof, pos, self.cache)
                order = np.argsort(-scores, kind="stable")
                pos, scores = pos[order], scores[order]
        explored = None
        if explore and len(pos):
            pos, scores, explored = apply_exploration_slot(pos, scores, self.cache, self.rng)
        return pos, explored

    # ------------------------------------------------------------------ one search
    def _resolve(
        self, plan: SimPlan, day: int, user: SimUser, ts: datetime
    ) -> tuple[str, bool, str | None, str | None, dict[str, float]]:
        strategy, explore, exp_key, variant = plan.base_strategy_by_day[day], False, None, None
        effects: dict[str, float] = {}
        for spec in plan.experiments:
            if not spec.active(day):
                continue
            v = assign_variant(spec.salt, user.id, spec.variants, 1.0)
            if v is None:
                continue
            if (spec.key, user.id) not in self.assignments:
                self.assignments[(spec.key, user.id)] = (v, ts)
            vcfg = next(x for x in spec.variants if x["key"] == v)
            if spec.decides_strategy:
                strategy = vcfg.get("strategy", strategy)
                explore = bool(vcfg.get("explore", explore))
                exp_key, variant = spec.key, v
            for k, lift in (vcfg.get("effect") or {}).items():  # UI arms: assumed lifts, simulation only
                effects[k] = (1 + effects.get(k, 0.0)) * (1 + float(lift)) - 1
            if not spec.decides_strategy and exp_key is None:
                exp_key, variant = spec.key, v  # tag events with the UI test when no ranking test is active
        return strategy, explore, exp_key, variant, effects

    def _context(self, q: dict, user: SimUser, device: str) -> np.ndarray:
        pq, _ = self._parse(q)
        group = self.cache.class_group.get(pq.top_class or "", "other")
        return build_context(
            group,
            pq.price_max is not None,
            len(pq.tokens),
            len(self.history.get(user.id, [])),
            user.segment,
            device,
        )

    def search(
        self,
        plan: SimPlan,
        day: int,
        user: SimUser,
        session_id: str,
        ts: datetime,
        q: dict,
        device: str = "desktop",
    ) -> bool:
        """Simulate one search; returns True if the session should continue."""
        strategy, explore, exp_key, variant, effects = self._resolve(plan, day, user, ts)
        bandit_meta, x = None, None
        if strategy == "bandit":
            if self.bandit is None:
                raise RuntimeError("bandit strategy requires a loaded policy")
            x = self._context(q, user, device)
            action, prop = self.bandit.select(x)
            strategy, explore = action_to_strategy(action)
            bandit_meta = {"action": action, "propensity": round(float(prop), 4)}
        pos, explored = self.rank_for(q, strategy, user, explore)
        shown = pos[: plan.page_size]
        common = (user.id, session_id)
        self.counters["searches"] += 1
        self.events.append(
            (
                ts,
                *common,
                "search",
                q["text"],
                q["id"],
                None,
                None,
                int(len(pos)),
                exp_key,
                variant,
                self.model_version,
                strategy,
                None,
                None,
                Decimal("3.0"),
                "search",
                json.dumps(
                    {
                        "page": 1,
                        "simulated": True,
                        "parsed": {"top_class": self._parse(q)[0].top_class},
                        "bandit": bandit_meta,
                    }
                ),
            )
        )
        if len(shown) == 0:
            self.counters["zero_results"] += 1
            return True
        grades = relevance_grades(shown, self.cache, self.labels.get(q["id"], {}), q.get("query_class"))
        clicked, carted, purchased = simulate_interactions(user, shown, grades, self.cache, self.rng, effects)
        t = ts
        for i, p in enumerate(shown):
            pid = int(self.cache.ids[p])
            self.events.append(
                (
                    ts,
                    *common,
                    "impression",
                    q["text"],
                    q["id"],
                    pid,
                    i + 1,
                    None,
                    exp_key,
                    variant,
                    self.model_version,
                    strategy,
                    None,
                    None,
                    None,
                    "search",
                    json.dumps({"explored": explored is not None and int(p) == explored})
                    if explored is not None
                    else None,
                )
            )
        self.counters["impressions"] += len(shown)
        bought_any = False
        for i in np.flatnonzero(clicked):
            p = shown[i]
            pid = int(self.cache.ids[p])
            t += timedelta(seconds=int(self.rng.integers(5, 60)))
            self.events.append(
                (
                    t,
                    *common,
                    "click",
                    q["text"],
                    q["id"],
                    pid,
                    int(i + 1),
                    None,
                    exp_key,
                    variant,
                    self.model_version,
                    strategy,
                    None,
                    None,
                    None,
                    "search",
                    None,
                )
            )
            self.events.append(
                (
                    t + timedelta(seconds=1),
                    *common,
                    "product_view",
                    q["text"],
                    q["id"],
                    pid,
                    int(i + 1),
                    None,
                    exp_key,
                    variant,
                    self.model_version,
                    strategy,
                    None,
                    None,
                    None,
                    "search",
                    None,
                )
            )
            self.history.setdefault(user.id, []).insert(0, ("click", pid))
            self.counters["clicks"] += 1
            if carted[i]:
                t += timedelta(seconds=int(self.rng.integers(10, 120)))
                self.events.append(
                    (
                        t,
                        *common,
                        "add_to_cart",
                        q["text"],
                        q["id"],
                        pid,
                        int(i + 1),
                        None,
                        exp_key,
                        variant,
                        self.model_version,
                        strategy,
                        None,
                        1,
                        None,
                        "search",
                        None,
                    )
                )
                self.history[user.id].insert(0, ("add_to_cart", pid))
                self.counters["carts"] += 1
            if purchased[i]:
                t += timedelta(seconds=int(self.rng.integers(60, 600)))
                qty = 2 if self.rng.random() < 0.1 else 1
                price = float(self.cache.price[p])
                rev = round(price * qty, 2)
                order_id = f"ord_{uuid.uuid4().hex[:12]}"
                self.events.append(
                    (
                        t,
                        *common,
                        "purchase",
                        q["text"],
                        q["id"],
                        pid,
                        int(i + 1),
                        None,
                        exp_key,
                        variant,
                        self.model_version,
                        strategy,
                        Decimal(f"{rev:.2f}"),
                        qty,
                        None,
                        "search",
                        json.dumps({"order_id": order_id}),
                    )
                )
                self.orders.append(
                    (order_id, user.id, session_id, t, Decimal(f"{rev:.2f}"), exp_key, variant)
                )
                self.order_items.append((order_id, pid, qty, Decimal(f"{price:.2f}")))
                self.history[user.id].insert(0, ("purchase", pid))
                self.counters["purchases"] += 1
                self.counters["revenue"] += rev
                bought_any = True
            self._dirty.add(user.id)
        if bandit_meta is not None:
            self.bandit.update(bandit_meta["action"], x, 1.0 if bought_any else 0.0)
        return not (bought_any and self.rng.random() < 0.8)

    # ------------------------------------------------------------------ whole run
    def run(
        self, plan: SimPlan, users: list[SimUser], days_scale: float = 1.0, log_every: int = 2000
    ) -> dict:
        t0 = time.perf_counter()
        pool = [q for q in self.queries if q["split"] in plan.query_splits]
        qw = np.array([q["popularity_weight"] for q in pool])
        qw /= qw.sum()
        n_days = plan.day_to - plan.day_from + 1
        for ui, user in enumerate(users):
            n_sessions = self.rng.poisson(user.sessions_lambda * n_days / 28 * days_scale)
            for _ in range(n_sessions):
                day = int(self.rng.integers(plan.day_from, plan.day_to + 1))
                hour = int(self.rng.choice(24, p=HOUR_WEIGHTS / HOUR_WEIGHTS.sum()))
                ts = self.start + timedelta(
                    days=day,
                    hours=hour,
                    minutes=int(self.rng.integers(0, 60)),
                    seconds=int(self.rng.integers(0, 60)),
                )
                session_id = f"s_{uuid.uuid4().hex[:12]}"
                device = str(self.rng.choice(["desktop", "mobile", "tablet"], p=[0.5, 0.42, 0.08]))
                self.sessions.append((session_id, user.id, ts, device))
                n_q = 1 + int(self.rng.geometric(0.55) - 1)
                for k in range(min(n_q, 4)):
                    q = pool[int(self.rng.choice(len(pool), p=qw))]
                    if not self.search(plan, day, user, session_id, ts + timedelta(minutes=3 * k), q, device):
                        break
            if log_every and (ui + 1) % log_every == 0:
                print(
                    f"  users {ui + 1:,}/{len(users):,}  searches={self.counters['searches']:,} clicks={self.counters['clicks']:,} "
                    f"purchases={self.counters['purchases']:,}  ({time.perf_counter() - t0:.0f}s)",
                    flush=True,
                )
        self.counters["elapsed_s"] = round(time.perf_counter() - t0, 1)
        return dict(self.counters)

    # ------------------------------------------------------------------ persistence
    async def persist(self, users: list[SimUser], plan: SimPlan) -> None:
        conn = await asyncpg_connect()
        try:
            async with conn.transaction():
                await conn.execute(
                    "CREATE TEMP TABLE tmp_users (LIKE users INCLUDING DEFAULTS) ON COMMIT DROP"
                )
                await conn.copy_records_to_table(
                    "tmp_users",
                    columns=["id", "persona", "segment", "traits", "is_simulated", "created_at"],
                    records=[
                        (u.id, u.persona, u.segment, json.dumps(u.traits), True, self.start) for u in users
                    ],
                )
                await conn.execute("INSERT INTO users SELECT * FROM tmp_users ON CONFLICT (id) DO NOTHING")
                await conn.copy_records_to_table(
                    "sessions", columns=["id", "user_id", "started_at", "device"], records=self.sessions
                )
                for i in range(0, len(self.events), 200_000):
                    await conn.copy_records_to_table(
                        "events", columns=EVENT_COLS, records=self.events[i : i + 200_000]
                    )
                await conn.copy_records_to_table(
                    "orders",
                    columns=["id", "user_id", "session_id", "ts", "total", "experiment_key", "variant"],
                    records=self.orders,
                )
                await conn.copy_records_to_table(
                    "order_items",
                    columns=["order_id", "product_id", "quantity", "unit_price"],
                    records=self.order_items,
                )
                for spec in plan.experiments:
                    await conn.execute(
                        """
                        INSERT INTO experiments (key, name, hypothesis, status, surface, variants, traffic_allocation, salt, primary_metric,
                                                 secondary_metrics, guardrail_metrics, config, start_at, end_at)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, 1.0, $7, $8, $9::jsonb, $10::jsonb, $11::jsonb, $12, $13)
                        ON CONFLICT (key) DO UPDATE SET status = EXCLUDED.status, variants = EXCLUDED.variants, start_at = EXCLUDED.start_at,
                                                        end_at = EXCLUDED.end_at, hypothesis = EXCLUDED.hypothesis, name = EXCLUDED.name,
                                                        config = EXCLUDED.config
                        """,
                        spec.key,
                        spec.name,
                        spec.hypothesis,
                        spec.status_after,
                        spec.surface,
                        json.dumps(spec.variants),
                        spec.salt,
                        spec.primary_metric,
                        json.dumps(spec.secondary_metrics),
                        json.dumps(spec.guardrail_metrics),
                        json.dumps(
                            {
                                "alpha": 0.05,
                                "power": 0.8,
                                "mde_rel": 0.05,
                                "pre_period_days": 7,
                                "simulated": True,
                                "summary": spec.summary,
                            }
                        ),
                        self.start + timedelta(days=spec.day_from),
                        self.start + timedelta(days=spec.day_to + 1),
                    )
                if self.assignments:
                    await conn.execute(
                        "CREATE TEMP TABLE tmp_assign (experiment_key text, user_id text, variant text, assigned_at timestamptz) ON COMMIT DROP"
                    )
                    await conn.copy_records_to_table(
                        "tmp_assign",
                        columns=["experiment_key", "user_id", "variant", "assigned_at"],
                        records=[(k[0], k[1], v[0], v[1]) for k, v in self.assignments.items()],
                    )
                    await conn.execute(
                        "INSERT INTO experiment_assignments (experiment_key, user_id, variant, assigned_at) "
                        "SELECT experiment_key, user_id, variant, assigned_at FROM tmp_assign ON CONFLICT DO NOTHING"
                    )
                await conn.execute(
                    "ANALYZE events; ANALYZE experiment_assignments; ANALYZE users; ANALYZE orders;"
                )
        finally:
            await conn.close()

    async def load_history(self, user_ids: list[str]) -> int:
        """Seed in-memory interaction history from events already in the DB (e.g. the warm-up period)."""
        conn = await asyncpg_connect()
        try:
            rows = await conn.fetch(
                "SELECT user_id, event_type, product_id FROM events WHERE user_id LIKE 'sim_%' AND product_id IS NOT NULL "
                "AND event_type IN ('click','add_to_cart','purchase') ORDER BY ts DESC"
            )
        finally:
            await conn.close()
        for r in rows:
            self.history.setdefault(r["user_id"], []).append((r["event_type"], r["product_id"]))
        return len(rows)


SIM_DAYS = 35  # 0-6 warm-up · 7-20 ranking A/B (+A/A) · 21-27 exploration slot · 28-34 bandit policy A/B


def simulation_start(days: int = SIM_DAYS) -> datetime:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days - 1)
