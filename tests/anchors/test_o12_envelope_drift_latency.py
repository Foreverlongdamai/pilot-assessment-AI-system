from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.o12_envelope_drift_latency import create_plugin
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    ProjectedSemanticScope,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    ControlEffectMapping,
    EnvelopeAxisLimit,
    EnvelopeDefinition,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
MS = 1_000_000
SAMPLE_PERIOD_NS = 10 * MS
SHA_A = "a" * 64


@dataclass(frozen=True)
class _StateSegment:
    start_t_ns: int
    end_t_ns: int
    value: float


@dataclass(frozen=True)
class _Pulse:
    start_t_ns: int
    end_t_ns: int
    value: float


def _envelope() -> EnvelopeDefinition:
    return EnvelopeDefinition(
        envelope_id="envelope-1",
        target_id="target-1",
        axis_limits=(
            EnvelopeAxisLimit(
                metric_id="state-error",
                desired_abs_max=1.0,
                adequate_abs_max=2.0,
                unit="m",
            ),
        ),
    )


def _mapping(*, correct_sign: int = -1) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id="mapping-a",
        state_axis_id="state-error",
        control_channel_id="control-a",
        correct_sign=correct_sign,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=1.0,
    )


def _rows(
    *,
    start_t_ns: int,
    end_t_ns: int,
    state_segments: tuple[_StateSegment, ...] = (),
    control_pulses: tuple[_Pulse, ...] = (),
    baseline_control: float = 0.0,
) -> tuple[tuple[int, float, float], ...]:
    rows: list[tuple[int, float, float]] = []
    for t_ns in range(start_t_ns, end_t_ns + SAMPLE_PERIOD_NS, SAMPLE_PERIOD_NS):
        state = 0.0
        control = baseline_control
        for segment in state_segments:
            if segment.start_t_ns <= t_ns < segment.end_t_ns:
                state = segment.value
        for pulse in control_pulses:
            if pulse.start_t_ns <= t_ns < pulse.end_t_ns:
                control = pulse.value
        rows.append((t_ns, state, control))
    return tuple(rows)


def _correction_pulse(
    filtered_onset_t_ns: int,
    *,
    value: float,
    duration_ns: int = 150 * MS,
) -> _Pulse:
    raw_start = filtered_onset_t_ns - SAMPLE_PERIOD_NS
    return _Pulse(raw_start, raw_start + duration_ns, value)


def _contracts() -> tuple[ResolvedInputTableContract, ...]:
    common = (
        ResolvedInputFieldContract(
            field_name="source_row_index", dtype_id="u64", unit="index", nullable=False
        ),
        ResolvedInputFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
        ResolvedInputFieldContract(
            field_name="in_session", dtype_id="bool", unit="bool", nullable=False
        ),
    )
    return (
        ResolvedInputTableContract(
            modality="U",
            table_role="samples",
            stream_aligned_schema_id="u-aligned-v0.1",
            table_aligned_schema_id="u-samples-aligned-v0.1",
            coordinate_frame_id="pilot-controls",
            fields=(
                *common,
                ResolvedInputFieldContract(
                    field_name="control-a", dtype_id="f64", unit="ratio", nullable=False
                ),
            ),
        ),
        ResolvedInputTableContract(
            modality="X",
            table_role="samples",
            stream_aligned_schema_id="x-aligned-v0.1",
            table_aligned_schema_id="x-samples-aligned-v0.1",
            coordinate_frame_id="task-error",
            fields=(
                *common,
                ResolvedInputFieldContract(
                    field_name="state-error", dtype_id="f64", unit="m", nullable=False
                ),
            ),
        ),
    )


def _tables(rows: tuple[tuple[int, float, float], ...]) -> tuple[pl.DataFrame, pl.DataFrame]:
    common = {
        "source_row_index": pl.Series("source_row_index", range(len(rows)), dtype=pl.UInt64),
        "t_ns": pl.Series("t_ns", [row[0] for row in rows], dtype=pl.Int64),
        "in_session": pl.Series("in_session", [True for _row in rows], dtype=pl.Boolean),
    }
    return (
        pl.DataFrame(
            {
                **common,
                "state-error": pl.Series("state-error", [row[1] for row in rows], dtype=pl.Float64),
            }
        ),
        pl.DataFrame(
            {
                **common,
                "control-a": pl.Series("control-a", [row[2] for row in rows], dtype=pl.Float64),
            }
        ),
    )


