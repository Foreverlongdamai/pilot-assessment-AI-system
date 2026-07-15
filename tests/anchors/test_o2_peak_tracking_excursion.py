from __future__ import annotations

import math
import statistics
from dataclasses import replace

import polars as pl
import pytest

from pilot_assessment.anchors.artifacts import InMemoryDerivedArtifactSink
from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.fingerprint import (
    aligned_reference_content_fingerprint,
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    reference_alignment_fingerprint,
    reference_resource_fingerprint,
    reference_table_contract_fingerprint,
    resolved_reference_set_fingerprint,
    session_semantic_snapshot_fingerprint,
)
from pilot_assessment.anchors.models import (
    AnchorEvaluationRequest,
    ResolvedReference,
    ResolvedReferenceSet,
)
from pilot_assessment.anchors.registry import PluginRegistry
from pilot_assessment.anchors.scoring import compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AnchorExecutionEntry,
    ReferenceAlignmentContract,
    ReferenceFieldContract,
    ReferenceSessionIdentity,
    ReferenceTableContract,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
    SemanticPhase,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.anchor_v2 import AnchorCalculationStatusV2
from pilot_assessment.contracts.synchronization import (
    PhaseInterval,
    PointTemporalArtifactMetrics,
    SynchronizationItemStatus,
    TaskReferenceSynchronizationResult,
)
from pilot_assessment.synchronization.models import AlignedAnnotations, AlignedStreamView
from tests.anchors.test_request_validation import END_NS, _report, _session
from tests.anchors.test_service import _canonical_plan, _policy
from tests.m4_support.micro_inputs import tiny_reference_table, tiny_x_table

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
METERS_PER_FOOT = 0.3048


def _definition():
    from pilot_assessment.anchors.plugins.o2_peak_tracking_excursion import create_plugin

    return create_plugin().definition()


def _x_contract(*, frame: str = "world", unit: str = "m") -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="X",
        table_role="samples",
        stream_aligned_schema_id="x-aligned-v0.1",
        table_aligned_schema_id="x-samples-aligned-v0.1",
        coordinate_frame_id=frame,
        fields=(
            ResolvedInputFieldContract(
                field_name="source_row_index", dtype_id="u64", unit="index", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="t_ns", dtype_id="i64", unit="ns", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="in_session", dtype_id="bool", unit="bool", nullable=False
            ),
            *tuple(
                ResolvedInputFieldContract(
                    field_name=axis, dtype_id="f64", unit=unit, nullable=False
                )
                for axis in ("x", "y", "z")
            ),
        ),
    )


def _reference_contract(*, frame: str = "world", unit: str = "m") -> ReferenceTableContract:
    draft = ReferenceTableContract(
        table_role="commanded-path",
        coordinate_frame_id=frame,
        stable_row_id_field="reference_sample_id",
        fields=(
            ReferenceFieldContract(
                field_name="reference_sample_id", dtype_id="u64", unit="index", nullable=False
            ),
            ReferenceFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
            ReferenceFieldContract(
                field_name="in_session", dtype_id="bool", unit="bool", nullable=False
            ),
            *tuple(
                ReferenceFieldContract(
                    field_name=f"r{axis}", dtype_id="f64", unit=unit, nullable=False
                )
                for axis in ("x", "y", "z")
            ),
        ),
        canonical_order_keys=("t_ns", "reference_sample_id"),
        table_contract_fingerprint=SHA_A,
    )
    return draft.model_copy(
        update={"table_contract_fingerprint": reference_table_contract_fingerprint(draft)}
    )


def _phase(
    start_t_ns: int = 0,
    end_t_ns: int = 100,
    *,
    phase_id: str = "phase-1",
) -> SemanticPhase:
    return SemanticPhase(
        phase_id=phase_id,
        phase_type="tracking",
        start_t_ns=start_t_ns,
        end_t_ns=end_t_ns,
    )


def _identity_transform(*, source_frame: str, target_frame: str) -> dict[str, object]:
    return {
        "transform_id": "reference-to-x-affine-v1",
        "source_frame_id": source_frame,
        "target_frame_id": target_frame,
        "matrix_row_major": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "translation_m": [0.0, 0.0, 0.0],
    }


