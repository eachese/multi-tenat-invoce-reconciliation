"""Pydantic schemas for tenant operations."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """Payload to create a new tenant."""

    name: str = Field(..., min_length=1, max_length=255)


class TenantRead(BaseModel):
    """Tenant representation returned by APIs."""

    id: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True
