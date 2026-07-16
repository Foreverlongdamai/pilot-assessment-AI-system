"""Append-only durable audit events with stable filtered pagination."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from pilot_assessment.contracts.project import AuditEvent
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)


class AuditRepositoryError(RuntimeError):
    """Base class for deterministic audit repository failures."""


class AuditEventAlreadyExistsError(AuditRepositoryError):
    """Raised rather than overwriting an immutable audit event."""


class AuditEventNotFoundError(KeyError):
    """Raised when an exact audit event ID is absent."""


@dataclass(frozen=True, slots=True)
class AuditQuery:
    event_type: str | None = None
    subject_kind: str | None = None
    subject_id: str | None = None
    transaction_id: str | None = None


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuditRepositoryError("audit timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AuditRepository:
    """Project-scoped append-only audit storage."""

    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def append(self, event: AuditEvent) -> AuditEvent:
        with self.database.transaction() as connection:
            self.append_in_transaction(connection, event)
        return event.model_copy(deep=True)

    def append_in_transaction(self, connection: sqlite3.Connection, event: AuditEvent) -> None:
        if connection.execute(
            "SELECT 1 FROM audit_events WHERE audit_event_id = ?",
            (event.audit_event_id,),
        ).fetchone():
            raise AuditEventAlreadyExistsError(event.audit_event_id)
        connection.execute(
            """
            INSERT INTO audit_events(
                audit_event_id, event_type, actor_id, occurred_at,
                subject_kind, subject_id, transaction_id, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.audit_event_id,
                event.event_type,
                event.actor_id,
                _utc_text(event.occurred_at),
                event.subject_kind,
                event.subject_id,
                event.transaction_id,
                encode_canonical_json(event.details),
            ),
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> AuditEvent:
        details = decode_canonical_json(row["details_json"])
        if not isinstance(details, dict):
            raise AuditRepositoryError("stored audit details must be a JSON object")
        return AuditEvent(
            audit_event_id=row["audit_event_id"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            occurred_at=row["occurred_at"],
            subject_kind=row["subject_kind"],
            subject_id=row["subject_id"],
            transaction_id=row["transaction_id"],
            details=details,
        )

    def get(self, audit_event_id: str) -> AuditEvent:
        row = self.database.fetchone(
            "SELECT * FROM audit_events WHERE audit_event_id = ?", (audit_event_id,)
        )
        if row is None:
            raise AuditEventNotFoundError(audit_event_id)
        return self._event(row)

    def list_events(
        self,
        query: AuditQuery | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AuditEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise AuditRepositoryError("audit limit must be a strict integer from 1 to 1000")
        if type(offset) is not int or offset < 0:
            raise AuditRepositoryError("audit offset must be a non-negative strict integer")
        selected = query or AuditQuery()
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("event_type", selected.event_type),
            ("subject_kind", selected.subject_kind),
            ("subject_id", selected.subject_id),
            ("transaction_id", selected.transaction_id),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                parameters.append(value)
        where = "" if not conditions else " WHERE " + " AND ".join(conditions)
        parameters.extend((limit, offset))
        rows = self.database.fetchall(
            "SELECT * FROM audit_events"
            + where
            + " ORDER BY occurred_at, audit_event_id LIMIT ? OFFSET ?",
            parameters,
        )
        return tuple(self._event(row) for row in rows)


__all__ = [
    "AuditEventAlreadyExistsError",
    "AuditEventNotFoundError",
    "AuditQuery",
    "AuditRepository",
    "AuditRepositoryError",
]
