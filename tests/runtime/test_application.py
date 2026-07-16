from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.model_library.profile import load_hover_starter_package
from pilot_assessment.model_library.repository import LibraryQuery
from pilot_assessment.runtime import ProjectApplication

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_application_composes_services_seeds_once_and_reopens_after_project_move(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    profile = load_hover_starter_package()
    application = ProjectApplication.create(
        root,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        expected_count = len(profile.library_items)
        assert application.seed_result.applied is True
        assert application.seed_result.manifest_hash == profile.manifest_hash
        assert len(application.components.list_records()) == expected_count
        assert len(application.operator_registry.catalog()) > 0
        assert len(application.source_catalog) == len(profile.source_catalog)
        assert set(application.source_provider_registry.source_ids()) == {
            descriptor.source_id for descriptor in profile.source_catalog.descriptors()
        }
        assert application.starter_scheme_id == profile.scheme.scheme_version_id
        assert application.run_recovery == ()
        assert application.runs.list_runs() == ()
        assert application.preflight.operator_registry is application.operator_registry
        assert application.pipeline.results is application.results

        repeated = application.initialize_starter()
        assert repeated.applied is False
        assert len(application.components.list_records()) == expected_count
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM project_seed_markers")[0]
            == 1
        )

        draft = application.schemes.create_draft_from_scheme(
            application.starter_scheme_id,
            draft_id="draft.persisted",
            author_id="expert.one",
        )
        assert application.drafts.get("draft.persisted") == draft
        assert (
            len(
                application.components.list_records(
                    LibraryQuery(kind=ComponentKind.ASSESSMENT_SCHEME_VERSION)
                )
            )
            == 1
        )
    finally:
        application.close()

    moved = tmp_path / "moved-project"
    root.rename(moved)
    reopened = ProjectApplication.open(moved, clock=lambda: NOW)
    try:
        assert reopened.project.root == moved.resolve()
        assert reopened.drafts.get("draft.persisted") == draft
        assert (
            reopened.components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                profile.scheme.scheme_version_id,
            )
            == profile.scheme
        )
        assert reopened.seed_result.applied is False
        assert reopened.initialize_starter().applied is False
        assert len(reopened.components.list_records()) == expected_count
        assert (
            reopened.project.database.fetchone("SELECT COUNT(*) FROM project_seed_markers")[0] == 1
        )
    finally:
        reopened.close()
