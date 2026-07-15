from __future__ import annotations

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
    SemanticPhase,
    SemanticVector,
    SessionSemanticSnapshot,
    TaskTargetDefinition,
)
from pilot_assessment.contracts.anchor_v2 import AnchorCalculationStatusV2
from pilot_assessment.contracts.synchronization import PhaseInterval, PointTemporalArtifactMetrics
from pilot_assessment.synchronization.models import AlignedAnnotations, AlignedStreamView
from tests.anchors.test_request_validation import END_NS, _report, _session
from tests.anchors.test_service import _canonical_plan, _canonical_references, _policy
from tests.m4_support.micro_inputs import tiny_x_table

NANOSECONDS_PER_SECOND = 1_000_000_000
SHA_A = "a" * 64
METRICS = (
    ("position-error", "m", 1.0),
    ("speed", "m_per_s", 2.0),
    ("angular-rate", "deg_per_s", 3.0),
)


def _definition():
    from pilot_assessment.anchors.plugins.o4_sustained_hover_time import create_plugin

    return create_plugin().definition()


def _contract(
    metrics: tuple[tuple[str, str, float], ...] = METRICS,
) -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="X",
        table_role="samples",
        stream_aligned_schema_id="x-aligned-v0.1",
        table_aligned_schema_id="x-samples-aligned-v0.1",
        coordinate_frame_id="world",
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
                    field_name=metric_id, dtype_id="f64", unit=unit, nullable=False
                )
                for metric_id, unit, _limit in metrics
            ),
        ),
    )


def _point_metrics(table: pl.DataFrame, gap_threshold_ns: int) -> PointTemporalArtifactMetrics:
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


def _envelope() -> EnvelopeDefinition:
    return EnvelopeDefinition(
        envelope_id="hover-envelope",
        target_id="hover-target",
        axis_limits=tuple(
            EnvelopeAxisLimit(
                metric_id=metric_id,
                desired_abs_max=limit,
                adequate_abs_max=2.0 * limit,
                unit=unit,
            )
            for metric_id, unit, limit in sorted(METRICS)
        ),
    )


def _phase(phase_id: str, start_t_ns: int, end_t_ns: int) -> SemanticPhase:
    return SemanticPhase(
        phase_id=phase_id,
        phase_type="hover",
        start_t_ns=start_t_ns,
        end_t_ns=end_t_ns,
        include_session_terminal_point=end_t_ns == END_NS,
        target_id="hover-target",
        envelope_id="hover-envelope",
    )


def _semantic(
    phases: tuple[SemanticPhase, ...], envelope: EnvelopeDefinition
) -> SessionSemanticSnapshot:
    target = TaskTargetDefinition(
        target_id="hover-target",
        position=SemanticVector(coordinate_frame_id="world", unit="m", values=(0.0, 0.0, 0.0)),
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
        phases=phases,
        events=(),
        aois=(),
        control_mappings=(),
        baselines=(),
        targets=(target,),
        envelopes=(envelope,),
        applicability=(
            AnchorApplicability(
                anchor_id="O4",
                status="applicable",
                phase_ids=tuple(phase.phase_id for phase in phases),
                target_ids=(target.target_id,),
                envelope_ids=(envelope.envelope_id,),
            ),
        ),
        semantic_snapshot_fingerprint="c" * 64,
    )
    return draft.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(draft)}
    )


def _temporal_recipe(
    phases: tuple[SemanticPhase, ...],
    contract: ResolvedInputTableContract,
    gap_threshold_ns: int,
) -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "o4",
        "scope_ids": [phase.phase_id for phase in phases],
        "phase_bindings": [
            {
                "phase_id": phase.phase_id,
                "start_t_ns": phase.start_t_ns,
                "end_t_ns": phase.end_t_ns,
                "include_session_terminal_point": phase.include_session_terminal_point,
                "envelope_id": phase.envelope_id,
            }
            for phase in phases
        ],
        "input_table_contracts": [contract.model_dump(mode="json")],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": gap_threshold_ns,
    }


