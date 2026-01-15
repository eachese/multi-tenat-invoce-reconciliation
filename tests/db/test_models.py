"""Tests covering ORM models in app.db.models."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import models


def test_tenant_relationship_collections(session, tenant) -> None:
    """Persisted child entities should appear in tenant relationship collections."""
    vendor = models.Vendor(name="Acme Corp", tenant_id=tenant.id)
    bank_tx = models.BankTransaction(
        tenant_id=tenant.id,
        external_id="tx-1",
        posted_at=datetime.now(timezone.utc),
        amount=Decimal("250.00"),
        currency="USD",
    )
    session.add_all([vendor, bank_tx])
    session.commit()
    session.refresh(tenant)

    assert vendor in tenant.vendors
    assert bank_tx in tenant.bank_transactions


def test_invoice_defaults(session, tenant) -> None:
    """Invoice should populate default currency and status."""
    invoice = models.Invoice(
        tenant_id=tenant.id,
        vendor_id=None,
        amount=Decimal("100.00"),
        invoice_number="INV-001",
    )
    session.add(invoice)
    session.commit()
    session.refresh(invoice)

    assert invoice.currency == models.DEFAULT_CURRENCY
    assert invoice.status is models.InvoiceStatus.OPEN


def test_match_candidate_relationships_and_default_status(session, tenant) -> None:
    """MatchCandidate should link invoice and bank transaction with default status."""
    vendor = models.Vendor(name="Vendor", tenant_id=tenant.id)
    invoice = models.Invoice(
        tenant_id=tenant.id,
        vendor=vendor,
        amount=Decimal("42.00"),
        invoice_number="INV-002",
        invoice_date=datetime.now().date(),
    )
    bank_tx = models.BankTransaction(
        tenant_id=tenant.id,
        posted_at=datetime.now(timezone.utc),
        amount=Decimal("42.00"),
        currency="USD",
        external_id="tx-2",
    )
    match = models.MatchCandidate(
        tenant_id=tenant.id,
        invoice=invoice,
        bank_transaction=bank_tx,
        score=Decimal("0.9876"),
    )
    session.add_all([match])
    session.commit()
    session.refresh(match)

    assert match.status is models.MatchStatus.PROPOSED
    assert match.invoice is invoice
    assert match.bank_transaction is bank_tx
    assert match in invoice.matches
    assert match in bank_tx.matches


def test_bank_transaction_external_id_unique_per_tenant(session, tenant) -> None:
    """Duplicate external IDs within a tenant should raise an integrity error."""
    session.add(
        models.BankTransaction(
            tenant_id=tenant.id,
            external_id="tx-duplicate",
            posted_at=datetime.now(timezone.utc),
            amount=Decimal("10.00"),
            currency="USD",
        )
    )
    session.commit()

    session.add(
        models.BankTransaction(
            tenant_id=tenant.id,
            external_id="tx-duplicate",
            posted_at=datetime.now(timezone.utc),
            amount=Decimal("10.00"),
            currency="USD",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_idempotency_key_unique_constraint(session, tenant) -> None:
    """IdempotencyKey enforces uniqueness per tenant, endpoint, and key."""
    session.add(
        models.IdempotencyKey(
            tenant_id=tenant.id,
            key="k-123",
            endpoint="/api/resource",
            payload_hash="hash",
            response_status=201,
            response_body={"ok": True},
        )
    )
    session.commit()

    session.add(
        models.IdempotencyKey(
            tenant_id=tenant.id,
            key="k-123",
            endpoint="/api/resource",
            payload_hash="hash",
            response_status=201,
            response_body={"ok": True},
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_invoice_status_enum_members() -> None:
    """Enum members should expose expected string values."""
    assert models.InvoiceStatus.OPEN.value == "open"
    assert models.InvoiceStatus.MATCHED.value == "matched"
    assert models.InvoiceStatus.PAID.value == "paid"
    assert models.InvoiceStatus.CANCELLED.value == "cancelled"
