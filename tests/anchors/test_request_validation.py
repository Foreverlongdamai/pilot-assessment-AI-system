from __future__ import annotations

from dataclasses import replace
from inspect import signature
from typing import cast

import polars as pl
import pytest

from pilot_assessment.anchors.models import (
    AnchorEvaluationRequest,
    AnchorRequestValidationError,
    ResolvedReference,
    ResolvedReferenceSet,
)
from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AoiDefinition,
    AoiGeometryKind,
    BaselineChannelBinding,
    BaselineDefinition,
    BaselineModality,
    DynamicAoiSource,
    ReferenceAlignmentContract,
    ReferenceFieldContract,
    ReferenceSessionIdentity,
    ReferenceTableContract,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedReferenceDescriptor,
    ScientificValidationStatus,
    ScorerPolicy,
    SemanticApplicabilityStatus,
    SemanticPhase,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.ingestion import StreamReadiness
from pilot_assessment.contracts.session import CORE_MODALITIES, CoreModality, StreamStatus
from pilot_assessment.contracts.synchronization import (
    AnnotationSynchronizationResult,
    BaselineInterval,
    ClockMappingSummary,
    PhaseInterval,
    PointTemporalArtifactMetrics,
    SessionWindow,
    StreamSynchronizationResult,
    SynchronizationDisposition,
    SynchronizationItemStatus,
    SynchronizationPolicy,
    SynchronizationReport,
    TaskReferenceSynchronizationResult,
)
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedSession,
    AlignedStreamView,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
END_NS = 10_000_000_000


def _clock(method: str = "affine-v1", clock_id: str = "sim-clock") -> ClockMappingSummary:
    return ClockMappingSummary(
        clock_id=clock_id,
        method=method,
        scale=1.0,
        offset_ns=0,
        drift_ppm=0.0,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
        declaration_consistent=True,
    )


def _point_metrics(
    role: str,
    source_schema: str,
    aligned_schema: str,
) -> PointTemporalArtifactMetrics:
    return PointTemporalArtifactMetrics(
        artifact_role=role,
        binding_mode="point",
        source_schema_id=source_schema,
        aligned_schema_id=aligned_schema,
        total_rows=1,
        in_session_rows=1,
        before_session_rows=0,
        after_session_rows=0,
        first_mapped_t_ns=0,
        last_mapped_t_ns=0,
        in_session_start_t_ns=0,
        in_session_end_t_ns=0,
        in_session_span_ns=0,
        session_span_ratio=0.0,
    )


def _optional_state(
    modality: str, status: SynchronizationItemStatus
) -> StreamSynchronizationResult:
    declared, readiness = {
        SynchronizationItemStatus.NOT_ATTEMPTED: (
            StreamStatus.EXPORT_PENDING,
            StreamReadiness.UNAVAILABLE,
        ),
        SynchronizationItemStatus.UNAVAILABLE: (
            StreamStatus.MISSING,
            StreamReadiness.UNAVAILABLE,
        ),
        SynchronizationItemStatus.INVALID: (
            StreamStatus.INVALID,
            StreamReadiness.INVALID,
        ),
        SynchronizationItemStatus.UNSUPPORTED: (
            StreamStatus.PRESENT,
            StreamReadiness.UNSUPPORTED,
        ),
        SynchronizationItemStatus.NOT_APPLICABLE: (
            StreamStatus.NOT_APPLICABLE,
            StreamReadiness.NOT_APPLICABLE,
        ),
    }[status]
    return StreamSynchronizationResult(
        modality=modality,
        declared_status=declared,
        required_for_import=False,
        input_readiness=readiness,
        synchronization_status=status,
    )


def _x_result() -> StreamSynchronizationResult:
    return StreamSynchronizationResult(
        modality="X",
        declared_status=StreamStatus.PRESENT,
        required_for_import=True,
        input_readiness=StreamReadiness.READY,
        synchronization_status=SynchronizationItemStatus.ALIGNED,
        clock=_clock(),
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        artifacts={"samples": _point_metrics("samples", "x-raw-v0.1", "x-samples-aligned-v0.1")},
    )


