"""Invoice service exposing tenant-scoped operations."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db.models import InvoiceStatus
from app.repositories.invoice import InvoiceRepository
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFilterParams,
    InvoiceListResponse,
    InvoiceRead,
)

from .exceptions import NotFoundError


class InvoiceService:
    """Tenant-scoped invoice operations."""

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self.session = session
        self.tenant = tenant
        self.invoices = InvoiceRepository(session)

    def create(self, payload: InvoiceCreate) -> InvoiceRead:
        invoice = self.invoices.model(
            tenant_id=self.tenant.tenant_id,
            amount=Decimal(str(payload.amount)),
            currency=payload.currency.upper(),
            vendor_id=payload.vendor_id,
            invoice_number=payload.invoice_number,
            invoice_date=payload.invoice_date,
            description=payload.description,
            status=InvoiceStatus.OPEN,
        )
        self.session.add(invoice)
        self.session.commit()
        self.session.refresh(invoice)
        return InvoiceRead.model_validate(invoice)

    def list(
        self,
        filters: InvoiceFilterParams,
        offset: int = 0,
        limit: int = 100,
    ) -> InvoiceListResponse:
        statement = self.invoices.build_filter_query(
            tenant=self.tenant,
            status=filters.status,
            vendor_id=filters.vendor_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            min_amount=filters.min_amount,
            max_amount=filters.max_amount,
            offset=offset,
            limit=limit,
        )
        rows = self.session.scalars(statement).all()
        total = self.invoices.count_filtered(
            tenant=self.tenant,
            status=filters.status,
            vendor_id=filters.vendor_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            min_amount=filters.min_amount,
            max_amount=filters.max_amount,
        )
        return InvoiceListResponse(
            items=[InvoiceRead.model_validate(row) for row in rows],
            total=total,
        )

    def delete(self, invoice_id: str) -> None:
        invoice = self.invoices.get_for_tenant(self.tenant, invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")
        self.session.delete(invoice)
        self.session.commit()
