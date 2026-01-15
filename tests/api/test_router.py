"""Unit tests for the root API router configuration."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import bank_transactions, invoices, reconciliation, tenants
from app.api.router import router


def _create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_health_check_returns_ok() -> None:
    client = _create_test_client()
    try:
        response = client.get("/api/health")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_route_metadata() -> None:
    health_route = next(route for route in router.routes if route.path == "/health")

    assert health_route.summary == "Health check"
    assert health_route.tags == ["health"]


def test_router_includes_all_endpoint_modules() -> None:
    endpoints = {route.endpoint for route in router.routes}

    assert tenants.create_tenant in endpoints
    assert tenants.list_tenants in endpoints
    assert invoices.create_invoice in endpoints
    assert invoices.list_invoices in endpoints
    assert invoices.delete_invoice in endpoints
    assert bank_transactions.import_transactions in endpoints
    assert reconciliation.reconcile in endpoints
    assert reconciliation.confirm_match in endpoints
    assert reconciliation.explain_match in endpoints