def _report(
    *,
    optional_status: SynchronizationItemStatus = SynchronizationItemStatus.NOT_ATTEMPTED,
    task_reference: TaskReferenceSynchronizationResult | None = None,
) -> SynchronizationReport:
    stream_results = {
        modality: (_x_result() if modality == "X" else _optional_state(modality, optional_status))
        for modality in sorted(CORE_MODALITIES)
    }
    degraded = optional_status is not SynchronizationItemStatus.NOT_APPLICABLE
    return SynchronizationReport(
        contract_version="0.1.0",
        validation_scope="native_rate_session_time_alignment_v1",
        session_id="session-1",
        source_snapshot_fingerprint=SHA_A,
        source_classification="captured-simulator",
        synthetic_provenance=None,
        policy=SynchronizationPolicy(),
        policy_fingerprint=SHA_F,
        binding_catalog_fingerprint=SHA_E,
        session_window=SessionWindow(end_t_ns=END_NS, source="master-clock-x-mapped-coverage-v1"),
        disposition=(
            SynchronizationDisposition.READY_PARTIAL
            if degraded
            else SynchronizationDisposition.READY
        ),
        can_continue_to_anchor_availability=True,
        formal_run_authorized=False,
        stream_results=stream_results,
        task_reference_result=task_reference,
        annotation_result=AnnotationSynchronizationResult(
            synchronization_status=SynchronizationItemStatus.ALIGNED,
            revision="annotations-1",
            phase_schema_id="phases-v0.1",
            event_schema_id="events-v0.1",
            baseline_schema_id="baselines-v0.1",
            phase_count=1,
            event_count=0,
            baseline_count=0,
            synthetic_semantics_unvalidated=False,
        ),
        synchronization_fingerprint=SHA_B,
    )


def _x_table(*, nullable_value: bool = False) -> pl.DataFrame:
    value = None if nullable_value else 1.0
    return pl.DataFrame(
        {
            "t_ns": pl.Series("t_ns", [0], dtype=pl.Int64),
            "in_session": pl.Series("in_session", [True], dtype=pl.Boolean),
            "value": pl.Series("value", [value], dtype=pl.Float64),
        }
    )


def _x_view(table: pl.DataFrame | None = None) -> AlignedStreamView:
    return AlignedStreamView(
        modality="X",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        clock_id="sim-clock",
        tables={"samples": table if table is not None else _x_table()},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/x.parquet": SHA_A},
    )


def _session(
    *,
    streams: dict[str, AlignedStreamView] | None = None,
    task_reference: AlignedStreamView | None = None,
) -> AlignedSession:
    return AlignedSession(
        session_id="session-1",
        window=SessionWindow(end_t_ns=END_NS, source="master-clock-x-mapped-coverage-v1"),
        streams={"X": _x_view()} if streams is None else streams,
        context={"flight_mode": "hover"},
        annotations=AlignedAnnotations(
            revision="annotations-1",
            phases=(PhaseInterval(phase_id="phase-1", start_t_ns=0, end_t_ns=END_NS),),
            events=(),
            baseline_intervals=(),
            source_schema_ids={
                "phases": "phases-v0.1",
                "events": "events-v0.1",
                "baselines": "baselines-v0.1",
            },
            synthetic_semantics_unvalidated=False,
        ),
        task_reference=task_reference,
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
    )


def _semantic(
    *,
    aois: tuple[AoiDefinition, ...] = (),
) -> SessionSemanticSnapshot:
    return SessionSemanticSnapshot(
        session_id="session-1",
        task_profile_id="profile-1",
        scenario_id="scenario-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        annotation_revision="annotations-1",
        synthetic_semantics_unvalidated=False,
        session_end_t_ns=END_NS,
        phases=(
            SemanticPhase(
                phase_id="phase-1",
                phase_type="hover",
                start_t_ns=0,
                end_t_ns=END_NS,
                include_session_terminal_point=True,
            ),
        ),
        events=(),
        aois=aois,
        control_mappings=(),
        baselines=(),
        targets=(),
        envelopes=(),
        applicability=(
            {
                "anchor_id": "O1",
                "status": "applicable",
                "phase_ids": ("phase-1",),
            },
        ),
        semantic_snapshot_fingerprint=SHA_C,
    )


