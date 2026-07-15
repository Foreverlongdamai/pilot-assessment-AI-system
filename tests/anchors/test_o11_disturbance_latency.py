from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.o11_disturbance_latency import create_plugin
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
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    SemanticEvent,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
MS = 1_000_000
SAMPLE_PERIOD_NS = 10 * MS
SHA_A = "a" * 64


@dataclass(frozen=True)
class _Pulse:
    channel_id: str
    start_t_ns: int
    end_t_ns: int
    value: float


def _mapping(
    mapping_id: str = "mapping-a",
    channel_id: str = "control-a",
    *,
    correct_sign: int = 1,
) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=mapping_id,
        state_axis_id=f"axis-{mapping_id}",
        control_channel_id=channel_id,
        correct_sign=correct_sign,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=1.0,
    )


def _event(
    event_id: str,
    t_ns: int,
    mapping_ids: tuple[str, ...] = ("mapping-a",),
    *,
    opportunity_end_t_ns: int | None = None,
) -> SemanticEvent:
    return SemanticEvent(
        event_id=event_id,
        event_type="disturbance",
        t_ns=t_ns,
        opportunity_end_t_ns=opportunity_end_t_ns,
        phase_id="phase-1",
        control_mapping_ids=mapping_ids,
    )


def _rows(
    *,
    start_t_ns: int,
    end_t_ns: int,
    pulses: tuple[_Pulse, ...] = (),
    baseline_a: float = 0.0,
    baseline_b: float = 0.0,
) -> tuple[tuple[int, float, float], ...]:
    rows: list[tuple[int, float, float]] = []
    for t_ns in range(start_t_ns, end_t_ns + SAMPLE_PERIOD_NS, SAMPLE_PERIOD_NS):
        values = {"control-a": baseline_a, "control-b": baseline_b}
        for pulse in pulses:
            if pulse.start_t_ns <= t_ns < pulse.end_t_ns:
                values[pulse.channel_id] = pulse.value
        rows.append((t_ns, values["control-a"], values["control-b"]))
    return tuple(rows)


def _response_pulse(
    event_t_ns: int,
    filtered_onset_t_ns: int,
    *,
    channel_id: str = "control-a",
    value: float = 0.10,
    duration_ns: int = 150 * MS,
) -> _Pulse:
    del event_t_ns
    raw_start = filtered_onset_t_ns - SAMPLE_PERIOD_NS
    return _Pulse(channel_id, raw_start, raw_start + duration_ns, value)


def _contract() -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="U",
        table_role="samples",
        stream_aligned_schema_id="u-aligned-v0.1",
        table_aligned_schema_id="u-samples-aligned-v0.1",
        coordinate_frame_id="pilot-controls",
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
            ResolvedInputFieldContract(
                field_name="control-a", dtype_id="f64", unit="ratio", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="control-b", dtype_id="f64", unit="ratio", nullable=False
            ),
        ),
    )


def _table(rows: tuple[tuple[int, float, float], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_row_index": pl.Series("source_row_index", range(len(rows)), dtype=pl.UInt64),
            "t_ns": pl.Series("t_ns", [row[0] for row in rows], dtype=pl.Int64),
            "in_session": pl.Series("in_session", [True for _row in rows], dtype=pl.Boolean),
            "control-a": pl.Series("control-a", [row[1] for row in rows], dtype=pl.Float64),
            "control-b": pl.Series("control-b", [row[2] for row in rows], dtype=pl.Float64),
        }
    )


def _context(
    rows: tuple[tuple[int, float, float], ...],
    events: tuple[SemanticEvent, ...],
    mappings: tuple[ControlEffectMapping, ...],
    *,
    session_end_t_ns: int,
    include_stream: bool = True,
) -> AnchorPluginContext:
    streams = {}
    if include_stream:
        streams["U"] = AlignedStreamView(
            modality="U",
            source_schema_id="u-raw-v0.1",
            aligned_schema_id="u-aligned-v0.1",
            clock_id="master-clock",
            tables={"samples": _table(rows)},
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
                "semantic.events": [event.model_dump(mode="json") for event in events],
                "semantic.control_mappings": [
                    mapping.model_dump(mode="json") for mapping in mappings
                ],
            }
        ),
        input_table_contracts=(_contract(),),
    )


