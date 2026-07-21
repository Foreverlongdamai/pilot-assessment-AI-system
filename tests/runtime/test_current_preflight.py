from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.run import (
    CurrentModelRunPreflightReportV2,
    CurrentModelRunSnapshotV2,
    RunPurpose,
    TechnicalDisposition,
)
from pilot_assessment.contracts.source_provenance import SourceChangeSummary
from pilot_assessment.runtime import ProjectApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 17, 16, 0, tzinfo=UTC)


def test_current_preflight_materializes_once_and_does_not_edit_current_objects(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external"
    shutil.copytree(m4_workflow_bundle, external)
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    application = ProjectApplication.create(
        tmp_path / "project",
        system=system,
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
        assert isinstance(report, CurrentModelRunPreflightReportV2)
        assert report.contract_version == "0.2.0"
        assert report.source_snapshot_ref is not None
        assert report.backend_source_identity == system.source_provenance.loaded_identity
        with application.artifacts.open_verified(report.source_snapshot_ref.artifact_id) as stream:
            assert stream.read(2) == b"PK"
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
                "SELECT COUNT(*) FROM model_execution_materializations_v2"
            )[0]
            == 1
        )
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM model_run_preflights_v2")[0]
            == 1
        )

        repeated = application.current_preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_id=scheme_before.scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        assert repeated == report
        assert application.artifacts.reference_count(report.source_snapshot_ref.artifact_id) == 1
        assert (
            application.project.database.fetchone(
                "SELECT COUNT(*) FROM model_execution_materializations_v2"
            )[0]
            == 1
        )
        assert application.current_model.get_scheme(scheme_before.scheme_id) == scheme_before

        clean_status = system.source_provenance.disk_status()
        drift_status = clean_status.model_copy(
            update={
                "loaded_to_disk_changes": SourceChangeSummary(
                    modified=("backend/src/pilot_assessment/example.py",)
                ),
                "runtime_restart_required": True,
            }
        )
        original_disk_status = system.source_provenance.disk_status
        system.source_provenance.disk_status = lambda: drift_status  # type: ignore[method-assign]
        try:
            blocked = application.current_preflight.prepare(
                session_revision_id=imported.revision.session_revision_id,
                scheme_id=scheme_before.scheme_id,
                purpose=RunPurpose.SOFTWARE_TEST,
                runtime_parameters={"drift_test": True},
            )
        finally:
            system.source_provenance.disk_status = original_disk_status  # type: ignore[method-assign]
        assert blocked.technical_disposition is TechnicalDisposition.BLOCKED
        assert blocked.source_snapshot_ref is None
        assert any(item.code == "runtime.restart_required" for item in blocked.diagnostics)
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
        assert isinstance(preview, CurrentModelRunSnapshotV2)
        assert preview.source_snapshot_ref == report.source_snapshot_ref
        assert application.artifacts.reference_count(report.source_snapshot_ref.artifact_id) == 2
        assert preview.scheme == scheme_before
        assert application.project.database.fetchone("SELECT COUNT(*) FROM runs")[0] == 0
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM model_run_links_v2")[0] == 0
        )
        assert application.current_model.get_scheme(scheme_before.scheme_id) == scheme_before
    finally:
        application.close()
        system.close()
