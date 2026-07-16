"""Explicit SQLite schema migrations for a self-contained assessment project."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

LATEST_SCHEMA_VERSION = 1

_BOOTSTRAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        version=1,
        name="m6_project_runtime_v1",
        statements=(
            """
            CREATE TABLE project_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                project_id TEXT NOT NULL UNIQUE,
                format_version TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                clean_shutdown INTEGER NOT NULL CHECK (clean_shutdown IN (0, 1)),
                last_opened_at TEXT NOT NULL,
                last_closed_at TEXT
            )
            """,
            """
            CREATE TABLE library_records (
                kind TEXT NOT NULL,
                record_id TEXT NOT NULL,
                concept_id TEXT,
                lifecycle TEXT NOT NULL,
                canonical_json BLOB NOT NULL,
                content_hash TEXT,
                created_at TEXT NOT NULL,
                changed_at TEXT,
                changed_by TEXT,
                reason TEXT,
                PRIMARY KEY (kind, record_id)
            )
            """,
            "CREATE INDEX library_records_concept_idx ON library_records(kind, concept_id)",
            "CREATE INDEX library_records_lifecycle_idx ON library_records(lifecycle)",
            """
            CREATE TABLE library_tags (
                kind TEXT NOT NULL,
                record_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (kind, record_id, tag),
                FOREIGN KEY (kind, record_id)
                    REFERENCES library_records(kind, record_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE library_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                record_id TEXT NOT NULL,
                lifecycle TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                FOREIGN KEY (kind, record_id)
                    REFERENCES library_records(kind, record_id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE scheme_drafts (
                draft_id TEXT PRIMARY KEY,
                canonical_json BLOB NOT NULL,
                graph_version INTEGER NOT NULL CHECK (graph_version >= 0),
                layout_version INTEGER NOT NULL CHECK (layout_version >= 0),
                history_cursor INTEGER NOT NULL CHECK (history_cursor >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                last_diff_json BLOB
            )
            """,
            """
            CREATE TABLE draft_snapshots (
                draft_id TEXT NOT NULL,
                snapshot_index INTEGER NOT NULL CHECK (snapshot_index >= 0),
                canonical_json BLOB NOT NULL,
                PRIMARY KEY (draft_id, snapshot_index),
                FOREIGN KEY (draft_id) REFERENCES scheme_drafts(draft_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE draft_transitions (
                draft_id TEXT NOT NULL,
                transition_index INTEGER NOT NULL CHECK (transition_index >= 0),
                diff_json BLOB NOT NULL,
                graph_changed INTEGER NOT NULL CHECK (graph_changed IN (0, 1)),
                layout_changed INTEGER NOT NULL CHECK (layout_changed IN (0, 1)),
                author_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (draft_id, transition_index),
                FOREIGN KEY (draft_id) REFERENCES scheme_drafts(draft_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                lifecycle TEXT NOT NULL,
                current_session_revision_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (current_session_revision_id)
                    REFERENCES session_revisions(session_revision_id)
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            """
            CREATE TABLE session_revisions (
                session_revision_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                managed_bundle_path TEXT NOT NULL UNIQUE,
                manifest_hash TEXT NOT NULL,
                bundle_root_hash TEXT NOT NULL,
                file_inventory_hash TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                imported_by TEXT NOT NULL,
                ingestion_readiness_ref TEXT NOT NULL,
                synchronization_ref TEXT,
                canonical_json BLOB NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            (
                "CREATE INDEX session_revisions_session_idx "
                "ON session_revisions(session_id, imported_at)"
            ),
            """
            CREATE TABLE session_files (
                session_revision_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                sha256 TEXT NOT NULL,
                PRIMARY KEY (session_revision_id, relative_path),
                FOREIGN KEY (session_revision_id)
                    REFERENCES session_revisions(session_revision_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE managed_artifacts (
                artifact_id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                media_type TEXT NOT NULL,
                schema_id TEXT,
                managed_relative_path TEXT NOT NULL UNIQUE,
                lifecycle TEXT NOT NULL,
                created_at TEXT NOT NULL,
                canonical_json BLOB NOT NULL
            )
            """,
            """
            CREATE TABLE artifact_references (
                owner_kind TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                role TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                PRIMARY KEY (owner_kind, owner_id, role),
                FOREIGN KEY (artifact_id)
                    REFERENCES managed_artifacts(artifact_id) ON DELETE RESTRICT
            )
            """,
            "CREATE INDEX artifact_references_artifact_idx ON artifact_references(artifact_id)",
            """
            CREATE TABLE file_operation_intents (
                intent_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                staging_relative_path TEXT NOT NULL,
                final_relative_path TEXT NOT NULL,
                expected_sha256 TEXT,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE idempotency_transactions (
                transaction_id TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                response_json BLOB,
                audit_event_id TEXT,
                completed_at TEXT
            )
            """,
            """
            CREATE TABLE run_preflights (
                preflight_id TEXT PRIMARY KEY,
                preflight_hash TEXT NOT NULL UNIQUE,
                report_json BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                preflight_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL UNIQUE,
                snapshot_json BLOB NOT NULL,
                state TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress_sequence INTEGER NOT NULL CHECK (progress_sequence >= 0),
                requested_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                cancellation_requested_at TEXT,
                FOREIGN KEY (preflight_id)
                    REFERENCES run_preflights(preflight_id) ON DELETE RESTRICT
            )
            """,
            "CREATE INDEX runs_state_idx ON runs(state, requested_at)",
            """
            CREATE TABLE run_events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                event_id TEXT NOT NULL UNIQUE,
                event_json BLOB NOT NULL,
                occurred_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE run_results (
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                result_hash TEXT NOT NULL UNIQUE,
                envelope_json BLOB NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE audit_events (
                audit_event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                transaction_id TEXT,
                details_json BLOB NOT NULL
            )
            """,
            (
                "CREATE INDEX audit_events_subject_idx "
                "ON audit_events(subject_kind, subject_id, occurred_at)"
            ),
            "CREATE INDEX audit_events_transaction_idx ON audit_events(transaction_id)",
            """
            CREATE TABLE project_seed_markers (
                seed_id TEXT PRIMARY KEY,
                seed_hash TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


class MigrationError(RuntimeError):
    """Raised when the on-disk schema cannot be brought to the supported version."""


def apply_migrations(connection: sqlite3.Connection, *, applied_at: str) -> None:
    """Apply each missing migration atomically and reject unknown future schemas."""

    connection.execute(_BOOTSTRAP_SCHEMA)
    rows = connection.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall()
    applied = {int(row[0]): str(row[1]) for row in rows}
    if any(version > LATEST_SCHEMA_VERSION for version in applied):
        raise MigrationError("project database schema is newer than this runtime")
    expected_prefix = tuple(range(1, max(applied, default=0) + 1))
    if tuple(sorted(applied)) != expected_prefix:
        raise MigrationError("project database migration history is not contiguous")

    by_version = {migration.version: migration for migration in MIGRATIONS}
    for version, name in applied.items():
        expected = by_version.get(version)
        if expected is None or expected.name != name:
            raise MigrationError(f"migration identity mismatch at version {version}")

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, applied_at),
            )
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()


__all__ = ["LATEST_SCHEMA_VERSION", "MIGRATIONS", "Migration", "MigrationError", "apply_migrations"]
