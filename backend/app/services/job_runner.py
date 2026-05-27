import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import Branch, Job, PredictionRun
from app.services.market_data import MarketDataService
from app.services.prediction_service import PredictionService


class JobRunner:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self.session_factory = session_factory
        self.market_data = MarketDataService()
        self.prediction_service = PredictionService(market_data=self.market_data)

    def run_once(self) -> bool:
        with self.session_factory() as db:
            job = self._claim_next_job(db)
            if not job:
                return False
            try:
                self._execute(db, job)
            except Exception as exc:  # noqa: BLE001 - job errors must be captured in DB
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                job.retry_count += 1
                db.commit()
            return True

    def run_forever(self, poll_seconds: float) -> None:
        while True:
            did_work = self.run_once()
            if not did_work:
                time.sleep(poll_seconds)

    def _claim_next_job(self, db: Session) -> Job | None:
        job = db.scalars(
            select(Job)
            .where(Job.status == "pending", Job.scheduled_at <= utcnow())
            .order_by(Job.priority.asc(), Job.scheduled_at.asc())
            .limit(1)
        ).first()
        if not job:
            return None
        job.status = "running"
        job.started_at = utcnow()
        db.commit()
        db.refresh(job)
        return job

    def _execute(self, db: Session, job: Job) -> None:
        if job.job_type == "run_prediction":
            self._run_prediction(db, job)
        elif job.job_type == "fetch_source":
            self._mark_stub_complete(job, "Fetch source adapter is not wired yet.")
        elif job.job_type == "refresh_market_snapshot":
            self._refresh_market_snapshot(db, job)
        else:
            self._mark_stub_complete(job, f"No executor registered for job type {job.job_type}.")
        job.status = "succeeded"
        job.finished_at = utcnow()
        db.commit()

    def _run_prediction(self, db: Session, job: Job) -> None:
        prediction_run_id = job.payload.get("prediction_run_id")
        run = db.get(PredictionRun, prediction_run_id)
        if not run:
            raise ValueError(f"Prediction run {prediction_run_id} not found")
        branch = db.get(Branch, run.branch_id)
        forecast_count = self.prediction_service.run_prediction(db, run)
        job.payload = {
            **job.payload,
            "branch": branch.name if branch else None,
            "forecast_count": forecast_count,
        }

    def _refresh_market_snapshot(self, db: Session, job: Job) -> None:
        snapshot_type = job.payload.get("snapshot_type", "daily")
        asset_ids = job.payload.get("asset_ids")
        snapshot = self.market_data.create_snapshot(db, snapshot_type=snapshot_type, asset_ids=asset_ids)
        job.payload = {
            **job.payload,
            "market_snapshot_id": snapshot.id,
            "captured_at": snapshot.captured_at.isoformat(),
        }

    def _mark_stub_complete(self, job: Job, message: str) -> None:
        job.payload = {**job.payload, "note": message}
