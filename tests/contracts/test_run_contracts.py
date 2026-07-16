from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.model_components import ComponentKind, PinnedComponentRef
from pilot_assessment.contracts.project import ArtifactIdRef, SessionRevisionRef
from pilot_assessment.contracts.run import (
    AssessmentRun,
    ExecutableIdentity,
    RunDiagnostic,
    RunDiagnosticSeverity,
    RunEvent,
    RunPreflightReport,
    RunPurpose,
    RunResultEnvelope,
    RunScientificStatus,
    RunSnapshot,
    RunStage,
    RunState,
    TechnicalDisposition,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _pin(kind: ComponentKind, version_id: str, content_hash: str = HASH_A) -> PinnedComponentRef:
    return PinnedComponentRef(kind=kind, version_id=version_id, content_hash=content_hash)


def _session_ref() -> SessionRevisionRef:
    return SessionRevisionRef(
        session_id="session.alpha",
        session_revision_id="session.alpha.rev1",
        bundle_root_hash=HASH_A,
    )


def _scheme_ref() -> PinnedComponentRef:
    return _pin(ComponentKind.ASSESSMENT_SCHEME_VERSION, "scheme.alpha.v1", HASH_B)


def _snapshot() -> RunSnapshot:
    return RunSnapshot(
        run_id="run.alpha",
        purpose=RunPurpose.SOFTWARE_TEST,
        session_revision_ref=_session_ref(),
        scheme_ref=_scheme_ref(),
        locked_component_refs=(_pin(ComponentKind.EVIDENCE_VERSION, "evidence.alpha.v1", HASH_C),),
        locked_source_refs=(_pin(ComponentKind.SOURCE_DESCRIPTOR, "source.x-state", HASH_D),),
        locked_operator_identities=(
            ExecutableIdentity(
                identity_id="operator.mean",
                version="1.0.0",
                content_hash=HASH_A,
            ),
        ),
        engine_identity=ExecutableIdentity(
            identity_id="engine.exact-discrete-bn",
            version="0.1.0",
            content_hash=HASH_B,
        ),
        numeric_runtime_identities=(
            ExecutableIdentity(
                identity_id="runtime.numpy",
                version="2.3.4",
                content_hash=HASH_C,
            ),
        ),
        runtime_parameters_hash=HASH_D,
        preflight_hash=HASH_A,
        snapshot_hash=HASH_B,
    )


def test_preflight_separates_technical_readiness_from_formal_authorization() -> None:
    ready = RunPreflightReport(
        preflight_id="preflight.alpha",
        session_revision_ref=_session_ref(),
        scheme_ref=_scheme_ref(),
        technical_disposition=TechnicalDisposition.READY,
        formal_run_authorized=False,
        synthetic_data=True,
        locked_component_refs=(_scheme_ref(),),
        diagnostics=(
            RunDiagnostic(
                code="SCIENTIFIC_VALIDATION_PENDING",
                severity=RunDiagnosticSeverity.WARNING,
                location="/scheme_ref",
                message="Engineering execution is available; formal use is not authorized.",
                details={},
            ),
        ),
        preflight_hash=HASH_A,
    )

    assert ready.technical_disposition is TechnicalDisposition.READY
    assert ready.formal_run_authorized is False
    with pytest.raises(ValidationError):
        RunPreflightReport.model_validate(
            {
                **ready.model_dump(),
                "formal_run_authorized": True,
            }
        )

    blocked = ready.model_dump()
    blocked.update(
        technical_disposition="blocked",
        synthetic_data=False,
        diagnostics=[
            {
                "code": "MANAGED_SESSION_CHANGED",
                "severity": "error",
                "location": "/session_revision_ref",
                "message": "Managed bytes no longer match the frozen root hash.",
                "details": {},
            }
        ],
    )
    assert RunPreflightReport.model_validate(blocked).technical_disposition is (
        TechnicalDisposition.BLOCKED
    )


def test_snapshot_requires_exact_unique_typed_locks() -> None:
    snapshot = _snapshot()

    assert snapshot.scheme_ref.kind is ComponentKind.ASSESSMENT_SCHEME_VERSION
    duplicate = snapshot.model_dump()
    duplicate["locked_component_refs"] = [
        duplicate["locked_component_refs"][0],
        duplicate["locked_component_refs"][0],
    ]
    with pytest.raises(ValidationError):
        RunSnapshot.model_validate(duplicate)

    wrong_source = snapshot.model_dump()
    wrong_source["locked_source_refs"] = [
        _pin(ComponentKind.EVIDENCE_VERSION, "evidence.wrong", HASH_D).model_dump()
    ]
    with pytest.raises(ValidationError):
        RunSnapshot.model_validate(wrong_source)


def test_assessment_run_enforces_lifecycle_timestamp_shapes() -> None:
    snapshot = _snapshot()
    queued = AssessmentRun(
        run_id=snapshot.run_id,
        snapshot=snapshot,
        state=RunState.QUEUED,
        stage=RunStage.QUEUED,
        progress_sequence=0,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        cancellation_requested_at=None,
    )
    completed = queued.model_dump()
    completed.update(
        state="completed",
        stage="completed",
        progress_sequence=8,
        started_at=NOW + timedelta(seconds=1),
        finished_at=NOW + timedelta(seconds=2),
    )

    assert AssessmentRun.model_validate(completed).state is RunState.COMPLETED
    with pytest.raises(ValidationError):
        AssessmentRun.model_validate({**queued.model_dump(), "started_at": NOW})
    with pytest.raises(ValidationError):
        AssessmentRun.model_validate(
            {
                **completed,
                "finished_at": NOW,
            }
        )


def test_run_event_uses_monotonic_sequence_units_without_hidden_quality_gate() -> None:
    event = RunEvent(
        event_id="run-event.alpha.1",
        run_id="run.alpha",
        sequence=1,
        state=RunState.RUNNING,
        stage=RunStage.EVIDENCE,
        completed_units=2,
        total_units=5,
        message="Computed evidence 2 of 5.",
        occurred_at=NOW,
        details={"evidence_version_id": "evidence.alpha.v1"},
    )

    assert event.completed_units == 2
    with pytest.raises(ValidationError):
        RunEvent.model_validate({**event.model_dump(), "completed_units": 6})
    with pytest.raises(ValidationError):
        RunEvent.model_validate({**event.model_dump(), "quality_gate": 0.8})


def test_result_envelope_uses_exact_artifact_refs_and_scientific_status() -> None:
    evidence_ref = ArtifactIdRef(artifact_id="artifact.evidence", sha256=HASH_A)
    trace_ref = ArtifactIdRef(artifact_id="artifact.evidence-trace", sha256=HASH_B)
    result = RunResultEnvelope(
        result_id="result.alpha",
        run_id="run.alpha",
        snapshot_hash=HASH_C,
        evidence_result_refs=(evidence_ref,),
        evidence_trace_refs=(trace_ref,),
        observation_set_ref=ArtifactIdRef(artifact_id="artifact.observations", sha256=HASH_C),
        posterior_ref=ArtifactIdRef(artifact_id="artifact.posterior", sha256=HASH_D),
        inference_trace_ref=ArtifactIdRef(artifact_id="artifact.inference-trace", sha256=HASH_A),
        reporting_refs=(),
        coverage_refs=(),
        scientific_status=RunScientificStatus.NOT_SUPPORTED,
        result_hash=HASH_B,
    )

    assert result.posterior_ref.sha256 == HASH_D
    duplicate = result.model_dump()
    duplicate["evidence_result_refs"] = [evidence_ref.model_dump(), evidence_ref.model_dump()]
    with pytest.raises(ValidationError):
        RunResultEnvelope.model_validate(duplicate)
