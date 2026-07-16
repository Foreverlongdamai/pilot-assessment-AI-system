from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind
from pilot_assessment.contracts.run import RunPurpose, RunState
from pilot_assessment.runtime import ProjectApplication
from pilot_assessment.schemes.operations import CloneComponentVersion, MoveLayoutNode
from tests.runtime.support import minimal_o1_scheme

NOW = datetime(2026, 7, 16, 22, 0, tzinfo=UTC)


def test_managed_project_survives_source_deletion_and_directory_move(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external_bundle = tmp_path / "external-session"
    project_root = tmp_path / "assessment-project"
    moved_root = tmp_path / "moved-assessment-project"
    shutil.copytree(m4_workflow_bundle, external_bundle)

    application = ProjectApplication.create(
        project_root,
        project_id="project.m6-vertical-slice",
        name="M6 managed vertical slice",
        created_at=NOW,
        clock=lambda: NOW,
    )
    published_scheme_id = ""
    imported_revision_id = ""
    result_id = ""
    run_id = "run.m6-managed"
    result_before_move = None
    try:
        imported = application.sessions.import_bundle(
            external_bundle,
            transaction_id="tx.m6-managed-session",
            imported_by="expert.integration",
        )
        imported_revision_id = imported.revision.session_revision_id
        managed_bundle = application.sessions.managed_bundle_path(imported_revision_id)
        assert managed_bundle.is_dir()
        assert project_root.resolve() in managed_bundle.resolve().parents

        shutil.rmtree(external_bundle)
        assert not external_bundle.exists()
        assert application.sessions.verify_managed_revision(imported_revision_id) == (
            imported.revision
        )

        foundation = minimal_o1_scheme(
            application,
            scheme_version_id="assessment-scheme-version.m6-foundation-o1.v1",
            scheme_concept_id="assessment-scheme-concept.m6-portable",
            name="M6 portable O1 foundation",
            created_at=NOW,
        )
        application.components.add(foundation, recorded_at=NOW)
        draft = application.schemes.create_draft_from_scheme(
            foundation.scheme_version_id,
            draft_id="draft.m6-portable",
            author_id="expert.integration",
        ).draft
        draft = application.schemes.apply_operation(
            draft.draft_id,
            CloneComponentVersion(
                expected_graph_version=draft.graph_version,
                source=ComponentIdRef(
                    kind=foundation.layout.kind,
                    version_id=foundation.layout.version_id,
                ),
                candidate_id="candidate.m6-layout",
                replace_source=True,
            ),
            author_id="expert.integration",
        ).draft
        output_node_id = foundation.output_node_ids[0].version_id
        draft = application.schemes.apply_operation(
            draft.draft_id,
            MoveLayoutNode(
                expected_layout_version=draft.layout_version,
                candidate_id="candidate.m6-layout",
                node_id=output_node_id,
                x=320.0,
                y=180.0,
            ),
            author_id="expert.integration",
        ).draft
        published = application.schemes.publish(
            draft.draft_id,
            expected_graph_version=draft.graph_version,
            expected_layout_version=draft.layout_version,
            author_id="expert.integration",
            note="Portable M6 software-test scheme derived from the editable foundation.",
        )
        published_scheme_id = published.scheme.scheme_version_id
        assert published.scheme.scheme_concept_id == foundation.scheme_concept_id
        assert published.scheme.scheme_version_id != foundation.scheme_version_id
        assert [reference.kind for reference in published.new_component_refs] == [
            ComponentKind.LAYOUT_VERSION
        ]

        prepared = application.preflight.prepare(
            session_revision_id=imported_revision_id,
            scheme_version_id=published_scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        snapshot = application.preflight.build_snapshot(
            prepared.report.preflight_id,
            run_id=run_id,
        )
        application.runs.create(
            snapshot,
            preflight_id=prepared.report.preflight_id,
            requested_at=NOW,
        )
        application.coordinator.enqueue(run_id)
        completed = application.coordinator.wait(run_id, timeout=30)
        assert completed.state is RunState.COMPLETED
        result_before_move = application.results.get_by_run(run_id)
        result_id = result_before_move.result_id
        with application.artifacts.open_verified(
            result_before_move.observation_set_ref.artifact_id
        ) as stream:
            assert stream.read()
    finally:
        application.close()

    assert project_root.resolve().parent == moved_root.resolve().parent
    project_root.rename(moved_root)
    assert not project_root.exists()

    reopened = ProjectApplication.open(moved_root, clock=lambda: NOW)
    try:
        assert reopened.project.descriptor.project_id == "project.m6-vertical-slice"
        assert reopened.sessions.verify_managed_revision(imported_revision_id).managed_bundle_path
        replay = reopened.schemes.replay_exact(published_scheme_id)
        assert replay.scheme.scheme_version_id == published_scheme_id
        assert all(
            reopened.components.get_exact(reference.kind, reference.version_id).content_hash
            == reference.content_hash
            for reference in replay.component_refs
        )
        result_after_move = reopened.results.get(result_id)
        assert result_after_move == result_before_move
        assert reopened.results.get_by_run(run_id) == result_after_move
        with reopened.artifacts.open_verified(
            result_after_move.observation_set_ref.artifact_id
        ) as stream:
            assert stream.read()
        rebased_draft = reopened.drafts.get("draft.m6-portable").draft
        assert rebased_draft.base_scheme_version_id == published_scheme_id
        assert rebased_draft.candidate_components == ()
    finally:
        reopened.close()
