"""Integration-style tests for core services."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.tenant import TenantContext
from app.db.base import Base
from app.schemas.bank_transaction import BankTransactionImportItem, BankTransactionImportRequest
from app.schemas.invoice import InvoiceCreate, InvoiceFilterParams
from app.schemas.tenant import TenantCreate
from app.services.bank_transaction_service import BankTransactionService
from app.services.exceptions import ConflictError
from app.services.invoice_service import InvoiceService
from app.services.reconciliation_service import ReconciliationService
from app.services.tenant_service import TenantService


@contextmanager
def in_memory_session() -> Session:
    """Yield a SQLAlchemy session backed by an in-memory SQLite database."""

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def create_tenant_context(session: Session, name: str = "Acme Corp") -> TenantContext:
    tenant_service = TenantService(session)
    tenant = tenant_service.create(TenantCreate(name=name))
    return TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)


def test_invoice_service_create_list_delete() -> None:
    with in_memory_session() as session:
        tenant_context = create_tenant_context(session)
        service = InvoiceService(session, tenant_context)

        created = service.create(InvoiceCreate(amount=125.5, currency="usd"))
        assert created.currency == "USD"

        response = service.list(InvoiceFilterParams(), offset=0, limit=10)
        assert response.total == 1
        assert response.items[0].id == created.id

        service.delete(created.id)
        after_delete = service.list(InvoiceFilterParams(), offset=0, limit=10)
        assert after_delete.total == 0


def test_bank_transaction_import_idempotent() -> None:
    with in_memory_session() as session:
        tenant_context = create_tenant_context(session)
        service = BankTransactionService(session, tenant_context)

        request = BankTransactionImportRequest(
            transactions=[
                BankTransactionImportItem(
                    external_id="txn-123",
                    posted_at=datetime.now(tz=timezone.utc),
                    amount=125.5,
                    currency="usd",
                    description="Invoice 1001",
                )
            ]
        )

        first = service.import_transactions(request, idempotency_key="batch-1")
        assert first.created == 1
        assert first.duplicates == 0

        second = service.import_transactions(request, idempotency_key="batch-1")
        assert second.created == 1
        assert second.transactions == first.transactions

        different_payload = BankTransactionImportRequest(
            transactions=[
                BankTransactionImportItem(
                    external_id="txn-123",
                    posted_at=datetime.now(tz=timezone.utc),
                    amount=300.0,
                    currency="usd",
                    description="Invoice 1002",
                )
            ]
        )

        with pytest.raises(ConflictError):
            service.import_transactions(different_payload, idempotency_key="batch-1")


def test_reconciliation_service_generates_and_confirms_match() -> None:
    with in_memory_session() as session:
        tenant_context = create_tenant_context(session)
        invoice_service = InvoiceService(session, tenant_context)
        bank_service = BankTransactionService(session, tenant_context)
        reconciliation_service = ReconciliationService(session, tenant_context)

        invoice = invoice_service.create(
            InvoiceCreate(
                amount=200.0,
                currency="usd",
                description="Consulting Services",
                invoice_date=datetime.now(tz=timezone.utc).date(),
            )
        )

        bank_service.import_transactions(
            BankTransactionImportRequest(
                transactions=[
                    BankTransactionImportItem(
                        external_id="txn-200",
                        posted_at=datetime.now(tz=timezone.utc),
                        amount=200.0,
                        currency="usd",
                        description="Consulting Services",
                    )
                ]
            ),
            idempotency_key="batch-2",
        )

        result = reconciliation_service.reconcile()
        assert len(result.matches) == 1
        match = result.matches[0]
        assert match.invoice_id == invoice.id

        confirmation = reconciliation_service.confirm_match(match.id)
        assert confirmation.invoice_status == "matched"

        repeat_result = reconciliation_service.reconcile()
        assert len(repeat_result.matches) == 0