def _context(
    rows: tuple[tuple[int, float, float], ...],
    *,
    session_end_t_ns: int,
    mapping: ControlEffectMapping,
    include_x: bool = True,
    include_u: bool = True,
) -> AnchorPluginContext:
    x_table, u_table = _tables(rows)
    streams = {}
    if include_x:
        streams["X"] = AlignedStreamView(
            modality="X",
            source_schema_id="x-raw-v0.1",
            aligned_schema_id="x-aligned-v0.1",
            clock_id="master-clock",
            tables={"samples": x_table},
            json_artifacts={},
            file_artifacts={},
            source_checksums={"samples": SHA_A},
        )
    if include_u:
        streams["U"] = AlignedStreamView(
            modality="U",
            source_schema_id="u-raw-v0.1",
            aligned_schema_id="u-aligned-v0.1",
            clock_id="master-clock",
            tables={"samples": u_table},
            json_artifacts={},
            file_artifacts={},
            source_checksums={"samples": SHA_A},
        )
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=session_end_t_ns,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams=streams,
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.envelopes": [_envelope().model_dump(mode="json")],
                "semantic.control_mappings": [mapping.model_dump(mode="json")],
            }
        ),
        input_table_contracts=_contracts(),
    )


def _recipe(
    *,
    phase_start_t_ns: int,
    phase_end_t_ns: int,
    session_end_t_ns: int,
) -> dict[str, object]:
    return {
        "window_policy": "bound-envelope-drift-correction-v1",
        "window_id_prefix": "o12",
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": phase_start_t_ns,
                "end_t_ns": phase_end_t_ns,
                "include_session_terminal_point": phase_end_t_ns == session_end_t_ns,
                "envelope_id": "envelope-1",
            }
        ],
        "control_mapping_ids": ["mapping-a"],
        "x_table_role": "samples",
        "u_table_role": "samples",
        "x_timestamp_column": "t_ns",
        "u_timestamp_column": "t_ns",
        "x_in_session_column": "in_session",
        "u_in_session_column": "in_session",
        "x_stable_keys": ["source_row_index"],
        "u_stable_keys": ["source_row_index"],
        "x_gap_threshold_ns": 50 * MS,
        "u_gap_threshold_ns": 50 * MS,
    }


@dataclass
class _Emitter:
    payloads: list[tuple[str, TabularArtifactPayload]]

    def stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        self.payloads.append((artifact_id, payload))
        return AnchorArtifactRef(
            artifact_id=artifact_id,
            kind=payload.artifact_kind,
            schema_id=payload.schema_id,
            logical_content_sha256=SHA_A,
            storage_file_sha256=None,
            row_count=payload.frame.height,
            start_t_ns=payload.start_t_ns,
            end_t_ns=payload.end_t_ns,
            grid_hash=payload.grid_hash,
            producer_anchor_id="O12",
            producer_plugin_id="o12-envelope-drift-latency",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O12 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    rows: tuple[tuple[int, float, float], ...],
    *,
    session_end_t_ns: int = 7 * NS,
    phase_start_t_ns: int = 0,
    phase_end_t_ns: int | None = None,
    mapping: ControlEffectMapping | None = None,
    include_x: bool = True,
    include_u: bool = True,
):
    active_mapping = _mapping() if mapping is None else mapping
    phase_end = session_end_t_ns if phase_end_t_ns is None else phase_end_t_ns
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(
            rows,
            session_end_t_ns=session_end_t_ns,
            mapping=active_mapping,
            include_x=include_x,
            include_u=include_u,
        ),
        {
            "exit_confirmation_ns": 100 * MS,
            "causal_median_window_ns": 20 * MS,
            "baseline_lookback_ns": NS,
            "correction_horizon_ns": 2 * NS,
            "control_excursion_threshold_pct": 5.0,
            "minimum_excursion_duration_ns": 100 * MS,
        },
        _recipe(
            phase_start_t_ns=phase_start_t_ns,
            phase_end_t_ns=phase_end,
            session_end_t_ns=session_end_t_ns,
        ),
        ResolvedDependencies(results={}, artifacts={}, algorithm_profiles={}, preprocessing={}),
        emitter,
    )
    return measurement, emitter


