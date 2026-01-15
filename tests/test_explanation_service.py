"""Tests for explanation service AI integration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.models import BankTransaction, MatchCandidate, MatchStatus, Tenant
from app.services.explanation_service import ExplanationService


class FakeSettings:
    def __init__(self, api_key: str | None) -> None:
        self.ai_api_key = api_key
        self.ai_model = "gpt-4o-mini"


class FakeAIClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[Any] = []

    def explain(self, context: Any) -> tuple[str, str | None]:
        self.calls.append(context)
        if self.fail:
            raise RuntimeError("boom")
        return "AI says OK", "medium"


class FakeFallbackClient:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def explain(self, context: Any) -> tuple[str, str | None]:
        self.calls.append(context)
        return "Fallback reasoning", "low"


@pytest.fixture()
def in_memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed_match(session: Session) -> MatchCandidate:
    tenant = Tenant(name="Tenant X")
    session.add(tenant)
    session.flush()

    transaction = BankTransaction(
        id="txn-1",
        tenant_id=tenant.id,
        external_id="txn-1",
        posted_at=datetime.now(tz=timezone.utc),
        amount=200,
        currency="USD",
        description="Consulting Services",
    )
    session.add(transaction)

    match = MatchCandidate(
        tenant_id=tenant.id,
        id="match-1",
        invoice_id="inv-1",
        bank_transaction_id=transaction.id,
        score=0.65,
        status=MatchStatus.PROPOSED,
        reasoning="Amount and memo close",
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def test_explanation_service_uses_fallback_when_no_ai_key(monkeypatch: pytest.MonkeyPatch, in_memory_session: Session) -> None:
    match = seed_match(in_memory_session)
    tenant_context = TenantContext(tenant_id=match.tenant_id, tenant_name="Tenant X")

    monkeypatch.setattr("app.services.explanation_service.get_settings", lambda: FakeSettings(api_key=None))

    fake_fallback = FakeFallbackClient()
    monkeypatch.setattr("app.services.explanation_service.fallback_client", lambda: fake_fallback)

    service = ExplanationService(in_memory_session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "Fallback reasoning"
    assert response.confidence == "low"
    assert len(fake_fallback.calls) == 1


def test_explanation_service_handles_ai_failure(monkeypatch: pytest.MonkeyPatch, in_memory_session: Session) -> None:
    match = seed_match(in_memory_session)
    tenant_context = TenantContext(tenant_id=match.tenant_id, tenant_name="Tenant X")

    monkeypatch.setattr("app.services.explanation_service.get_settings", lambda: FakeSettings(api_key="fake-key"))

    fake_client = FakeAIClient(fail=True)
    monkeypatch.setattr("app.services.explanation_service.resolve_ai_client", lambda model, key: fake_client)

    fake_fallback = FakeFallbackClient()
    monkeypatch.setattr("app.services.explanation_service.fallback_client", lambda: fake_fallback)

    service = ExplanationService(in_memory_session, tenant_context)
    response = service.explain_match(match.id)

    assert response.explanation == "Fallback reasoning"
    assert response.confidence == "low"
    assert len(fake_client.calls) == 1
    assert len(fake_fallback.calls) == 1
