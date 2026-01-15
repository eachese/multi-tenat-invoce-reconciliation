"""Tests for app.db.base module."""
from datetime import datetime

from app.db import models


def test_base_declares_lowercase_tablenames() -> None:
    """Declarative base should derive lowercase tablenames from class names."""
    assert models.Tenant.__tablename__ == "tenant"
    assert models.BankTransaction.__tablename__ == "banktransaction"


def test_timestamp_mixin_populates_created_at(session, tenant) -> None:
    """TimestampMixin should automatically populate created_at via database default."""
    vendor = models.Vendor(name="Acme", tenant_id=tenant.id)
    session.add(vendor)
    session.commit()
    session.refresh(vendor)

    assert isinstance(vendor.created_at, datetime)
