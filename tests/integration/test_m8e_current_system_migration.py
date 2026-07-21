from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.model_workspace_legacy import (
    LegacyModelNodeV010,
    LegacyTaskSchemeV010,
)
from pilot_assessment.model_workspace.content_migration import model_content_fingerprint
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.runtime import SystemApplication

NOW = datetime(2026, 7, 21, 18, 30, tzinfo=UTC)
RELEASE_TOOLS = Path(__file__).resolve().parents[2] / "tools" / "release"
sys.path.insert(0, str(RELEASE_TOOLS))


def _capture_api():
    from system_model_capture import inspect_system_source

    return inspect_system_source


def _legacy_payload(payload: dict[str, object], *, object_id: str) -> dict[str, object]:
    legacy = deepcopy(payload)
    legacy["contract_version"] = "0.1.0"
    legacy["name_en"] = legacy.pop("name")
    legacy["name_zh"] = None
    if legacy["contract_id"] == "model-node":
        legacy["short_name_en"] = legacy.pop("short_name")
        legacy["short_name_zh"] = None
        definition = dict(legacy["definition"])
        definition["help_text_en"] = definition.pop("help_text")
        definition["help_text_zh"] = None
        legacy["definition"] = definition
    legacy["description_en"] = legacy.pop("description")
    legacy["description_zh"] = None
    semantic_payload = encode_canonical_json(
        {key: value for key, value in legacy.items() if key not in {"content_hash", "layout_hash"}}
    )
    legacy["content_hash"] = hashlib.sha256(
        b"m8e-legacy-content\0" + object_id.encode("utf-8") + semantic_payload
    ).hexdigest()
    legacy["layout_hash"] = hashlib.sha256(
        b"m8e-legacy-layout\0" + object_id.encode("utf-8") + semantic_payload
    ).hexdigest()
    return legacy


def _downgrade_current_tables(database: ProjectDatabase) -> tuple[str, str]:
    nodes: list[LegacyModelNodeV010] = []
    schemes: list[LegacyTaskSchemeV010] = []
    for table, id_column, model, target in (
        ("model_nodes", "node_id", LegacyModelNodeV010, nodes),
        ("task_schemes", "scheme_id", LegacyTaskSchemeV010, schemes),
    ):
        for row in database.fetchall(f"SELECT * FROM {table} ORDER BY {id_column}"):
            decoded = decode_canonical_json(row["canonical_json"])
            assert isinstance(decoded, dict)
            object_id = row[id_column]
            legacy = _legacy_payload(decoded, object_id=object_id)
            target.append(model.model_validate(legacy))
            database.execute(
                f"""
                UPDATE {table}
                SET canonical_json = ?, content_hash = ?, layout_hash = ?
                WHERE {id_column} = ?
                """,  # noqa: S608 - closed test-only identifiers
                (
                    encode_canonical_json(legacy),
                    legacy["content_hash"],
                    legacy["layout_hash"],
                    object_id,
                ),
            )
    return (
        model_content_fingerprint(tuple(nodes), tuple(schemes), include_revisions=True),
        model_content_fingerprint(tuple(nodes), tuple(schemes), include_revisions=False),
    )


def _snapshot_bytes(value: object) -> bytes:
    assert isinstance(value, dict) and set(value) == {"$bytes"}
    encoded = value["$bytes"]
    assert isinstance(encoded, str)
    return base64.b64decode(encoded, validate=True)


def _downgrade_edit_snapshots(database: ProjectDatabase) -> dict[int, tuple[str, str]]:
    fingerprints: dict[int, tuple[str, str]] = {}
    for snapshot in database.fetchall(
        "SELECT * FROM model_edit_session_snapshots ORDER BY sequence"
    ):
        state = decode_canonical_json(snapshot["state_json"])
        assert isinstance(state, dict)
        nodes: list[LegacyModelNodeV010] = []
        schemes: list[LegacyTaskSchemeV010] = []
        for table, id_column, model, target in (
            ("model_nodes", "node_id", LegacyModelNodeV010, nodes),
            ("task_schemes", "scheme_id", LegacyTaskSchemeV010, schemes),
        ):
            rows = state[table]
            assert isinstance(rows, list)
            for row in rows:
                assert isinstance(row, dict)
                decoded = decode_canonical_json(_snapshot_bytes(row["canonical_json"]))
                assert isinstance(decoded, dict)
                object_id = row[id_column]
                assert isinstance(object_id, str)
                legacy = _legacy_payload(decoded, object_id=object_id)
                row["canonical_json"] = {
                    "$bytes": base64.b64encode(encode_canonical_json(legacy)).decode("ascii")
                }
                row["content_hash"] = legacy["content_hash"]
                row["layout_hash"] = legacy["layout_hash"]
                target.append(model.model_validate(legacy))
        state_json = encode_canonical_json(state)
        sequence = int(snapshot["sequence"])
        database.execute(
            """
            UPDATE model_edit_session_snapshots
            SET state_json = ?, state_hash = ?
            WHERE sequence = ?
            """,
            (state_json, hashlib.sha256(state_json).hexdigest(), sequence),
        )
        fingerprints[sequence] = (
            model_content_fingerprint(tuple(nodes), tuple(schemes), include_revisions=True),
            model_content_fingerprint(tuple(nodes), tuple(schemes), include_revisions=False),
        )
    return fingerprints


