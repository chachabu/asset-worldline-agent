import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import AssetForecast, AssetGroup, Branch, Job, PredictionRun


class JobRunner:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self.session_factory = session_factory

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
            self._mark_stub_complete(job, "Market data adapter is not wired yet.")
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
        groups = db.scalars(
            select(AssetGroup)
            .options(selectinload(AssetGroup.assets))
            .where(AssetGroup.enabled.is_(True))
            .order_by(AssetGroup.category.asc(), AssetGroup.name.asc())
            .limit(35)
        ).all()

        run.status = "running"
        run.started_at = utcnow()
        for group in groups:
            primary = next((asset for asset in group.assets if asset.role == "primary"), None)
            for horizon in ("1W", "1M", "3M"):
                db.add(
                    AssetForecast(
                        prediction_run_id=run.id,
                        branch_id=run.branch_id,
                        asset_group_id=group.id,
                        primary_asset_id=primary.id if primary else None,
                        region=group.region,
                        horizon=horizon,
                        direction="neutral",
                        confidence=0.0,
                        rationale=(
                            "MVP scaffold forecast. The branch/run boundaries and forecast matrix "
                            "are wired; real LLM discussion and market-data targets are next."
                        ),
                    )
                )
        run.status = "succeeded"
        run.finished_at = utcnow()
        job.payload = {**job.payload, "branch": branch.name if branch else None, "forecast_count": len(groups) * 3}

    def _mark_stub_complete(self, job: Job, message: str) -> None:
        job.payload = {**job.payload, "note": message}

