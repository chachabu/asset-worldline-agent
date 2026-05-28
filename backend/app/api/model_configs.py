from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import ModelConfig
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/model-configs", tags=["model-configs"])
llm_client = LLMClient()


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
    provider_statuses = llm_client.provider_statuses()
    return [
        {
            "id": config.id,
            "role": config.role,
            "provider": config.provider,
            "provider_key_configured": provider_statuses.get(config.provider, False),
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


@router.get("/providers")
def list_provider_statuses(_: CurrentUser) -> dict:
    return {
        "providers": [
            {"provider": provider, "key_configured": configured}
            for provider, configured in llm_client.provider_statuses().items()
        ]
    }


@router.post("/{role}/test")
def test_model_config(
    role: str,
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    config = db.scalar(select(ModelConfig).where(ModelConfig.role == role))
    if not config:
        return {"ok": False, "error": "Unknown role"}
    result = llm_client.test_config(config)
    return {
        "ok": not result.used_fallback and bool(result.json_data),
        "provider": result.provider,
        "model": result.model,
        "used_fallback": result.used_fallback,
        "message": result.json_data.get("fallback_reason")
        or result.json_data.get("reason")
        or "Connection test completed.",
    }
