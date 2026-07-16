from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pilot_assessment.persistence.database import (
    DatabaseTransactionError,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_database_applies_v1_migration_and_required_pragmas(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    try:
        assert database.fetchone("PRAGMA foreign_keys")[0] == 1
        assert database.fetchone("PRAGMA journal_mode")[0] == "wal"
        assert database.fetchone("PRAGMA synchronous")[0] == 2
        versions = database.fetchall("SELECT version FROM schema_migrations")
        assert [row["version"] for row in versions] == [1]

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
        }.issubset(tables)
    finally:
        database.close()


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