def _entry(
    phases: tuple[SemanticPhase, ...],
    contract: ResolvedInputTableContract,
    *,
    max_behavioral_excursion_ns: int,
    gap_threshold_ns: int,
) -> AnchorExecutionEntry:
    definition = _definition()
    schema = load_parameter_schema(definition.parameter_schema_id)
    scorer_annotation = schema["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, dict)
    parameters = {"max_behavioral_excursion_ns": max_behavioral_excursion_ns}
    return AnchorExecutionEntry(
        anchor_id="O4",
        definition_version=definition.definition_version,
        lifecycle="active",
        canonical_order=3,
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
        temporal_recipe=_temporal_recipe(phases, contract, gap_threshold_ns),
        scorer_policy=compile_scorer_policy(scorer_annotation),
    )


def _table(timestamps: list[int], values: dict[str, list[float]]) -> pl.DataFrame:
    return tiny_x_table(timestamps, values)


def _stable_values(count: int) -> dict[str, list[float]]:
    return {metric_id: [0.0] * count for metric_id, _unit, _limit in METRICS}


def _evaluate(
    *,
    table: pl.DataFrame,
    phases: tuple[SemanticPhase, ...] = (_phase("hover-1", 0, END_NS),),
    envelope: EnvelopeDefinition | None = None,
    max_behavioral_excursion_ns: int = 0,
    gap_threshold_ns: int = END_NS,
):
    from pilot_assessment.anchors.plugins.o4_sustained_hover_time import create_plugin
    from pilot_assessment.anchors.service import AnchorEvaluator

    envelope = envelope or _envelope()
    contract = _contract()
    semantic = _semantic(phases, envelope)
    entry = _entry(
        phases,
        contract,
        max_behavioral_excursion_ns=max_behavioral_excursion_ns,
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
    base_report = _report()
    x_result = base_report.stream_results["X"].model_copy(
        update={"artifacts": {"samples": _point_metrics(table, gap_threshold_ns)}}
    )
    report = base_report.model_copy(
        update={
            "stream_results": {**base_report.stream_results, "X": x_result},
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
    evaluation = AnchorEvaluator.for_testing(registry, _policy()).evaluate(
        request, InMemoryDerivedArtifactSink()
    )
    assert len(evaluation.results) == 1
    return evaluation.results[0]


@pytest.mark.parametrize(
    ("stable_ns", "expected_state"),
    [
        (10 * NANOSECONDS_PER_SECOND, EvidenceState.DESIRED),
        (5 * NANOSECONDS_PER_SECOND, EvidenceState.ADEQUATE),
        (5 * NANOSECONDS_PER_SECOND - 1, EvidenceState.UNACCEPTABLE),
    ],
)
def test_o4_exact_ten_and_five_second_boundaries(
    stable_ns: int, expected_state: EvidenceState
) -> None:
    if stable_ns == END_NS:
        timestamps = [0]
        values = _stable_values(1)
    else:
        timestamps = [0, stable_ns]
        values = _stable_values(2)
        values["position-error"][1] = 2.0
    result = _evaluate(table=_table(timestamps, values))

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None
    assert result.primary_value.value == stable_ns / NANOSECONDS_PER_SECOND
    assert result.evidence_state is expected_state


@pytest.mark.parametrize("violated_metric", ["position-error", "speed", "angular-rate"])
def test_o4_stability_is_conjunction_of_hover_speed_and_angular_rate(
    violated_metric: str,
) -> None:
    values = _stable_values(1)
    values[violated_metric][0] = 100.0
    result = _evaluate(table=_table([0], values))

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None and result.primary_value.value == 0.0
    assert result.evidence_state is EvidenceState.UNACCEPTABLE


def test_o4_all_false_is_zero_seconds_computed_u_not_missing() -> None:
    values = {metric_id: [100.0] for metric_id, _unit, _limit in METRICS}
    result = _evaluate(table=_table([0], values))

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None and result.primary_value.value == 0.0
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    assert result.classification_override is None
    assert len(result.derived_artifacts) == 1
    assert result.derived_artifacts[0].artifact_id == "stable-hover-mask"


@pytest.mark.parametrize(
    ("tolerance_ns", "expected_seconds", "expected_state"),
    [
        (NANOSECONDS_PER_SECOND, 10.0, EvidenceState.DESIRED),
        (NANOSECONDS_PER_SECOND - 1, 5.0, EvidenceState.ADEQUATE),
    ],
)
def test_o4_behavioral_excursion_tolerance_is_explicit_and_inclusive(
    tolerance_ns: int,
    expected_seconds: float,
    expected_state: EvidenceState,
) -> None:
    values = _stable_values(3)
    values["position-error"][1] = 2.0
    result = _evaluate(
        table=_table([0, 4 * NANOSECONDS_PER_SECOND, 5 * NANOSECONDS_PER_SECOND], values),
        max_behavioral_excursion_ns=tolerance_ns,
    )

    assert result.primary_value is not None and result.primary_value.value == expected_seconds
    assert result.evidence_state is expected_state
    phase = result.phase_results[0]
    expected_bridged = NANOSECONDS_PER_SECOND if tolerance_ns == NANOSECONDS_PER_SECOND else 0
    assert phase.raw_metrics["bridged-excursion-duration"].value == expected_bridged


@pytest.mark.parametrize(
    ("position_values", "timestamps"),
    [
        ([2.0, 0.0], [0, NANOSECONDS_PER_SECOND]),
        ([0.0, 2.0], [0, 9 * NANOSECONDS_PER_SECOND]),
    ],
)
def test_o4_behavioral_tolerance_does_not_bridge_leading_or_trailing_excursion(
    position_values: list[float], timestamps: list[int]
) -> None:
    values = _stable_values(2)
    values["position-error"] = position_values
    result = _evaluate(
        table=_table(timestamps, values),
        max_behavioral_excursion_ns=END_NS,
    )

    assert result.primary_value is not None and result.primary_value.value == 9.0
    assert result.evidence_state is EvidenceState.ADEQUATE
    assert result.phase_results[0].raw_metrics["bridged-excursion-count"].value == 0


def test_o4_effective_mask_records_an_explicitly_tolerated_excursion() -> None:
    from pilot_assessment.anchors.primitives import envelopes

    phases = (_phase("hover-1", 0, END_NS),)
    contract = _contract()
    values = _stable_values(3)
    values["position-error"][1] = 2.0
    result = envelopes.compute_o4_kernel(
        x_table=_table([0, 4 * NANOSECONDS_PER_SECOND, 5 * NANOSECONDS_PER_SECOND], values),
        phase_id="hover-1",
        envelope=_envelope(),
        scope_start_t_ns=0,
        scope_end_t_ns=END_NS,
        include_session_terminal_point=True,
        input_contracts=(contract,),
        parameters={"max_behavioral_excursion_ns": NANOSECONDS_PER_SECOND},
        temporal_recipe=_temporal_recipe(phases, contract, END_NS),
    )

    assert result.status == "computed"
    assert tuple(row.stable for row in result.mask_rows) == (True, True, True)


def test_o4_finite_extreme_performance_remains_computed_u() -> None:
    values = _stable_values(1)
    values["position-error"][0] = 1e200
    result = _evaluate(table=_table([0], values))

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None and result.primary_value.value == 0.0
    assert result.evidence_state is EvidenceState.UNACCEPTABLE


def test_o4_gap_splits_stable_run_even_with_large_behavioral_tolerance() -> None:
    timestamps = [
        0,
        NANOSECONDS_PER_SECOND,
        5 * NANOSECONDS_PER_SECOND,
        6 * NANOSECONDS_PER_SECOND,
    ]
    result = _evaluate(
        table=_table(timestamps, _stable_values(len(timestamps))),
        gap_threshold_ns=2 * NANOSECONDS_PER_SECOND,
        max_behavioral_excursion_ns=END_NS,
    )

    assert result.primary_value is not None and result.primary_value.value == 5.0
    assert result.evidence_state is EvidenceState.ADEQUATE
    assert result.phase_results[0].raw_metrics["gap-count"].value == 1


def test_o4_does_not_join_stability_across_phase_boundaries() -> None:
    phases = (
        _phase("hover-1", 0, 5 * NANOSECONDS_PER_SECOND),
        _phase("hover-2", 5 * NANOSECONDS_PER_SECOND, END_NS),
    )
    result = _evaluate(
        table=_table([0, 5 * NANOSECONDS_PER_SECOND], _stable_values(2)),
        phases=phases,
    )

    assert result.primary_value is not None and result.primary_value.value == 5.0
    assert result.evidence_state is EvidenceState.ADEQUATE
    assert tuple(item.breakdown_id for item in result.phase_results) == ("hover-1", "hover-2")
    assert all(
        item.primary_value is not None and item.primary_value.value == 5.0
        for item in result.phase_results
    )


def test_o4_missing_later_phase_support_prevents_partial_session_score() -> None:
    phases = (
        _phase("hover-1", 0, 5 * NANOSECONDS_PER_SECOND),
        _phase("hover-2", 5 * NANOSECONDS_PER_SECOND, END_NS),
    )
    result = _evaluate(table=_table([0], _stable_values(1)), phases=phases)

    assert result.calculation_status is AnchorCalculationStatusV2.MISSING_INPUT
    assert result.primary_value is None
    assert result.evidence_state is None
    assert tuple(item.calculation_status for item in result.phase_results) == (
        AnchorCalculationStatusV2.COMPUTED,
        AnchorCalculationStatusV2.MISSING_INPUT,
    )


def test_o4_replay_is_deterministic_and_does_not_mutate_x() -> None:
    table = _table([0], _stable_values(1))
    original = table.clone()

    first = _evaluate(table=table)
    second = _evaluate(table=table)

    assert first.result_fingerprint == second.result_fingerprint
    assert table.equals(original)
    assert first.derived_artifacts[0].schema_id == "stable-hover-mask-v0.1"
    assert first.derived_artifacts[0].row_count == 1


def test_o4_plugin_calls_shared_envelope_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    from pilot_assessment.anchors.primitives import envelopes

    real_kernel = envelopes.compute_o4_kernel
    calls: list[str] = []

    def spy(*args, **kwargs):
        calls.append(kwargs["phase_id"])
        return real_kernel(*args, **kwargs)

    monkeypatch.setattr(envelopes, "compute_o4_kernel", spy)
    _evaluate(table=_table([0], _stable_values(1)))

    assert calls == ["hover-1"]


def test_o4_catalog_definition_parameter_and_artifact_recipe_are_exact() -> None:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O4"
    )
    definition = _definition()
    parameter_schema = load_parameter_schema(definition.parameter_schema_id)

    assert definition.plugin_id == catalog_entry.plugin_id
    assert definition.required_streams == ("X",)
    assert definition.required_semantic_paths == ("semantic.envelopes",)
    assert definition.parameter_schema_id == "o4-parameters-0.1"
    assert parameter_schema["properties"]["max_behavioral_excursion_ns"]["default"] == 0
    assert definition.artifact_recipes == catalog_entry.artifact_recipes
    fields = definition.artifact_recipes[0].schema_descriptor["fields"]
    assert [field["name"] for field in fields] == [
        "phase_id",
        "t_ns",
        "source_row_id",
        "stable",
    ]
