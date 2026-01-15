"""Unit tests for tenant context utilities."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.tenant import (
    TenantContext,
    TenantMismatchError,
    TenantNotFoundError,
    load_tenant_context,
)
from app.db.models import Tenant


class DummyEntity:
    def __init__(self, tenant_id: object | None) -> None:
        self.tenant_id = tenant_id


def test_ensure_matches_accepts_matching_tenant() -> None:
    context = TenantContext(tenant_id="tenant-123", tenant_name="Tenant")

    context.ensure_matches("tenant-123")


@pytest.mark.parametrize("provided_id", [None, "tenant-999"])
def test_ensure_matches_rejects_invalid_ids(provided_id: str | None) -> None:
    context = TenantContext(tenant_id="tenant-123", tenant_name="Tenant")

    with pytest.raises(TenantMismatchError):
        context.ensure_matches(provided_id)


def test_ensure_entity_belongs_casts_identifier_to_string() -> None:
    context = TenantContext(tenant_id="123", tenant_name="Tenant")
    entity = DummyEntity(tenant_id=123)

    context.ensure_entity_belongs(entity)


def test_ensure_entity_belongs_without_tenant_attribute_raises() -> None:
    context = TenantContext(tenant_id="tenant-123", tenant_name="Tenant")
    entity = DummyEntity(tenant_id=None)

    with pytest.raises(TenantMismatchError):
        context.ensure_entity_belongs(entity)


def test_load_tenant_context_returns_bound_context(session: Session) -> None:
    tenant = Tenant(name="Acme Corp")
    session.add(tenant)
    session.commit()

    context = load_tenant_context(session, tenant.id)

    assert context.tenant_id == str(tenant.id)
    assert context.tenant_name == tenant.name


def test_load_tenant_context_missing_tenant_raises(session: Session) -> None:
    missing_id = "non-existent-tenant"

    with pytest.raises(TenantNotFoundError):
        load_tenant_context(session, missing_id)
