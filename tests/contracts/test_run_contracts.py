from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

import pilot_assessment.contracts as public_contracts
import pilot_assessment.contracts.model_workspace as current
import pilot_assessment.contracts.model_workspace_legacy as legacy
import pilot_assessment.contracts.run as run_contracts
from pilot_assessment.contracts.evidence_recipe import (
    PortCardinality,
    PortType,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import (
    ComponentKind,
    PinnedComponentRef,
    RawModality,
    SourceDescriptor,
    SourceKind,
)
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
from pilot_assessment.contracts.source_provenance import (
    BackendSourceIdentity,
    DependencyManifestIdentity,
    OperatorCatalogIdentity,
    PythonRuntimeIdentity,
    SourceChangeSummary,
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


def _legacy_preflight() -> RunPreflightReport:
    return RunPreflightReport(
        preflight_id="preflight.legacy",
        session_revision_ref=_session_ref(),
        scheme_ref=_scheme_ref(),
        technical_disposition=TechnicalDisposition.READY,
        formal_run_authorized=False,
        synthetic_data=True,
        locked_component_refs=(_scheme_ref(),),
        diagnostics=(),
        preflight_hash=HASH_B,
    )


def _current_raw_node() -> current.ModelNode:
    node_id = "raw.x"
    return current.ModelNode(
        node_id=node_id,
        node_kind=current.ModelNodeKind.RAW_INPUT,
        name="Flight state",
        short_name="X",
        description="Current raw X input.",
        tags=("starter",),
        group=None,
        lifecycle=current.ModelObjectLifecycle.ACTIVE,
        copied_from_node_id=None,
        definition=current.RawInputNodeDefinition(
            family=current.RawInputFamily.X,
            resource_role=current.RawResourceRole.STREAM,
            source_descriptor=SourceDescriptor(
                source_id="source.X",
                kind=SourceKind.RAW_STREAM,
                name="Flight state",
                description="Aligned X stream.",
                declared_type=PortType(
                    value_type="table",
                    cardinality=PortCardinality.ONE,
                    temporal_semantics=TemporalSemantics.SAMPLED,
                    unit=None,
                ),
                raw_modality=RawModality.X,
                source_dependencies=(),
                metadata={},
                content_hash=HASH_A,
            ),
            metadata={},
            help_text="Raw input fields.",
        ),
        global_layout=current.NodeLayout(node_id=node_id, x=0.0, y=0.0),
        semantic_revision=2,
        layout_revision=1,
        technical_status=current.ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=HASH_C,
        layout_hash=HASH_D,
        created_at=NOW,
        updated_at=NOW,
    )


def _current_scheme() -> current.TaskScheme:
    return current.TaskScheme(
        scheme_id="scheme.current",
        name="Current Scheme",
        description="Autosaved current task scheme.",
        tags=("starter",),
        group=None,
        lifecycle=current.ModelObjectLifecycle.ACTIVE,
        copied_from_scheme_id=None,
        explicit_active_node_ids=("raw.x",),
        computed_active_closure=("raw.x",),
        output_node_ids=(),
        task_bindings={},
        layout_overrides=(),
        semantic_revision=3,
        layout_revision=1,
        technical_status=current.ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=HASH_A,
        layout_hash=HASH_B,
        created_at=NOW,
        updated_at=NOW,
    )


def _legacy_raw_node() -> legacy.LegacyModelNodeV010:
    payload = _current_raw_node().model_dump(mode="json")
    payload["contract_version"] = "0.1.0"
    payload["name_en"] = payload.pop("name")
    payload["name_zh"] = None
    payload["short_name_en"] = payload.pop("short_name")
    payload["short_name_zh"] = None
    payload["description_en"] = payload.pop("description")
    payload["description_zh"] = None
    payload["definition"]["help_text_en"] = payload["definition"].pop("help_text")
    payload["definition"]["help_text_zh"] = None
    return legacy.LegacyModelNodeV010.model_validate(payload)


def _legacy_scheme() -> legacy.LegacyTaskSchemeV010:
    payload = _current_scheme().model_dump(mode="json")
    payload["contract_version"] = "0.1.0"
    payload["name_en"] = payload.pop("name")
    payload["name_zh"] = None
    payload["description_en"] = payload.pop("description")
    payload["description_zh"] = None
    return legacy.LegacyTaskSchemeV010.model_validate(payload)


def _backend_source_identity() -> BackendSourceIdentity:
    return BackendSourceIdentity(
        active_source_root="backend/src",
        source_tree_sha256=HASH_A,
        source_file_count=1,
        release_baseline_sha256=HASH_A,
        baseline_available=True,
        locally_modified=False,
        baseline_changes=SourceChangeSummary(),
        pyproject_sha256=HASH_B,
        uv_lock_sha256=HASH_C,
        python_runtime=PythonRuntimeIdentity(
            implementation="CPython",
            version="3.13.5",
            executable_name="python.exe",
            executable_sha256=HASH_D,
            private_runtime=True,
            identity_sha256=HASH_A,
        ),
        dependencies=DependencyManifestIdentity(package_count=1, manifest_sha256=HASH_B),
        operator_catalog=OperatorCatalogIdentity(operator_count=1, catalog_sha256=HASH_C),
        identity_sha256=HASH_D,
    )


def _legacy_current_snapshot() -> run_contracts.CurrentModelRunSnapshot:
    execution = _snapshot()
    return run_contracts.CurrentModelRunSnapshot(
        run_id=execution.run_id,
        purpose=execution.purpose,
        session_revision_ref=execution.session_revision_ref,
        scheme=_legacy_scheme(),
        active_nodes=(_legacy_raw_node(),),
        locked_operator_identities=execution.locked_operator_identities,
        engine_identity=execution.engine_identity,
        numeric_runtime_identities=execution.numeric_runtime_identities,
        runtime_parameters_hash=execution.runtime_parameters_hash,
        preflight_hash=HASH_C,
        execution_snapshot=execution,
        snapshot_hash=HASH_D,
    )


def _current_snapshot_v3() -> run_contracts.CurrentModelRunSnapshotV3:
    execution = _snapshot()
    return run_contracts.CurrentModelRunSnapshotV3(
        run_id=execution.run_id,
        purpose=execution.purpose,
        session_revision_ref=execution.session_revision_ref,
        scheme=_current_scheme(),
        active_nodes=(_current_raw_node(),),
        locked_operator_identities=execution.locked_operator_identities,
        engine_identity=execution.engine_identity,
        numeric_runtime_identities=execution.numeric_runtime_identities,
        runtime_parameters_hash=execution.runtime_parameters_hash,
        preflight_hash=HASH_C,
        execution_snapshot=execution,
        snapshot_hash=HASH_D,
        backend_source_identity=_backend_source_identity(),
        source_snapshot_ref=ArtifactIdRef(artifact_id=f"artifact.{HASH_A}", sha256=HASH_A),
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


def test_current_preflight_locks_current_scheme_and_nodes_without_changing_legacy() -> None:
    node = _current_raw_node()
    execution = _legacy_preflight()
    report = run_contracts.CurrentModelRunPreflightReport(
        preflight_id="preflight.current",
        session_revision_ref=_session_ref(),
        scheme_id="scheme.current",
        scheme_semantic_revision=3,
        scheme_content_hash=HASH_A,
        active_node_refs=(
            run_contracts.ModelNodeSnapshotRef(
                node_id=node.node_id,
                node_kind=node.node_kind,
                semantic_revision=node.semantic_revision,
                content_hash=node.content_hash,
            ),
        ),
        technical_disposition=TechnicalDisposition.READY,
        formal_run_authorized=False,
        synthetic_data=True,
        diagnostics=(),
        execution_preflight=execution,
        preflight_hash=HASH_C,
    )

    assert (
        run_contracts.CurrentModelRunPreflightReport.model_validate_json(report.model_dump_json())
        == report
    )
    assert report.execution_preflight is not None
    assert report.execution_preflight.contract_version == "0.1.0"

    duplicate = report.model_dump(mode="json")
    duplicate["active_node_refs"].append(duplicate["active_node_refs"][0])
    with pytest.raises(ValidationError, match="active node"):
        run_contracts.CurrentModelRunPreflightReport.model_validate(duplicate)

    missing_execution = report.model_dump(mode="json")
    missing_execution["execution_preflight"] = None
    with pytest.raises(ValidationError, match="ready"):
        run_contracts.CurrentModelRunPreflightReport.model_validate(missing_execution)


def test_current_snapshot_freezes_complete_nodes_and_legacy_execution_snapshot() -> None:
    snapshot = _legacy_current_snapshot()
    assert isinstance(snapshot, run_contracts.CurrentModelRunSnapshot)

    assert (
        run_contracts.CurrentModelRunSnapshot.model_validate_json(snapshot.model_dump_json())
        == snapshot
    )
    assert snapshot.execution_snapshot.contract_version == "0.1.0"
    assert snapshot.active_nodes[0].content_hash == HASH_C

    missing_active_node = snapshot.model_dump(mode="json")
    missing_active_node["active_nodes"] = []
    with pytest.raises(ValidationError, match="active closure"):
        run_contracts.CurrentModelRunSnapshot.model_validate(missing_active_node)

    wrong_execution_run = snapshot.model_dump(mode="json")
    wrong_execution_run["execution_snapshot"]["run_id"] = "run.other"
    with pytest.raises(ValidationError, match="execution snapshot"):
        run_contracts.CurrentModelRunSnapshot.model_validate(wrong_execution_run)


def test_assessment_run_v2_uses_current_snapshot_and_preserves_legacy_contract() -> None:
    snapshot = _legacy_current_snapshot()
    run = run_contracts.AssessmentRunV2(
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

    assert run.contract_version == "0.2.0"
    assert run_contracts.AssessmentRunV2.model_validate_json(run.model_dump_json()) == run
    assert (
        AssessmentRun(
            run_id="run.alpha",
            snapshot=_snapshot(),
            state=RunState.QUEUED,
            stage=RunStage.QUEUED,
            progress_sequence=0,
            requested_at=NOW,
            started_at=None,
            finished_at=None,
            cancellation_requested_at=None,
        ).contract_version
        == "0.1.0"
    )

    mismatch = run.model_dump(mode="json")
    mismatch["run_id"] = "run.other"
    with pytest.raises(ValidationError, match="run_id"):
        run_contracts.AssessmentRunV2.model_validate(mismatch)

    non_utc = run.model_dump(mode="python")
    non_utc["requested_at"] = NOW.astimezone(timezone(timedelta(hours=1)))
    with pytest.raises(ValidationError, match="UTC"):
        run_contracts.AssessmentRunV2.model_validate(non_utc)


def test_historical_v2_run_bytes_remain_readable_and_new_run_uses_v3_snapshot() -> None:
    assert public_contracts.AssessmentRunV3 is run_contracts.AssessmentRunV3
    assert public_contracts.CurrentModelRunSnapshotV3 is run_contracts.CurrentModelRunSnapshotV3
    legacy_snapshot_payload = _legacy_current_snapshot().model_dump(mode="python")
    legacy_snapshot_payload["contract_version"] = "0.2.0"
    legacy_snapshot = run_contracts.CurrentModelRunSnapshotV2(
        **legacy_snapshot_payload,
        backend_source_identity=_backend_source_identity(),
        source_snapshot_ref=ArtifactIdRef(artifact_id=f"artifact.{HASH_A}", sha256=HASH_A),
    )
    legacy_run = run_contracts.AssessmentRunV2(
        run_id=legacy_snapshot.run_id,
        snapshot=legacy_snapshot,
        state=RunState.QUEUED,
        stage=RunStage.QUEUED,
        progress_sequence=0,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        cancellation_requested_at=None,
    )
    historical_bytes = legacy_run.model_dump_json().encode("utf-8")
    historical_digest = sha256(historical_bytes).hexdigest()

    restored = run_contracts.AssessmentRunV2.model_validate_json(historical_bytes)

    assert restored.model_dump_json().encode("utf-8") == historical_bytes
    assert sha256(restored.model_dump_json().encode("utf-8")).hexdigest() == historical_digest
    assert restored.snapshot.snapshot_hash == HASH_D

    current_snapshot = _current_snapshot_v3()
    current_run = run_contracts.AssessmentRunV3(
        run_id=current_snapshot.run_id,
        snapshot=current_snapshot,
        state=RunState.QUEUED,
        stage=RunStage.QUEUED,
        progress_sequence=0,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        cancellation_requested_at=None,
    )
    current_payload = current_run.model_dump(mode="json")
    assert current_run.contract_version == "0.3.0"
    assert current_payload["snapshot"]["contract_version"] == "0.3.0"
    assert current_payload["snapshot"]["scheme"]["contract_version"] == "0.2.0"
    assert current_payload["snapshot"]["active_nodes"][0]["name"] == "Flight state"
    assert "name_en" not in current_payload["snapshot"]["active_nodes"][0]
