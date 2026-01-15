"""Unit tests for match repository tenant isolation and helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db import models
from app.db.models import MatchCandidate, MatchStatus
from app.repositories.match import MatchRepository

TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEFAULT_SCORE = Decimal("0.9000")


def _tenant_context(tenant: models.Tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)


def _save(session: Session, *entities: models.Base) -> None:
    session.add_all(entities)
    session.commit()
    for entity in entities:
        session.refresh(entity)


def _create_invoice(session: Session, tenant: models.Tenant, invoice_id: str) -> models.Invoice:
    invoice = models.Invoice(
        id=invoice_id,
        tenant_id=tenant.id,
        amount=Decimal("10.00"),
        currency="USD",
        invoice_number=f"{invoice_id}-num",
    )
    _save(session, invoice)
    return invoice


def _create_bank_transaction(session: Session, tenant: models.Tenant, transaction_id: str) -> models.BankTransaction:
    transaction = models.BankTransaction(
        id=transaction_id,
        tenant_id=tenant.id,
        posted_at=TIMESTAMP,
        amount=Decimal("10.00"),
        currency="USD",
        external_id=f"{transaction_id}-ext",
    )
    _save(session, transaction)
    return transaction


def _create_match(
    session: Session,
    tenant: models.Tenant,
    invoice: models.Invoice,
    transaction: models.BankTransaction,
    *,
    status: MatchStatus = MatchStatus.PROPOSED,
) -> models.MatchCandidate:
    match = models.MatchCandidate(
        tenant_id=tenant.id,
        invoice=invoice,
        bank_transaction=transaction,
        score=DEFAULT_SCORE,
        status=status,
        reasoning="auto-generated",
    )
    _save(session, match)
    return match


def test_list_proposed_returns_only_proposed_for_tenant(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    proposed_match = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-proposed"),
        _create_bank_transaction(session, tenant, "txn-proposed"),
    )
    _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-confirmed"),
        _create_bank_transaction(session, tenant, "txn-confirmed"),
        status=MatchStatus.CONFIRMED,
    )

    other_tenant = models.Tenant(name="Other Tenant")
    _save(session, other_tenant)
    _create_match(
        session,
        other_tenant,
        _create_invoice(session, other_tenant, "inv-other"),
        _create_bank_transaction(session, other_tenant, "txn-other"),
    )

    results = repo.list_proposed(tenant_ctx)

    assert {match.id for match in results} == {proposed_match.id}
    assert all(match.status is MatchStatus.PROPOSED for match in results)
    assert all(match.tenant_id == tenant.id for match in results)


def test_clear_proposed_removes_only_proposed_candidates(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    proposed = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-to-remove"),
        _create_bank_transaction(session, tenant, "txn-to-remove"),
    )
    confirmed = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-keep"),
        _create_bank_transaction(session, tenant, "txn-keep"),
        status=MatchStatus.CONFIRMED,
    )

    repo.clear_proposed(tenant_ctx)

    assert session.get(MatchCandidate, proposed.id) is None
    assert session.get(MatchCandidate, confirmed.id) is not None


def test_reject_other_matches_marks_remaining_as_rejected(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    shared_invoice = _create_invoice(session, tenant, "inv-shared")
    keep_match = _create_match(
        session,
        tenant,
        shared_invoice,
        _create_bank_transaction(session, tenant, "txn-keep"),
    )
    to_reject = _create_match(
        session,
        tenant,
        shared_invoice,
        _create_bank_transaction(session, tenant, "txn-reject"),
    )
    confirmed = _create_match(
        session,
        tenant,
        shared_invoice,
        _create_bank_transaction(session, tenant, "txn-confirmed"),
        status=MatchStatus.CONFIRMED,
    )

    other_tenant = models.Tenant(name="Other Tenant For Reject")
    _save(session, other_tenant)
    other_match = _create_match(
        session,
        other_tenant,
        _create_invoice(session, other_tenant, "inv-other-shared"),
        _create_bank_transaction(session, other_tenant, "txn-other-shared"),
    )

    repo.reject_other_matches(tenant_ctx, invoice_id=shared_invoice.id, exclude_match_id=keep_match.id)
    session.flush()
    session.refresh(keep_match)
    session.refresh(to_reject)
    session.refresh(confirmed)
    session.refresh(other_match)

    assert keep_match.status is MatchStatus.PROPOSED
    assert to_reject.status is MatchStatus.REJECTED
    assert confirmed.status is MatchStatus.CONFIRMED
    assert other_match.status is MatchStatus.PROPOSED


def test_existing_pairs_returns_invoice_transaction_pairs(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    first_match = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-1"),
        _create_bank_transaction(session, tenant, "txn-1"),
    )
    second_match = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-2"),
        _create_bank_transaction(session, tenant, "txn-2"),
    )

    other_tenant = models.Tenant(name="Pairs Tenant")
    _save(session, other_tenant)
    _create_match(
        session,
        other_tenant,
        _create_invoice(session, other_tenant, "inv-x"),
        _create_bank_transaction(session, other_tenant, "txn-x"),
    )

    pairs = repo.existing_pairs(tenant_ctx)

    assert pairs == {
        (first_match.invoice_id, first_match.bank_transaction_id),
        (second_match.invoice_id, second_match.bank_transaction_id),
    }


def test_confirmed_id_helpers_return_only_tenant_confirmed_records(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    confirmed_one = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-confirm-1"),
        _create_bank_transaction(session, tenant, "txn-confirm-1"),
        status=MatchStatus.CONFIRMED,
    )
    confirmed_two = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-confirm-2"),
        _create_bank_transaction(session, tenant, "txn-confirm-2"),
        status=MatchStatus.CONFIRMED,
    )
    _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-proposed"),
        _create_bank_transaction(session, tenant, "txn-proposed"),
    )

    other_tenant = models.Tenant(name="Confirmed Tenant")
    _save(session, other_tenant)
    _create_match(
        session,
        other_tenant,
        _create_invoice(session, other_tenant, "inv-other"),
        _create_bank_transaction(session, other_tenant, "txn-other"),
        status=MatchStatus.CONFIRMED,
    )

    invoice_ids = repo.confirmed_invoice_ids(tenant_ctx)
    transaction_ids = repo.confirmed_transaction_ids(tenant_ctx)

    assert invoice_ids == {confirmed_one.invoice_id, confirmed_two.invoice_id}
    assert transaction_ids == {confirmed_one.bank_transaction_id, confirmed_two.bank_transaction_id}


def test_list_for_tenant_with_status_filters_when_requested(session: Session, tenant: models.Tenant) -> None:
    repo = MatchRepository(session)
    tenant_ctx = _tenant_context(tenant)

    proposed = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-tenant-proposed"),
        _create_bank_transaction(session, tenant, "txn-tenant-proposed"),
    )
    confirmed = _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-tenant-confirmed"),
        _create_bank_transaction(session, tenant, "txn-tenant-confirmed"),
        status=MatchStatus.CONFIRMED,
    )
    _create_match(
        session,
        tenant,
        _create_invoice(session, tenant, "inv-tenant-rejected"),
        _create_bank_transaction(session, tenant, "txn-tenant-rejected"),
        status=MatchStatus.REJECTED,
    )

    other_tenant = models.Tenant(name="List Status Tenant")
    _save(session, other_tenant)
    _create_match(
        session,
        other_tenant,
        _create_invoice(session, other_tenant, "inv-other-list"),
        _create_bank_transaction(session, other_tenant, "txn-other-list"),
        status=MatchStatus.CONFIRMED,
    )

    all_matches = repo.list_for_tenant_with_status(tenant_ctx)
    confirmed_only = repo.list_for_tenant_with_status(tenant_ctx, status=MatchStatus.CONFIRMED)

    assert {match.id for match in all_matches} == {m.id for m in [proposed, confirmed]}
    assert {match.id for match in confirmed_only} == {confirmed.id}
