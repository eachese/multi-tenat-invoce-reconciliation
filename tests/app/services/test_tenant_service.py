"""Unit tests for the TenantService."""
from __future__ import annotations

from sqlalchemy import select

import pytest

from app.db.models import Tenant
from app.schemas.tenant import TenantCreate
from app.services.exceptions import ConflictError, NotFoundError
from app.services.tenant_service import TenantService


def test_create_persists_and_returns_read_model(session) -> None:
    service = TenantService(session)

    result = service.create(TenantCreate(name="Acme Corp"))

    assert result.name == "Acme Corp"
    assert isinstance(result.id, str) and result.id

    persisted = session.get(Tenant, result.id)
    assert persisted is not None
    assert persisted.name == "Acme Corp"


def test_create_duplicate_name_raises_conflict_error(session) -> None:
    service = TenantService(session)
    service.create(TenantCreate(name="Acme Corp"))

    with pytest.raises(ConflictError):
        service.create(TenantCreate(name="Acme Corp"))

    names = session.scalars(select(Tenant.name)).all()
    assert names == ["Acme Corp"]


def test_list_returns_all_tenants(session) -> None:
    service = TenantService(session)
    service.create(TenantCreate(name="Acme Corp"))
    service.create(TenantCreate(name="Beta LLC"))

    tenants = service.list()

    assert {tenant.name for tenant in tenants} == {"Acme Corp", "Beta LLC"}
    assert all(tenant.created_at is not None for tenant in tenants)


def test_get_returns_tenant(session) -> None:
    service = TenantService(session)
    created = service.create(TenantCreate(name="Acme Corp"))

    retrieved = service.get(created.id)

    assert retrieved.id == created.id
    assert retrieved.name == "Acme Corp"


def test_get_missing_raises_not_found(session) -> None:
    service = TenantService(session)

    with pytest.raises(NotFoundError):
        service.get("non-existent-id")