def _state(value_ms: float) -> EvidenceState:
    annotation = load_parameter_schema("o12-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value_ms, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o12_definition_declares_exact_inputs_and_correction_artifact() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O12"
    assert definition.required_streams == ("X", "U")
    assert definition.required_semantic_paths == (
        "semantic.control_mappings",
        "semantic.envelopes",
    )
    assert definition.dependencies == ()
    assert tuple(item.artifact_id for item in definition.artifact_recipes) == ("correction-events",)


def test_exit_is_confirmed_later_but_latency_starts_at_first_outside_sample() -> None:
    exit_t_ns = 2 * NS
    onset_t_ns = exit_t_ns + 250 * MS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(_correction_pulse(onset_t_ns, value=-0.10),),
    )

    measurement, emitter = _compute(rows)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)
    assert _state(float(measurement.primary_value.value)) is EvidenceState.DESIRED
    artifact_row = emitter.payloads[0][1].frame.to_dicts()[0]
    assert artifact_row["exit_t_ns"] == exit_t_ns
    assert artifact_row["onset_t_ns"] == onset_t_ns
    assert artifact_row["correct_sign"] is True


@pytest.mark.parametrize(("duration_ns", "applicable"), ((90 * MS, False), (100 * MS, True)))
def test_exit_confirmation_duration_boundary_is_inclusive(
    duration_ns: int, applicable: bool
) -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + duration_ns, 1.5),),
        control_pulses=(_correction_pulse(exit_t_ns + 250 * MS, value=-0.10),),
    )

    measurement, emitter = _compute(rows)

    assert (measurement.calculation_status.value == "computed") is applicable
    assert (len(emitter.payloads) == 1) is applicable


def test_negative_state_error_flips_the_mapping_correction_sign() -> None:
    exit_t_ns = 2 * NS
    onset_t_ns = exit_t_ns + 250 * MS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, -1.5),),
        control_pulses=(_correction_pulse(onset_t_ns, value=0.10),),
    )

    measurement, emitter = _compute(rows)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)
    assert emitter.payloads[0][1].frame.to_dicts()[0]["correct_sign"] is True


def test_short_nonempty_phase_pre_window_is_used_as_baseline() -> None:
    exit_t_ns = 2 * NS
    phase_start = exit_t_ns - 50 * MS
    rows = _rows(
        start_t_ns=phase_start,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(_correction_pulse(exit_t_ns + 250 * MS, value=0.10),),
        baseline_control=0.20,
    )

    measurement, _emitter = _compute(rows, phase_start_t_ns=phase_start)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)


def test_mapping_trim_is_used_only_when_no_pre_exit_sample_exists() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=exit_t_ns,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(_correction_pulse(exit_t_ns + 250 * MS, value=-0.10),),
    )

    measurement, _emitter = _compute(rows, phase_start_t_ns=exit_t_ns)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)


@pytest.mark.parametrize(("amplitude", "missed"), ((-0.05, True), (-0.050001, False)))
def test_excursion_threshold_is_strict_and_duration_boundary_is_inclusive(
    amplitude: float, missed: bool
) -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(
            _correction_pulse(
                exit_t_ns + 250 * MS,
                value=amplitude,
                duration_ns=100 * MS,
            ),
        ),
    )

    measurement, _emitter = _compute(rows)

    assert (measurement.primary_value_reason == "correction_missed") is missed
    assert (measurement.primary_value is None) is missed


@pytest.mark.parametrize(
    ("latency_ms", "expected_state"),
    (
        (300, EvidenceState.DESIRED),
        (800, EvidenceState.ADEQUATE),
        (810, EvidenceState.UNACCEPTABLE),
    ),
)
def test_exact_three_hundred_and_eight_hundred_millisecond_boundaries(
    latency_ms: int, expected_state: EvidenceState
) -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(_correction_pulse(exit_t_ns + latency_ms * MS, value=-0.10),),
    )

    measurement, _emitter = _compute(rows)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(float(latency_ms))
    assert _state(float(measurement.primary_value.value)) is expected_state


