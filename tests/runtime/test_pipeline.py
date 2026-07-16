from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.bayesian import ObservationKind
from pilot_assessment.contracts.run import RunPurpose, RunStage
from pilot_assessment.persistence.database import decode_canonical_json
from pilot_assessment.runtime import (
    ProjectApplication,
    RunCancelledError,
    RunResultNotFoundError,
)
from tests.runtime.support import minimal_o1_scheme

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _artifact_json(application: ProjectApplication, artifact_id: str):
    with application.artifacts.open_verified(artifact_id) as stream:
        return decode_canonical_json(stream.read())


def test_pipeline_executes_one_dynamic_evidence_to_bn_and_persists_exact_result(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external"
    shutil.copytree(m4_workflow_bundle, external)
    external_manifest = (external / "manifest.json").read_bytes()
    application = ProjectApplication.create(
        tmp_path / "project",
        project_id="project.pipeline",
        name="Pipeline project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        imported = application.sessions.import_bundle(
            external,
            transaction_id="tx.pipeline-session",
            imported_by="expert.one",
        )
        scheme = minimal_o1_scheme(
            application,
            scheme_version_id="assessment-scheme-version.pipeline-o1.v1",
            scheme_concept_id="assessment-scheme-concept.pipeline-o1",
            name="Pipeline O1 software smoke",
            created_at=NOW,
        )
        application.components.add(scheme, recorded_at=NOW)
        prepared = application.preflight.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_version_id=scheme.scheme_version_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        snapshot = application.preflight.build_snapshot(
            prepared.report.preflight_id,
            run_id="run.pipeline-o1",
        )
        application.runs.create(
            snapshot,
            preflight_id=prepared.report.preflight_id,
            requested_at=NOW,
        )

        progress: list[tuple[RunStage, int, int]] = []
        result = application.pipeline.execute(
            snapshot,
            progress=lambda stage, completed, total, _message: progress.append(
                (stage, completed, total)
            ),
        )
        artifact_count = application.project.database.fetchone(
            "SELECT COUNT(*) FROM managed_artifacts"
        )[0]
        assert application.pipeline.execute(snapshot) == result
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM managed_artifacts")[0]
            == artifact_count
        )

        assert result.run_id == snapshot.run_id
        assert len(result.evidence_result_refs) == 1
        assert len(result.evidence_trace_refs) == 1
        assert application.results.get_by_run(snapshot.run_id) == result
        observation_payload = _artifact_json(
            application,
            result.observation_set_ref.artifact_id,
        )
        posterior_payload = _artifact_json(application, result.posterior_ref.artifact_id)
        evidence_payload = _artifact_json(
            application,
            result.evidence_result_refs[0].artifact_id,
        )
        assert observation_payload["observations"][0]["kind"] in {
            ObservationKind.HARD.value,
            ObservationKind.VIRTUAL.value,
        }
        assert posterior_payload["posteriors"]
        assert evidence_payload["evidence_version_id"] == (scheme.evidence_versions[0].version_id)
        assert evidence_payload["calculation_status"] == "computed"
        assert progress == [
            (RunStage.SNAPSHOT_VALIDATION, 1, 6),
            (RunStage.INGESTION, 2, 6),
            (RunStage.SYNCHRONIZATION, 3, 6),
            (RunStage.EVIDENCE, 4, 6),
            (RunStage.INFERENCE, 5, 6),
            (RunStage.REPORTING, 6, 6),
        ]
        assert (
            application.sessions.verify_managed_revision(imported.revision.session_revision_id)
            == imported.revision
        )
        assert (external / "manifest.json").read_bytes() == external_manifest

        cancelled_snapshot = application.preflight.build_snapshot(
            prepared.report.preflight_id,
            run_id="run.pipeline-o1-cancelled",
        )
        application.runs.create(
            cancelled_snapshot,
            preflight_id=prepared.report.preflight_id,
            requested_at=NOW,
        )
        cancellation_checks = 0

        def cancel_at_first_artifact_boundary() -> None:
            nonlocal cancellation_checks
            cancellation_checks += 1
            if cancellation_checks == 7:
                raise RunCancelledError("cancel at artifact boundary")

        reference_count_before = application.project.database.fetchone(
            "SELECT COUNT(*) FROM artifact_references"
        )[0]
        with pytest.raises(RunCancelledError, match="artifact boundary"):
            application.pipeline.execute(
                cancelled_snapshot,
                cancellation=cancel_at_first_artifact_boundary,
            )
        with pytest.raises(RunResultNotFoundError):
            application.results.get_by_run(cancelled_snapshot.run_id)
        assert (
            application.project.database.fetchone("SELECT COUNT(*) FROM artifact_references")[0]
            == reference_count_before
        )
    finally:
        application.close()
