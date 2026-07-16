from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.bayesian import ObservationKind
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
    PinnedComponentRef,
    VersionLineage,
)
from pilot_assessment.contracts.run import RunPurpose, RunStage
from pilot_assessment.model_library.repository import component_content_hash
from pilot_assessment.persistence.database import decode_canonical_json
from pilot_assessment.runtime import (
    ProjectApplication,
    RunCancelledError,
    RunResultNotFoundError,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
ZERO_HASH = "0" * 64


def _pin(item) -> PinnedComponentRef:
    identity = {
        EvidenceVersion: (ComponentKind.EVIDENCE_VERSION, "evidence_version_id"),
        EvidenceBindingVersion: (
            ComponentKind.EVIDENCE_BINDING_VERSION,
            "evidence_binding_version_id",
        ),
        BnNodeVersion: (ComponentKind.BN_NODE_VERSION, "bn_node_version_id"),
        CptVersion: (ComponentKind.CPT_VERSION, "cpt_version_id"),
    }[type(item)]
    return PinnedComponentRef(
        kind=identity[0],
        version_id=getattr(item, identity[1]),
        content_hash=item.content_hash,
    )


def _minimal_o1_scheme(application: ProjectApplication) -> AssessmentSchemeVersion:
    starter = application.components.get_exact(
        ComponentKind.ASSESSMENT_SCHEME_VERSION,
        application.starter_scheme_id,
    )
    assert isinstance(starter, AssessmentSchemeVersion)
    evidence = next(
        item
        for reference in starter.evidence_versions
        if isinstance(
            item := application.components.get_exact(reference.kind, reference.version_id),
            EvidenceVersion,
        )
        and item.recipe.anchor.anchor_id == "O1"
    )
    binding = next(
        item
        for reference in starter.evidence_binding_versions
        if isinstance(
            item := application.components.get_exact(reference.kind, reference.version_id),
            EvidenceBindingVersion,
        )
        and item.evidence_version_id.version_id == evidence.evidence_version_id
    )
    bn_by_id = {
        item.bn_node_version_id: item
        for reference in starter.bn_node_versions
        if isinstance(
            item := application.components.get_exact(reference.kind, reference.version_id),
            BnNodeVersion,
        )
    }
    selected_bn_ids: set[str] = set()
    pending = list(binding.ordered_probabilistic_parent_ids)
    while pending:
        reference = pending.pop()
        if reference.kind is not ComponentKind.BN_NODE_VERSION:
            continue
        if reference.version_id in selected_bn_ids:
            continue
        selected_bn_ids.add(reference.version_id)
        pending.extend(bn_by_id[reference.version_id].ordered_probabilistic_parent_ids)
    selected_bn = tuple(
        bn_by_id[reference.version_id]
        for reference in starter.bn_node_versions
        if reference.version_id in selected_bn_ids
    )
    selected_cpt_ids = {
        binding.cpt_version_id.version_id,
        *(node.cpt_version_id.version_id for node in selected_bn),
    }
    selected_cpts = tuple(
        item
        for reference in starter.cpt_versions
        if reference.version_id in selected_cpt_ids
        and isinstance(
            item := application.components.get_exact(reference.kind, reference.version_id),
            CptVersion,
        )
    )
    provisional = starter.model_copy(
        update={
            "scheme_version_id": "assessment-scheme-version.pipeline-o1.v1",
            "scheme_concept_id": "assessment-scheme-concept.pipeline-o1",
            "name": "Pipeline O1 software smoke",
            "description": "Minimal engineering-only M6 pipeline scheme.",
            "evidence_versions": (_pin(evidence),),
            "evidence_binding_versions": (_pin(binding),),
            "bn_node_versions": tuple(_pin(item) for item in selected_bn),
            "cpt_versions": tuple(_pin(item) for item in selected_cpts),
            "output_node_ids": (binding.ordered_probabilistic_parent_ids[0],),
            "lineage": VersionLineage(
                source_version_ids=(starter.scheme_version_id,),
                created_at=NOW,
                created_by="test.pipeline",
                note="Lightweight runtime vertical slice only.",
            ),
            "content_hash": ZERO_HASH,
        }
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


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
        scheme = _minimal_o1_scheme(application)
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