def _input_contract(
    modality: CoreModality = CoreModality.X,
    *,
    table_role: str = "samples",
    table_schema: str | None = None,
    frame: str = "world",
    fields: tuple[ResolvedInputFieldContract, ...] | None = None,
) -> ResolvedInputTableContract:
    default_fields = (
        ResolvedInputFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
        ResolvedInputFieldContract(
            field_name="in_session", dtype_id="bool", unit="bool", nullable=False
        ),
        ResolvedInputFieldContract(field_name="value", dtype_id="f64", unit="m", nullable=False),
    )
    return ResolvedInputTableContract(
        modality=modality,
        table_role=table_role,
        stream_aligned_schema_id=f"{modality.value.lower()}-aligned-v0.1",
        table_aligned_schema_id=table_schema or f"{modality.value.lower()}-samples-aligned-v0.1",
        coordinate_frame_id=frame,
        fields=fields or default_fields,
    )


def _entry(
    *,
    required_streams: tuple[CoreModality, ...] = (CoreModality.X,),
    required_reference_ids: tuple[str, ...] = (),
) -> AnchorExecutionEntry:
    return AnchorExecutionEntry(
        anchor_id="O1",
        definition_version="0.1.0",
        lifecycle="active",
        canonical_order=0,
        plugin_id="o1-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        definition_fingerprint=SHA_A,
        implementation_digest=SHA_B,
        parameter_schema_id="o1-parameters-v0.1",
        parameters={"gain": 1.0},
        parameter_hash=SHA_C,
        required_streams=required_streams,
        required_context_paths=("context.flight_mode",),
        required_semantic_paths=("semantic.phases",),
        required_reference_ids=required_reference_ids,
        applicability=SemanticApplicabilityStatus.APPLICABLE,
        phase_scope=("phase-1",),
        event_scope=(),
        dependencies=(),
        measurement_schema_id="anchor-measurement-v0.1",
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=(),
        temporal_recipe={"scope": "phase"},
        scorer_policy=ScorerPolicy(
            scorer_id="dau",
            scorer_version="0.1.0",
            policy_schema_id="dau-v0.1",
            parameters={"desired": 1.0, "adequate": 2.0},
            policy_hash=SHA_D,
        ),
    )


def _plan(
    *,
    entry: AnchorExecutionEntry | None = None,
    contracts: tuple[ResolvedInputTableContract, ...] | None = None,
    reference_set_fingerprint: str = SHA_D,
) -> AnchorExecutionPlan:
    entry = entry or _entry()
    return AnchorExecutionPlan(
        plan_id="plan-1",
        model_profile_id="profile-1",
        scientific_validation_status=ScientificValidationStatus.ENGINEERING_DEFAULT,
        catalog_fingerprint=SHA_E,
        registry_fingerprint=SHA_F,
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        semantic_snapshot_fingerprint=SHA_C,
        reference_set_fingerprint=reference_set_fingerprint,
        entries=(entry,),
        input_table_contracts=contracts or (_input_contract(),),
        algorithm_profiles=(),
        preprocessing_recipes=(),
        parameter_fingerprint=SHA_A,
        plan_fingerprint=SHA_B,
    )


def _resolved_empty() -> ResolvedReferenceSet:
    return ResolvedReferenceSet(
        session_identity=ReferenceSessionIdentity(
            session_id="session-1",
            source_snapshot_fingerprint=SHA_A,
            synchronization_fingerprint=SHA_B,
            session_end_t_ns=END_NS,
        ),
        entries={},
        reference_set_fingerprint=SHA_D,
    )


def _request_parts() -> dict[str, object]:
    return {
        "aligned_session": _session(),
        "synchronization_report": _report(),
        "session_semantic_snapshot": _semantic(),
        "execution_plan": _plan(),
        "resolved_references": _resolved_empty(),
    }


def _assert_code(code: str, **parts: object) -> None:
    with pytest.raises(AnchorRequestValidationError) as caught:
        AnchorEvaluationRequest(**parts)  # type: ignore[arg-type]
    assert caught.value.code == code


