"""Unit tests for API dependency providers."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.api import dependencies
from app.core.tenant import TenantContext, TenantNotFoundError
from app.schemas.invoice import InvoiceFilterParams


def test_tenant_id_path_returns_string() -> None:
    tenant_uuid = uuid4()

    result = dependencies.tenant_id_path(tenant_uuid)

    assert result == str(tenant_uuid)


def test_get_tenant_context_returns_loaded_context(session, monkeypatch) -> None:
    expected = TenantContext(tenant_id="tenant-1", tenant_name="Tenant One")

    def fake_load_tenant_context(db_session, tenant_id):
        assert db_session is session
        assert tenant_id == "tenant-1"
        return expected

    monkeypatch.setattr(dependencies, "load_tenant_context", fake_load_tenant_context)

    result = dependencies.get_tenant_context(tenant_id="tenant-1", session=session)

    assert result is expected


def test_get_tenant_context_missing_tenant_raises_http_exception(session, monkeypatch) -> None:
    def fake_load_tenant_context(*_args, **_kwargs):
        raise TenantNotFoundError("Tenant tenant-404 not found")

    monkeypatch.setattr(dependencies, "load_tenant_context", fake_load_tenant_context)

    with pytest.raises(HTTPException) as exc_info:
        dependencies.get_tenant_context(tenant_id="tenant-404", session=session)

    exc = exc_info.value
    assert exc.status_code == status.HTTP_404_NOT_FOUND
    assert exc.detail == "Tenant tenant-404 not found"


def test_get_tenant_service_returns_service_instance(session, monkeypatch) -> None:
    class DummyTenantService:
        def __init__(self, db_session):
            self.db_session = db_session

    monkeypatch.setattr(dependencies, "TenantService", DummyTenantService)

    result = dependencies.get_tenant_service(session=session)

    assert isinstance(result, DummyTenantService)
    assert result.db_session is session


def test_get_invoice_service_binds_session_and_tenant(session, monkeypatch) -> None:
    tenant = TenantContext(tenant_id="tenant-1", tenant_name="Tenant One")

    class DummyInvoiceService:
        def __init__(self, db_session, context):
            self.db_session = db_session
            self.context = context

    monkeypatch.setattr(dependencies, "InvoiceService", DummyInvoiceService)

    result = dependencies.get_invoice_service(tenant=tenant, session=session)

    assert isinstance(result, DummyInvoiceService)
    assert result.db_session is session
    assert result.context is tenant


def test_get_bank_transaction_service_binds_session_and_tenant(session, monkeypatch) -> None:
    tenant = TenantContext(tenant_id="tenant-99", tenant_name="Tenant Ninety-Nine")

    class DummyBankTransactionService:
        def __init__(self, db_session, context):
            self.db_session = db_session
            self.context = context

    monkeypatch.setattr(dependencies, "BankTransactionService", DummyBankTransactionService)

    result = dependencies.get_bank_transaction_service(tenant=tenant, session=session)

    assert isinstance(result, DummyBankTransactionService)
    assert result.db_session is session
    assert result.context is tenant


def test_get_reconciliation_service_binds_session_and_tenant(session, monkeypatch) -> None:
    tenant = TenantContext(tenant_id="tenant-42", tenant_name="Tenant Forty-Two")

    class DummyReconciliationService:
        def __init__(self, db_session, context):
            self.db_session = db_session
            self.context = context

    monkeypatch.setattr(dependencies, "ReconciliationService", DummyReconciliationService)

    result = dependencies.get_reconciliation_service(tenant=tenant, session=session)

    assert isinstance(result, DummyReconciliationService)
    assert result.db_session is session
    assert result.context is tenant


def test_get_explanation_service_binds_session_and_tenant(session, monkeypatch) -> None:
    tenant = TenantContext(tenant_id="tenant-007", tenant_name="Tenant Seven")

    class DummyExplanationService:
        def __init__(self, db_session, context):
            self.db_session = db_session
            self.context = context

    monkeypatch.setattr(dependencies, "ExplanationService", DummyExplanationService)

    result = dependencies.get_explanation_service(tenant=tenant, session=session)

    assert isinstance(result, DummyExplanationService)
    assert result.db_session is session
    assert result.context is tenant


def test_get_invoice_filters_returns_identity() -> None:
    params = InvoiceFilterParams()

    result = dependencies.get_invoice_filters(params)

    assert result is params
