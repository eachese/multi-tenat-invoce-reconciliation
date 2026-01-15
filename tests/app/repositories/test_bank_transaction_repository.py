"""Unit tests for the bank transaction repository."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.tenant import TenantContext
from app.db.models import BankTransaction, Tenant
from app.repositories.bank_transaction import BankTransactionRepository


@pytest.fixture()
def tenant_context(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=str(tenant.id), tenant_name=tenant.name)


def _create_transaction(
    *,
    tenant_id: str,
    external_id: str | None,
    posted_at: datetime,
    amount: Decimal,
    description: str,
) -> BankTransaction:
    return BankTransaction(
        tenant_id=tenant_id,
        external_id=external_id,
        posted_at=posted_at,
        amount=amount,
        currency="USD",
        description=description,
    )


def test_get_by_external_ids_returns_map_for_matching_transactions(
    session, tenant: Tenant, tenant_context: TenantContext
) -> None:
    repository = BankTransactionRepository(session)

    other_tenant = Tenant(name="Other Tenant")
    session.add(other_tenant)
    session.commit()

    posted_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    session.add_all(
        [
            _create_transaction(
                tenant_id=tenant.id,
                external_id="ext-1",
                posted_at=posted_at,
                amount=Decimal("10.00"),
                description="First",
            ),
            _create_transaction(
                tenant_id=tenant.id,
                external_id="ext-2",
                posted_at=posted_at,
                amount=Decimal("20.00"),
                description="Second",
            ),
            _create_transaction(
                tenant_id=other_tenant.id,
                external_id="ext-3",
                posted_at=posted_at,
                amount=Decimal("30.00"),
                description="Other tenant",
            ),
        ]
    )
    session.commit()

    result = repository.get_by_external_ids(
        tenant_context, ["ext-1", "ext-2", "ext-999", "", None]
    )

    assert set(result.keys()) == {"ext-1", "ext-2"}
    assert all(tx.tenant_id == tenant.id for tx in result.values())


def test_get_by_external_ids_with_no_valid_identifiers_returns_empty_dict(
    session, tenant_context: TenantContext
) -> None:
    repository = BankTransactionRepository(session)

    result = repository.get_by_external_ids(tenant_context, ["", None])

    assert result == {}


def test_list_for_invoice_matching_returns_only_tenant_transactions(
    session, tenant: Tenant, tenant_context: TenantContext
) -> None:
    repository = BankTransactionRepository(session)

    other_tenant = Tenant(name="Competitor")
    session.add(other_tenant)
    session.commit()

    posted_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    session.add_all(
        [
            _create_transaction(
                tenant_id=tenant.id,
                external_id="match-1",
                posted_at=posted_at,
                amount=Decimal("100.00"),
                description="Eligible",
            ),
            _create_transaction(
                tenant_id=tenant.id,
                external_id="match-2",
                posted_at=posted_at,
                amount=Decimal("200.00"),
                description="Eligible",
            ),
            _create_transaction(
                tenant_id=other_tenant.id,
                external_id="match-3",
                posted_at=posted_at,
                amount=Decimal("300.00"),
                description="Other tenant",
            ),
        ]
    )
    session.commit()

    transactions = repository.list_for_invoice_matching(tenant_context)

    assert {tx.external_id for tx in transactions} == {"match-1", "match-2"}
    assert all(tx.tenant_id == tenant.id for tx in transactions)


def test_list_for_tenant_applies_pagination(
    session, tenant: Tenant, tenant_context: TenantContext
) -> None:
    repository = BankTransactionRepository(session)

    posted_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    session.add_all(
        [
            _create_transaction(
                tenant_id=tenant.id,
                external_id=f"page-{index}",
                posted_at=posted_at,
                amount=Decimal("50.00") + Decimal(index),
                description=f"Transaction {index}",
            )
            for index in range(3)
        ]
    )
    session.commit()

    first_page = repository.list_for_tenant(tenant_context, offset=0, limit=2)
    second_page = repository.list_for_tenant(tenant_context, offset=2, limit=2)
    beyond = repository.list_for_tenant(tenant_context, offset=5, limit=2)

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert beyond == []
    assert all(tx.tenant_id == tenant.id for tx in first_page + second_page)
