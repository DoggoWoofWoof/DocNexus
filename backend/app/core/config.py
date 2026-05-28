from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "DocNexus Agent Orchestrator"
    database_url: str = "sqlite:///./docnexus.db"
    artifact_dir: Path = Path("./artifacts")

    llm_provider: str = "mistral"
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-small-latest"

    e2b_api_key: str | None = None
    sandbox_provider: str = "e2b"
    sandbox_timeout_seconds: int = 30

    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_artifact_dir(self) -> Path:
        return self.artifact_dir.expanduser().resolve()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
