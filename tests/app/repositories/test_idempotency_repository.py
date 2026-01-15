"""Tests for the IdempotencyRepository."""
from __future__ import annotations

from app.core.tenant import TenantContext
from app.db.models import IdempotencyKey, Tenant
from app.repositories.idempotency import IdempotencyRepository


def _tenant_context(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=str(tenant.id), tenant_name=tenant.name)


def _persist_idempotency_key(
    session,
    *,
    tenant_id: str,
    endpoint: str,
    key: str,
    payload_hash: str = "hash",
):
    record = IdempotencyKey(
        tenant_id=tenant_id,
        endpoint=endpoint,
        key=key,
        payload_hash=payload_hash,
        response_status=200,
        response_body={"created": 1},
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_get_key_returns_matching_record(session, tenant) -> None:
    repository = IdempotencyRepository(session)
    tenant_context = _tenant_context(tenant)

    persisted = _persist_idempotency_key(
        session,
        tenant_id=str(tenant.id),
        endpoint="bank_transactions_import",
        key="batch-1",
    )

    result = repository.get_key(tenant_context, "bank_transactions_import", "batch-1")

    assert result is not None
    assert result.id == persisted.id


def test_get_key_ignores_records_from_other_tenants(session, tenant) -> None:
    repository = IdempotencyRepository(session)

    other_tenant = Tenant(name="Other Tenant")
    session.add(other_tenant)
    session.commit()
    session.refresh(other_tenant)

    _persist_idempotency_key(
        session,
        tenant_id=str(other_tenant.id),
        endpoint="bank_transactions_import",
        key="batch-1",
    )

    tenant_context = _tenant_context(tenant)
    result = repository.get_key(tenant_context, "bank_transactions_import", "batch-1")

    assert result is None


def test_get_key_requires_exact_endpoint_and_key(session, tenant) -> None:
    repository = IdempotencyRepository(session)
    tenant_context = _tenant_context(tenant)

    _persist_idempotency_key(
        session,
        tenant_id=str(tenant.id),
        endpoint="bank_transactions_import",
        key="batch-1",
    )

    missing_endpoint = repository.get_key(tenant_context, "different_endpoint", "batch-1")
    missing_key = repository.get_key(tenant_context, "bank_transactions_import", "different-key")

    assert missing_endpoint is None
    assert missing_key is None
