"""External inspection and durable import of immutable managed Session Bundles."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import RLock

from pydantic import TypeAdapter, ValidationError

from pilot_assessment.contracts.common import BundleRelativePath, StableId
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.project import (
    ArtifactOwnerKind,
    ArtifactReference,
    AuditEvent,
    SessionLifecycle,
    SessionRecord,
    SessionRevision,
    SessionSourceKind,
    TransactionReceipt,
)
from pilot_assessment.ingestion import (
    inspect_ingestion_readiness,
    inspect_loaded_ingestion_readiness,
)
from pilot_assessment.ingestion.manifest_loader import ManifestLoader
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.persistence.artifacts import ManagedArtifactStore
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.transactions import (
    IdempotencyResult,
    IdempotencyStore,
    MutationResult,
)

_STABLE_ID = TypeAdapter(StableId)
_RELATIVE_PATH = TypeAdapter(BundleRelativePath)
_COPY_CHUNK_SIZE = 1024 * 1024


class SessionImportError(RuntimeError):
    """Base class for deterministic Session Bundle import failures."""


class SessionImportPathError(SessionImportError):
    """Raised for path escape, links, junctions, or non-regular source entries."""


class SessionImportBlockedError(SessionImportError):
    """Raised when current M1/M2 checks do not permit synchronization."""


class SessionImportIntegrityError(SessionImportError):
    """Raised when copied or persisted bytes no longer match their identity."""


class SessionNotFoundError(SessionImportError):
    """Raised when an exact managed session is absent."""


class SessionRevisionNotFoundError(SessionImportError):
    """Raised when an exact managed session revision is absent."""


class SessionIdentityConflictError(SessionImportError):
    """Raised when a manifest session identity conflicts with a stored session."""


class ManagedSessionChangedError(SessionImportIntegrityError):
    """Raised when project-local Session Bundle bytes changed after import."""


@dataclass(frozen=True, slots=True)
class SessionImportLimits:
    max_files: int = 10_000
    max_single_file_bytes: int = 64 * 1024 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.max_files, self.max_single_file_bytes, self.max_total_bytes) <= 0:
            raise ValueError("session import limits must be positive")


@dataclass(frozen=True, slots=True)
class SessionFileRecord:
    relative_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SessionImportResult:
    session: SessionRecord
    revision: SessionRevision
    receipt: TransactionReceipt
    replayed: bool


@dataclass(frozen=True, slots=True)
class SessionRecoveryReport:
    cleared_intents: int
    removed_staging_trees: int
    removed_orphan_trees: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SessionImportError("session import clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


class SessionImportService:
    """Inspect external bundles and copy exact immutable revisions into one project."""

    def __init__(
        self,
        project_root: str | Path,
        database: ProjectDatabase,
        *,
        project_id: str,
        artifact_store: ManagedArtifactStore | None = None,
        idempotency: IdempotencyStore | None = None,
        limits: SessionImportLimits | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise SessionImportPathError("project root must be an existing directory")
        self.root = root
        self.database = database
        self.project_id = self._stable_id(project_id, "project_id")
        self.artifacts = artifact_store or ManagedArtifactStore(root, database, clock=clock)
        if self.artifacts.database is not database or self.artifacts.root != root:
            raise SessionImportError("artifact and session services must share one project")
        if idempotency is None:
            idempotency = IdempotencyStore(
                database,
                AuditRepository(database),
                clock=clock,
            )
        if idempotency.database is not database:
            raise SessionImportError("idempotency and session services must share one database")
        self.idempotency = idempotency
        self.limits = limits or SessionImportLimits()
        self._clock = clock
        self._lock = RLock()

    def inspect(self, external_bundle: str | Path) -> IngestionReadinessReport:
        """Run current M1/M2 checks without copying or changing project state."""

        return inspect_ingestion_readiness(self._external_root(external_bundle)).report

    def import_bundle(
        self,
        external_bundle: str | Path,
        *,
        transaction_id: str,
        imported_by: str,
    ) -> SessionImportResult:
        """Copy and register one exact revision, replaying a completed request exactly."""

        transaction_id = self._stable_id(transaction_id, "transaction_id")
        imported_by = self._stable_id(imported_by, "imported_by")
        source_locator = Path(external_bundle).expanduser().resolve(strict=False)
        params = {
            "project_id": self.project_id,
            "source_locator_hash": hashlib.sha256(str(source_locator).encode("utf-8")).hexdigest(),
            "imported_by": imported_by,
        }
        if self.database.fetchone(
            "SELECT 1 FROM idempotency_transactions WHERE transaction_id = ?",
            (transaction_id,),
        ):
            replay = self.idempotency.execute(
                transaction_id=transaction_id,
                method="session.import",
                params=params,
                mutation=self._unexpected_replay_mutation,
            )
            return self._result_from_receipt(replay)

        with self._lock:
            if self.database.fetchone(
                "SELECT 1 FROM idempotency_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ):
                replay = self.idempotency.execute(
                    transaction_id=transaction_id,
                    method="session.import",
                    params=params,
                    mutation=self._unexpected_replay_mutation,
                )
                return self._result_from_receipt(replay)
            self.recover()
            try:
                external_root = self._external_root(external_bundle)
                external_loaded = ManifestLoader().load(external_root)
                external_outcome = inspect_loaded_ingestion_readiness(external_loaded)
                self._require_importable(external_outcome.report)
                source_inventory = self._inventory(external_root)

                staging_relative = f"staging/imports/{transaction_id}/bundle"
                staging_bundle = self._project_path(staging_relative)
                staging_bundle.mkdir(parents=True)
                self._copy_inventory(external_root, staging_bundle, source_inventory)
                staged_inventory = self._inventory(staging_bundle)
                if staged_inventory != source_inventory:
                    raise SessionImportIntegrityError(
                        "staged Session Bundle inventory differs from the external snapshot"
                    )

                staged_loaded = ManifestLoader().load(staging_bundle)
                staged_outcome = inspect_loaded_ingestion_readiness(staged_loaded)
                self._require_importable(staged_outcome.report)
                if (
                    staged_outcome.report.source_snapshot_fingerprint
                    != external_outcome.report.source_snapshot_fingerprint
                ):
                    raise SessionImportIntegrityError(
                        "staged Session Bundle readiness fingerprint changed during copy"
                    )

                manifest_hash = self._manifest_hash(staged_inventory)
                inventory_hash = self._inventory_hash(staged_inventory)
                bundle_root_hash = self._bundle_root_hash(manifest_hash, inventory_hash)
                # Keep the directory identity short enough for ordinary Windows path APIs;
                # the complete 256-bit root identity remains frozen on SessionRevision.
                revision_id = f"session-revision.{bundle_root_hash[:32]}"
                session_id = staged_loaded.manifest.session_id
                final_relative = f"sessions/{session_id}/{revision_id}/bundle"
                final_bundle = self._project_path(final_relative)
                now = self._clock()

                readiness_artifact = self.artifacts.put_bytes(
                    encode_canonical_json(staged_outcome.report.model_dump(mode="json")),
                    transaction_id=(
                        "readiness."
                        + hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()[:32]
                    ),
                    media_type="application/json",
                    schema_id="ingestion-readiness-report-0.1.0",
                    owner=None,
                )
                revision = SessionRevision(
                    session_revision_id=revision_id,
                    session_id=session_id,
                    managed_bundle_path=final_relative,
                    manifest_hash=manifest_hash,
                    bundle_root_hash=bundle_root_hash,
                    file_inventory_hash=inventory_hash,
                    source_kind=SessionSourceKind.MANAGED_IMPORT,
                    imported_at=now,
                    imported_by=imported_by,
                    ingestion_readiness_ref=readiness_artifact.artifact_id,
                    synchronization_ref=None,
                )
                intent_id = self._record_intent(
                    transaction_id=transaction_id,
                    staging_relative=staging_relative,
                    final_relative=final_relative,
                    bundle_root_hash=bundle_root_hash,
                    created_at=_utc_text(now),
                )
                self._promote_or_reuse(
                    staging_bundle,
                    final_bundle,
                    source_inventory,
                    bundle_root_hash,
                )
                result = self.idempotency.execute(
                    transaction_id=transaction_id,
                    method="session.import",
                    params=params,
                    mutation=lambda connection: self._register_import(
                        connection,
                        revision=revision,
                        participant_id=staged_loaded.manifest.participant.pseudonymous_id,
                        inventory=source_inventory,
                        intent_id=intent_id,
                        transaction_id=transaction_id,
                        imported_by=imported_by,
                    ),
                )
            except BaseException:
                self.recover()
                raise
            self._prune_empty_parents(
                staging_bundle.parent,
                self.root / "staging" / "imports",
            )
            return self._result_from_receipt(result)

    def get(self, session_id: str) -> SessionRecord:
        session_id = self._stable_id(session_id, "session_id")
        row = self.database.fetchone("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._session_from_row(row)

    def get_revision(self, session_revision_id: str) -> SessionRevision:
        revision_id = self._stable_id(session_revision_id, "session_revision_id")
        row = self.database.fetchone(
            "SELECT * FROM session_revisions WHERE session_revision_id = ?",
            (revision_id,),
        )
        if row is None:
            raise SessionRevisionNotFoundError(revision_id)
        return self._revision_from_row(row)

    def list_sessions(self) -> tuple[SessionRecord, ...]:
        rows = self.database.fetchall("SELECT * FROM sessions ORDER BY created_at, rowid")
        return tuple(self._session_from_row(row) for row in rows)

    def list_revisions(self, session_id: str) -> tuple[SessionRevision, ...]:
        session_id = self._stable_id(session_id, "session_id")
        rows = self.database.fetchall(
            """
            SELECT * FROM session_revisions
            WHERE session_id = ? ORDER BY imported_at, rowid
            """,
            (session_id,),
        )
        return tuple(self._revision_from_row(row) for row in rows)

    def managed_bundle_path(self, session_revision_id: str) -> Path:
        revision = self.get_revision(session_revision_id)
        path = self._project_path(revision.managed_bundle_path)
        if not path.is_dir():
            raise ManagedSessionChangedError("managed Session Bundle directory is missing")
        return path

    def verify_managed_revision(self, session_revision_id: str) -> SessionRevision:
        revision = self.get_revision(session_revision_id)
        inventory = self._inventory(self.managed_bundle_path(session_revision_id))
        if inventory != self._stored_inventory(session_revision_id):
            raise ManagedSessionChangedError("MANAGED_SESSION_CHANGED: file inventory differs")
        manifest_hash = self._manifest_hash(inventory)
        inventory_hash = self._inventory_hash(inventory)
        root_hash = self._bundle_root_hash(manifest_hash, inventory_hash)
        if (
            manifest_hash != revision.manifest_hash
            or inventory_hash != revision.file_inventory_hash
            or root_hash != revision.bundle_root_hash
        ):
            raise ManagedSessionChangedError("MANAGED_SESSION_CHANGED: root hash differs")
        return revision

    def recover(self) -> SessionRecoveryReport:
        """Remove only prepared session-import trees without a durable revision owner."""

        with self._lock:
            rows = self.database.fetchall(
                """
                SELECT * FROM file_operation_intents
                WHERE operation = 'session.import'
                ORDER BY created_at, intent_id
                """
            )
            intents = [self._validate_intent(row) for row in rows]
            registered = {
                str(row["managed_bundle_path"])
                for row in self.database.fetchall(
                    "SELECT managed_bundle_path FROM session_revisions"
                )
            }
            removed_staging = 0
            removed_orphans = 0
            for intent_id, _staging_relative, staging_path, final_relative, final_path in intents:
                if staging_path.exists():
                    self._remove_tree(staging_path, self.root / "staging" / "imports")
                    removed_staging += 1
                    self._prune_empty_parents(
                        staging_path.parent,
                        self.root / "staging" / "imports",
                    )
                if final_relative not in registered and final_path.exists():
                    self._remove_tree(final_path, self.root / "sessions")
                    removed_orphans += 1
                    self._prune_empty_parents(final_path.parent, self.root / "sessions")
                with self.database.transaction() as connection:
                    connection.execute(
                        "DELETE FROM file_operation_intents WHERE intent_id = ?",
                        (intent_id,),
                    )

            staging_root = self.root / "staging" / "imports"
            for child in tuple(staging_root.iterdir()):
                self._remove_tree(child, staging_root)
                removed_staging += 1
            return SessionRecoveryReport(
                cleared_intents=len(intents),
                removed_staging_trees=removed_staging,
                removed_orphan_trees=removed_orphans,
            )

    @staticmethod
    def _unexpected_replay_mutation(_connection: sqlite3.Connection) -> MutationResult:
        raise SessionImportIntegrityError("completed transaction unexpectedly executed again")

    def _result_from_receipt(self, result: IdempotencyResult) -> SessionImportResult:
        payload = result.receipt.response_payload
        if payload is None:
            raise SessionImportIntegrityError("session import receipt has no response")
        session_id = payload.get("session_id")
        revision_id = payload.get("session_revision_id")
        if not isinstance(session_id, str) or not isinstance(revision_id, str):
            raise SessionImportIntegrityError("session import receipt IDs are invalid")
        return SessionImportResult(
            session=self.get(session_id),
            revision=self.get_revision(revision_id),
            receipt=result.receipt,
            replayed=result.replayed,
        )

    def _register_import(
        self,
        connection: sqlite3.Connection,
        *,
        revision: SessionRevision,
        participant_id: str,
        inventory: tuple[SessionFileRecord, ...],
        intent_id: str,
        transaction_id: str,
        imported_by: str,
    ) -> MutationResult:
        revision_row = connection.execute(
            "SELECT * FROM session_revisions WHERE session_revision_id = ?",
            (revision.session_revision_id,),
        ).fetchone()
        if revision_row is None:
            connection.execute(
                """
                INSERT INTO session_revisions(
                    session_revision_id, session_id, managed_bundle_path,
                    manifest_hash, bundle_root_hash, file_inventory_hash,
                    source_kind, imported_at, imported_by,
                    ingestion_readiness_ref, synchronization_ref, canonical_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.session_revision_id,
                    revision.session_id,
                    revision.managed_bundle_path,
                    revision.manifest_hash,
                    revision.bundle_root_hash,
                    revision.file_inventory_hash,
                    revision.source_kind.value,
                    _utc_text(revision.imported_at),
                    revision.imported_by,
                    revision.ingestion_readiness_ref,
                    revision.synchronization_ref,
                    encode_canonical_json(revision.model_dump(mode="json")),
                ),
            )
            connection.executemany(
                """
                INSERT INTO session_files(
                    session_revision_id, relative_path, byte_size, sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (
                        revision.session_revision_id,
                        item.relative_path,
                        item.byte_size,
                        item.sha256,
                    )
                    for item in inventory
                ),
            )
        else:
            stored_revision = self._revision_from_row(revision_row)
            stored_inventory = self._stored_inventory_in_transaction(
                connection,
                revision.session_revision_id,
            )
            if (
                stored_revision.session_id != revision.session_id
                or stored_revision.bundle_root_hash != revision.bundle_root_hash
                or stored_revision.managed_bundle_path != revision.managed_bundle_path
                or stored_inventory != inventory
            ):
                raise SessionImportIntegrityError(
                    "existing session revision conflicts with the imported content"
                )
            revision = stored_revision

        session_row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (revision.session_id,),
        ).fetchone()
        if session_row is None:
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id, project_id, participant_id, lifecycle,
                    current_session_revision_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.session_id,
                    self.project_id,
                    participant_id,
                    SessionLifecycle.ACTIVE.value,
                    revision.session_revision_id,
                    _utc_text(revision.imported_at),
                ),
            )
        else:
            stored_session = self._session_from_row(session_row)
            if (
                stored_session.project_id != self.project_id
                or stored_session.participant_id != participant_id
            ):
                raise SessionIdentityConflictError(
                    "session ID is already registered for another project or participant"
                )
            connection.execute(
                """
                UPDATE sessions SET current_session_revision_id = ?, lifecycle = ?
                WHERE session_id = ?
                """,
                (
                    revision.session_revision_id,
                    SessionLifecycle.ACTIVE.value,
                    revision.session_id,
                ),
            )

        self.artifacts.add_reference_in_transaction(
            connection,
            ArtifactReference(
                owner_kind=ArtifactOwnerKind.SESSION_REVISION,
                owner_id=revision.session_revision_id,
                role="ingestion_readiness",
                artifact_id=revision.ingestion_readiness_ref,
            ),
        )
        connection.execute(
            "DELETE FROM file_operation_intents WHERE intent_id = ?",
            (intent_id,),
        )
        audit_id = (
            "audit.session-import." + hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()
        )
        return MutationResult(
            response_payload={
                "session_id": revision.session_id,
                "session_revision_id": revision.session_revision_id,
                "bundle_root_hash": revision.bundle_root_hash,
            },
            audit_event=AuditEvent(
                audit_event_id=audit_id,
                event_type="session.revision.imported",
                actor_id=imported_by,
                occurred_at=self._clock(),
                subject_kind="session_revision",
                subject_id=revision.session_revision_id,
                transaction_id=transaction_id,
                details={
                    "bundle_root_hash": revision.bundle_root_hash,
                    "file_inventory_hash": revision.file_inventory_hash,
                    "file_count": len(inventory),
                    "ingestion_readiness_ref": revision.ingestion_readiness_ref,
                },
            ),
        )

    def _record_intent(
        self,
        *,
        transaction_id: str,
        staging_relative: str,
        final_relative: str,
        bundle_root_hash: str,
        created_at: str,
    ) -> str:
        intent_id = "intent.session." + hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO file_operation_intents(
                    intent_id, transaction_id, operation, staging_relative_path,
                    final_relative_path, expected_sha256, state, created_at
                ) VALUES (?, ?, 'session.import', ?, ?, ?, 'prepared', ?)
                """,
                (
                    intent_id,
                    transaction_id,
                    staging_relative,
                    final_relative,
                    bundle_root_hash,
                    created_at,
                ),
            )
        return intent_id

    def _promote_or_reuse(
        self,
        staging: Path,
        final: Path,
        expected_inventory: tuple[SessionFileRecord, ...],
        expected_root_hash: str,
    ) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        self._project_path(final.relative_to(self.root).as_posix())
        if final.exists():
            if not final.is_dir() or _is_link_or_junction(final):
                raise SessionImportPathError("managed revision target is not a regular directory")
            inventory = self._inventory(final)
            actual_root_hash = self._bundle_root_hash(
                self._manifest_hash(inventory),
                self._inventory_hash(inventory),
            )
            if inventory != expected_inventory or actual_root_hash != expected_root_hash:
                raise SessionImportIntegrityError(
                    "existing managed revision path conflicts with imported bytes"
                )
            self._remove_tree(staging, self.root / "staging" / "imports")
            return
        staging.replace(final)

    def _validate_intent(
        self,
        row: sqlite3.Row,
    ) -> tuple[str, str, Path, str, Path]:
        if row["state"] != "prepared":
            raise SessionImportIntegrityError("unsupported session import intent state")
        transaction_id = self._stable_id(str(row["transaction_id"]), "transaction_id")
        staging_relative = str(row["staging_relative_path"])
        final_relative = str(row["final_relative_path"])
        if staging_relative != f"staging/imports/{transaction_id}/bundle":
            raise SessionImportPathError("session import staging path is not canonical")
        parts = PurePosixPath(final_relative).parts
        if len(parts) != 4 or parts[0] != "sessions" or parts[3] != "bundle":
            raise SessionImportPathError("session import final path is not canonical")
        self._stable_id(parts[1], "session_id")
        self._stable_id(parts[2], "session_revision_id")
        expected_hash = str(row["expected_sha256"])
        if len(expected_hash) != 64 or any(
            character not in "0123456789abcdef" for character in expected_hash
        ):
            raise SessionImportIntegrityError("session import intent root hash is invalid")
        if parts[2] != f"session-revision.{expected_hash[:32]}":
            raise SessionImportPathError(
                "session import revision path does not match its root hash"
            )
        return (
            str(row["intent_id"]),
            staging_relative,
            self._project_path(staging_relative),
            final_relative,
            self._project_path(final_relative),
        )

    def _external_root(self, value: str | Path) -> Path:
        candidate = Path(value).expanduser()
        if _is_link_or_junction(candidate):
            raise SessionImportPathError("external bundle root cannot be a link or junction")
        try:
            root = candidate.resolve(strict=True)
        except OSError as error:
            raise SessionImportPathError("external bundle root does not exist") from error
        if not root.is_dir():
            raise SessionImportPathError("external bundle root must be a directory")
        if root.is_relative_to(self.root):
            raise SessionImportPathError("external bundle must be outside the managed project")
        return root

    def _project_path(self, relative: str) -> Path:
        try:
            validated = _RELATIVE_PATH.validate_python(relative)
        except ValidationError as error:
            raise SessionImportPathError(f"unsafe project-relative path: {error}") from error
        path = self.root.joinpath(*PurePosixPath(validated).parts)
        current = self.root
        for part in PurePosixPath(validated).parts:
            current /= part
            if current.exists() and _is_link_or_junction(current):
                raise SessionImportPathError("project path contains a link or junction")
        if not path.resolve(strict=False).is_relative_to(self.root):
            raise SessionImportPathError("project-relative path escapes the project root")
        return path

    def _inventory(self, root: Path) -> tuple[SessionFileRecord, ...]:
        paths = tuple(self._walk_regular_files(root))
        if len(paths) > self.limits.max_files:
            raise SessionImportIntegrityError("Session Bundle exceeds the file-count limit")
        records: list[SessionFileRecord] = []
        total_size = 0
        for path in paths:
            relative = path.relative_to(root).as_posix()
            try:
                _RELATIVE_PATH.validate_python(relative)
            except ValidationError as error:
                raise SessionImportPathError(
                    f"invalid bundle path {relative!r}: {error}"
                ) from error
            size = path.stat().st_size
            if size > self.limits.max_single_file_bytes:
                raise SessionImportIntegrityError(
                    f"Session Bundle file exceeds the size limit: {relative}"
                )
            total_size += size
            if total_size > self.limits.max_total_bytes:
                raise SessionImportIntegrityError("Session Bundle exceeds the total-size limit")
            digest, hashed_size = self._hash_file(path)
            if hashed_size != size:
                raise SessionImportIntegrityError(
                    f"Session Bundle file changed while hashing: {relative}"
                )
            records.append(
                SessionFileRecord(
                    relative_path=relative,
                    byte_size=size,
                    sha256=digest,
                )
            )
        return tuple(sorted(records, key=lambda item: item.relative_path))

    def _walk_regular_files(self, root: Path) -> Iterator[Path]:
        if _is_link_or_junction(root) or not root.is_dir():
            raise SessionImportPathError("Session Bundle root is not a regular directory")
        resolved_root = root.resolve()

        def walk(directory: Path) -> Iterator[Path]:
            try:
                with os.scandir(directory) as scanner:
                    entries = sorted(scanner, key=lambda entry: entry.name)
            except OSError as error:
                raise SessionImportPathError("cannot enumerate Session Bundle") from error
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink() or _is_link_or_junction(path):
                    raise SessionImportPathError(
                        f"Session Bundle contains a link, reparse point, or junction: {entry.name}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    yield from walk(path)
                elif entry.is_file(follow_symlinks=False):
                    if not path.resolve(strict=True).is_relative_to(resolved_root):
                        raise SessionImportPathError("Session Bundle file escapes its root")
                    yield path
                else:
                    raise SessionImportPathError(
                        f"Session Bundle contains a non-regular entry: {entry.name}"
                    )

        yield from walk(root)

    def _copy_inventory(
        self,
        source_root: Path,
        target_root: Path,
        inventory: tuple[SessionFileRecord, ...],
    ) -> None:
        for record in inventory:
            source = source_root.joinpath(*PurePosixPath(record.relative_path).parts)
            if _is_link_or_junction(source) or not source.is_file():
                raise SessionImportPathError(
                    f"Session Bundle source changed to a link or non-file: {record.relative_path}"
                )
            target = target_root.joinpath(*PurePosixPath(record.relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            byte_size = 0
            with source.open("rb") as input_stream, target.open("xb") as output_stream:
                while chunk := input_stream.read(_COPY_CHUNK_SIZE):
                    digest.update(chunk)
                    byte_size += len(chunk)
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            if digest.hexdigest() != record.sha256 or byte_size != record.byte_size:
                raise SessionImportIntegrityError(
                    f"Session Bundle source changed during copy: {record.relative_path}"
                )

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(_COPY_CHUNK_SIZE):
                digest.update(chunk)
                byte_size += len(chunk)
        return digest.hexdigest(), byte_size

    @staticmethod
    def _manifest_hash(inventory: tuple[SessionFileRecord, ...]) -> str:
        for item in inventory:
            if item.relative_path == "manifest.json":
                return item.sha256
        raise SessionImportIntegrityError("Session Bundle inventory has no manifest.json")

    @staticmethod
    def _inventory_hash(inventory: tuple[SessionFileRecord, ...]) -> str:
        return typed_content_sha256(
            "session-file-inventory",
            "0.1.0",
            [
                {
                    "relative_path": item.relative_path,
                    "byte_size": item.byte_size,
                    "sha256": item.sha256,
                }
                for item in inventory
            ],
        )

    @staticmethod
    def _bundle_root_hash(manifest_hash: str, inventory_hash: str) -> str:
        return typed_content_sha256(
            "managed-session-bundle-root",
            "0.1.0",
            {
                "manifest_hash": manifest_hash,
                "file_inventory_hash": inventory_hash,
            },
        )

    @staticmethod
    def _require_importable(report: IngestionReadinessReport) -> None:
        if not report.can_continue_to_synchronization:
            raise SessionImportBlockedError(
                "Session Bundle is technically blocked by current ingestion checks"
            )

    def _stored_inventory(self, revision_id: str) -> tuple[SessionFileRecord, ...]:
        rows = self.database.fetchall(
            """
            SELECT relative_path, byte_size, sha256 FROM session_files
            WHERE session_revision_id = ? ORDER BY relative_path
            """,
            (revision_id,),
        )
        return self._inventory_from_rows(rows)

    @staticmethod
    def _stored_inventory_in_transaction(
        connection: sqlite3.Connection,
        revision_id: str,
    ) -> tuple[SessionFileRecord, ...]:
        rows = connection.execute(
            """
            SELECT relative_path, byte_size, sha256 FROM session_files
            WHERE session_revision_id = ? ORDER BY relative_path
            """,
            (revision_id,),
        ).fetchall()
        return SessionImportService._inventory_from_rows(rows)

    @staticmethod
    def _inventory_from_rows(rows: list[sqlite3.Row]) -> tuple[SessionFileRecord, ...]:
        return tuple(
            SessionFileRecord(
                relative_path=row["relative_path"],
                byte_size=int(row["byte_size"]),
                sha256=row["sha256"],
            )
            for row in rows
        )

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            project_id=row["project_id"],
            participant_id=row["participant_id"],
            lifecycle=row["lifecycle"],
            current_session_revision_id=row["current_session_revision_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> SessionRevision:
        try:
            decoded = decode_canonical_json(row["canonical_json"])
            revision = SessionRevision.model_validate(decoded)
        except (ValueError, ValidationError) as error:
            raise SessionImportIntegrityError("stored session revision JSON is invalid") from error
        indexed = (
            row["session_revision_id"],
            row["session_id"],
            row["managed_bundle_path"],
            row["manifest_hash"],
            row["bundle_root_hash"],
            row["file_inventory_hash"],
            row["source_kind"],
            row["imported_by"],
            row["ingestion_readiness_ref"],
            row["synchronization_ref"],
        )
        canonical = (
            revision.session_revision_id,
            revision.session_id,
            revision.managed_bundle_path,
            revision.manifest_hash,
            revision.bundle_root_hash,
            revision.file_inventory_hash,
            revision.source_kind.value,
            revision.imported_by,
            revision.ingestion_readiness_ref,
            revision.synchronization_ref,
        )
        if indexed != canonical:
            raise SessionImportIntegrityError("session revision index and canonical JSON disagree")
        return revision

    def _remove_tree(self, path: Path, allowed_root: Path) -> None:
        if _is_link_or_junction(path):
            raise SessionImportPathError("refusing to remove a linked managed tree")
        resolved_root = allowed_root.resolve()
        if not path.resolve(strict=False).is_relative_to(resolved_root):
            raise SessionImportPathError("refusing to remove a tree outside its managed root")
        if path.is_file():
            path.unlink()
            return
        if not path.is_dir():
            raise SessionImportPathError("managed recovery target is not a regular tree")
        for child in tuple(path.iterdir()):
            self._remove_tree(child, allowed_root)
        path.rmdir()

    @staticmethod
    def _prune_empty_parents(start: Path, stop: Path) -> None:
        current = start
        while current != stop and stop in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    @staticmethod
    def _stable_id(value: str, label: str) -> str:
        try:
            return _STABLE_ID.validate_python(value)
        except ValidationError as error:
            raise SessionImportError(f"invalid {label}: {error}") from error


__all__ = [
    "ManagedSessionChangedError",
    "SessionFileRecord",
    "SessionIdentityConflictError",
    "SessionImportBlockedError",
    "SessionImportError",
    "SessionImportIntegrityError",
    "SessionImportLimits",
    "SessionImportPathError",
    "SessionImportResult",
    "SessionImportService",
    "SessionNotFoundError",
    "SessionRecoveryReport",
    "SessionRevisionNotFoundError",
]
