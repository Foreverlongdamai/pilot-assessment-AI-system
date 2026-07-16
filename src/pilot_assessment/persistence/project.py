"""Create, open, validate, recover, and close a portable managed project."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, ValidationError

from pilot_assessment.contracts.common import BundleRelativePath, StableId, StrictContractModel
from pilot_assessment.contracts.project import ProjectDescriptor
from pilot_assessment.persistence.database import (
    Clock,
    DatabaseError,
    DatabaseIntegrityError,
    ProjectDatabase,
    encode_canonical_json,
)

PROJECT_LOCATOR_NAME = "project.json"
PROJECT_DATABASE_NAME = "project.sqlite3"
PROJECT_DIRECTORY_NAMES = ("sessions", "artifacts", "exports", "logs", "staging")
_STAGING_DIRECTORY_NAMES = ("imports", "artifacts", "results")

RecoveryHook = Callable[[Path, ProjectDatabase], tuple[str, ...]]


class ProjectError(RuntimeError):
    """Base class for deterministic project lifecycle failures."""


class ProjectAlreadyExistsError(ProjectError):
    """Raised rather than adopting or overwriting an existing directory."""


class ProjectFormatError(ProjectError):
    """Raised when project.json or the on-disk layout violates the format contract."""


class ProjectIntegrityError(ProjectError):
    """Raised when project.json and SQLite canonical identity disagree."""


class _ProjectLocator(StrictContractModel):
    format_version: Literal["0.1.0"]
    project_id: StableId
    name: str
    created_at: AwareDatetime
    database_path: BundleRelativePath


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProjectFormatError("project lifecycle clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _resolve_root(root: str | Path) -> Path:
    return Path(root).expanduser().resolve()


def _write_locator(path: Path, locator: _ProjectLocator) -> None:
    payload = encode_canonical_json(locator.model_dump(mode="json"))
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _read_locator(path: Path) -> _ProjectLocator:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ProjectFormatError(f"cannot read {PROJECT_LOCATOR_NAME}") from error
    try:
        decoded = json.loads(payload.decode("utf-8", errors="strict"))
        locator = _ProjectLocator.model_validate(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ProjectFormatError(f"invalid database_path or project locator: {error}") from error
    if encode_canonical_json(locator.model_dump(mode="json")) != payload:
        raise ProjectFormatError("project locator must use canonical RFC 8785 JSON")
    if locator.database_path != PROJECT_DATABASE_NAME:
        raise ProjectFormatError(f"database_path must be {PROJECT_DATABASE_NAME!r}")
    return locator


def _descriptor_from_locator(locator: _ProjectLocator) -> ProjectDescriptor:
    return ProjectDescriptor(
        project_id=locator.project_id,
        format_version=locator.format_version,
        name=locator.name,
        created_at=locator.created_at,
    )


@dataclass(slots=True)
class ProjectStore:
    root: Path
    descriptor: ProjectDescriptor
    database: ProjectDatabase
    recovery_diagnostics: tuple[str, ...]
    _clock: Clock = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        project_id: str,
        name: str,
        created_at: datetime,
        clock: Clock = _utc_now,
    ) -> ProjectStore:
        project_root = _resolve_root(root)
        if project_root.exists():
            if not project_root.is_dir() or any(project_root.iterdir()):
                raise ProjectAlreadyExistsError(
                    "project creation requires a missing or empty directory"
                )
        else:
            project_root.mkdir(parents=True)

        descriptor = ProjectDescriptor(
            project_id=project_id,
            format_version="0.1.0",
            name=name,
            created_at=created_at,
        )
        for directory_name in PROJECT_DIRECTORY_NAMES:
            (project_root / directory_name).mkdir()
        (project_root / "artifacts" / "sha256").mkdir()
        for directory_name in _STAGING_DIRECTORY_NAMES:
            (project_root / "staging" / directory_name).mkdir()

        locator = _ProjectLocator(
            format_version=descriptor.format_version,
            project_id=descriptor.project_id,
            name=descriptor.name,
            created_at=descriptor.created_at,
            database_path=PROJECT_DATABASE_NAME,
        )
        _write_locator(project_root / PROJECT_LOCATOR_NAME, locator)
        database = ProjectDatabase.connect(project_root / PROJECT_DATABASE_NAME, clock=clock)
        now = _utc_text(clock())
        try:
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO project_metadata(
                        singleton, project_id, format_version, name, created_at,
                        clean_shutdown, last_opened_at, last_closed_at
                    ) VALUES (1, ?, ?, ?, ?, 0, ?, NULL)
                    """,
                    (
                        descriptor.project_id,
                        descriptor.format_version,
                        descriptor.name,
                        _utc_text(descriptor.created_at),
                        now,
                    ),
                )
        except BaseException:
            database.close()
            raise
        return cls(
            root=project_root,
            descriptor=descriptor,
            database=database,
            recovery_diagnostics=(),
            _clock=clock,
        )

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        clock: Clock = _utc_now,
        recovery_hooks: tuple[RecoveryHook, ...] = (),
    ) -> ProjectStore:
        project_root = _resolve_root(root)
        if not project_root.is_dir():
            raise ProjectFormatError("project root must be an existing directory")
        locator = _read_locator(project_root / PROJECT_LOCATOR_NAME)
        database_path = (project_root / locator.database_path).resolve()
        try:
            database_path.relative_to(project_root)
        except ValueError as error:
            raise ProjectFormatError("database_path escapes the project root") from error
        if not database_path.is_file():
            raise ProjectFormatError("project database does not exist")

        try:
            database = ProjectDatabase.connect(database_path, clock=clock)
        except DatabaseError as error:
            raise ProjectIntegrityError(str(error)) from error
        try:
            try:
                database.verify_integrity()
            except DatabaseIntegrityError as error:
                raise ProjectIntegrityError(str(error)) from error
            rows = database.fetchall(
                """
                SELECT project_id, format_version, name, created_at, clean_shutdown
                FROM project_metadata
                """
            )
            if len(rows) != 1:
                raise ProjectIntegrityError("project database must contain one metadata row")
            row = rows[0]
            stored = ProjectDescriptor(
                project_id=row["project_id"],
                format_version=row["format_version"],
                name=row["name"],
                created_at=row["created_at"],
            )
            expected = _descriptor_from_locator(locator)
            if stored != expected:
                raise ProjectIntegrityError("project locator and database identity disagree")

            diagnostics: list[str] = []
            if int(row["clean_shutdown"]) == 0:
                diagnostics.append("previous_shutdown_unclean")
            for hook in recovery_hooks:
                diagnostics.extend(hook(project_root, database))
            with database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE project_metadata
                    SET clean_shutdown = 0, last_opened_at = ?, last_closed_at = NULL
                    WHERE singleton = 1
                    """,
                    (_utc_text(clock()),),
                )
        except BaseException:
            database.close()
            raise
        return cls(
            root=project_root,
            descriptor=stored,
            database=database,
            recovery_diagnostics=tuple(diagnostics),
            _clock=clock,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE project_metadata
                SET clean_shutdown = 1, last_closed_at = ?
                WHERE singleton = 1
                """,
                (_utc_text(self._clock()),),
            )
        self.database.checkpoint()
        self.database.close()
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "PROJECT_DATABASE_NAME",
    "PROJECT_DIRECTORY_NAMES",
    "PROJECT_LOCATOR_NAME",
    "ProjectAlreadyExistsError",
    "ProjectError",
    "ProjectFormatError",
    "ProjectIntegrityError",
    "ProjectStore",
    "RecoveryHook",
]
