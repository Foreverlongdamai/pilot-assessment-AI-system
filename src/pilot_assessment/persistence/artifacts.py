"""Managed, content-addressed project artifacts with crash-safe recovery."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from pydantic import TypeAdapter, ValidationError

from pilot_assessment.contracts.common import BundleRelativePath, StableId
from pilot_assessment.contracts.project import (
    ArtifactLifecycle,
    ArtifactOwnerKind,
    ArtifactReference,
    ManagedArtifact,
)
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

_STABLE_ID = TypeAdapter(StableId)
_RELATIVE_PATH = TypeAdapter(BundleRelativePath)
_COPY_CHUNK_SIZE = 1024 * 1024


class ArtifactStoreError(RuntimeError):
    """Base class for deterministic managed-artifact failures."""


class ArtifactPathError(ArtifactStoreError):
    """Raised when a managed path is unsafe or outside the project root."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Raised when stored bytes or indexed metadata fail integrity checks."""


class ArtifactReferenceConflictError(ArtifactStoreError):
    """Raised when one owner role is already bound to another artifact."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when an exact artifact identifier is absent."""


class ArtifactTransactionConflictError(ArtifactStoreError):
    """Raised when an artifact transaction identifier is reused inconsistently."""


@dataclass(frozen=True, slots=True)
class ArtifactOwner:
    """The unique owner-role key that keeps an artifact active."""

    owner_kind: ArtifactOwnerKind
    owner_id: str
    role: str

    def __post_init__(self) -> None:
        try:
            owner_kind = TypeAdapter(ArtifactOwnerKind).validate_python(self.owner_kind)
            owner_id = _STABLE_ID.validate_python(self.owner_id)
            role = _STABLE_ID.validate_python(self.role)
        except ValidationError as error:
            raise ArtifactReferenceConflictError(f"invalid artifact owner: {error}") from error
        object.__setattr__(self, "owner_kind", owner_kind)
        object.__setattr__(self, "owner_id", owner_id)
        object.__setattr__(self, "role", role)


