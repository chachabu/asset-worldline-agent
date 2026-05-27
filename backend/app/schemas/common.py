from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str


class InformationSourceCreate(BaseModel):
    name: str
    source_type: str = "financial_news"
    entry_url: str
    fetch_mode: str = "list_page"
    language: str | None = None
    region: str | None = None
    default_tags: list[str] = Field(default_factory=list)
    source_weight: float = 1.0
    fetch_frequency_minutes: int = 180
    requires_browser: bool = False
    enabled: bool = True
    selectors: dict[str, Any] = Field(default_factory=dict)
    url_rules: dict[str, Any] = Field(default_factory=dict)


class InformationSourceOut(InformationSourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_fetch_at: datetime | None
    last_status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class SourceTestRequest(BaseModel):
    entry_url: str
    fetch_mode: str = "list_page"
    selectors: dict[str, Any] = Field(default_factory=dict)


class SourceTestCandidate(BaseModel):
    title: str
    url: str
    published_at: str | None = None
    snippet: str | None = None
    status: str
    error: str | None = None


class EventScoreUpdate(BaseModel):
    importance: float
    direction: str | None = None
    impact_horizons: list[str] = Field(default_factory=list)
    affected_groups: list[str] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
    reason: str | None = None

