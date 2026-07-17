"""Durable current ModelNode/TaskScheme state and append-only M7 change journal."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    ModelChangeEvent,
    ModelChangeKind,
    ModelNode,
    ModelObjectKind,
    ModelObjectLifecycle,
    TaskScheme,
)
from pilot_assessment.model_workspace.hashing import (
    model_node_layout_hash,
    model_node_semantic_hash,
    rehash_model_node,
    rehash_task_scheme,
    task_scheme_layout_hash,
    task_scheme_semantic_hash,
)
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

CurrentObject = ModelNode | TaskScheme


class ModelWorkspaceRepositoryError(RuntimeError):
    """Base error for durable M7 current-object operations."""


class CurrentObjectNotFoundError(ModelWorkspaceRepositoryError):
    """Raised when one current node or scheme does not exist."""


class CurrentObjectConflictError(ModelWorkspaceRepositoryError):
    """Raised for duplicate identities or optimistic revision conflicts."""


class CurrentObjectIntegrityError(ModelWorkspaceRepositoryError):
    """Raised when stored canonical JSON and indexed columns disagree."""


class UndoRedoUnavailableError(ModelWorkspaceRepositoryError):
    """Raised at a current object's undo/redo boundary."""


@dataclass(frozen=True, slots=True)
class _ObjectSpec:
    object_kind: ModelObjectKind
    table: str
    id_column: str
    model: type[ModelNode] | type[TaskScheme]


@dataclass(frozen=True, slots=True)
class _StoredObject:
    item: CurrentObject
    head_event_id: str | None
    redo_event_id: str | None


@dataclass(frozen=True, slots=True)
class _StoredEvent:
    event: ModelChangeEvent
    before_json: bytes | None
    after_json: bytes | None


_NODE_SPEC = _ObjectSpec(ModelObjectKind.NODE, "model_nodes", "node_id", ModelNode)
_SCHEME_SPEC = _ObjectSpec(
    ModelObjectKind.SCHEME,
    "task_schemes",
    "scheme_id",
    TaskScheme,
)


def _utc_text(value: datetime, label: str) -> str:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ModelWorkspaceRepositoryError(f"{label} must be timezone-aware")
    if offset.total_seconds() != 0:
        raise ModelWorkspaceRepositoryError(f"{label} must use UTC offset +00:00")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _object_id(item: CurrentObject) -> str:
    return item.node_id if isinstance(item, ModelNode) else item.scheme_id


def _spec_for(item: CurrentObject) -> _ObjectSpec:
    return _NODE_SPEC if isinstance(item, ModelNode) else _SCHEME_SPEC


def _rehash(item: CurrentObject) -> CurrentObject:
    return rehash_model_node(item) if isinstance(item, ModelNode) else rehash_task_scheme(item)


def _semantic_hash(item: CurrentObject) -> str:
    return (
        model_node_semantic_hash(item)
        if isinstance(item, ModelNode)
        else task_scheme_semantic_hash(item)
    )


def _layout_hash(item: CurrentObject) -> str:
    return (
        model_node_layout_hash(item)
        if isinstance(item, ModelNode)
        else task_scheme_layout_hash(item)
    )


def _snapshot(item: CurrentObject) -> CurrentObject:
    model = ModelNode if isinstance(item, ModelNode) else TaskScheme
    return model.model_validate(item.model_dump(mode="json"))


def _validate_revision(value: int | None, label: str) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise CurrentObjectConflictError(f"{label} must be a non-negative strict integer")


def _check_expected(
    item: CurrentObject,
    *,
    expected_semantic_revision: int | None,
    expected_layout_revision: int | None,
    require_both: bool = False,
) -> None:
    _validate_revision(expected_semantic_revision, "expected_semantic_revision")
    _validate_revision(expected_layout_revision, "expected_layout_revision")
    if require_both and (expected_semantic_revision is None or expected_layout_revision is None):
        raise CurrentObjectConflictError("undo/redo requires both expected revisions")
    if expected_semantic_revision is None and expected_layout_revision is None:
        raise CurrentObjectConflictError("a mutation requires an expected revision")
    if (
        expected_semantic_revision is not None
        and item.semantic_revision != expected_semantic_revision
    ):
        raise CurrentObjectConflictError(
            f"semantic revision is {item.semantic_revision}, not {expected_semantic_revision}"
        )
    if expected_layout_revision is not None and item.layout_revision != expected_layout_revision:
        raise CurrentObjectConflictError(
            f"layout revision is {item.layout_revision}, not {expected_layout_revision}"
        )


