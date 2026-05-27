from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InformationSource(Base, TimestampMixin):
    __tablename__ = "information_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="financial_news")
    entry_url: Mapped[str] = mapped_column(Text)
    fetch_mode: Mapped[str] = mapped_column(String(40), default="list_page")
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_weight: Mapped[float] = mapped_column(Float, default=1.0)
    fetch_frequency_minutes: Mapped[int] = mapped_column(Integer, default=180)
    requires_browser: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    selectors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    url_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(80), default="never_fetched")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_news: Mapped[list["RawNews"]] = relationship(back_populates="source")


class RawNews(Base, TimestampMixin):
    __tablename__ = "raw_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("information_sources.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="new")
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source: Mapped[InformationSource] = relationship(back_populates="raw_news")
    cluster_memberships: Mapped[list["EventClusterMember"]] = relationship(back_populates="raw_news")


class EventCluster(Base, TimestampMixin):
    __tablename__ = "event_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    earliest_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    source_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    representative_news_id: Mapped[int | None] = mapped_column(ForeignKey("raw_news.id"), nullable=True)
    involved_assets: Mapped[list[str]] = mapped_column(JSON, default=list)
    involved_themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    neutral_extraction: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    members: Mapped[list["EventClusterMember"]] = relationship(back_populates="cluster")
    scores: Mapped[list["EventScore"]] = relationship(back_populates="cluster")


class EventClusterMember(Base):
    __tablename__ = "event_cluster_members"
    __table_args__ = (UniqueConstraint("event_cluster_id", "raw_news_id", name="uq_cluster_news"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_cluster_id: Mapped[int] = mapped_column(ForeignKey("event_clusters.id"), index=True)
    raw_news_id: Mapped[int] = mapped_column(ForeignKey("raw_news.id"), index=True)

    cluster: Mapped[EventCluster] = relationship(back_populates="members")
    raw_news: Mapped[RawNews] = relationship(back_populates="cluster_memberships")


class AssetGroup(Base, TimestampMixin):
    __tablename__ = "asset_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40), default="theme")
    region: Mapped[str] = mapped_column(String(40), default="global")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    assets: Mapped[list["Asset"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("asset_groups.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    market: Mapped[str] = mapped_column(String(40), default="global")
    currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(40), default="stock")
    role: Mapped[str] = mapped_column(String(40), default="supporting")
    data_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    group: Mapped[AssetGroup] = relationship(back_populates="assets")


class MarketSnapshot(Base, TimestampMixin):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_type: Mapped[str] = mapped_column(String(40), default="daily")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    prices: Mapped[list["MarketPrice"]] = relationship(back_populates="snapshot")


class MarketPrice(Base, TimestampMixin):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("market_snapshots.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    fetch_status: Mapped[str] = mapped_column(String(80), default="pending")
    historical_features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    snapshot: Mapped[MarketSnapshot] = relationship(back_populates="prices")


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventScore(Base, TimestampMixin):
    __tablename__ = "event_scores"
    __table_args__ = (UniqueConstraint("branch_id", "event_cluster_id", name="uq_branch_cluster_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    event_cluster_id: Mapped[int] = mapped_column(ForeignKey("event_clusters.id"), index=True)
    score_type: Mapped[str] = mapped_column(String(40), default="human")
    importance: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(40), nullable=True)
    impact_horizons: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_assets: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    branch: Mapped[Branch] = relationship()
    cluster: Mapped[EventCluster] = relationship(back_populates="scores")


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("role", name="uq_model_config_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(80), default="openai")
    model_name: Mapped[str] = mapped_column(String(160))
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=3000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PredictionRun(Base, TimestampMixin):
    __tablename__ = "prediction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    market_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("market_snapshots.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="pending")
    run_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_event_cluster_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    branch: Mapped[Branch] = relationship()
    agent_outputs: Mapped[list["AgentOutput"]] = relationship(back_populates="prediction_run")
    forecasts: Mapped[list["AssetForecast"]] = relationship(back_populates="prediction_run")


class AgentOutput(Base, TimestampMixin):
    __tablename__ = "agent_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_run_id: Mapped[int] = mapped_column(ForeignKey("prediction_runs.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    role: Mapped[str] = mapped_column(String(80))
    round_name: Mapped[str] = mapped_column(String(80))
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="agent_outputs")
    branch: Mapped[Branch] = relationship()


class AssetForecast(Base, TimestampMixin):
    __tablename__ = "asset_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_run_id: Mapped[int] = mapped_column(ForeignKey("prediction_runs.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    asset_group_id: Mapped[int] = mapped_column(ForeignKey("asset_groups.id"), index=True)
    primary_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    region: Mapped[str] = mapped_column(String(40), default="global")
    horizon: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(40), default="neutral")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    bull_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    bear_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    support_levels: Mapped[list[float]] = mapped_column(JSON, default=list)
    resistance_levels: Mapped[list[float]] = mapped_column(JSON, default=list)
    invalidation: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_event_cluster_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    model_disagreements: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="forecasts")
    branch: Mapped[Branch] = relationship()
    asset_group: Mapped[AssetGroup] = relationship()
    primary_asset: Mapped[Asset] = relationship()
    scenarios: Mapped[list["ForecastScenario"]] = relationship(back_populates="forecast")


class ForecastScenario(Base, TimestampMixin):
    __tablename__ = "forecast_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("asset_forecasts.id"), index=True)
    scenario_type: Mapped[str] = mapped_column(String(40))
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    catalysts: Mapped[list[str]] = mapped_column(JSON, default=list)
    invalidations: Mapped[list[str]] = mapped_column(JSON, default=list)

    forecast: Mapped[AssetForecast] = relationship(back_populates="scenarios")


class ForecastEvaluation(Base, TimestampMixin):
    __tablename__ = "forecast_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("asset_forecasts.id"), index=True)
    realized_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    direction_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    target_error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

