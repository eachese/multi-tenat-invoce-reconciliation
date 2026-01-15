"""Unit tests for the application entrypoint module."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from app import main
from app.core.settings import Settings


def test_ensure_sqlite_directory_creates_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "db.sqlite"
    database_url = f"sqlite:///{db_path}"
    settings = Settings(database_url=database_url, environment="test")

    assert not db_path.parent.exists()

    main._ensure_sqlite_directory(settings)

    assert db_path.parent.exists()
    assert db_path.parent.is_dir()


@pytest.mark.asyncio
async def test_lifespan_initializes_and_disposes_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = object()
    ensure_calls: list[object] = []
    schema_calls: list[bool] = []
    disposed: list[bool] = []

    def fake_get_settings() -> object:
        return fake_settings

    def fake_ensure(settings: object) -> None:
        ensure_calls.append(settings)

    def fake_create_schema() -> None:
        schema_calls.append(True)

    class DummyEngine:
        def dispose(self) -> None:
            disposed.append(True)

    monkeypatch.setattr(main, "get_settings", fake_get_settings)
    monkeypatch.setattr(main, "_ensure_sqlite_directory", fake_ensure)
    monkeypatch.setattr(main, "create_database_schema", fake_create_schema)
    monkeypatch.setattr(main, "ENGINE", DummyEngine())

    app = FastAPI()

    async with main.lifespan(app):
        assert getattr(app.state, "settings") is fake_settings

    assert ensure_calls == [fake_settings]
    assert schema_calls == [True]
    assert disposed == [True]


def test_create_app_configures_routes_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    custom_settings = Settings(app_name="Test App", database_url="sqlite:///:memory:", environment="test")

    monkeypatch.setattr(main, "get_settings", lambda: custom_settings)

    application = main.create_app()

    assert isinstance(application, FastAPI)
    assert application.title == "Test App"
    assert application.version == "0.1.0"
    assert application.router.lifespan_context is main.lifespan

    paths = {getattr(route, "path", None) for route in application.routes}
    assert "/api/health" in paths
    assert "/graphql" in paths


def test_module_level_app_is_fastapi_instance() -> None:
    assert isinstance(main.app, FastAPI)
