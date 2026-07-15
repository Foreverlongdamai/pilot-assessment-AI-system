from __future__ import annotations

import math
import statistics
from dataclasses import replace

import polars as pl
import pytest

from pilot_assessment.anchors.artifacts import InMemoryDerivedArtifactSink
from pilot_assessment.anchors.catalog import load_packaged_catalog, load_parameter_schema
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    session_semantic_snapshot_fingerprint,
)
from pilot_assessment.anchors.models import AnchorEvaluationRequest
from pilot_assessment.anchors.registry import PluginRegistry
from pilot_assessment.anchors.scoring import compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AnchorExecutionEntry,
    EnvelopeAxisLimit,
    EnvelopeDefinition,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    SemanticEvent,
    SemanticPhase,
    SemanticVector,
    SessionSemanticSnapshot,
    TaskTargetDefinition,
)
from pilot_assessment.contracts.anchor_v2 import AnchorCalculationStatusV2
from pilot_assessment.contracts.synchronization import (
    EventMarker,
    PhaseInterval,
    PointTemporalArtifactMetrics,
)
from pilot_assessment.synchronization.models import AlignedAnnotations, AlignedStreamView
from tests.anchors.test_request_validation import END_NS, _report, _session
from tests.anchors.test_service import _canonical_plan, _canonical_references, _policy
from tests.m4_support.micro_inputs import tiny_x_table

SHA_A = "a" * 64
NANOSECONDS_PER_SECOND = 1_000_000_000


def _definition():
    from pilot_assessment.anchors.plugins.o3_terminal_capture_quality import create_plugin

    return create_plugin().definition()


def _x_contract(*, frame: str = "world", unit: str = "ft") -> ResolvedInputTableContract:
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


def _event(
    *,
    event_id: str = "d-to-h-1",
    duration_ns: int = 8 * NANOSECONDS_PER_SECOND,
    opportunity_end_t_ns: int | None = None,
    target_id: str | None = "hover-target",
    envelope_id: str | None = "hover-envelope",
) -> SemanticEvent:
    return SemanticEvent(
        event_id=event_id,
        event_type="d-to-h-boundary",
        t_ns=0,
        duration_ns=duration_ns,
        opportunity_end_t_ns=opportunity_end_t_ns,
        phase_id="phase-1",
        target_id=target_id,
        envelope_id=envelope_id,
    )


def _target(
    *,
    frame: str = "world",
    unit: str = "ft",
    arrival_axis: tuple[float, float, float] | None = (1.0, 0.0, 0.0),
) -> TaskTargetDefinition:
    return TaskTargetDefinition(
        target_id="hover-target",
        position=SemanticVector(
            coordinate_frame_id=frame,
            unit=unit,
            values=(0.0, 0.0, 0.0),
        ),
        arrival_axis=(
            None
            if arrival_axis is None
            else SemanticVector(
                coordinate_frame_id=frame,
                unit="dimensionless",
                values=arrival_axis,
            )
        ),
    )


def _envelope(*, unit: str = "ft") -> EnvelopeDefinition:
    return EnvelopeDefinition(
        envelope_id="hover-envelope",
        target_id="hover-target",
        axis_limits=tuple(
            EnvelopeAxisLimit(
                metric_id=axis,
                desired_abs_max=1.0,
                adequate_abs_max=2.0,
                unit=unit,
            )
            for axis in ("x", "y", "z")
        ),
    )


def _point_metrics(
    table: pl.DataFrame,
    gap_threshold_ns: int,
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


def _semantic(
    events: tuple[SemanticEvent, ...],
    target: TaskTargetDefinition,
    envelope: EnvelopeDefinition,
) -> SessionSemanticSnapshot:
    phase = SemanticPhase(
        phase_id="phase-1",
        phase_type="hover",
        start_t_ns=0,
        end_t_ns=END_NS,
        include_session_terminal_point=True,
        target_id=target.target_id,
        envelope_id=envelope.envelope_id,
    )
    target_ids = tuple(sorted({event.target_id for event in events if event.target_id is not None}))
    envelope_ids = tuple(
        sorted({event.envelope_id for event in events if event.envelope_id is not None})
    )
    draft = SessionSemanticSnapshot(
        session_id="session-1",
        task_profile_id="profile-1",
        scenario_id="scenario-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint="b" * 64,
        annotation_revision="annotations-1",
        synthetic_semantics_unvalidated=False,
        session_end_t_ns=END_NS,
        phases=(phase,),
        events=events,
        aois=(),
        control_mappings=(),
        baselines=(),
        targets=(target,),
        envelopes=(envelope,),
        applicability=(
            AnchorApplicability(
                anchor_id="O3",
                status="applicable",
                event_ids=tuple(event.event_id for event in events),
                target_ids=target_ids,
                envelope_ids=envelope_ids,
            ),
        ),
        semantic_snapshot_fingerprint="c" * 64,
    )
    return draft.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(draft)}
    )