def _decode_object(payload: bytes, spec: _ObjectSpec) -> CurrentObject:
    try:
        decoded = decode_canonical_json(payload)
        if spec.object_kind is ModelObjectKind.NODE:
            return ModelNode.model_validate(decoded)
        return TaskScheme.model_validate(decoded)
    except (TypeError, ValueError, ValidationError) as error:
        raise CurrentObjectIntegrityError("stored current-object JSON is invalid") from error


def _row_timestamp_matches(value: str, expected: datetime) -> bool:
    return value == _utc_text(expected, "stored object timestamp")


def _record_from_row(row: sqlite3.Row, spec: _ObjectSpec) -> _StoredObject:
    item = _decode_object(row["canonical_json"], spec)
    expected_id = _object_id(item)
    columns_match = (
        row[spec.id_column] == expected_id
        and row["lifecycle"] == item.lifecycle.value
        and row["semantic_revision"] == item.semantic_revision
        and row["layout_revision"] == item.layout_revision
        and row["content_hash"] == item.content_hash
        and row["layout_hash"] == item.layout_hash
        and row["technical_status"] == item.technical_status.value
        and _row_timestamp_matches(row["created_at"], item.created_at)
        and _row_timestamp_matches(row["updated_at"], item.updated_at)
    )
    if not columns_match:
        raise CurrentObjectIntegrityError(
            "stored current-object indexed columns do not match canonical JSON"
        )
    if item.content_hash != _semantic_hash(item) or item.layout_hash != _layout_hash(item):
        raise CurrentObjectIntegrityError("stored current-object hash claim does not match")
    return _StoredObject(
        item=_snapshot(item),
        head_event_id=row["head_event_id"],
        redo_event_id=row["redo_event_id"],
    )


def _event_from_row(row: sqlite3.Row) -> _StoredEvent:
    try:
        diff = CanonicalModelDiff.model_validate(decode_canonical_json(row["diff_json"]))
        event = ModelChangeEvent(
            event_id=row["event_id"],
            object_kind=row["object_kind"],
            object_id=row["object_id"],
            event_kind=row["event_kind"],
            parent_event_id=row["parent_event_id"],
            semantic_revision=row["semantic_revision"],
            layout_revision=row["layout_revision"],
            before_hash=row["before_hash"],
            after_hash=row["after_hash"],
            diff=diff,
            transaction_id=row["transaction_id"],
            actor_id=row["actor_id"],
            occurred_at=row["occurred_at"],
        )
    except (TypeError, ValueError, ValidationError) as error:
        raise CurrentObjectIntegrityError("stored model change event is invalid") from error
    before = row["before_json"]
    after = row["after_json"]
    if before is not None:
        decode_canonical_json(before)
    if after is not None:
        decode_canonical_json(after)
    return _StoredEvent(event=event, before_json=before, after_json=after)


def _merge_update(
    current: CurrentObject,
    proposed: CurrentObject,
    *,
    semantic_changed: bool,
    layout_changed: bool,
    occurred_at: datetime,
) -> CurrentObject:
    if type(current) is not type(proposed) or _object_id(current) != _object_id(proposed):
        raise CurrentObjectConflictError("replacement current-object identity does not match")
    if isinstance(current, ModelNode) and isinstance(proposed, ModelNode):
        if current.node_kind is not proposed.node_kind:
            raise CurrentObjectConflictError("a current node cannot change node_kind")
        if semantic_changed and layout_changed:
            candidate: CurrentObject = proposed
        elif semantic_changed:
            candidate = proposed.model_copy(update={"global_layout": current.global_layout})
        else:
            candidate = current.model_copy(update={"global_layout": proposed.global_layout})
    elif isinstance(current, TaskScheme) and isinstance(proposed, TaskScheme):
        if semantic_changed and layout_changed:
            candidate = proposed
        elif semantic_changed:
            candidate = proposed.model_copy(update={"layout_overrides": current.layout_overrides})
        else:
            candidate = current.model_copy(update={"layout_overrides": proposed.layout_overrides})
    else:  # pragma: no cover - protected by exact type check above
        raise CurrentObjectConflictError("replacement current-object type does not match")
    canonical = candidate.model_copy(
        update={
            "created_at": current.created_at,
            "updated_at": occurred_at,
            "semantic_revision": current.semantic_revision + int(semantic_changed),
            "layout_revision": current.layout_revision + int(layout_changed),
        }
    )
    return _rehash(canonical)


