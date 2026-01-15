"""Service handling bank transaction import and retrieval."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.db.models import BankTransaction, IdempotencyKey
from app.repositories.bank_transaction import BankTransactionRepository
from app.repositories.idempotency import IdempotencyRepository
from app.schemas.bank_transaction import (
    BankTransactionImportItem,
    BankTransactionImportRequest,
    BankTransactionImportResponse,
    BankTransactionRead,
)
from app.utils.hash import stable_hash

from .exceptions import ConflictError, ValidationError


class BankTransactionService:
    """Coordinate tenant-scoped bank transaction operations."""

    IDEMPOTENCY_ENDPOINT = "bank_transactions_import"

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self.session = session
        self.tenant = tenant
        self.transactions = BankTransactionRepository(session)
        self.idempotency = IdempotencyRepository(session)

    def import_transactions(
        self,
        payload: BankTransactionImportRequest,
        idempotency_key: str | None,
    ) -> BankTransactionImportResponse:
        if idempotency_key is None:
            raise ValidationError("Idempotency-Key header is required for imports")

        payload_hash = stable_hash([item.model_dump() for item in payload.transactions])
        existing = self.idempotency.get_key(self.tenant, self.IDEMPOTENCY_ENDPOINT, idempotency_key)
        if existing:
            if existing.payload_hash != payload_hash:
                raise ConflictError("Idempotency key re-used with different payload")
            return self._deserialize_response(existing)

        external_map = self.transactions.get_by_external_ids(
            self.tenant, (item.external_id for item in payload.transactions)
        )

        seen_external_ids: set[str] = set()
        created_entities: list[BankTransaction] = []
        duplicates = 0

        for item in payload.transactions:
            normalized_id = self._normalize_external_id(item.external_id)
            duplicate_reason = self._duplicate_reason(normalized_id, external_map, seen_external_ids)
            if duplicate_reason == "payload":
                raise ConflictError("Duplicate external IDs found within import payload")
            if duplicate_reason == "existing":
                duplicates += 1
                continue
            created_entities.append(self._build_entity(item, normalized_id))

        self.session.add_all(created_entities)

        try:
            self.session.flush()
            for entity in created_entities:
                self.session.refresh(entity)
            response = BankTransactionImportResponse(
                created=len(created_entities),
                duplicates=duplicates,
                conflicts=0,
                transactions=[self._serialize_entity(entity) for entity in created_entities],
            )

            serialized_response = response.model_dump(mode="json")

            record = IdempotencyKey(
                tenant_id=self.tenant.tenant_id,
                endpoint=self.IDEMPOTENCY_ENDPOINT,
                key=idempotency_key,
                payload_hash=payload_hash,
                response_status=200,
                response_body=serialized_response,
            )
            self.session.add(record)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Failed to import transactions due to database constraint") from exc

        return response

    @staticmethod
    def _normalize_external_id(external_id: str | None) -> str | None:
        if external_id is None:
            return None
        trimmed = external_id.strip()
        return trimmed or None

    def _build_entity(
        self,
        item: BankTransactionImportItem,
        external_id: str | None,
    ) -> BankTransaction:
        entity = BankTransaction(
            tenant_id=self.tenant.tenant_id,
            external_id=external_id,
            posted_at=item.posted_at,
            amount=Decimal(str(item.amount)),
            currency=item.currency.upper(),
            description=item.description,
        )
        return entity

    @staticmethod
    def _duplicate_reason(
        external_id: str | None,
        existing_ids: dict[str, BankTransaction],
        seen_external_ids: set[str],
    ) -> str | None:
        if external_id is None:
            return None
        if external_id in seen_external_ids:
            return "payload"
        if external_id in existing_ids:
            return "existing"
        seen_external_ids.add(external_id)
        return None

    @staticmethod
    def _serialize_entity(entity: BankTransaction) -> BankTransactionRead:
        return BankTransactionRead.model_validate(entity)

    def _deserialize_response(self, record: IdempotencyKey) -> BankTransactionImportResponse:
        body = record.response_body or {}
        return BankTransactionImportResponse.model_validate(body)

    def list_transactions(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BankTransactionRead]:
        rows = self.transactions.list_for_tenant(self.tenant, offset=offset, limit=limit)
        return [BankTransactionRead.model_validate(row) for row in rows]
