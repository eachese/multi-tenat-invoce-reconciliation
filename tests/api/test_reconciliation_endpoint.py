"""Unit tests for reconciliation REST endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.api.dependencies import get_explanation_service, get_reconciliation_service
from app.api.endpoints import reconciliation
from app.db.models import MatchStatus
from app.schemas.match import (
    AIExplanationResponse,
    MatchCandidateRead,
    MatchConfirmationResponse,
    ReconciliationResponse,
)
from app.services.exceptions import ConflictError, NotFoundError, ServiceError


FIXED_TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _sample_match_candidate() -> MatchCandidateRead:
    return MatchCandidateRead(
        id="match-1",
        invoice_id="inv-1",
        bank_transaction_id="txn-1",
        score=0.93,
        status=MatchStatus.PROPOSED,
        reasoning="High confidence",
        created_at=FIXED_TIMESTAMP,
    )


class StubReconciliationService:
    def __init__(
        self,
        *,
        reconcile_response: ReconciliationResponse | None = None,
        reconcile_exception: Exception | None = None,
        confirm_response: MatchConfirmationResponse | None = None,
        confirm_exception: Exception | None = None,
    ) -> None:
        self.reconcile_response = reconcile_response or ReconciliationResponse(matches=[_sample_match_candidate()])
        self.reconcile_exception = reconcile_exception
        self.confirm_response = confirm_response or MatchConfirmationResponse(
            match=_sample_match_candidate(),
            invoice_status="matched",
        )
        self.confirm_exception = confirm_exception
        self.reconcile_calls = 0
        self.confirm_calls: list[str] = []

    def reconcile(self) -> ReconciliationResponse:
        self.reconcile_calls += 1
        if self.reconcile_exception:
            raise self.reconcile_exception
        return self.reconcile_response

    def confirm_match(self, match_id: str) -> MatchConfirmationResponse:
        self.confirm_calls.append(match_id)
        if self.confirm_exception:
            raise self.confirm_exception
        return self.confirm_response


class StubExplanationService:
    def __init__(
        self,
        *,
        response: AIExplanationResponse | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.response = response or AIExplanationResponse(explanation="AI rationale", confidence="high")
        self.exception = exception
        self.calls: list[str] = []

    def explain_match(self, match_id: str) -> AIExplanationResponse:
        self.calls.append(match_id)
        if self.exception:
            raise self.exception
        return self.response


def _create_client(
    reconciliation_service: StubReconciliationService,
    explanation_service_factory: Callable[[], StubExplanationService] | None = None,
) -> tuple[TestClient, StubExplanationService | None]:
    app = FastAPI()
    app.include_router(reconciliation.router, prefix="/api")
    app.dependency_overrides[get_reconciliation_service] = lambda: reconciliation_service

    explanation_stub: StubExplanationService | None = None
    if explanation_service_factory is not None:
        explanation_stub = explanation_service_factory()
        app.dependency_overrides[get_explanation_service] = lambda: explanation_stub

    return TestClient(app), explanation_stub


def test_reconcile_returns_service_response() -> None:
    stub = StubReconciliationService(
        reconcile_response=ReconciliationResponse(matches=[_sample_match_candidate()])
    )
    client, _ = _create_client(stub, explanation_service_factory=lambda: StubExplanationService())

    tenant_id = str(uuid4())
    response = client.post(f"/api/tenants/{tenant_id}/reconcile")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == stub.reconcile_response.model_dump()
    assert stub.reconcile_calls == 1


def test_confirm_match_returns_confirmation_payload() -> None:
    confirmation = MatchConfirmationResponse(
        match=_sample_match_candidate(),
        invoice_status="matched",
    )
    stub = StubReconciliationService(confirm_response=confirmation)
    client, _ = _create_client(stub, explanation_service_factory=lambda: StubExplanationService())

    tenant_id = str(uuid4())
    match_id = "match-123"
    response = client.post(f"/api/tenants/{tenant_id}/matches/{match_id}/confirm")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == confirmation.model_dump()
    assert stub.confirm_calls == [match_id]


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_detail"),
    [
        (NotFoundError("match missing"), status.HTTP_404_NOT_FOUND, "match missing"),
        (ConflictError("already confirmed"), status.HTTP_409_CONFLICT, "already confirmed"),
        (ServiceError("unexpected"), status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal service error"),
    ],
)
def test_confirm_match_maps_service_errors(exception: ServiceError, expected_status: int, expected_detail: str) -> None:
    stub = StubReconciliationService(confirm_exception=exception)
    client, _ = _create_client(stub, explanation_service_factory=lambda: StubExplanationService())

    tenant_id = str(uuid4())
    response = client.post(f"/api/tenants/{tenant_id}/matches/m-1/confirm")

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert stub.confirm_calls == ["m-1"]


def test_explain_match_returns_service_payload() -> None:
    recon_stub = StubReconciliationService()
    explanation_stub = StubExplanationService(
        response=AIExplanationResponse(explanation="Reasoned summary", confidence="medium")
    )

    client, injected_explanation = _create_client(
        recon_stub, explanation_service_factory=lambda: explanation_stub
    )

    tenant_id = str(uuid4())
    match_id = "match-789"
    response = client.get(
        f"/api/tenants/{tenant_id}/reconcile/explain",
        params={"match_id": match_id},
    )

    assert injected_explanation is explanation_stub
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == explanation_stub.response.model_dump()
    assert explanation_stub.calls == [match_id]


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_detail"),
    [
        (NotFoundError("explanation missing"), status.HTTP_404_NOT_FOUND, "explanation missing"),
        (ServiceError("ai failed"), status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal service error"),
    ],
)
def test_explain_match_maps_service_errors(
    exception: ServiceError, expected_status: int, expected_detail: str
) -> None:
    recon_stub = StubReconciliationService()
    client, explanation_stub = _create_client(
        recon_stub,
        explanation_service_factory=lambda: StubExplanationService(exception=exception),
    )

    tenant_id = str(uuid4())
    response = client.get(
        f"/api/tenants/{tenant_id}/reconcile/explain",
        params={"match_id": "match-404"},
    )

    assert explanation_stub is not None
    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert explanation_stub.calls == ["match-404"]
