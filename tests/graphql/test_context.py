"""Tests for GraphQL context utilities."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app.core.tenant import TenantContext
from app.graphql import context as graphql_context


async def _empty_receive() -> dict[str, str]:
    await asyncio.sleep(0)
    return {"type": "http.request"}


def _make_request(headers: dict[str, str]) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/graphql",
        "headers": raw_headers,
    }
    return Request(scope, _empty_receive)


class DummySession:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> "DummySession":
        self.closed = False
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.closed = True
        return False


def test_graphql_context_get_session_uses_session_factory() -> None:
    tenant = TenantContext(tenant_id="tenant-1", tenant_name="Tenant One")
    sessions = [object(), object()]
    session_factory = MagicMock(side_effect=sessions)

    context = graphql_context.GraphQLContext(tenant=tenant, session_factory=session_factory)

    first_session = context.get_session()
    second_session = context.get_session()

    assert first_session is sessions[0]
    assert second_session is sessions[1]
    assert session_factory.call_count == 2


def test_build_context_loads_tenant_and_returns_graphql_context(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_context = TenantContext(tenant_id="tenant-123", tenant_name="Tenant 123")
    load_mock = MagicMock(return_value=tenant_context)
    monkeypatch.setattr(graphql_context, "load_tenant_context", load_mock)

    created_sessions: list[DummySession] = []

    def build_dummy_session() -> DummySession:
        session = DummySession()
        created_sessions.append(session)
        return session

    session_factory_mock = MagicMock(side_effect=build_dummy_session)
    monkeypatch.setattr(graphql_context, "SessionLocal", session_factory_mock)

    result = graphql_context.build_context("tenant-123")

    assert isinstance(result, graphql_context.GraphQLContext)
    assert result.tenant is tenant_context
    assert result.session_factory is session_factory_mock

    load_mock.assert_called_once()
    assert len(created_sessions) == 1
    session_used = created_sessions[0]
    load_mock.assert_called_with(session_used, "tenant-123")
    assert session_used.closed is True


def test_context_getter_builds_context_when_header_present(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_context = object()
    build_mock = MagicMock(return_value=expected_context)
    monkeypatch.setattr(graphql_context, "build_context", build_mock)

    request = _make_request({"x-tenant-id": "tenant-xyz"})

    result = graphql_context.context_getter(request)

    assert result is expected_context
    build_mock.assert_called_once_with("tenant-xyz")


def test_context_getter_missing_header_raises_http_exception() -> None:
    request = _make_request({})

    with pytest.raises(HTTPException) as exc_info:
        graphql_context.context_getter(request)

    exc = exc_info.value
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == "Missing x-tenant-id header"
