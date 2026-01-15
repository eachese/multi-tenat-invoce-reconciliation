"""Invoice REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_invoice_filters, get_invoice_service
from app.api.errors import map_service_error
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFilterParams,
    InvoiceListResponse,
    InvoiceRead,
)
from app.services.exceptions import ServiceError
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/tenants/{tenant_id}/invoices", tags=["invoices"])


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceRead:
    """Create an invoice for the tenant."""

    try:
        return service.create(payload)
    except ServiceError as exc:
        raise map_service_error(exc) from exc


@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    filters: InvoiceFilterParams = Depends(get_invoice_filters),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceListResponse:
    """List invoices with optional filters."""

    return service.list(filters, offset=offset, limit=limit)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: str,
    service: InvoiceService = Depends(get_invoice_service),
) -> Response:
    """Delete an invoice for the tenant."""

    try:
        service.delete(invoice_id)
    except ServiceError as exc:
        raise map_service_error(exc) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
