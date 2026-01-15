"""Database engine and session management utilities."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, models  # noqa: F401  # Ensure models are imported for metadata registration

from .settings import get_settings

_settings = get_settings()

ENGINE = create_engine(_settings.database_url, future=True)
SessionLocal = sessionmaker(bind=ENGINE, class_=Session, autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session and ensure closure."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_database_schema() -> None:
    """Create database tables based on ORM metadata."""

    Base.metadata.create_all(bind=ENGINE)