@dataclass(frozen=True, slots=True)
class ArtifactRecoveryReport:
    """A minimal, count-only report for deterministic startup recovery."""

    cleared_intents: int
    removed_staging_files: int
    removed_orphan_files: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ArtifactStoreError("artifact clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _row_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    raise ArtifactIntegrityError("stored artifact JSON must be bytes")


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


class ManagedArtifactStore:
    """Store immutable payloads once and maintain durable owner references."""

    def __init__(
        self,
        project_root: str | Path,
        database: ProjectDatabase,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise ArtifactPathError("project root must be an existing directory")
        self.root = root
        self.database = database
        self._clock = clock

    def put_bytes(
        self,
        payload: bytes,
        *,
        transaction_id: str,
        media_type: str,
        schema_id: str | None,
        owner: ArtifactOwner | None,
    ) -> ManagedArtifact:
        """Durably store exact bytes, deduplicating by their SHA-256 digest."""

        if type(payload) is not bytes:
            raise TypeError("artifact payload must be exact bytes")
        validated_transaction_id = self._validate_transaction_id(transaction_id)
        staging_relative = f"staging/artifacts/{validated_transaction_id}/payload"
        staging_path = self._resolve_relative(staging_relative)
        digest = hashlib.sha256(payload).hexdigest()
        self._write_staging_bytes(staging_path, payload, digest)
        return self._commit_staged(
            staging_path=staging_path,
            staging_relative=staging_relative,
            transaction_id=validated_transaction_id,
            digest=digest,
            byte_size=len(payload),
            media_type=media_type,
            schema_id=schema_id,
            owner=owner,
        )

    def put_file(
        self,
        source: str | Path,
        *,
        transaction_id: str,
        media_type: str,
        schema_id: str | None,
        owner: ArtifactOwner | None,
    ) -> ManagedArtifact:
        """Stream a file into managed storage without loading it fully into memory."""

        source_path = Path(source)
        if _is_link_or_junction(source_path) or not source_path.is_file():
            raise ArtifactPathError("artifact source must be a regular file")
        validated_transaction_id = self._validate_transaction_id(transaction_id)
        staging_relative = f"staging/artifacts/{validated_transaction_id}/payload"
        staging_path = self._resolve_relative(staging_relative)
        digest, byte_size = self._copy_to_staging(source_path, staging_path)
        return self._commit_staged(
            staging_path=staging_path,
            staging_relative=staging_relative,
            transaction_id=validated_transaction_id,
            digest=digest,
            byte_size=byte_size,
            media_type=media_type,
            schema_id=schema_id,
            owner=owner,
        )

    def get(self, artifact_id: str) -> ManagedArtifact:
        validated_id = self._validate_stable_id(artifact_id, "artifact_id")
        row = self.database.fetchone(
            "SELECT * FROM managed_artifacts WHERE artifact_id = ?",
            (validated_id,),
        )
        if row is None:
            raise ArtifactNotFoundError(f"artifact {validated_id!r} does not exist")
        return self._artifact_from_row(row)

    def reference_count(self, artifact_id: str) -> int:
        artifact = self.get(artifact_id)
        row = self.database.fetchone(
            "SELECT COUNT(*) AS count FROM artifact_references WHERE artifact_id = ?",
            (artifact.artifact_id,),
        )
        assert row is not None
        return int(row["count"])

    def add_reference(self, reference: ArtifactReference) -> ManagedArtifact:
        if not isinstance(reference, ArtifactReference):
            raise TypeError("reference must be an ArtifactReference")
        with self.database.transaction() as connection:
            return self.add_reference_in_transaction(connection, reference)

    def add_reference_in_transaction(
        self,
        connection: sqlite3.Connection,
        reference: ArtifactReference,
    ) -> ManagedArtifact:
        """Bind a reference through an owning service's existing DB transaction."""

        if not isinstance(reference, ArtifactReference):
            raise TypeError("reference must be an ArtifactReference")
        row = connection.execute(
            "SELECT * FROM managed_artifacts WHERE artifact_id = ?",
            (reference.artifact_id,),
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError(f"artifact {reference.artifact_id!r} does not exist")
        artifact = self._artifact_from_row(row)
        self._add_reference_in_transaction(connection, reference)
        return self._set_derived_lifecycle(connection, artifact)

    def remove_reference(self, owner: ArtifactOwner) -> bool:
        if not isinstance(owner, ArtifactOwner):
            raise TypeError("owner must be an ArtifactOwner")
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT artifact_id FROM artifact_references
                WHERE owner_kind = ? AND owner_id = ? AND role = ?
                """,
                (owner.owner_kind.value, owner.owner_id, owner.role),
            ).fetchone()
            if row is None:
                return False
            artifact_row = connection.execute(
                "SELECT * FROM managed_artifacts WHERE artifact_id = ?",
                (row["artifact_id"],),
            ).fetchone()
            if artifact_row is None:
                raise ArtifactIntegrityError("artifact reference points to a missing record")
            artifact = self._artifact_from_row(artifact_row)
            connection.execute(
                """
                DELETE FROM artifact_references
                WHERE owner_kind = ? AND owner_id = ? AND role = ?
                """,
                (owner.owner_kind.value, owner.owner_id, owner.role),
            )
            self._set_derived_lifecycle(connection, artifact)
            return True

    @contextmanager
    def open_verified(self, artifact_id: str) -> Iterator[BinaryIO]:
        """Verify the registered hash and size before yielding a readable stream."""

        artifact = self.get(artifact_id)
        path = self._resolve_relative(artifact.managed_relative_path)
        self._require_regular_managed_file(path)
        with path.open("rb") as stream:
            digest, byte_size = self._hash_stream(stream)
            if digest != artifact.sha256 or byte_size != artifact.byte_size:
                raise ArtifactIntegrityError(
                    f"SHA-256 integrity check failed for artifact {artifact.artifact_id!r}"
                )
            stream.seek(0)
            yield stream

    def recover(self) -> ArtifactRecoveryReport:
        """Resolve incomplete puts and remove only provable staging/orphan payloads."""

        rows = self.database.fetchall(
            """
            SELECT * FROM file_operation_intents
            WHERE operation = 'artifact.put'
            ORDER BY created_at, intent_id
            """
        )
        validated_intents = [self._validate_intent_row(row) for row in rows]
        registered_rows = self.database.fetchall(
            "SELECT managed_relative_path FROM managed_artifacts"
        )
        registered = {str(row["managed_relative_path"]) for row in registered_rows}

        removed_staging = 0
        removed_orphans = 0
        for (
            intent_id,
            _staging_relative,
            staging_path,
            final_relative,
            final_path,
        ) in validated_intents:
            if self._unlink_known_file(staging_path):
                removed_staging += 1
                self._prune_empty_parents(staging_path.parent, self.root / "staging" / "artifacts")
            if final_relative not in registered and self._unlink_known_file(final_path):
                removed_orphans += 1
                self._prune_empty_parents(final_path.parent, self.root / "artifacts" / "sha256")
            with self.database.transaction() as connection:
                connection.execute(
                    "DELETE FROM file_operation_intents WHERE intent_id = ?",
                    (intent_id,),
                )

        intent_staging_paths = {item[1] for item in validated_intents}
        staging_root = self._resolve_relative_directory("staging/artifacts")
        for candidate in tuple(staging_root.rglob("payload")):
            relative = self._relative_posix(candidate)
            if relative in intent_staging_paths:
                continue
            path = self._resolve_relative(relative)
            if self._unlink_known_file(path):
                removed_staging += 1
                self._prune_empty_parents(path.parent, staging_root)

        artifact_root = self._resolve_relative_directory("artifacts/sha256")
        for candidate in tuple(artifact_root.rglob("payload")):
            relative = self._relative_posix(candidate)
            if relative in registered:
                continue
            self._validate_content_path(relative)
            path = self._resolve_relative(relative)
            if self._unlink_known_file(path):
                removed_orphans += 1
                self._prune_empty_parents(path.parent, artifact_root)

        return ArtifactRecoveryReport(
            cleared_intents=len(validated_intents),
            removed_staging_files=removed_staging,
            removed_orphan_files=removed_orphans,
        )

    def _commit_staged(
        self,
        *,
        staging_path: Path,
        staging_relative: str,
        transaction_id: str,
        digest: str,
        byte_size: int,
        media_type: str,
        schema_id: str | None,
        owner: ArtifactOwner | None,
    ) -> ManagedArtifact:
        final_relative = self._content_relative_path(digest)
        final_path = self._resolve_relative(final_relative)
        now = self._clock()
        candidate = ManagedArtifact(
            artifact_id=f"artifact.{digest}",
            sha256=digest,
            byte_size=byte_size,
            media_type=media_type,
            schema_id=schema_id,
            managed_relative_path=final_relative,
            lifecycle=(
                ArtifactLifecycle.ACTIVE if owner is not None else ArtifactLifecycle.UNREFERENCED
            ),
            created_at=now,
        )
        intent_id = self._intent_id(transaction_id)
        self._record_intent(
            intent_id=intent_id,
            transaction_id=transaction_id,
            staging_relative=staging_relative,
            final_relative=final_relative,
            digest=digest,
            created_at=_utc_text(now),
        )

        self._ensure_parent_directory(final_path)
        if final_path.exists() or _is_link_or_junction(final_path):
            self._verify_file(final_path, digest, byte_size)
        else:
            staging_path.replace(final_path)

        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM managed_artifacts WHERE sha256 = ?",
                (digest,),
            ).fetchone()
            if row is None:
                artifact = candidate
                connection.execute(
                    """
                    INSERT INTO managed_artifacts(
                        artifact_id, sha256, byte_size, media_type, schema_id,
                        managed_relative_path, lifecycle, created_at, canonical_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.artifact_id,
                        artifact.sha256,
                        artifact.byte_size,
                        artifact.media_type,
                        artifact.schema_id,
                        artifact.managed_relative_path,
                        artifact.lifecycle.value,
                        _utc_text(artifact.created_at),
                        self._artifact_json(artifact),
                    ),
                )
            else:
                artifact = self._artifact_from_row(row)
                self._require_matching_metadata(artifact, candidate)

            if owner is not None:
                self._add_reference_in_transaction(
                    connection,
                    ArtifactReference(
                        owner_kind=owner.owner_kind,
                        owner_id=owner.owner_id,
                        role=owner.role,
                        artifact_id=artifact.artifact_id,
                    ),
                )
            artifact = self._set_derived_lifecycle(connection, artifact)
            connection.execute(
                "DELETE FROM file_operation_intents WHERE intent_id = ?",
                (intent_id,),
            )

        if staging_path.exists():
            self._unlink_known_file(staging_path)
        self._prune_empty_parents(staging_path.parent, self.root / "staging" / "artifacts")
        return artifact

    def _record_intent(
        self,
        *,
        intent_id: str,
        transaction_id: str,
        staging_relative: str,
        final_relative: str,
        digest: str,
        created_at: str,
    ) -> None:
        expected = (
            transaction_id,
            "artifact.put",
            staging_relative,
            final_relative,
            digest,
            "prepared",
        )
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM file_operation_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is not None:
                actual = (
                    row["transaction_id"],
                    row["operation"],
                    row["staging_relative_path"],
                    row["final_relative_path"],
                    row["expected_sha256"],
                    row["state"],
                )
                if actual != expected:
                    raise ArtifactTransactionConflictError(
                        "artifact transaction identifier was reused with different content"
                    )
                return
            connection.execute(
                """
                INSERT INTO file_operation_intents(
                    intent_id, transaction_id, operation, staging_relative_path,
                    final_relative_path, expected_sha256, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (intent_id, *expected, created_at),
            )

    def _artifact_from_row(self, row: sqlite3.Row) -> ManagedArtifact:
        try:
            decoded = decode_canonical_json(_row_bytes(row["canonical_json"]))
            artifact = ManagedArtifact.model_validate(decoded)
        except (ValueError, ValidationError) as error:
            raise ArtifactIntegrityError("stored artifact JSON is invalid") from error
        indexed = (
            row["artifact_id"],
            row["sha256"],
            int(row["byte_size"]),
            row["media_type"],
            row["schema_id"],
            row["managed_relative_path"],
            row["lifecycle"],
        )
        canonical = (
            artifact.artifact_id,
            artifact.sha256,
            artifact.byte_size,
            artifact.media_type,
            artifact.schema_id,
            artifact.managed_relative_path,
            artifact.lifecycle.value,
        )
        if indexed != canonical:
            raise ArtifactIntegrityError("artifact index and canonical JSON disagree")
        return artifact

    def _set_derived_lifecycle(
        self,
        connection: sqlite3.Connection,
        artifact: ManagedArtifact,
    ) -> ManagedArtifact:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM artifact_references WHERE artifact_id = ?",
            (artifact.artifact_id,),
        ).fetchone()
        assert row is not None
        lifecycle = (
            ArtifactLifecycle.ACTIVE if int(row["count"]) > 0 else ArtifactLifecycle.UNREFERENCED
        )
        if artifact.lifecycle is lifecycle:
            return artifact
        updated = artifact.model_copy(update={"lifecycle": lifecycle})
        connection.execute(
            """
            UPDATE managed_artifacts
            SET lifecycle = ?, canonical_json = ?
            WHERE artifact_id = ?
            """,
            (lifecycle.value, self._artifact_json(updated), updated.artifact_id),
        )
        return updated

    def _add_reference_in_transaction(
        self,
        connection: sqlite3.Connection,
        reference: ArtifactReference,
    ) -> None:
        row = connection.execute(
            """
            SELECT artifact_id FROM artifact_references
            WHERE owner_kind = ? AND owner_id = ? AND role = ?
            """,
            (reference.owner_kind.value, reference.owner_id, reference.role),
        ).fetchone()
        if row is not None:
            if row["artifact_id"] != reference.artifact_id:
                raise ArtifactReferenceConflictError(
                    "artifact owner role is already bound to another artifact"
                )
            return
        connection.execute(
            """
            INSERT INTO artifact_references(owner_kind, owner_id, role, artifact_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                reference.owner_kind.value,
                reference.owner_id,
                reference.role,
                reference.artifact_id,
            ),
        )

    @staticmethod
    def _artifact_json(artifact: ManagedArtifact) -> bytes:
        return encode_canonical_json(artifact.model_dump(mode="json"))

    @staticmethod
    def _require_matching_metadata(
        existing: ManagedArtifact,
        candidate: ManagedArtifact,
    ) -> None:
        if (
            existing.artifact_id != candidate.artifact_id
            or existing.byte_size != candidate.byte_size
            or existing.managed_relative_path != candidate.managed_relative_path
            or existing.media_type != candidate.media_type
            or existing.schema_id != candidate.schema_id
        ):
            raise ArtifactIntegrityError(
                "content-addressed artifact metadata conflicts with its existing record"
            )

    def _validate_intent_row(
        self,
        row: sqlite3.Row,
    ) -> tuple[str, str, Path, str, Path]:
        if row["operation"] != "artifact.put" or row["state"] != "prepared":
            raise ArtifactIntegrityError("unsupported artifact file-operation intent")
        transaction_id = self._validate_transaction_id(str(row["transaction_id"]))
        digest = str(row["expected_sha256"])
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ArtifactIntegrityError("artifact intent has an invalid SHA-256 digest")
        staging_relative = str(row["staging_relative_path"])
        final_relative = str(row["final_relative_path"])
        expected_staging = f"staging/artifacts/{transaction_id}/payload"
        if staging_relative != expected_staging:
            raise ArtifactPathError("artifact intent staging path is not canonical")
        if final_relative != self._content_relative_path(digest):
            raise ArtifactPathError("artifact intent final path is not content-addressed")
        return (
            str(row["intent_id"]),
            staging_relative,
            self._resolve_relative(staging_relative),
            final_relative,
            self._resolve_relative(final_relative),
        )

    def _validate_content_path(self, relative: str) -> None:
        parts = PurePosixPath(relative).parts
        if len(parts) != 5 or parts[:2] != ("artifacts", "sha256") or parts[-1] != "payload":
            raise ArtifactPathError("artifact payload path is not content-addressed")
        digest = parts[3]
        if parts[2] != digest[:2] or len(digest) != 64:
            raise ArtifactPathError("artifact payload path has an invalid digest layout")
        if any(character not in "0123456789abcdef" for character in digest):
            raise ArtifactPathError("artifact payload path has a non-hex digest")

    @staticmethod
    def _content_relative_path(digest: str) -> str:
        return f"artifacts/sha256/{digest[:2]}/{digest}/payload"

    @staticmethod
    def _intent_id(transaction_id: str) -> str:
        digest = hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()
        return f"intent.artifact.{digest}"

    def _validate_transaction_id(self, transaction_id: str) -> str:
        return self._validate_stable_id(transaction_id, "transaction_id")

    @staticmethod
    def _validate_stable_id(value: str, label: str) -> str:
        try:
            return _STABLE_ID.validate_python(value)
        except ValidationError as error:
            raise ArtifactStoreError(f"invalid {label}: {error}") from error

    def _resolve_relative(self, relative: str) -> Path:
        try:
            validated = _RELATIVE_PATH.validate_python(relative)
        except ValidationError as error:
            raise ArtifactPathError(f"unsafe managed path: {error}") from error
        lexical = self.root.joinpath(*PurePosixPath(validated).parts)
        current = self.root
        for part in PurePosixPath(validated).parts:
            current = current / part
            if current.exists() and _is_link_or_junction(current):
                raise ArtifactPathError("managed path contains a symbolic link or junction")
        resolved = lexical.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ArtifactPathError("managed path escapes the project root") from error
        return lexical

    def _resolve_relative_directory(self, relative: str) -> Path:
        marker = self._resolve_relative(f"{relative}/.directory-marker")
        directory = marker.parent
        if not directory.is_dir():
            raise ArtifactPathError(f"managed directory {relative!r} does not exist")
        return directory

    def _relative_posix(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ArtifactPathError("discovered path escapes the project root") from error

    def _ensure_parent_directory(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        relative = self._relative_posix(path)
        checked = self._resolve_relative(relative)
        if checked != path:
            raise ArtifactPathError("managed artifact path changed during directory creation")

    def _write_staging_bytes(self, path: Path, payload: bytes, digest: str) -> None:
        self._ensure_parent_directory(path)
        if path.exists() or _is_link_or_junction(path):
            self._verify_file(path, digest, len(payload), transaction_conflict=True)
            return
        try:
            with path.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            self._verify_file(path, digest, len(payload), transaction_conflict=True)

    def _copy_to_staging(self, source: Path, staging: Path) -> tuple[str, int]:
        self._ensure_parent_directory(staging)
        if staging.exists() or _is_link_or_junction(staging):
            with staging.open("rb") as stream:
                return self._hash_stream(stream)
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with source.open("rb") as source_stream, staging.open("xb") as target_stream:
                while chunk := source_stream.read(_COPY_CHUNK_SIZE):
                    digest.update(chunk)
                    byte_size += len(chunk)
                    target_stream.write(chunk)
                target_stream.flush()
                os.fsync(target_stream.fileno())
        except FileExistsError as error:
            raise ArtifactTransactionConflictError(
                "artifact transaction staging file appeared concurrently"
            ) from error
        return digest.hexdigest(), byte_size

    @staticmethod
    def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        while chunk := stream.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
            byte_size += len(chunk)
        return digest.hexdigest(), byte_size

    def _verify_file(
        self,
        path: Path,
        expected_digest: str,
        expected_size: int,
        *,
        transaction_conflict: bool = False,
    ) -> None:
        self._require_regular_managed_file(path)
        with path.open("rb") as stream:
            digest, byte_size = self._hash_stream(stream)
        if digest == expected_digest and byte_size == expected_size:
            return
        if transaction_conflict:
            raise ArtifactTransactionConflictError(
                "artifact transaction staging bytes do not match the requested payload"
            )
        raise ArtifactIntegrityError(f"SHA-256 integrity check failed for {path.name!r}")

    @staticmethod
    def _require_regular_managed_file(path: Path) -> None:
        if _is_link_or_junction(path) or not path.is_file():
            raise ArtifactIntegrityError(
                "managed artifact payload is missing or not a regular file"
            )

    def _unlink_known_file(self, path: Path) -> bool:
        if not path.exists() and not _is_link_or_junction(path):
            return False
        if _is_link_or_junction(path) or not path.is_file():
            raise ArtifactPathError("recovery target is not a regular managed file")
        path.unlink()
        return True

    @staticmethod
    def _prune_empty_parents(start: Path, stop: Path) -> None:
        current = start
        while current != stop and stop in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


__all__ = [
    "ArtifactIntegrityError",
    "ArtifactNotFoundError",
    "ArtifactOwner",
    "ArtifactPathError",
    "ArtifactRecoveryReport",
    "ArtifactReferenceConflictError",
    "ArtifactStoreError",
    "ArtifactTransactionConflictError",
    "ManagedArtifactStore",
]
