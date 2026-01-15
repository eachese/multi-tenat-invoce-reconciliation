"""Schemas for reconciliation and match endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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

    class Config:
        from_attributes = True


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
