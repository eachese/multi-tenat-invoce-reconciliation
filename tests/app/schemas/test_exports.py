"""Tests for the :mod:`app.schemas` package exports."""
from __future__ import annotations

import importlib


def _resolve(module_path: str, attribute: str):
    module = importlib.import_module(module_path)
    return getattr(module, attribute)


def test_all_exports_match_expected() -> None:
    schemas_module = importlib.import_module("app.schemas")

    export_sources = {
        "TenantCreate": ("app.schemas.tenant", "TenantCreate"),
        "TenantRead": ("app.schemas.tenant", "TenantRead"),
        "InvoiceCreate": ("app.schemas.invoice", "InvoiceCreate"),
        "InvoiceRead": ("app.schemas.invoice", "InvoiceRead"),
        "InvoiceListResponse": ("app.schemas.invoice", "InvoiceListResponse"),
        "InvoiceFilterParams": ("app.schemas.invoice", "InvoiceFilterParams"),
        "BankTransactionImportItem": ("app.schemas.bank_transaction", "BankTransactionImportItem"),
        "BankTransactionImportRequest": ("app.schemas.bank_transaction", "BankTransactionImportRequest"),
        "BankTransactionRead": ("app.schemas.bank_transaction", "BankTransactionRead"),
        "BankTransactionImportResponse": ("app.schemas.bank_transaction", "BankTransactionImportResponse"),
        "MatchCandidateRead": ("app.schemas.match", "MatchCandidateRead"),
        "ReconciliationResponse": ("app.schemas.match", "ReconciliationResponse"),
        "MatchConfirmationResponse": ("app.schemas.match", "MatchConfirmationResponse"),
        "AIExplanationResponse": ("app.schemas.match", "AIExplanationResponse"),
    }

    expected_order = list(export_sources)
    assert schemas_module.__all__ == expected_order
    assert len(set(schemas_module.__all__)) == len(expected_order)

    for export_name, (module_path, attr_name) in export_sources.items():
        assert getattr(schemas_module, export_name) is _resolve(module_path, attr_name)