def _downgrade_complete_clean_system(root: Path) -> None:
    canonical = ProjectDatabase.connect(root / "model-library.sqlite3", clock=lambda: NOW)
    staging = ProjectDatabase.connect(
        root / "staging" / "model-edit" / "workspace.sqlite3",
        clock=lambda: NOW,
    )
    try:
        legacy_base_fingerprint, _ = _downgrade_current_tables(canonical)
        _downgrade_current_tables(staging)
        snapshot_fingerprints = _downgrade_edit_snapshots(staging)
        staging.execute(
            """
            UPDATE model_edit_session_state
            SET base_fingerprint = ?, baseline_state_hash = ?
            WHERE singleton = 1
            """,
            (legacy_base_fingerprint, snapshot_fingerprints[0][1]),
        )
    finally:
        staging.close()
        canonical.close()


def _rows(root: Path, table: str, id_column: str) -> dict[str, dict[str, object]]:
    connection = sqlite3.connect(root / "model-library.sqlite3")
    try:
        return {
            str(object_id): json.loads(canonical_json)
            for object_id, canonical_json in connection.execute(
                f"SELECT {id_column}, canonical_json FROM {table} ORDER BY {id_column}"
            )
        }
    finally:
        connection.close()


def _run_rows(root: Path) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(root / "model-library.sqlite3")
    try:
        return tuple(connection.execute("SELECT * FROM runs ORDER BY run_id"))
    finally:
        connection.close()


def _migration_rows(root: Path) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(root / "model-library.sqlite3")
    try:
        return tuple(
            connection.execute(
                """
                SELECT object_kind, object_id, from_contract_version,
                       to_contract_version, diagnostics_json
                FROM model_content_migration_events
                ORDER BY object_kind, object_id
                """
            )
        )
    finally:
        connection.close()


