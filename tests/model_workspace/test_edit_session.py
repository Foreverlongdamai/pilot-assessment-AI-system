from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.model_workspace_legacy import (
    LegacyModelNodeV010,
    LegacyTaskSchemeV010,
)
from pilot_assessment.model_workspace.content_migration import model_content_fingerprint
from pilot_assessment.model_workspace.edit_session import (
    ModelEditSessionConflictError,
    ModelEditSessionDirtyError,
)
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.runtime import SystemApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _legacy_payload(payload: dict[str, object], *, object_id: str) -> dict[str, object]:
    legacy = dict(payload)
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
        b"legacy-content\0" + object_id.encode("utf-8") + semantic_payload
    ).hexdigest()
    legacy["layout_hash"] = hashlib.sha256(
        b"legacy-layout\0" + object_id.encode("utf-8") + semantic_payload
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


def _edit_first_node(app: SystemApplication, suffix: str, transaction_id: str) -> str:
    current = app.editable_model.list_nodes()[0]
    updated_name = f"{current.name} {suffix}"
    proposal = current.model_copy(update={"name": updated_name})
    with app.model_edits.database.transaction() as connection:
        app.editable_model.update_node(
            proposal,
            expected_semantic_revision=current.semantic_revision,
            expected_layout_revision=None,
            transaction_id=transaction_id,
            actor_id="expert.test",
        )
        app.model_edits.capture_checkpoint(
            connection,
            transaction_id=transaction_id,
            method="model.node.update",
        )
    return current.node_id


def test_edit_session_isolates_undoes_and_atomically_commits(tmp_path: Path) -> None:
    root = tmp_path / "system"
    app = open_test_system(root, clock=lambda: NOW)
    try:
        node_id = _edit_first_node(app, "Draft", "tx.draft-update")
        canonical_before = app.current_model.get_node(node_id)
        draft = app.editable_model.get_node(node_id)
        assert draft.name.endswith(" Draft")
        assert canonical_before.name != draft.name
        assert app.model_edits.status().dirty is True
        with pytest.raises(ModelEditSessionDirtyError):
            app.model_edits.require_clean_for_run()

        app.model_edits.undo(transaction_id="tx.edit-undo", actor_id="expert.test")
        assert app.model_edits.status().dirty is False
        app.model_edits.require_clean_for_run()
        assert app.editable_model.get_node(node_id).name == canonical_before.name

        app.model_edits.redo(transaction_id="tx.edit-redo", actor_id="expert.test")
        assert app.model_edits.status().dirty is True
        _edit_first_node(app, "Final", "tx.draft-update-final")
        app.model_edits.commit(transaction_id="tx.edit-commit", actor_id="expert.test")

        canonical_after = app.current_model.get_node(node_id)
        assert canonical_after.name.endswith(" Draft Final")
        assert canonical_after.semantic_revision == canonical_before.semantic_revision + 1
        assert app.model_edits.status().dirty is False
        assert app.editable_model.get_node(node_id) == canonical_after
    finally:
        app.close()


def test_dirty_edit_session_recovers_and_discard_keeps_canonical(tmp_path: Path) -> None:
    root = tmp_path / "system"
    first = open_test_system(root, clock=lambda: NOW)
    node_id = _edit_first_node(first, "Recovered", "tx.recover-update")
    canonical_name = first.current_model.get_node(node_id).name
    first.close()

    reopened = open_test_system(root, clock=lambda: NOW)
    try:
        status = reopened.model_edits.status()
        assert status.dirty is True
        assert status.recovered is True
        assert reopened.editable_model.get_node(node_id).name.endswith(" Recovered")
        assert reopened.current_model.get_node(node_id).name == canonical_name

        reopened.model_edits.discard(
            transaction_id="tx.recover-discard",
            actor_id="expert.test",
        )
        assert reopened.model_edits.status().dirty is False
        assert reopened.current_model.get_node(node_id).name == canonical_name
        assert reopened.editable_model.get_node(node_id).name == canonical_name
    finally:
        reopened.close()


def test_commit_conflict_preserves_dirty_edit_session(tmp_path: Path) -> None:
    app = open_test_system(tmp_path / "system", clock=lambda: NOW)
    try:
        node_id = _edit_first_node(app, "Draft", "tx.conflict-draft")
        canonical = app.current_model.get_node(node_id)
        app.current_model.update_node(
            canonical.model_copy(update={"name": f"{canonical.name} External"}),
            expected_semantic_revision=canonical.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.external-update",
            actor_id="other.process",
        )

        with pytest.raises(ModelEditSessionConflictError):
            app.model_edits.commit(
                transaction_id="tx.conflicting-commit",
                actor_id="expert.test",
            )

        assert app.model_edits.status().dirty is True
        assert app.editable_model.get_node(node_id).name.endswith(" Draft")
        assert app.current_model.get_node(node_id).name.endswith(" External")
    finally:
        app.close()


def test_legacy_dirty_edit_session_migrates_without_losing_history(tmp_path: Path) -> None:
    root = tmp_path / "system"
    first = open_test_system(root, clock=lambda: NOW)
    node_id = _edit_first_node(first, "Legacy Draft", "tx.legacy-dirty-update")
    status_before = first.model_edits.status()
    assert status_before.dirty is True
    first.close()

    canonical = ProjectDatabase.connect(root / "model-library.sqlite3", clock=lambda: NOW)
    staging = ProjectDatabase.connect(
        root / "staging" / "model-edit" / "workspace.sqlite3",
        clock=lambda: NOW,
    )
    try:
        legacy_base_fingerprint, _legacy_canonical_state = _downgrade_current_tables(canonical)
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
        history_before = tuple(
            (
                row["sequence"],
                row["transaction_id"],
                row["method"],
                row["recorded_at"],
            )
            for row in staging.fetchall(
                "SELECT * FROM model_edit_session_snapshots ORDER BY sequence"
            )
        )
    finally:
        staging.close()
        canonical.close()

    reopened = open_test_system(root, clock=lambda: NOW)
    try:
        status_after = reopened.model_edits.status()
        assert status_after.dirty is True
        assert status_after.recovered is True
        assert status_after.cursor == status_before.cursor
        assert status_after.latest_sequence == status_before.latest_sequence
        assert reopened.editable_model.get_node(node_id).name.endswith(" Legacy Draft")
        assert reopened.current_model.get_node(node_id).name.endswith(" Legacy Draft") is False
        history_after = tuple(
            (
                row["sequence"],
                row["transaction_id"],
                row["method"],
                row["recorded_at"],
            )
            for row in reopened.model_edits.database.fetchall(
                "SELECT * FROM model_edit_session_snapshots ORDER BY sequence"
            )
        )
        assert history_after == history_before
        assert (
            reopened.store.database.fetchone(
                "SELECT COUNT(*) AS count FROM model_content_migration_events"
            )["count"]
            > 0
        )
        assert (
            reopened.model_edits.database.fetchone(
                "SELECT COUNT(*) AS count FROM model_content_migration_events"
            )["count"]
            > 0
        )
        assert tuple(root.glob("staging/model-edit/workspace.conflict.*.sqlite3")) == ()
    finally:
        reopened.close()
