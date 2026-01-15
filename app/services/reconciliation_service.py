"""Reconciliation service implementing deterministic matching logic."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db.models import MatchCandidate, MatchStatus, InvoiceStatus
from app.repositories.bank_transaction import BankTransactionRepository
from app.repositories.invoice import InvoiceRepository
from app.repositories.match import MatchRepository
from app.schemas.match import MatchCandidateRead, MatchConfirmationResponse, ReconciliationResponse
from app.services.scoring import format_reasoning, score_match

from .exceptions import ConflictError, NotFoundError


class ReconciliationService:
    """Orchestrates reconciliation engine and match lifecycle."""

    SCORE_THRESHOLD = 0.45
    CANDIDATES_PER_INVOICE = 3

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self.session = session
        self.tenant = tenant
        self.invoices = InvoiceRepository(session)
        self.transactions = BankTransactionRepository(session)
        self.matches = MatchRepository(session)

    def reconcile(self) -> ReconciliationResponse:
        """Run deterministic reconciliation and return proposed matches."""

        open_invoices = self.invoices.list_open_invoices(self.tenant)
        candidate_transactions = self.transactions.list_for_invoice_matching(self.tenant)

        if not open_invoices or not candidate_transactions:
            return self._clear_and_return_empty()

        confirmed_invoice_ids = self.matches.confirmed_invoice_ids(self.tenant)
        confirmed_transaction_ids = self.matches.confirmed_transaction_ids(self.tenant)
        existing_pairs = self.matches.existing_pairs(self.tenant)

        self.matches.clear_proposed(self.tenant)

        proposed_entities = self._build_proposed_entities(
            open_invoices,
            candidate_transactions,
            confirmed_invoice_ids,
            confirmed_transaction_ids,
            existing_pairs,
        )

        if not proposed_entities:
            self.session.commit()
            return ReconciliationResponse(matches=[])

        for entity in proposed_entities:
            self.session.add(entity)
        self.session.commit()
        for entity in proposed_entities:
            self.session.refresh(entity)

        return ReconciliationResponse(
            matches=[MatchCandidateRead.model_validate(candidate) for candidate in proposed_entities]
        )

    def _clear_and_return_empty(self) -> ReconciliationResponse:
        self.matches.clear_proposed(self.tenant)
        self.session.commit()
        return ReconciliationResponse(matches=[])

    def _build_proposed_entities(
        self,
        invoices,
        transactions,
        confirmed_invoice_ids: set[str],
        confirmed_transaction_ids: set[str],
        existing_pairs: set[tuple[str, str]],
    ) -> list[MatchCandidate]:
        candidate_pool: list[tuple[float, MatchCandidate]] = []

        for invoice in invoices:
            if invoice.id in confirmed_invoice_ids:
                continue

            per_invoice_candidates: list[tuple[float, MatchCandidate]] = []
            for transaction in transactions:
                if transaction.id in confirmed_transaction_ids:
                    continue
                if (invoice.id, transaction.id) in existing_pairs:
                    continue

                match_score = score_match(invoice, transaction)
                if match_score.total < self.SCORE_THRESHOLD:
                    continue

                candidate = MatchCandidate(
                    tenant_id=self.tenant.tenant_id,
                    invoice_id=invoice.id,
                    bank_transaction_id=transaction.id,
                    score=Decimal(str(match_score.total)),
                    status=MatchStatus.PROPOSED,
                    reasoning=format_reasoning(match_score),
                )
                per_invoice_candidates.append((match_score.total, candidate))

            if per_invoice_candidates:
                per_invoice_candidates.sort(key=lambda item: item[0], reverse=True)
                candidate_pool.extend(per_invoice_candidates[: self.CANDIDATES_PER_INVOICE])

        if not candidate_pool:
            return []

        sorted_pool = sorted(candidate_pool, key=lambda item: item[0], reverse=True)
        used_transactions = set(confirmed_transaction_ids)
        per_invoice_counts: dict[str, int] = {}
        selected: list[MatchCandidate] = []

        for score_value, candidate in sorted_pool:
            invoice_id = candidate.invoice_id
            txn_id = candidate.bank_transaction_id

            if txn_id in used_transactions:
                continue
            if per_invoice_counts.get(invoice_id, 0) >= self.CANDIDATES_PER_INVOICE:
                continue

            selected.append(candidate)
            used_transactions.add(txn_id)
            per_invoice_counts[invoice_id] = per_invoice_counts.get(invoice_id, 0) + 1

        return selected

    def confirm_match(self, match_id: str) -> MatchConfirmationResponse:
        """Confirm a proposed match, updating invoice state and rejecting others."""

        match = self.matches.get_for_tenant(self.tenant, match_id)
        if match is None:
            raise NotFoundError("Match not found")
        if match.status != MatchStatus.PROPOSED:
            raise ConflictError("Only proposed matches can be confirmed")

        match.status = MatchStatus.CONFIRMED
        invoice = match.invoice
        invoice.status = InvoiceStatus.MATCHED

        self.matches.reject_other_matches(self.tenant, match.invoice_id, match.id)

        self.session.commit()
        self.session.refresh(match)
        self.session.refresh(invoice)

        return MatchConfirmationResponse(
            match=MatchCandidateRead.model_validate(match),
            invoice_status=invoice.status.value,
        )

    def list_matches(self, status: MatchStatus | None = None) -> list[MatchCandidateRead]:
        rows = self.matches.list_for_tenant_with_status(self.tenant, status=status)
        return [MatchCandidateRead.model_validate(row) for row in rows]
