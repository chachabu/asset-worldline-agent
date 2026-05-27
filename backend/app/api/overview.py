from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import (
    AssetForecast,
    EventCluster,
    EventScore,
    InformationSource,
    Job,
    PredictionRun,
)

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def overview(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> dict:
    source_count = db.scalar(select(func.count(InformationSource.id))) or 0
    enabled_source_count = (
        db.scalar(select(func.count(InformationSource.id)).where(InformationSource.enabled.is_(True))) or 0
    )
    event_count = db.scalar(select(func.count(EventCluster.id))) or 0
    scored_event_count = db.scalar(select(func.count(EventScore.id))) or 0
    pending_job_count = db.scalar(select(func.count(Job.id)).where(Job.status == "pending")) or 0
    failed_job_count = db.scalar(select(func.count(Job.id)).where(Job.status == "failed")) or 0
    latest_run = db.scalars(select(PredictionRun).order_by(PredictionRun.created_at.desc()).limit(1)).first()
    latest_forecasts = db.scalars(
        select(AssetForecast)
        .options(
            joinedload(AssetForecast.asset_group),
            joinedload(AssetForecast.branch),
            joinedload(AssetForecast.primary_asset),
        )
        .order_by(AssetForecast.created_at.desc())
        .limit(12)
    ).all()
    return {
        "sources": {"total": source_count, "enabled": enabled_source_count},
        "events": {"clusters": event_count, "scores": scored_event_count},
        "jobs": {"pending": pending_job_count, "failed": failed_job_count},
        "latest_prediction_run": {
            "id": latest_run.id,
            "status": latest_run.status,
            "created_at": latest_run.created_at,
        }
        if latest_run
        else None,
        "latest_forecasts": [
            {
                "id": forecast.id,
                "asset_group": forecast.asset_group.name,
                "asset_group_id": forecast.asset_group_id,
                "primary_asset": forecast.primary_asset.symbol if forecast.primary_asset else None,
                "branch": forecast.branch.name,
                "region": forecast.region,
                "horizon": forecast.horizon,
                "direction": forecast.direction,
                "base_target": forecast.base_target,
                "confidence": forecast.confidence,
            }
            for forecast in latest_forecasts
        ],
    }
