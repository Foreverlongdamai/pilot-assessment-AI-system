"""Create, open, lock, validate, and close the software-copy system model store."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, ValidationError

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    Sha256Digest,
    StableId,
    StrictContractModel,
)
from pilot_assessment.contracts.system import ProductVersion, SystemDescriptor
from pilot_assessment.persistence.database import (
    Clock,
    DatabaseError,
    DatabaseIntegrityError,
    ProjectDatabase,
    encode_canonical_json,
)

SYSTEM_LOCATOR_NAME = "system.json"
SYSTEM_DATABASE_NAME = "model-library.sqlite3"
SYSTEM_LOCK_NAME = ".system-writer.lock"
SYSTEM_STAGING_DIRECTORY = "staging/model-edit"


class SystemStoreError(RuntimeError):
    """Base class for deterministic system-store lifecycle failures."""


class SystemStoreAlreadyExistsError(SystemStoreError):
    """Raised rather than adopting unrelated content as a system store."""


class SystemStoreFormatError(SystemStoreError):
    """Raised when the locator or directory layout violates the contract."""


class SystemStoreIntegrityError(SystemStoreError):
    """Raised when the locator and database identities disagree."""


class SystemStoreLockedError(SystemStoreError):
    """Raised when another process already owns the software-copy writer lock."""


class _SystemLocator(StrictContractModel):
    format_version: Literal["0.1.0"]
    model_library_id: StableId
    database_path: BundleRelativePath
    created_from_product_version: ProductVersion
    starter_seed_id: StableId
    starter_seed_hash: Sha256Digest
    created_at: AwareDatetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SystemStoreFormatError("system lifecycle clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _resolve_root(root: str | Path) -> Path:
    return Path(root).expanduser().resolve()


def _write_locator(path: Path, locator: _SystemLocator) -> None:
    payload = encode_canonical_json(locator.model_dump(mode="json"))
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _read_locator(path: Path) -> _SystemLocator:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise SystemStoreFormatError(f"cannot read {SYSTEM_LOCATOR_NAME}") from error
    try:
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
        locator = _SystemLocator.model_validate(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise SystemStoreFormatError(f"invalid system locator: {error}") from error
    if encode_canonical_json(locator.model_dump(mode="json")) != payload:
        raise SystemStoreFormatError("system locator must use canonical RFC 8785 JSON")
    if locator.database_path != SYSTEM_DATABASE_NAME:
        raise SystemStoreFormatError(f"database_path must be {SYSTEM_DATABASE_NAME!r}")
    return locator


def _descriptor_from_locator(locator: _SystemLocator) -> SystemDescriptor:
    return SystemDescriptor(
        model_library_id=locator.model_library_id,
        format_version=locator.format_version,
        created_from_product_version=locator.created_from_product_version,
        starter_seed_id=locator.starter_seed_id,
        starter_seed_hash=locator.starter_seed_hash,
        created_at=locator.created_at,
    )


def _apply_system_schema(database: ProjectDatabase) -> None:
    """Apply the system-owner namespace on top of the shared SQLite kernel."""

    with database.transaction() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                model_library_id TEXT NOT NULL UNIQUE,
                format_version TEXT NOT NULL,
                created_from_product_version TEXT NOT NULL,
                starter_seed_id TEXT NOT NULL,
                starter_seed_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                clean_shutdown INTEGER NOT NULL CHECK (clean_shutdown IN (0, 1)),
                last_opened_at TEXT NOT NULL,
                last_closed_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO system_schema_migrations(version, name, applied_at)
            VALUES (1, 'm8b_system_model_owner_v1', ?)
            """,
            (_utc_text(_utc_now()),),
        )


class _SystemWriterLock:
    def __init__(self, path: Path, handle: BinaryIO) -> None:
        self.path = path
        self._handle = handle
        self._released = False

    @classmethod
    def acquire(cls, root: Path) -> _SystemWriterLock:
        root.mkdir(parents=True, exist_ok=True)
        path = root / SYSTEM_LOCK_NAME
        handle: BinaryIO | None = None
        try:
            handle = path.open("a+b")
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
            if handle is not None:
                handle.close()
            raise SystemStoreLockedError(
                "another Pilot Assessment process is already using this system model store"
            ) from error
        return cls(path, handle)

    def release(self) -> None:
        if self._released:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._released = True