def test_wrong_direction_first_vetoes_a_later_correct_correction() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(
            _correction_pulse(exit_t_ns + 200 * MS, value=0.10),
            _correction_pulse(exit_t_ns + 600 * MS, value=-0.10),
        ),
    )

    measurement, emitter = _compute(rows)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "correction_missed"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "correction_missed"
    artifact_row = emitter.payloads[0][1].frame.to_dicts()[0]
    assert artifact_row["onset_t_ns"] == exit_t_ns + 200 * MS
    assert artifact_row["correct_sign"] is False
    assert artifact_row["missed"] is True


def test_subthreshold_wrong_direction_noise_does_not_veto_correction() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
        control_pulses=(
            _correction_pulse(exit_t_ns + 200 * MS, value=0.049),
            _correction_pulse(exit_t_ns + 600 * MS, value=-0.10),
        ),
    )

    measurement, _emitter = _compute(rows)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(600.0)
    assert measurement.classification_override_candidate is None


def test_no_correction_is_a_finite_two_second_computed_miss() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=6 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
    )

    measurement, emitter = _compute(rows)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "correction_missed"
    assert measurement.raw_metrics["observed_wait"].value == pytest.approx(2000.0)
    assert emitter.payloads[0][1].frame.to_dicts()[0]["latency_ms"] == pytest.approx(2000.0)


def test_early_miss_vetoes_session_but_later_exit_trace_is_retained() -> None:
    first_exit = NS
    second_exit = 4 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=7 * NS,
        state_segments=(
            _StateSegment(first_exit, first_exit + 300 * MS, 1.5),
            _StateSegment(second_exit, second_exit + 300 * MS, 1.5),
        ),
        control_pulses=(_correction_pulse(second_exit + 250 * MS, value=-0.10),),
    )

    measurement, emitter = _compute(rows)

    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "correction_missed"
    assert len(measurement.event_results) == 2
    assert measurement.event_results[1].primary_value is not None
    assert measurement.event_results[1].primary_value.value == pytest.approx(250.0)
    assert emitter.payloads[0][1].frame.height == 2


def test_multi_exit_session_uses_worst_successful_latency() -> None:
    first_exit = NS
    second_exit = 4 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=7 * NS,
        state_segments=(
            _StateSegment(first_exit, first_exit + 300 * MS, 1.5),
            _StateSegment(second_exit, second_exit + 300 * MS, 1.5),
        ),
        control_pulses=(
            _correction_pulse(first_exit + 250 * MS, value=-0.10),
            _correction_pulse(second_exit + 800 * MS, value=-0.10),
        ),
    )

    measurement, emitter = _compute(rows)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(800.0)
    assert emitter.payloads[0][1].frame.height == 2


def test_never_leaving_desired_envelope_is_not_applicable() -> None:
    rows = _rows(start_t_ns=0, end_t_ns=5 * NS)

    measurement, emitter = _compute(rows)

    assert measurement.calculation_status.value == "not_applicable"
    assert measurement.event_results == ()
    assert emitter.payloads == []


def test_missing_state_axis_effect_mapping_is_not_computable() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
    )
    incompatible = _mapping().model_copy(update={"state_axis_id": "other-axis"})

    measurement, emitter = _compute(rows, mapping=incompatible)

    assert measurement.calculation_status.value == "not_computable"
    assert measurement.primary_value is None
    assert emitter.payloads == []


def test_true_absence_of_u_after_a_confirmed_exit_is_missing_input() -> None:
    exit_t_ns = 2 * NS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        state_segments=(_StateSegment(exit_t_ns, exit_t_ns + 300 * MS, 1.5),),
    )

    measurement, emitter = _compute(rows, include_u=False)

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert emitter.payloads == []


def test_true_absence_of_x_prevents_opportunity_detection() -> None:
    rows = _rows(start_t_ns=0, end_t_ns=5 * NS)

    measurement, emitter = _compute(rows, include_x=False)

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert emitter.payloads == []
