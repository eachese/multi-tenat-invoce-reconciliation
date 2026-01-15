"""End-to-end tests covering REST flows."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi import status

from app.db.models import InvoiceStatus


def _invoice_payload(amount: float, description: str) -> dict[str, object]:
    return {
        "amount": amount,
        "currency": "usd",
        "invoice_date": date.today().isoformat(),
        "description": description,
    }


def _import_payload(amount: float, description: str) -> dict[str, object]:
    return {
        "transactions": [
            {
                "external_id": f"txn-{uuid4()}",
                "posted_at": datetime.now(tz=timezone.utc).isoformat(),
                "amount": amount,
                "currency": "USD",
                "description": description,
            }
        ]
    }


def test_invoice_crud_flow(client, tenant) -> None:
    base_url = f"/api/tenants/{tenant.id}/invoices"

    create_resp = client.post(base_url, json=_invoice_payload(125.0, "Initial invoice"))
    assert create_resp.status_code == status.HTTP_201_CREATED
    created_invoice = create_resp.json()
    assert created_invoice["currency"] == "USD"

    second_resp = client.post(base_url, json=_invoice_payload(250.0, "Second invoice"))
    assert second_resp.status_code == status.HTTP_201_CREATED

    list_resp = client.get(
        base_url,
        params={
            "status": InvoiceStatus.OPEN.value,
            "max_amount": 150,
        },
    )
    assert list_resp.status_code == status.HTTP_200_OK
    data = list_resp.json()
    assert data["total"] == 1
    assert data["items"][0]["description"] == "Initial invoice"

    delete_resp = client.delete(f"{base_url}/{created_invoice['id']}")
    assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

    after_resp = client.get(base_url)
    assert after_resp.status_code == status.HTTP_200_OK
    remaining_ids = {item["id"] for item in after_resp.json()["items"]}
    assert created_invoice["id"] not in remaining_ids


def test_bank_transaction_import_idempotency(client, tenant) -> None:
    url = f"/api/tenants/{tenant.id}/bank-transactions/import"
    payload = _import_payload(200.0, "Consulting Services")

    headers = {"Idempotency-Key": "batch-1"}
    first = client.post(url, json=payload, headers=headers)
    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert first_body["created"] == 1
    assert first_body["duplicates"] == 0

    second = client.post(url, json=payload, headers=headers)
    assert second.status_code == status.HTTP_200_OK
    assert second.json() == first_body

    conflict_payload = _import_payload(300.0, "Different memo")
    conflict = client.post(url, json=conflict_payload, headers=headers)
    assert conflict.status_code == status.HTTP_409_CONFLICT


def _seed_match(client, tenant) -> dict[str, object]:
    invoice_resp = client.post(
        f"/api/tenants/{tenant.id}/invoices",
        json=_invoice_payload(200.0, "Consulting Services"),
    )
    assert invoice_resp.status_code == status.HTTP_201_CREATED

    import_resp = client.post(
        f"/api/tenants/{tenant.id}/bank-transactions/import",
        json=_import_payload(200.0, "Consulting Services"),
        headers={"Idempotency-Key": f"match-{uuid4()}"},
    )
    assert import_resp.status_code == status.HTTP_200_OK

    reconcile_resp = client.post(f"/api/tenants/{tenant.id}/reconcile")
    assert reconcile_resp.status_code == status.HTTP_200_OK
    matches = reconcile_resp.json()["matches"]
    assert matches
    return matches[0]


def test_reconciliation_match_confirmation_flow(client, tenant) -> None:
    match = _seed_match(client, tenant)

    confirm_resp = client.post(f"/api/tenants/{tenant.id}/matches/{match['id']}/confirm")
    assert confirm_resp.status_code == status.HTTP_200_OK
    assert confirm_resp.json()["invoice_status"] == "matched"

    rerun_resp = client.post(f"/api/tenants/{tenant.id}/reconcile")
    assert rerun_resp.status_code == status.HTTP_200_OK
    assert rerun_resp.json()["matches"] == []


def test_ai_explanation_endpoint_success(client, tenant, monkeypatch) -> None:
    match = _seed_match(client, tenant)

    class FakeAI:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def explain(self, context) -> tuple[str, str | None]:  # type: ignore[override]
            self.calls.append(context)
            return "AI explanation", "high"

    class FakeFallback:
        def __init__(self) -> None:
            self.calls = 0

        def explain(self, context) -> tuple[str, str | None]:  # type: ignore[override]
            self.calls += 1
            return "Fallback explanation", "low"

    fake_ai = FakeAI()
    fake_fallback = FakeFallback()

    monkeypatch.setattr(
        "app.services.explanation_service.resolve_ai_client",
        lambda model, key: fake_ai,
    )
    monkeypatch.setattr(
        "app.services.explanation_service.fallback_client",
        lambda: fake_fallback,
    )

    response = client.get(
        f"/api/tenants/{tenant.id}/reconcile/explain",
        params={
            "invoice_id": match["invoice_id"],
            "bank_transaction_id": match["bank_transaction_id"],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["explanation"] == "AI explanation"
    assert body["confidence"] == "high"
    assert len(fake_ai.calls) == 1
    assert fake_fallback.calls == 0


def test_ai_explanation_endpoint_fallback(client, tenant, monkeypatch) -> None:
    match = _seed_match(client, tenant)

    class FailingAI:
        def explain(self, context) -> tuple[str, str | None]:  # type: ignore[override]
            raise RuntimeError("boom")

    class TrackingFallback:
        def __init__(self) -> None:
            self.calls = 0

        def explain(self, context) -> tuple[str, str | None]:  # type: ignore[override]
            self.calls += 1
            return "Fallback explanation", "low"

    fake_fallback = TrackingFallback()

    monkeypatch.setattr(
        "app.services.explanation_service.resolve_ai_client",
        lambda model, key: FailingAI(),
    )
    monkeypatch.setattr(
        "app.services.explanation_service.fallback_client",
        lambda: fake_fallback,
    )

    response = client.get(
        f"/api/tenants/{tenant.id}/reconcile/explain",
        params={
            "invoice_id": match["invoice_id"],
            "bank_transaction_id": match["bank_transaction_id"],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["explanation"] == "Fallback explanation"
    assert body["confidence"] == "low"
    assert fake_fallback.calls == 1
