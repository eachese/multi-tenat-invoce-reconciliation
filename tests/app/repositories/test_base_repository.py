"""Unit tests for repository abstractions."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext, TenantMismatchError
from app.db.models import Tenant, Vendor
from app.repositories.tenant import TenantRepository
from app.repositories.vendor import VendorRepository


def test_repository_crud_and_listing(session: Session) -> None:
    repo = TenantRepository(session)

    tenant_alpha = repo.add(Tenant(name="Alpha"))
    tenant_bravo = repo.add(Tenant(name="Bravo"))
    session.commit()

    alpha_id = tenant_alpha.id
    bravo_id = tenant_bravo.id

    fetched = repo.get(alpha_id)
    assert fetched is not None
    assert fetched.id == alpha_id

    missing = repo.get("missing-id")
    assert missing is None

    all_tenants = repo.list()
    assert {tenant.id for tenant in all_tenants} == {alpha_id, bravo_id}

    limited = repo.list(limit=1)
    assert len(limited) == 1

    empty_page = repo.list(offset=10)
    assert empty_page == []

    repo.delete(tenant_alpha)
    session.commit()

    assert repo.get(alpha_id) is None
    remaining_ids = {tenant.id for tenant in repo.list()}
    assert remaining_ids == {bravo_id}


def test_tenant_scoped_repository_filters_by_tenant(session: Session) -> None:
    tenant_repo = TenantRepository(session)
    tenant_a = tenant_repo.add(Tenant(name="Tenant A"))
    tenant_b = tenant_repo.add(Tenant(name="Tenant B"))
    session.commit()

    vendor_repo = VendorRepository(session)
    vendor_a1 = vendor_repo.add(Vendor(name="Vendor A1", tenant_id=tenant_a.id))
    vendor_a2 = vendor_repo.add(Vendor(name="Vendor A2", tenant_id=tenant_a.id))
    vendor_b1 = vendor_repo.add(Vendor(name="Vendor B1", tenant_id=tenant_b.id))
    session.commit()

    context_a = TenantContext(tenant_id=str(tenant_a.id), tenant_name=tenant_a.name)
    context_b = TenantContext(tenant_id=str(tenant_b.id), tenant_name=tenant_b.name)

    assert vendor_repo.get_for_tenant(context_a, vendor_a1.id) is not None
    assert vendor_repo.get_for_tenant(context_a, vendor_b1.id) is None

    tenant_a_vendors = vendor_repo.list_for_tenant(context_a)
    assert {vendor.id for vendor in tenant_a_vendors} == {vendor_a1.id, vendor_a2.id}

    tenant_b_vendors = vendor_repo.list_for_tenant(context_b, limit=1)
    assert len(tenant_b_vendors) == 1
    assert tenant_b_vendors[0].tenant_id == tenant_b.id


def test_assert_entity_tenant_accepts_non_string_ids(session: Session) -> None:
    repo = VendorRepository(session)
    context = TenantContext(tenant_id="42", tenant_name="Tenant")
    entity = SimpleNamespace(tenant_id=42)

    repo.assert_entity_tenant(context, entity)


def test_assert_entity_tenant_raises_when_missing_id(session: Session) -> None:
    repo = VendorRepository(session)
    context = TenantContext(tenant_id="tenant-1", tenant_name="Tenant")
    entity = SimpleNamespace(tenant_id=None)

    with pytest.raises(TenantMismatchError):
        repo.assert_entity_tenant(context, entity)


def test_assert_entity_tenant_raises_on_mismatch(session: Session) -> None:
    repo = VendorRepository(session)
    context = TenantContext(tenant_id="tenant-1", tenant_name="Tenant")
    entity = SimpleNamespace(tenant_id="tenant-2")

    with pytest.raises(TenantMismatchError):
        repo.assert_entity_tenant(context, entity)
