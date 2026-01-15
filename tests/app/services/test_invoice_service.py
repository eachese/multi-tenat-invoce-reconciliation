"""Unit tests for :mod:`app.services.invoice_service`."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.tenant import TenantContext
from app.db.models import InvoiceStatus
from app.schemas.invoice import InvoiceCreate, InvoiceFilterParams
from app.services import invoice_service
from app.services.invoice_service import InvoiceService


def _invoice_namespace(**overrides: object) -> SimpleNamespace:
    base = {
        "id": overrides.get("id", "generated-id"),
        "tenant_id": overrides["tenant_id"],
        "vendor_id": overrides.get("vendor_id"),
        "invoice_number": overrides.get("invoice_number"),
        "amount": overrides.get("amount", Decimal("0")),
        "currency": overrides.get("currency", "USD"),
        "invoice_date": overrides.get("invoice_date"),
        "description": overrides.get("description"),
        "status": overrides.get("status", InvoiceStatus.OPEN),
        "created_at": overrides.get("created_at", datetime(2024, 1, 1)),
    }
    return SimpleNamespace(**base)


def test_create_persists_invoice_with_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    tenant = TenantContext(tenant_id="tenant-123", tenant_name="Tenant")

    class RecordingRepository:
        def __init__(self, bound_session: MagicMock) -> None:
            self.session = bound_session
            self.created_kwargs: dict[str, object] | None = None

        def model(self, **kwargs: object) -> SimpleNamespace:
            self.created_kwargs = kwargs
            return _invoice_namespace(**kwargs)

    repository = RecordingRepository(session)
    monkeypatch.setattr(invoice_service, "InvoiceRepository", lambda _session: repository)

    service = InvoiceService(session, tenant)
    payload = InvoiceCreate(amount=125.5, currency="usd", description="Consulting")

    result = service.create(payload)

    assert repository.created_kwargs is not None
    assert repository.created_kwargs["tenant_id"] == tenant.tenant_id
    assert repository.created_kwargs["currency"] == "USD"
    assert isinstance(repository.created_kwargs["amount"], Decimal)
    session.add.assert_called_once()
    session.commit.assert_called_once()
    session.refresh.assert_called_once()

    assert result.currency == "USD"
    assert result.tenant_id == tenant.tenant_id
    assert result.amount == Decimal("125.50")


def test_list_applies_filters_and_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    tenant = TenantContext(tenant_id="tenant-abc", tenant_name="Tenant")
    statement = object()
    rows = [
        _invoice_namespace(
            tenant_id=tenant.tenant_id,
            id="invoice-1",
            amount=Decimal("50.00"),
            currency="USD",
            status=InvoiceStatus.MATCHED,
        )
    ]

    scalars_result = MagicMock()
    scalars_result.all.return_value = rows
    session.scalars.return_value = scalars_result

    class QueryRepository:
        def __init__(self, bound_session: MagicMock) -> None:
            self.session = bound_session
            self.built_filters: dict[str, object] | None = None
            self.count_filters: dict[str, object] | None = None

        def build_filter_query(
            self,
            *,
            tenant: TenantContext,
            status: InvoiceStatus | None,
            vendor_id: str | None,
            start_date,
            end_date,
            min_amount,
            max_amount,
            offset: int,
            limit: int,
        ) -> object:
            self.built_filters = {
                "tenant": tenant,
                "status": status,
                "vendor_id": vendor_id,
                "start_date": start_date,
                "end_date": end_date,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "offset": offset,
                "limit": limit,
            }
            return statement

        def count_filtered(
            self,
            *,
            tenant: TenantContext,
            status: InvoiceStatus | None,
            vendor_id: str | None,
            start_date,
            end_date,
            min_amount,
            max_amount,
        ) -> int:
            self.count_filters = {
                "tenant": tenant,
                "status": status,
                "vendor_id": vendor_id,
                "start_date": start_date,
                "end_date": end_date,
                "min_amount": min_amount,
                "max_amount": max_amount,
            }
            return 7

    repository = QueryRepository(session)
    monkeypatch.setattr(invoice_service, "InvoiceRepository", lambda _session: repository)

    service = InvoiceService(session, tenant)
    filters = InvoiceFilterParams(
        status=InvoiceStatus.MATCHED,
        vendor_id="vendor-1",
        min_amount=10,
        max_amount=100,
    )

    response = service.list(filters, offset=5, limit=2)

    assert repository.built_filters == {
        "tenant": tenant,
        "status": InvoiceStatus.MATCHED,
        "vendor_id": "vendor-1",
        "start_date": None,
        "end_date": None,
        "min_amount": 10,
        "max_amount": 100,
        "offset": 5,
        "limit": 2,
    }
    assert repository.count_filters == {
        "tenant": tenant,
        "status": InvoiceStatus.MATCHED,
        "vendor_id": "vendor-1",
        "start_date": None,
        "end_date": None,
        "min_amount": 10,
        "max_amount": 100,
    }
    session.scalars.assert_called_once_with(statement)
    scalars_result.all.assert_called_once()

    assert response.total == 7
    assert len(response.items) == 1
    assert response.items[0].id == "invoice-1"
    assert response.items[0].status == InvoiceStatus.MATCHED


def test_delete_removes_invoice_for_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    tenant = TenantContext(tenant_id="tenant-xyz", tenant_name="Tenant")
    invoice_obj = _invoice_namespace(tenant_id=tenant.tenant_id, id="invoice-42")

    class DeleteRepository:
        def __init__(self, bound_session: MagicMock) -> None:
            self.session = bound_session
            self.requested_tenant: TenantContext | None = None
            self.requested_id: str | None = None

        def get_for_tenant(self, tenant: TenantContext, invoice_id: str) -> SimpleNamespace:
            self.requested_tenant = tenant
            self.requested_id = invoice_id
            return invoice_obj

    repository = DeleteRepository(session)
    monkeypatch.setattr(invoice_service, "InvoiceRepository", lambda _session: repository)

    service = InvoiceService(session, tenant)
    service.delete("invoice-42")

    assert repository.requested_tenant == tenant
    assert repository.requested_id == "invoice-42"
    session.delete.assert_called_once_with(invoice_obj)
    session.commit.assert_called_once()


def test_delete_raises_when_invoice_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    tenant = TenantContext(tenant_id="tenant-missing", tenant_name="Tenant")

    class EmptyRepository:
        def __init__(self, bound_session: MagicMock) -> None:
            self.session = bound_session

        def get_for_tenant(self, tenant: TenantContext, invoice_id: str) -> None:
            return None

    repository = EmptyRepository(session)
    monkeypatch.setattr(invoice_service, "InvoiceRepository", lambda _session: repository)

    service = InvoiceService(session, tenant)

    with pytest.raises(invoice_service.NotFoundError):
        service.delete("unknown")

    session.delete.assert_not_called()
    session.commit.assert_not_called()
