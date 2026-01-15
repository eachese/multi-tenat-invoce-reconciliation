"""Unit tests for deterministic scoring heuristics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from app.db.models import BankTransaction, Invoice
from app.services.scoring import (
    MatchScore,
    ScoreComponent,
    format_reasoning,
    score_match,
)


@pytest.mark.parametrize(
    "achieved,expected",
    [(-0.5, 0.0), (0.75, 0.225), (1.5, 0.3)],
)
def test_score_component_contribution_clamps_to_unit_interval(achieved: float, expected: float) -> None:
    component = ScoreComponent(name="test", weight=0.3, achieved=achieved, detail="n/a")
    assert component.contribution == pytest.approx(expected)


@pytest.mark.parametrize(
    "total,label",
    [(0.2, "low"), (0.55, "medium"), (0.7999, "medium"), (0.8, "high"), (0.92, "high")],
)
def test_match_score_confidence_label_thresholds(total: float, label: str) -> None:
    match_score = MatchScore(total=total, components=[])
    assert match_score.confidence_label == label


@pytest.fixture
def perfect_invoice():
    return cast(
        Invoice,
        SimpleNamespace(
            amount=Decimal("200.00"),
            invoice_date=datetime(2024, 5, 20, tzinfo=timezone.utc).date(),
            description="Consulting Services", 
            vendor=SimpleNamespace(name="Acme"),
        ),
    )


@pytest.fixture
def perfect_transaction():
    return cast(
        BankTransaction,
        SimpleNamespace(
            amount=Decimal("200.00"),
            posted_at=datetime(2024, 5, 21, 14, 30, tzinfo=timezone.utc),
            description="Consulting Services for Acme",
        ),
    )


def test_score_match_perfect_alignment_yields_high_confidence(perfect_invoice, perfect_transaction) -> None:
    match_score = score_match(perfect_invoice, perfect_transaction)

    assert match_score.total == pytest.approx(1.0)
    assert match_score.confidence_label == "high"
    assert [component.name for component in match_score.components] == [
        "amount_exact",
        "amount_tolerance",
        "date",
        "description",
        "vendor_boost",
    ]
    details = {component.name: component.detail for component in match_score.components}
    assert details["amount_exact"] == "Exact amount match"
    assert details["vendor_boost"] == "Vendor name present in transaction memo"


def test_score_match_missing_date_and_description_is_medium(perfect_transaction) -> None:
    invoice = cast(
        Invoice,
        SimpleNamespace(
            amount=Decimal("200.00"),
            invoice_date=None,
            description=None,
            vendor=None,
        ),
    )

    match_score = score_match(invoice, perfect_transaction)

    assert match_score.total == pytest.approx(0.79, abs=1e-4)
    assert match_score.confidence_label == "medium"
    details = {component.name: component.detail for component in match_score.components}
    assert "Invoice date missing" in details["date"]
    assert details["description"] == "Limited description data"


def test_score_match_large_mismatch_is_low_confidence() -> None:
    invoice = cast(
        Invoice,
        SimpleNamespace(
            amount=Decimal("100.00"),
            invoice_date=datetime(2024, 1, 10, tzinfo=timezone.utc).date(),
            description="Retainer Fee",
            vendor=None,
        ),
    )
    transaction = cast(
        BankTransaction,
        SimpleNamespace(
            amount=Decimal("250.00"),
            posted_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            description=None,
        ),
    )

    match_score = score_match(invoice, transaction)

    assert match_score.total == pytest.approx(0.0)
    assert match_score.confidence_label == "low"
    details = {component.name: component.detail for component in match_score.components}
    assert details["amount_exact"] == "Amount diff $150.00"
    assert details["amount_tolerance"] == "Outside $1 tolerance (difference $150.00)"


def test_format_reasoning_mirrors_match_score_reasoning(perfect_invoice, perfect_transaction) -> None:
    match_score = score_match(perfect_invoice, perfect_transaction)
    assert format_reasoning(match_score) == match_score.reasoning_text()


def test_match_score_reasoning_text_orders_component_details() -> None:
    components = [
        ScoreComponent(name="first", weight=0.4, achieved=0.9, detail="Primary"),
        ScoreComponent(name="second", weight=0.3, achieved=0.5, detail="Secondary"),
    ]
    match_score = MatchScore(total=0.7, components=components)

    reasoning = match_score.reasoning_text()

    assert reasoning == "first: Primary (weight 0.40, achieved 0.90); second: Secondary (weight 0.30, achieved 0.50)"
