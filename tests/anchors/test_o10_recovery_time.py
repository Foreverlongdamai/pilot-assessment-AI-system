from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.o10_recovery_time import create_plugin
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    ProjectedSemanticScope,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    EnvelopeAxisLimit,
    EnvelopeDefinition,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    SemanticEvent,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
SHA_A = "a" * 64


def _envelope() -> EnvelopeDefinition:
    return EnvelopeDefinition(
        envelope_id="flight-envelope",
        target_id="flight-target",
        axis_limits=(
            EnvelopeAxisLimit(
                metric_id="position-error",
                desired_abs_max=1.0,
                adequate_abs_max=2.0,
                unit="m",
            ),
        ),
    )


def _event(
    event_id: str,
    t_ns: int,
    *,
    opportunity_end_t_ns: int | None = None,
) -> SemanticEvent:
    return SemanticEvent(
        event_id=event_id,
        event_type="disturbance",
        t_ns=t_ns,
        opportunity_end_t_ns=opportunity_end_t_ns,
        phase_id="phase-1",
        envelope_id="flight-envelope",
    )


def _contract() -> ResolvedInputTableContract:
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
            ResolvedInputFieldContract(
                field_name="position-error", dtype_id="f64", unit="m", nullable=False
            ),
        ),
    )


def _table(rows: tuple[tuple[int, float], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_row_index": pl.Series("source_row_index", range(len(rows)), dtype=pl.UInt64),
            "t_ns": pl.Series("t_ns", [row[0] for row in rows], dtype=pl.Int64),
            "in_session": pl.Series("in_session", [True for _row in rows], dtype=pl.Boolean),
            "position-error": pl.Series(
                "position-error", [row[1] for row in rows], dtype=pl.Float64
            ),
        }
    )


def _context(
    rows: tuple[tuple[int, float], ...],
    events: tuple[SemanticEvent, ...],
    *,
    session_end_t_ns: int,
    include_stream: bool = True,
) -> AnchorPluginContext:
    streams = {}
    if include_stream:
        streams["X"] = AlignedStreamView(
            modality="X",
            source_schema_id="x-raw-v0.1",
            aligned_schema_id="x-aligned-v0.1",
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
                "semantic.envelopes": [_envelope().model_dump(mode="json")],
            }
        ),
        input_table_contracts=(_contract(),),
    )


def _recipe(
    events: tuple[SemanticEvent, ...],
    *,
    phase_end_t_ns: int,
    session_end_t_ns: int,
) -> dict[str, object]:
    return {
        "window_policy": "marker-or-adequate-exit-v1",
        "window_id_prefix": "o10",
        "marker_event_ids": [event.event_id for event in events],
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": 0,
                "end_t_ns": phase_end_t_ns,
                "include_session_terminal_point": phase_end_t_ns == session_end_t_ns,
                "envelope_id": "flight-envelope",
            }
        ],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": session_end_t_ns,
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
            producer_anchor_id="O10",
            producer_plugin_id="o10-recovery-time",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O10 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    rows: tuple[tuple[int, float], ...],
    events: tuple[SemanticEvent, ...],
    *,
    session_end_t_ns: int = 20 * NS,
    phase_end_t_ns: int | None = None,
    include_stream: bool = True,
):
    phase_end = session_end_t_ns if phase_end_t_ns is None else phase_end_t_ns
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(
            rows,
            events,
            session_end_t_ns=session_end_t_ns,
            include_stream=include_stream,
        ),
        {
            "adequate_exit_confirmation_ns": 100_000_000,
            "desired_hold_ns": 2 * NS,
            "recovery_horizon_ns": 15 * NS,
        },
        _recipe(
            events,
            phase_end_t_ns=phase_end,
            session_end_t_ns=session_end_t_ns,
        ),
        ResolvedDependencies(results={}, artifacts={}, algorithm_profiles={}, preprocessing={}),
        emitter,
    )
    return measurement, emitter


