"""Reconciliation, match confirmation, and explanation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    get_explanation_service,
    get_reconciliation_service,
)
from app.api.errors import map_service_error
from app.schemas.match import AIExplanationResponse, MatchConfirmationResponse, ReconciliationResponse
from app.services.explanation_service import ExplanationService
from app.services.exceptions import ServiceError
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["reconciliation"])


@router.post("/reconcile", response_model=ReconciliationResponse)
def reconcile(
    tenant_id: str,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ReconciliationResponse:
    """Trigger reconciliation for a tenant."""

    return service.reconcile()


@router.post("/matches/{match_id}/confirm", response_model=MatchConfirmationResponse)
def confirm_match(
    tenant_id: str,
    match_id: str,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> MatchConfirmationResponse:
    """Confirm a proposed match for a tenant."""

    try:
        return service.confirm_match(match_id)
    except ServiceError as exc:
        raise map_service_error(exc) from exc


@router.get("/reconcile/explain", response_model=AIExplanationResponse)
def explain_match(
    tenant_id: str,
    match_id: str | None = Query(default=None, description="Match identifier"),
    invoice_id: str | None = Query(default=None, description="Invoice identifier"),
    bank_transaction_id: str | None = Query(default=None, description="Bank transaction identifier"),
    service: ExplanationService = Depends(get_explanation_service),
) -> AIExplanationResponse:
    """Return AI/fallback explanation for a match or an explicit invoice/transaction pair."""

    try:
        if match_id is not None:
            return service.explain_match(match_id)
        if invoice_id is not None and bank_transaction_id is not None:
            return service.explain_pair(invoice_id, bank_transaction_id)
    except ServiceError as exc:
        raise map_service_error(exc) from exc

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Provide match_id or both invoice_id and bank_transaction_id",
    )
