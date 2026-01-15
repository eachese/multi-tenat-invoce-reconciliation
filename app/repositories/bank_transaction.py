"""Repository for bank transaction entities."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Select, select

from app.core.tenant import TenantContext
from app.db.models import BankTransaction

from .base import TenantScopedRepository


class BankTransactionRepository(TenantScopedRepository[BankTransaction]):
    """Bank transaction repository with helper queries."""

    model = BankTransaction

    def get_by_external_ids(
        self, tenant: TenantContext, external_ids: Iterable[str]
    ) -> dict[str, BankTransaction]:
        ids = [eid for eid in external_ids if eid]
        if not ids:
            return {}
        statement = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.external_id.in_(ids))  # type: ignore[attr-defined]
        )
        rows = self.session.scalars(statement).all()
        return {row.external_id: row for row in rows if row.external_id}

    def list_for_invoice_matching(self, tenant: TenantContext) -> list[BankTransaction]:
        """Return bank transactions eligible for matching."""

        statement: Select[tuple[BankTransaction]] = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
        )
        return self.session.scalars(statement).all()

    def list_for_tenant(
        self,
        tenant: TenantContext,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BankTransaction]:
        statement: Select[tuple[BankTransaction]] = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()
