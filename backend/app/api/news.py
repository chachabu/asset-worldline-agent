from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import Branch, EventCluster, EventScore
from app.schemas.common import EventScoreUpdate

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/clusters")
def list_event_clusters(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    clusters = db.scalars(select(EventCluster).order_by(EventCluster.created_at.desc()).limit(200)).all()
    return [
        {
            "id": cluster.id,
            "canonical_title": cluster.canonical_title,
            "summary": cluster.summary,
            "source_count": cluster.source_count,
            "source_types": cluster.source_types,
            "involved_assets": cluster.involved_assets,
            "involved_themes": cluster.involved_themes,
            "created_at": cluster.created_at,
        }
        for cluster in clusters
    ]


@router.post("/clusters/{cluster_id}/human-score")
def upsert_human_score(
    cluster_id: int,
    payload: EventScoreUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    cluster = db.get(EventCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Event cluster not found")
    branch = db.scalar(select(Branch).where(Branch.name == "human_scored"))
    if not branch:
        raise HTTPException(status_code=500, detail="Human branch is not seeded")
    score = db.scalar(
        select(EventScore).where(
            EventScore.branch_id == branch.id,
            EventScore.event_cluster_id == cluster_id,
        )
    )
    if not score:
        score = EventScore(branch_id=branch.id, event_cluster_id=cluster_id, score_type="human")
        db.add(score)
    score.importance = payload.importance
    score.direction = payload.direction
    score.impact_horizons = payload.impact_horizons
    score.affected_groups = payload.affected_groups
    score.affected_assets = payload.affected_assets
    score.reason = payload.reason
    score.scored_by_user_id = user.id
    db.commit()
    return {"ok": True, "score_id": score.id}