def test_valid_request_is_frozen_and_has_no_candidate_or_test_bypass() -> None:
    request = AnchorEvaluationRequest(**_request_parts())  # type: ignore[arg-type]
    assert request.aligned_session.session_id == "session-1"
    assert set(signature(AnchorEvaluationRequest).parameters) == {
        "aligned_session",
        "synchronization_report",
        "session_semantic_snapshot",
        "execution_plan",
        "resolved_references",
    }
    with pytest.raises((AttributeError, TypeError)):
        request.execution_plan = _plan()  # type: ignore[misc]


def test_model_profile_and_session_task_profile_are_independent_namespaces() -> None:
    parts = _request_parts()
    parts["execution_plan"] = _plan().model_copy(
        update={"model_profile_id": "reference-model-v0.1"}
    )
    request = AnchorEvaluationRequest(**parts)  # type: ignore[arg-type]
    assert request.execution_plan.model_profile_id == "reference-model-v0.1"
    assert request.session_semantic_snapshot.task_profile_id == "profile-1"


def test_session_gate_rejects_both_report_view_inventory_directions() -> None:
    parts = _request_parts()
    parts["aligned_session"] = _session(streams={})
    _assert_code("request_session_mismatch", **parts)

    parts = _request_parts()
    u_view = replace(_x_view(), modality="U")
    parts["aligned_session"] = _session(streams={"X": _x_view(), "U": u_view})
    _assert_code("request_session_mismatch", **parts)

    parts = _request_parts()
    parts["aligned_session"] = replace(_session(), session_id="other")
    _assert_code("request_session_mismatch", **parts)


def test_blocked_or_missing_m3_outcome_never_constructs_a_request() -> None:
    parts = _request_parts()
    blocked = _report().model_copy(
        update={
            "disposition": SynchronizationDisposition.BLOCKED,
            "can_continue_to_anchor_availability": False,
            "session_window": None,
        }
    )
    parts["synchronization_report"] = blocked
    parts["aligned_session"] = cast(AlignedSession, None)
    _assert_code("request_session_mismatch", **parts)


def test_annotation_input_table_and_applicability_are_semantic_relations() -> None:
    parts = _request_parts()
    parts["aligned_session"] = replace(
        _session(), annotations=replace(_session().annotations, revision="other")
    )
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    bad_view = _x_view(_x_table(nullable_value=True))
    parts["aligned_session"] = _session(streams={"X": bad_view})
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    parts["session_semantic_snapshot"] = _semantic().model_copy(update={"applicability": ()})
    _assert_code("request_semantic_identity_mismatch", **parts)


def test_annotation_schema_and_complete_baseline_identity_are_exact() -> None:
    parts = _request_parts()
    parts["aligned_session"] = replace(
        _session(),
        annotations=replace(
            _session().annotations,
            source_schema_ids={
                "phases": "wrong-phases-v0.1",
                "events": "events-v0.1",
                "baselines": "baselines-v0.1",
            },
        ),
    )
    _assert_code("request_semantic_identity_mismatch", **parts)

    baseline = BaselineInterval(
        interval_id="baseline-1",
        start_t_ns=0,
        end_t_ns=1_000_000_000,
        condition="rest",
        valid=True,
    )
    semantic_baseline = BaselineDefinition(
        baseline_id="baseline-1",
        start_t_ns=0,
        end_t_ns=1_000_000_000,
        channel_bindings=(
            BaselineChannelBinding(modality=BaselineModality.ECG, channel_ids=("lead-1",)),
        ),
        condition_id="different-condition",
        annotation_valid=True,
    )
    parts = _request_parts()
    parts["aligned_session"] = replace(
        _session(),
        annotations=replace(_session().annotations, baseline_intervals=(baseline,)),
    )
    parts["synchronization_report"] = _report().model_copy(
        update={
            "annotation_result": _report().annotation_result.model_copy(
                update={"baseline_count": 1}
            )
        }
    )
    parts["session_semantic_snapshot"] = _semantic().model_copy(
        update={"baselines": (semantic_baseline,)}
    )
    _assert_code("request_semantic_identity_mismatch", **parts)


