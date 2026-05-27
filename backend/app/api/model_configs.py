from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import ModelConfig

router = APIRouter(prefix="/model-configs", tags=["model-configs"])


class ModelConfigUpdate(BaseModel):
    provider: str
    model_name: str
    temperature: float = 0.2
    max_tokens: int = 3000
    timeout_seconds: int = 120
    enabled: bool = True
    extra: dict = Field(default_factory=dict)


@router.get("")
def list_model_configs(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    configs = db.scalars(select(ModelConfig).order_by(ModelConfig.role)).all()
    return [
        {
            "id": config.id,
            "role": config.role,
            "provider": config.provider,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "timeout_seconds": config.timeout_seconds,
            "enabled": config.enabled,
            "extra": config.extra,
        }
        for config in configs
    ]


@router.put("/{role}")
def update_model_config(
    role: str,
    payload: ModelConfigUpdate,
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    config = db.scalar(select(ModelConfig).where(ModelConfig.role == role))
    if not config:
        config = ModelConfig(role=role, provider=payload.provider, model_name=payload.model_name)
        db.add(config)
    for key, value in payload.model_dump().items():
        setattr(config, key, value)
    db.commit()
    return {"ok": True, "id": config.id}

