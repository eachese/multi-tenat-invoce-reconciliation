"""ORM model definitions for Flow RMS."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as SQLEnum, ForeignKey, Index, Numeric, String, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

DELETE_CASCADE = "all, delete-orphan"

UUID_STR = String(36)
CURRENCY_CODE = String(3)
DEFAULT_CURRENCY = "USD"


class InvoiceStatus(str, Enum):
    """Lifecycle state for invoices."""

    OPEN = "open"
    MATCHED = "matched"
    PAID = "paid"
    CANCELLED = "cancelled"


class MatchStatus(str, Enum):
    """States for reconciliation matches."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Tenant(Base, TimestampMixin):
    """Tenant represents an isolated organization."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    vendors: Mapped[list["Vendor"]] = relationship("Vendor", back_populates="tenant", cascade=DELETE_CASCADE)
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="tenant", cascade=DELETE_CASCADE)
    bank_transactions: Mapped[list["BankTransaction"]] = relationship(
        "BankTransaction", back_populates="tenant", cascade=DELETE_CASCADE
    )
    matches: Mapped[list["MatchCandidate"]] = relationship(
        "MatchCandidate", back_populates="tenant", cascade=DELETE_CASCADE
    )


class TenantScopedMixin(TimestampMixin):
    """Mixin for tenant-scoped entities."""

    tenant_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("tenant.id", ondelete="cascade"), nullable=False, index=True)


class Vendor(TenantScopedMixin, Base):
    """Vendor associated with a tenant."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="vendors")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="vendor")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_vendor_name_per_tenant"),
    )


class Invoice(TenantScopedMixin, Base):
    """Invoice issued by a tenant."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    vendor_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("vendor.id", ondelete="set null"), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CURRENCY_CODE, nullable=False, default=DEFAULT_CURRENCY)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        SQLEnum(InvoiceStatus, name="invoice_status"), default=InvoiceStatus.OPEN, nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="invoices")
    vendor: Mapped[Vendor | None] = relationship("Vendor", back_populates="invoices")
    matches: Mapped[list["MatchCandidate"]] = relationship("MatchCandidate", back_populates="invoice")

    __table_args__ = (
        Index("ix_invoice_status", "tenant_id", "status"),
        Index("ix_invoice_vendor", "tenant_id", "vendor_id"),
        UniqueConstraint("tenant_id", "invoice_number", name="uq_invoice_number_per_tenant"),
    )


class BankTransaction(TenantScopedMixin, Base):
    """Bank transaction imported for reconciliation."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CURRENCY_CODE, nullable=False, default=DEFAULT_CURRENCY)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="bank_transactions")
    matches: Mapped[list["MatchCandidate"]] = relationship("MatchCandidate", back_populates="bank_transaction")

    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_transaction_external_id"),
        Index("ix_transaction_posted_at", "tenant_id", "posted_at"),
    )


class MatchCandidate(TenantScopedMixin, Base):
    """Proposed or finalized match between invoice and bank transaction."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    invoice_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("invoice.id", ondelete="cascade"), nullable=False)
    bank_transaction_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("banktransaction.id", ondelete="cascade"), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        SQLEnum(MatchStatus, name="match_status"), default=MatchStatus.PROPOSED, nullable=False
    )
    reasoning: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="matches")
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="matches")
    bank_transaction: Mapped[BankTransaction] = relationship("BankTransaction", back_populates="matches")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "invoice_id",
            "bank_transaction_id",
            name="uq_match_unique_pair",
        ),
        Index("ix_match_status", "tenant_id", "status"),
    )


class IdempotencyKey(TenantScopedMixin, Base):
    """Persisted idempotency key usage for POST operations."""

    id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_key"),
    )


__all__ = [
    "Tenant",
    "Vendor",
    "Invoice",
    "BankTransaction",
    "MatchCandidate",
    "IdempotencyKey",
    "InvoiceStatus",
    "MatchStatus",
]
