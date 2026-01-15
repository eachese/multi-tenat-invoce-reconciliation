"""Unit tests for tenant Pydantic schemas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.tenant import TenantCreate, TenantRead


def test_tenant_create_accepts_valid_name() -> None:
    payload = TenantCreate(name="Acme Corp")

    assert payload.name == "Acme Corp"


def test_tenant_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError) as excinfo:
        TenantCreate(name="")

    (error,) = excinfo.value.errors()
    assert error["loc"] == ("name",)
    assert error["type"] == "string_too_short"


def test_tenant_create_rejects_name_exceeding_max_length() -> None:
    with pytest.raises(ValidationError) as excinfo:
        TenantCreate(name="a" * 256)

    (error,) = excinfo.value.errors()
    assert error["loc"] == ("name",)
    assert error["type"] == "string_too_long"


def test_tenant_read_supports_model_validate_from_attributes() -> None:
    created_at = datetime.now(timezone.utc)

    class FakeTenant:
        def __init__(self) -> None:
            self.id = "tenant-123"
            self.name = "Acme Corp"
            self.created_at = created_at

    tenant = FakeTenant()

    read_model = TenantRead.model_validate(tenant)

    assert read_model.id == "tenant-123"
    assert read_model.name == "Acme Corp"
    assert read_model.created_at == created_at
