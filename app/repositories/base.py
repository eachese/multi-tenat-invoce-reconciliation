"""Repository abstractions for database access."""
from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.core.tenant import TenantContext, TenantMismatchError

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """Base repository providing CRUD convenience helpers."""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    def get(self, obj_id: str) -> ModelT | None:
        statement = self._base_query().where(self.model.id == obj_id)  # type: ignore[attr-defined]
        return self.session.scalar(statement)

    def list(self, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        statement = self._base_query().offset(offset).limit(limit)
        return self.session.scalars(statement).all()

    def delete(self, instance: ModelT) -> None:
        self.session.delete(instance)

    def _base_query(self) -> Select[tuple[ModelT]]:
        return select(self.model)


class TenantScopedRepository(Repository[ModelT]):
    """Repository enforcing tenant-based filtering."""

    def get_for_tenant(self, tenant: TenantContext, obj_id: int | str) -> ModelT | None:
        statement = (
            self._base_query()
            .where(self.model.id == obj_id)  # type: ignore[attr-defined]
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
        )
        return self.session.scalar(statement)

    def list_for_tenant(
        self,
        tenant: TenantContext,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelT]:
        statement = (
            self._base_query()
            .where(self.model.tenant_id == tenant.tenant_id)  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def assert_entity_tenant(self, tenant: TenantContext, entity: ModelT) -> None:
        """Ensure that an entity belongs to the provided tenant context."""

        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id is None:
            raise TenantMismatchError("Entity lacks tenant_id for validation")
        tenant.ensure_matches(str(entity_tenant_id))