def _legacy_lineage(root: Path) -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    str,
]:
    connection = sqlite3.connect(root / "model-library.sqlite3")
    try:
        rows = tuple(
            connection.execute(
                """
                SELECT object_kind, object_id, legacy_payload,
                       old_content_hash, old_layout_hash
                FROM model_content_migration_events
                ORDER BY object_kind, object_id
                """
            )
        )
    finally:
        connection.close()
    nodes: dict[str, dict[str, object]] = {}
    schemes: dict[str, dict[str, object]] = {}
    by_kind = {"node": nodes, "scheme": schemes}
    digest = hashlib.sha256()
    for kind in ("node", "scheme"):
        for row_kind, object_id, legacy_payload, content_hash, layout_hash in rows:
            if row_kind != kind:
                continue
            by_kind[kind][str(object_id)] = json.loads(legacy_payload)
            digest.update(kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(str(object_id).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(content_hash).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(layout_hash).encode("ascii"))
            digest.update(b"\n")
    return nodes, schemes, digest.hexdigest()


def _file_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _structure(payload: dict[str, object]) -> dict[str, object]:
    projected = deepcopy(payload)
    for key in (
        "contract_version",
        "name",
        "name_en",
        "name_zh",
        "short_name",
        "short_name_en",
        "short_name_zh",
        "description",
        "description_en",
        "description_zh",
        "content_hash",
        "layout_hash",
    ):
        projected.pop(key, None)
    definition = projected.get("definition")
    if isinstance(definition, dict):
        for key in ("help_text", "help_text_en", "help_text_zh"):
            definition.pop(key, None)
    return projected


def _assert_single_english_equivalent(
    legacy: dict[str, dict[str, object]],
    current: dict[str, dict[str, object]],
) -> None:
    assert current.keys() == legacy.keys()
    for object_id, old in legacy.items():
        new = current[object_id]
        assert new["contract_version"] == "0.2.0"
        assert new["name"] == old["name_en"]
        assert new["description"] == old["description_en"]
        assert not ({"name_en", "name_zh", "description_en", "description_zh"} & new.keys())
        if new["contract_id"] == "model-node":
            assert new["short_name"] == old["short_name_en"]
            definition = new["definition"]
            old_definition = old["definition"]
            assert isinstance(definition, dict)
            assert isinstance(old_definition, dict)
            assert definition["help_text"] == old_definition["help_text_en"]
            assert not ({"help_text_en", "help_text_zh"} & definition.keys())
        assert _structure(new) == _structure(old)


def _assert_no_sqlite_transients(root: Path) -> None:
    assert tuple(root.rglob("*.sqlite3-wal")) == ()
    assert tuple(root.rglob("*.sqlite3-shm")) == ()


def test_complete_system_copy_rehearsal_preserves_model_semantics_and_history(
    tmp_path: Path,
) -> None:
    inspect_system_source = _capture_api()
    source = tmp_path / "legacy-system"
    initial = SystemApplication.open_or_create(source, clock=lambda: NOW)
    initial.close()
    _downgrade_complete_clean_system(source)

    legacy_nodes = _rows(source, "model_nodes", "node_id")
    legacy_schemes = _rows(source, "task_schemes", "scheme_id")
    historical_runs = _run_rows(source)
    before_report = inspect_system_source(source)
    source_files = _file_snapshot(source)
    expected_counts = (len(legacy_nodes), len(legacy_schemes))

    assert expected_counts[0] > 0
    assert expected_counts[1] > 0
    assert {item["contract_version"] for item in legacy_nodes.values()} == {"0.1.0"}
    assert {item["contract_version"] for item in legacy_schemes.values()} == {"0.1.0"}
    assert historical_runs == ()
    assert not any(before_report.user_owned_row_counts.values())

    rehearsal = tmp_path / "rehearsal-system"
    shutil.copytree(source, rehearsal)
    copied = SystemApplication.open_or_create(rehearsal, clock=lambda: NOW)
    copied.close()

    rehearsal_report = inspect_system_source(rehearsal)
    _assert_single_english_equivalent(
        legacy_nodes,
        _rows(rehearsal, "model_nodes", "node_id"),
    )
    _assert_single_english_equivalent(
        legacy_schemes,
        _rows(rehearsal, "task_schemes", "scheme_id"),
    )
    assert rehearsal_report.model_library_id == before_report.model_library_id
    assert (rehearsal_report.node_count, rehearsal_report.scheme_count) == expected_counts
    assert rehearsal_report.model_identity_sha256 != before_report.model_identity_sha256
    assert _run_rows(rehearsal) == historical_runs
    assert len(_migration_rows(rehearsal)) == sum(expected_counts)
    assert _file_snapshot(source) == source_files
    _assert_no_sqlite_transients(rehearsal)

    applied = SystemApplication.open_or_create(source, clock=lambda: NOW)
    applied.close()
    applied_report = inspect_system_source(source)

    assert applied_report.model_library_id == before_report.model_library_id
    assert applied_report.model_identity_sha256 == rehearsal_report.model_identity_sha256
    assert (applied_report.node_count, applied_report.scheme_count) == expected_counts
    assert not any(applied_report.user_owned_row_counts.values())
    assert _run_rows(source) == historical_runs
    assert len(_migration_rows(source)) == sum(expected_counts)
    _assert_no_sqlite_transients(source)


def test_explicitly_selected_current_system_has_complete_d055_lineage() -> None:
    configured = os.environ.get("PILOT_ASSESSMENT_CURRENT_SYSTEM")
    if not configured:
        pytest.skip("set PILOT_ASSESSMENT_CURRENT_SYSTEM for the explicit release-source gate")

    root = Path(configured).resolve()
    inspect_system_source = _capture_api()
    report = inspect_system_source(root)
    current_nodes = _rows(root, "model_nodes", "node_id")
    current_schemes = _rows(root, "task_schemes", "scheme_id")
    legacy_nodes, legacy_schemes, legacy_identity = _legacy_lineage(root)
    migration_rows = _migration_rows(root)

    assert (report.node_count, report.scheme_count) == (54, 2)
    assert len(migration_rows) == report.node_count + report.scheme_count
    assert {(row[0], row[2], row[3]) for row in migration_rows} == {
        ("node", "0.1.0", "0.2.0"),
        ("scheme", "0.1.0", "0.2.0"),
    }
    _assert_single_english_equivalent(legacy_nodes, current_nodes)
    _assert_single_english_equivalent(legacy_schemes, current_schemes)
    assert report.model_identity_sha256 != legacy_identity
    assert not any(report.user_owned_row_counts.values())
    assert _run_rows(root) == ()
    _assert_no_sqlite_transients(root)
