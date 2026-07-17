from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from pilot_assessment.persistence.database import (
    DatabaseTransactionError,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.migrations import MIGRATIONS

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_database_applies_v1_then_v2_migrations_and_required_pragmas(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    try:
        assert database.fetchone("PRAGMA foreign_keys")[0] == 1
        assert database.fetchone("PRAGMA journal_mode")[0] == "wal"
        assert database.fetchone("PRAGMA synchronous")[0] == 2
        versions = database.fetchall("SELECT version FROM schema_migrations")
        assert [row["version"] for row in versions] == [1, 2]

        tables = {
            row["name"]
            for row in database.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "project_metadata",
            "library_records",
            "scheme_drafts",
            "sessions",
            "session_revisions",
            "managed_artifacts",
            "idempotency_transactions",
            "run_preflights",
            "runs",
            "run_events",
            "run_results",
            "audit_events",
            "model_nodes",
            "task_schemes",
            "model_change_events",
            "model_starter_mappings",
            "model_execution_materializations",
            "model_run_preflights",
            "model_run_links",
        }.issubset(tables)
    finally:
        database.close()


def test_existing_v1_database_upgrades_once_without_changing_legacy_rows(tmp_path) -> None:
    path = tmp_path / "project.sqlite3"
    raw = sqlite3.connect(path)
    try:
        raw.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )
        migration_v1 = MIGRATIONS[0]
        assert migration_v1.version == 1
        for statement in migration_v1.statements:
            raw.execute(statement)
        raw.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (1, ?, ?)",
            (migration_v1.name, "2026-07-16T12:00:00Z"),
        )
        legacy_row = (
            "source_descriptor",
            "source.legacy",
            None,
            "active",
            b'{"legacy":true}',
            None,
            "2026-07-16T12:00:00Z",
            None,
            None,
            None,
        )
        raw.execute(
            """
            INSERT INTO library_records(
                kind, record_id, concept_id, lifecycle, canonical_json,
                content_hash, created_at, changed_at, changed_by, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            legacy_row,
        )
        raw.commit()
    finally:
        raw.close()

    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        assert [
            row["version"]
            for row in database.fetchall("SELECT version FROM schema_migrations ORDER BY version")
        ] == [1, 2]
        assert (
            tuple(
                database.fetchone(
                    """
                SELECT kind, record_id, concept_id, lifecycle, canonical_json,
                       content_hash, created_at, changed_at, changed_by, reason
                FROM library_records WHERE record_id = 'source.legacy'
                """
                )
            )
            == legacy_row
        )
    finally:
        database.close()

    reopened = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        assert reopened.fetchone("SELECT COUNT(*) FROM schema_migrations WHERE version = 2")[0] == 1
    finally:
        reopened.close()


def test_canonical_json_codec_rejects_noncanonical_or_non_json_payloads() -> None:
    payload = encode_canonical_json({"z": 1, "a": [True, "飞行员"]})

    assert payload == '{"a":[true,"飞行员"],"z":1}'.encode()
    assert decode_canonical_json(payload) == {"a": [True, "飞行员"], "z": 1}
    with pytest.raises(ValueError, match="canonical"):
        decode_canonical_json(b'{"z":1,"a":2}')
    with pytest.raises(ValueError, match="UTF-8 JSON"):
        decode_canonical_json(b"not-json")


def test_explicit_transactions_commit_rollback_and_reject_nesting(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    database.execute("CREATE TABLE transaction_probe (value TEXT NOT NULL)")
    try:
        with database.transaction() as connection:
            connection.execute("INSERT INTO transaction_probe(value) VALUES (?)", ("committed",))

        with pytest.raises(RuntimeError, match="rollback"), database.transaction() as connection:
            connection.execute("INSERT INTO transaction_probe(value) VALUES (?)", ("rolled-back",))
            raise RuntimeError("rollback")

        with (
            pytest.raises(DatabaseTransactionError, match="nested"),
            database.transaction() as connection,
        ):
            connection.execute("INSERT INTO transaction_probe(value) VALUES (?)", ("nested",))
            with database.transaction():
                pass

        values = database.fetchall("SELECT value FROM transaction_probe")
        assert [row["value"] for row in values] == ["committed"]
    finally:
        database.close()
