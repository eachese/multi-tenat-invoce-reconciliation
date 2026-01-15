"""Tests for app.db package exports."""
from app.db import Base, TimestampMixin, models


def test_db_exports_expected_symbols() -> None:
    """The db package should expose Base, TimestampMixin, and models."""
    assert Base.__name__ == "Base"
    assert TimestampMixin.__name__ == "TimestampMixin"
    assert hasattr(models, "Tenant")
    assert hasattr(models, "Invoice")