def _temporal_recipe(
    phases: tuple[SemanticPhase, ...],
    contract: ResolvedInputTableContract,
    *,
    reference_frame: str,
    reference_gap_threshold_ns: int = 100,
    transform: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "semantic_path": "semantic.phases",
        "window_policy": "semantic-span-v1",
        "window_id_prefix": "o2",
        "scope_ids": [phase.phase_id for phase in phases],
        "input_table_contracts": [contract.model_dump(mode="json")],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "axis_bindings": [
            {"axis_id": axis, "x_field": axis, "reference_field": f"r{axis}"}
            for axis in ("x", "y", "z")
        ],
        "reference_gap_threshold_ns": reference_gap_threshold_ns,
        "coordinate_transform": transform
        or _identity_transform(
            source_frame=reference_frame,
            target_frame=contract.coordinate_frame_id,
        ),
    }


def _point_metrics(
    table: pl.DataFrame, gap_threshold_ns: int = 100
) -> PointTemporalArtifactMetrics:
    times = sorted(int(value) for value in table["t_ns"].to_list())
    deltas = [right - left for left, right in zip(times, times[1:], strict=False) if right > left]
    median = float(statistics.median(deltas)) if deltas else None
    return PointTemporalArtifactMetrics(
        artifact_role="samples",
        binding_mode="point",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-samples-aligned-v0.1",
        total_rows=table.height,
        in_session_rows=table.height,
        before_session_rows=0,
        after_session_rows=0,
        first_mapped_t_ns=times[0] if times else None,
        last_mapped_t_ns=times[-1] if times else None,
        in_session_start_t_ns=times[0] if times else None,
        in_session_end_t_ns=times[-1] if times else None,
        in_session_span_ns=(times[-1] - times[0]) if times else None,
        session_span_ratio=((times[-1] - times[0]) / END_NS) if times else None,
        median_period_ns=median,
        gap_threshold_ns=gap_threshold_ns if median is not None else None,
        gap_count=sum(delta > gap_threshold_ns for delta in deltas),
        max_gap_ns=max(deltas) if deltas else None,
    )


def _semantic(phases: tuple[SemanticPhase, ...]) -> SessionSemanticSnapshot:
    draft = SessionSemanticSnapshot(
        session_id="session-1",
        task_profile_id="profile-1",
        scenario_id="scenario-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        annotation_revision="annotations-1",
        synthetic_semantics_unvalidated=False,
        session_end_t_ns=END_NS,
        phases=phases,
        events=(),
        aois=(),
        control_mappings=(),
        baselines=(),
        targets=(),
        envelopes=(),
        applicability=(
            AnchorApplicability(
                anchor_id="O2",
                status="applicable",
                phase_ids=tuple(phase.phase_id for phase in phases),
            ),
        ),
        semantic_snapshot_fingerprint=SHA_C,
    )
    return draft.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(draft)}
    )


