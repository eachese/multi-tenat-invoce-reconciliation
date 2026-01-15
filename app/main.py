"""Application entrypoint and FastAPI factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from alembic import command
from alembic.config import Config
from strawberry.fastapi import GraphQLRouter

from app.api.router import router as api_router
from app.core.database import ENGINE, create_database_schema
from app.core.settings import Settings, get_settings
from app.graphql.context import context_getter
from app.graphql.schema import schema


def _run_migrations() -> None:
    """Execute Alembic migrations; fallback to metadata create_all on failure."""

    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
    except Exception:
        create_database_schema()


def _ensure_sqlite_directory(settings: Settings) -> None:
    """If using SQLite file storage, ensure parent directory exists."""

    url = settings.database_url
    if url.startswith("sqlite") and ":memory:" not in url:
        # sqlite:///./data/dev.db -> ./data/dev.db
        database_path = url.removeprefix("sqlite:///")
        db_file = Path(database_path).expanduser().resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan, ensuring shared resources are initialized/closed."""

    settings = get_settings()
    _ensure_sqlite_directory(settings)
    _run_migrations()
    app.state.settings = settings
    try:
        yield
    finally:
        ENGINE.dispose()


def create_app() -> FastAPI:
    """Application factory used by ASGI servers."""

    settings = get_settings()
    graphql_app = GraphQLRouter(schema, path="/graphql", context_getter=context_getter)

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    application.include_router(api_router, prefix="/api")
    application.include_router(graphql_app, prefix="")

    return application


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
