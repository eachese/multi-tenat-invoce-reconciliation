"""Repository for match candidate entities."""
from __future__ import annotations

from sqlalchemy import Select, delete, select

from app.core.tenant import TenantContext
from app.db.models import MatchCandidate, MatchStatus

from .base import TenantScopedRepository


class MatchRepository(TenantScopedRepository[MatchCandidate]):
    """Match candidate persistence helpers."""

    model = MatchCandidate

    def list_proposed(self, tenant: TenantContext) -> list[MatchCandidate]:
        statement: Select[tuple[MatchCandidate]] = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.status == MatchStatus.PROPOSED)  # type: ignore[attr-defined]
        )
        return self.session.scalars(statement).all()

    def clear_proposed(self, tenant: TenantContext) -> None:
        statement = (
            delete(self.model)
            .where(self.model.tenant_id == tenant.tenant_id)
            .where(self.model.status == MatchStatus.PROPOSED)
        )
        self.session.execute(statement)
        self.session.flush()

    def reject_other_matches(self, tenant: TenantContext, invoice_id: str, exclude_match_id: str) -> None:
        statement = (
            select(self.model)
            .where(self.model.tenant_id == tenant.tenant_id)
            .where(self.model.invoice_id == invoice_id)
            .where(self.model.id != exclude_match_id)
            .where(self.model.status == MatchStatus.PROPOSED)
        )
        for candidate in self.session.scalars(statement).all():
            candidate.status = MatchStatus.REJECTED

    def existing_pairs(self, tenant: TenantContext) -> set[tuple[str, str]]:
        statement = (
            select(self.model.invoice_id, self.model.bank_transaction_id)
            .where(self.model.tenant_id == tenant.tenant_id)
        )
        return {(row[0], row[1]) for row in self.session.execute(statement)}

    def confirmed_invoice_ids(self, tenant: TenantContext) -> set[str]:
        statement = (
            select(self.model.invoice_id)
            .where(self.model.tenant_id == tenant.tenant_id)
            .where(self.model.status == MatchStatus.CONFIRMED)
        )
        return {row[0] for row in self.session.execute(statement)}

    def confirmed_transaction_ids(self, tenant: TenantContext) -> set[str]:
        statement = (
            select(self.model.bank_transaction_id)
            .where(self.model.tenant_id == tenant.tenant_id)
            .where(self.model.status == MatchStatus.CONFIRMED)
        )
        return {row[0] for row in self.session.execute(statement)}

    def get_by_invoice_transaction(
        self,
        tenant: TenantContext,
        invoice_id: str,
        bank_transaction_id: str,
    ) -> MatchCandidate | None:
        statement: Select[tuple[MatchCandidate]] = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.invoice_id == invoice_id)  # type: ignore[attr-defined]
            .where(self.model.bank_transaction_id == bank_transaction_id)  # type: ignore[attr-defined]
        )
        return self.session.scalar(statement)

    def list_for_tenant_with_status(
        self, tenant: TenantContext, status: MatchStatus | None = None
    ) -> list[MatchCandidate]:
        statement: Select[tuple[MatchCandidate]] = (
            self._base_query().where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
        )
        if status is not None:
            statement = statement.where(self.model.status == status)  # type: ignore[attr-defined]
        return self.session.scalars(statement).all()
