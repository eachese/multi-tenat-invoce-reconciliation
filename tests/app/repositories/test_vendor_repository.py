"""Unit tests for the vendor repository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db.models import Tenant, Vendor
from app.repositories.vendor import VendorRepository


def test_get_by_name_returns_vendor_for_matching_tenant(session: Session, tenant: Tenant) -> None:
    repository = VendorRepository(session)
    vendor = Vendor(name="Acme Supplies", tenant_id=tenant.id)
    session.add(vendor)
    session.commit()

    context = TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)

    result = repository.get_by_name(context, "Acme Supplies")

    assert result is not None
    assert result.id == vendor.id


def test_get_by_name_filters_out_other_tenant(session: Session, tenant: Tenant) -> None:
    repository = VendorRepository(session)
    other_tenant = Tenant(name="Other Corp")
    session.add(other_tenant)
    session.commit()

    tenant_vendor = Vendor(name="Shared Vendor", tenant_id=tenant.id)
    other_vendor = Vendor(name="Shared Vendor", tenant_id=other_tenant.id)
    session.add_all([tenant_vendor, other_vendor])
    session.commit()

    context = TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)

    result = repository.get_by_name(context, "Shared Vendor")

    assert result is not None
    assert result.id == tenant_vendor.id


def test_get_by_name_returns_none_for_missing_vendor(session: Session, tenant: Tenant) -> None:
    repository = VendorRepository(session)
    context = TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)

    result = repository.get_by_name(context, "Unknown Vendor")

    assert result is None
