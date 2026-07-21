from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.migrations import LATEST_SCHEMA_VERSION

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_v6_adds_append_only_model_content_migration_lineage(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "workspace.sqlite3", clock=lambda: NOW)
    try:
        assert LATEST_SCHEMA_VERSION == 6
        version = database.fetchone("SELECT MAX(version) AS version FROM schema_migrations")
        assert version is not None and version["version"] == 6
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO model_content_migration_events(
                    migration_event_id, object_kind, object_id,
                    from_contract_version, to_contract_version,
                    old_content_hash, new_content_hash, old_layout_hash, new_layout_hash,
                    before_workspace_fingerprint, after_workspace_fingerprint,
                    legacy_payload, diagnostics_json, migrated_at
                ) VALUES (?, 'node', 'node.one', '0.1.0', '0.2.0', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "model-content-migration.one",
                    "a" * 64,
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                    "f" * 64,
                    b"{}",
                    b"[]",
                    "2026-07-21T12:00:00Z",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute("UPDATE model_content_migration_events SET object_id = 'node.two'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute("DELETE FROM model_content_migration_events")
    finally:
        database.close()
