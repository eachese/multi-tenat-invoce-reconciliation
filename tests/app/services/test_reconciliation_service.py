"""Unit tests for the reconciliation service."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.tenant import TenantContext
from app.db.models import (
    BankTransaction,
    Invoice,
    InvoiceStatus,
    MatchCandidate,
    MatchStatus,
)
from app.services.exceptions import ConflictError, NotFoundError
from app.services.reconciliation_service import ReconciliationService


def create_service(session, tenant) -> ReconciliationService:
    """Instantiate the reconciliation service for a tenant."""

    context = TenantContext(tenant_id=str(tenant.id), tenant_name=tenant.name)
    return ReconciliationService(session, context)


def create_invoice(
    session,
    tenant_id: str,
    *,
    amount: Decimal | float = Decimal("100.00"),
    status: InvoiceStatus = InvoiceStatus.OPEN,
    description: str = "Consulting Services",
    invoice_date=None,
) -> Invoice:
    invoice = Invoice(
        tenant_id=tenant_id,
        amount=Decimal(str(amount)),
        currency="USD",
        status=status,
        description=description,
        invoice_date=invoice_date or datetime.now(timezone.utc).date(),
    )
    session.add(invoice)
    session.flush()
    return invoice


def create_transaction(
    session,
    tenant_id: str,
    *,
    amount: Decimal | float = Decimal("100.00"),
    description: str = "Consulting Services",
    posted_at=None,
    external_id: str | None = None,
) -> BankTransaction:
    transaction = BankTransaction(
        tenant_id=tenant_id,
        amount=Decimal(str(amount)),
        currency="USD",
        description=description,
        posted_at=posted_at or datetime.now(timezone.utc),
        external_id=external_id,
    )
    session.add(transaction)
    session.flush()
    return transaction


def create_match(
    session,
    tenant_id: str,
    invoice: Invoice,
    transaction: BankTransaction,
    *,
    status: MatchStatus = MatchStatus.PROPOSED,
    score: Decimal | float = Decimal("0.9"),
    reasoning: str = "high confidence",
) -> MatchCandidate:
    match = MatchCandidate(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        bank_transaction_id=transaction.id,
        score=Decimal(str(score)),
        status=status,
        reasoning=reasoning,
    )
    session.add(match)
    session.flush()
    return match


def test_reconcile_clears_proposed_when_no_open_invoices(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice = create_invoice(
        session,
        tenant.id,
        status=InvoiceStatus.MATCHED,
        description="Closed engagement",
    )
    transaction = create_transaction(session, tenant.id, description="Closed engagement")
    create_match(session, tenant.id, invoice, transaction, status=MatchStatus.PROPOSED)

    result = service.reconcile()

    assert result.matches == []
    remaining = session.scalars(select(MatchCandidate)).all()
    assert remaining == []


def test_reconcile_generates_candidates_respecting_per_invoice_limit(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice_date = datetime(2024, 1, 1, tzinfo=timezone.utc).date()
    invoice = create_invoice(
        session,
        tenant.id,
        amount=Decimal("150.00"),
        description="Implementation retainer",
        invoice_date=invoice_date,
    )

    for idx in range(4):
        create_transaction(
            session,
            tenant.id,
            amount=Decimal("150.00"),
            description="Implementation retainer",
            posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            external_id=f"txn-{idx}",
        )

    response = service.reconcile()

    assert len(response.matches) == 3
    invoice_ids = {match.invoice_id for match in response.matches}
    txn_ids = {match.bank_transaction_id for match in response.matches}
    assert invoice_ids == {invoice.id}
    assert len(txn_ids) == 3

    persisted = session.scalars(select(MatchCandidate).where(MatchCandidate.status == MatchStatus.PROPOSED)).all()
    assert len(persisted) == 3


def test_reconcile_skips_confirmed_invoices_and_transactions(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice_date = datetime(2024, 2, 1, tzinfo=timezone.utc).date()
    invoice_one = create_invoice(session, tenant.id, description="Retained services", invoice_date=invoice_date)
    invoice_two = create_invoice(session, tenant.id, amount=Decimal("275.00"), description="Quarterly billing", invoice_date=invoice_date)

    transaction_one = create_transaction(
        session,
        tenant.id,
        description="Retained services",
        posted_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        external_id="txn-confirmed",
    )
    transaction_two = create_transaction(
        session,
        tenant.id,
        amount=Decimal("275.00"),
        description="Quarterly billing",
        posted_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        external_id="txn-open",
    )

    create_match(
        session,
        tenant.id,
        invoice_one,
        transaction_one,
        status=MatchStatus.CONFIRMED,
        reasoning="already confirmed",
    )

    response = service.reconcile()

    assert len(response.matches) == 1
    match = response.matches[0]
    assert match.invoice_id == invoice_two.id
    assert match.bank_transaction_id == transaction_two.id

    proposed = session.scalars(
        select(MatchCandidate).where(MatchCandidate.invoice_id == invoice_one.id, MatchCandidate.status == MatchStatus.PROPOSED)
    ).all()
    assert proposed == []


def test_confirm_match_updates_invoice_and_rejects_others(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice = create_invoice(session, tenant.id, description="Advisory services")
    preferred_transaction = create_transaction(session, tenant.id, description="Advisory services", external_id="txn-primary")
    secondary_transaction = create_transaction(session, tenant.id, description="Advisory services", external_id="txn-secondary")

    winning_match = create_match(session, tenant.id, invoice, preferred_transaction)
    losing_match = create_match(session, tenant.id, invoice, secondary_transaction)

    confirmation = service.confirm_match(winning_match.id)

    assert confirmation.match.id == winning_match.id
    assert confirmation.invoice_status == InvoiceStatus.MATCHED.value

    refreshed_invoice = session.get(Invoice, invoice.id)
    assert refreshed_invoice.status == InvoiceStatus.MATCHED

    confirmed = session.get(MatchCandidate, winning_match.id)
    rejected = session.get(MatchCandidate, losing_match.id)
    assert confirmed.status == MatchStatus.CONFIRMED
    assert rejected.status == MatchStatus.REJECTED


def test_confirm_match_raises_not_found_for_unknown_id(session, tenant) -> None:
    service = create_service(session, tenant)

    with pytest.raises(NotFoundError):
        service.confirm_match("missing-id")


def test_confirm_match_requires_proposed_status(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice = create_invoice(session, tenant.id, description="Research retainer")
    transaction = create_transaction(session, tenant.id, description="Research retainer", external_id="txn-confirmed")
    match = create_match(
        session,
        tenant.id,
        invoice,
        transaction,
        status=MatchStatus.CONFIRMED,
        reasoning="already processed",
    )

    with pytest.raises(ConflictError):
        service.confirm_match(match.id)


def test_list_matches_supports_status_filter(session, tenant) -> None:
    service = create_service(session, tenant)

    invoice = create_invoice(session, tenant.id, description="Subscription")
    transaction_one = create_transaction(session, tenant.id, description="Subscription", external_id="txn-one")
    transaction_two = create_transaction(session, tenant.id, description="Subscription", external_id="txn-two")

    create_match(session, tenant.id, invoice, transaction_one, status=MatchStatus.PROPOSED)
    create_match(session, tenant.id, invoice, transaction_two, status=MatchStatus.CONFIRMED)

    all_matches = service.list_matches()
    assert {match.status for match in all_matches} == {MatchStatus.PROPOSED, MatchStatus.CONFIRMED}

    confirmed_matches = service.list_matches(MatchStatus.CONFIRMED)
    assert len(confirmed_matches) == 1
    assert confirmed_matches[0].status == MatchStatus.CONFIRMED
