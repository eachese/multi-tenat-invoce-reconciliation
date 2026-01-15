"""Unit tests for the database utilities."""
from __future__ import annotations

import sys
from importlib import import_module
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def load_database_module(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Reload app.core.database with a configurable DATABASE_URL."""

    def _loader(database_url: str = "sqlite+pysqlite:///:memory:"):
        from app.core import settings as settings_module

        monkeypatch.setenv("DATABASE_URL", database_url)
        settings_module.get_settings.cache_clear()
        sys.modules.pop("app.core.database", None)

        module = import_module("app.core.database")

        request.addfinalizer(lambda module_name="app.core.database": sys.modules.pop(module_name, None))
        request.addfinalizer(module.ENGINE.dispose)
        request.addfinalizer(settings_module.get_settings.cache_clear)

        return module

    return _loader


def test_engine_uses_database_url(load_database_module):
    url = "sqlite+pysqlite:///:memory:?cache=shared"
    database = load_database_module(url)

    assert database.ENGINE.url.render_as_string(hide_password=False) == url


def test_sessionlocal_creates_session_bound_to_engine(load_database_module):
    database = load_database_module()

    session = database.SessionLocal()
    try:
        assert session.bind is database.ENGINE
    finally:
        session.close()


def test_get_db_session_yields_and_closes(monkeypatch, load_database_module):
    database = load_database_module()

    class DummySession:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:  # pragma: no cover - simple setter
            self.closed = True

    dummy_session = DummySession()
    session_local = MagicMock(return_value=dummy_session)
    monkeypatch.setattr(database, "SessionLocal", session_local)

    session_generator = database.get_db_session()
    session_instance = next(session_generator)

    assert session_instance is dummy_session
    session_local.assert_called_once_with()

    with pytest.raises(StopIteration):
        next(session_generator)

    assert dummy_session.closed is True


def test_create_database_schema_invokes_metadata(monkeypatch, load_database_module):
    database = load_database_module()

    create_all = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", create_all)

    database.create_database_schema()

    create_all.assert_called_once_with(bind=database.ENGINE)
