"""Bank transaction REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status

from app.api.dependencies import get_bank_transaction_service
from app.api.errors import map_service_error
from app.schemas.bank_transaction import (
    BankTransactionImportRequest,
    BankTransactionImportResponse,
)
from app.services.bank_transaction_service import BankTransactionService
from app.services.exceptions import ServiceError

router = APIRouter(prefix="/tenants/{tenant_id}/bank-transactions", tags=["bank-transactions"])


@router.post("/import", response_model=BankTransactionImportResponse, status_code=status.HTTP_200_OK)
def import_transactions(
    payload: BankTransactionImportRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    service: BankTransactionService = Depends(get_bank_transaction_service),
) -> BankTransactionImportResponse:
    """Import bank transactions with idempotency protection."""

    try:
        return service.import_transactions(payload, idempotency_key)
    except ServiceError as exc:
        raise map_service_error(exc) from exc
