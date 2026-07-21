"""Durable system-model edit session with delayed canonical commit."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    ModelNode,
    ModelObjectKind,
    TaskScheme,
)
from pilot_assessment.contracts.project import AuditEvent
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.model_workspace.content_migration import (
    CurrentModelContentMigrationError,
    ModelContentMigrationResult,
    migrate_current_model_content,
    model_content_fingerprint,
    normalise_current_model_row,
)
from pilot_assessment.model_workspace.hashing import rehash_model_node, rehash_task_scheme
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.model_workspace_repository import (
    SqliteModelWorkspaceRepository,
)
from pilot_assessment.persistence.transactions import (
    IdempotencyResult,
    IdempotencyStore,
    MutationResult,
)

Clock = Callable[[], datetime]


class ModelEditSessionError(RuntimeError):
    """Base class for deterministic edit-session failures."""


class ModelEditSessionConflictError(ModelEditSessionError):
    """Raised when canonical state changed after the edit-session baseline."""


class ModelEditSessionHistoryBoundaryError(ModelEditSessionError):
    """Raised when global undo or redo has reached its boundary."""


class ModelEditSessionDirtyError(ModelEditSessionError):
    """Raised when a canonical-only operation is requested while edits are dirty."""


@dataclass(frozen=True, slots=True)
class ModelEditSessionStatus:
    contract_id: str
    contract_version: str
    session_id: str
    model_library_id: str
    base_fingerprint: str
    cursor: int
    latest_sequence: int
    dirty: bool
    can_undo: bool
    can_redo: bool
    change_count: int
    recovered: bool


@dataclass(frozen=True, slots=True)
class ModelEditCommitResult:
    status: ModelEditSessionStatus
    changed_node_ids: tuple[str, ...]
    changed_scheme_ids: tuple[str, ...]


_MODEL_TABLES: tuple[tuple[str, str], ...] = (
    ("model_nodes", "node_id"),
    ("task_schemes", "scheme_id"),
)

_MODEL_TABLE_KINDS = {
    "model_nodes": ModelObjectKind.NODE,
    "task_schemes": ModelObjectKind.SCHEME,
}


@dataclass(frozen=True, slots=True)
class _NormalisedEditSnapshot:
    state_json: bytes
    state_hash: str
    fingerprint: str
    semantic_state_hash: str
    migrated: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ModelEditSessionError("edit-session timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _row_payload(row: sqlite3.Row) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in row.keys():  # noqa: SIM118 - sqlite3.Row iteration yields values
        value = row[key]
        payload[key] = (
            {"$bytes": base64.b64encode(value).decode("ascii")}
            if isinstance(value, bytes)
            else value
        )
    return payload


def _row_value(value: object) -> object:
    if isinstance(value, dict) and set(value) == {"$bytes"}:
        encoded = value.get("$bytes")
        if type(encoded) is not str:
            raise ModelEditSessionError("snapshot byte payload is invalid")
        return base64.b64decode(encoded, validate=True)
    return value


def _stable_hash(payload: object) -> str:
    return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def _object_state(item: ModelNode | TaskScheme, *, include_revisions: bool) -> dict[str, object]:
    excluded = {"created_at", "updated_at"}
    if not include_revisions:
        excluded.update({"semantic_revision", "layout_revision"})
    return item.model_dump(mode="json", exclude=excluded)


def _workspace_fingerprint(
    workspace: CurrentModelWorkspaceService,
    *,
    include_revisions: bool,
) -> str:
    payload = {
        "nodes": [
            _object_state(node, include_revisions=include_revisions)
            for node in sorted(workspace.list_nodes(), key=lambda item: item.node_id)
        ],
        "schemes": [
            _object_state(scheme, include_revisions=include_revisions)
            for scheme in sorted(workspace.list_schemes(), key=lambda item: item.scheme_id)
        ],
    }
    return _stable_hash(payload)


def _normalise_snapshot_state(payload: bytes) -> _NormalisedEditSnapshot:
    decoded = decode_canonical_json(payload)
    if not isinstance(decoded, dict):
        raise ModelEditSessionError("edit-session snapshot must be an object")

    nodes: list[ModelNode] = []
    schemes: list[TaskScheme] = []
    migrated = False
    normalised_payload: dict[str, list[dict[str, object]]] = {}
    for table, _id_column in _MODEL_TABLES:
        rows = decoded.get(table)
        if not isinstance(rows, list):
            raise ModelEditSessionError(f"edit-session snapshot is missing {table}")
        normalised_rows: list[dict[str, object]] = []
        for raw_row in rows:
            if not isinstance(raw_row, dict) or not raw_row:
                raise ModelEditSessionError(f"edit-session {table} row is invalid")
            stored_row = {key: _row_value(value) for key, value in raw_row.items()}
            normalised = normalise_current_model_row(
                stored_row,
                object_kind=_MODEL_TABLE_KINDS[table],
            )
            normalised_rows.append(
                {
                    key: (
                        {"$bytes": base64.b64encode(value).decode("ascii")}
                        if isinstance(value, bytes)
                        else value
                    )
                    for key, value in normalised.values.items()
                }
            )
            migrated = migrated or normalised.migrated
            if isinstance(normalised.item, ModelNode):
                nodes.append(normalised.item)
            else:
                schemes.append(normalised.item)
        normalised_payload[table] = normalised_rows

    state_json = encode_canonical_json(normalised_payload)
    return _NormalisedEditSnapshot(
        state_json=state_json,
        state_hash=hashlib.sha256(state_json).hexdigest(),
        fingerprint=model_content_fingerprint(tuple(nodes), tuple(schemes), include_revisions=True),
        semantic_state_hash=model_content_fingerprint(
            tuple(nodes), tuple(schemes), include_revisions=False
        ),
        migrated=migrated,
    )


class ModelEditSessionManager:
    """Own the durable editable mirror and one atomic canonical save boundary."""

    def __init__(
        self,
        *,
        model_root: Path,
        model_library_id: str,
        canonical_database: ProjectDatabase,
        canonical_workspace: CurrentModelWorkspaceService,
        canonical_idempotency: IdempotencyStore,
        operator_registry: OperatorRegistry,
        source_catalog: SourceCatalog,
        canonical_content_migration: ModelContentMigrationResult | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        self.model_root = model_root.resolve()
        self.model_library_id = model_library_id
        self.canonical_database = canonical_database
        self.canonical_workspace = canonical_workspace
        self.canonical_idempotency = canonical_idempotency
        self.operator_registry = operator_registry
        self.source_catalog = source_catalog
        self.canonical_content_migration = canonical_content_migration
        self._clock = clock
        self._database_path = self.model_root / "staging" / "model-edit" / "workspace.sqlite3"
        self._database: ProjectDatabase | None = None
        self.workspace: CurrentModelWorkspaceService
        self.audit: AuditRepository
        self.idempotency: IdempotencyStore
        self._recovered = False
        self._open_or_rebuild()

    @property
    def database(self) -> ProjectDatabase:
        if self._database is None or self._database.closed:
            raise ModelEditSessionError("model edit session is closed")
        return self._database

    def _bind(self, database: ProjectDatabase) -> None:
        self._database = database
        self.audit = AuditRepository(database)
        self.idempotency = IdempotencyStore(database, self.audit, clock=self._clock)
        self.workspace = CurrentModelWorkspaceService(
            SqliteModelWorkspaceRepository(database),
            model_library_id=self.model_library_id,
            operator_registry=self.operator_registry,
            source_catalog=self.source_catalog,
            clock=self._clock,
        )

    def _create_session_tables(self, database: ProjectDatabase) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS model_edit_session_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                session_id TEXT NOT NULL,
                model_library_id TEXT NOT NULL,
                base_fingerprint TEXT NOT NULL,
                baseline_state_hash TEXT NOT NULL,
                cursor INTEGER NOT NULL CHECK (cursor >= 0),
                latest_sequence INTEGER NOT NULL CHECK (latest_sequence >= 0),
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"] for row in database.fetchall("PRAGMA table_info(model_edit_session_state)")
        }
        if "project_id" in columns and "model_library_id" not in columns:
            database.execute(
                "ALTER TABLE model_edit_session_state RENAME COLUMN project_id TO model_library_id"
            )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS model_edit_session_snapshots (
                sequence INTEGER PRIMARY KEY CHECK (sequence >= 0),
                transaction_id TEXT NOT NULL,
                method TEXT NOT NULL,
                state_json BLOB NOT NULL,
                state_hash TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )

    def _open_or_rebuild(self) -> None:
        if self._database_path.exists():
            candidate = ProjectDatabase.connect(self._database_path, clock=self._clock)
            self._create_session_tables(candidate)
            state = candidate.fetchone("SELECT * FROM model_edit_session_state WHERE singleton = 1")
            canonical_fingerprint = _workspace_fingerprint(
                self.canonical_workspace,
                include_revisions=True,
            )
            accepted_base_fingerprints = {canonical_fingerprint}
            if self.canonical_content_migration is not None:
                accepted_base_fingerprints.update(
                    self.canonical_content_migration.compatible_predecessor_fingerprints
                )
            if (
                state is not None
                and state["model_library_id"] == self.model_library_id
                and state["base_fingerprint"] in accepted_base_fingerprints
                and candidate.fetchone(
                    "SELECT 1 FROM model_edit_session_snapshots WHERE sequence = 0"
                )
                is not None
            ):
                try:
                    snapshots: dict[int, tuple[sqlite3.Row, _NormalisedEditSnapshot]] = {}
                    for row in candidate.fetchall(
                        "SELECT * FROM model_edit_session_snapshots ORDER BY sequence"
                    ):
                        if hashlib.sha256(row["state_json"]).hexdigest() != row["state_hash"]:
                            raise ModelEditSessionError(
                                "edit-session snapshot hash claim does not match"
                            )
                        snapshots[int(row["sequence"])] = (
                            row,
                            _normalise_snapshot_state(row["state_json"]),
                        )
                    baseline = snapshots.get(0)
                    cursor = snapshots.get(int(state["cursor"]))
                    latest = snapshots.get(int(state["latest_sequence"]))
                    if baseline is None or cursor is None or latest is None:
                        raise ModelEditSessionError(
                            "edit-session history is missing baseline, cursor, or latest state"
                        )
                    if baseline[1].fingerprint != canonical_fingerprint:
                        raise ModelEditSessionError(
                            "edit-session baseline does not match canonical current content"
                        )

                    live_migration = migrate_current_model_content(
                        candidate,
                        migrated_at=self._clock(),
                    )
                    if live_migration.after_fingerprint != cursor[1].fingerprint:
                        raise ModelEditSessionError(
                            "edit-session live state does not match its cursor snapshot"
                        )
                    with candidate.transaction() as connection:
                        for sequence, (row, normalised) in snapshots.items():
                            if (
                                normalised.state_json != row["state_json"]
                                or normalised.state_hash != row["state_hash"]
                            ):
                                connection.execute(
                                    """
                                    UPDATE model_edit_session_snapshots
                                    SET state_json = ?, state_hash = ?
                                    WHERE sequence = ?
                                    """,
                                    (
                                        normalised.state_json,
                                        normalised.state_hash,
                                        sequence,
                                    ),
                                )
                        connection.execute(
                            """
                            UPDATE model_edit_session_state
                            SET base_fingerprint = ?, baseline_state_hash = ?
                            WHERE singleton = 1
                            """,
                            (
                                canonical_fingerprint,
                                baseline[1].semantic_state_hash,
                            ),
                        )
                except (
                    CurrentModelContentMigrationError,
                    ModelEditSessionError,
                    KeyError,
                    TypeError,
                    ValueError,
                    sqlite3.DatabaseError,
                ) as error:
                    candidate.close()
                    raise ModelEditSessionError(
                        "MODEL_EDIT_SESSION_CONTENT_MIGRATION_FAILED"
                    ) from error
                self._bind(candidate)
                self._recovered = self.status().dirty
                return
            candidate.close()
            self._preserve_incompatible_database()
        self._rebuild()

    def _preserve_incompatible_database(self) -> None:
        if not self._database_path.exists():
            return
        suffix = self._clock().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self._database_path.with_name(f"workspace.conflict.{suffix}.sqlite3")
        counter = 1
        while target.exists():
            target = self._database_path.with_name(f"workspace.conflict.{suffix}.{counter}.sqlite3")
            counter += 1
        self._database_path.replace(target)
        for suffix_name in ("-wal", "-shm"):
            sidecar = Path(f"{self._database_path}{suffix_name}")
            if sidecar.exists():
                sidecar.unlink()

    def _remove_database_files(self) -> None:
        for path in (
            self._database_path,
            Path(f"{self._database_path}-wal"),
            Path(f"{self._database_path}-shm"),
        ):
            if path.exists():
                path.unlink()

    def _copy_canonical_model_tables(self, database: ProjectDatabase) -> None:
        events = self.canonical_database.fetchall(
            "SELECT * FROM model_change_events ORDER BY occurred_at, event_id"
        )
        nodes = self.canonical_database.fetchall("SELECT * FROM model_nodes ORDER BY node_id")
        schemes = self.canonical_database.fetchall("SELECT * FROM task_schemes ORDER BY scheme_id")
        database.execute("PRAGMA foreign_keys = OFF")
        try:
            with database.transaction() as connection:
                for row in events:
                    columns = tuple(row.keys())
                    connection.execute(
                        f"INSERT INTO model_change_events({', '.join(columns)}) "
                        f"VALUES ({', '.join('?' for _ in columns)})",
                        tuple(row[column] for column in columns),
                    )
                for table, rows in (("model_nodes", nodes), ("task_schemes", schemes)):
                    for row in rows:
                        columns = tuple(row.keys())
                        connection.execute(
                            f"INSERT INTO {table}({', '.join(columns)}) "
                            f"VALUES ({', '.join('?' for _ in columns)})",
                            tuple(row[column] for column in columns),
                        )
        finally:
            database.execute("PRAGMA foreign_keys = ON")
        database.verify_integrity()

    def _rebuild(self) -> None:
        if self._database is not None and not self._database.closed:
            self._database.close()
        self._database = None
        self._remove_database_files()
        database = ProjectDatabase.connect(self._database_path, clock=self._clock)
        self._create_session_tables(database)
        self._copy_canonical_model_tables(database)
        self._bind(database)
        now = self._clock()
        base_fingerprint = _workspace_fingerprint(
            self.canonical_workspace,
            include_revisions=True,
        )
        baseline_state_hash = _workspace_fingerprint(
            self.canonical_workspace,
            include_revisions=False,
        )
        state_json = self._capture_state_json()
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO model_edit_session_state(
                    singleton, session_id, model_library_id, base_fingerprint,
                    baseline_state_hash, cursor, latest_sequence, started_at, updated_at
                ) VALUES (1, ?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (
                    f"model-edit-session.{uuid4().hex}",
                    self.model_library_id,
                    base_fingerprint,
                    baseline_state_hash,
                    _utc_text(now),
                    _utc_text(now),
                ),
            )
            connection.execute(
                """
                INSERT INTO model_edit_session_snapshots(
                    sequence, transaction_id, method, state_json, state_hash, recorded_at
                ) VALUES (0, 'baseline', 'model.edit.baseline', ?, ?, ?)
                """,
                (state_json, hashlib.sha256(state_json).hexdigest(), _utc_text(now)),
            )
        self._recovered = False

    def _capture_state_json(self) -> bytes:
        payload = {
            table: [
                _row_payload(row)
                for row in self.database.fetchall(f"SELECT * FROM {table} ORDER BY {id_column}")
            ]
            for table, id_column in _MODEL_TABLES
        }
        return encode_canonical_json(payload)

    def _restore_state_json(self, connection: sqlite3.Connection, payload: bytes) -> None:
        decoded = decode_canonical_json(payload)
        if not isinstance(decoded, dict):
            raise ModelEditSessionError("edit-session snapshot must be an object")
        connection.execute("PRAGMA defer_foreign_keys = ON")
        for table, _id_column in reversed(_MODEL_TABLES):
            connection.execute(f"DELETE FROM {table}")
        for table, _id_column in _MODEL_TABLES:
            rows = decoded.get(table)
            if not isinstance(rows, list):
                raise ModelEditSessionError(f"edit-session snapshot is missing {table}")
            for raw_row in rows:
                if not isinstance(raw_row, dict) or not raw_row:
                    raise ModelEditSessionError(f"edit-session {table} row is invalid")
                columns = tuple(raw_row)
                connection.execute(
                    f"INSERT INTO {table}({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    tuple(_row_value(raw_row[column]) for column in columns),
                )

    def status(self) -> ModelEditSessionStatus:
        state = self.database.fetchone("SELECT * FROM model_edit_session_state WHERE singleton = 1")
        if state is None:
            raise ModelEditSessionError("edit-session state is missing")
        current_state_hash = _workspace_fingerprint(self.workspace, include_revisions=False)
        cursor = int(state["cursor"])
        latest = int(state["latest_sequence"])
        return ModelEditSessionStatus(
            contract_id="model-edit-session-status",
            contract_version="0.2.0",
            session_id=state["session_id"],
            model_library_id=state["model_library_id"],
            base_fingerprint=state["base_fingerprint"],
            cursor=cursor,
            latest_sequence=latest,
            dirty=current_state_hash != state["baseline_state_hash"],
            can_undo=cursor > 0,
            can_redo=cursor < latest,
            change_count=cursor,
            recovered=self._recovered,
        )

    def require_clean_for_run(self) -> None:
        if self.status().dirty:
            raise ModelEditSessionDirtyError(
                "save or discard the current model edit session before previewing or running"
            )

    def refresh_clean_from_canonical(self) -> None:
        """Rebase a clean staging mirror after an external canonical import."""

        if self.status().dirty:
            raise ModelEditSessionDirtyError(
                "cannot refresh a dirty model edit session from canonical state"
            )
        self._rebuild()

    def capture_checkpoint(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_id: str,
        method: str,
    ) -> ModelEditSessionStatus:
        state = connection.execute(
            "SELECT * FROM model_edit_session_state WHERE singleton = 1"
        ).fetchone()
        if state is None:
            raise ModelEditSessionError("edit-session state is missing")
        cursor = int(state["cursor"])
        connection.execute(
            "DELETE FROM model_edit_session_snapshots WHERE sequence > ?",
            (cursor,),
        )
        payload = self._capture_state_json()
        payload_hash = hashlib.sha256(payload).hexdigest()
        current = connection.execute(
            "SELECT state_hash FROM model_edit_session_snapshots WHERE sequence = ?",
            (cursor,),
        ).fetchone()
        if current is not None and current["state_hash"] == payload_hash:
            return self.status()
        sequence = cursor + 1
        now = self._clock()
        connection.execute(
            """
            INSERT INTO model_edit_session_snapshots(
                sequence, transaction_id, method, state_json, state_hash, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sequence, transaction_id, method, payload, payload_hash, _utc_text(now)),
        )
        connection.execute(
            """
            UPDATE model_edit_session_state
            SET cursor = ?, latest_sequence = ?, updated_at = ?
            WHERE singleton = 1
            """,
            (sequence, sequence, _utc_text(now)),
        )
        return self.status()

    def _history_move(
        self,
        *,
        direction: str,
        transaction_id: str,
        actor_id: str,
    ) -> IdempotencyResult:
        method = f"model.edit.{direction}"
        params = {"transaction_id": transaction_id, "actor": actor_id}

        def mutate(connection: sqlite3.Connection) -> MutationResult:
            state = connection.execute(
                "SELECT * FROM model_edit_session_state WHERE singleton = 1"
            ).fetchone()
            if state is None:
                raise ModelEditSessionError("edit-session state is missing")
            cursor = int(state["cursor"])
            latest = int(state["latest_sequence"])
            target = cursor - 1 if direction == "undo" else cursor + 1
            if target < 0 or target > latest:
                raise ModelEditSessionHistoryBoundaryError(
                    f"model edit session has no {direction} state"
                )
            snapshot = connection.execute(
                "SELECT state_json FROM model_edit_session_snapshots WHERE sequence = ?",
                (target,),
            ).fetchone()
            if snapshot is None:
                raise ModelEditSessionError("edit-session history snapshot is missing")
            self._restore_state_json(connection, snapshot["state_json"])
            connection.execute(
                """
                UPDATE model_edit_session_state
                SET cursor = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (target, _utc_text(self._clock())),
            )
            status = self.status()
            audit = AuditEvent(
                audit_event_id=f"audit.{uuid4().hex}",
                event_type=method,
                actor_id=actor_id,
                occurred_at=self._clock(),
                subject_kind="model_edit_session",
                subject_id=status.session_id,
                transaction_id=transaction_id,
                details={"direction": direction, "cursor": target},
            )
            return MutationResult(
                response_payload={"edit_session": asdict(status)},
                audit_event=audit,
            )

        return self.idempotency.execute(
            transaction_id=transaction_id,
            method=method,
            params=params,
            mutation=mutate,
        )

    def undo(self, *, transaction_id: str, actor_id: str) -> IdempotencyResult:
        return self._history_move(
            direction="undo",
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def redo(self, *, transaction_id: str, actor_id: str) -> IdempotencyResult:
        return self._history_move(
            direction="redo",
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    @staticmethod
    def _changed_semantics(current: ModelNode | TaskScheme, draft: ModelNode | TaskScheme) -> bool:
        return (
            current.content_hash != draft.content_hash
            or current.lifecycle != draft.lifecycle
            or current.technical_status != draft.technical_status
            or current.diagnostics != draft.diagnostics
        )

    @staticmethod
    def _diff(*, kind: str, object_id: str, created: bool) -> CanonicalModelDiff:
        return CanonicalModelDiff(
            changed_paths=("/",),
            added_node_ids=((object_id,) if created and kind == "node" else ()),
            removed_node_ids=(),
            added_edge_ids=(),
            removed_edge_ids=(),
            metadata={"mutation": "commit_edit_session", "object_kind": kind},
        )

    def _apply_final_state(
        self,
        *,
        transaction_id: str,
        actor_id: str,
        occurred_at: datetime,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        repository = self.canonical_workspace.repository
        canonical_nodes = {node.node_id: node for node in self.canonical_workspace.list_nodes()}
        draft_nodes = {node.node_id: node for node in self.workspace.list_nodes()}
        canonical_schemes = {
            scheme.scheme_id: scheme for scheme in self.canonical_workspace.list_schemes()
        }
        draft_schemes = {scheme.scheme_id: scheme for scheme in self.workspace.list_schemes()}
        if set(canonical_nodes) - set(draft_nodes) or set(canonical_schemes) - set(draft_schemes):
            raise ModelEditSessionError("edit session cannot physically delete canonical objects")

        changed_nodes: list[str] = []
        for node_id in sorted(draft_nodes):
            draft = draft_nodes[node_id]
            current = canonical_nodes.get(node_id)
            if current is None:
                created = rehash_model_node(
                    draft.model_copy(
                        update={
                            "semantic_revision": 0,
                            "layout_revision": 0,
                            "created_at": occurred_at,
                            "updated_at": occurred_at,
                        }
                    )
                )
                repository.create_node(
                    created,
                    event_id=f"model-event.{uuid4().hex}",
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=self._diff(kind="node", object_id=node_id, created=True),
                    join_existing=True,
                )
                changed_nodes.append(node_id)
                continue
            semantic_changed = self._changed_semantics(current, draft)
            layout_changed = current.layout_hash != draft.layout_hash
            if not semantic_changed and not layout_changed:
                continue
            repository.update_node(
                draft,
                expected_semantic_revision=(
                    current.semantic_revision if semantic_changed else None
                ),
                expected_layout_revision=(current.layout_revision if layout_changed else None),
                event_id=f"model-event.{uuid4().hex}",
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=self._diff(kind="node", object_id=node_id, created=False),
                join_existing=True,
            )
            changed_nodes.append(node_id)

        changed_schemes: list[str] = []
        for scheme_id in sorted(draft_schemes):
            draft = draft_schemes[scheme_id]
            current = canonical_schemes.get(scheme_id)
            if current is None:
                created = rehash_task_scheme(
                    draft.model_copy(
                        update={
                            "semantic_revision": 0,
                            "layout_revision": 0,
                            "created_at": occurred_at,
                            "updated_at": occurred_at,
                        }
                    )
                )
                repository.create_scheme(
                    created,
                    event_id=f"model-event.{uuid4().hex}",
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=self._diff(kind="scheme", object_id=scheme_id, created=True),
                    join_existing=True,
                )
                changed_schemes.append(scheme_id)
                continue
            semantic_changed = self._changed_semantics(current, draft)
            layout_changed = current.layout_hash != draft.layout_hash
            if not semantic_changed and not layout_changed:
                continue
            repository.update_scheme(
                draft,
                expected_semantic_revision=(
                    current.semantic_revision if semantic_changed else None
                ),
                expected_layout_revision=(current.layout_revision if layout_changed else None),
                event_id=f"model-event.{uuid4().hex}",
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=self._diff(kind="scheme", object_id=scheme_id, created=False),
                join_existing=True,
            )
            changed_schemes.append(scheme_id)
        return tuple(changed_nodes), tuple(changed_schemes)

    def commit(self, *, transaction_id: str, actor_id: str) -> IdempotencyResult:
        params = {"transaction_id": transaction_id, "actor": actor_id}

        def mutate(_connection: sqlite3.Connection) -> MutationResult:
            current_fingerprint = _workspace_fingerprint(
                self.canonical_workspace,
                include_revisions=True,
            )
            status = self.status()
            if current_fingerprint != status.base_fingerprint:
                raise ModelEditSessionConflictError(
                    "canonical model changed after this edit session was opened"
                )
            occurred_at = self._clock()
            changed_nodes, changed_schemes = self._apply_final_state(
                transaction_id=transaction_id,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
            audit = AuditEvent(
                audit_event_id=f"audit.{uuid4().hex}",
                event_type="model.edit.commit",
                actor_id=actor_id,
                occurred_at=occurred_at,
                subject_kind="model_edit_session",
                subject_id=status.session_id,
                transaction_id=transaction_id,
                details={
                    "changed_node_ids": list(changed_nodes),
                    "changed_scheme_ids": list(changed_schemes),
                },
            )
            return MutationResult(
                response_payload={
                    "changed_node_ids": list(changed_nodes),
                    "changed_scheme_ids": list(changed_schemes),
                },
                audit_event=audit,
            )

        outcome = self.canonical_idempotency.execute(
            transaction_id=transaction_id,
            method="model.edit.commit",
            params=params,
            mutation=mutate,
        )
        self._rebuild()
        return outcome

    def discard(self, *, transaction_id: str, actor_id: str) -> IdempotencyResult:
        params = {"transaction_id": transaction_id, "actor": actor_id}
        status = self.status()

        def mutate(_connection: sqlite3.Connection) -> MutationResult:
            audit = AuditEvent(
                audit_event_id=f"audit.{uuid4().hex}",
                event_type="model.edit.discard",
                actor_id=actor_id,
                occurred_at=self._clock(),
                subject_kind="model_edit_session",
                subject_id=status.session_id,
                transaction_id=transaction_id,
                details={"discarded_change_count": status.change_count},
            )
            return MutationResult(
                response_payload={"discarded_change_count": status.change_count},
                audit_event=audit,
            )

        outcome = self.canonical_idempotency.execute(
            transaction_id=transaction_id,
            method="model.edit.discard",
            params=params,
            mutation=mutate,
        )
        self._rebuild()
        return outcome

    def close(self) -> None:
        if self._database is None:
            return
        self._database.close()
        self._database = None


__all__ = [
    "ModelEditCommitResult",
    "ModelEditSessionConflictError",
    "ModelEditSessionDirtyError",
    "ModelEditSessionError",
    "ModelEditSessionHistoryBoundaryError",
    "ModelEditSessionManager",
    "ModelEditSessionStatus",
]
