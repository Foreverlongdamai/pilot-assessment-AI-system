from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.model_library.profile import load_hover_starter_package
from pilot_assessment.model_workspace.edit_session import ModelEditSessionManager
from pilot_assessment.model_workspace.migration import seed_current_starter
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.model_workspace_repository import (
    SqliteModelWorkspaceRepository,
)
from pilot_assessment.persistence.project import ProjectStore
from pilot_assessment.persistence.transactions import IdempotencyStore
from pilot_assessment.runtime import ProjectApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 21, 14, 0, tzinfo=UTC)


def _legacy_project_model(
    root: Path,
    *,
    system,
    project_id: str,
) -> tuple[ProjectStore, CurrentModelWorkspaceService]:
    project = ProjectStore.create(
        root,
        project_id=project_id,
        name="Legacy project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    workspace = CurrentModelWorkspaceService(
        SqliteModelWorkspaceRepository(project.database),
        model_library_id=project_id,
        operator_registry=system.operator_registry,
        source_catalog=system.source_catalog,
        clock=lambda: NOW,
    )
    seed_current_starter(
        load_hover_starter_package(),
        workspace,
        recorded_at=NOW,
    )
    return project, workspace


def test_saved_legacy_model_is_merged_without_overwriting_system_nodes_and_replays(
    tmp_path: Path,
) -> None:
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    project_root = tmp_path / "legacy-project"
    project, legacy = _legacy_project_model(
        project_root,
        system=system,
        project_id="project.legacy.saved",
    )
    source = legacy.list_nodes()[0]
    legacy.update_node(
        source.model_copy(update={"name": f"{source.name} Legacy"}),
        expected_semantic_revision=source.semantic_revision,
        expected_layout_revision=None,
        transaction_id="tx.legacy.saved-edit",
        actor_id="expert.legacy",
    )
    project.close()

    original = system.current_model.get_node(source.node_id)
    initial_count = len(system.current_model.list_nodes())
    application = ProjectApplication.open(project_root, system=system, clock=lambda: NOW)
    try:
        result = application.legacy_model_import
        imported_id = result.node_id_mapping[source.node_id]
        assert result.legacy_model_detected is True
        assert result.imported is True
        assert result.replayed is False
        assert result.inserted_node_count > 0
        assert result.inserted_scheme_count == 1
        assert imported_id != source.node_id
        assert system.current_model.get_node(source.node_id) == original
        assert system.current_model.get_node(imported_id).name.endswith(" Legacy")
        assert len(system.current_model.list_nodes()) > initial_count
        assert application.project.database.fetchone("SELECT COUNT(*) FROM model_nodes")[0] == 53
    finally:
        application.close()

    replay = ProjectApplication.open(project_root, system=system, clock=lambda: NOW)
    try:
        assert replay.legacy_model_import.replayed is True
        assert replay.legacy_model_import.imported is False
        assert replay.legacy_model_import.node_id_mapping[source.node_id] == imported_id
    finally:
        replay.close()
        system.close()


def test_unsaved_legacy_edit_is_recovered_as_one_system_staging_change(
    tmp_path: Path,
) -> None:
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    project_root = tmp_path / "legacy-dirty-project"
    project, legacy = _legacy_project_model(
        project_root,
        system=system,
        project_id="project.legacy.dirty",
    )
    manager = ModelEditSessionManager(
        model_root=project.root,
        model_library_id=project.descriptor.project_id,
        canonical_database=project.database,
        canonical_workspace=legacy,
        canonical_idempotency=IdempotencyStore(
            project.database,
            AuditRepository(project.database),
            clock=lambda: NOW,
        ),
        operator_registry=system.operator_registry,
        source_catalog=system.source_catalog,
        clock=lambda: NOW,
    )
    source = manager.workspace.list_nodes()[0]
    with manager.database.transaction() as connection:
        manager.workspace.update_node(
            source.model_copy(update={"name": f"{source.name} Unsaved"}),
            expected_semantic_revision=source.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.legacy.unsaved-edit",
            actor_id="expert.legacy",
        )
        manager.capture_checkpoint(
            connection,
            transaction_id="tx.legacy.unsaved-edit",
            method="model.node.update",
        )
    assert manager.status().dirty is True
    manager.close()
    project.close()

    canonical_name = system.current_model.get_node(source.node_id).name
    application = ProjectApplication.open(project_root, system=system, clock=lambda: NOW)
    try:
        result = application.legacy_model_import
        assert result.legacy_model_detected is True
        assert result.dirty_edit_recovered is True
        assert result.inserted_node_count == 0
        assert result.inserted_scheme_count == 0
        assert system.current_model.get_node(source.node_id).name == canonical_name
        assert system.editable_model.get_node(source.node_id).name.endswith(" Unsaved")
        assert system.model_edits.status().dirty is True
        assert system.model_edits.status().change_count == 1
    finally:
        system.model_edits.discard(
            transaction_id="tx.test.discard-recovered-edit",
            actor_id="expert.test",
        )
        application.close()
        system.close()