def _state(value: float) -> EvidenceState:
    annotation = load_parameter_schema("o10-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o10_definition_declares_exact_inputs_and_recovery_artifact() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O10"
    assert definition.required_streams == ("X",)
    assert definition.required_semantic_paths == ("semantic.envelopes", "semantic.events")
    assert definition.dependencies == ()
    assert tuple(item.artifact_id for item in definition.artifact_recipes) == ("recovery-events",)


def test_marker_recovery_records_hold_onset_not_hold_confirmation() -> None:
    measurement, emitter = _compute(
        ((0, 3.0), (3 * NS, 0.0), (5 * NS, 0.0)),
        (_event("disturbance-1", 0),),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(3.0)
    assert _state(float(measurement.primary_value.value)) is EvidenceState.DESIRED
    assert measurement.event_results[0].raw_metrics["recovery-hold-confirmed-t-ns"].value == 5 * NS
    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "recovery-events"
    assert payload.frame.to_dicts() == [
        {
            "event_id": "disturbance-1",
            "onset_t_ns": 0,
            "recovered_t_ns": 3 * NS,
            "latency_ms": 3000.0,
            "missed": False,
        }
    ]


def test_confirmed_adequate_exit_uses_first_outside_sample_as_onset() -> None:
    measurement, emitter = _compute(
        (
            (0, 0.0),
            (NS, 3.0),
            (NS + 50_000_000, 3.0),
            (NS + 100_000_000, 3.0),
            (NS + 200_000_000, 0.0),
            (3 * NS + 200_000_000, 0.0),
        ),
        (),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(0.2)
    row = emitter.payloads[0][1].frame.to_dicts()[0]
    assert row["event_id"].startswith("o10-exit-")
    assert row["onset_t_ns"] == NS
    assert row["recovered_t_ns"] == NS + 200_000_000


def test_short_observable_horizon_is_a_finite_recovery_miss() -> None:
    event = _event("disturbance-1", 2 * NS, opportunity_end_t_ns=8 * NS)
    measurement, emitter = _compute(((0, 3.0), (20 * NS, 3.0)), (event,))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "recovery_missed"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "recovery_missed"
    assert measurement.raw_metrics["observed_wait"].value == pytest.approx(6.0)
    assert emitter.payloads[0][1].frame.to_dicts()[0] == {
        "event_id": "disturbance-1",
        "onset_t_ns": 2 * NS,
        "recovered_t_ns": None,
        "latency_ms": 6000.0,
        "missed": True,
    }


@pytest.mark.parametrize(
    ("latency_ns", "expected_state"),
    (
        (5 * NS, EvidenceState.DESIRED),
        (10 * NS, EvidenceState.ADEQUATE),
        (10 * NS + 1, EvidenceState.UNACCEPTABLE),
    ),
)
def test_o10_exact_five_and_ten_second_boundaries(
    latency_ns: int, expected_state: EvidenceState
) -> None:
    measurement, _emitter = _compute(
        ((0, 3.0), (latency_ns, 0.0), (latency_ns + 2 * NS, 0.0)),
        (_event("disturbance-1", 0),),
    )

    assert measurement.primary_value is not None
    assert _state(float(measurement.primary_value.value)) is expected_state


def test_early_miss_vetoes_session_but_later_event_trace_is_retained() -> None:
    events = (
        _event("disturbance-1", 0, opportunity_end_t_ns=5 * NS),
        _event("disturbance-2", 10 * NS),
    )
    measurement, emitter = _compute(
        ((0, 3.0), (5 * NS, 3.0), (10 * NS, 3.0), (12 * NS, 0.0), (14 * NS, 0.0)),
        events,
        session_end_t_ns=30 * NS,
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "recovery_missed"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.details["missed_event_ids"] == [
        "disturbance-1"
    ]
    assert len(measurement.event_results) == 2
    assert measurement.event_results[1].primary_value is not None
    assert measurement.event_results[1].primary_value.value == pytest.approx(2.0)
    assert emitter.payloads[0][1].frame.height == 2


def test_multi_event_session_uses_the_worst_successful_recovery() -> None:
    events = (_event("disturbance-1", 0), _event("disturbance-2", 10 * NS))
    measurement, emitter = _compute(
        (
            (0, 3.0),
            (2 * NS, 0.0),
            (4 * NS, 0.0),
            (10 * NS, 3.0),
            (15 * NS, 0.0),
            (17 * NS, 0.0),
        ),
        events,
        session_end_t_ns=30 * NS,
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(5.0)
    assert measurement.classification_override_candidate is None
    assert [
        item.primary_value.value for item in measurement.event_results if item.primary_value
    ] == [
        pytest.approx(2.0),
        pytest.approx(5.0),
    ]
    assert emitter.payloads[0][1].frame.height == 2


def test_no_marker_or_adequate_exit_is_not_applicable() -> None:
    measurement, emitter = _compute(((0, 0.0), (20 * NS, 0.0)), ())

    assert measurement.calculation_status.value == "not_applicable"
    assert measurement.primary_value is None
    assert measurement.event_results == ()
    assert emitter.payloads == []


def test_true_absence_of_x_is_missing_input_not_poor_performance() -> None:
    measurement, emitter = _compute((), (_event("disturbance-1", 0),), include_stream=False)

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert emitter.payloads == []
