"""Unit tests for invoice REST endpoints."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_invoice_service
from app.api.endpoints import invoices
from app.db.models import InvoiceStatus
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFilterParams,
    InvoiceListResponse,
    InvoiceRead,
)
from app.services.exceptions import NotFoundError, ValidationError

TENANT_ID = "tenant-123"


class ServiceStub:
    """Collects calls while returning configured results."""

    def __init__(self) -> None:
        self.create_calls: list[InvoiceCreate] = []
        self.list_calls: list[tuple[InvoiceFilterParams, int, int]] = []
        self.delete_calls: list[str] = []
        self.create_return: InvoiceRead | None = None
        self.create_exception: Exception | None = None
        self.list_return: InvoiceListResponse = InvoiceListResponse(items=[], total=0)
        self.list_exception: Exception | None = None
        self.delete_exception: Exception | None = None

    def create(self, payload: InvoiceCreate) -> InvoiceRead:
        self.create_calls.append(payload)
        if self.create_exception is not None:
            raise self.create_exception
        assert self.create_return is not None, "create_return must be set for successful calls"
        return self.create_return

    def list(self, filters: InvoiceFilterParams, offset: int = 0, limit: int = 100) -> InvoiceListResponse:
        self.list_calls.append((filters, offset, limit))
        if self.list_exception is not None:
            raise self.list_exception
        return self.list_return

    def delete(self, invoice_id: str) -> None:
        self.delete_calls.append(invoice_id)
        if self.delete_exception is not None:
            raise self.delete_exception


@pytest.fixture()
def api_client() -> tuple[TestClient, FastAPI]:
    app = FastAPI()
    app.include_router(invoices.router)

    with TestClient(app) as client:
        yield client, app
        app.dependency_overrides.clear()


def make_invoice_read(**overrides: object) -> InvoiceRead:
    base = {
        "id": "inv-1",
        "tenant_id": TENANT_ID,
        "vendor_id": None,
        "invoice_number": "2025-001",
        "amount": 150.75,
        "currency": "USD",
        "invoice_date": date(2025, 1, 1),
        "description": "Consulting",
        "status": InvoiceStatus.OPEN,
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return InvoiceRead(**base)


def test_create_invoice_returns_service_result(api_client: tuple[TestClient, FastAPI]) -> None:
    client, app = api_client
    invoice = make_invoice_read()

    service = ServiceStub()
    service.create_return = invoice
    app.dependency_overrides[get_invoice_service] = lambda: service

    payload = {"amount": 150.75, "currency": "usd"}
    response = client.post(f"/tenants/{TENANT_ID}/invoices", json=payload)

    assert response.status_code == 201
    assert len(service.create_calls) == 1
    create_payload = service.create_calls[0]
    assert isinstance(create_payload, InvoiceCreate)
    assert create_payload.amount == payload["amount"]
    assert create_payload.currency == "USD"

    body = response.json()
    assert body["id"] == invoice.id
    assert body["status"] == InvoiceStatus.OPEN.value


def test_create_invoice_maps_service_validation_errors(api_client: tuple[TestClient, FastAPI]) -> None:
    client, app = api_client

    service = ServiceStub()
    service.create_exception = ValidationError("Invalid invoice data")
    app.dependency_overrides[get_invoice_service] = lambda: service

    response = client.post(
        f"/tenants/{TENANT_ID}/invoices",
        json={"amount": 99.0, "currency": "usd"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid invoice data"}


def test_list_invoices_passes_filters_and_pagination(api_client: tuple[TestClient, FastAPI]) -> None:
    client, app = api_client
    invoice = make_invoice_read(id="inv-2", amount=210.5, invoice_number="2025-002")

    service = ServiceStub()
    service.list_return = InvoiceListResponse(items=[invoice], total=1)
    app.dependency_overrides[get_invoice_service] = lambda: service

    response = client.get(
        f"/tenants/{TENANT_ID}/invoices",
        params={
            "status": InvoiceStatus.OPEN.value,
            "vendor_id": "vendor-9",
            "min_amount": 100,
            "max_amount": 300,
            "offset": 2,
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert len(service.list_calls) == 1
    filters, offset, limit = service.list_calls[0]
    assert isinstance(filters, InvoiceFilterParams)
    assert filters.status == InvoiceStatus.OPEN
    assert filters.vendor_id == "vendor-9"
    assert filters.min_amount == 100
    assert filters.max_amount == 300
    assert offset == 2
    assert limit == 5

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == invoice.id


def test_delete_invoice_returns_no_content(api_client: tuple[TestClient, FastAPI]) -> None:
    client, app = api_client
    service = ServiceStub()
    app.dependency_overrides[get_invoice_service] = lambda: service

    response = client.delete(f"/tenants/{TENANT_ID}/invoices/inv-123")

    assert response.status_code == 204
    assert service.delete_calls == ["inv-123"]


def test_delete_invoice_maps_not_found(api_client: tuple[TestClient, FastAPI]) -> None:
    client, app = api_client
    service = ServiceStub()
    service.delete_exception = NotFoundError("Invoice not found")
    app.dependency_overrides[get_invoice_service] = lambda: service

    response = client.delete(f"/tenants/{TENANT_ID}/invoices/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Invoice not found"}
