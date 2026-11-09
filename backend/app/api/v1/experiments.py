import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.cache import ANALYTICS
from app.core.db import get_db
from app.experiments import power as pw
from app.experiments.analysis import analyze
from app.experiments.assignment import assign_variant
from app.models import Experiment, ExperimentAssignment
from app.schemas.experiments import (
    DraftIn,
    ExperimentCreate,
    ExperimentOut,
    ExposeIn,
    SimulateIn,
    StatusUpdate,
)
from app.services import experiment_draft_service, experiment_service
from app.simulation.ui_traffic import simulate_ui_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])


async def _out(db: AsyncSession, e: Experiment) -> ExperimentOut:
    n = await db.scalar(
        select(func.count())
        .select_from(ExperimentAssignment)
        .where(ExperimentAssignment.experiment_key == e.key)
    )
    return ExperimentOut(
        **{
            c.name: getattr(e, c.name)
            for c in Experiment.__table__.columns
            if c.name != "salt" and c.name != "id"
        },
        assigned_users=n or 0,
    )


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(Experiment).order_by(Experiment.start_at.desc().nullslast(), Experiment.id.desc())
        )
    ).all()
    return [await _out(db, e) for e in rows]


@router.get("/tools/power", summary="Sample size / MDE / duration calculator")
async def power_calculator(
    baseline_rate: float = Query(0.03, gt=0, lt=1),
    mde_rel: float = Query(0.05, gt=0, lt=5),
    alpha: float = Query(0.05, gt=0, lt=0.5),
    power: float = Query(0.8, gt=0.5, lt=1),
    daily_users: float = Query(1000, gt=0),
    n_variants: int = Query(2, ge=2, le=10),
    allocation: float = Query(1.0, gt=0, le=1),
):
    n = pw.sample_size_proportion(baseline_rate, mde_rel, alpha, power)
    return {
        "required_n_per_arm": n,
        "total_users": n * n_variants,
        "duration_days": round(pw.duration_days(n, daily_users, allocation, n_variants), 1),
        "mde_curve": [
            {"n_per_arm": k, "mde_rel": round(pw.mde_proportion(baseline_rate, k, alpha, power), 4)}
            for k in (1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000)
        ],
    }


@router.get("/{key}", response_model=ExperimentOut)
async def get_experiment(key: str, db: AsyncSession = Depends(get_db)):
    e = await db.scalar(select(Experiment).where(Experiment.key == key))
    if e is None:
        raise HTTPException(404, "experiment not found")
    return await _out(db, e)


@router.get("/{key}/analysis", dependencies=[Depends(require_admin)])
async def experiment_analysis(key: str, db: AsyncSession = Depends(get_db)):
    if (hit := ANALYTICS.get(("analysis", key))) is not None:
        return hit
    try:
        result = await analyze(db, key)
        ANALYTICS.set(("analysis", key), result)
        return result
    except KeyError:
        raise HTTPException(404, "experiment not found") from None
    except Exception as e:  # mart missing → tell the operator what to run
        if "mart_experiment_user" in str(e):
            raise HTTPException(503, "analytics marts not built - run `make marts`") from None
        raise


@router.get("/{key}/assignment")
async def assignment(key: str, user_id: str, db: AsyncSession = Depends(get_db)):
    e = await db.scalar(select(Experiment).where(Experiment.key == key))
    if e is None:
        raise HTTPException(404, "experiment not found")
    return {
        "experiment_key": key,
        "user_id": user_id,
        "variant": assign_variant(e.salt, user_id, e.variants, e.traffic_allocation),
    }


@router.post("", response_model=ExperimentOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_experiment(body: ExperimentCreate, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(Experiment).where(Experiment.key == body.key)):
        raise HTTPException(409, "experiment key already exists")
    e = Experiment(
        **body.model_dump(exclude={"variants"}),
        variants=[v.model_dump() for v in body.variants],
        salt=secrets.token_hex(8),
        status="draft",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    experiment_service.invalidate_cache()
    return await _out(db, e)


@router.patch("/{key}/status", response_model=ExperimentOut, dependencies=[Depends(require_admin)])
async def set_status(key: str, body: StatusUpdate, db: AsyncSession = Depends(get_db)):
    try:
        e = await experiment_service.set_status(db, key, body.status)
    except LookupError:
        raise HTTPException(404, "experiment not found") from None
    except RuntimeError as ex:
        raise HTTPException(409, str(ex)) from None
    return await _out(db, e)


@router.post(
    "/expose", summary="Assign a shopper to the running UI experiment and return that arm's storefront config"
)
async def expose(body: ExposeIn, db: AsyncSession = Depends(get_db)):
    return await experiment_service.expose_ui(db, body.user_id, body.surface)


@router.post("/{key}/simulate", status_code=202, dependencies=[Depends(require_admin)])
async def simulate(key: str, body: SimulateIn, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Send simulated shoppers through a UI experiment (runs in the background; poll GET /{key})."""
    e = await db.scalar(select(Experiment).where(Experiment.key == key))
    if e is None:
        raise HTTPException(404, "experiment not found")
    if e.surface != "ui":
        raise HTTPException(400, "simulated traffic is only for UI experiments")
    if (e.config or {}).get("simulated_traffic", {}).get("status") == "running":
        raise HTTPException(409, "a simulation is already running for this experiment")
    tasks.add_task(simulate_ui_experiment, key, body.users, body.days, body.seed)
    return {"scheduled": True, "key": key, "users": body.users, "days": body.days}


@router.post("/draft", dependencies=[Depends(require_admin)])
async def draft(body: DraftIn, db: AsyncSession = Depends(get_db)):
    """The console assistant: describe a storefront change, get a drafted test, a sample-size plan and, after a yes,
    a launched test with simulated traffic and a hypothesis-test verdict."""
    return await experiment_draft_service.draft(db, body.messages, body.proposal, body.experiment_key)
