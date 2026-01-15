"""Tests for the Strawberry GraphQL schema resolvers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from graphql import GraphQLError

from app.core.tenant import TenantContext
from app.db.models import InvoiceStatus, MatchStatus
from app.graphql import schema
from app.graphql.context import GraphQLContext
from app.schemas.bank_transaction import (
    BankTransactionImportRequest,
    BankTransactionImportResponse,
    BankTransactionRead,
)
from app.schemas.invoice import InvoiceCreate, InvoiceListResponse, InvoiceRead
from app.schemas.match import (
    AIExplanationResponse,
    MatchCandidateRead,
    MatchConfirmationResponse,
    ReconciliationResponse,
)
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.exceptions import ServiceError


class DummySession:
    """Minimal session stub ensuring the context manager closes sessions."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:  # pragma: no cover - simple one-line setter
        self.closed = True


@pytest.fixture
def graphql_info() -> tuple[SimpleNamespace, list[DummySession], GraphQLContext]:
    sessions: list[DummySession] = []

    def session_factory() -> DummySession:
        session = DummySession()
        sessions.append(session)
        return session

    context = GraphQLContext(
        tenant=TenantContext(tenant_id="tenant-1", tenant_name="Tenant One"),
        session_factory=session_factory,
    )
    info = SimpleNamespace(context=context)
    return info, sessions, context


def test_health_returns_ok_status() -> None:
    result = schema.Query().health()
    assert result.status == "ok"


