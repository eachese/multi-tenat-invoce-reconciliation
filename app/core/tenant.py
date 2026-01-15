"""Tenant context utilities and multi-tenancy guardrails."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Tenant


class TenantAccessError(RuntimeError):
    """Base error for tenant access violations."""


class TenantNotFoundError(TenantAccessError):
    """Raised when a tenant cannot be located."""


class TenantMismatchError(TenantAccessError):
    """Raised when data access crosses tenant boundaries."""


@dataclass(slots=True, frozen=True)
class TenantContext:
    """Runtime context binding operations to a specific tenant."""

    tenant_id: str
    tenant_name: str

    def ensure_matches(self, tenant_id: str | None) -> None:
        """Assert that the provided tenant_id matches the current context."""

        if tenant_id is None or tenant_id != self.tenant_id:
            raise TenantMismatchError(
                f"Tenant mismatch: expected {self.tenant_id}, received {tenant_id}"
            )

    def ensure_entity_belongs(self, entity: Any) -> None:
        """Ensure the given ORM entity belongs to the current tenant."""

        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id is not None:
            entity_tenant_id = str(entity_tenant_id)
        self.ensure_matches(entity_tenant_id)


def load_tenant_context(session: Session, tenant_id: str) -> TenantContext:
    """Load a tenant from persistence and return a context wrapper."""

    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFoundError(f"Tenant {tenant_id} not found")
    return TenantContext(tenant_id=str(tenant.id), tenant_name=tenant.name)
