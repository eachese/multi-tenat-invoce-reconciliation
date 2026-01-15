"""Pydantic schemas for bank transaction import APIs."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, PositiveFloat


class BankTransactionRead(BaseModel):
    """Serialized bank transaction."""

    id: str
    tenant_id: str
    external_id: str | None
    posted_at: datetime
    amount: float
    currency: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class BankTransactionImportItem(BaseModel):
    """Represents a transaction within an import batch."""

    external_id: str | None = Field(default=None, max_length=128)
    posted_at: datetime
    amount: PositiveFloat
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=500)


class BankTransactionImportRequest(BaseModel):
    """Bulk import request payload."""

    transactions: list[BankTransactionImportItem]


class BankTransactionImportResponse(BaseModel):
    """Result of an import invocation."""

    created: int
    duplicates: int
    conflicts: int
    transactions: list[BankTransactionRead]
