from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.run import RunPurpose, TechnicalDisposition
from pilot_assessment.runtime import ProjectApplication

NOW = datetime(2026, 7, 17, 16, 0, tzinfo=UTC)


def test_current_preflight_materializes_once_and_does_not_edit_current_objects(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external"
    shutil.copytree(m4_workflow_bundle, external)
    application = ProjectApplication.create(
        tmp_path / "project",
        project_id="project.current-preflight",
        name="Current preflight",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        imported = application.sessions.import_bundle(
            external,
            transaction_id="tx.current-preflight-session",
            imported_by="expert.one",
        )
        scheme_before = application.current_model.get_scheme(application.current_starter_scheme_id)
        node_before = {
            node.node_id: (node.semantic_revision, node.content_hash)
            for node in application.current_model.list_nodes()
        }
        history_before = len(application.current_model.scheme_history(scheme_before.scheme_id))

        report = application.current_preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme_before.scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )

        assert report.technical_disposition is TechnicalDisposition.READY
        assert report.formal_run_authorized is False
        assert report.synthetic_data is True
        assert report.execution_preflight is not None
        assert len(report.active_node_refs) == 52
        assert tuple(item.node_id for item in report.active_node_refs) == tuple(
            sorted(scheme_before.computed_active_closure)
        )
        assert application.current_preflight.get(report.preflight_id) == report
        assert (
            application.project.database.fetchone(
                "SELECT COUNT(*) FROM model_execution_materializations"
            )[0]
            == 1
        )
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM model_run_preflights")[0]
            == 1
        )

        repeated = application.current_preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme_before.scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        assert repeated == report
        assert (
            application.project.database.fetchone(
                "SELECT COUNT(*) FROM model_execution_materializations"
            )[0]
            == 1
        )
        assert application.current_model.get_scheme(scheme_before.scheme_id) == scheme_before
        assert len(application.current_model.scheme_history(scheme_before.scheme_id)) == (
            history_before
        )
        assert {
            node.node_id: (node.semantic_revision, node.content_hash)
            for node in application.current_model.list_nodes()
        } == node_before

        preview = application.current_preflight.preview_node(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme_before.scheme_id,
            node_id=scheme_before.computed_active_closure[0],
            runtime_parameters={},
            preview_id="preview.current-scheme",
        )
        assert preview.purpose is RunPurpose.PREVIEW
        assert preview.scheme == scheme_before
        assert application.project.database.fetchone("SELECT COUNT(*) FROM runs")[0] == 0
        assert application.project.database.fetchone("SELECT COUNT(*) FROM model_run_links")[0] == 0
        assert application.current_model.get_scheme(scheme_before.scheme_id) == scheme_before
    finally:
        application.close()
