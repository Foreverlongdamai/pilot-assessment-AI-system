from __future__ import annotations

from datetime import UTC, datetime

from pilot_assessment.runtime import SystemApplication

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_system_application_reopens_starter_and_edit_session_without_project(tmp_path) -> None:
    root = tmp_path / "system"
    first = SystemApplication.open_or_create(
        root,
        model_library_id="model-library.no-project",
        clock=lambda: NOW,
    )
    node = first.editable_model.list_nodes()[0]
    assert first.model_edits.status().model_library_id == "model-library.no-project"
    assert first.current_model.graph_snapshot(first.current_starter_scheme_id).model_library_id == (
        "model-library.no-project"
    )
    first.close()

    reopened = SystemApplication.open_or_create(root, clock=lambda: NOW)
    try:
        assert reopened.seed_result.applied is False
        assert reopened.current_seed_result.applied is False
        assert reopened.current_model.get_node(node.node_id) == node
        assert reopened.model_edits.status().dirty is False
    finally:
        reopened.close()