def test_tenants_returns_converted_types(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    created_at = datetime.now(tz=timezone.utc)
    tenants = [TenantRead(id="t-1", name="Tenant", created_at=created_at)]
    captured: dict[str, object] = {}

    class FakeTenantService:
        def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session

        def list(self) -> list[TenantRead]:
            captured["called"] = True
            return tenants

    monkeypatch.setattr(schema, "TenantService", FakeTenantService)

    result = schema.Query().tenants(info)

    assert captured["called"] is True
    assert isinstance(result[0], schema.TenantType)
    assert result[0].id == "t-1"
    assert captured["session"] is sessions[0]
    assert sessions[0].closed is True


def test_tenants_wraps_service_errors(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info

    class ErrorTenantService:
        def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
            self.session = session

        def list(self) -> list[TenantRead]:
            raise ServiceError("tenant boom")

    monkeypatch.setattr(schema, "TenantService", ErrorTenantService)

    with pytest.raises(GraphQLError) as exc_info:
        schema.Query().tenants(info)

    assert str(exc_info.value) == "tenant boom"
    assert sessions[0].closed is True


def test_invoices_applies_filters_and_limits(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, context = graphql_info
    created_at = datetime.now(tz=timezone.utc)
    invoice = InvoiceRead(
        id="inv-1",
        tenant_id=context.tenant.tenant_id,
        vendor_id="vendor-1",
        invoice_number="INV-1",
        amount=150.0,
        currency="USD",
        invoice_date=date(2024, 1, 10),
        description="Consulting",
        status=InvoiceStatus.OPEN,
        created_at=created_at,
    )
    response = InvoiceListResponse(items=[invoice], total=1)
    captured: dict[str, object] = {}

    class FakeInvoiceService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def list(self, filters, offset, limit) -> InvoiceListResponse:  # type: ignore[no-untyped-def]
            captured["filters"] = filters
            captured["offset"] = offset
            captured["limit"] = limit
            return response

    monkeypatch.setattr(schema, "InvoiceService", FakeInvoiceService)

    filters_input = schema.InvoiceFilterInput(
        status=schema.InvoiceStatusEnum.OPEN,
        vendor_id="vendor-99",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        min_amount=10.0,
        max_amount=250.0,
    )

    result = schema.Query().invoices(info, filters=filters_input, offset=5, limit=10)

    assert result.total == 1
    assert result.items[0].id == "inv-1"
    assert captured["filters"].vendor_id == "vendor-99"
    assert captured["filters"].status == InvoiceStatus.OPEN
    assert captured["offset"] == 5
    assert captured["limit"] == 10
    assert captured["session"] is sessions[0]
    assert sessions[0].closed is True


def test_bank_transactions_return_converted_rows(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, context = graphql_info
    captured: dict[str, object] = {}
    txn = BankTransactionRead(
        id="txn-1",
        tenant_id=context.tenant.tenant_id,
        external_id="ext-1",
        posted_at=datetime.now(tz=timezone.utc),
        amount=200.0,
        currency="USD",
        description="Deposit",
        created_at=datetime.now(tz=timezone.utc),
    )

    class FakeBankTransactionService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def list_transactions(self, offset, limit) -> list[BankTransactionRead]:  # type: ignore[no-untyped-def]
            captured["offset"] = offset
            captured["limit"] = limit
            return [txn]

    monkeypatch.setattr(schema, "BankTransactionService", FakeBankTransactionService)

    result = schema.Query().bank_transactions(info, offset=2, limit=3)

    assert len(result) == 1
    assert result[0].id == "txn-1"
    assert captured["offset"] == 2
    assert captured["limit"] == 3
    assert captured["session"] is sessions[0]
    assert sessions[0].closed is True


def test_match_candidates_translates_status(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    captured: dict[str, object] = {}
    candidate = MatchCandidateRead(
        id="match-1",
        invoice_id="inv-1",
        bank_transaction_id="txn-1",
        score=0.9,
        status=MatchStatus.PROPOSED,
        reasoning="High similarity",
        created_at=datetime.now(tz=timezone.utc),
    )

    class FakeReconciliationService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def list_matches(self, status=None) -> list[MatchCandidateRead]:  # type: ignore[no-untyped-def]
            captured["status"] = status
            return [candidate]

    monkeypatch.setattr(schema, "ReconciliationService", FakeReconciliationService)

    result = schema.Query().match_candidates(info, status=schema.MatchStatusEnum.CONFIRMED)

    assert len(result) == 1
    assert result[0].id == "match-1"
    assert captured["status"] == MatchStatus.CONFIRMED
    assert captured["session"] is sessions[0]
    assert sessions[0].closed is True


def test_match_candidates_without_status(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    captured: dict[str, object] = {}

    class FakeReconciliationService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session

        def list_matches(self, status=None):  # type: ignore[no-untyped-def]
            captured["status"] = status
            return []

    monkeypatch.setattr(schema, "ReconciliationService", FakeReconciliationService)

    result = schema.Query().match_candidates(info)

    assert result == []
    assert captured["status"] is None
    assert sessions[0].closed is True


def test_explain_reconciliation_returns_ai_payload(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    captured: dict[str, object] = {}

    class FakeExplanationService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def explain_pair(self, invoice_id: str, transaction_id: str) -> AIExplanationResponse:
            captured["invoice_id"] = invoice_id
            captured["transaction_id"] = transaction_id
            return AIExplanationResponse(explanation="Details", confidence="high")

    monkeypatch.setattr(schema, "ExplanationService", FakeExplanationService)

    result = schema.Query().explain_reconciliation(
        info,
        invoice_id="inv-9",
        bank_transaction_id="txn-9",
    )

    assert result.explanation == "Details"
    assert result.confidence == "high"
    assert captured["invoice_id"] == "inv-9"
    assert captured["transaction_id"] == "txn-9"
    assert captured["session"] is sessions[0]
    assert sessions[0].closed is True


def test_create_tenant_returns_graphql_type(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    created_at = datetime.now(tz=timezone.utc)
    captured: dict[str, object] = {}

    class FakeTenantService:
        def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session

        def create(self, payload: TenantCreate) -> TenantRead:
            captured["payload"] = payload
            return TenantRead(id="t-99", name=payload.name, created_at=created_at)

    monkeypatch.setattr(schema, "TenantService", FakeTenantService)

    result = schema.Mutation().create_tenant(info, name="New Tenant")

    assert result.id == "t-99"
    assert result.name == "New Tenant"
    assert isinstance(captured["payload"], TenantCreate)
    assert sessions[0].closed is True


def test_create_tenant_wraps_service_error(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info

    class ErrorTenantService:
        def __init__(self, session) -> None:  # type: ignore[no-untyped-def]
            self.session = session

        def create(self, payload: TenantCreate) -> TenantRead:
            raise ServiceError("create tenant boom")

    monkeypatch.setattr(schema, "TenantService", ErrorTenantService)

    with pytest.raises(GraphQLError) as exc_info:
        schema.Mutation().create_tenant(info, name="Boom")

    assert str(exc_info.value) == "create tenant boom"
    assert sessions[0].closed is True


def test_create_invoice_passes_expected_payload(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, context = graphql_info
    created_at = datetime.now(tz=timezone.utc)
    captured: dict[str, object] = {}
    invoice = InvoiceRead(
        id="inv-9",
        tenant_id=context.tenant.tenant_id,
        vendor_id="vendor-1",
        invoice_number="INV-9",
        amount=300.0,
        currency="USD",
        invoice_date=date(2024, 2, 1),
        description="Design work",
        status=InvoiceStatus.OPEN,
        created_at=created_at,
    )

    class FakeInvoiceService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def create(self, payload: InvoiceCreate) -> InvoiceRead:
            captured["payload"] = payload
            return invoice

    monkeypatch.setattr(schema, "InvoiceService", FakeInvoiceService)

    payload = schema.InvoiceCreateInput(
        amount=300.0,
        currency="usd",
        vendor_id="vendor-1",
        invoice_number="INV-9",
        invoice_date=date(2024, 2, 1),
        description="Design work",
    )

    result = schema.Mutation().create_invoice(info, payload=payload)

    assert result.id == "inv-9"
    assert isinstance(captured["payload"], InvoiceCreate)
    assert captured["payload"].vendor_id == "vendor-1"
    assert sessions[0].closed is True


def test_delete_invoice_invokes_service(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    captured: dict[str, object] = {}

    class FakeInvoiceService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def delete(self, invoice_id: str) -> None:
            captured["invoice_id"] = invoice_id

    monkeypatch.setattr(schema, "InvoiceService", FakeInvoiceService)

    result = schema.Mutation().delete_invoice(info, invoice_id="inv-1")

    assert result.success is True
    assert captured["invoice_id"] == "inv-1"
    assert sessions[0].closed is True


def test_import_bank_transactions_builds_request(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, context = graphql_info
    captured: dict[str, object] = {}
    now = datetime.now(tz=timezone.utc)

    class FakeBankTransactionService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def import_transactions(
            self,
            request: BankTransactionImportRequest,
            key: str,
        ) -> BankTransactionImportResponse:
            captured["request"] = request
            captured["key"] = key
            return BankTransactionImportResponse(
                created=1,
                duplicates=0,
                conflicts=0,
                transactions=[
                    BankTransactionRead(
                        id="txn-1",
                        tenant_id=context.tenant.tenant_id,
                        external_id="ext-1",
                        posted_at=now,
                        amount=200.0,
                        currency="USD",
                        description="Deposit",
                        created_at=now,
                    )
                ],
            )

    monkeypatch.setattr(schema, "BankTransactionService", FakeBankTransactionService)

    payload = schema.BankTransactionImportInput(
        transactions=[
            schema.BankTransactionImportItemInput(
                external_id="ext-1",
                posted_at=now,
                amount=200.0,
                currency="USD",
                description="Deposit",
            )
        ]
    )

    result = schema.Mutation().import_bank_transactions(info, payload=payload, idempotency_key="key-1")

    assert result.created == 1
    assert captured["key"] == "key-1"
    assert isinstance(captured["request"], BankTransactionImportRequest)
    assert captured["request"].transactions[0].external_id == "ext-1"
    assert sessions[0].closed is True


def test_reconcile_returns_matches(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    now = datetime.now(tz=timezone.utc)
    captured: dict[str, object] = {}
    response = ReconciliationResponse(
        matches=[
            MatchCandidateRead(
                id="match-1",
                invoice_id="inv-1",
                bank_transaction_id="txn-1",
                score=0.95,
                status=MatchStatus.PROPOSED,
                reasoning=None,
                created_at=now,
            )
        ]
    )

    class FakeReconciliationService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def reconcile(self) -> ReconciliationResponse:
            captured["called"] = True
            return response

    monkeypatch.setattr(schema, "ReconciliationService", FakeReconciliationService)

    result = schema.Mutation().reconcile(info)

    assert len(result.matches) == 1
    assert captured["called"] is True
    assert sessions[0].closed is True


def test_confirm_match_returns_confirmation(monkeypatch: pytest.MonkeyPatch, graphql_info) -> None:
    info, sessions, _ = graphql_info
    now = datetime.now(tz=timezone.utc)
    captured: dict[str, object] = {}
    response = MatchConfirmationResponse(
        match=MatchCandidateRead(
            id="match-1",
            invoice_id="inv-1",
            bank_transaction_id="txn-1",
            score=0.9,
            status=MatchStatus.CONFIRMED,
            reasoning=None,
            created_at=now,
        ),
        invoice_status="matched",
    )

    class FakeReconciliationService:
        def __init__(self, session, tenant) -> None:  # type: ignore[no-untyped-def]
            captured["session"] = session
            captured["tenant"] = tenant

        def confirm_match(self, match_id: str) -> MatchConfirmationResponse:
            captured["match_id"] = match_id
            return response

    monkeypatch.setattr(schema, "ReconciliationService", FakeReconciliationService)

    result = schema.Mutation().confirm_match(info, match_id="match-1")

    assert result.invoice_status == "matched"
    assert captured["match_id"] == "match-1"
    assert sessions[0].closed is True
