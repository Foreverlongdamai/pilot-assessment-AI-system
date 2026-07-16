"""Durable business idempotency independent from JSON-RPC request IDs."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import JsonValue

from pilot_assessment.contracts.project import (
    AuditEvent,
    TransactionReceipt,
    TransactionStatus,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

Clock = Callable[[], datetime]


class IdempotencyError(RuntimeError):
    """Base class for deterministic business idempotency failures."""


class TransactionReuseMismatchError(IdempotencyError):
    """Raised when one transaction ID is reused for another canonical request."""


class TransactionInProgressError(IdempotencyError):
    """Raised when recovery has not resolved a durable prepared transaction."""


class IdempotencyIntegrityError(IdempotencyError):
    """Raised when a completed receipt is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class MutationResult:
    response_payload: dict[str, JsonValue]
    audit_event: AuditEvent


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    receipt: TransactionReceipt
    replayed: bool


Mutation = Callable[[sqlite3.Connection], MutationResult]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IdempotencyError("idempotency clock must be timezone-aware")
    return value


def _utc_text(value: datetime) -> str:
    return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def transaction_request_hash(method: str, params: object) -> str:
    """Hash canonical method and params; JSON-RPC request ID is intentionally excluded."""

    return typed_content_sha256(
        "idempotent-mutation-request",
        "0.1.0",
        {"method": method, "params": params},
    )


class IdempotencyStore:
    """Execute a DB mutation and persist its canonical response exactly once."""

    def __init__(
        self,
        database: ProjectDatabase,
        audit: AuditRepository,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        if audit.database is not database:
            raise IdempotencyError("idempotency and audit repositories must share a database")
        self.database = database
        self.audit = audit
        self._clock = clock

    @staticmethod
    def _replay_receipt(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> TransactionReceipt:
        if row["status"] != TransactionStatus.COMPLETED.value:
            raise TransactionInProgressError(row["transaction_id"])
        if (
            row["response_json"] is None
            or row["audit_event_id"] is None
            or row["completed_at"] is None
        ):
            raise IdempotencyIntegrityError("completed transaction fields are incomplete")
        if (
            connection.execute(
                "SELECT 1 FROM audit_events WHERE audit_event_id = ?",
                (row["audit_event_id"],),
            ).fetchone()
            is None
        ):
            raise IdempotencyIntegrityError("completed transaction audit event is missing")
        response = decode_canonical_json(row["response_json"])
        if not isinstance(response, dict):
            raise IdempotencyIntegrityError("stored transaction response must be a JSON object")
        return TransactionReceipt(
            transaction_id=row["transaction_id"],
            method=row["method"],
            request_hash=row["request_hash"],
            status=TransactionStatus.COMPLETED,
            response_payload=response,
            audit_event_id=row["audit_event_id"],
            completed_at=row["completed_at"],
        )

    def execute(
        self,
        *,
        transaction_id: str,
        method: str,
        params: object,
        mutation: Mutation,
    ) -> IdempotencyResult:
        request_hash = transaction_request_hash(method, params)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM idempotency_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if row is not None:
                if row["method"] != method or row["request_hash"] != request_hash:
                    raise TransactionReuseMismatchError(
                        "transaction ID was already used for a different canonical request"
                    )
                return IdempotencyResult(
                    receipt=self._replay_receipt(connection, row),
                    replayed=True,
                )

            connection.execute(
                """
                INSERT INTO idempotency_transactions(
                    transaction_id, method, request_hash, status,
                    response_json, audit_event_id, completed_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    transaction_id,
                    method,
                    request_hash,
                    TransactionStatus.PREPARED.value,
                ),
            )
            result = mutation(connection)
            if result.audit_event.transaction_id != transaction_id:
                raise IdempotencyError(
                    "mutation audit event must reference the executing transaction"
                )
            self.audit.append_in_transaction(connection, result.audit_event)
            completed_at = _aware(self._clock())
            response_bytes = encode_canonical_json(result.response_payload)
            receipt = TransactionReceipt(
                transaction_id=transaction_id,
                method=method,
                request_hash=request_hash,
                status=TransactionStatus.COMPLETED,
                response_payload=result.response_payload,
                audit_event_id=result.audit_event.audit_event_id,
                completed_at=completed_at,
            )
            connection.execute(
                """
                UPDATE idempotency_transactions
                SET status = ?, response_json = ?, audit_event_id = ?, completed_at = ?
                WHERE transaction_id = ?
                """,
                (
                    TransactionStatus.COMPLETED.value,
                    response_bytes,
                    receipt.audit_event_id,
                    _utc_text(completed_at),
                    transaction_id,
                ),
            )
        return IdempotencyResult(receipt=receipt, replayed=False)


__all__ = [
    "IdempotencyError",
    "IdempotencyIntegrityError",
    "IdempotencyResult",
    "IdempotencyStore",
    "Mutation",
    "MutationResult",
    "TransactionInProgressError",
    "TransactionReuseMismatchError",
    "transaction_request_hash",
]
