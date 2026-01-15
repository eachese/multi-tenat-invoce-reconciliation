"""Deterministic reconciliation scoring heuristics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from decimal import Decimal

from app.db.models import BankTransaction, Invoice


@dataclass(slots=True)
class ScoreComponent:
    """Represents individual heuristic contribution."""

    name: str
    weight: float
    achieved: float
    detail: str

    @property
    def contribution(self) -> float:
        normalized = max(0.0, min(self.achieved, 1.0))
        return self.weight * normalized


@dataclass(slots=True)
class MatchScore:
    """Composite score built from components."""

    total: float
    components: list[ScoreComponent]

    @property
    def confidence_label(self) -> str:
        if self.total >= 0.8:
            return "high"
        if self.total >= 0.55:
            return "medium"
        return "low"

    def reasoning_text(self) -> str:
        parts = [f"{c.name}: {c.detail} (weight {c.weight:.2f}, achieved {c.achieved:.2f})" for c in self.components]
        return "; ".join(parts)


def _exact_amount_component(amount_diff: float) -> ScoreComponent:
    achieved = 1.0 if amount_diff <= 0.01 else 0.0
    detail = "Exact amount match" if achieved else f"Amount diff ${amount_diff:.2f}"
    return ScoreComponent(name="amount_exact", weight=0.5, achieved=achieved, detail=detail)


def _tolerance_component(amount_diff: float) -> ScoreComponent:
    if amount_diff <= 1.0:
        achieved = max(0.0, 1.0 - amount_diff)
        detail = f"Within $1 tolerance (difference ${amount_diff:.2f})"
    else:
        achieved = 0.0
        detail = f"Outside $1 tolerance (difference ${amount_diff:.2f})"
    return ScoreComponent(name="amount_tolerance", weight=0.2, achieved=achieved, detail=detail)


def _date_component(invoice_date: date | None, posted_at: date) -> ScoreComponent:
    if invoice_date is None:
        return ScoreComponent(
            name="date",
            weight=0.2,
            achieved=0.3,
            detail="Invoice date missing; partial credit",
        )
    days = abs((posted_at - invoice_date).days)
    if days <= 3:
        achieved = 1.0
        detail = "Transaction within ±3 days"
    elif days <= 7:
        achieved = 0.5
        detail = f"Transaction within ±7 days ({days} days apart)"
    else:
        achieved = 0.0
        detail = f"Transaction {days} days apart"
    return ScoreComponent(name="date", weight=0.2, achieved=achieved, detail=detail)


def _description_component(invoice_description: str | None, txn_description: str | None) -> ScoreComponent:
    if not invoice_description or not txn_description:
        return ScoreComponent(
            name="description",
            weight=0.1,
            achieved=0.3 if invoice_description or txn_description else 0.0,
            detail="Limited description data",
        )
    ratio = SequenceMatcher(None, invoice_description.lower(), txn_description.lower()).ratio()
    detail = f"Text similarity {ratio:.2f}"
    return ScoreComponent(name="description", weight=0.1, achieved=ratio, detail=detail)


def _vendor_component(vendor_name: str | None, txn_description: str | None) -> ScoreComponent:
    if not vendor_name:
        return ScoreComponent(name="vendor_boost", weight=0.05, achieved=0.0, detail="No vendor specified")
    if not txn_description:
        return ScoreComponent(
            name="vendor_boost",
            weight=0.05,
            achieved=0.2,
            detail="Vendor known but transaction lacks memo",
        )
    achieved = 1.0 if vendor_name.lower() in txn_description.lower() else 0.0
    detail = "Vendor name present in transaction memo" if achieved else "Vendor not referenced in memo"
    return ScoreComponent(name="vendor_boost", weight=0.05, achieved=achieved, detail=detail)


def score_match(invoice: Invoice, transaction: BankTransaction) -> MatchScore:
    """Compute heuristic score for an invoice/transaction pair."""

    invoice_amount = getattr(invoice, "amount", Decimal("0"))
    txn_amount = getattr(transaction, "amount", Decimal("0"))
    amount_diff = abs(float(invoice_amount) - float(txn_amount))
    components: list[ScoreComponent] = [
        _exact_amount_component(amount_diff),
        _tolerance_component(amount_diff),
        _date_component(invoice.invoice_date, transaction.posted_at.date()),
        _description_component(invoice.description, transaction.description),
    ]

    vendor_name = getattr(getattr(invoice, "vendor", None), "name", None)
    components.append(_vendor_component(vendor_name, transaction.description))

    total = sum(component.contribution for component in components)
    total = round(min(total, 1.0), 4)
    return MatchScore(total=total, components=components)


def format_reasoning(match_score: MatchScore) -> str:
    """Produce a human-readable reasoning summary."""

    return match_score.reasoning_text()