def _restore_snapshot(
    current: CurrentObject,
    target: CurrentObject,
    *,
    occurred_at: datetime,
) -> CurrentObject:
    if type(current) is not type(target) or _object_id(current) != _object_id(target):
        raise CurrentObjectIntegrityError("history snapshot identity does not match current object")
    semantic_changed = _semantic_hash(target) != current.content_hash
    layout_changed = _layout_hash(target) != current.layout_hash
    restored = target.model_copy(
        update={
            "created_at": current.created_at,
            "updated_at": occurred_at,
            "semantic_revision": current.semantic_revision + int(semantic_changed),
            "layout_revision": current.layout_revision + int(layout_changed),
        }
    )
    return _rehash(restored)


def _cursor_diff(
    source: CanonicalModelDiff,
    *,
    undo: bool,
    metadata: dict[str, JsonValue],
) -> CanonicalModelDiff:
    return CanonicalModelDiff(
        changed_paths=source.changed_paths,
        added_node_ids=(source.removed_node_ids if undo else source.added_node_ids),
        removed_node_ids=(source.added_node_ids if undo else source.removed_node_ids),
        added_edge_ids=(source.removed_edge_ids if undo else source.added_edge_ids),
        removed_edge_ids=(source.added_edge_ids if undo else source.removed_edge_ids),
        metadata=metadata,
    )


