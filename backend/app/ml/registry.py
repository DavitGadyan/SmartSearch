"""MLflow tracking + the ranking_models registry table the API serves from."""

import httpx
import mlflow
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models import RankingModel

log = get_logger("registry")
EXPERIMENT = "smartsearch-ranking"


def mlflow_setup() -> str:
    """Use the configured tracking server if reachable, else a local file store. Returns the URI in use."""
    uri = settings.mlflow_tracking_uri
    if uri.startswith("http"):
        try:
            httpx.get(f"{uri.rstrip('/')}/health", timeout=2.0).raise_for_status()
        except Exception:
            uri = f"file:{settings.artifacts_dir / 'mlruns'}"
            log.warning("MLflow server unreachable - logging to %s", uri)
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENT)
    return uri


async def next_version(db: AsyncSession, prefix: str = "ltr") -> str:
    n = await db.scalar(select(func.count()).select_from(RankingModel))
    return f"{prefix}_v{(n or 0) + 1}"


async def register(
    db: AsyncSession,
    *,
    version: str,
    algorithm: str,
    run_id: str | None,
    artifact_path: str,
    params: dict,
    metrics: dict,
    feature_importance: dict,
    feature_names: list[str],
    primary_metric: str = "cv_hybrid_ltr_ndcg@10",
) -> RankingModel:
    """Insert the model; promote it if it is at least as good on the primary metric, or if the current champion's
    feature set no longer matches the serving code (it could not be loaded anyway)."""
    champ = await db.scalar(select(RankingModel).where(RankingModel.is_champion.is_(True)))
    incompatible = champ is not None and list(champ.feature_names or []) != list(feature_names)
    better = champ is None or metrics.get(primary_metric, 0) >= (champ.metrics or {}).get(primary_metric, 0)
    promote = champ is None or incompatible or better
    if promote and champ is not None:
        await db.execute(
            update(RankingModel).where(RankingModel.is_champion.is_(True)).values(is_champion=False)
        )
    row = RankingModel(
        version=version,
        algorithm=algorithm,
        mlflow_run_id=run_id,
        artifact_path=artifact_path,
        params=params,
        metrics=metrics,
        feature_importance=feature_importance,
        feature_names=feature_names,
        is_champion=promote,
    )
    db.add(row)
    await db.commit()
    log.info(
        "registered %s (champion=%s%s, %s=%.4f)",
        version,
        promote,
        " [feature set changed]" if incompatible else "",
        primary_metric,
        metrics.get(primary_metric, 0),
    )
    return row
