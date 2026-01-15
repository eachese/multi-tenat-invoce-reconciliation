"""Tenant-related REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_tenant_service
from app.api.errors import map_service_error
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.exceptions import ServiceError
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    service: TenantService = Depends(get_tenant_service),
) -> TenantRead:
    """Create a new tenant."""

    try:
        return service.create(payload)
    except ServiceError as exc:
        raise map_service_error(exc) from exc


@router.get("", response_model=list[TenantRead])
def list_tenants(
    service: TenantService = Depends(get_tenant_service),
) -> list[TenantRead]:
    """List available tenants."""

    return service.list()
