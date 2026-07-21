"""Explicit SQLite schema migrations for a self-contained assessment project."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

LATEST_SCHEMA_VERSION = 6

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
    Migration(
        version=2,
        name="m7_current_model_workspace_v2",
        statements=(
            """
            CREATE TABLE model_change_events (
                event_id TEXT PRIMARY KEY,
                object_kind TEXT NOT NULL CHECK (object_kind IN ('node', 'scheme')),
                object_id TEXT NOT NULL,
                event_kind TEXT NOT NULL CHECK (
                    event_kind IN ('create', 'update', 'archive', 'undo', 'redo', 'migrate')
                ),
                parent_event_id TEXT,
                semantic_revision INTEGER NOT NULL CHECK (semantic_revision >= 0),
                layout_revision INTEGER NOT NULL CHECK (layout_revision >= 0),
                before_hash TEXT,
                after_hash TEXT,
                before_json BLOB,
                after_json BLOB,
                diff_json BLOB NOT NULL,
                transaction_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (parent_event_id)
                    REFERENCES model_change_events(event_id) ON DELETE RESTRICT
            )
            """,
            (
                "CREATE INDEX model_change_events_object_idx "
                "ON model_change_events(object_kind, object_id, occurred_at, event_id)"
            ),
            (
                "CREATE INDEX model_change_events_transaction_idx "
                "ON model_change_events(transaction_id)"
            ),
            """
            CREATE TRIGGER model_change_events_append_only_update
            BEFORE UPDATE ON model_change_events
            BEGIN
                SELECT RAISE(ABORT, 'model_change_events is append-only');
            END
            """,
            """
            CREATE TRIGGER model_change_events_append_only_delete
            BEFORE DELETE ON model_change_events
            BEGIN
                SELECT RAISE(ABORT, 'model_change_events is append-only');
            END
            """,
            """
            CREATE TABLE model_nodes (
                node_id TEXT PRIMARY KEY,
                canonical_json BLOB NOT NULL,
                lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'archived')),
                semantic_revision INTEGER NOT NULL CHECK (semantic_revision >= 0),
                layout_revision INTEGER NOT NULL CHECK (layout_revision >= 0),
                content_hash TEXT NOT NULL,
                layout_hash TEXT NOT NULL,
                technical_status TEXT NOT NULL CHECK (
                    technical_status IN ('executable', 'incomplete', 'blocked')
                ),
                head_event_id TEXT,
                redo_event_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (head_event_id)
                    REFERENCES model_change_events(event_id) ON DELETE RESTRICT,
                FOREIGN KEY (redo_event_id)
                    REFERENCES model_change_events(event_id) ON DELETE RESTRICT
            )
            """,
            "CREATE INDEX model_nodes_lifecycle_idx ON model_nodes(lifecycle, node_id)",
            ("CREATE INDEX model_nodes_status_idx ON model_nodes(technical_status, node_id)"),
            """
            CREATE TABLE task_schemes (
                scheme_id TEXT PRIMARY KEY,
                canonical_json BLOB NOT NULL,
                lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'archived')),
                semantic_revision INTEGER NOT NULL CHECK (semantic_revision >= 0),
                layout_revision INTEGER NOT NULL CHECK (layout_revision >= 0),
                content_hash TEXT NOT NULL,
                layout_hash TEXT NOT NULL,
                technical_status TEXT NOT NULL CHECK (
                    technical_status IN ('executable', 'incomplete', 'blocked')
                ),
                head_event_id TEXT,
                redo_event_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (head_event_id)
                    REFERENCES model_change_events(event_id) ON DELETE RESTRICT,
                FOREIGN KEY (redo_event_id)
                    REFERENCES model_change_events(event_id) ON DELETE RESTRICT
            )
            """,
            "CREATE INDEX task_schemes_lifecycle_idx ON task_schemes(lifecycle, scheme_id)",
            ("CREATE INDEX task_schemes_status_idx ON task_schemes(technical_status, scheme_id)"),
            """
            CREATE TABLE model_starter_mappings (
                mapping_id TEXT PRIMARY KEY,
                legacy_kind TEXT NOT NULL,
                legacy_record_id TEXT NOT NULL,
                current_object_kind TEXT NOT NULL CHECK (
                    current_object_kind IN ('node', 'scheme')
                ),
                current_object_id TEXT NOT NULL,
                seed_id TEXT NOT NULL,
                seed_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (legacy_kind, legacy_record_id, seed_id),
                UNIQUE (current_object_kind, current_object_id, seed_id)
            )
            """,
            (
                "CREATE INDEX model_starter_mappings_current_idx "
                "ON model_starter_mappings(current_object_kind, current_object_id)"
            ),
            """
            CREATE TABLE model_execution_materializations (
                graph_hash TEXT PRIMARY KEY,
                scheme_id TEXT NOT NULL,
                scheme_semantic_revision INTEGER NOT NULL CHECK (
                    scheme_semantic_revision >= 0
                ),
                scheme_content_hash TEXT NOT NULL,
                legacy_scheme_version_id TEXT NOT NULL,
                legacy_scheme_content_hash TEXT NOT NULL,
                materialization_json BLOB NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scheme_id) REFERENCES task_schemes(scheme_id) ON DELETE RESTRICT
            )
            """,
            (
                "CREATE INDEX model_execution_materializations_scheme_idx "
                "ON model_execution_materializations(scheme_id, scheme_semantic_revision)"
            ),
            """
            CREATE TABLE model_run_preflights (
                current_preflight_id TEXT PRIMARY KEY,
                current_preflight_hash TEXT NOT NULL UNIQUE,
                scheme_id TEXT NOT NULL,
                scheme_semantic_revision INTEGER NOT NULL CHECK (
                    scheme_semantic_revision >= 0
                ),
                scheme_content_hash TEXT NOT NULL,
                report_json BLOB NOT NULL,
                legacy_preflight_id TEXT NOT NULL,
                legacy_preflight_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scheme_id) REFERENCES task_schemes(scheme_id) ON DELETE RESTRICT,
                FOREIGN KEY (legacy_preflight_id)
                    REFERENCES run_preflights(preflight_id) ON DELETE RESTRICT
            )
            """,
            (
                "CREATE INDEX model_run_preflights_scheme_idx "
                "ON model_run_preflights(scheme_id, scheme_semantic_revision)"
            ),
            """
            CREATE TABLE model_run_links (
                run_id TEXT PRIMARY KEY,
                current_preflight_id TEXT NOT NULL,
                current_snapshot_hash TEXT NOT NULL UNIQUE,
                current_snapshot_json BLOB NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE RESTRICT,
                FOREIGN KEY (current_preflight_id)
                    REFERENCES model_run_preflights(current_preflight_id) ON DELETE RESTRICT
            )
            """,
            ("CREATE INDEX model_run_links_preflight_idx ON model_run_links(current_preflight_id)"),
        ),
    ),
    Migration(
        version=3,
        name="m7_starter_mapping_relation_v3",
        statements=(
            "DROP INDEX model_starter_mappings_current_idx",
            "ALTER TABLE model_starter_mappings RENAME TO model_starter_mappings_v2",
            """
            CREATE TABLE model_starter_mappings (
                mapping_id TEXT PRIMARY KEY,
                legacy_kind TEXT NOT NULL,
                legacy_record_id TEXT NOT NULL,
                current_object_kind TEXT NOT NULL CHECK (
                    current_object_kind IN ('node', 'scheme')
                ),
                current_object_id TEXT NOT NULL,
                seed_id TEXT NOT NULL,
                seed_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (
                    legacy_kind, legacy_record_id,
                    current_object_kind, current_object_id,
                    seed_id
                )
            )
            """,
            """
            INSERT INTO model_starter_mappings(
                mapping_id, legacy_kind, legacy_record_id,
                current_object_kind, current_object_id,
                seed_id, seed_hash, created_at
            )
            SELECT mapping_id, legacy_kind, legacy_record_id,
                   current_object_kind, current_object_id,
                   seed_id, seed_hash, created_at
            FROM model_starter_mappings_v2
            """,
            "DROP TABLE model_starter_mappings_v2",
            (
                "CREATE INDEX model_starter_mappings_current_idx "
                "ON model_starter_mappings(current_object_kind, current_object_id)"
            ),
        ),
    ),
    Migration(
        version=4,
        name="m8b_system_model_project_snapshots_v4",
        statements=(
            """
            CREATE TABLE model_execution_materializations_v2 (
                graph_hash TEXT PRIMARY KEY,
                scheme_id TEXT NOT NULL,
                scheme_semantic_revision INTEGER NOT NULL CHECK (
                    scheme_semantic_revision >= 0
                ),
                scheme_content_hash TEXT NOT NULL,
                legacy_scheme_version_id TEXT NOT NULL,
                legacy_scheme_content_hash TEXT NOT NULL,
                materialization_json BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            (
                "CREATE INDEX model_execution_materializations_v2_scheme_idx "
                "ON model_execution_materializations_v2(scheme_id, scheme_semantic_revision)"
            ),
            """
            CREATE TABLE model_run_preflights_v2 (
                current_preflight_id TEXT PRIMARY KEY,
                current_preflight_hash TEXT NOT NULL UNIQUE,
                scheme_id TEXT NOT NULL,
                scheme_semantic_revision INTEGER NOT NULL CHECK (
                    scheme_semantic_revision >= 0
                ),
                scheme_content_hash TEXT NOT NULL,
                report_json BLOB NOT NULL,
                legacy_preflight_id TEXT NOT NULL,
                legacy_preflight_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (legacy_preflight_id)
                    REFERENCES run_preflights(preflight_id) ON DELETE RESTRICT
            )
            """,
            (
                "CREATE INDEX model_run_preflights_v2_scheme_idx "
                "ON model_run_preflights_v2(scheme_id, scheme_semantic_revision)"
            ),
            """
            CREATE TABLE model_run_links_v2 (
                run_id TEXT PRIMARY KEY,
                current_preflight_id TEXT NOT NULL,
                current_snapshot_hash TEXT NOT NULL UNIQUE,
                current_snapshot_json BLOB NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE RESTRICT,
                FOREIGN KEY (current_preflight_id)
                    REFERENCES model_run_preflights_v2(current_preflight_id) ON DELETE RESTRICT
            )
            """,
            (
                "CREATE INDEX model_run_links_v2_preflight_idx "
                "ON model_run_links_v2(current_preflight_id)"
            ),
        ),
    ),
    Migration(
        version=5,
        name="m8b_legacy_system_model_import_receipts_v5",
        statements=(
            """
            CREATE TABLE legacy_system_model_import_receipts (
                import_fingerprint TEXT PRIMARY KEY,
                source_project_id TEXT NOT NULL,
                canonical_fingerprint TEXT NOT NULL,
                legacy_edit_fingerprint TEXT,
                node_mapping_json BLOB NOT NULL,
                scheme_mapping_json BLOB NOT NULL,
                inserted_node_count INTEGER NOT NULL CHECK (inserted_node_count >= 0),
                inserted_scheme_count INTEGER NOT NULL CHECK (inserted_scheme_count >= 0),
                reused_node_count INTEGER NOT NULL CHECK (reused_node_count >= 0),
                reused_scheme_count INTEGER NOT NULL CHECK (reused_scheme_count >= 0),
                dirty_edit_recovered INTEGER NOT NULL CHECK (dirty_edit_recovered IN (0, 1)),
                imported_at TEXT NOT NULL
            )
            """,
            (
                "CREATE INDEX legacy_system_model_import_receipts_project_idx "
                "ON legacy_system_model_import_receipts(source_project_id, imported_at)"
            ),
        ),
    ),
    Migration(
        version=6,
        name="m8e_single_english_model_content_lineage_v6",
        statements=(
            """
            CREATE TABLE model_content_migration_events (
                migration_event_id TEXT PRIMARY KEY,
                object_kind TEXT NOT NULL CHECK (object_kind IN ('node', 'scheme')),
                object_id TEXT NOT NULL,
                from_contract_version TEXT NOT NULL,
                to_contract_version TEXT NOT NULL,
                old_content_hash TEXT NOT NULL,
                new_content_hash TEXT NOT NULL,
                old_layout_hash TEXT NOT NULL,
                new_layout_hash TEXT NOT NULL,
                before_workspace_fingerprint TEXT NOT NULL,
                after_workspace_fingerprint TEXT NOT NULL,
                legacy_payload BLOB NOT NULL,
                diagnostics_json BLOB NOT NULL,
                migrated_at TEXT NOT NULL,
                UNIQUE (
                    object_kind, object_id, from_contract_version, to_contract_version,
                    old_content_hash, new_content_hash, old_layout_hash, new_layout_hash
                )
            )
            """,
            (
                "CREATE INDEX model_content_migration_events_object_idx "
                "ON model_content_migration_events(object_kind, object_id, migrated_at)"
            ),
            """
            CREATE TRIGGER model_content_migration_events_append_only_update
            BEFORE UPDATE ON model_content_migration_events
            BEGIN
                SELECT RAISE(ABORT, 'model_content_migration_events is append-only');
            END
            """,
            """
            CREATE TRIGGER model_content_migration_events_append_only_delete
            BEFORE DELETE ON model_content_migration_events
            BEGIN
                SELECT RAISE(ABORT, 'model_content_migration_events is append-only');
            END
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