@pytest.mark.parametrize(
    "semantic_applicability",
    [
        (AnchorApplicability(anchor_id="O1", status="not_applicable", reason="not-in-scenario"),),
        (AnchorApplicability(anchor_id="O1", status="applicable", phase_ids=()),),
    ],
)
def test_applicability_status_and_scopes_match_plan_exactly(
    semantic_applicability: tuple[AnchorApplicability, ...],
) -> None:
    parts = _request_parts()
    parts["session_semantic_snapshot"] = _semantic().model_copy(
        update={"applicability": semantic_applicability}
    )
    _assert_code("request_semantic_identity_mismatch", **parts)


def test_malformed_runtime_objects_fail_with_stable_request_codes() -> None:
    parts = _request_parts()
    parts["execution_plan"] = object()
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    malformed_view = replace(_x_view(), tables={"samples": object()})  # type: ignore[dict-item]
    parts["aligned_session"] = _session(streams={"X": malformed_view})
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    parts["aligned_session"] = replace(_session(), annotations=object())  # type: ignore[arg-type]
    _assert_code("request_semantic_identity_mismatch", **parts)


@pytest.mark.parametrize(
    "status",
    [
        SynchronizationItemStatus.NOT_ATTEMPTED,
        SynchronizationItemStatus.UNAVAILABLE,
        SynchronizationItemStatus.INVALID,
        SynchronizationItemStatus.UNSUPPORTED,
        SynchronizationItemStatus.NOT_APPLICABLE,
    ],
)
def test_optional_non_aligned_required_stream_is_not_a_request_error(
    status: SynchronizationItemStatus,
) -> None:
    i_contract = _input_contract(
        CoreModality.SCENE,
        table_schema="i-samples-aligned-v0.1",
    )
    entry = _entry(required_streams=(CoreModality.SCENE, CoreModality.X))
    plan = _plan(
        entry=entry,
        contracts=tuple(
            sorted((i_contract, _input_contract()), key=lambda item: item.modality.value)
        ),
    )
    request = AnchorEvaluationRequest(
        aligned_session=_session(),
        synchronization_report=_report(optional_status=status),
        session_semantic_snapshot=_semantic(),
        execution_plan=plan,
        resolved_references=_resolved_empty(),
    )
    assert request.synchronization_report.stream_results["I"].synchronization_status is status


def _dynamic_i_contract() -> ResolvedInputTableContract:
    fields = (
        ResolvedInputFieldContract(
            field_name="frame-id", dtype_id="i64", unit="index", nullable=False
        ),
        ResolvedInputFieldContract(field_name="aoi-id", dtype_id="utf8", unit="id", nullable=False),
        *tuple(
            ResolvedInputFieldContract(field_name=name, dtype_id="f64", unit="px", nullable=False)
            for name in ("x-min", "y-min", "x-max", "y-max")
        ),
    )
    return _input_contract(
        CoreModality.SCENE,
        table_role="aoi-geometry",
        table_schema="i-aoi-aligned-v0.1",
        frame="screen",
        fields=fields,
    )


def _dynamic_aois(
    frame: str = "screen",
    geometry_fields: tuple[str, ...] = ("x-min", "y-min", "x-max", "y-max"),
) -> tuple[AoiDefinition, ...]:
    return (
        AoiDefinition(
            aoi_id="aoi-dynamic",
            taxonomy_id="tax-1",
            role="display",
            geometry_kind=AoiGeometryKind.DYNAMIC_2D,
            priority=1,
            role_weight=1.0,
            off_task=False,
            dynamic_source=DynamicAoiSource(
                table_role="aoi-geometry",
                aligned_schema_id="i-aoi-aligned-v0.1",
                coordinate_frame_id=frame,
                unit="px",
                frame_id_field="frame-id",
                aoi_id_field="aoi-id",
                geometry_field_ids=geometry_fields,
            ),
        ),
        AoiDefinition(
            aoi_id="aoi-other",
            taxonomy_id="tax-1",
            role="other_scene",
            geometry_kind=AoiGeometryKind.CATCH_ALL,
            priority=0,
            role_weight=0.0,
            off_task=True,
        ),
    )


