"""Unit tests for match-related Pydantic schemas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.db.models import MatchStatus
from app.schemas.match import (
    AIExplanationResponse,
    MatchCandidateRead,
    MatchConfirmationResponse,
    ReconciliationResponse,
)


FIXED_TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _match_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "match-1",
        "invoice_id": "invoice-42",
        "bank_transaction_id": "txn-99",
        "score": 0.85,
        "status": MatchStatus.PROPOSED,
        "reasoning": "Solid metadata alignment",
        "created_at": FIXED_TIMESTAMP,
    }
    payload.update(overrides)
    return payload


def test_match_candidate_read_accepts_valid_payload() -> None:
    candidate = MatchCandidateRead(**_match_payload())

    assert candidate.id == "match-1"
    assert candidate.score == pytest.approx(0.85)
    assert candidate.status is MatchStatus.PROPOSED
    assert candidate.created_at == FIXED_TIMESTAMP


@pytest.mark.parametrize("score", [-0.01, 1.1])
def test_match_candidate_read_rejects_scores_outside_unit_interval(score: float) -> None:
    with pytest.raises(ValidationError):
        MatchCandidateRead(**_match_payload(score=score))


def test_match_candidate_read_supports_from_attributes() -> None:
    class ORMStub:
        def __init__(self, **attrs: object) -> None:
            for key, value in attrs.items():
                setattr(self, key, value)

    orm_object = ORMStub(**_match_payload(status="confirmed"))

    candidate = MatchCandidateRead.model_validate(orm_object)

    assert candidate.status is MatchStatus.CONFIRMED
    assert candidate.reasoning == "Solid metadata alignment"


def test_reconciliation_response_wraps_candidates() -> None:
    candidate = MatchCandidateRead(**_match_payload())

    response = ReconciliationResponse(matches=[candidate])

    assert response.matches == [candidate]


def test_reconciliation_response_requires_match_items() -> None:
    with pytest.raises(ValidationError):
        ReconciliationResponse(matches=[None])  # type: ignore[arg-type]


def test_match_confirmation_response_returns_match_and_invoice_status() -> None:
    candidate = MatchCandidateRead(**_match_payload())

    response = MatchConfirmationResponse(match=candidate, invoice_status="matched")

    assert response.match == candidate
    assert response.invoice_status == "matched"


def test_ai_explanation_response_with_optional_confidence() -> None:
    response = AIExplanationResponse(explanation="High overlap", confidence="medium")

    assert response.explanation == "High overlap"
    assert response.confidence == "medium"


def test_ai_explanation_response_defaults_confidence_to_none() -> None:
    response = AIExplanationResponse(explanation="Reasoning unavailable")

    assert response.confidence is None
