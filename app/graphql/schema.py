"""Strawberry GraphQL schema definition."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime
from typing import TypeVar
import strawberry
from graphql import GraphQLError
from strawberry.types import Info

from app.db.models import InvoiceStatus, MatchStatus
from app.graphql.context import GraphQLContext
from app.repositories.bank_transaction import BankTransactionRepository
from app.repositories.match import MatchRepository
from app.schemas.bank_transaction import (
    BankTransactionImportItem,
    BankTransactionImportRequest,
    BankTransactionImportResponse,
    BankTransactionRead,
)
from app.schemas.invoice import InvoiceCreate, InvoiceFilterParams, InvoiceListResponse, InvoiceRead
from app.schemas.match import (
    AIExplanationResponse,
    MatchCandidateRead,
    MatchConfirmationResponse,
    ReconciliationResponse,
)
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.bank_transaction_service import BankTransactionService
from app.services.exceptions import ServiceError
from app.services.explanation_service import ExplanationService
from app.services.invoice_service import InvoiceService
from app.services.reconciliation_service import ReconciliationService
from app.services.tenant_service import TenantService


ServiceType = TypeVar("ServiceType")
ResultType = TypeVar("ResultType")


InvoiceStatusEnum = strawberry.enum(InvoiceStatus, name="InvoiceStatus")
MatchStatusEnum = strawberry.enum(MatchStatus, name="MatchStatus")


@contextmanager
def _session_scope(context: GraphQLContext):
    session = context.get_session()
    try:
        yield session
    finally:
        session.close()


def _execute_with_service(
    info: Info[GraphQLContext, None],
    builder: Callable[["Session", GraphQLContext], ServiceType],
    executor: Callable[[ServiceType], ResultType],
) -> ResultType:
    from sqlalchemy.orm import Session  # local import to avoid circular dependency at module load

    context = info.context
    with _session_scope(context) as session:
        service = builder(session, context)
        try:
            return executor(service)
        except ServiceError as exc:
            raise GraphQLError(str(exc)) from exc


@strawberry.type
class HealthCheck:
    """Simple health payload for initial schema bootstrap."""

    status: str


@strawberry.type
class TenantType:
    id: strawberry.ID
    name: str
    created_at: datetime


@strawberry.type
class InvoiceType:
    id: strawberry.ID
    tenant_id: strawberry.ID
    vendor_id: strawberry.ID | None
    invoice_number: str | None
    amount: float
    currency: str
    invoice_date: date | None
    description: str | None
    status: InvoiceStatusEnum
    created_at: datetime


@strawberry.type
class InvoiceListType:
    items: list[InvoiceType]
    total: int


@strawberry.type
class BankTransactionType:
    id: strawberry.ID
    tenant_id: strawberry.ID
    external_id: str | None
    posted_at: datetime
    amount: float
    currency: str
    description: str | None
    created_at: datetime


@strawberry.type
class BankTransactionImportResult:
    created: int
    duplicates: int
    conflicts: int
    transactions: list[BankTransactionType]


@strawberry.type
class MatchCandidateType:
    id: strawberry.ID
    invoice_id: strawberry.ID
    bank_transaction_id: strawberry.ID
    score: float
    status: MatchStatusEnum
    reasoning: str | None
    created_at: datetime


@strawberry.type
class ReconciliationResult:
    matches: list[MatchCandidateType]


@strawberry.type
class MatchConfirmationResult:
    match: MatchCandidateType
    invoice_status: str


@strawberry.type
class AIExplanationType:
    explanation: str
    confidence: str | None


@strawberry.type
class SuccessResult:
    success: bool


@strawberry.input
class InvoiceCreateInput:
    amount: float
    currency: str = "USD"
    vendor_id: strawberry.ID | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    description: str | None = None


@strawberry.input
class InvoiceFilterInput:
    status: InvoiceStatusEnum | None = None
    vendor_id: strawberry.ID | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount: float | None = None
    max_amount: float | None = None


@strawberry.input
class BankTransactionImportItemInput:
    external_id: str | None = None
    posted_at: datetime
    amount: float
    currency: str = "USD"
    description: str | None = None


@strawberry.input
class BankTransactionImportInput:
    transactions: list[BankTransactionImportItemInput]


def _to_tenant_type(tenant: TenantRead) -> TenantType:
    return TenantType(id=tenant.id, name=tenant.name, created_at=tenant.created_at)


def _to_invoice_type(invoice: InvoiceRead) -> InvoiceType:
    return InvoiceType(
        id=invoice.id,
        tenant_id=invoice.tenant_id,
        vendor_id=invoice.vendor_id,
        invoice_number=invoice.invoice_number,
        amount=invoice.amount,
        currency=invoice.currency,
        invoice_date=invoice.invoice_date,
        description=invoice.description,
        status=InvoiceStatusEnum(invoice.status),
        created_at=invoice.created_at,
    )


def _to_invoice_list(response: InvoiceListResponse) -> InvoiceListType:
    return InvoiceListType(items=[_to_invoice_type(item) for item in response.items], total=response.total)


def _to_bank_transaction_type(transaction: BankTransactionRead) -> BankTransactionType:
    return BankTransactionType(
        id=transaction.id,
        tenant_id=transaction.tenant_id,
        external_id=transaction.external_id,
        posted_at=transaction.posted_at,
        amount=transaction.amount,
        currency=transaction.currency,
        description=transaction.description,
        created_at=transaction.created_at,
    )


def _to_import_result(response: BankTransactionImportResponse) -> BankTransactionImportResult:
    return BankTransactionImportResult(
        created=response.created,
        duplicates=response.duplicates,
        conflicts=response.conflicts,
        transactions=[_to_bank_transaction_type(txn) for txn in response.transactions],
    )


def _to_match_type(candidate: MatchCandidateRead) -> MatchCandidateType:
    return MatchCandidateType(
        id=candidate.id,
        invoice_id=candidate.invoice_id,
        bank_transaction_id=candidate.bank_transaction_id,
        score=candidate.score,
        status=MatchStatusEnum(candidate.status),
        reasoning=candidate.reasoning,
        created_at=candidate.created_at,
    )


def _to_reconciliation_result(response: ReconciliationResponse) -> ReconciliationResult:
    return ReconciliationResult(matches=[_to_match_type(item) for item in response.matches])


def _to_confirmation_result(response: MatchConfirmationResponse) -> MatchConfirmationResult:
    return MatchConfirmationResult(
        match=_to_match_type(response.match),
        invoice_status=response.invoice_status,
    )


def _to_ai_explanation(response: AIExplanationResponse) -> AIExplanationType:
    return AIExplanationType(explanation=response.explanation, confidence=response.confidence)


def _build_invoice_filters(filters: InvoiceFilterInput | None) -> InvoiceFilterParams:
    if filters is None:
        return InvoiceFilterParams()
    return InvoiceFilterParams(
        status=filters.status,
        vendor_id=str(filters.vendor_id) if filters.vendor_id is not None else None,
        start_date=filters.start_date,
        end_date=filters.end_date,
        min_amount=filters.min_amount,
        max_amount=filters.max_amount,
    )


def _build_import_request(payload: BankTransactionImportInput) -> BankTransactionImportRequest:
    items: list[BankTransactionImportItem] = []
    for item in payload.transactions:
        items.append(
            BankTransactionImportItem(
                external_id=item.external_id,
                posted_at=item.posted_at,
                amount=item.amount,
                currency=item.currency,
                description=item.description,
            )
        )
    return BankTransactionImportRequest(transactions=items)


@strawberry.type
class Query:
    """Root GraphQL query type."""

    @strawberry.field(description="Basic service liveness check")
    def health(self) -> HealthCheck:
        return HealthCheck(status="ok")

    @strawberry.field(description="List all tenants")
    def tenants(self, info: Info[GraphQLContext, None]) -> list[TenantType]:
        result = _execute_with_service(
            info,
            lambda session, _context: TenantService(session),
            lambda service: service.list(),
        )
        return [_to_tenant_type(item) for item in result]

    @strawberry.field(description="List tenant invoices with optional filters")
    def invoices(
        self,
        info: Info[GraphQLContext, None],
        filters: InvoiceFilterInput | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> InvoiceListType:
        response = _execute_with_service(
            info,
            lambda session, context: InvoiceService(session, context.tenant),
            lambda service: service.list(_build_invoice_filters(filters), offset=offset, limit=limit),
        )
        return _to_invoice_list(response)

    @strawberry.field(description="List bank transactions for the current tenant")
    def bank_transactions(
        self,
        info: Info[GraphQLContext, None],
        offset: int = 0,
        limit: int = 100,
    ) -> list[BankTransactionType]:
        rows = _execute_with_service(
            info,
            lambda session, context: BankTransactionService(session, context.tenant),
            lambda service: service.list_transactions(offset=offset, limit=limit),
        )
        return [_to_bank_transaction_type(item) for item in rows]

    @strawberry.field(description="List match candidates, optionally filtered by status")
    def match_candidates(
        self,
        info: Info[GraphQLContext, None],
        status: MatchStatusEnum | None = None,
    ) -> list[MatchCandidateType]:
        status_filter = status if status is None else MatchStatus(status.value)
        rows = _execute_with_service(
            info,
            lambda session, context: ReconciliationService(session, context.tenant),
            lambda service: service.list_matches(status=status_filter),
        )
        return [_to_match_type(item) for item in rows]

    @strawberry.field(description="Explain reconciliation for a specific invoice/transaction pair")
    def explain_reconciliation(
        self,
        info: Info[GraphQLContext, None],
        invoice_id: strawberry.ID,
        bank_transaction_id: strawberry.ID,
    ) -> AIExplanationType:
        response = _execute_with_service(
            info,
            lambda session, context: ExplanationService(session, context.tenant),
            lambda service: service.explain_pair(str(invoice_id), str(bank_transaction_id)),
        )
        return _to_ai_explanation(response)


@strawberry.type
class Mutation:
    """Root GraphQL mutation type."""

    @strawberry.mutation(description="Create a new tenant")
    def create_tenant(self, info: Info[GraphQLContext, None], name: str) -> TenantType:
        tenant = _execute_with_service(
            info,
            lambda session, _context: TenantService(session),
            lambda service: service.create(TenantCreate(name=name)),
        )
        return _to_tenant_type(tenant)

    @strawberry.mutation(description="Create an invoice for the current tenant")
    def create_invoice(
        self,
        info: Info[GraphQLContext, None],
        payload: InvoiceCreateInput,
    ) -> InvoiceType:
        invoice = _execute_with_service(
            info,
            lambda session, context: InvoiceService(session, context.tenant),
            lambda service: service.create(
                InvoiceCreate(
                    amount=payload.amount,
                    currency=payload.currency,
                    vendor_id=str(payload.vendor_id) if payload.vendor_id is not None else None,
                    invoice_number=payload.invoice_number,
                    invoice_date=payload.invoice_date,
                    description=payload.description,
                )
            ),
        )
        return _to_invoice_type(invoice)

    @strawberry.mutation(description="Delete an invoice for the current tenant")
    def delete_invoice(
        self,
        info: Info[GraphQLContext, None],
        invoice_id: strawberry.ID,
    ) -> SuccessResult:
        _execute_with_service(
            info,
            lambda session, context: InvoiceService(session, context.tenant),
            lambda service: service.delete(str(invoice_id)),
        )
        return SuccessResult(success=True)

    @strawberry.mutation(description="Import bank transactions for the current tenant")
    def import_bank_transactions(
        self,
        info: Info[GraphQLContext, None],
        payload: BankTransactionImportInput,
        idempotency_key: str,
    ) -> BankTransactionImportResult:
        response = _execute_with_service(
            info,
            lambda session, context: BankTransactionService(session, context.tenant),
            lambda service: service.import_transactions(_build_import_request(payload), idempotency_key),
        )
        return _to_import_result(response)

    @strawberry.mutation(description="Run reconciliation for the current tenant")
    def reconcile(self, info: Info[GraphQLContext, None]) -> ReconciliationResult:
        response = _execute_with_service(
            info,
            lambda session, context: ReconciliationService(session, context.tenant),
            lambda service: service.reconcile(),
        )
        return _to_reconciliation_result(response)

    @strawberry.mutation(description="Confirm a proposed match")
    def confirm_match(
        self,
        info: Info[GraphQLContext, None],
        match_id: strawberry.ID,
    ) -> MatchConfirmationResult:
        response = _execute_with_service(
            info,
            lambda session, context: ReconciliationService(session, context.tenant),
            lambda service: service.confirm_match(str(match_id)),
        )
        return _to_confirmation_result(response)


schema = strawberry.Schema(query=Query, mutation=Mutation)
