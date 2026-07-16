"""SQLite draft timelines and atomic M5 workspace publication."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from pilot_assessment.contracts.assessment_scheme import SchemeDraft
from pilot_assessment.model_library.repository import VersionLibraryItem
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.schemes.operations import OperationDiff
from pilot_assessment.schemes.repository import (
    DraftHistoryBoundaryError,
    DraftRevisionConflictError,
    SchemeDraftAlreadyExistsError,
    SchemeDraftNotFoundError,
    SchemeDraftRecord,
    SchemeDraftRepositoryError,
)

Clock = Callable[[], datetime]
FailureHook = Callable[[str], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime, label: str = "repository clock") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchemeDraftRepositoryError(f"{label} must be timezone-aware")
    return value


def _utc_text(value: datetime) -> str:
    return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SchemeDraftRepositoryError("stored draft timestamp is invalid") from error
    return _aware(parsed, "stored draft timestamp")


def _author(value: str) -> str:
    if type(value) is not str or not value:
        raise SchemeDraftRepositoryError("author_id must be a non-empty string")
    return value


def _snapshot(draft: SchemeDraft) -> SchemeDraft:
    return SchemeDraft.model_validate(draft.model_dump(mode="json"))


def _check_expected(
    draft: SchemeDraft,
    *,
    expected_graph_version: int | None,
    expected_layout_version: int | None,
    require_graph: bool,
    require_layout: bool,
) -> None:
    for label, value in (
        ("expected_graph_version", expected_graph_version),
        ("expected_layout_version", expected_layout_version),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise DraftRevisionConflictError(f"{label} must be a non-negative strict integer")
    if require_graph and expected_graph_version is None:
        raise DraftRevisionConflictError("graph operation requires expected_graph_version")
    if require_layout and expected_layout_version is None:
        raise DraftRevisionConflictError("layout operation requires expected_layout_version")
    if expected_graph_version is not None and draft.graph_version != expected_graph_version:
        raise DraftRevisionConflictError(
            f"draft graph is at {draft.graph_version}, not {expected_graph_version}"
        )
    if expected_layout_version is not None and draft.layout_version != expected_layout_version:
        raise DraftRevisionConflictError(
            f"draft layout is at {draft.layout_version}, not {expected_layout_version}"
        )


def _diff_payload(diff: OperationDiff) -> dict[str, object]:
    return {
        "operation_type": diff.operation_type,
        "changed_paths": diff.changed_paths,
        "added_component_ids": diff.added_component_ids,
        "removed_component_ids": diff.removed_component_ids,
    }


def _decode_diff(payload: bytes | None) -> OperationDiff | None:
    if payload is None:
        return None
    value = decode_canonical_json(payload)
    if not isinstance(value, dict) or set(value) != {
        "operation_type",
        "changed_paths",
        "added_component_ids",
        "removed_component_ids",
    }:
        raise SchemeDraftRepositoryError("stored draft diff has an invalid shape")
    operation_type = value["operation_type"]
    if type(operation_type) is not str or not operation_type:
        raise SchemeDraftRepositoryError("stored draft operation type is invalid")

    def strings(field: str) -> tuple[str, ...]:
        members = value[field]
        if not isinstance(members, list) or any(type(member) is not str for member in members):
            raise SchemeDraftRepositoryError(f"stored draft diff {field} is invalid")
        return tuple(members)

    return OperationDiff(
        operation_type=operation_type,
        changed_paths=strings("changed_paths"),
        added_component_ids=strings("added_component_ids"),
        removed_component_ids=strings("removed_component_ids"),
    )


def _decode_draft(payload: bytes) -> SchemeDraft:
    try:
        return SchemeDraft.model_validate(decode_canonical_json(payload))
    except (TypeError, ValueError) as error:
        raise SchemeDraftRepositoryError("stored draft JSON is invalid") from error


class SqliteSchemeDraftRepository:
    """Durable autosave timeline implementing the M5 draft repository protocol."""

    def __init__(self, database: ProjectDatabase, *, clock: Clock = _utc_now) -> None:
        self.database = database
        self._clock = clock

    def _now(self) -> datetime:
        return _aware(self._clock())

    def _row(self, connection: sqlite3.Connection, draft_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM scheme_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise SchemeDraftNotFoundError(draft_id)
        return row

    def _record(self, row: sqlite3.Row) -> SchemeDraftRecord:
        draft = _decode_draft(row["canonical_json"])
        if (
            draft.draft_id != row["draft_id"]
            or draft.graph_version != row["graph_version"]
            or draft.layout_version != row["layout_version"]
            or draft.history_cursor != row["history_cursor"]
        ):
            raise SchemeDraftRepositoryError("stored draft identity columns do not match JSON")
        return SchemeDraftRecord(
            draft=draft,
            created_at=_parse_time(row["created_at"]),
            updated_at=_parse_time(row["updated_at"]),
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            last_diff=_decode_diff(row["last_diff_json"]),
        )

    def create(self, draft: SchemeDraft, *, author_id: str) -> SchemeDraftRecord:
        author = _author(author_id)
        canonical = _snapshot(draft).model_copy(update={"history_cursor": 0})
        now = self._now()
        now_text = _utc_text(now)
        payload = encode_canonical_json(canonical.model_dump(mode="json"))
        with self.database.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM scheme_drafts WHERE draft_id = ?", (canonical.draft_id,)
            ).fetchone():
                raise SchemeDraftAlreadyExistsError(canonical.draft_id)
            connection.execute(
                """
                INSERT INTO scheme_drafts(
                    draft_id, canonical_json, graph_version, layout_version,
                    history_cursor, created_at, updated_at, created_by,
                    updated_by, last_diff_json
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, NULL)
                """,
                (
                    canonical.draft_id,
                    payload,
                    canonical.graph_version,
                    canonical.layout_version,
                    now_text,
                    now_text,
                    author,
                    author,
                ),
            )
            connection.execute(
                """
                INSERT INTO draft_snapshots(draft_id, snapshot_index, canonical_json)
                VALUES (?, 0, ?)
                """,
                (canonical.draft_id, payload),
            )
        return SchemeDraftRecord(
            draft=canonical,
            created_at=now,
            updated_at=now,
            created_by=author,
            updated_by=author,
            last_diff=None,
        )

    def get(self, draft_id: str) -> SchemeDraftRecord:
        row = self.database.fetchone("SELECT * FROM scheme_drafts WHERE draft_id = ?", (draft_id,))
        if row is None:
            raise SchemeDraftNotFoundError(draft_id)
        return self._record(row)

    def save(
        self,
        proposed: SchemeDraft,
        *,
        expected_graph_version: int | None,
        expected_layout_version: int | None,
        graph_changed: bool,
        layout_changed: bool,
        diff: OperationDiff,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        if not graph_changed and not layout_changed:
            raise SchemeDraftRepositoryError("an operation must change graph or layout state")
        with self.database.transaction() as connection:
            row = self._row(connection, proposed.draft_id)
            current_record = self._record(row)
            current = current_record.draft
            _check_expected(
                current,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                require_graph=graph_changed,
                require_layout=layout_changed,
            )
            cursor = current.history_cursor
            next_cursor = cursor + 1
            canonical = _snapshot(proposed).model_copy(
                update={
                    "graph_version": current.graph_version + int(graph_changed),
                    "layout_version": current.layout_version + int(layout_changed),
                    "history_cursor": next_cursor,
                }
            )
            payload = encode_canonical_json(canonical.model_dump(mode="json"))
            diff_payload = encode_canonical_json(_diff_payload(diff))
            now = self._now()
            now_text = _utc_text(now)
            connection.execute(
                "DELETE FROM draft_snapshots WHERE draft_id = ? AND snapshot_index > ?",
                (current.draft_id, cursor),
            )
            connection.execute(
                "DELETE FROM draft_transitions WHERE draft_id = ? AND transition_index >= ?",
                (current.draft_id, cursor),
            )
            connection.execute(
                """
                INSERT INTO draft_snapshots(draft_id, snapshot_index, canonical_json)
                VALUES (?, ?, ?)
                """,
                (current.draft_id, next_cursor, payload),
            )
            connection.execute(
                """
                INSERT INTO draft_transitions(
                    draft_id, transition_index, diff_json, graph_changed,
                    layout_changed, author_id, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current.draft_id,
                    cursor,
                    diff_payload,
                    int(graph_changed),
                    int(layout_changed),
                    author,
                    now_text,
                ),
            )
            connection.execute(
                """
                UPDATE scheme_drafts
                SET canonical_json = ?, graph_version = ?, layout_version = ?,
                    history_cursor = ?, updated_at = ?, updated_by = ?, last_diff_json = ?
                WHERE draft_id = ?
                """,
                (
                    payload,
                    canonical.graph_version,
                    canonical.layout_version,
                    next_cursor,
                    now_text,
                    author,
                    diff_payload,
                    current.draft_id,
                ),
            )
        return SchemeDraftRecord(
            draft=canonical,
            created_at=current_record.created_at,
            updated_at=now,
            created_by=current_record.created_by,
            updated_by=author,
            last_diff=diff,
        )

    def _travel(
        self,
        draft_id: str,
        *,
        direction: int,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        with self.database.transaction() as connection:
            row = self._row(connection, draft_id)
            current_record = self._record(row)
            current = current_record.draft
            _check_expected(
                current,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                require_graph=True,
                require_layout=True,
            )
            target_cursor = current.history_cursor + direction
            snapshot_row = connection.execute(
                """
                SELECT canonical_json FROM draft_snapshots
                WHERE draft_id = ? AND snapshot_index = ?
                """,
                (draft_id, target_cursor),
            ).fetchone()
            if target_cursor < 0 or snapshot_row is None:
                label = "undo" if direction < 0 else "redo"
                raise DraftHistoryBoundaryError(f"draft has no {label} state")
            transition_index = current.history_cursor if direction > 0 else target_cursor
            transition_row = connection.execute(
                """
                SELECT * FROM draft_transitions
                WHERE draft_id = ? AND transition_index = ?
                """,
                (draft_id, transition_index),
            ).fetchone()
            if transition_row is None:
                raise SchemeDraftRepositoryError("draft history transition is missing")
            transition = _decode_diff(transition_row["diff_json"])
            assert transition is not None
            target = _decode_draft(snapshot_row["canonical_json"])
            canonical = target.model_copy(
                update={
                    "graph_version": current.graph_version + int(transition_row["graph_changed"]),
                    "layout_version": current.layout_version
                    + int(transition_row["layout_changed"]),
                    "history_cursor": target_cursor,
                }
            )
            prefix = "undo" if direction < 0 else "redo"
            diff = OperationDiff(
                operation_type=f"{prefix}:{transition.operation_type}",
                changed_paths=transition.changed_paths,
                added_component_ids=transition.removed_component_ids,
                removed_component_ids=transition.added_component_ids,
            )
            now = self._now()
            now_text = _utc_text(now)
            payload = encode_canonical_json(canonical.model_dump(mode="json"))
            diff_payload = encode_canonical_json(_diff_payload(diff))
            connection.execute(
                """
                UPDATE scheme_drafts
                SET canonical_json = ?, graph_version = ?, layout_version = ?,
                    history_cursor = ?, updated_at = ?, updated_by = ?, last_diff_json = ?
                WHERE draft_id = ?
                """,
                (
                    payload,
                    canonical.graph_version,
                    canonical.layout_version,
                    target_cursor,
                    now_text,
                    author,
                    diff_payload,
                    draft_id,
                ),
            )
        return SchemeDraftRecord(
            draft=canonical,
            created_at=current_record.created_at,
            updated_at=now,
            created_by=current_record.created_by,
            updated_by=author,
            last_diff=diff,
        )

    def undo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._travel(
            draft_id,
            direction=-1,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def redo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._travel(
            draft_id,
            direction=1,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def replace_after_publication_in_transaction(
        self,
        connection: sqlite3.Connection,
        draft: SchemeDraft,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        row = self._row(connection, draft.draft_id)
        current_record = self._record(row)
        _check_expected(
            current_record.draft,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            require_graph=True,
            require_layout=True,
        )
        canonical = _snapshot(draft).model_copy(update={"history_cursor": 0})
        now = self._now()
        now_text = _utc_text(now)
        diff = OperationDiff(operation_type="PublishScheme", changed_paths=("/",))
        payload = encode_canonical_json(canonical.model_dump(mode="json"))
        diff_payload = encode_canonical_json(_diff_payload(diff))
        connection.execute("DELETE FROM draft_transitions WHERE draft_id = ?", (draft.draft_id,))
        connection.execute("DELETE FROM draft_snapshots WHERE draft_id = ?", (draft.draft_id,))
        connection.execute(
            """
            INSERT INTO draft_snapshots(draft_id, snapshot_index, canonical_json)
            VALUES (?, 0, ?)
            """,
            (draft.draft_id, payload),
        )
        connection.execute(
            """
            UPDATE scheme_drafts
            SET canonical_json = ?, graph_version = ?, layout_version = ?,
                history_cursor = 0, updated_at = ?, updated_by = ?, last_diff_json = ?
            WHERE draft_id = ?
            """,
            (
                payload,
                canonical.graph_version,
                canonical.layout_version,
                now_text,
                author,
                diff_payload,
                draft.draft_id,
            ),
        )
        return SchemeDraftRecord(
            draft=canonical,
            created_at=current_record.created_at,
            updated_at=now,
            created_by=current_record.created_by,
            updated_by=author,
            last_diff=diff,
        )


class SqliteWorkspaceUnitOfWork:
    """Commit immutable component versions and the rebased draft in one transaction."""

    def __init__(
        self,
        database: ProjectDatabase,
        components: SqliteComponentLibraryRepository,
        drafts: SqliteSchemeDraftRepository,
        *,
        failure_hook: FailureHook | None = None,
    ) -> None:
        if components.database is not database or drafts.database is not database:
            raise SchemeDraftRepositoryError(
                "workspace repositories must share the same project database"
            )
        self.database = database
        self.components = components
        self.drafts = drafts
        self._failure_hook = failure_hook

    def publish_atomic(
        self,
        items: tuple[VersionLibraryItem, ...],
        *,
        recorded_at: datetime,
        draft_id: str,
        expected_graph_version: int,
        expected_layout_version: int,
        rebased_draft: SchemeDraft,
        author_id: str,
    ) -> SchemeDraftRecord:
        _aware(recorded_at, "recorded_at")
        if rebased_draft.draft_id != draft_id:
            raise SchemeDraftRepositoryError("rebased draft ID must match publication draft_id")
        with self.database.transaction() as connection:
            for item in items:
                self.components.add_in_transaction(
                    connection,
                    item,
                    recorded_at=recorded_at,
                )
            record = self.drafts.replace_after_publication_in_transaction(
                connection,
                rebased_draft,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                author_id=author_id,
            )
            if self._failure_hook is not None:
                self._failure_hook("before_commit")
        return record


__all__ = ["SqliteSchemeDraftRepository", "SqliteWorkspaceUnitOfWork"]
