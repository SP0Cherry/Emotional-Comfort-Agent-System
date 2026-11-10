from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "postgresql+psycopg://companion_dev:development@localhost:5432/companion"
    secret_key: str = "development-only-change-this-secret-before-deployment"
    phone_encryption_key: str = "development-only-separate-phone-encryption-key"
    provider_mode: str = "mock"
    llm_base_url: str = ""
    llm_model: str = "qwen-plus"
    dashscope_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    local_storage_dir: Path = Path("storage")
    run_timeout_seconds: int = Field(default=60, gt=0)
    generation_timeout_seconds: int = Field(default=45, gt=0)
    worker_concurrency: int = Field(default=4, gt=0, le=100)
    lease_seconds: int = Field(default=90, gt=0)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    signed_url_seconds: int = 300
    max_personas: int = 3
    max_avatar_bytes: int = 5 * 1024 * 1024
    max_avatar_pixels: int = 16_000_000
    max_user_daily_runs: int = 100
    sse_poll_seconds: float = Field(default=0.5, gt=0)
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def validate_environment(self):
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        if self.embedding_dimensions != 1024:
            raise ValueError("The current database requires EMBEDDING_DIMENSIONS=1024")
        if self.provider_mode not in {"mock", "live"}:
            raise ValueError("PROVIDER_MODE must be mock or live")
        if self.app_env not in {"development", "test"}:
            if self.provider_mode == "mock":
                raise ValueError("Mock providers are restricted to development/test")
            for name in ("secret_key", "phone_encryption_key"):
                value = getattr(self, name)
                if len(value) < 32 or "development" in value.lower():
                    raise ValueError(f"A separate, strong {name.upper()} is required")
            # SMS delivery is deliberately not impersonated by the development OTP provider.
            raise ValueError("Production startup is disabled until an audited SMS provider is configured")
        if self.provider_mode == "live" and (not self.dashscope_api_key or not self.llm_base_url):
            raise ValueError("Live mode requires DASHSCOPE_API_KEY and LLM_BASE_URL")
        return self


settings = Settings()
