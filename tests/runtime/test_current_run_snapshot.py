from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_workspace import EvidenceNodeDefinition
from pilot_assessment.contracts.run import AssessmentRunV2, RunPurpose, RunState
from pilot_assessment.runtime import ProjectApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)


def test_current_run_freezes_nodes_executes_and_survives_later_shared_node_edit(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external"
    shutil.copytree(m4_workflow_bundle, external)
    project_root = tmp_path / "project"
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    application = ProjectApplication.create(
        project_root,
        system=system,
        project_id="project.current-run",
        name="Current run",
        created_at=NOW,
        clock=lambda: NOW,
    )
    first_snapshot_hash = ""
    first_node_hash = ""
    try:
        imported = application.sessions.import_bundle(
            external,
            transaction_id="tx.current-run-session",
            imported_by="expert.one",
        )
        scheme = application.current_model.get_scheme(application.current_starter_scheme_id)
        first_preflight = application.current_preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme.scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        first = application.current_preflight.create_run(
            first_preflight.preflight_id,
            run_id="run.current.first",
            expected_scheme_revision=scheme.semantic_revision,
            requested_at=NOW,
        )
        assert isinstance(first, AssessmentRunV2)
        assert len(first.snapshot.active_nodes) == 52
        assert application.runs.get(first.run_id) == first
        assert (
            application.current_preflight.create_run(
                first_preflight.preflight_id,
                run_id="run.current.first",
                expected_scheme_revision=scheme.semantic_revision,
                requested_at=NOW,
            )
            == first
        )

        application.coordinator.enqueue(first.run_id)
        completed = application.coordinator.wait(first.run_id, timeout=30.0)
        assert isinstance(completed, AssessmentRunV2)
        assert completed.state is RunState.COMPLETED
        result = application.results.get_by_run(first.run_id)
        assert result.snapshot_hash == first.snapshot.snapshot_hash
        assert (
            application.current_preflight.create_run(
                first_preflight.preflight_id,
                run_id="run.current.first",
                expected_scheme_revision=scheme.semantic_revision,
                requested_at=NOW,
            )
            == completed
        )
        first_snapshot_hash = first.snapshot.snapshot_hash

        evidence = next(
            node
            for node in application.current_model.list_nodes()
            if isinstance(node.definition, EvidenceNodeDefinition)
        )
        first_node_hash = evidence.content_hash
        application.current_model.update_node(
            evidence.model_copy(
                update={
                    "description_en": (
                        f"{evidence.description_en} Expert-visible documentation edit."
                    )
                }
            ),
            expected_semantic_revision=evidence.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.current-node-edit",
            actor_id="expert.one",
        )
        changed_scheme = application.current_model.get_scheme(scheme.scheme_id)
        second_preflight = application.current_preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme.scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        second = application.current_preflight.create_run(
            second_preflight.preflight_id,
            run_id="run.current.second",
            expected_scheme_revision=changed_scheme.semantic_revision,
            requested_at=NOW,
        )

        assert second.snapshot.snapshot_hash != first_snapshot_hash
        assert application.runs.get(first.run_id).snapshot.snapshot_hash == first_snapshot_hash
        frozen_node = next(
            node for node in first.snapshot.active_nodes if node.node_id == evidence.node_id
        )
        future_node = next(
            node for node in second.snapshot.active_nodes if node.node_id == evidence.node_id
        )
        assert frozen_node.content_hash == first_node_hash
        assert future_node.content_hash != first_node_hash
        assert (
            application.current_preflight.create_run(
                first_preflight.preflight_id,
                run_id="run.current.first",
                expected_scheme_revision=scheme.semantic_revision,
                requested_at=NOW,
            )
            == completed
        )
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM model_run_links_v2")[0] == 2
        )
    finally:
        application.close()

    reopened = ProjectApplication.open(project_root, system=system, clock=lambda: NOW)
    try:
        replay = reopened.runs.get("run.current.first")
        assert isinstance(replay, AssessmentRunV2)
        assert replay.state is RunState.COMPLETED
        assert replay.snapshot.snapshot_hash == first_snapshot_hash
        assert any(node.content_hash == first_node_hash for node in replay.snapshot.active_nodes)
        assert reopened.results.get_by_run(replay.run_id).snapshot_hash == first_snapshot_hash
    finally:
        reopened.close()
        system.close()
