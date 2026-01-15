"""Unit tests for tenant REST endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import status
from fastapi.testclient import TestClient

from app.api.dependencies import get_tenant_service
from app.main import create_app
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.exceptions import ConflictError


def _client_with_service(service) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_tenant_service] = lambda: service
    try:
        client = TestClient(app)
    except Exception:
        app.dependency_overrides.clear()
        raise
    return client


def test_create_tenant_success() -> None:
    created_at = datetime.now(timezone.utc)
    expected = TenantRead(id="tenant-1", name="Acme Corp", created_at=created_at)

    class RecordingTenantService:
        def __init__(self) -> None:
            self.received: TenantCreate | None = None

        def create(self, payload: TenantCreate) -> TenantRead:
            self.received = payload
            return expected

        def list(self) -> list[TenantRead]:  # pragma: no cover - not used here
            raise AssertionError("list should not be called")

    service = RecordingTenantService()
    client = _client_with_service(service)

    try:
        response = client.post(
            "/api/tenants",
            json={"name": "Acme Corp"},
        )
    finally:
        client.app.dependency_overrides.clear()
        client.close()

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == {
        "id": "tenant-1",
        "name": "Acme Corp",
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    assert service.received == TenantCreate(name="Acme Corp")


def test_create_tenant_conflict_error() -> None:
    class ConflictTenantService:
        def create(self, payload: TenantCreate) -> TenantRead:  # pragma: no cover - return unused
            raise ConflictError("Tenant name already exists")

        def list(self) -> list[TenantRead]:  # pragma: no cover - not used here
            raise AssertionError("list should not be called")

    client = _client_with_service(ConflictTenantService())

    try:
        response = client.post(
            "/api/tenants",
            json={"name": "Existing Tenant"},
        )
    finally:
        client.app.dependency_overrides.clear()
        client.close()

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": "Tenant name already exists"}


def test_list_tenants_success() -> None:
    created_at = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    tenants = [
        TenantRead(id="tenant-1", name="Acme Corp", created_at=created_at),
        TenantRead(id="tenant-2", name="Beta LLC", created_at=created_at),
    ]

    class ListingTenantService:
        def create(self, payload: TenantCreate) -> TenantRead:  # pragma: no cover - not used here
            raise AssertionError("create should not be called")

        def list(self) -> list[TenantRead]:
            return tenants

    client = _client_with_service(ListingTenantService())

    try:
        response = client.get("/api/tenants")
    finally:
        client.app.dependency_overrides.clear()
        client.close()

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "id": "tenant-1",
            "name": "Acme Corp",
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
        },
        {
            "id": "tenant-2",
            "name": "Beta LLC",
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
        },
    ]