def test_dynamic_aoi_binds_plan_contract_even_when_i_is_optional_non_aligned() -> None:
    entry = _entry(required_streams=(CoreModality.SCENE, CoreModality.X))
    contracts = tuple(
        sorted((_dynamic_i_contract(), _input_contract()), key=lambda item: item.modality.value)
    )
    request = AnchorEvaluationRequest(
        aligned_session=_session(),
        synchronization_report=_report(),
        session_semantic_snapshot=_semantic(aois=_dynamic_aois()),
        execution_plan=_plan(entry=entry, contracts=contracts),
        resolved_references=_resolved_empty(),
    )
    assert request.session_semantic_snapshot.aois[0].dynamic_source is not None

    parts = _request_parts()
    parts.update(
        {
            "session_semantic_snapshot": _semantic(aois=_dynamic_aois("body")),
            "execution_plan": _plan(entry=entry, contracts=contracts),
        }
    )
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    parts.update(
        {
            "session_semantic_snapshot": _semantic(
                aois=_dynamic_aois(geometry_fields=("y-min", "x-min", "x-max", "y-max"))
            ),
            "execution_plan": _plan(entry=entry, contracts=contracts),
        }
    )
    _assert_code("request_semantic_identity_mismatch", **parts)


def _reference_contract() -> ReferenceTableContract:
    return ReferenceTableContract(
        table_role="commanded-path",
        coordinate_frame_id="world",
        stable_row_id_field="row-id",
        fields=(
            ReferenceFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
            ReferenceFieldContract(
                field_name="in_session", dtype_id="bool", unit="bool", nullable=False
            ),
            ReferenceFieldContract(
                field_name="row-id", dtype_id="i64", unit="index", nullable=False
            ),
            ReferenceFieldContract(field_name="x", dtype_id="f64", unit="m", nullable=False),
        ),
        canonical_order_keys=("t_ns", "row-id"),
        table_contract_fingerprint=SHA_A,
    )


def _reference_descriptor(
    *,
    present: bool,
    source_kind: str = "bundle",
) -> ResolvedReferenceDescriptor:
    return ResolvedReferenceDescriptor.model_validate(
        {
            "reference_id": "reference-1",
            "resolution_status": "present" if present else "absent",
            "source_kind": source_kind,
            "source_schema_id": "reference-raw-v0.1",
            "aligned_schema_id": "reference-aligned-v0.1",
            "clock_id": "reference-clock",
            "alignment_contract": ReferenceAlignmentContract(
                mapping_method="affine-v1",
                mapping_policy_id="native-alignment-engineering-v0.1",
                source_clock_id="reference-clock",
                scale=1.0,
                offset_ns=0,
                declared_drift_ppm=0.0,
            ),
            "table_contract": _reference_contract(),
            "resource_checksums": (
                [{"path": "references/commanded.parquet", "checksum": SHA_E}] if present else []
            ),
            "resource_fingerprint": SHA_A if present else None,
            "aligned_content_fingerprint": SHA_B if present else None,
            "alignment_fingerprint": SHA_C if present else None,
            "absence_reason": None if present else "not-provided",
        }
    )


def _reference_view() -> AlignedStreamView:
    return AlignedStreamView(
        modality="task_reference",
        source_schema_id="reference-raw-v0.1",
        aligned_schema_id="reference-aligned-v0.1",
        clock_id="reference-clock",
        tables={
            "commanded-path": pl.DataFrame(
                {
                    "t_ns": pl.Series("t_ns", [0], dtype=pl.Int64),
                    "in_session": pl.Series("in_session", [True], dtype=pl.Boolean),
                    "row-id": pl.Series("row-id", [0], dtype=pl.Int64),
                    "x": pl.Series("x", [0.0], dtype=pl.Float64),
                }
            )
        },
        json_artifacts={},
        file_artifacts={},
        source_checksums={"references/commanded.parquet": SHA_E},
    )


def _resolved_reference(
    *,
    present: bool,
    source_kind: str = "bundle",
) -> ResolvedReferenceSet:
    descriptor = _reference_descriptor(present=present, source_kind=source_kind)
    view = _reference_view() if present else None
    return ResolvedReferenceSet(
        session_identity=ReferenceSessionIdentity(
            session_id="session-1",
            source_snapshot_fingerprint=SHA_A,
            synchronization_fingerprint=SHA_B,
            session_end_t_ns=END_NS,
        ),
        entries={
            descriptor.reference_id: ResolvedReference(descriptor=descriptor, aligned_view=view)
        },
        reference_set_fingerprint=SHA_D,
    )


