from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100)).all()
    return [
        {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "priority": job.priority,
            "payload": job.payload,
            "scheduled_at": job.scheduled_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
        }
        for job in jobs
    ]


@router.post("/market-snapshot")
def enqueue_market_snapshot(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> dict:
    job = Job(job_type="refresh_market_snapshot", payload={"snapshot_type": "manual"})
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"ok": True, "job_id": job.id}
