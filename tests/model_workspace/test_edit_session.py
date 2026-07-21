from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.model_workspace.edit_session import (
    ModelEditSessionConflictError,
    ModelEditSessionDirtyError,
)
from pilot_assessment.runtime import SystemApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _edit_first_node(app: SystemApplication, suffix: str, transaction_id: str) -> str:
    current = app.editable_model.list_nodes()[0]
    updated_name = f"{current.name_en} {suffix}"
    proposal = current.model_copy(update={"name_en": updated_name})
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
        assert draft.name_en.endswith(" Draft")
        assert canonical_before.name_en != draft.name_en
        assert app.model_edits.status().dirty is True
        with pytest.raises(ModelEditSessionDirtyError):
            app.model_edits.require_clean_for_run()

        app.model_edits.undo(transaction_id="tx.edit-undo", actor_id="expert.test")
        assert app.model_edits.status().dirty is False
        app.model_edits.require_clean_for_run()
        assert app.editable_model.get_node(node_id).name_en == canonical_before.name_en

        app.model_edits.redo(transaction_id="tx.edit-redo", actor_id="expert.test")
        assert app.model_edits.status().dirty is True
        _edit_first_node(app, "Final", "tx.draft-update-final")
        app.model_edits.commit(transaction_id="tx.edit-commit", actor_id="expert.test")

        canonical_after = app.current_model.get_node(node_id)
        assert canonical_after.name_en.endswith(" Draft Final")
        assert canonical_after.semantic_revision == canonical_before.semantic_revision + 1
        assert app.model_edits.status().dirty is False
        assert app.editable_model.get_node(node_id) == canonical_after
    finally:
        app.close()


def test_dirty_edit_session_recovers_and_discard_keeps_canonical(tmp_path: Path) -> None:
    root = tmp_path / "system"
    first = open_test_system(root, clock=lambda: NOW)
    node_id = _edit_first_node(first, "Recovered", "tx.recover-update")
    canonical_name = first.current_model.get_node(node_id).name_en
    first.close()

    reopened = open_test_system(root, clock=lambda: NOW)
    try:
        status = reopened.model_edits.status()
        assert status.dirty is True
        assert status.recovered is True
        assert reopened.editable_model.get_node(node_id).name_en.endswith(" Recovered")
        assert reopened.current_model.get_node(node_id).name_en == canonical_name

        reopened.model_edits.discard(
            transaction_id="tx.recover-discard",
            actor_id="expert.test",
        )
        assert reopened.model_edits.status().dirty is False
        assert reopened.current_model.get_node(node_id).name_en == canonical_name
        assert reopened.editable_model.get_node(node_id).name_en == canonical_name
    finally:
        reopened.close()


def test_commit_conflict_preserves_dirty_edit_session(tmp_path: Path) -> None:
    app = open_test_system(tmp_path / "system", clock=lambda: NOW)
    try:
        node_id = _edit_first_node(app, "Draft", "tx.conflict-draft")
        canonical = app.current_model.get_node(node_id)
        app.current_model.update_node(
            canonical.model_copy(update={"name_en": f"{canonical.name_en} External"}),
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
        assert app.editable_model.get_node(node_id).name_en.endswith(" Draft")
        assert app.current_model.get_node(node_id).name_en.endswith(" External")
    finally:
        app.close()
