"""Unit tests for the invoice repository."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.tenant import TenantContext
from app.db.models import Invoice, InvoiceStatus, Tenant, Vendor
from app.repositories.invoice import InvoiceRepository


@pytest.fixture()
def tenant_context(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=str(tenant.id), tenant_name=tenant.name)


def _create_invoice(
    *,
    tenant_id: str,
    invoice_number: str,
    amount: str,
    invoice_date: date,
    status: InvoiceStatus,
    vendor_id: str | None = None,
    description: str | None = "Test invoice",
) -> Invoice:
    return Invoice(
        tenant_id=tenant_id,
        vendor_id=vendor_id,
        invoice_number=invoice_number,
        amount=Decimal(amount),
        currency="USD",
        invoice_date=invoice_date,
        description=description,
        status=status,
    )


def test_build_filter_query_applies_all_filters(
    session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    repository = InvoiceRepository(session)

    vendor = Vendor(name="Preferred Vendor", tenant_id=tenant.id)
    other_vendor = Vendor(name="Supporting Vendor", tenant_id=tenant.id)
    other_tenant = Tenant(name="Other Tenant")
    session.add_all([vendor, other_vendor, other_tenant])
    session.flush()

    matching_invoice = _create_invoice(
        tenant_id=tenant.id,
        vendor_id=vendor.id,
        invoice_number="INV-001",
        amount="120.00",
        invoice_date=date(2024, 1, 15),
        status=InvoiceStatus.OPEN,
    )
    session.add(matching_invoice)

    session.add_all(
        [
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                invoice_number="INV-002",
                amount="120.00",
                invoice_date=date(2024, 1, 15),
                status=InvoiceStatus.PAID,
            ),
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=other_vendor.id,
                invoice_number="INV-003",
                amount="120.00",
                invoice_date=date(2024, 1, 15),
                status=InvoiceStatus.OPEN,
            ),
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                invoice_number="INV-004",
                amount="120.00",
                invoice_date=date(2023, 12, 31),
                status=InvoiceStatus.OPEN,
            ),
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                invoice_number="INV-005",
                amount="200.00",
                invoice_date=date(2024, 1, 15),
                status=InvoiceStatus.OPEN,
            ),
            _create_invoice(
                tenant_id=other_tenant.id,
                vendor_id=None,
                invoice_number="INV-006",
                amount="120.00",
                invoice_date=date(2024, 1, 15),
                status=InvoiceStatus.OPEN,
            ),
        ]
    )
    session.flush()

    statement = repository.build_filter_query(
        tenant=tenant_context,
        status=InvoiceStatus.OPEN,
        vendor_id=vendor.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        min_amount=100.0,
        max_amount=150.0,
        offset=0,
        limit=5,
    )

    results = session.scalars(statement).all()

    assert [invoice.id for invoice in results] == [matching_invoice.id]


def test_build_filter_query_respects_pagination(
    session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    repository = InvoiceRepository(session)

    invoices = [
        _create_invoice(
            tenant_id=tenant.id,
            vendor_id=None,
            invoice_number=f"INV-1{index}",
            amount=f"{100 + index}.00",
            invoice_date=date(2024, 2, 10 + index),
            status=InvoiceStatus.OPEN,
        )
        for index in range(3)
    ]
    session.add_all(invoices)
    session.flush()

    all_results = session.scalars(
        repository.build_filter_query(tenant_context, offset=0, limit=10)
    ).all()
    paged_results = session.scalars(
        repository.build_filter_query(tenant_context, offset=1, limit=1)
    ).all()

    assert len(all_results) == 3
    assert len(paged_results) == 1
    assert paged_results[0].id == all_results[1].id


def test_count_filtered_applies_filters(
    session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    repository = InvoiceRepository(session)

    vendor = Vendor(name="Count Vendor", tenant_id=tenant.id)
    other_vendor = Vendor(name="Other Count Vendor", tenant_id=tenant.id)
    other_tenant = Tenant(name="Foreign Tenant")
    session.add_all([vendor, other_vendor, other_tenant])
    session.flush()

    session.add_all(
        [
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                invoice_number="MATCH-001",
                amount="90.00",
                invoice_date=date(2024, 3, 1),
                status=InvoiceStatus.MATCHED,
            ),
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                invoice_number="MATCH-002",
                amount="95.00",
                invoice_date=date(2024, 3, 2),
                status=InvoiceStatus.OPEN,
            ),
            _create_invoice(
                tenant_id=tenant.id,
                vendor_id=other_vendor.id,
                invoice_number="MATCH-003",
                amount="92.00",
                invoice_date=date(2024, 3, 3),
                status=InvoiceStatus.MATCHED,
            ),
            _create_invoice(
                tenant_id=other_tenant.id,
                vendor_id=None,
                invoice_number="MATCH-004",
                amount="91.00",
                invoice_date=date(2024, 3, 4),
                status=InvoiceStatus.MATCHED,
            ),
        ]
    )
    session.flush()

    count = repository.count_filtered(
        tenant=tenant_context,
        status=InvoiceStatus.MATCHED,
        vendor_id=vendor.id,
        start_date=date(2024, 3, 1),
        end_date=date(2024, 3, 31),
        min_amount=80.0,
        max_amount=100.0,
    )

    assert count == 1


def test_list_open_invoices_returns_only_open_for_tenant(
    session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    repository = InvoiceRepository(session)

    other_tenant = Tenant(name="External Tenant")
    session.add(other_tenant)
    session.flush()

    open_one = _create_invoice(
        tenant_id=tenant.id,
        vendor_id=None,
        invoice_number="OPEN-001",
        amount="50.00",
        invoice_date=date(2024, 4, 5),
        status=InvoiceStatus.OPEN,
    )
    open_two = _create_invoice(
        tenant_id=tenant.id,
        vendor_id=None,
        invoice_number="OPEN-002",
        amount="75.00",
        invoice_date=date(2024, 4, 6),
        status=InvoiceStatus.OPEN,
    )
    non_open = _create_invoice(
        tenant_id=tenant.id,
        vendor_id=None,
        invoice_number="OPEN-003",
        amount="80.00",
        invoice_date=date(2024, 4, 7),
        status=InvoiceStatus.PAID,
    )
    external_open = _create_invoice(
        tenant_id=other_tenant.id,
        vendor_id=None,
        invoice_number="OPEN-004",
        amount="65.00",
        invoice_date=date(2024, 4, 8),
        status=InvoiceStatus.OPEN,
    )
    session.add_all([open_one, open_two, non_open, external_open])
    session.flush()

    results = repository.list_open_invoices(tenant_context)

    assert {invoice.id for invoice in results} == {open_one.id, open_two.id}
    assert all(invoice.tenant_id == tenant.id for invoice in results)
