"""Pydantic schemas for invoice endpoints."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, PositiveFloat, field_validator

from app.db.models import InvoiceStatus


class InvoiceCreate(BaseModel):
    """Payload for creating invoices."""

    amount: PositiveFloat
    currency: str = Field(default="USD", min_length=3, max_length=3)
    vendor_id: str | None = None
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    description: str | None = Field(default=None, max_length=500)

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, value: str) -> str:
        return value.upper()


class InvoiceRead(BaseModel):
    """Invoice representation returned to clients."""

    id: str
    tenant_id: str
    vendor_id: str | None
    invoice_number: str | None
    amount: float
    currency: str
    invoice_date: date | None
    description: str | None
    status: InvoiceStatus
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceFilterParams(BaseModel):
    """Query parameters for invoice listing."""

    status: InvoiceStatus | None = None
    vendor_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)


class InvoiceListResponse(BaseModel):
    """Paginated invoice list."""

    items: list[InvoiceRead]
    total: int
