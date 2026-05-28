import hashlib
import time
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import (
    Branch,
    EventCluster,
    EventClusterMember,
    InformationSource,
    Job,
    PredictionRun,
    RawNews,
)
from app.services.market_data import MarketDataService
from app.services.prediction_service import PredictionService
from app.services.source_fetcher import FetchCandidate, test_fetch


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
            self._fetch_source(db, job)
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
        snapshot = self.market_data.create_snapshot(
            db,
            snapshot_type=snapshot_type,
            asset_ids=asset_ids,
        )
        job.payload = {
            **job.payload,
            "market_snapshot_id": snapshot.id,
            "captured_at": snapshot.captured_at.isoformat(),
        }

    def _fetch_source(self, db: Session, job: Job) -> None:
        source_id = job.payload.get("source_id")
        source = db.get(InformationSource, source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        candidates = test_fetch(source.entry_url, source.fetch_mode, source.selectors)
        ok_candidates = [candidate for candidate in candidates if candidate.status == "ok"]
        if not ok_candidates:
            message = candidates[0].error if candidates else "No candidates returned"
            source.last_fetch_at = utcnow()
            source.last_status = "failed"
            source.last_error = message
            job.payload = {
                **job.payload,
                "candidate_count": len(candidates),
                "inserted_count": 0,
                "skipped_count": 0,
                "error": message,
            }
            return

        inserted_count = 0
        skipped_count = 0
        for candidate in ok_candidates:
            raw_news, inserted = self._upsert_raw_news(db, source, candidate)
            if inserted:
                inserted_count += 1
            else:
                skipped_count += 1
            self._ensure_cluster(db, source, raw_news, candidate)

        source.last_fetch_at = utcnow()
        source.last_status = "succeeded"
        source.last_error = None
        job.payload = {
            **job.payload,
            "candidate_count": len(candidates),
            "inserted_count": inserted_count,
            "skipped_count": skipped_count,
        }

    def _upsert_raw_news(
        self,
        db: Session,
        source: InformationSource,
        candidate: FetchCandidate,
    ) -> tuple[RawNews, bool]:
        canonical_url = candidate.url
        existing = db.scalars(
            select(RawNews)
            .where(RawNews.source_id == source.id, RawNews.canonical_url == canonical_url)
            .limit(1)
        ).first()
        if existing:
            existing.summary = candidate.snippet or existing.summary
            existing.updated_at = utcnow()
            return existing, False

        raw_news = RawNews(
            source_id=source.id,
            title=candidate.title,
            url=candidate.url,
            canonical_url=canonical_url,
            published_at=_parse_candidate_datetime(candidate.published_at),
            language=source.language,
            region=source.region,
            extracted_text=candidate.snippet,
            summary=candidate.snippet,
            content_hash=_candidate_hash(source.id, candidate),
            status="new",
            metadata_json={"fetch_mode": source.fetch_mode, "source_type": source.source_type},
        )
        db.add(raw_news)
        db.flush()
        return raw_news, True

    def _ensure_cluster(
        self,
        db: Session,
        source: InformationSource,
        raw_news: RawNews,
        candidate: FetchCandidate,
    ) -> None:
        existing_membership = db.scalars(
            select(EventClusterMember)
            .where(EventClusterMember.raw_news_id == raw_news.id)
            .limit(1)
        ).first()
        if existing_membership:
            return

        cluster = EventCluster(
            canonical_title=raw_news.title,
            summary=candidate.snippet,
            earliest_published_at=raw_news.published_at,
            latest_published_at=raw_news.published_at,
            source_count=1,
            source_types=[source.source_type],
            representative_news_id=raw_news.id,
            involved_assets=[],
            involved_themes=[],
            neutral_extraction={"source_name": source.name, "fetch_mode": source.fetch_mode},
        )
        db.add(cluster)
        db.flush()
        db.add(EventClusterMember(event_cluster_id=cluster.id, raw_news_id=raw_news.id))

    def _mark_stub_complete(self, job: Job, message: str) -> None:
        job.payload = {**job.payload, "note": message}


def _parse_candidate_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _candidate_hash(source_id: int, candidate: FetchCandidate) -> str:
    payload = f"{source_id}\n{candidate.url}\n{candidate.title}".encode()
    return hashlib.sha256(payload).hexdigest()