def _temporal_recipe(
    events: tuple[SemanticEvent, ...],
    contract: ResolvedInputTableContract,
    gap_threshold_ns: int,
) -> dict[str, object]:
    return {
        "semantic_path": "semantic.events",
        "event_span": "auto",
        "window_policy": "semantic-span-v1",
        "window_id_prefix": "o3",
        "scope_ids": [event.event_id for event in events],
        "input_table_contracts": [contract.model_dump(mode="json")],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": gap_threshold_ns,
        "position_bindings": [
            {"axis_id": axis, "x_field": axis, "target_component_index": index}
            for index, axis in enumerate(("x", "y", "z"))
        ],
    }


def _entry(
    events: tuple[SemanticEvent, ...],
    contract: ResolvedInputTableContract,
    *,
    capture_hold_ns: int,
    gap_threshold_ns: int,
) -> AnchorExecutionEntry:
    definition = _definition()
    schema = load_parameter_schema(definition.parameter_schema_id)
    scorer_annotation = schema["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, dict)
    parameters = {"capture_hold_ns": capture_hold_ns}
    return AnchorExecutionEntry(
        anchor_id="O3",
        definition_version=definition.definition_version,
        lifecycle="active",
        canonical_order=2,
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
        phase_scope=(),
        event_scope=tuple(event.event_id for event in events),
        dependencies=definition.dependencies,
        measurement_schema_id=definition.measurement_schema_id,
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=definition.artifact_recipes,
        temporal_recipe=_temporal_recipe(events, contract, gap_threshold_ns),
        scorer_policy=compile_scorer_policy(scorer_annotation),
    )


def _evaluate(
    *,
    table: pl.DataFrame,
    events: tuple[SemanticEvent, ...] = (_event(),),
    target: TaskTargetDefinition | None = None,
    envelope: EnvelopeDefinition | None = None,
    x_frame: str = "world",
    x_unit: str = "ft",
    capture_hold_ns: int = 2 * NANOSECONDS_PER_SECOND,
    gap_threshold_ns: int = 10 * NANOSECONDS_PER_SECOND,
):
    from pilot_assessment.anchors.plugins.o3_terminal_capture_quality import create_plugin
    from pilot_assessment.anchors.service import AnchorEvaluator

    target = target or _target()
    envelope = envelope or _envelope()
    contract = _x_contract(frame=x_frame, unit=x_unit)
    semantic = _semantic(events, target, envelope)
    entry = _entry(
        events,
        contract,
        capture_hold_ns=capture_hold_ns,
        gap_threshold_ns=gap_threshold_ns,
    )
    references = _canonical_references()
    plan = _canonical_plan(
        (entry,),
        semantic.semantic_snapshot_fingerprint,
        references.reference_set_fingerprint,
        contracts=(contract,),
    )
    view = AlignedStreamView(
        modality="X",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        clock_id="sim-clock",
        tables={"samples": table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/x.parquet": SHA_A},
    )
    base_session = _session()
    session = replace(
        base_session,
        streams={"X": view},
        annotations=AlignedAnnotations(
            revision="annotations-1",
            phases=(PhaseInterval(phase_id="phase-1", start_t_ns=0, end_t_ns=END_NS),),
            events=tuple(
                EventMarker(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    t_ns=event.t_ns,
                    duration_ns=event.duration_ns,
                )
                for event in events
            ),
            baseline_intervals=(),
            source_schema_ids={
                "phases": "phases-v0.1",
                "events": "events-v0.1",
                "baselines": "baselines-v0.1",
            },
            synthetic_semantics_unvalidated=False,
        ),
    )
    base_report = _report()
    x_result = base_report.stream_results["X"].model_copy(
        update={"artifacts": {"samples": _point_metrics(table, gap_threshold_ns)}}
    )
    stream_results = dict(base_report.stream_results)
    stream_results["X"] = x_result
    report = base_report.model_copy(
        update={
            "stream_results": stream_results,
            "annotation_result": base_report.annotation_result.model_copy(
                update={"phase_count": 1, "event_count": len(events)}
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
    evaluation = AnchorEvaluator.for_testing(registry, _policy()).evaluate(
        request, InMemoryDerivedArtifactSink()
    )
    assert len(evaluation.results) == 1
    return evaluation.results[0]


def _table(timestamps: list[int], x_values: list[float]) -> pl.DataFrame:
    return tiny_x_table(
        timestamps,
        {
            "x": x_values,
            "y": [0.0] * len(timestamps),
            "z": [0.0] * len(timestamps),
        },
    )


@pytest.mark.parametrize(
    ("overshoot_ft", "settling_s", "expected_state"),
    [
        (2.0, 3.0, EvidenceState.DESIRED),
        (2.01, 3.0, EvidenceState.ADEQUATE),
        (5.0, 5.0, EvidenceState.ADEQUATE),
        (5.01, 5.0, EvidenceState.UNACCEPTABLE),
        (1e200, 1.0, EvidenceState.UNACCEPTABLE),
    ],
)
def test_o3_exact_conjunction_boundaries_and_finite_extreme(
    overshoot_ft: float,
    settling_s: float,
    expected_state: EvidenceState,
) -> None:
    settling_ns = round(settling_s * NANOSECONDS_PER_SECOND)
    result = _evaluate(table=_table([0, settling_ns], [overshoot_ft, 0.0]))

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.evidence_state is expected_state
    assert result.primary_value is None
    assert result.primary_value_reason == "composite_conjunction"
    assert math.isclose(float(result.raw_metrics["overshoot"].value), overshoot_ft)
    assert result.raw_metrics["settling_time"].value == settling_s
    assert result.classification_override is None
    assert result.event_results[0].evidence_state is expected_state


def test_o3_normalizes_arrival_axis_and_ignores_negative_direction() -> None:
    result = _evaluate(
        table=_table(
            [0, NANOSECONDS_PER_SECOND, 2 * NANOSECONDS_PER_SECOND],
            [-100.0, 4.0, 0.0],
        ),
        events=(_event(duration_ns=6 * NANOSECONDS_PER_SECOND),),
        target=_target(arrival_axis=(2.0, 0.0, 0.0)),
    )

    assert result.raw_metrics["overshoot"].value == 4.0
    assert result.raw_metrics["settling_time"].value == 2.0
    assert result.evidence_state is EvidenceState.ADEQUATE


def test_o3_confirms_full_hold_but_records_latency_at_later_hold_start() -> None:
    result = _evaluate(
        table=_table(
            [
                0,
                NANOSECONDS_PER_SECOND,
                2_500_000_000,
                3 * NANOSECONDS_PER_SECOND,
            ],
            [2.0, 0.0, 2.0, 0.0],
        ),
        events=(_event(duration_ns=6 * NANOSECONDS_PER_SECOND),),
    )

    assert result.evidence_state is EvidenceState.DESIRED
    assert result.raw_metrics["settling_time"].value == 3.0
    event = result.event_results[0]
    assert event.raw_metrics["capture-hold-start-t-ns"].value == 3 * NANOSECONDS_PER_SECOND
    assert event.raw_metrics["capture-hold-end-t-ns"].value == 5 * NANOSECONDS_PER_SECOND


def test_o3_declared_gap_cannot_be_used_as_capture_hold() -> None:
    result = _evaluate(
        table=_table([0, 3 * NANOSECONDS_PER_SECOND], [0.0, 0.0]),
        events=(_event(duration_ns=6 * NANOSECONDS_PER_SECOND),),
        gap_threshold_ns=NANOSECONDS_PER_SECOND,
    )

    assert result.evidence_state is EvidenceState.DESIRED
    assert result.raw_metrics["settling_time"].value == 3.0
    assert result.event_results[0].raw_metrics["gap-count"].value == 1


def test_o3_opportunity_end_clips_horizon_and_miss_is_finite_computed_u() -> None:
    result = _evaluate(
        table=_table([0, 3 * NANOSECONDS_PER_SECOND], [2.0, 0.0]),
        events=(
            _event(
                duration_ns=8 * NANOSECONDS_PER_SECOND,
                opportunity_end_t_ns=4 * NANOSECONDS_PER_SECOND,
            ),
        ),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    assert result.primary_value is None
    assert result.primary_value_reason == "composite_conjunction"
    assert result.classification_override is not None
    assert result.classification_override.code == "capture_missed"
    assert result.raw_metrics["observed_wait"].value == 4.0
    assert result.raw_metrics["overshoot"].value == 2.0
    assert "settling_time" not in result.raw_metrics
    assert result.provenance.computation_trace.analysis_end_t_ns == 4 * NANOSECONDS_PER_SECOND


def test_o3_missing_axis_or_frame_mismatch_is_not_computable() -> None:
    table = _table([0], [0.0])
    missing_axis = _evaluate(table=table, target=_target(arrival_axis=None))
    wrong_frame = _evaluate(table=table, target=_target(frame="body"))
    missing_target = _evaluate(table=table, events=(_event(target_id=None),))

    for result, reason in (
        (missing_axis, "arrival-axis-missing"),
        (wrong_frame, "coordinate-frame-mismatch"),
        (missing_target, "event-target-missing"),
    ):
        assert result.calculation_status is AnchorCalculationStatusV2.NOT_COMPUTABLE
        assert result.primary_value is None
        assert result.evidence_state is None
        assert result.event_results[0].diagnostics[0].error_code == f"anchor.o3.{reason}"


def test_o3_zero_confirmation_duration_captures_at_first_inside_sample() -> None:
    result = _evaluate(
        table=_table([NANOSECONDS_PER_SECOND], [0.0]),
        events=(_event(duration_ns=4 * NANOSECONDS_PER_SECOND),),
        capture_hold_ns=0,
    )

    assert result.evidence_state is EvidenceState.DESIRED
    assert result.raw_metrics["settling_time"].value == 1.0
    assert result.event_results[0].raw_metrics["capture-hold-start-t-ns"].value == (
        NANOSECONDS_PER_SECOND
    )
    assert result.event_results[0].raw_metrics["capture-hold-end-t-ns"].value == (
        NANOSECONDS_PER_SECOND
    )


def test_o3_multi_event_session_uses_miss_veto_after_all_breakdowns() -> None:
    result = _evaluate(
        table=_table([0, 3 * NANOSECONDS_PER_SECOND], [2.0, 0.0]),
        events=(
            _event(event_id="d-to-h-1"),
            _event(
                event_id="d-to-h-2",
                opportunity_end_t_ns=4 * NANOSECONDS_PER_SECOND,
            ),
        ),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    assert result.classification_override is not None
    assert result.classification_override.code == "capture_missed"
    states = {item.breakdown_id: item.evidence_state for item in result.event_results}
    assert states == {
        "d-to-h-1": EvidenceState.DESIRED,
        "d-to-h-2": EvidenceState.UNACCEPTABLE,
    }
    assert len(result.derived_artifacts) == 1
    assert result.derived_artifacts[0].row_count == 4


def test_o3_semantic_contract_rejects_nonfinite_or_zero_arrival_axis() -> None:
    with pytest.raises(ValueError):
        SemanticVector(
            coordinate_frame_id="world",
            unit="dimensionless",
            values=(math.inf, 0.0, 0.0),
        )
    with pytest.raises(ValueError, match="non-zero"):
        _target(arrival_axis=(0.0, 0.0, 0.0))


def test_o3_replay_is_deterministic_does_not_mutate_x_and_emits_exact_trace() -> None:
    table = _table([0, 2 * NANOSECONDS_PER_SECOND], [2.0, 0.0])
    original = table.clone()

    first = _evaluate(table=table)
    second = _evaluate(table=table)

    assert first.result_fingerprint == second.result_fingerprint
    assert table.equals(original)
    assert len(first.derived_artifacts) == 1
    artifact = first.derived_artifacts[0]
    assert artifact.artifact_id == "capture-trace"
    assert artifact.schema_id == "capture-trace-v0.1"
    assert artifact.row_count == 2


def test_o3_plugin_calls_shared_envelope_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    from pilot_assessment.anchors.primitives import envelopes

    real_kernel = envelopes.compute_o3_kernel
    calls: list[str] = []

    def spy(*args, **kwargs):
        calls.append(kwargs["event"].event_id)
        return real_kernel(*args, **kwargs)

    monkeypatch.setattr(envelopes, "compute_o3_kernel", spy)
    _evaluate(table=_table([0, 2 * NANOSECONDS_PER_SECOND], [2.0, 0.0]))

    assert calls == ["d-to-h-1"]


def test_o3_catalog_definition_and_artifact_recipe_are_exact() -> None:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O3"
    )
    definition = _definition()

    assert definition.plugin_id == catalog_entry.plugin_id
    assert definition.parameter_schema_id == "o3-parameters-0.1"
    assert definition.required_streams == ("X",)
    assert definition.required_semantic_paths == (
        "semantic.envelopes",
        "semantic.events",
        "semantic.targets",
    )
    assert definition.artifact_recipes == catalog_entry.artifact_recipes
    fields = definition.artifact_recipes[0].schema_descriptor["fields"]
    assert [field["name"] for field in fields] == [
        "event_id",
        "t_ns",
        "source_row_id",
        "overshoot",
        "inside_hover",
    ]