def _entry(
    phases: tuple[SemanticPhase, ...],
    contract: ResolvedInputTableContract,
    *,
    reference_frame: str,
    reference_gap_threshold_ns: int = 100,
    transform: dict[str, object] | None = None,
) -> AnchorExecutionEntry:
    definition = _definition()
    schema = load_parameter_schema(definition.parameter_schema_id)
    scorer_annotation = schema["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, dict)
    parameters: dict[str, object] = {}
    return AnchorExecutionEntry(
        anchor_id="O2",
        definition_version=definition.definition_version,
        lifecycle="active",
        canonical_order=1,
        plugin_id=definition.plugin_id,
        plugin_version=definition.plugin_version,
        api_version=definition.api_version,
        definition_fingerprint=plugin_definition_fingerprint(definition),
        implementation_digest=SHA_A,
        parameter_schema_id=definition.parameter_schema_id,
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=definition.required_streams,
        required_context_paths=definition.required_context_paths,
        required_semantic_paths=definition.required_semantic_paths,
        required_reference_ids=definition.required_reference_ids,
        applicability="applicable",
        phase_scope=tuple(phase.phase_id for phase in phases),
        event_scope=(),
        dependencies=definition.dependencies,
        measurement_schema_id=definition.measurement_schema_id,
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=definition.artifact_recipes,
        temporal_recipe=_temporal_recipe(
            phases,
            contract,
            reference_frame=reference_frame,
            reference_gap_threshold_ns=reference_gap_threshold_ns,
            transform=transform,
        ),
        scorer_policy=compile_scorer_policy(scorer_annotation),
    )


def _resolved_references(
    table: pl.DataFrame,
    contract: ReferenceTableContract,
    *,
    present: bool,
) -> ResolvedReferenceSet:
    identity = ReferenceSessionIdentity(
        session_id="session-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        session_end_t_ns=END_NS,
    )
    alignment = ReferenceAlignmentContract(
        mapping_method="affine-v1",
        mapping_policy_id="native-alignment-engineering-v0.1",
        source_clock_id="reference-clock",
        scale=1.0,
        offset_ns=0,
        declared_drift_ppm=0.0,
    )
    view = AlignedStreamView(
        modality="task_reference",
        source_schema_id="reference-raw-v0.1",
        aligned_schema_id="reference-aligned-v0.1",
        clock_id="reference-clock",
        tables={"commanded-path": table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"references/commanded.parquet": SHA_D},
    )
    payload: dict[str, object] = {
        "reference_id": "task_reference",
        "resolution_status": "present" if present else "absent",
        "source_kind": "model_bundle",
        "source_schema_id": "reference-raw-v0.1",
        "aligned_schema_id": "reference-aligned-v0.1",
        "clock_id": "reference-clock",
        "alignment_contract": alignment,
        "table_contract": contract,
        "resource_checksums": (
            [{"path": "references/commanded.parquet", "checksum": SHA_D}] if present else []
        ),
        "resource_fingerprint": SHA_A if present else None,
        "aligned_content_fingerprint": SHA_B if present else None,
        "alignment_fingerprint": SHA_C if present else None,
        "absence_reason": None if present else "not_provided",
    }
    descriptor = ResolvedReferenceDescriptor.model_validate(payload)
    if present:
        descriptor = descriptor.model_copy(
            update={
                "resource_fingerprint": reference_resource_fingerprint(descriptor),
                "aligned_content_fingerprint": aligned_reference_content_fingerprint(
                    table, descriptor.aligned_schema_id, contract
                ),
            }
        )
        descriptor = descriptor.model_copy(
            update={"alignment_fingerprint": reference_alignment_fingerprint(descriptor, identity)}
        )
    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=identity,
        descriptors=(descriptor,),
        reference_set_fingerprint=SHA_A,
    )
    reference_set_fingerprint = resolved_reference_set_fingerprint(snapshot)
    return ResolvedReferenceSet(
        session_identity=identity,
        entries={
            "task_reference": ResolvedReference(
                descriptor=descriptor,
                aligned_view=view if present else None,
            )
        },
        reference_set_fingerprint=reference_set_fingerprint,
    )


