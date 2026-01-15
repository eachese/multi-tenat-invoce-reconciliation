"""Root API router for REST endpoints."""
from fastapi import APIRouter

from app.api.endpoints import bank_transactions, invoices, reconciliation, tenants

router = APIRouter()


@router.get("/health", tags=["health"], summary="Health check")
def health_check() -> dict[str, str]:
    """Return basic service health information."""

    return {"status": "ok"}


router.include_router(tenants.router)
router.include_router(invoices.router)
router.include_router(bank_transactions.router)
router.include_router(reconciliation.router)
