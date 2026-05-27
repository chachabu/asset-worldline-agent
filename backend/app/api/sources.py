from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import InformationSource
from app.schemas.common import (
    InformationSourceCreate,
    InformationSourceOut,
    SourceTestCandidate,
    SourceTestRequest,
)
from app.services.source_fetcher import test_fetch

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[InformationSourceOut])
def list_sources(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[InformationSource]:
    return list(db.scalars(select(InformationSource).order_by(InformationSource.created_at.desc())).all())


@router.post("", response_model=InformationSourceOut)
def create_source(
    payload: InformationSourceCreate,
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> InformationSource:
    source = InformationSource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.put("/{source_id}", response_model=InformationSourceOut)
def update_source(
    source_id: int,
    payload: InformationSourceCreate,
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> InformationSource:
    source = db.get(InformationSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    for key, value in payload.model_dump().items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.post("/test", response_model=list[SourceTestCandidate])
def test_source(payload: SourceTestRequest, _: CurrentUser) -> list[dict]:
    candidates = test_fetch(payload.entry_url, payload.fetch_mode, payload.selectors)
    return [candidate.__dict__ for candidate in candidates]

