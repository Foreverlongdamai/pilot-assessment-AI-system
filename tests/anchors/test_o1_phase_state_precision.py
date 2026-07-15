from __future__ import annotations

import statistics
from dataclasses import replace

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
from pilot_assessment.contracts.synchronization import (
    PhaseInterval,
    PointTemporalArtifactMetrics,
)
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedStreamView,
)
from tests.anchors.test_request_validation import END_NS, _report, _session
from tests.anchors.test_service import _canonical_plan, _canonical_references, _policy
from tests.m4_support.micro_inputs import tiny_x_table
from tests.m4_support.micro_oracles import duration_percent, higher_is_better_state

SHA_A = "a" * 64


def _definition():
    from pilot_assessment.anchors.plugins.o1_phase_state_precision import create_plugin

    return create_plugin().definition()


def _input_contract(axis_ids: tuple[str, ...]) -> ResolvedInputTableContract:
    fields = (
        ResolvedInputFieldContract(
            field_name="source_row_index", dtype_id="u64", unit="index", nullable=False
        ),
        ResolvedInputFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
        ResolvedInputFieldContract(
            field_name="in_session", dtype_id="bool", unit="bool", nullable=False
        ),
        *tuple(
            ResolvedInputFieldContract(field_name=axis_id, dtype_id="f64", unit="m", nullable=False)
            for axis_id in axis_ids
        ),
    )
    return ResolvedInputTableContract(
        modality="X",
        table_role="samples",
        stream_aligned_schema_id="x-aligned-v0.1",
        table_aligned_schema_id="x-samples-aligned-v0.1",
        coordinate_frame_id="world",
        fields=fields,
    )


def _point_metrics(table, gap_threshold_ns: int) -> PointTemporalArtifactMetrics:
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


def _entry(
    phases: tuple[SemanticPhase, ...],
    contract: ResolvedInputTableContract,
    gap_threshold_ns: int,
) -> AnchorExecutionEntry:
    definition = _definition()
    schema = load_parameter_schema(definition.parameter_schema_id)
    scorer_annotation = schema["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, dict)
    parameters: dict[str, object] = {}
    temporal_recipe = {
        "semantic_path": "semantic.phases",
        "window_policy": "semantic-span-v1",
        "window_id_prefix": "o1",
        "scope_ids": [phase.phase_id for phase in phases],
        "input_table_contracts": [contract.model_dump(mode="json")],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": gap_threshold_ns,
    }
    return AnchorExecutionEntry(
        anchor_id="O1",
        definition_version=definition.definition_version,
        lifecycle="active",
        canonical_order=0,
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
        temporal_recipe=temporal_recipe,
        scorer_policy=compile_scorer_policy(scorer_annotation),
    )


def _semantic(
    phases: tuple[SemanticPhase, ...],
    envelopes: tuple[EnvelopeDefinition, ...],
) -> SessionSemanticSnapshot:
    target_ids = tuple(sorted({envelope.target_id for envelope in envelopes}))
    targets = tuple(
        TaskTargetDefinition(
            target_id=target_id,
            position=SemanticVector(coordinate_frame_id="world", unit="m", values=(0.0, 0.0, 0.0)),
        )
        for target_id in target_ids
    )
    draft = SessionSemanticSnapshot(
        session_id="session-1",
        task_profile_id="profile-1",
        scenario_id="scenario-1",
        source_snapshot_fingerprint="a" * 64,
        synchronization_fingerprint="b" * 64,
        annotation_revision="annotations-1",
        synthetic_semantics_unvalidated=False,
        session_end_t_ns=END_NS,
        phases=phases,
        events=(),
        aois=(),
        control_mappings=(),
        baselines=(),
        targets=targets,
        envelopes=envelopes,
        applicability=(
            AnchorApplicability(
                anchor_id="O1",
                status="applicable",
                phase_ids=tuple(phase.phase_id for phase in phases),
                target_ids=target_ids,
                envelope_ids=tuple(envelope.envelope_id for envelope in envelopes),
            ),
        ),
        semantic_snapshot_fingerprint="c" * 64,
    )
    return draft.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(draft)}
    )


def _evaluate(
    *,
    table,
    phases: tuple[SemanticPhase, ...],
    envelopes: tuple[EnvelopeDefinition, ...],
    gap_threshold_ns: int = 100,
):
    from pilot_assessment.anchors.plugins.o1_phase_state_precision import create_plugin
    from pilot_assessment.anchors.service import AnchorEvaluator

    contract = _input_contract(tuple(limit.metric_id for limit in envelopes[0].axis_limits))
    entry = _entry(phases, contract, gap_threshold_ns)
    semantic = _semantic(phases, envelopes)
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
        source_checksums={"streams/x.parquet": "a" * 64},
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
    sink = InMemoryDerivedArtifactSink()
    evaluation = AnchorEvaluator.for_testing(registry, _policy()).evaluate(request, sink)
    assert len(evaluation.results) == 1
    return evaluation.results[0]


def _phase(
    phase_id: str,
    start_t_ns: int,
    end_t_ns: int,
    *,
    envelope_id: str | None = "envelope-1",
) -> SemanticPhase:
    return SemanticPhase(
        phase_id=phase_id,
        phase_type="test",
        start_t_ns=start_t_ns,
        end_t_ns=end_t_ns,
        target_id="target-1" if envelope_id is not None else None,
        envelope_id=envelope_id,
    )


