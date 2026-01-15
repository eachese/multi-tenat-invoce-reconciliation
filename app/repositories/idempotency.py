"""Repository handling idempotency key persistence."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant import TenantContext
from app.db.models import IdempotencyKey

from .base import TenantScopedRepository


class IdempotencyRepository(TenantScopedRepository[IdempotencyKey]):
    """Persist and retrieve idempotency key usages."""

    model = IdempotencyKey

    def get_key(self, tenant: TenantContext, endpoint: str, key: str) -> IdempotencyKey | None:
        statement = (
            select(self.model)
            .where(self.model.tenant_id == tenant.tenant_id)
            .where(self.model.endpoint == endpoint)
            .where(self.model.key == key)
        )
        return self.session.scalar(statement)
