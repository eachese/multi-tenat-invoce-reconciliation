"""GraphQL context utilities for tenant-aware operations."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker
from strawberry.fastapi import BaseContext

from app.core.database import SessionLocal
from app.core.tenant import TenantContext, load_tenant_context


@dataclass(slots=True)
class GraphQLContext(BaseContext):
    """GraphQL-specific request context containing tenant and DB session."""

    tenant: TenantContext
    session_factory: sessionmaker[Session]

    def get_session(self) -> Session:
        """Return a new SQLAlchemy session for resolver use."""

        return self.session_factory()


def build_context(tenant_id: str) -> GraphQLContext:
    """Construct a GraphQL context with resolved tenant."""

    with SessionLocal() as session:
        tenant_context = load_tenant_context(session, tenant_id)
    return GraphQLContext(tenant=tenant_context, session_factory=SessionLocal)


def context_getter(request: Request) -> GraphQLContext:
    """FastAPI-compatible context getter for Strawberry GraphQL router."""

    header_name = "x-tenant-id"
    tenant_id = request.headers.get(header_name)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing {header_name} header",
        )
    return build_context(tenant_id)