class SqliteModelWorkspaceRepository:
    """Project-scoped current objects with optimistic autosave and auditable cursors."""

    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def _row(
        self,
        connection: sqlite3.Connection,
        spec: _ObjectSpec,
        object_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            f"SELECT * FROM {spec.table} WHERE {spec.id_column} = ?",  # noqa: S608
            (object_id,),
        ).fetchone()
        if row is None:
            raise CurrentObjectNotFoundError(f"{spec.object_kind.value}:{object_id}")
        return row

    def _event_row(self, connection: sqlite3.Connection, event_id: str) -> _StoredEvent:
        row = connection.execute(
            "SELECT * FROM model_change_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise CurrentObjectIntegrityError(f"model change event {event_id!r} is missing")
        return _event_from_row(row)

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        spec: _ObjectSpec,
        object_id: str,
        event_id: str,
        event_kind: ModelChangeKind,
        parent_event_id: str | None,
        before: CurrentObject | None,
        after: CurrentObject,
        diff: CanonicalModelDiff,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
    ) -> ModelChangeEvent:
        event = ModelChangeEvent(
            event_id=event_id,
            object_kind=spec.object_kind,
            object_id=object_id,
            event_kind=event_kind,
            parent_event_id=parent_event_id,
            semantic_revision=after.semantic_revision,
            layout_revision=after.layout_revision,
            before_hash=None if before is None else before.content_hash,
            after_hash=after.content_hash,
            diff=diff,
            transaction_id=transaction_id,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )
        try:
            connection.execute(
                """
                INSERT INTO model_change_events(
                    event_id, object_kind, object_id, event_kind, parent_event_id,
                    semantic_revision, layout_revision, before_hash, after_hash,
                    before_json, after_json, diff_json, transaction_id, actor_id,
                    occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.object_kind.value,
                    event.object_id,
                    event.event_kind.value,
                    event.parent_event_id,
                    event.semantic_revision,
                    event.layout_revision,
                    event.before_hash,
                    event.after_hash,
                    (
                        None
                        if before is None
                        else encode_canonical_json(before.model_dump(mode="json"))
                    ),
                    encode_canonical_json(after.model_dump(mode="json")),
                    encode_canonical_json(diff.model_dump(mode="json")),
                    event.transaction_id,
                    event.actor_id,
                    _utc_text(event.occurred_at, "occurred_at"),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise CurrentObjectConflictError(
                f"model change event {event.event_id!r} already exists or is invalid"
            ) from error
        return event

    def _insert_object(
        self,
        connection: sqlite3.Connection,
        spec: _ObjectSpec,
        item: CurrentObject,
    ) -> None:
        sql = f"""
            INSERT INTO {spec.table}(
                {spec.id_column}, canonical_json, lifecycle,
                semantic_revision, layout_revision, content_hash, layout_hash,
                technical_status, head_event_id, redo_event_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """  # noqa: S608 - table and column come from closed internal specs
        try:
            connection.execute(
                sql,
                (
                    _object_id(item),
                    encode_canonical_json(item.model_dump(mode="json")),
                    item.lifecycle.value,
                    item.semantic_revision,
                    item.layout_revision,
                    item.content_hash,
                    item.layout_hash,
                    item.technical_status.value,
                    _utc_text(item.created_at, "created_at"),
                    _utc_text(item.updated_at, "updated_at"),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise CurrentObjectConflictError(
                f"{spec.object_kind.value} {_object_id(item)!r} already exists"
            ) from error

    def _write_object(
        self,
        connection: sqlite3.Connection,
        spec: _ObjectSpec,
        item: CurrentObject,
        *,
        head_event_id: str | None,
        redo_event_id: str | None,
    ) -> None:
        sql = f"""
            UPDATE {spec.table}
            SET canonical_json = ?, lifecycle = ?, semantic_revision = ?,
                layout_revision = ?, content_hash = ?, layout_hash = ?,
                technical_status = ?, head_event_id = ?, redo_event_id = ?,
                updated_at = ?
            WHERE {spec.id_column} = ?
            """  # noqa: S608 - table and column come from closed internal specs
        connection.execute(
            sql,
            (
                encode_canonical_json(item.model_dump(mode="json")),
                item.lifecycle.value,
                item.semantic_revision,
                item.layout_revision,
                item.content_hash,
                item.layout_hash,
                item.technical_status.value,
                head_event_id,
                redo_event_id,
                _utc_text(item.updated_at, "updated_at"),
                _object_id(item),
            ),
        )

    def _create(
        self,
        item: CurrentObject,
        *,
        spec: _ObjectSpec,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool,
    ) -> CurrentObject:
        if _spec_for(item) != spec:
            raise CurrentObjectConflictError("current-object type does not match repository method")
        if item.semantic_revision != 0 or item.layout_revision != 0:
            raise CurrentObjectConflictError("new current objects must start at revision zero")
        canonical = _rehash(_snapshot(item))
        with self.database.transaction(join_existing=join_existing) as connection:
            self._insert_object(connection, spec, canonical)
            event = self._insert_event(
                connection,
                spec=spec,
                object_id=_object_id(canonical),
                event_id=event_id,
                event_kind=ModelChangeKind.CREATE,
                parent_event_id=None,
                before=None,
                after=canonical,
                diff=diff,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
            )
            self._write_object(
                connection,
                spec,
                canonical,
                head_event_id=event.event_id,
                redo_event_id=None,
            )
        return _snapshot(canonical)

    def create_node(
        self,
        node: ModelNode,
        *,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> ModelNode:
        return cast(
            ModelNode,
            self._create(
                node,
                spec=_NODE_SPEC,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def create_scheme(
        self,
        scheme: TaskScheme,
        *,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> TaskScheme:
        return cast(
            TaskScheme,
            self._create(
                scheme,
                spec=_SCHEME_SPEC,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def _get(self, spec: _ObjectSpec, object_id: str) -> CurrentObject:
        row = self.database.fetchone(
            f"SELECT * FROM {spec.table} WHERE {spec.id_column} = ?",  # noqa: S608
            (object_id,),
        )
        if row is None:
            raise CurrentObjectNotFoundError(f"{spec.object_kind.value}:{object_id}")
        return _record_from_row(row, spec).item

    def get_node(self, node_id: str) -> ModelNode:
        return cast(ModelNode, self._get(_NODE_SPEC, node_id))

    def get_scheme(self, scheme_id: str) -> TaskScheme:
        return cast(TaskScheme, self._get(_SCHEME_SPEC, scheme_id))

    def _list(
        self,
        spec: _ObjectSpec,
        lifecycle: ModelObjectLifecycle | None,
    ) -> tuple[CurrentObject, ...]:
        if lifecycle is None:
            rows = self.database.fetchall(
                f"SELECT {spec.id_column} FROM {spec.table} ORDER BY {spec.id_column}"  # noqa: S608
            )
        else:
            sql = f"""
                SELECT {spec.id_column} FROM {spec.table}
                WHERE lifecycle = ? ORDER BY {spec.id_column}
                """  # noqa: S608 - table and column come from closed internal specs
            rows = self.database.fetchall(
                sql,
                (lifecycle.value,),
            )
        return tuple(self._get(spec, row[spec.id_column]) for row in rows)

    def list_nodes(
        self,
        *,
        lifecycle: ModelObjectLifecycle | None = None,
    ) -> tuple[ModelNode, ...]:
        return cast(tuple[ModelNode, ...], self._list(_NODE_SPEC, lifecycle))

    def list_schemes(
        self,
        *,
        lifecycle: ModelObjectLifecycle | None = None,
    ) -> tuple[TaskScheme, ...]:
        return cast(tuple[TaskScheme, ...], self._list(_SCHEME_SPEC, lifecycle))

    def _update(
        self,
        proposed: CurrentObject,
        *,
        spec: _ObjectSpec,
        expected_semantic_revision: int | None,
        expected_layout_revision: int | None,
        event_id: str,
        event_kind: ModelChangeKind,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool,
    ) -> CurrentObject:
        semantic_changed = expected_semantic_revision is not None
        layout_changed = expected_layout_revision is not None
        with self.database.transaction(join_existing=join_existing) as connection:
            record = _record_from_row(
                self._row(connection, spec, _object_id(proposed)),
                spec,
            )
            _check_expected(
                record.item,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
            )
            canonical = _merge_update(
                record.item,
                proposed,
                semantic_changed=semantic_changed,
                layout_changed=layout_changed,
                occurred_at=occurred_at,
            )
            event = self._insert_event(
                connection,
                spec=spec,
                object_id=_object_id(canonical),
                event_id=event_id,
                event_kind=event_kind,
                parent_event_id=record.head_event_id,
                before=record.item,
                after=canonical,
                diff=diff,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
            )
            self._write_object(
                connection,
                spec,
                canonical,
                head_event_id=event.event_id,
                redo_event_id=None,
            )
        return _snapshot(canonical)

    def update_node(
        self,
        proposed: ModelNode,
        *,
        expected_semantic_revision: int | None,
        expected_layout_revision: int | None,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> ModelNode:
        return cast(
            ModelNode,
            self._update(
                proposed,
                spec=_NODE_SPEC,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                event_kind=ModelChangeKind.UPDATE,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def update_scheme(
        self,
        proposed: TaskScheme,
        *,
        expected_semantic_revision: int | None,
        expected_layout_revision: int | None,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> TaskScheme:
        return cast(
            TaskScheme,
            self._update(
                proposed,
                spec=_SCHEME_SPEC,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                event_kind=ModelChangeKind.UPDATE,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def archive_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> ModelNode:
        current = self.get_node(node_id)
        if current.lifecycle is ModelObjectLifecycle.ARCHIVED:
            raise CurrentObjectConflictError(f"node {node_id!r} is already archived")
        return cast(
            ModelNode,
            self._update(
                current.model_copy(update={"lifecycle": ModelObjectLifecycle.ARCHIVED}),
                spec=_NODE_SPEC,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=None,
                event_id=event_id,
                event_kind=ModelChangeKind.ARCHIVE,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def archive_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        diff: CanonicalModelDiff,
        join_existing: bool = False,
    ) -> TaskScheme:
        current = self.get_scheme(scheme_id)
        if current.lifecycle is ModelObjectLifecycle.ARCHIVED:
            raise CurrentObjectConflictError(f"scheme {scheme_id!r} is already archived")
        return cast(
            TaskScheme,
            self._update(
                current.model_copy(update={"lifecycle": ModelObjectLifecycle.ARCHIVED}),
                spec=_SCHEME_SPEC,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=None,
                event_id=event_id,
                event_kind=ModelChangeKind.ARCHIVE,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=join_existing,
            ),
        )

    def _travel(
        self,
        object_id: str,
        *,
        spec: _ObjectSpec,
        direction: Literal["undo", "redo"],
        expected_semantic_revision: int,
        expected_layout_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        join_existing: bool,
    ) -> CurrentObject:
        with self.database.transaction(join_existing=join_existing) as connection:
            record = _record_from_row(self._row(connection, spec, object_id), spec)
            _check_expected(
                record.item,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                require_both=True,
            )
            if direction == "undo":
                if record.head_event_id is None:
                    raise UndoRedoUnavailableError(f"{spec.object_kind.value} has no undo state")
                source_event = self._event_row(connection, record.head_event_id)
                if source_event.before_json is None:
                    raise UndoRedoUnavailableError(
                        f"{spec.object_kind.value} creation cannot be undone"
                    )
                target = _decode_object(source_event.before_json, spec)
                restored = _restore_snapshot(record.item, target, occurred_at=occurred_at)
                cursor_diff = _cursor_diff(
                    source_event.event.diff,
                    undo=True,
                    metadata={
                        "cursor": "undo",
                        "undone_event_id": source_event.event.event_id,
                        "next_redo_event_id": record.redo_event_id,
                    },
                )
                cursor = self._insert_event(
                    connection,
                    spec=spec,
                    object_id=object_id,
                    event_id=event_id,
                    event_kind=ModelChangeKind.UNDO,
                    parent_event_id=record.head_event_id,
                    before=record.item,
                    after=restored,
                    diff=cursor_diff,
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                )
                next_head = source_event.event.parent_event_id
                next_redo = cursor.event_id
            else:
                if record.redo_event_id is None:
                    raise UndoRedoUnavailableError(f"{spec.object_kind.value} has no redo state")
                undo_cursor = self._event_row(connection, record.redo_event_id)
                if undo_cursor.event.event_kind is not ModelChangeKind.UNDO:
                    raise CurrentObjectIntegrityError(
                        "redo pointer does not identify an undo cursor"
                    )
                undone_event_id = undo_cursor.event.diff.metadata.get("undone_event_id")
                pending_redo = undo_cursor.event.diff.metadata.get("next_redo_event_id")
                if type(undone_event_id) is not str or (
                    pending_redo is not None and type(pending_redo) is not str
                ):
                    raise CurrentObjectIntegrityError("undo cursor redo metadata is invalid")
                source_event = self._event_row(connection, undone_event_id)
                if source_event.after_json is None:
                    raise CurrentObjectIntegrityError("redo source event has no after snapshot")
                target = _decode_object(source_event.after_json, spec)
                restored = _restore_snapshot(record.item, target, occurred_at=occurred_at)
                cursor_diff = _cursor_diff(
                    source_event.event.diff,
                    undo=False,
                    metadata={
                        "cursor": "redo",
                        "redone_event_id": source_event.event.event_id,
                    },
                )
                self._insert_event(
                    connection,
                    spec=spec,
                    object_id=object_id,
                    event_id=event_id,
                    event_kind=ModelChangeKind.REDO,
                    parent_event_id=record.head_event_id,
                    before=record.item,
                    after=restored,
                    diff=cursor_diff,
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                )
                next_head = source_event.event.event_id
                next_redo = pending_redo
            self._write_object(
                connection,
                spec,
                restored,
                head_event_id=next_head,
                redo_event_id=next_redo,
            )
        return _snapshot(restored)

    def undo_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        join_existing: bool = False,
    ) -> ModelNode:
        return cast(
            ModelNode,
            self._travel(
                node_id,
                spec=_NODE_SPEC,
                direction="undo",
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                join_existing=join_existing,
            ),
        )

    def redo_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        join_existing: bool = False,
    ) -> ModelNode:
        return cast(
            ModelNode,
            self._travel(
                node_id,
                spec=_NODE_SPEC,
                direction="redo",
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                join_existing=join_existing,
            ),
        )

    def undo_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        join_existing: bool = False,
    ) -> TaskScheme:
        return cast(
            TaskScheme,
            self._travel(
                scheme_id,
                spec=_SCHEME_SPEC,
                direction="undo",
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                join_existing=join_existing,
            ),
        )

    def redo_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        event_id: str,
        actor_id: str,
        transaction_id: str,
        occurred_at: datetime,
        join_existing: bool = False,
    ) -> TaskScheme:
        return cast(
            TaskScheme,
            self._travel(
                scheme_id,
                spec=_SCHEME_SPEC,
                direction="redo",
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=event_id,
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                join_existing=join_existing,
            ),
        )

    def _history(self, spec: _ObjectSpec, object_id: str) -> tuple[ModelChangeEvent, ...]:
        self._get(spec, object_id)
        rows = self.database.fetchall(
            """
            SELECT * FROM model_change_events
            WHERE object_kind = ? AND object_id = ? ORDER BY rowid
            """,
            (spec.object_kind.value, object_id),
        )
        return tuple(_event_from_row(row).event for row in rows)

    def node_history(self, node_id: str) -> tuple[ModelChangeEvent, ...]:
        return self._history(_NODE_SPEC, node_id)

    def scheme_history(self, scheme_id: str) -> tuple[ModelChangeEvent, ...]:
        return self._history(_SCHEME_SPEC, scheme_id)


__all__ = [
    "CurrentObjectConflictError",
    "CurrentObjectIntegrityError",
    "CurrentObjectNotFoundError",
    "ModelWorkspaceRepositoryError",
    "SqliteModelWorkspaceRepository",
    "UndoRedoUnavailableError",
]
