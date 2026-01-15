"""Repository for tenant entities."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Tenant

from .base import Repository


class TenantRepository(Repository[Tenant]):
    """Tenant repository with simple CRUD helpers."""

    model = Tenant

    def __init__(self, session: Session) -> None:
        super().__init__(session)
