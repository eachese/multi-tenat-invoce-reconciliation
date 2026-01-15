"""Unit tests for :mod:`app.services.explanation_service`."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.ai.provider import ExplanationContext
from app.core.tenant import TenantContext
from app.db.models import BankTransaction, Invoice, MatchCandidate, MatchStatus, Tenant
from app.services import explanation_service
from app.services.explanation_service import ExplanationService
from app.services.exceptions import NotFoundError


class FakeSettings:
    def __init__(self, api_key: str | None, model: str = "gpt-4o-mini") -> None:
        self.ai_api_key = api_key
        self.ai_model = model


class StubAIClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[ExplanationContext] = []

    def explain(self, context: ExplanationContext) -> tuple[str, str | None]:
        self.calls.append(context)
        if self.fail:
            raise RuntimeError("boom")
        return "AI explanation", "medium"


class StubFallbackClient:
    def __init__(self) -> None:
        self.calls: list[ExplanationContext] = []

    def explain(self, context: ExplanationContext) -> tuple[str, str | None]:
        self.calls.append(context)
        return "Fallback explanation", "low"


def create_match(
    session: Session,
    tenant: Tenant,
    *,
    reasoning: str | None = "Stored reasoning",
) -> MatchCandidate:
    invoice = Invoice(
        tenant_id=tenant.id,
        amount=Decimal("200.00"),
        currency="USD",
        description="Consulting Services",
        invoice_date=datetime(2024, 5, 20, tzinfo=timezone.utc).date(),
    )
    transaction = BankTransaction(
        tenant_id=tenant.id,
        posted_at=datetime(2024, 5, 21, 14, 30, tzinfo=timezone.utc),
        amount=Decimal("200.00"),
        currency="USD",
        description="Consulting Services invoice",
    )
    session.add_all([invoice, transaction])
    session.commit()
    session.refresh(invoice)
    session.refresh(transaction)

    match = MatchCandidate(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        bank_transaction_id=transaction.id,
        score=Decimal("0.72"),
        status=MatchStatus.PROPOSED,
        reasoning=reasoning,
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


@pytest.fixture()
def tenant_context(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, tenant_name=tenant.name)


def configure_fallback(monkeypatch: pytest.MonkeyPatch, client: StubFallbackClient) -> None:
    monkeypatch.setattr(explanation_service, "fallback_client", lambda: client)


def configure_settings(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> None:
    monkeypatch.setattr(explanation_service, "get_settings", lambda: FakeSettings(api_key=api_key))


def test_explain_match_uses_ai_client(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    match = create_match(session, tenant)

    ai_client = StubAIClient()
    fallback = StubFallbackClient()

    configure_settings(monkeypatch, api_key="integration-key")
    monkeypatch.setattr(explanation_service, "resolve_ai_client", lambda model, key: ai_client)
    configure_fallback(monkeypatch, fallback)

    service = ExplanationService(session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "AI explanation"
    assert response.confidence == "medium"
    assert len(ai_client.calls) == 1
    assert fallback.calls == []


def test_explain_match_uses_fallback_when_no_ai_key(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    match = create_match(session, tenant)

    fallback = StubFallbackClient()
    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, fallback)

    service = ExplanationService(session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "Fallback explanation"
    assert response.confidence == "low"
    assert len(fallback.calls) == 1


def test_explain_match_falls_back_on_ai_error(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    match = create_match(session, tenant)

    ai_client = StubAIClient(fail=True)
    fallback = StubFallbackClient()

    configure_settings(monkeypatch, api_key="integration-key")
    monkeypatch.setattr(explanation_service, "resolve_ai_client", lambda model, key: ai_client)
    configure_fallback(monkeypatch, fallback)

    service = ExplanationService(session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "Fallback explanation"
    assert response.confidence == "low"
    assert len(ai_client.calls) == 1
    assert len(fallback.calls) == 1


def test_explain_match_generates_reasoning_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    match = create_match(session, tenant, reasoning=None)

    ai_client = StubAIClient()
    configure_settings(monkeypatch, api_key="integration-key")
    monkeypatch.setattr(explanation_service, "resolve_ai_client", lambda model, key: ai_client)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "AI explanation"
    generated = ai_client.calls[0].reasoning
    assert generated is not None and "weight" in generated


def test_explain_match_missing_match_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)

    with pytest.raises(NotFoundError):
        service.explain_match("missing-id")


def test_explain_match_missing_related_entities_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    class DummyMatch:
        def __init__(self) -> None:
            self.invoice = None
            self.bank_transaction = None
            self.reasoning = "reason"
            self.score = Decimal("0.2")

    monkeypatch.setattr(ExplanationService, "_get_match", lambda self, match_id: DummyMatch())

    service = ExplanationService(session, tenant_context)

    with pytest.raises(NotFoundError):
        service.explain_match("any")


def test_explain_match_rejects_cross_tenant_access(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    other_tenant = Tenant(name="Other Tenant")
    session.add(other_tenant)
    session.commit()
    session.refresh(other_tenant)

    other_match = create_match(session, other_tenant)

    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)

    with pytest.raises(NotFoundError):
        service.explain_match(other_match.id)


def test_explain_pair_uses_existing_match_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    match = create_match(session, tenant, reasoning="Stored reasoning")

    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)
    response = service.explain_pair(match.invoice_id, match.bank_transaction_id)

    assert response.explanation == "Fallback explanation"
    assert response.confidence == "low"


def test_explain_pair_generates_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant: Tenant,
    tenant_context: TenantContext,
) -> None:
    invoice = Invoice(
        tenant_id=tenant.id,
        amount=Decimal("150.00"),
        currency="USD",
        description="Design work",
        invoice_date=datetime(2024, 6, 1, tzinfo=timezone.utc).date(),
    )
    transaction = BankTransaction(
        tenant_id=tenant.id,
        posted_at=datetime(2024, 6, 2, tzinfo=timezone.utc),
        amount=Decimal("150.00"),
        currency="USD",
        description="Design payment",
    )
    session.add_all([invoice, transaction])
    session.commit()
    session.refresh(invoice)
    session.refresh(transaction)

    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)
    response = service.explain_pair(invoice.id, transaction.id)

    assert response.explanation == "Fallback explanation"
    assert response.confidence == "low"


def test_explain_pair_missing_invoice_raises(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tenant_context: TenantContext,
) -> None:
    configure_settings(monkeypatch, api_key=None)
    configure_fallback(monkeypatch, StubFallbackClient())

    service = ExplanationService(session, tenant_context)

    with pytest.raises(NotFoundError):
        service.explain_pair("missing-invoice", "missing-txn")
