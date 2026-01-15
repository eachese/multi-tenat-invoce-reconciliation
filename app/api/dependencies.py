"""FastAPI dependency utilities for tenant-scoped access."""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.core.tenant import TenantContext, TenantNotFoundError, load_tenant_context
from app.schemas.invoice import InvoiceFilterParams
from app.services.bank_transaction_service import BankTransactionService
from app.services.explanation_service import ExplanationService
from app.services.invoice_service import InvoiceService
from app.services.reconciliation_service import ReconciliationService
from app.services.tenant_service import TenantService


def tenant_id_path(tenant_id: UUID = Path(..., description="Tenant identifier")) -> str:
    """Validate tenant identifier extracted from path."""

    return str(tenant_id)


def get_tenant_context(
    tenant_id: str = Depends(tenant_id_path),
    session: Session = Depends(get_db_session),
) -> TenantContext:
    """Resolve a tenant context for the request."""

    try:
        return load_tenant_context(session, tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def get_tenant_service(session: Session = Depends(get_db_session)) -> TenantService:
    """Provide tenant service with database session."""

    return TenantService(session)


def get_invoice_service(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db_session),
) -> InvoiceService:
    """Provide invoice service bound to tenant context."""

    return InvoiceService(session, tenant)


def get_bank_transaction_service(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db_session),
) -> BankTransactionService:
    """Provide bank transaction service bound to tenant context."""

    return BankTransactionService(session, tenant)


def get_reconciliation_service(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db_session),
) -> ReconciliationService:
    """Provide reconciliation service bound to tenant context."""

    return ReconciliationService(session, tenant)


def get_explanation_service(
    tenant: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db_session),
) -> ExplanationService:
    """Provide explanation service bound to tenant context."""

    return ExplanationService(session, tenant)


def get_invoice_filters(params: InvoiceFilterParams = Depends()) -> InvoiceFilterParams:
    """Expose invoice filters via dependency injection."""

    return params
