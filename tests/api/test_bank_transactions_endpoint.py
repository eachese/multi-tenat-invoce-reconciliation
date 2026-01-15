"""Unit tests for the bank transactions endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_bank_transaction_service
from app.api.endpoints.bank_transactions import router
from app.schemas.bank_transaction import (
    BankTransactionImportRequest,
    BankTransactionImportResponse,
    BankTransactionRead,
)
from app.services.exceptions import ConflictError, ServiceError, ValidationError

BASE_URL = "/api/tenants/test-tenant/bank-transactions/import"


def _request_payload() -> dict[str, object]:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return {
        "transactions": [
            {
                "external_id": "txn-123",
                "posted_at": now.isoformat(),
                "amount": 200.0,
                "currency": "USD",
                "description": "Consulting services",
            }
        ]
    }


def _response_fixture() -> BankTransactionImportResponse:
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return BankTransactionImportResponse(
        created=1,
        duplicates=0,
        conflicts=0,
        transactions=[
            BankTransactionRead(
                id="bt-1",
                tenant_id="test-tenant",
                external_id="txn-123",
                posted_at=timestamp,
                amount=200.0,
                currency="USD",
                description="Consulting services",
                created_at=timestamp,
            )
        ],
    )


@pytest.fixture()
def api_app() -> Generator[FastAPI, None, None]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    yield app
    app.dependency_overrides.clear()


@pytest.fixture()
def api_client(api_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(api_app) as client:
        yield client


class RecordingService:
    def __init__(self, response: BankTransactionImportResponse) -> None:
        self.response = response
        self.calls: list[tuple[BankTransactionImportRequest, str | None]] = []

    def import_transactions(
        self,
        payload: BankTransactionImportRequest,
        idempotency_key: str | None,
    ) -> BankTransactionImportResponse:
        self.calls.append((payload, idempotency_key))
        return self.response


class RaisingService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def import_transactions(
        self,
        payload: BankTransactionImportRequest,
        idempotency_key: str | None,
    ) -> BankTransactionImportResponse:
        raise self.exc


def test_import_transactions_success_returns_service_response(api_app: FastAPI, api_client: TestClient) -> None:
    service = RecordingService(_response_fixture())
    api_app.dependency_overrides[get_bank_transaction_service] = lambda: service

    response = api_client.post(
        BASE_URL,
        json=_request_payload(),
        headers={"Idempotency-Key": "batch-42"},
    )

    assert response.status_code == 200
    body = response.json()
    expected = service.response
    assert body["created"] == expected.created
    assert body["duplicates"] == expected.duplicates
    assert body["conflicts"] == expected.conflicts
    assert len(body["transactions"]) == len(expected.transactions)

    transaction = body["transactions"][0]
    expected_transaction = expected.transactions[0]
    assert transaction["id"] == expected_transaction.id
    assert transaction["posted_at"] == expected_transaction.posted_at.isoformat()
    assert transaction["amount"] == expected_transaction.amount
    assert transaction["currency"] == expected_transaction.currency
    assert transaction["description"] == expected_transaction.description

    assert len(service.calls) == 1
    payload, key = service.calls[0]
    assert isinstance(payload, BankTransactionImportRequest)
    assert key == "batch-42"
    assert payload.transactions[0].amount == pytest.approx(200.0)
    assert payload.transactions[0].external_id == "txn-123"


def test_import_transactions_validation_error_maps_to_400(
    api_app: FastAPI, api_client: TestClient
) -> None:
    api_app.dependency_overrides[get_bank_transaction_service] = lambda: RaisingService(
        ValidationError("Idempotency key required"),
    )

    response = api_client.post(BASE_URL, json=_request_payload(), headers={"Idempotency-Key": "batch"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency key required"


def test_import_transactions_conflict_error_maps_to_409(
    api_app: FastAPI, api_client: TestClient
) -> None:
    api_app.dependency_overrides[get_bank_transaction_service] = lambda: RaisingService(
        ConflictError("Idempotency key re-used with different payload"),
    )

    response = api_client.post(BASE_URL, json=_request_payload(), headers={"Idempotency-Key": "batch"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Idempotency key re-used with different payload"


def test_import_transactions_generic_service_error_maps_to_500(
    api_app: FastAPI, api_client: TestClient
) -> None:
    api_app.dependency_overrides[get_bank_transaction_service] = lambda: RaisingService(ServiceError("boom"))

    response = api_client.post(BASE_URL, json=_request_payload(), headers={"Idempotency-Key": "batch"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal service error"
