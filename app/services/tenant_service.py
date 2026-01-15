"""Tenant service handling CRUD operations."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.tenant import TenantRepository
from app.schemas.tenant import TenantCreate, TenantRead

from .exceptions import ConflictError, NotFoundError


class TenantService:
    """Service responsible for tenant lifecycle actions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenants = TenantRepository(session)

    def create(self, payload: TenantCreate) -> TenantRead:
        tenant = self.tenants.model(name=payload.name)
        self.session.add(tenant)
        try:
            self.session.commit()
        except IntegrityError as exc:  # pragma: no cover - DB constraint enforcement
            self.session.rollback()
            raise ConflictError("Tenant name already exists") from exc
        self.session.refresh(tenant)
        return TenantRead.model_validate(tenant)

    def list(self) -> list[TenantRead]:
        results = self.tenants.list()
        return [TenantRead.model_validate(row) for row in results]

    def get(self, tenant_id: str) -> TenantRead:
        tenant = self.tenants.get(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return TenantRead.model_validate(tenant)