def _plan_requiring_reference() -> AnchorExecutionPlan:
    return _plan(entry=_entry(required_reference_ids=("reference-1",)))


def test_reference_inventory_precedes_provenance_and_absent_is_valid() -> None:
    parts = _request_parts()
    parts["execution_plan"] = _plan_requiring_reference()
    _assert_code("request_reference_inventory_mismatch", **parts)

    request = AnchorEvaluationRequest(
        aligned_session=_session(),
        synchronization_report=_report(),
        session_semantic_snapshot=_semantic(),
        execution_plan=_plan_requiring_reference(),
        resolved_references=_resolved_reference(present=False),
    )
    assert request.resolved_references.entries["reference-1"].aligned_view is None


def test_bundle_present_and_model_bundle_deferred_provenance() -> None:
    bundle_result = TaskReferenceSynchronizationResult(
        reference_id="reference-1",
        source="bundle",
        declared_status=StreamStatus.PRESENT,
        required_for_import=True,
        input_readiness=StreamReadiness.READY,
        synchronization_status=SynchronizationItemStatus.ALIGNED,
        clock=_clock("affine-v1", "reference-clock"),
        source_schema_id="reference-raw-v0.1",
        aligned_schema_id="reference-aligned-v0.1",
        source_checksums={"references/commanded.parquet": SHA_E},
        artifacts={
            "commanded-path": _point_metrics(
                "commanded-path",
                "reference-raw-v0.1",
                "reference-aligned-v0.1",
            )
        },
    )
    bundle_refs = _resolved_reference(present=True)
    bundle_view = bundle_refs.entries["reference-1"].aligned_view
    assert bundle_view is not None
    bundle_request = AnchorEvaluationRequest(
        aligned_session=_session(task_reference=bundle_view),
        synchronization_report=_report(task_reference=bundle_result),
        session_semantic_snapshot=_semantic(),
        execution_plan=_plan_requiring_reference(),
        resolved_references=bundle_refs,
    )
    assert bundle_request.resolved_references.entries["reference-1"].aligned_view is bundle_view

    deferred = TaskReferenceSynchronizationResult(
        reference_id="reference-1",
        source="model_bundle",
        synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
    )
    model_request = AnchorEvaluationRequest(
        aligned_session=_session(),
        synchronization_report=_report(task_reference=deferred),
        session_semantic_snapshot=_semantic(),
        execution_plan=_plan_requiring_reference(),
        resolved_references=_resolved_reference(present=True, source_kind="model_bundle"),
    )
    assert (
        model_request.synchronization_report.task_reference_result.synchronization_status
        is SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
    )


def test_reference_provenance_and_final_fingerprint_codes_are_stable() -> None:
    parts = _request_parts()
    parts["execution_plan"] = _plan_requiring_reference()
    parts["resolved_references"] = _resolved_reference(present=False)
    wrong_record = TaskReferenceSynchronizationResult(
        reference_id="other-reference",
        source="model_bundle",
        synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
    )
    parts["synchronization_report"] = _report(task_reference=wrong_record)
    _assert_code("request_reference_provenance_mismatch", **parts)

    parts = _request_parts()
    parts["execution_plan"] = _plan().model_copy(update={"semantic_snapshot_fingerprint": SHA_F})
    _assert_code("request_fingerprint_mismatch", **parts)


def test_semantic_and_provenance_errors_precede_stale_fingerprints() -> None:
    parts = _request_parts()
    parts["session_semantic_snapshot"] = _semantic().model_copy(update={"applicability": ()})
    parts["execution_plan"] = _plan().model_copy(update={"semantic_snapshot_fingerprint": SHA_F})
    _assert_code("request_semantic_identity_mismatch", **parts)

    parts = _request_parts()
    parts["execution_plan"] = _plan_requiring_reference().model_copy(
        update={"semantic_snapshot_fingerprint": SHA_F}
    )
    parts["resolved_references"] = _resolved_reference(present=False)
    parts["synchronization_report"] = _report(
        task_reference=TaskReferenceSynchronizationResult(
            reference_id="other-reference",
            source="model_bundle",
            synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
        )
    )
    _assert_code("request_reference_provenance_mismatch", **parts)
