"""Environment-based configuration. No secret has a default value."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    frontend_url: str = "http://localhost:5173"
    extra_cors_origins: str = ""
    trust_proxy_headers: bool = False

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/farmagent"

    # Anthropic
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    anthropic_base_url: str | None = None
    anthropic_timeout_seconds: float = 60.0
    anthropic_max_retries: int = 2
    anthropic_max_tokens: int = 4096
    anthropic_adaptive_thinking: bool = False

    # Agent guard rails
    agent_max_iterations: int = Field(default=6, ge=1, le=20)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=40)
    agent_total_timeout_seconds: float = 150.0
    agent_history_messages: int = Field(default=20, ge=0, le=100)
    agent_max_message_chars: int = Field(default=4000, ge=100, le=20000)

    # OpenWeatherMap
    openweather_api_key: SecretStr | None = None
    openweather_base_url: str = "https://api.openweathermap.org"
    openweather_timeout_seconds: float = 10.0
    openweather_max_retries: int = Field(default=2, ge=0, le=5)
    openweather_retry_backoff_seconds: float = 0.4

    # Weather cache and freshness
    weather_current_ttl_seconds: int = 600
    weather_forecast_ttl_seconds: int = 1800
    weather_stale_after_seconds: int = 3 * 3600
    weather_cache_max_age_seconds: int = 6 * 3600

    # Rate limits, per client per minute
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_agent_per_minute: int = 12
    rate_limit_session_per_minute: int = 10

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Supabase and Render hand out plain postgres:// URLs; the app drives Postgres with psycopg 3.
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("anthropic_api_key", "openweather_api_key", mode="before")
    @classmethod
    def _blank_secret_is_missing(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def ai_configured(self) -> bool:
        return self.anthropic_api_key is not None

    @property
    def weather_configured(self) -> bool:
        return self.openweather_api_key is not None

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_url.rstrip("/")}
        origins.update(
            o.strip().rstrip("/") for o in self.extra_cors_origins.split(",") if o.strip()
        )
        if self.environment in ("development", "test"):
            origins.update({"http://localhost:5173", "http://127.0.0.1:5173"})
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
