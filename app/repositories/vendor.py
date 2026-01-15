"""Repository for vendor entities."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant import TenantContext
from app.db.models import Vendor

from .base import TenantScopedRepository


class VendorRepository(TenantScopedRepository[Vendor]):
    """Vendor repository with tenant-scoped helpers."""

    model = Vendor

    def get_by_name(self, tenant: TenantContext, name: str) -> Vendor | None:
        statement = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.name == name)
        )
        return self.session.scalar(statement)
