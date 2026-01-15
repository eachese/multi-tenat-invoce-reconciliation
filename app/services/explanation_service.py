"""Service responsible for explaining reconciliation matches."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai.provider import ExplanationContext, fallback_client, resolve_ai_client
from app.core.settings import get_settings
from app.core.tenant import TenantContext
from app.db.models import BankTransaction, Invoice, MatchCandidate
from app.repositories.bank_transaction import BankTransactionRepository
from app.repositories.invoice import InvoiceRepository
from app.repositories.match import MatchRepository
from app.schemas.match import AIExplanationResponse
from app.services.scoring import format_reasoning, score_match

from .exceptions import NotFoundError


logger = logging.getLogger(__name__)


class ExplanationService:
    """Generate explainability output for reconciliation decisions."""

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self.session = session
        self.tenant = tenant
        self.matches = MatchRepository(session)
        self.invoices = InvoiceRepository(session)
        self.transactions = BankTransactionRepository(session)
        settings = get_settings()
        self.ai_client = resolve_ai_client(settings.ai_model, settings.ai_api_key)
        self.fallback = fallback_client()

    def explain_match(self, match_id: str) -> AIExplanationResponse:
        match = self._get_match(match_id)
        invoice = match.invoice
        bank_transaction = match.bank_transaction

        if invoice is None or bank_transaction is None:
            raise NotFoundError("Related invoice or bank transaction missing for match")

        reasoning = match.reasoning or self._generate_reasoning(invoice, bank_transaction)
        score_value = float(match.score)

        return self._explain_with_context(invoice, bank_transaction, reasoning, score_value)

    def explain_pair(self, invoice_id: str, bank_transaction_id: str) -> AIExplanationResponse:
        invoice = self._get_invoice(invoice_id)
        bank_transaction = self._get_transaction(bank_transaction_id)

        existing_match = self.matches.get_by_invoice_transaction(
            self.tenant, invoice_id=invoice_id, bank_transaction_id=bank_transaction_id
        )

        if existing_match is not None:
            reasoning = existing_match.reasoning or self._generate_reasoning(invoice, bank_transaction)
            score_value = float(existing_match.score)
        else:
            match_score = score_match(invoice, bank_transaction)
            reasoning = format_reasoning(match_score)
            score_value = float(match_score.total)

        return self._explain_with_context(invoice, bank_transaction, reasoning, score_value)

    def _get_match(self, match_id: str) -> MatchCandidate:
        match = self.matches.get_for_tenant(self.tenant, match_id)
        if match is None:
            raise NotFoundError("Match not found")
        return match

    def _get_invoice(self, invoice_id: str) -> Invoice:
        invoice = self.invoices.get_for_tenant(self.tenant, invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")
        return invoice

    def _get_transaction(self, bank_transaction_id: str) -> BankTransaction:
        transaction = self.transactions.get_for_tenant(self.tenant, bank_transaction_id)
        if transaction is None:
            raise NotFoundError("Bank transaction not found")
        return transaction

    def _generate_reasoning(self, invoice: Invoice, bank_transaction: BankTransaction) -> str:
        return format_reasoning(score_match(invoice, bank_transaction))

    def _explain_with_context(
        self,
        invoice: Invoice,
        bank_transaction: BankTransaction,
        reasoning: str,
        score_value: float,
    ) -> AIExplanationResponse:
        context = ExplanationContext(
            invoice_amount=float(invoice.amount),
            invoice_currency=invoice.currency,
            invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            invoice_description=invoice.description,
            vendor_name=getattr(getattr(invoice, "vendor", None), "name", None),
            transaction_amount=float(bank_transaction.amount),
            transaction_currency=bank_transaction.currency,
            transaction_date=bank_transaction.posted_at.isoformat(),
            transaction_description=bank_transaction.description,
            score=score_value,
            reasoning=reasoning,
        )

        explanation, confidence = self._generate_explanation(context)

        return AIExplanationResponse(explanation=explanation, confidence=confidence)

    def _generate_explanation(self, context: ExplanationContext) -> tuple[str, str | None]:
        if self.ai_client is None:
            return self.fallback.explain(context)

        try:
            return self.ai_client.explain(context)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("AI explanation failed; falling back: %s", exc)
            return self.fallback.explain(context)