def _recipe(
    events: tuple[SemanticEvent, ...],
    *,
    phase_start_t_ns: int,
    phase_end_t_ns: int,
    session_end_t_ns: int,
    gap_threshold_ns: int = 50 * MS,
) -> dict[str, object]:
    return {
        "window_policy": "bound-disturbance-response-v1",
        "window_id_prefix": "o11",
        "event_ids": [event.event_id for event in events],
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": phase_start_t_ns,
                "end_t_ns": phase_end_t_ns,
                "include_session_terminal_point": phase_end_t_ns == session_end_t_ns,
            }
        ],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": gap_threshold_ns,
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
            producer_anchor_id="O11",
            producer_plugin_id="o11-disturbance-latency",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O11 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    rows: tuple[tuple[int, float, float], ...],
    events: tuple[SemanticEvent, ...],
    mappings: tuple[ControlEffectMapping, ...] = (_mapping(),),
    *,
    session_end_t_ns: int = 6 * NS,
    phase_start_t_ns: int = 0,
    phase_end_t_ns: int | None = None,
    include_stream: bool = True,
    gap_threshold_ns: int = 50 * MS,
):
    phase_end = session_end_t_ns if phase_end_t_ns is None else phase_end_t_ns
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(
            rows,
            events,
            mappings,
            session_end_t_ns=session_end_t_ns,
            include_stream=include_stream,
        ),
        {
            "baseline_lookback_ns": NS,
            "causal_median_window_ns": 20 * MS,
            "control_excursion_threshold_pct": 5.0,
            "minimum_excursion_duration_ns": 100 * MS,
            "response_horizon_ns": 2 * NS,
        },
        _recipe(
            events,
            phase_start_t_ns=phase_start_t_ns,
            phase_end_t_ns=phase_end,
            session_end_t_ns=session_end_t_ns,
            gap_threshold_ns=gap_threshold_ns,
        ),
        ResolvedDependencies(results={}, artifacts={}, algorithm_profiles={}, preprocessing={}),
        emitter,
    )
    return measurement, emitter


def _state(value_ms: float) -> EvidenceState:
    annotation = load_parameter_schema("o11-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value_ms, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o11_definition_declares_exact_inputs_and_response_artifact() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O11"
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == (
        "semantic.control_mappings",
        "semantic.events",
    )
    assert definition.dependencies == ()
    assert tuple(item.artifact_id for item in definition.artifact_recipes) == ("response-events",)


def test_trailing_causal_median_and_earliest_mapped_channel_determine_onset() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns, ("mapping-a", "mapping-b"))
    mappings = (_mapping(), _mapping("mapping-b", "control-b"))
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        pulses=(
            _response_pulse(event_t_ns, event_t_ns + 800 * MS),
            _response_pulse(
                event_t_ns,
                event_t_ns + 250 * MS,
                channel_id="control-b",
            ),
        ),
    )

    measurement, emitter = _compute(rows, (event,), mappings)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)
    assert _state(float(measurement.primary_value.value)) is EvidenceState.DESIRED
    rows_by_channel = {row["channel_id"]: row for row in emitter.payloads[0][1].frame.to_dicts()}
    assert rows_by_channel["control-b"]["onset_t_ns"] == event_t_ns + 250 * MS
    assert rows_by_channel["control-b"]["correct_sign"] is True


def test_short_nonempty_phase_pre_window_is_used_as_baseline() -> None:
    event_t_ns = 2 * NS
    phase_start = event_t_ns - 50 * MS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=phase_start,
        end_t_ns=4 * NS,
        baseline_a=0.20,
        pulses=(
            _response_pulse(
                event_t_ns,
                event_t_ns + 250 * MS,
                value=0.30,
            ),
        ),
    )

    measurement, _emitter = _compute(
        rows,
        (event,),
        phase_start_t_ns=phase_start,
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)


def test_trim_is_used_only_when_no_pre_event_sample_exists() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=event_t_ns,
        end_t_ns=4 * NS,
        pulses=(_response_pulse(event_t_ns, event_t_ns + 250 * MS),),
    )

    measurement, _emitter = _compute(
        rows,
        (event,),
        phase_start_t_ns=event_t_ns,
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)


@pytest.mark.parametrize(
    ("amplitude", "missed"),
    ((0.05, True), (0.050001, False)),
)
def test_excursion_threshold_is_strict_and_duration_boundary_is_inclusive(
    amplitude: float, missed: bool
) -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=0,
        end_t_ns=4 * NS,
        pulses=(
            _response_pulse(
                event_t_ns,
                event_t_ns + 250 * MS,
                value=amplitude,
                duration_ns=100 * MS,
            ),
        ),
    )

    measurement, _emitter = _compute(rows, (event,))

    assert (measurement.primary_value_reason == "response_missed") is missed
    assert (measurement.primary_value is None) is missed


@pytest.mark.parametrize(
    ("latency_ms", "expected_state"),
    (
        (500, EvidenceState.DESIRED),
        (1000, EvidenceState.ADEQUATE),
        (1010, EvidenceState.UNACCEPTABLE),
    ),
)
def test_exact_five_hundred_and_one_thousand_millisecond_boundaries(
    latency_ms: int, expected_state: EvidenceState
) -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    onset = event_t_ns + latency_ms * MS
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        pulses=(_response_pulse(event_t_ns, onset),),
    )

    measurement, _emitter = _compute(rows, (event,))

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(float(latency_ms))
    assert _state(float(measurement.primary_value.value)) is expected_state