def _envelope(desired_abs_max: float = 1.0) -> EnvelopeDefinition:
    return EnvelopeDefinition(
        envelope_id="envelope-1",
        target_id="target-1",
        axis_limits=(
            EnvelopeAxisLimit(
                metric_id="axis-x",
                desired_abs_max=desired_abs_max,
                adequate_abs_max=max(2.0, desired_abs_max),
                unit="m",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("inside_ns", "expected_state"),
    [
        (100, EvidenceState.DESIRED),
        (90, EvidenceState.DESIRED),
        (89, EvidenceState.ADEQUATE),
        (70, EvidenceState.ADEQUATE),
        (69, EvidenceState.UNACCEPTABLE),
    ],
)
def test_o1_desired_adequate_unacceptable_and_exact_boundaries(
    inside_ns: int, expected_state: EvidenceState
) -> None:
    timestamps = [0] if inside_ns == 100 else [0, inside_ns]
    values = [0.0] if inside_ns == 100 else [0.0, 2.0]
    result = _evaluate(
        table=tiny_x_table(timestamps, {"axis-x": values}),
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(),),
    )

    expected_percent = duration_percent(inside_ns, 100)
    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None
    assert result.primary_value.value == expected_percent
    assert result.evidence_state is expected_state
    assert result.evidence_state.value == higher_is_better_state(
        expected_percent, desired_at_least=90.0, adequate_at_least=70.0
    )


def test_o1_partial_support_is_scored_against_full_phase_without_quality_gate() -> None:
    result = _evaluate(
        table=tiny_x_table([80], {"axis-x": [0.0]}),
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(),),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.primary_value is not None and result.primary_value.value == 20.0
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    phase = result.phase_results[0]
    assert phase.raw_metrics["observed-support-duration"].value == 20
    assert phase.raw_metrics["phase-duration"].value == 100


def test_o1_noncomputed_later_phase_prevents_partial_session_score() -> None:
    result = _evaluate(
        table=tiny_x_table([0], {"axis-x": [0.0]}),
        phases=(
            _phase("phase-1", 0, 50),
            _phase("phase-2", 50, 100),
        ),
        envelopes=(_envelope(),),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.MISSING_INPUT
    assert result.primary_value is None
    assert tuple(item.calculation_status for item in result.phase_results) == (
        AnchorCalculationStatusV2.COMPUTED,
        AnchorCalculationStatusV2.MISSING_INPUT,
    )


def test_o1_computes_all_phase_traces_after_early_unacceptable() -> None:
    result = _evaluate(
        table=tiny_x_table([0, 50], {"axis-x": [2.0, 0.0]}),
        phases=(
            _phase("phase-1", 0, 50),
            _phase("phase-2", 50, 100),
        ),
        envelopes=(_envelope(),),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    assert tuple(item.evidence_state for item in result.phase_results) == (
        EvidenceState.UNACCEPTABLE,
        EvidenceState.DESIRED,
    )
    assert len(result.derived_artifacts) == 1
    assert result.derived_artifacts[0].row_count == 4


def test_o1_gap_does_not_extend_inside_duration() -> None:
    result = _evaluate(
        table=tiny_x_table([0, 40], {"axis-x": [0.0, 0.0]}),
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(),),
        gap_threshold_ns=10,
    )

    assert result.primary_value is not None and result.primary_value.value == 60.0
    phase = result.phase_results[0]
    assert phase.raw_metrics["gap-count"].value == 1
    assert phase.raw_metrics["observed-support-duration"].value == 60


def test_o1_parameter_change_changes_result_fingerprint() -> None:
    table = tiny_x_table([0], {"axis-x": [0.5]})
    broad = _evaluate(
        table=table,
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(1.0),),
    )
    narrow = _evaluate(
        table=table,
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(0.1),),
    )

    assert broad.evidence_state is EvidenceState.DESIRED
    assert narrow.evidence_state is EvidenceState.UNACCEPTABLE
    assert broad.result_fingerprint != narrow.result_fingerprint


def test_o1_missing_phase_envelope_is_not_computable() -> None:
    result = _evaluate(
        table=tiny_x_table([0], {"axis-x": [0.0]}),
        phases=(_phase("phase-1", 0, 100, envelope_id=None),),
        envelopes=(_envelope(),),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.NOT_COMPUTABLE
    assert result.primary_value is None
    assert result.phase_results[0].diagnostics[0].error_code == ("anchor.o1.phase-envelope-missing")


def test_o1_replay_is_deterministic_and_does_not_mutate_x() -> None:
    table = tiny_x_table([0, 90], {"axis-x": [0.0, 2.0]})
    original = table.clone()

    first = _evaluate(
        table=table,
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(),),
    )
    second = _evaluate(
        table=table,
        phases=(_phase("phase-1", 0, 100),),
        envelopes=(_envelope(),),
    )

    assert first.result_fingerprint == second.result_fingerprint
    assert table.equals(original)


def test_o1_plugin_calls_shared_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    from pilot_assessment.anchors.primitives import envelopes

    real_kernel = envelopes.compute_o1_kernel
    calls: list[str] = []

    def spy(*args, **kwargs):
        calls.append(kwargs["phase"].phase_id)
        return real_kernel(*args, **kwargs)

    monkeypatch.setattr(envelopes, "compute_o1_kernel", spy)
    _evaluate(
        table=tiny_x_table([0, 50], {"axis-x": [0.0, 0.0]}),
        phases=(
            _phase("phase-1", 0, 50),
            _phase("phase-2", 50, 100),
        ),
        envelopes=(_envelope(),),
    )

    assert calls == ["phase-1", "phase-2"]


def test_o1_catalog_definition_and_artifact_recipe_are_exact() -> None:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O1"
    )
    definition = _definition()

    assert definition.plugin_id == catalog_entry.plugin_id
    assert definition.parameter_schema_id == catalog_entry.parameter_schema_id
    assert definition.required_streams == ("X",)
    assert definition.required_semantic_paths == (
        "semantic.envelopes",
        "semantic.phases",
    )
    assert definition.artifact_recipes == catalog_entry.artifact_recipes
