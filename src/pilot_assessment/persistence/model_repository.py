"""SQLite adapter for the M5 immutable component-library repository protocol."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    ComponentKind,
    ComponentLifecycle,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    SourceDescriptor,
    VersionLineage,
)
from pilot_assessment.model_library.repository import (
    ComponentHashMismatchError,
    ComponentLibraryError,
    DuplicateLibraryItemError,
    LibraryItem,
    LibraryItemNotFoundError,
    LibraryQuery,
    LibraryRecord,
    LibraryRecordMetadata,
    component_concept_id,
    component_content_hash,
    component_kind,
    component_lineage,
    component_record_id,
)
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

_MODEL_BY_KIND: dict[ComponentKind, type[BaseModel]] = {
    ComponentKind.EVIDENCE_CONCEPT: EvidenceConcept,
    ComponentKind.EVIDENCE_VERSION: EvidenceVersion,
    ComponentKind.BN_NODE_CONCEPT: BnNodeConcept,
    ComponentKind.BN_NODE_VERSION: BnNodeVersion,
    ComponentKind.EVIDENCE_BINDING_VERSION: EvidenceBindingVersion,
    ComponentKind.CPT_VERSION: CptVersion,
    ComponentKind.TASK_PROFILE_VERSION: TaskProfileVersion,
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: CoverageReportingPolicyVersion,
    ComponentKind.LAYOUT_VERSION: LayoutVersion,
    ComponentKind.ASSESSMENT_SCHEME_VERSION: AssessmentSchemeVersion,
    ComponentKind.SOURCE_DESCRIPTOR: SourceDescriptor,
}

_CONCEPT_KIND_BY_VERSION_KIND = {
    ComponentKind.EVIDENCE_VERSION: ComponentKind.EVIDENCE_CONCEPT,
    ComponentKind.BN_NODE_VERSION: ComponentKind.BN_NODE_CONCEPT,
}


def _utc_text(value: datetime, label: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ComponentLibraryError(f"{label} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ComponentLibraryError("stored component timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ComponentLibraryError("stored component timestamp is not timezone-aware")
    return parsed


class SqliteComponentLibraryRepository:
    """Durable exact-version storage implementing `ComponentLibraryRepository`."""

    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def add(self, item: LibraryItem, *, recorded_at: datetime) -> None:
        timestamp = _utc_text(recorded_at, "recorded_at")
        with self.database.transaction() as connection:
            self.add_in_transaction(connection, item, recorded_at_text=timestamp)

    def add_in_transaction(
        self,
        connection: sqlite3.Connection,
        item: LibraryItem,
        *,
        recorded_at: datetime | None = None,
        recorded_at_text: str | None = None,
    ) -> None:
        """Insert one item through an existing transaction for the durable M5 unit of work."""

        if (recorded_at is None) == (recorded_at_text is None):
            raise ComponentLibraryError("provide exactly one of recorded_at or recorded_at_text")
        timestamp = (
            _utc_text(recorded_at, "recorded_at")
            if recorded_at is not None
            else cast(str, recorded_at_text)
        )
        kind = component_kind(item)
        record_id = component_record_id(item)
        if connection.execute(
            "SELECT 1 FROM library_records WHERE kind = ? AND record_id = ?",
            (kind.value, record_id),
        ).fetchone():
            raise DuplicateLibraryItemError(
                f"library item {kind.value}:{record_id} already exists and cannot be overwritten"
            )

        content_hash: str | None = None
        if not isinstance(item, (EvidenceConcept, BnNodeConcept)):
            actual = component_content_hash(item)
            if item.content_hash != actual:
                raise ComponentHashMismatchError(
                    f"component {kind.value}:{record_id} content hash claim does not match"
                )
            content_hash = actual
        lifecycle = (
            item.lifecycle
            if isinstance(item, (EvidenceConcept, BnNodeConcept))
            else ComponentLifecycle.ACTIVE
        )
        connection.execute(
            """
            INSERT INTO library_records(
                kind, record_id, concept_id, lifecycle, canonical_json,
                content_hash, created_at, changed_at, changed_by, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                kind.value,
                record_id,
                component_concept_id(item),
                lifecycle.value,
                encode_canonical_json(item.model_dump(mode="json")),
                content_hash,
                timestamp,
            ),
        )
        if isinstance(item, (EvidenceConcept, BnNodeConcept)):
            connection.executemany(
                "INSERT INTO library_tags(kind, record_id, tag) VALUES (?, ?, ?)",
                ((kind.value, record_id, tag) for tag in item.tags),
            )

    def _load_item(self, row: sqlite3.Row) -> LibraryItem:
        try:
            kind = ComponentKind(row["kind"])
            model = _MODEL_BY_KIND[kind]
            item = cast(
                LibraryItem,
                model.model_validate(decode_canonical_json(row["canonical_json"])),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ComponentLibraryError("stored component JSON is invalid") from error
        record_id = str(row["record_id"])
        if component_kind(item) is not kind or component_record_id(item) != record_id:
            raise ComponentLibraryError("stored component identity columns do not match JSON")
        if not isinstance(item, (EvidenceConcept, BnNodeConcept)):
            actual = component_content_hash(item)
            if item.content_hash != actual or row["content_hash"] != actual:
                raise ComponentHashMismatchError(
                    f"component {kind.value}:{record_id} content hash claim does not match"
                )
        elif row["content_hash"] is not None:
            raise ComponentLibraryError("concept records must not carry a version content hash")
        return item.model_copy(deep=True)

    def _row(self, kind: ComponentKind, record_id: str) -> sqlite3.Row:
        row = self.database.fetchone(
            "SELECT * FROM library_records WHERE kind = ? AND record_id = ?",
            (kind.value, record_id),
        )
        if row is None:
            raise LibraryItemNotFoundError(f"{kind.value}:{record_id}")
        return row

    def get_exact(self, kind: ComponentKind, record_id: str) -> LibraryItem:
        return self._load_item(self._row(kind, record_id))

    def _tags_for(self, item: LibraryItem) -> tuple[str, ...]:
        kind = component_kind(item)
        record_id = component_record_id(item)
        if isinstance(item, (EvidenceConcept, BnNodeConcept)):
            concept_kind = kind
            concept_id = record_id
        else:
            concept_kind = _CONCEPT_KIND_BY_VERSION_KIND.get(kind)
            concept_id = component_concept_id(item)
            if concept_kind is None or concept_id is None:
                return ()
        row = self.database.fetchone(
            """
            SELECT * FROM library_records
            WHERE kind = ? AND record_id = ?
            """,
            (concept_kind.value, concept_id),
        )
        if row is None:
            return ()
        concept = self._load_item(row)
        if not isinstance(concept, (EvidenceConcept, BnNodeConcept)):
            raise ComponentLibraryError("concept tag owner has an invalid component kind")
        return concept.tags

    def get_record(self, kind: ComponentKind, record_id: str) -> LibraryRecord:
        row = self._row(kind, record_id)
        item = self._load_item(row)
        metadata = LibraryRecordMetadata(
            created_at=_parse_time(row["created_at"]),
            lifecycle=ComponentLifecycle(row["lifecycle"]),
            changed_at=(None if row["changed_at"] is None else _parse_time(row["changed_at"])),
            changed_by=row["changed_by"],
            reason=row["reason"],
        )
        return LibraryRecord(
            kind=kind,
            record_id=record_id,
            concept_id=component_concept_id(item),
            tags=self._tags_for(item),
            item=item,
            metadata=metadata,
        )

    def list_records(self, query: LibraryQuery | None = None) -> tuple[LibraryRecord, ...]:
        selected = query or LibraryQuery()
        conditions: list[str] = []
        parameters: list[object] = []
        if selected.kind is not None:
            conditions.append("kind = ?")
            parameters.append(selected.kind.value)
        if selected.concept_id is not None:
            conditions.append("concept_id = ?")
            parameters.append(selected.concept_id)
        if selected.lifecycle is not None:
            conditions.append("lifecycle = ?")
            parameters.append(selected.lifecycle.value)
        where = "" if not conditions else " WHERE " + " AND ".join(conditions)
        rows = self.database.fetchall(
            "SELECT kind, record_id FROM library_records"
            + where
            + " ORDER BY created_at, record_id, kind",
            parameters,
        )
        required_tags = frozenset(selected.tags)
        records = tuple(
            self.get_record(ComponentKind(row["kind"]), row["record_id"]) for row in rows
        )
        return tuple(record for record in records if required_tags.issubset(record.tags))

    def set_lifecycle(
        self,
        kind: ComponentKind,
        record_id: str,
        *,
        lifecycle: ComponentLifecycle,
        changed_at: datetime,
        changed_by: str,
        reason: str,
    ) -> LibraryRecordMetadata:
        timestamp = _utc_text(changed_at, "changed_at")
        if type(changed_by) is not str or not changed_by:
            raise ComponentLibraryError("changed_by must not be empty")
        if type(reason) is not str or not reason:
            raise ComponentLibraryError("lifecycle reason must not be empty")
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT created_at FROM library_records
                WHERE kind = ? AND record_id = ?
                """,
                (kind.value, record_id),
            ).fetchone()
            if row is None:
                raise LibraryItemNotFoundError(f"{kind.value}:{record_id}")
            connection.execute(
                """
                UPDATE library_records
                SET lifecycle = ?, changed_at = ?, changed_by = ?, reason = ?
                WHERE kind = ? AND record_id = ?
                """,
                (
                    lifecycle.value,
                    timestamp,
                    changed_by,
                    reason,
                    kind.value,
                    record_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO library_lifecycle_events(
                    event_id, kind, record_id, lifecycle, changed_at, changed_by, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"lifecycle.{uuid4().hex}",
                    kind.value,
                    record_id,
                    lifecycle.value,
                    timestamp,
                    changed_by,
                    reason,
                ),
            )
        return LibraryRecordMetadata(
            created_at=_parse_time(row["created_at"]),
            lifecycle=lifecycle,
            changed_at=changed_at,
            changed_by=changed_by,
            reason=reason,
        )

    def get_lineage(self, kind: ComponentKind, record_id: str) -> VersionLineage | None:
        return component_lineage(self.get_exact(kind, record_id))


__all__ = ["SqliteComponentLibraryRepository"]
