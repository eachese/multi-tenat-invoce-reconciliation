"""Unit tests for the tenant repository implementation."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Tenant
from app.repositories.tenant import TenantRepository


def test_model_attribute_is_tenant(session: Session) -> None:
    repo = TenantRepository(session)

    assert repo.model is Tenant


def test_add_persists_tenant(session: Session) -> None:
    repo = TenantRepository(session)
    created = repo.add(Tenant(name="Acme Corp"))

    session.commit()

    persisted = session.get(Tenant, created.id)
    assert persisted is not None
    assert persisted.name == "Acme Corp"


def test_get_returns_tenant_by_id(session: Session, tenant: Tenant) -> None:
    repo = TenantRepository(session)

    found = repo.get(tenant.id)

    assert found is not None
    assert found.id == tenant.id
    assert found.name == tenant.name


def test_get_returns_none_for_missing_tenant(session: Session) -> None:
    repo = TenantRepository(session)

    missing = repo.get("missing-tenant-id")

    assert missing is None


def test_list_returns_all_tenants(session: Session) -> None:
    repo = TenantRepository(session)
    tenants = [Tenant(name="Tenant A"), Tenant(name="Tenant B"), Tenant(name="Tenant C")]
    session.add_all(tenants)
    session.commit()

    retrieved = repo.list()

    assert {tenant.id for tenant in retrieved} == {tenant.id for tenant in tenants}


def test_delete_removes_tenant(session: Session) -> None:
    repo = TenantRepository(session)
    removable = Tenant(name="Removable Tenant")
    session.add(removable)
    session.commit()

    repo.delete(removable)
    session.commit()

    assert session.get(Tenant, removable.id) is None
