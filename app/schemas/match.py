"""Schemas for reconciliation and match endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.db.models import MatchStatus


class MatchCandidateRead(BaseModel):
    """Match candidate representation."""

    id: str
    invoice_id: str
    bank_transaction_id: str
    score: float = Field(ge=0, le=1)
    status: MatchStatus
    reasoning: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _isoformat_z(value)


class ReconciliationResponse(BaseModel):
    """Response returned by reconciliation endpoint."""

    matches: list[MatchCandidateRead]


class MatchConfirmationResponse(BaseModel):
    """Payload returned when a match is confirmed."""

    match: MatchCandidateRead
    invoice_status: str


class AIExplanationResponse(BaseModel):
    """Natural language explanation of a potential match."""

    explanation: str
    confidence: str | None = None

    @field_validator("explanation", "confidence")
    @classmethod
    def _strip_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def _isoformat_z(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso
