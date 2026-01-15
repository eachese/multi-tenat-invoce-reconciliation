"""Unit tests for invoice Pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.db.models import InvoiceStatus
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFilterParams,
    InvoiceListResponse,
    InvoiceRead,
)


def test_invoice_create_currency_normalized() -> None:
    payload = InvoiceCreate(amount=150.75, currency="eur", vendor_id="vendor-1")

    assert payload.currency == "EUR"
    assert payload.vendor_id == "vendor-1"
    assert payload.description is None


def test_invoice_create_rejects_non_positive_amount() -> None:
    with pytest.raises(ValidationError) as exc:
        InvoiceCreate(amount=0, currency="USD")

    assert "Input should be greater than 0" in str(exc.value)


def test_invoice_create_invoice_number_length_constraint() -> None:
    with pytest.raises(ValidationError) as exc:
        InvoiceCreate(amount=50, currency="USD", invoice_number="x" * 65)

    assert "String should have at most 64 characters" in str(exc.value)


def test_invoice_read_from_attributes() -> None:
    class InvoiceRecord:
        def __init__(self) -> None:
            self.id = "inv-1"
            self.tenant_id = "tenant-123"
            self.vendor_id = None
            self.invoice_number = "2025-001"
            self.amount = 125.5
            self.currency = "USD"
            self.invoice_date = date(2025, 1, 5)
            self.description = "Consulting"
            self.status = InvoiceStatus.OPEN
            self.created_at = datetime(2025, 1, 6, tzinfo=timezone.utc)

    record = InvoiceRecord()
    invoice = InvoiceRead.model_validate(record)

    assert invoice.id == record.id
    assert invoice.status is InvoiceStatus.OPEN
    assert invoice.created_at == record.created_at


def test_invoice_filter_params_validate_amount_bounds() -> None:
    params = InvoiceFilterParams(
        status=InvoiceStatus.PAID,
        vendor_id="vendor-123",
        min_amount=10,
        max_amount=500,
    )

    assert params.status is InvoiceStatus.PAID
    assert params.min_amount == 10
    assert params.max_amount == 500


def test_invoice_filter_params_rejects_negative_amounts() -> None:
    with pytest.raises(ValidationError):
        InvoiceFilterParams(min_amount=-1)

    with pytest.raises(ValidationError):
        InvoiceFilterParams(max_amount=-5)


def test_invoice_list_response_round_trips_items() -> None:
    invoice = InvoiceRead(
        id="inv-99",
        tenant_id="tenant-xyz",
        vendor_id=None,
        invoice_number="INV-99",
        amount=320.45,
        currency="USD",
        invoice_date=date(2025, 2, 1),
        description="Research services",
        status=InvoiceStatus.MATCHED,
        created_at=datetime(2025, 2, 2, tzinfo=timezone.utc),
    )

    response = InvoiceListResponse(items=[invoice], total=1)

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].id == invoice.id
