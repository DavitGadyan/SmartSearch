"""Process-wide ML runtime: catalog snapshot, embedder, class index and champion ranker, loaded once at startup."""

from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.bandit.policy import LinTS
from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.logging import get_logger
from app.decision.client import backend_name
from app.graph.kg import load_graph
from app.ml.catalog_cache import CatalogCache, load_catalog
from app.ml.query import ClassIndex, ParsedQuery, parse_query
from app.ml.ranking.ltr import Ranker
from app.ml.retrieval.embedder import Embedder, get_embedder
from app.models import RankingModel

log = get_logger("runtime")


class Runtime:
    def __init__(self) -> None:
        self.catalog: CatalogCache | None = None
        self.embedder: Embedder | None = None
        self.classes: ClassIndex | None = None
        self.ranker: Ranker | None = None
        self.model_version: str = "none"
        self.suggest_terms: list[tuple[str, str]] = []  # (lowercased text, kind)
        self.bandit: LinTS | None = None
        self.graph = None
        self.rng = np.random.default_rng()

    @property
    def ready(self) -> bool:
        return self.catalog is not None and self.embedder is not None

    async def load(self) -> None:
        self.embedder = get_embedder()
        try:
            self.catalog = await load_catalog(engine)
        except Exception as e:  # empty DB / before migrations
            log.warning("catalog not loaded (%s) - run `make data`", e)
            return
        self.classes = ClassIndex(self.catalog.class_names, self.embedder)
        await self.load_champion()
        self._build_suggest_terms()
        bp = settings.artifacts_dir / "bandit_policy.json"
        self.bandit = LinTS.load(bp) if bp.exists() else None
        gp = settings.artifacts_dir / "graph.pkl"
        self.graph = load_graph(gp) if gp.exists() else None
        log.info("runtime ready: %d products, ranker=%s", self.catalog.n, self.model_version)

    async def load_champion(self) -> None:
        async with SessionLocal() as db:
            champ = await db.scalar(select(RankingModel).where(RankingModel.is_champion.is_(True)))
        if champ and champ.artifact_path and Path(champ.artifact_path).exists():
            self.ranker = Ranker.load(Path(champ.artifact_path), champ.version)
            self.model_version = champ.version
        else:
            self.ranker, self.model_version = None, "none"
            log.warning("no champion ranker - LTR strategies fall back to RRF order until `make train`")

    async def refresh_stats(self) -> None:
        """Reload product_stats after marts refresh (behavioral features change)."""
        if self.catalog is None:
            return
        fresh = await load_catalog(engine)
        self.catalog.stats = fresh.stats
        self.catalog.refresh_stat_arrays()

    def _build_suggest_terms(self) -> None:
        seen: set[str] = set()
        terms: list[tuple[str, str]] = []
        for c in self.catalog.class_names:
            if c.lower() not in seen:
                terms.append((c.lower(), "category"))
                seen.add(c.lower())
        for nm in self.catalog.df["name"]:
            s = str(nm).strip().lower()
            if 3 <= len(s) <= 60 and s not in seen:
                terms.append((s, "product"))
                seen.add(s)
        self.suggest_terms = sorted(terms)

    def parse(self, q: str) -> tuple[ParsedQuery, np.ndarray]:
        pq = parse_query(q)
        qvec = self.embedder.encode_one(pq.text)
        return self.classes.annotate(pq, qvec), qvec

    def status(self) -> dict:
        return {
            "ready": self.ready,
            "products": self.catalog.n if self.catalog else 0,
            "embedding_model": settings.embedding_model,
            "ranker": self.model_version,
            "bandit_policy": self.bandit is not None,
            "knowledge_graph": None
            if self.graph is None
            else {
                "nodes": self.graph.g.number_of_nodes(),
                "edges": self.graph.g.number_of_edges(),
                "communities": len(self.graph.communities),
            },
            "decision_backend": backend_name(),
        }


runtime = Runtime()
