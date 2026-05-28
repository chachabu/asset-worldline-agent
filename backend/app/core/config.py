from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/etc/asset-worldline/config.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Asset Worldline Agent"
    environment: str = "development"
    secret_key: str = Field(default="change-me-before-deploy")
    session_cookie_name: str = "asset_worldline_session"
    session_max_age_seconds: int = 7 * 24 * 60 * 60
    session_cookie_secure: bool = False

    database_url: str = "sqlite:///./dev.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    admin_bootstrap_user: str = "admin"
    admin_bootstrap_password: str | None = None
    admin_bootstrap_password_hash: str | None = None

    data_dir: Path = Path("/var/lib/asset-worldline")
    log_dir: Path = Path("/var/log/asset-worldline")

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None
    qwen_api_key: str | None = None
    stepfun_api_key: str | None = None
    openrouter_api_key: str | None = None

    fred_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    finnhub_api_key: str | None = None

    fetch_timeout_seconds: float = 20.0
    job_poll_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
