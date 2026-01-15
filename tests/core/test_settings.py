"""Unit tests for the app.core.settings module."""
from __future__ import annotations

import importlib
import sys
from typing import Iterable

import pytest

ENV_KEYS: Iterable[str] = ("ENVIRONMENT", "DATABASE_URL", "AI_API_KEY", "AI_MODEL")


@pytest.fixture()
def settings_module(monkeypatch: pytest.MonkeyPatch):
    module = importlib.import_module("app.core.settings")
    module.get_settings.cache_clear()

    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)

    yield module

    module.get_settings.cache_clear()


def test_settings_defaults(settings_module):
    settings = settings_module.Settings()

    assert settings.app_name == "Flow RMS Invoice API"
    assert settings.environment == "development"
    assert settings.database_url == "sqlite:///./data/dev.db"
    assert settings.ai_api_key is None
    assert settings.ai_model == "gpt-4o-mini"


def test_settings_env_alias_override(settings_module, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gpt-4.1-mini")

    settings = settings_module.Settings()

    assert settings.environment == "production"
    assert settings.database_url == "postgresql+psycopg://user:pass@localhost/db"
    assert settings.ai_api_key == "test-key"
    assert settings.ai_model == "gpt-4.1-mini"


def test_settings_accepts_field_names_despite_alias(settings_module):
    settings = settings_module.Settings(
        environment="qa",
        database_url="sqlite:///./test.db",
        ai_model="gpt-test",
        ai_api_key="inline-key",
    )

    assert settings.environment == "qa"
    assert settings.database_url == "sqlite:///./test.db"
    assert settings.ai_model == "gpt-test"
    assert settings.ai_api_key == "inline-key"


def test_settings_env_lookup_case_insensitive(settings_module, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ai_model", "case-insensitive-model")

    settings = settings_module.Settings()

    assert settings.ai_model == "case-insensitive-model"


def test_get_settings_returns_cached_instance(settings_module):
    first = settings_module.get_settings()
    second = settings_module.get_settings()

    assert first is second


def test_get_settings_cache_clear_allows_refresh(settings_module, monkeypatch: pytest.MonkeyPatch):
    first = settings_module.get_settings()
    assert first.environment == "development"

    monkeypatch.setenv("ENVIRONMENT", "staging")

    still_cached = settings_module.get_settings()
    assert still_cached is first
    assert still_cached.environment == "development"

    settings_module.get_settings.cache_clear()
    refreshed = settings_module.get_settings()

    assert refreshed is not first
    assert refreshed.environment == "staging"


def test_settings_module_loads_dotenv_file(monkeypatch: pytest.MonkeyPatch):
    dotenv_module = importlib.import_module("dotenv")
    original = dotenv_module.load_dotenv

    calls: dict[str, dict[str, object]] = {}

    def fake_load_dotenv(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return True

    monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)
    sys.modules.pop("app.core.settings", None)

    module = importlib.import_module("app.core.settings")

    assert "kwargs" in calls
    assert calls["kwargs"].get("dotenv_path") == module.ENV_FILE

    monkeypatch.setattr("dotenv.load_dotenv", original)
    importlib.reload(module)
    module.get_settings.cache_clear()