def test_wrong_direction_first_vetoes_a_later_correct_response() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        pulses=(
            _response_pulse(event_t_ns, event_t_ns + 200 * MS, value=-0.10),
            _response_pulse(event_t_ns, event_t_ns + 600 * MS, value=0.10),
        ),
    )

    measurement, emitter = _compute(rows, (event,))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "response_missed"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "response_missed"
    row = emitter.payloads[0][1].frame.to_dicts()[0]
    assert row["onset_t_ns"] == event_t_ns + 200 * MS
    assert row["correct_sign"] is False
    assert row["missed"] is True


def test_subthreshold_wrong_direction_noise_does_not_veto_correct_response() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        pulses=(
            _response_pulse(event_t_ns, event_t_ns + 200 * MS, value=-0.049),
            _response_pulse(event_t_ns, event_t_ns + 600 * MS, value=0.10),
        ),
    )

    measurement, _emitter = _compute(rows, (event,))

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(600.0)
    assert measurement.classification_override_candidate is None


def test_mapping_correct_sign_is_applied_to_negative_control_response() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(
        start_t_ns=0,
        end_t_ns=5 * NS,
        pulses=(_response_pulse(event_t_ns, event_t_ns + 250 * MS, value=-0.10),),
    )

    measurement, emitter = _compute(
        rows,
        (event,),
        (_mapping(correct_sign=-1),),
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(250.0)
    assert emitter.payloads[0][1].frame.to_dicts()[0]["correct_sign"] is True


def test_no_response_is_a_finite_two_second_computed_miss() -> None:
    event_t_ns = 2 * NS
    event = _event("disturbance-1", event_t_ns)
    rows = _rows(start_t_ns=0, end_t_ns=5 * NS)

    measurement, emitter = _compute(rows, (event,))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "response_missed"
    assert measurement.raw_metrics["observed_wait"].value == pytest.approx(2000.0)
    assert emitter.payloads[0][1].frame.to_dicts()[0]["latency_ms"] == pytest.approx(2000.0)


def test_early_miss_vetoes_session_but_later_event_trace_is_retained() -> None:
    first_t_ns = NS
    second_t_ns = 4 * NS
    events = (
        _event("disturbance-1", first_t_ns),
        _event("disturbance-2", second_t_ns),
    )
    rows = _rows(
        start_t_ns=0,
        end_t_ns=7 * NS,
        pulses=(_response_pulse(second_t_ns, second_t_ns + 250 * MS),),
    )

    measurement, emitter = _compute(rows, events, session_end_t_ns=7 * NS)

    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "response_missed"
    assert len(measurement.event_results) == 2
    assert measurement.event_results[1].primary_value is not None
    assert measurement.event_results[1].primary_value.value == pytest.approx(250.0)
    assert emitter.payloads[0][1].frame.height == 2


def test_multi_event_session_uses_worst_successful_latency() -> None:
    first_t_ns = NS
    second_t_ns = 4 * NS
    events = (
        _event("disturbance-1", first_t_ns),
        _event("disturbance-2", second_t_ns),
    )
    rows = _rows(
        start_t_ns=0,
        end_t_ns=7 * NS,
        pulses=(
            _response_pulse(first_t_ns, first_t_ns + 250 * MS),
            _response_pulse(second_t_ns, second_t_ns + 800 * MS),
        ),
    )

    measurement, emitter = _compute(rows, events, session_end_t_ns=7 * NS)

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(800.0)
    assert measurement.classification_override_candidate is None
    assert emitter.payloads[0][1].frame.height == 2


def test_missing_event_mapping_is_not_computable() -> None:
    event = _event("disturbance-1", 2 * NS, ())
    rows = _rows(start_t_ns=0, end_t_ns=4 * NS)

    measurement, emitter = _compute(rows, (event,))

    assert measurement.calculation_status.value == "not_computable"
    assert measurement.primary_value is None
    assert emitter.payloads == []


def test_true_absence_of_u_is_missing_input() -> None:
    event = _event("disturbance-1", 2 * NS)

    measurement, emitter = _compute((), (event,), include_stream=False)

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert emitter.payloads == []


def test_no_bound_disturbance_event_is_not_applicable() -> None:
    rows = _rows(start_t_ns=0, end_t_ns=4 * NS)

    measurement, emitter = _compute(rows, ())

    assert measurement.calculation_status.value == "not_applicable"
    assert measurement.event_results == ()
    assert emitter.payloads == []
