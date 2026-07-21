"""Inspect and consistently capture one saved, closed system model store."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import cast

SYSTEM_LOCATOR_NAME = "system.json"
SYSTEM_DATABASE_NAME = "model-library.sqlite3"
SYSTEM_EDIT_DATABASE = Path("staging/model-edit/workspace.sqlite3")
SYSTEM_LOCK_NAME = ".system-writer.lock"
SYSTEM_FORMAT_VERSION = "0.1.0"
SUPPORTED_DATABASE_SCHEMA_VERSION = 5
SUPPORTED_SYSTEM_SCHEMA_VERSION = 1

USER_OWNED_SYSTEM_TABLES = (
    "project_metadata",
    "sessions",
    "session_revisions",
    "managed_artifacts",
    "artifact_references",
    "run_preflights",
    "runs",
    "run_results",
    "model_run_preflights_v2",
    "model_run_links_v2",
)

SOURCE_LOCAL_SYSTEM_TABLES = ("legacy_system_model_import_receipts",)

_MODEL_TABLES = (
    ("model_nodes", "node_id"),
    ("task_schemes", "scheme_id"),
)
_WORKSPACE_EXCLUDED_FIELDS = {
    "created_at",
    "updated_at",
    "semantic_revision",
    "layout_revision",
}


class SystemCaptureError(RuntimeError):
    """A selected system cannot be safely used as a release input."""


@dataclass(frozen=True, slots=True)
class SystemCaptureReport:
    """Immutable facts observed while holding the selected system writer lock."""

    model_library_id: str
    system_format_version: str
    database_schema_version: int
    system_schema_version: int
    starter_seed_id: str
    starter_seed_hash: str
    model_identity_sha256: str
    node_count: int
    scheme_count: int
    source_locator_sha256: str
    source_canonical_sha256: str
    base_fingerprint: str
    baseline_state_hash: str
    user_owned_row_counts: dict[str, int]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_identity(connection: sqlite3.Connection) -> tuple[str, int, int]:
    """Return the release/runtime identity and dynamic current-object counts."""

    digest = hashlib.sha256()
    node_rows = connection.execute(
        "SELECT node_id, content_hash, layout_hash FROM model_nodes ORDER BY node_id"
    ).fetchall()
    scheme_rows = connection.execute(
        "SELECT scheme_id, content_hash, layout_hash FROM task_schemes ORDER BY scheme_id"
    ).fetchall()
    for kind, rows in (("node", node_rows), ("scheme", scheme_rows)):
        for identity, content_hash, layout_hash in rows:
            digest.update(kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(str(identity).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(content_hash).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(layout_hash).encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest(), len(node_rows), len(scheme_rows)


class _SystemWriterLock(AbstractContextManager["_SystemWriterLock"]):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None
        self._created = False

    def __enter__(self) -> _SystemWriterLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._created = not self.path.exists()
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise SystemCaptureError(
                "system is in use; close the application before building"
            ) from error
        self._handle = handle
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None
            if self._created:
                with suppress(FileNotFoundError):
                    self.path.unlink()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError(f"cannot read system database {path.name}: {error}") from error


def _verify_integrity(connection: sqlite3.Connection, *, label: str) -> None:
    try:
        results = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
        if results != ("ok",):
            raise SystemCaptureError(f"{label} database integrity check failed: {results}")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError(f"{label} database integrity check failed: {error}") from error
    if foreign_keys:
        raise SystemCaptureError(
            f"{label} database integrity check found {len(foreign_keys)} foreign-key error(s)"
        )


def _schema_version(
    connection: sqlite3.Connection,
    *,
    table: str,
    supported: int,
    label: str,
) -> int:
    try:
        rows = connection.execute(f"SELECT version FROM {table} ORDER BY version").fetchall()
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError(f"{label} schema history is missing or invalid") from error
    versions = [int(row[0]) for row in rows]
    if not versions or versions != list(range(1, versions[-1] + 1)):
        raise SystemCaptureError(f"{label} schema history is not contiguous")
    if versions[-1] > supported:
        raise SystemCaptureError(
            f"{label} uses unsupported schema version {versions[-1]} (maximum {supported})"
        )
    return versions[-1]


def _canonical_json(payload: bytes, *, label: str) -> object:
    try:
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemCaptureError(f"{label} is not valid UTF-8 JSON") from error
    return decoded


def _locator(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise SystemCaptureError(f"cannot read {SYSTEM_LOCATOR_NAME}") from error
    decoded = _canonical_json(payload, label=SYSTEM_LOCATOR_NAME)
    if not isinstance(decoded, dict):
        raise SystemCaptureError(f"{SYSTEM_LOCATOR_NAME} must contain one JSON object")
    locator = cast(dict[str, object], decoded)
    canonical = json.dumps(
        locator,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != payload:
        raise SystemCaptureError(f"{SYSTEM_LOCATOR_NAME} must use canonical JSON")
    required = {
        "format_version",
        "model_library_id",
        "database_path",
        "created_from_product_version",
        "starter_seed_id",
        "starter_seed_hash",
        "created_at",
    }
    if set(locator) != required:
        raise SystemCaptureError(f"{SYSTEM_LOCATOR_NAME} fields are incomplete or unknown")
    if locator.get("format_version") != SYSTEM_FORMAT_VERSION:
        raise SystemCaptureError(
            f"system uses unsupported format version {locator.get('format_version')!r}"
        )
    if locator.get("database_path") != SYSTEM_DATABASE_NAME:
        raise SystemCaptureError("system database_path is invalid")
    return locator, payload


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


def _baseline_snapshot_matches_canonical(
    canonical: sqlite3.Connection,
    edit: sqlite3.Connection,
) -> bool:
    try:
        row = edit.execute(
            "SELECT state_json FROM model_edit_session_snapshots WHERE sequence = 0"
        ).fetchone()
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError("model edit baseline snapshot is missing or invalid") from error
    if row is None or not isinstance(row[0], bytes):
        raise SystemCaptureError("model edit baseline snapshot is missing or invalid")
    baseline = _canonical_json(row[0], label="model edit baseline snapshot")
    expected = {
        table: [
            _row_payload(item)
            for item in canonical.execute(f"SELECT * FROM {table} ORDER BY {identity}")
        ]
        for table, identity in _MODEL_TABLES
    }
    return baseline == expected


def _workspace_objects(
    connection: sqlite3.Connection,
    *,
    table: str,
    identity: str,
) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    try:
        rows = connection.execute(
            f"SELECT canonical_json FROM {table} ORDER BY {identity}"
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError(f"model edit workspace table {table} is invalid") from error
    for row in rows:
        payload = row[0]
        if not isinstance(payload, bytes):
            raise SystemCaptureError(f"{table}.canonical_json must be bytes")
        decoded = _canonical_json(payload, label=f"{table}.canonical_json")
        if not isinstance(decoded, dict):
            raise SystemCaptureError(f"{table}.canonical_json must contain an object")
        normalized = dict(decoded)
        for key in _WORKSPACE_EXCLUDED_FIELDS:
            normalized.pop(key, None)
        objects.append(normalized)
    return objects


def _workspace_is_clean(
    canonical: sqlite3.Connection,
    edit: sqlite3.Connection,
) -> bool:
    for table, identity in (("model_nodes", "node_id"), ("task_schemes", "scheme_id")):
        if _workspace_objects(canonical, table=table, identity=identity) != _workspace_objects(
            edit,
            table=table,
            identity=identity,
        ):
            return False
    return True


def _user_owned_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    return {
        table: (
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            if table in tables
            else 0
        )
        for table in USER_OWNED_SYSTEM_TABLES
    }


def _require_no_transient_sqlite_files(root: Path) -> None:
    transients = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.sqlite3-wal", "*.sqlite3-shm")
        for path in root.rglob(pattern)
    )
    if transients:
        raise SystemCaptureError(
            "system has active SQLite transient files; close the application before building: "
            + ", ".join(transients)
        )


def _inspect_locked(source_root: Path) -> SystemCaptureReport:
    locator_path = source_root / SYSTEM_LOCATOR_NAME
    canonical_path = source_root / SYSTEM_DATABASE_NAME
    edit_path = source_root / SYSTEM_EDIT_DATABASE
    missing = [
        path.relative_to(source_root).as_posix()
        for path in (locator_path, canonical_path, edit_path)
        if not path.is_file()
    ]
    if missing:
        raise SystemCaptureError(f"system directory is incomplete: {missing}")
    _require_no_transient_sqlite_files(source_root)
    locator, locator_bytes = _locator(locator_path)
    canonical = _read_only_connection(canonical_path)
    edit = _read_only_connection(edit_path)
    try:
        _verify_integrity(canonical, label="canonical system")
        _verify_integrity(edit, label="model edit workspace")
        database_schema_version = _schema_version(
            canonical,
            table="schema_migrations",
            supported=SUPPORTED_DATABASE_SCHEMA_VERSION,
            label="system database",
        )
        edit_schema_version = _schema_version(
            edit,
            table="schema_migrations",
            supported=SUPPORTED_DATABASE_SCHEMA_VERSION,
            label="model edit workspace",
        )
        if edit_schema_version != database_schema_version:
            raise SystemCaptureError("canonical and edit-workspace schema versions differ")
        system_schema_version = _schema_version(
            canonical,
            table="system_schema_migrations",
            supported=SUPPORTED_SYSTEM_SCHEMA_VERSION,
            label="system owner",
        )
        metadata = canonical.execute(
            """
            SELECT model_library_id, format_version, starter_seed_id,
                   starter_seed_hash, clean_shutdown
            FROM system_metadata WHERE singleton = 1
            """
        ).fetchone()
        if metadata is None:
            raise SystemCaptureError("system metadata is missing")
        state = edit.execute(
            """
            SELECT model_library_id, base_fingerprint, baseline_state_hash
            FROM model_edit_session_state WHERE singleton = 1
            """
        ).fetchone()
        if state is None:
            raise SystemCaptureError("model edit session state is missing")
        model_library_id = str(metadata[0])
        if not (
            locator.get("model_library_id") == model_library_id == str(state[0])
            and locator.get("format_version") == str(metadata[1])
            and locator.get("starter_seed_id") == str(metadata[2])
            and locator.get("starter_seed_hash") == str(metadata[3])
        ):
            raise SystemCaptureError(
                "system locator, canonical database and edit identities differ"
            )
        if int(metadata[4]) != 1:
            raise SystemCaptureError(
                "system was not cleanly closed; close the application before building"
            )
        if not _baseline_snapshot_matches_canonical(canonical, edit) or not _workspace_is_clean(
            canonical,
            edit,
        ):
            raise SystemCaptureError(
                "system has unsaved model edits; save or discard them before building"
            )
        user_counts = _user_owned_counts(canonical)
        nonzero = {table: count for table, count in user_counts.items() if count}
        if nonzero:
            raise SystemCaptureError(f"system contains user-owned rows: {nonzero}")
        identity, node_count, scheme_count = model_identity(canonical)
        return SystemCaptureReport(
            model_library_id=model_library_id,
            system_format_version=str(metadata[1]),
            database_schema_version=database_schema_version,
            system_schema_version=system_schema_version,
            starter_seed_id=str(metadata[2]),
            starter_seed_hash=str(metadata[3]),
            model_identity_sha256=identity,
            node_count=node_count,
            scheme_count=scheme_count,
            source_locator_sha256=hashlib.sha256(locator_bytes).hexdigest(),
            source_canonical_sha256=sha256_file(canonical_path),
            base_fingerprint=str(state[1]),
            baseline_state_hash=str(state[2]),
            user_owned_row_counts=user_counts,
        )
    except sqlite3.DatabaseError as error:
        raise SystemCaptureError(f"system database inspection failed: {error}") from error
    finally:
        edit.close()
        canonical.close()


def inspect_system_source(source_root: Path) -> SystemCaptureReport:
    """Inspect one system without adopting, migrating, seeding, or modifying its model."""

    root = Path(source_root).expanduser().resolve()
    if not root.is_dir():
        raise SystemCaptureError("system source must be an existing directory")
    with _SystemWriterLock(root / SYSTEM_LOCK_NAME):
        return _inspect_locked(root)


def capture_current_system(
    source_root: Path,
    destination_root: Path,
) -> SystemCaptureReport:
    """Capture canonical system state; the caller rebuilds the target edit workspace."""

    source = Path(source_root).expanduser().resolve()
    destination = Path(destination_root).expanduser().resolve()
    if not source.is_dir():
        raise SystemCaptureError("system source must be an existing directory")
    if destination == source or destination.is_relative_to(source):
        raise SystemCaptureError("capture destination must be outside the source system")
    if destination.exists():
        raise SystemCaptureError("capture destination must not already exist")

    created = False
    try:
        with _SystemWriterLock(source / SYSTEM_LOCK_NAME):
            report = _inspect_locked(source)
            destination.mkdir(parents=True)
            created = True
            (destination / SYSTEM_EDIT_DATABASE.parent).mkdir(parents=True)
            shutil.copy2(source / SYSTEM_LOCATOR_NAME, destination / SYSTEM_LOCATOR_NAME)
            source_database = _read_only_connection(source / SYSTEM_DATABASE_NAME)
            target_database = sqlite3.connect(destination / SYSTEM_DATABASE_NAME)
            try:
                source_database.backup(target_database)
                target_database.execute("PRAGMA secure_delete = ON")
                for table in SOURCE_LOCAL_SYSTEM_TABLES:
                    target_database.execute(f"DELETE FROM {table}")
                target_database.commit()
                target_database.execute("VACUUM")
            finally:
                target_database.close()
                source_database.close()
            return report
    except BaseException:
        if created and destination.exists():
            shutil.rmtree(destination)
        raise


__all__ = [
    "SUPPORTED_DATABASE_SCHEMA_VERSION",
    "SUPPORTED_SYSTEM_SCHEMA_VERSION",
    "SYSTEM_DATABASE_NAME",
    "SYSTEM_EDIT_DATABASE",
    "SYSTEM_FORMAT_VERSION",
    "SYSTEM_LOCATOR_NAME",
    "SYSTEM_LOCK_NAME",
    "SOURCE_LOCAL_SYSTEM_TABLES",
    "USER_OWNED_SYSTEM_TABLES",
    "SystemCaptureError",
    "SystemCaptureReport",
    "capture_current_system",
    "inspect_system_source",
    "model_identity",
    "sha256_file",
]
