"""Application settings and environment loading utilities."""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseSettings):
    """Central application configuration."""

    app_name: str = "Flow RMS Invoice API"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    database_url: str = Field(
        default="sqlite:///./data/dev.db",
        description="SQLAlchemy database URL",
        alias="DATABASE_URL",
    )
    ai_api_key: str | None = Field(default=None, alias="AI_API_KEY")
    ai_model: str = Field(default="gpt-4o-mini", alias="AI_MODEL")

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = False
        populate_by_name = True


@lru_cache
def get_settings() -> "Settings":
    """Return cached settings instance."""

    return Settings()
