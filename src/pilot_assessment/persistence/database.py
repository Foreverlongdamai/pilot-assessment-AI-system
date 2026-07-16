"""SQLite connection, transaction, integrity, and canonical JSON primitives."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from pydantic import JsonValue

from pilot_assessment.model_library.identity import jcs_bytes
from pilot_assessment.persistence.migrations import MigrationError, apply_migrations

Clock = Callable[[], datetime]
SqlParameters = Sequence[object] | Mapping[str, object]


class DatabaseError(RuntimeError):
    """Base class for project database failures."""


class DatabaseMigrationError(DatabaseError):
    """Raised when an explicit schema migration cannot be validated or applied."""


class DatabaseTransactionError(DatabaseError):
    """Raised when an invalid transaction boundary is requested."""


class DatabaseIntegrityError(DatabaseError):
    """Raised when SQLite integrity or foreign-key checks fail."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DatabaseError("database clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def encode_canonical_json(value: object) -> bytes:
    """Encode a supported JSON value as RFC 8785 canonical UTF-8 bytes."""

    return jcs_bytes(value)


def decode_canonical_json(payload: bytes) -> JsonValue:
    """Decode and verify RFC 8785 bytes before returning the JSON value."""

    if type(payload) is not bytes:
        raise TypeError("canonical JSON payload must be exact bytes")
    try:
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("payload must be valid UTF-8 JSON") from error
    try:
        canonical = encode_canonical_json(decoded)
    except (TypeError, ValueError) as error:
        raise ValueError("payload is outside the canonical JSON domain") from error
    if canonical != payload:
        raise ValueError("payload must use canonical RFC 8785 bytes")
    return decoded


class ProjectDatabase:
    """One project-scoped SQLite connection with explicit serialized transactions."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection
        self._lock = RLock()
        self._closed = False

    @classmethod
    def connect(cls, path: str | Path, *, clock: Clock = _utc_now) -> ProjectDatabase:
        database_path = Path(path).resolve()
        if database_path.exists() and not database_path.is_file():
            raise DatabaseError("database path must identify a regular file")
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            database_path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA trusted_schema = OFF")
            try:
                apply_migrations(connection, applied_at=_aware_utc_text(clock()))
            except MigrationError as error:
                raise DatabaseMigrationError(str(error)) from error
        except BaseException:
            connection.close()
            raise
        return cls(database_path, connection)

    @property
    def closed(self) -> bool:
        return self._closed

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            raise DatabaseError("project database is closed")
        return self._connection

    def execute(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> sqlite3.Cursor:
        with self._lock:
            return self._require_open().execute(sql, parameters)

    def fetchone(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> sqlite3.Row | None:
        with self._lock:
            return self._require_open().execute(sql, parameters).fetchone()

    def fetchall(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> list[sqlite3.Row]:
        with self._lock:
            return self._require_open().execute(sql, parameters).fetchall()

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._require_open()
            if connection.in_transaction:
                raise DatabaseTransactionError("nested project database transactions are forbidden")
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def verify_integrity(self) -> None:
        with self._lock:
            connection = self._require_open()
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
            results = tuple(str(row[0]) for row in integrity_rows)
            if results != ("ok",):
                raise DatabaseIntegrityError(f"SQLite integrity check failed: {results}")
            foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_rows:
                raise DatabaseIntegrityError(
                    f"SQLite foreign-key check failed for {len(foreign_key_rows)} row(s)"
                )

    def checkpoint(self) -> None:
        with self._lock:
            self._require_open().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._connection.in_transaction:
                self._connection.rollback()
            self._connection.close()
            self._closed = True


__all__ = [
    "Clock",
    "DatabaseError",
    "DatabaseIntegrityError",
    "DatabaseMigrationError",
    "DatabaseTransactionError",
    "ProjectDatabase",
    "SqlParameters",
    "decode_canonical_json",
    "encode_canonical_json",
]
