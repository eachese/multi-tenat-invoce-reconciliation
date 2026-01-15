"""Invoice repository handling tenant-scoped queries."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select

from app.core.tenant import TenantContext
from app.db.models import Invoice, InvoiceStatus

from .base import TenantScopedRepository


class InvoiceRepository(TenantScopedRepository[Invoice]):
    """Invoice repository with filtering helpers."""

    model = Invoice

    def build_filter_query(
        self,
        tenant: TenantContext,
        status: InvoiceStatus | None = None,
        vendor_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Select[tuple[Invoice]]:
        statement = self._base_query().where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
        if status is not None:
            statement = statement.where(self.model.status == status)  # type: ignore[attr-defined]
        if vendor_id:
            statement = statement.where(self.model.vendor_id == vendor_id)  # type: ignore[attr-defined]
        if start_date:
            statement = statement.where(self.model.invoice_date >= start_date)  # type: ignore[attr-defined]
        if end_date:
            statement = statement.where(self.model.invoice_date <= end_date)  # type: ignore[attr-defined]
        if min_amount is not None:
            statement = statement.where(self.model.amount >= min_amount)  # type: ignore[attr-defined]
        if max_amount is not None:
            statement = statement.where(self.model.amount <= max_amount)  # type: ignore[attr-defined]
        return statement.offset(offset).limit(limit)

    def count_filtered(
        self,
        tenant: TenantContext,
        status: InvoiceStatus | None = None,
        vendor_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
    ) -> int:
        statement = select(func.count()).select_from(self.model).where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
        if status is not None:
            statement = statement.where(self.model.status == status)  # type: ignore[attr-defined]
        if vendor_id:
            statement = statement.where(self.model.vendor_id == vendor_id)  # type: ignore[attr-defined]
        if start_date:
            statement = statement.where(self.model.invoice_date >= start_date)  # type: ignore[attr-defined]
        if end_date:
            statement = statement.where(self.model.invoice_date <= end_date)  # type: ignore[attr-defined]
        if min_amount is not None:
            statement = statement.where(self.model.amount >= min_amount)  # type: ignore[attr-defined]
        if max_amount is not None:
            statement = statement.where(self.model.amount <= max_amount)  # type: ignore[attr-defined]
        return int(self.session.scalar(statement) or 0)

    def list_open_invoices(self, tenant: TenantContext) -> list[Invoice]:
        statement: Select[tuple[Invoice]] = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.status == InvoiceStatus.OPEN)  # type: ignore[attr-defined]
        )
        return self.session.scalars(statement).all()
