"""Application settings and environment loading utilities."""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseSettings):
    """Central application configuration."""

    app_name: str = "Flow RMS Invoice API"
    environment: str = Field(default="development")
    database_url: str = Field(
        default="sqlite:///./data/dev.db",
        description="SQLAlchemy database URL",
    )
    ai_api_key: str | None = Field(default=None)
    ai_model: str = Field(default="gpt-4o-mini")

    model_config = SettingsConfigDict(
        case_sensitive=False,
        populate_by_name=True,
        env_ignore_empty=True,
    )


@lru_cache
def get_settings() -> "Settings":
    """Return cached settings instance."""

    return Settings()
