"""Tests for tenant context isolation mechanics."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.tenant import TenantContext, TenantMismatchError, load_tenant_context
from app.db.base import Base
from app.db.models import Invoice, Tenant


@contextmanager
def in_memory_session() -> Session:
    """Yield a session backed by an isolated in-memory SQLite database."""

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionTest = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_load_tenant_context_returns_expected_tenant() -> None:
    with in_memory_session() as session:
        tenant = Tenant(name="Acme Corp")
        session.add(tenant)
        session.commit()

        context = load_tenant_context(session, tenant.id)

        assert context.tenant_id == tenant.id
        assert context.tenant_name == tenant.name


def test_ensure_entity_belongs_blocks_cross_tenant_access() -> None:
    with in_memory_session() as session:
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([tenant_a, tenant_b])
        session.commit()

        invoice = Invoice(
            tenant_id=tenant_a.id,
            amount=100,
            currency="USD",
        )
        session.add(invoice)
        session.commit()

        context_a = TenantContext(tenant_id=tenant_a.id, tenant_name=tenant_a.name)
        context_b = TenantContext(tenant_id=tenant_b.id, tenant_name=tenant_b.name)

        # context A accepts its own entity
        context_a.ensure_entity_belongs(invoice)

        # context B must not be able to access tenant A invoice
        try:
            context_b.ensure_entity_belongs(invoice)
        except TenantMismatchError as exc:
            assert "expected" in str(exc)
        else:  # pragma: no cover - safety net if exception is not raised
            raise AssertionError("TenantMismatchError was not raised for cross-tenant access")
