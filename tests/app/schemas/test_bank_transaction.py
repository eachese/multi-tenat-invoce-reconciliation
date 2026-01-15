"""Unit tests for bank transaction schemas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.bank_transaction import (
    BankTransactionImportItem,
    BankTransactionImportRequest,
    BankTransactionImportResponse,
    BankTransactionRead,
)


class DummyTransaction:
    def __init__(
        self,
        *,
        id: str,
        tenant_id: str,
        external_id: str | None,
        posted_at: datetime,
        amount: float,
        currency: str,
        description: str | None,
        created_at: datetime,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.external_id = external_id
        self.posted_at = posted_at
        self.amount = amount
        self.currency = currency
        self.description = description
        self.created_at = created_at


def test_bank_transaction_read_accepts_orm_object() -> None:
    posted_at = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    created_at = posted_at.replace(hour=13)
    instance = DummyTransaction(
        id="txn-1",
        tenant_id="tenant-123",
        external_id="ext-123",
        posted_at=posted_at,
        amount=125.75,
        currency="USD",
        description="Invoice 42",
        created_at=created_at,
    )

    parsed = BankTransactionRead.model_validate(instance)

    assert parsed.id == "txn-1"
    assert parsed.tenant_id == "tenant-123"
    assert parsed.external_id == "ext-123"
    assert parsed.posted_at == posted_at
    assert parsed.amount == pytest.approx(125.75)
    assert parsed.currency == "USD"
    assert parsed.description == "Invoice 42"
    assert parsed.created_at == created_at


def test_bank_transaction_import_item_defaults() -> None:
    posted_at = datetime.now(tz=timezone.utc)

    item = BankTransactionImportItem(posted_at=posted_at, amount=150.0)

    assert item.external_id is None
    assert item.currency == "USD"
    assert item.description is None
    assert item.posted_at == posted_at
    assert item.amount == pytest.approx(150.0)


@pytest.mark.parametrize("amount", [0.0, -10.5])
def test_bank_transaction_import_item_requires_positive_amount(amount: float) -> None:
    posted_at = datetime.now(tz=timezone.utc)

    with pytest.raises(ValidationError):
        BankTransactionImportItem(posted_at=posted_at, amount=amount)


@pytest.mark.parametrize("currency", ["US", "USDE"])
def test_bank_transaction_import_item_enforces_currency_length(currency: str) -> None:
    posted_at = datetime.now(tz=timezone.utc)

    with pytest.raises(ValidationError):
        BankTransactionImportItem(posted_at=posted_at, amount=15.0, currency=currency)


def test_bank_transaction_import_item_external_id_max_length() -> None:
    posted_at = datetime.now(tz=timezone.utc)
    external_id = "x" * 129

    with pytest.raises(ValidationError):
        BankTransactionImportItem(posted_at=posted_at, amount=25.0, external_id=external_id)


def test_bank_transaction_import_item_description_max_length() -> None:
    posted_at = datetime.now(tz=timezone.utc)
    description = "d" * 501

    with pytest.raises(ValidationError):
        BankTransactionImportItem(posted_at=posted_at, amount=25.0, description=description)


def test_bank_transaction_import_request_accepts_transactions() -> None:
    posted_at = datetime.now(tz=timezone.utc)
    items = [
        BankTransactionImportItem(
            external_id="ext-1",
            posted_at=posted_at,
            amount=100.0,
            currency="EUR",
            description="Invoice 1001",
        ),
        BankTransactionImportItem(
            posted_at=posted_at,
            amount=50.0,
        ),
    ]

    request = BankTransactionImportRequest(transactions=items)

    assert request.transactions == items


def test_bank_transaction_import_response_round_trip() -> None:
    posted_at = datetime(2025, 2, 10, 9, 30, tzinfo=timezone.utc)
    created_at = posted_at.replace(hour=10)
    transaction = BankTransactionRead(
        id="txn-100",
        tenant_id="tenant-42",
        external_id="ext-100",
        posted_at=posted_at,
        amount=200.5,
        currency="GBP",
        description="Payment for invoice 100",
        created_at=created_at,
    )

    response = BankTransactionImportResponse(
        created=1,
        duplicates=0,
        conflicts=0,
        transactions=[transaction],
    )

    assert response.created == 1
    assert response.duplicates == 0
    assert response.conflicts == 0
    assert len(response.transactions) == 1
    assert response.transactions[0].model_dump() == transaction.model_dump()


def test_bank_transaction_import_response_requires_valid_transactions() -> None:
    with pytest.raises(ValidationError):
        BankTransactionImportResponse(
            created=0,
            duplicates=0,
            conflicts=0,
            transactions=[{"tenant_id": "tenant-1"}],
        )
