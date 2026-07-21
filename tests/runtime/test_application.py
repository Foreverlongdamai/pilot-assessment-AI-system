from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.model_library.profile import load_hover_starter_package
from pilot_assessment.model_library.repository import LibraryQuery
from pilot_assessment.model_workspace.execution import CurrentModelExecutionMaterializer
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.runtime import CurrentRunPreflightService, ProjectApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_system_owns_model_once_while_project_moves_without_a_model_copy(
    tmp_path: Path,
) -> None:
    profile = load_hover_starter_package()
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    root = tmp_path / "project"
    application = ProjectApplication.create(
        root,
        system=system,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        expected_count = len(profile.library_items)
        assert system.seed_result.applied is True
        assert system.current_seed_result.applied is True
        assert system.seed_result.manifest_hash == profile.manifest_hash
        assert len(system.components.list_records()) == expected_count
        assert len(application.components.list_records()) == 0
        assert application.project.database.fetchone("SELECT COUNT(*) FROM model_nodes")[0] == 0
        assert application.project.database.fetchone("SELECT COUNT(*) FROM task_schemes")[0] == 0
        assert len(system.operator_registry.catalog()) > 0
        assert len(system.source_catalog) == len(profile.source_catalog)
        assert set(system.source_provider_registry.source_ids()) == {
            descriptor.source_id for descriptor in profile.source_catalog.descriptors()
        }
        assert application.system is system
        assert application.current_model is system.current_model
        assert isinstance(application.current_model, CurrentModelWorkspaceService)
        assert isinstance(application.execution_materializer, CurrentModelExecutionMaterializer)
        assert isinstance(application.current_preflight, CurrentRunPreflightService)
        assert application.current_model.repository.database is system.store.database
        assert len(application.current_model.list_nodes()) == 53
        assert len(application.current_model.list_schemes()) == 1

        repeated = system.initialize_starter()
        assert repeated.applied is False
        assert len(system.components.list_records()) == expected_count

        draft = system.schemes.create_draft_from_scheme(
            system.starter_scheme_id,
            draft_id="draft.persisted",
            author_id="expert.one",
        )
        assert system.drafts.get("draft.persisted") == draft
        assert (
            len(
                system.components.list_records(
                    LibraryQuery(kind=ComponentKind.ASSESSMENT_SCHEME_VERSION)
                )
            )
            == 1
        )
    finally:
        application.close()

    moved = tmp_path / "moved-project"
    root.rename(moved)
    reopened = ProjectApplication.open(moved, system=system, clock=lambda: NOW)
    try:
        assert reopened.project.root == moved.resolve()
        assert reopened.drafts.get("draft.persisted") == draft
        assert (
            system.components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                profile.scheme.scheme_version_id,
            )
            == profile.scheme
        )
        assert len(reopened.components.list_records()) == 0
        assert reopened.project.database.fetchone("SELECT COUNT(*) FROM model_nodes")[0] == 0
        assert len(reopened.current_model.list_nodes()) == 53
        assert len(reopened.current_model.list_schemes()) == 1
    finally:
        reopened.close()
        system.close()
