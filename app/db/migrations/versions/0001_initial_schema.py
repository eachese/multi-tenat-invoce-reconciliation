"""Initial schema for Flow RMS invoice reconciliation domain.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-01-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

invoice_status_enum = sa.Enum("open", "matched", "paid", "cancelled", name="invoice_status")
match_status_enum = sa.Enum("proposed", "confirmed", "rejected", name="match_status")
TENANT_PK = "tenant.id"

def upgrade() -> None:
    bind = op.get_bind()
    invoice_status_enum.create(bind, checkfirst=True)
    match_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "tenant",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "vendor",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], [TENANT_PK], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_vendor_name_per_tenant"),
    )

    op.create_table(
        "invoice",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=True),
        sa.Column("invoice_number", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", invoice_status_enum, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], [TENANT_PK], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "invoice_number", name="uq_invoice_number_per_tenant"),
    )

    op.create_table(
        "banktransaction",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], [TENANT_PK], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_transaction_external_id"),
    )

    op.create_table(
        "matchcandidate",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("bank_transaction_id", sa.String(length=36), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", match_status_enum, nullable=False, server_default="proposed"),
        sa.Column("reasoning", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], [TENANT_PK], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["banktransaction.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "invoice_id",
            "bank_transaction_id",
            name="uq_match_unique_pair",
        ),
    )

    op.create_table(
        "idempotencykey",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], [TENANT_PK], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_key"),
    )

    op.create_index("ix_vendor_tenant_id", "vendor", ["tenant_id"])
    op.create_index("ix_invoice_status", "invoice", ["tenant_id", "status"])
    op.create_index("ix_invoice_vendor", "invoice", ["tenant_id", "vendor_id"])
    op.create_index("ix_banktransaction_posted_at", "banktransaction", ["tenant_id", "posted_at"],)
    op.create_index("ix_match_status", "matchcandidate", ["tenant_id", "status"])
    op.create_index("ix_idempotencykey_tenant_id", "idempotencykey", ["tenant_id"])

def downgrade() -> None:
    op.drop_index("ix_idempotencykey_tenant_id", table_name="idempotencykey")
    op.drop_index("ix_match_status", table_name="matchcandidate")
    op.drop_index("ix_banktransaction_posted_at", table_name="banktransaction")
    op.drop_index("ix_invoice_vendor", table_name="invoice")
    op.drop_index("ix_invoice_status", table_name="invoice")
    op.drop_index("ix_vendor_tenant_id", table_name="vendor")

    op.drop_table("idempotencykey")
    op.drop_table("matchcandidate")
    op.drop_table("banktransaction")
    op.drop_table("invoice")
    op.drop_table("vendor")
    op.drop_table("tenant")

    bind = op.get_bind()
    match_status_enum.drop(bind, checkfirst=True)
    invoice_status_enum.drop(bind, checkfirst=True)
