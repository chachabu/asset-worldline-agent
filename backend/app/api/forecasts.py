from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import AssetForecast, Branch, Job, PredictionRun

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/matrix")
def forecast_matrix(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    forecasts = db.scalars(
        select(AssetForecast)
        .options(
            joinedload(AssetForecast.asset_group),
            joinedload(AssetForecast.branch),
            joinedload(AssetForecast.primary_asset),
        )
        .order_by(AssetForecast.created_at.desc())
        .limit(300)
    ).all()
    return [
        {
            "id": forecast.id,
            "branch": forecast.branch.name,
            "asset_group": forecast.asset_group.name,
            "asset_group_id": forecast.asset_group_id,
            "primary_asset": forecast.primary_asset.symbol if forecast.primary_asset else None,
            "region": forecast.region,
            "horizon": forecast.horizon,
            "direction": forecast.direction,
            "confidence": forecast.confidence,
            "current_price": forecast.current_price,
            "base_target": forecast.base_target,
            "bull_target": forecast.bull_target,
            "bear_target": forecast.bear_target,
            "rationale": forecast.rationale,
        }
        for forecast in forecasts
    ]


@router.post("/runs")
def create_prediction_job(
    branch_name: str,
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    branch = db.scalar(select(Branch).where(Branch.name == branch_name))
    if not branch:
        return {"ok": False, "error": "Unknown branch"}
    run = PredictionRun(branch_id=branch.id, status="queued", run_reason="manual")
    db.add(run)
    db.flush()
    job = Job(job_type="run_prediction", payload={"prediction_run_id": run.id, "branch_id": branch.id})
    db.add(job)
    db.commit()
    return {"ok": True, "prediction_run_id": run.id, "job_id": job.id}