def _evaluate(
    *,
    x_table: pl.DataFrame,
    reference_table: pl.DataFrame,
    phases: tuple[SemanticPhase, ...] = (_phase(),),
    x_frame: str = "world",
    x_unit: str = "m",
    reference_frame: str = "world",
    reference_unit: str = "m",
    reference_gap_threshold_ns: int = 100,
    transform: dict[str, object] | None = None,
    reference_present: bool = True,
):
    from pilot_assessment.anchors.plugins.o2_peak_tracking_excursion import create_plugin
    from pilot_assessment.anchors.service import AnchorEvaluator

    x_contract = _x_contract(frame=x_frame, unit=x_unit)
    reference_contract = _reference_contract(frame=reference_frame, unit=reference_unit)
    references = _resolved_references(
        reference_table,
        reference_contract,
        present=reference_present,
    )
    semantic = _semantic(phases)
    entry = _entry(
        phases,
        x_contract,
        reference_frame=reference_frame,
        reference_gap_threshold_ns=reference_gap_threshold_ns,
        transform=transform,
    )
    plan = _canonical_plan(
        (entry,),
        semantic.semantic_snapshot_fingerprint,
        references.reference_set_fingerprint,
        contracts=(x_contract,),
    )
    x_view = AlignedStreamView(
        modality="X",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        clock_id="sim-clock",
        tables={"samples": x_table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/x.parquet": SHA_A},
    )
    base_session = _session()
    session = replace(
        base_session,
        streams={"X": x_view},
        annotations=AlignedAnnotations(
            revision="annotations-1",
            phases=tuple(
                PhaseInterval(
                    phase_id=phase.phase_id,
                    start_t_ns=phase.start_t_ns,
                    end_t_ns=phase.end_t_ns,
                )
                for phase in phases
            ),
            events=(),
            baseline_intervals=(),
            source_schema_ids={
                "phases": "phases-v0.1",
                "events": "events-v0.1",
                "baselines": "baselines-v0.1",
            },
            synthetic_semantics_unvalidated=False,
        ),
    )
    base_report = _report(
        task_reference=TaskReferenceSynchronizationResult(
            reference_id="task_reference",
            source="model_bundle",
            synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
        )
    )
    x_result = base_report.stream_results["X"].model_copy(
        update={"artifacts": {"samples": _point_metrics(x_table)}}
    )
    stream_results = dict(base_report.stream_results)
    stream_results["X"] = x_result
    report = base_report.model_copy(
        update={
            "stream_results": stream_results,
            "annotation_result": base_report.annotation_result.model_copy(
                update={"phase_count": len(phases)}
            ),
        }
    )
    request = AnchorEvaluationRequest(
        aligned_session=session,
        synchronization_report=report,
        session_semantic_snapshot=semantic,
        execution_plan=plan,
        resolved_references=references,
    )
    registry = PluginRegistry.from_factories_for_testing(
        {(entry.plugin_id, entry.plugin_version): create_plugin}, {}
    )
    evaluation = AnchorEvaluator.for_testing(
        registry,
        _policy(),
    ).evaluate(request, InMemoryDerivedArtifactSink())
    assert len(evaluation.results) == 1
    return evaluation.results[0]


def _kernel(
    *,
    x_table: pl.DataFrame,
    reference_table: pl.DataFrame,
    x_frame: str = "world",
    x_unit: str = "m",
    reference_frame: str = "world",
    reference_unit: str = "m",
    reference_gap_threshold_ns: int = 100,
    transform: dict[str, object] | None = None,
):
    from pilot_assessment.anchors.primitives.reference_join import compute_o2_kernel

    phase = _phase()
    x_contract = _x_contract(frame=x_frame, unit=x_unit)
    reference_contract = _reference_contract(frame=reference_frame, unit=reference_unit)
    recipe = _temporal_recipe(
        (phase,),
        x_contract,
        reference_frame=reference_frame,
        reference_gap_threshold_ns=reference_gap_threshold_ns,
        transform=transform,
    )
    return compute_o2_kernel(
        x_table=x_table,
        reference_table=reference_table,
        phase=phase,
        x_contract=x_contract,
        reference_contract=reference_contract,
        scope_start_t_ns=phase.start_t_ns,
        scope_end_t_ns=phase.end_t_ns,
        temporal_recipe=recipe,
    )


@pytest.mark.parametrize(
    ("excursion_ft", "expected_state"),
    [
        (0.0, EvidenceState.DESIRED),
        (2.0, EvidenceState.DESIRED),
        (2.01, EvidenceState.ADEQUATE),
        (5.0, EvidenceState.ADEQUATE),
        (5.01, EvidenceState.UNACCEPTABLE),
        (1_000_000.0, EvidenceState.UNACCEPTABLE),
        (1e200, EvidenceState.UNACCEPTABLE),
    ],
)
def test_o2_desired_adequate_unacceptable_exact_boundaries_and_finite_extreme(
    excursion_ft: float,
    expected_state: EvidenceState,
) -> None:
    result = _evaluate(
        x_table=tiny_x_table(
            [50],
            {"x": [excursion_ft * METERS_PER_FOOT], "y": [0.0], "z": [0.0]},
        ),
        reference_table=tiny_reference_table(
            [50],
            {"rx": [0.0], "ry": [0.0], "rz": [0.0]},
        ),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None
    assert result.primary_value.value == pytest.approx(excursion_ft)
    assert result.evidence_state is expected_state


def test_o2_exact_timestamp_tie_uses_first_stable_reference_row() -> None:
    reference = tiny_reference_table(
        [50, 50],
        {"rx": [100.0, 1.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
    ).with_columns(pl.Series("reference_sample_id", [9, 1], dtype=pl.UInt64))
    result = _kernel(
        x_table=tiny_x_table([50], {"x": [1.0], "y": [0.0], "z": [0.0]}),
        reference_table=reference,
    )

    assert result.status == "computed"
    assert result.peak_excursion_ft == 0.0
    assert result.trace_rows[0].reference_row_id == 1


def test_o2_same_segment_linear_interpolation_saves_per_axis_error() -> None:
    result = _kernel(
        x_table=tiny_x_table([50], {"x": [6.0], "y": [2.0], "z": [0.0]}),
        reference_table=tiny_reference_table(
            [0, 100],
            {"rx": [0.0, 10.0], "ry": [0.0, 2.0], "rz": [0.0, 0.0]},
        ),
    )

    row = result.trace_rows[0]
    assert row.error_x_ft == pytest.approx(1.0 / METERS_PER_FOOT)
    assert row.error_y_ft == pytest.approx(1.0 / METERS_PER_FOOT)
    assert row.error_z_ft == 0.0
    assert row.error_norm_ft == pytest.approx(math.sqrt(2.0) / METERS_PER_FOOT)


def test_o2_forbids_extrapolation_and_cross_gap_join() -> None:
    result = _kernel(
        x_table=tiny_x_table(
            [20, 50, 90],
            {"x": [0.0, 0.0, 0.0], "y": [0.0, 0.0, 0.0], "z": [0.0, 0.0, 0.0]},
        ),
        reference_table=tiny_reference_table(
            [20, 80],
            {"rx": [0.0, 0.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
        ),
        reference_gap_threshold_ns=10,
    )

    assert result.status == "computed"
    assert result.joined_point_count == 1
    assert tuple(row.t_ns for row in result.trace_rows) == (20,)


def test_o2_peak_tie_uses_earliest_timestamp_then_stable_x_row() -> None:
    x_table = tiny_x_table(
        [20, 10, 10],
        {"x": [1.0, -1.0, 1.0], "y": [0.0, 0.0, 0.0], "z": [0.0, 0.0, 0.0]},
    ).with_columns(pl.Series("source_row_index", [7, 9, 2], dtype=pl.UInt64))
    result = _kernel(
        x_table=x_table,
        reference_table=tiny_reference_table(
            [10, 20],
            {"rx": [0.0, 0.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
        ),
    )

    assert result.peak_t_ns == 10
    assert result.peak_source_row_id == 2


def test_o2_applies_explicit_frame_transform_and_unit_conversion() -> None:
    transform = {
        "transform_id": "reference-ned-ft-to-world-m-v1",
        "source_frame_id": "reference-frame",
        "target_frame_id": "world",
        "matrix_row_major": [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        "translation_m": [1.0, 2.0, 3.0],
    }
    result = _kernel(
        x_table=tiny_x_table(
            [50],
            {"x": [2.0 + METERS_PER_FOOT], "y": [2.0], "z": [3.0]},
        ),
        reference_table=tiny_reference_table(
            [50],
            {
                "rx": [0.0],
                "ry": [1.0 / METERS_PER_FOOT],
                "rz": [0.0],
            },
        ),
        reference_frame="reference-frame",
        reference_unit="ft",
        transform=transform,
    )

    assert result.peak_excursion_ft == pytest.approx(1.0)
    assert result.trace_rows[0].error_x_ft == pytest.approx(1.0)


def test_o2_tiny_single_timestamp_overlap_is_still_computed() -> None:
    result = _evaluate(
        x_table=tiny_x_table([50], {"x": [1.0], "y": [0.0], "z": [0.0]}),
        reference_table=tiny_reference_table(
            [50],
            {"rx": [0.0], "ry": [0.0], "rz": [0.0]},
        ),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.raw_metrics["joined-point-count"].value == 1
    assert result.derived_artifacts[0].row_count == 1


def test_o2_no_overlap_is_not_computable_without_overlap_gate() -> None:
    result = _evaluate(
        x_table=tiny_x_table([50], {"x": [0.0], "y": [0.0], "z": [0.0]}),
        reference_table=tiny_reference_table(
            [0, 10],
            {"rx": [0.0, 0.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
        ),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.NOT_COMPUTABLE
    assert result.primary_value is None
    assert result.derived_artifacts == ()
    assert any(item.error_code == "anchor.o2.no_reference_overlap" for item in result.diagnostics)


def test_o2_absent_independent_reference_never_falls_back_to_actual_x() -> None:
    x_table = tiny_x_table([50], {"x": [0.0], "y": [0.0], "z": [0.0]})
    result = _evaluate(
        x_table=x_table,
        reference_table=tiny_reference_table(
            [50],
            {"rx": [0.0], "ry": [0.0], "rz": [0.0]},
        ),
        reference_present=False,
    )

    assert result.calculation_status is AnchorCalculationStatusV2.NOT_COMPUTABLE
    assert result.primary_value is None
    assert result.derived_artifacts == ()
    assert any(item.error_code == "anchor.input.reference_absent" for item in result.diagnostics)
    assert result.diagnostics[0].diagnostics["reference_ids"] == ["task_reference"]


def test_o2_any_noncomputed_applicable_phase_prevents_session_classification() -> None:
    phases = (
        _phase(0, 50, phase_id="phase-computed"),
        _phase(50, 100, phase_id="phase-without-x-support"),
    )
    result = _evaluate(
        x_table=tiny_x_table([20], {"x": [0.0], "y": [0.0], "z": [0.0]}),
        reference_table=tiny_reference_table(
            [20],
            {"rx": [0.0], "ry": [0.0], "rz": [0.0]},
        ),
        phases=phases,
    )

    assert tuple(item.calculation_status for item in result.phase_results) == (
        AnchorCalculationStatusV2.COMPUTED,
        AnchorCalculationStatusV2.MISSING_INPUT,
    )
    assert result.calculation_status is AnchorCalculationStatusV2.MISSING_INPUT
    assert result.primary_value is None
    assert result.evidence_state is None


def test_o2_session_peak_is_the_maximum_across_all_applicable_phases() -> None:
    phases = (
        _phase(0, 50, phase_id="phase-1"),
        _phase(50, 100, phase_id="phase-2"),
    )
    result = _evaluate(
        x_table=tiny_x_table(
            [20, 70],
            {
                "x": [2.0 * METERS_PER_FOOT, 5.0 * METERS_PER_FOOT],
                "y": [0.0, 0.0],
                "z": [0.0, 0.0],
            },
        ),
        reference_table=tiny_reference_table(
            [20, 70],
            {"rx": [0.0, 0.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
        ),
        phases=phases,
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None
    assert result.primary_value.value == pytest.approx(5.0)
    assert result.evidence_state is EvidenceState.ADEQUATE
    phase_values = tuple(
        item.primary_value.value for item in result.phase_results if item.primary_value is not None
    )
    assert phase_values == pytest.approx((2.0, 5.0))


def test_o2_is_deterministic_and_does_not_mutate_sources() -> None:
    x_table = tiny_x_table(
        [10, 50, 90],
        {"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 0.0], "z": [0.0, 0.0, 0.0]},
    )
    reference_table = tiny_reference_table(
        [0, 100],
        {"rx": [0.0, 0.0], "ry": [0.0, 0.0], "rz": [0.0, 0.0]},
    )
    x_before = x_table.clone()
    reference_before = reference_table.clone()

    first = _evaluate(x_table=x_table, reference_table=reference_table)
    second = _evaluate(x_table=x_table, reference_table=reference_table)

    assert first.result_fingerprint == second.result_fingerprint
    assert first.derived_artifacts == second.derived_artifacts
    assert x_table.equals(x_before)
    assert reference_table.equals(reference_before)