@dataclass(slots=True)
class SystemStore:
    """The single writable model-state owner for one unpacked software copy."""

    root: Path
    descriptor: SystemDescriptor
    database: ProjectDatabase
    recovery_diagnostics: tuple[str, ...]
    _clock: Clock = field(repr=False)
    _writer_lock: _SystemWriterLock = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        model_library_id: str | None = None,
        created_from_product_version: str,
        starter_seed_id: str,
        starter_seed_hash: str,
        created_at: datetime,
        clock: Clock = _utc_now,
    ) -> Self:
        system_root = _resolve_root(root)
        writer_lock = _SystemWriterLock.acquire(system_root)
        try:
            occupants = tuple(
                path for path in system_root.iterdir() if path.name != SYSTEM_LOCK_NAME
            )
            if occupants:
                raise SystemStoreAlreadyExistsError(
                    "system store creation requires a missing or otherwise empty directory"
                )
            descriptor = SystemDescriptor(
                model_library_id=(model_library_id or f"model-library.{uuid4().hex}"),
                format_version="0.1.0",
                created_from_product_version=created_from_product_version,
                starter_seed_id=starter_seed_id,
                starter_seed_hash=starter_seed_hash,
                created_at=created_at,
            )
            (system_root / SYSTEM_STAGING_DIRECTORY).mkdir(parents=True)
            locator = _SystemLocator(
                format_version=descriptor.format_version,
                model_library_id=descriptor.model_library_id,
                database_path=SYSTEM_DATABASE_NAME,
                created_from_product_version=descriptor.created_from_product_version,
                starter_seed_id=descriptor.starter_seed_id,
                starter_seed_hash=descriptor.starter_seed_hash,
                created_at=descriptor.created_at,
            )
            _write_locator(system_root / SYSTEM_LOCATOR_NAME, locator)
            database = ProjectDatabase.connect(system_root / SYSTEM_DATABASE_NAME, clock=clock)
            _apply_system_schema(database)
            now = _utc_text(clock())
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO system_metadata(
                        singleton, model_library_id, format_version,
                        created_from_product_version, starter_seed_id, starter_seed_hash,
                        created_at, clean_shutdown, last_opened_at, last_closed_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, 0, ?, NULL)
                    """,
                    (
                        descriptor.model_library_id,
                        descriptor.format_version,
                        descriptor.created_from_product_version,
                        descriptor.starter_seed_id,
                        descriptor.starter_seed_hash,
                        _utc_text(descriptor.created_at),
                        now,
                    ),
                )
        except BaseException:
            writer_lock.release()
            raise
        return cls(
            root=system_root,
            descriptor=descriptor,
            database=database,
            recovery_diagnostics=(),
            _clock=clock,
            _writer_lock=writer_lock,
        )

    @classmethod
    def open(cls, root: str | Path, *, clock: Clock = _utc_now) -> Self:
        system_root = _resolve_root(root)
        if not system_root.is_dir():
            raise SystemStoreFormatError("system root must be an existing directory")
        writer_lock = _SystemWriterLock.acquire(system_root)
        database: ProjectDatabase | None = None
        try:
            locator = _read_locator(system_root / SYSTEM_LOCATOR_NAME)
            database_path = (system_root / locator.database_path).resolve()
            try:
                database_path.relative_to(system_root)
            except ValueError as error:
                raise SystemStoreFormatError("database_path escapes the system root") from error
            if not database_path.is_file():
                raise SystemStoreFormatError("system model database does not exist")
            try:
                database = ProjectDatabase.connect(database_path, clock=clock)
            except DatabaseError as error:
                raise SystemStoreIntegrityError(str(error)) from error
            _apply_system_schema(database)
            try:
                database.verify_integrity()
            except DatabaseIntegrityError as error:
                raise SystemStoreIntegrityError(str(error)) from error
            rows = database.fetchall(
                """
                SELECT model_library_id, format_version, created_from_product_version,
                       starter_seed_id, starter_seed_hash, created_at, clean_shutdown
                FROM system_metadata
                """
            )
            if len(rows) != 1:
                raise SystemStoreIntegrityError("system database must contain one metadata row")
            row = rows[0]
            stored = SystemDescriptor(
                model_library_id=row["model_library_id"],
                format_version=row["format_version"],
                created_from_product_version=row["created_from_product_version"],
                starter_seed_id=row["starter_seed_id"],
                starter_seed_hash=row["starter_seed_hash"],
                created_at=row["created_at"],
            )
            if stored != _descriptor_from_locator(locator):
                raise SystemStoreIntegrityError("system locator and database identity disagree")
            diagnostics = () if int(row["clean_shutdown"]) else ("previous_shutdown_unclean",)
            with database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE system_metadata
                    SET clean_shutdown = 0, last_opened_at = ?, last_closed_at = NULL
                    WHERE singleton = 1
                    """,
                    (_utc_text(clock()),),
                )
        except BaseException:
            if database is not None:
                database.close()
            writer_lock.release()
            raise
        return cls(
            root=system_root,
            descriptor=stored,
            database=database,
            recovery_diagnostics=diagnostics,
            _clock=clock,
            _writer_lock=writer_lock,
        )

    @classmethod
    def open_or_create(
        cls,
        root: str | Path,
        *,
        created_from_product_version: str,
        starter_seed_id: str,
        starter_seed_hash: str,
        model_library_id: str | None = None,
        clock: Clock = _utc_now,
    ) -> Self:
        system_root = _resolve_root(root)
        if (system_root / SYSTEM_LOCATOR_NAME).is_file():
            return cls.open(system_root, clock=clock)
        return cls.create(
            system_root,
            model_library_id=model_library_id,
            created_from_product_version=created_from_product_version,
            starter_seed_id=starter_seed_id,
            starter_seed_hash=starter_seed_hash,
            created_at=clock(),
            clock=clock,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def model_edit_root(self) -> Path:
        return self.root / SYSTEM_STAGING_DIRECTORY

    def close(self) -> None:
        if self._closed:
            return
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE system_metadata
                    SET clean_shutdown = 1, last_closed_at = ?
                    WHERE singleton = 1
                    """,
                    (_utc_text(self._clock()),),
                )
            self.database.checkpoint()
            self.database.close()
        finally:
            self._writer_lock.release()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "SYSTEM_DATABASE_NAME",
    "SYSTEM_LOCATOR_NAME",
    "SYSTEM_LOCK_NAME",
    "SYSTEM_STAGING_DIRECTORY",
    "SystemStore",
    "SystemStoreAlreadyExistsError",
    "SystemStoreError",
    "SystemStoreFormatError",
    "SystemStoreIntegrityError",
    "SystemStoreLockedError",
]
