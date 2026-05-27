import time

from sqlalchemy import select

from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import InformationSource, Job


def enqueue_due_source_fetches() -> int:
    created = 0
    with SessionLocal() as db:
        sources = db.scalars(select(InformationSource).where(InformationSource.enabled.is_(True))).all()
        for source in sources:
            pending_fetch_jobs = db.scalars(
                select(Job).where(Job.job_type == "fetch_source", Job.status == "pending")
            ).all()
            existing = next(
                (job for job in pending_fetch_jobs if job.payload.get("source_id") == source.id),
                None,
            )
            if existing:
                continue
            db.add(Job(job_type="fetch_source", payload={"source_id": source.id}, scheduled_at=utcnow()))
            created += 1
        db.commit()
    return created


def main() -> None:
    while True:
        enqueue_due_source_fetches()
        time.sleep(60)


if __name__ == "__main__":
    main()
