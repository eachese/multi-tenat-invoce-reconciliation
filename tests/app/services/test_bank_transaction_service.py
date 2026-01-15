"""Unit tests for the bank transaction service."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db.models import BankTransaction, IdempotencyKey
from app.schemas.bank_transaction import (
    BankTransactionImportItem,
    BankTransactionImportRequest,
    BankTransactionImportResponse,
)
from app.services.bank_transaction_service import BankTransactionService
from app.services.exceptions import ConflictError, ValidationError
from app.utils.hash import stable_hash


@pytest.fixture()
def tenant_context(tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)


@pytest.fixture()
def service(session: Session, tenant_context: TenantContext) -> BankTransactionService:
    return BankTransactionService(session, tenant_context)


def _build_item(
    external_id: str | None,
    amount: float,
    description: str,
    posted_at: datetime | None = None,
) -> BankTransactionImportItem:
    return BankTransactionImportItem(
        external_id=external_id,
        posted_at=posted_at or datetime.now(tz=timezone.utc),
        amount=amount,
        currency="usd",
        description=description,
    )


def test_import_transactions_requires_idempotency_key(service: BankTransactionService) -> None:
    request = BankTransactionImportRequest(transactions=[_build_item("txn-1", 15.0, "First")])

    with pytest.raises(ValidationError):
        service.import_transactions(request, idempotency_key=None)


def test_import_transactions_returns_existing_idempotent_response(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    request = BankTransactionImportRequest(transactions=[_build_item("txn-1", 15.0, "First")])
    stored_response = BankTransactionImportResponse(
        created=0, duplicates=0, conflicts=0, transactions=[]
    )
    payload_hash = stable_hash([item.model_dump() for item in request.transactions])
    record = IdempotencyKey(
        tenant_id=tenant_context.tenant_id,
        endpoint=BankTransactionService.IDEMPOTENCY_ENDPOINT,
        key="key-123",
        payload_hash=payload_hash,
        response_status=200,
        response_body=stored_response.model_dump(),
    )
    session.add(record)
    session.commit()

    result = service.import_transactions(request, idempotency_key="key-123")

    assert result.model_dump() == stored_response.model_dump()


def test_import_transactions_persists_transactions_and_records_idempotency(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    request = BankTransactionImportRequest(transactions=[_build_item("txn-1", 99.5, "Fresh")])

    response = service.import_transactions(request, idempotency_key="batch-001")

    assert response.created == 1
    assert response.duplicates == 0
    assert response.conflicts == 0
    payload_hash = stable_hash([item.model_dump() for item in request.transactions])

    rows = session.scalars(
        select(BankTransaction).where(BankTransaction.tenant_id == tenant_context.tenant_id)
    ).all()
    assert len(rows) == 1
    entity = rows[0]
    assert entity.external_id == "txn-1"
    assert entity.currency == "USD"

    idempotency_record = session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.key == "batch-001")
    )
    assert idempotency_record is not None
    assert idempotency_record.payload_hash == payload_hash
    assert idempotency_record.response_body == response.model_dump()


def test_import_transactions_counts_existing_duplicates(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    existing = BankTransaction(
        tenant_id=tenant_context.tenant_id,
        external_id="txn-duplicate",
        posted_at=datetime.now(tz=timezone.utc),
        amount=Decimal("25.00"),
        currency="USD",
        description="Existing",
    )
    session.add(existing)
    session.commit()

    request = BankTransactionImportRequest(
        transactions=[
            _build_item("txn-duplicate", 40.0, "Duplicate"),
            _build_item("txn-new", 75.0, "Inserted"),
        ]
    )

    response = service.import_transactions(request, idempotency_key="batch-duplicates")

    assert response.created == 1
    assert response.duplicates == 1
    rows = session.scalars(select(BankTransaction)).all()
    assert len(rows) == 2
    assert any(row.external_id == "txn-new" for row in rows)


def test_import_transactions_rejects_payload_mismatch(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    original_request = BankTransactionImportRequest(
        transactions=[_build_item("txn-1", 10.0, "Original")]
    )
    payload_hash = stable_hash([item.model_dump() for item in original_request.transactions])
    record = IdempotencyKey(
        tenant_id=tenant_context.tenant_id,
        endpoint=BankTransactionService.IDEMPOTENCY_ENDPOINT,
        key="batch-777",
        payload_hash=payload_hash,
        response_status=200,
        response_body=BankTransactionImportResponse(
            created=1, duplicates=0, conflicts=0, transactions=[]
        ).model_dump(),
    )
    session.add(record)
    session.commit()

    different_request = BankTransactionImportRequest(
        transactions=[_build_item("txn-1", 20.0, "Different amount")]
    )

    with pytest.raises(ConflictError):
        service.import_transactions(different_request, idempotency_key="batch-777")


def test_import_transactions_rolls_back_on_integrity_error(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    request = BankTransactionImportRequest(
        transactions=[
            _build_item("txn-dup", 30.0, "First"),
            _build_item("txn-dup", 31.0, "Second"),
        ]
    )

    with pytest.raises(ConflictError):
        service.import_transactions(request, idempotency_key="batch-conflict")

    transactions = session.scalars(select(BankTransaction)).all()
    assert transactions == []
    idempotency_records = session.scalars(select(IdempotencyKey)).all()
    assert idempotency_records == []


def test_list_transactions_returns_serialized_rows(
    service: BankTransactionService,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    tx_one = BankTransaction(
        tenant_id=tenant_context.tenant_id,
        external_id="txn-a",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        amount=Decimal("50.00"),
        currency="USD",
        description="Payment A",
    )
    tx_two = BankTransaction(
        tenant_id=tenant_context.tenant_id,
        external_id="txn-b",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        amount=Decimal("75.00"),
        currency="USD",
        description="Payment B",
    )
    session.add_all([tx_one, tx_two])
    session.commit()

    result = service.list_transactions()

    assert {item.id for item in result} == {tx_one.id, tx_two.id}
    assert all(item.tenant_id == tenant_context.tenant_id for item in result)
