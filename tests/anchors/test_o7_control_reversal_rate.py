from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.plugins.o7_control_reversal_rate import create_plugin
from pilot_assessment.anchors.primitives.movement import (
    MovementChannelResult,
    MovementKernelResult,
    MovementSupportSegment,
    MovementTurningPoint,
)
from pilot_assessment.anchors.primitives.reversal import compute_o7_kernel
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingArtifactIdentity,
    ProjectedSemanticScope,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import ControlEffectMapping
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow

NS = 1_000_000_000
MIN_SEPARATION_NS = 150_000_000
SHA_A = "a" * 64
SHA_B = "b" * 64


def _mapping(channel_id: str) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=f"mapping-{channel_id}",
        state_axis_id=f"axis-{channel_id}",
        control_channel_id=channel_id,
        correct_sign=1,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=1.0,
    )


def _turning_points(
    reversal_count: int,
    *,
    start_t_ns: int = 0,
    separation_ns: int = MIN_SEPARATION_NS,
    amplitude_pct: float = 2.0,
) -> tuple[MovementTurningPoint, ...]:
    return tuple(
        MovementTurningPoint(
            t_ns=start_t_ns + index * separation_ns,
            value_pct=amplitude_pct if index % 2 else 0.0,
        )
        for index in range(reversal_count + 1)
    )


def _channel(
    channel_id: str,
    *,
    support_segments: tuple[MovementSupportSegment, ...] = (MovementSupportSegment(0, NS),),
    turning_points: tuple[MovementTurningPoint, ...] = (),
) -> MovementChannelResult:
    return MovementChannelResult(
        channel_id=channel_id,
        observed_support_duration_ns=sum(
            segment.end_t_ns - segment.start_t_ns for segment in support_segments
        ),
        support_segments=support_segments,
        turning_points=turning_points,
        movements=(),
        grid_sample_count=0,
        short_filter_bypass_count=0,
    )


def _kernel(*channels: MovementChannelResult) -> MovementKernelResult:
    starts = tuple(
        segment.start_t_ns for channel in channels for segment in channel.support_segments
    )
    ends = tuple(segment.end_t_ns for channel in channels for segment in channel.support_segments)
    return MovementKernelResult(
        status="computed",
        reason=None,
        channels=tuple(sorted(channels, key=lambda channel: channel.channel_id)),
        sample_count=sum(len(channel.turning_points) for channel in channels),
        source_start_t_ns=min(starts),
        source_end_t_ns=max(ends),
        gap_count=0,
        max_gap_ns=None,
    )


def _compute_kernel(movement: MovementKernelResult, channel_ids: tuple[str, ...]):
    return compute_o7_kernel(
        movement,
        channel_ids,
        minimum_reversal_amplitude_pct=2.0,
        minimum_reversal_separation_ns=MIN_SEPARATION_NS,
    )


def _state(value: float) -> EvidenceState:
    annotation = load_parameter_schema("o7-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value, {}, None, compile_scorer_policy(annotation)
    )
    return state


@pytest.mark.parametrize(
    ("reversal_count", "expected_state"),
    ((1, EvidenceState.DESIRED), (2, EvidenceState.ADEQUATE), (4, EvidenceState.UNACCEPTABLE)),
)
def test_o7_exact_two_and_four_hz_boundaries(
    reversal_count: int, expected_state: EvidenceState
) -> None:
    result = _compute_kernel(
        _kernel(_channel("stick", turning_points=_turning_points(reversal_count))),
        ("stick",),
    )

    assert result.status == "computed"
    assert result.reversal_rate_hz == pytest.approx(float(reversal_count))
    assert _state(result.reversal_rate_hz) is expected_state


def test_o7_amplitude_and_separation_thresholds_are_inclusive() -> None:
    exact = _compute_kernel(
        _kernel(_channel("stick", turning_points=_turning_points(1))), ("stick",)
    )
    low_amplitude = _compute_kernel(
        _kernel(
            _channel(
                "stick",
                turning_points=_turning_points(1, amplitude_pct=1.999999),
            )
        ),
        ("stick",),
    )
    short_separation = _compute_kernel(
        _kernel(
            _channel(
                "stick",
                turning_points=_turning_points(1, separation_ns=MIN_SEPARATION_NS - 1),
            )
        ),
        ("stick",),
    )

    assert exact.total_reversal_count == 1
    assert low_amplitude.total_reversal_count == 0
    assert short_separation.total_reversal_count == 0


def test_o7_never_pairs_turning_points_across_support_gaps() -> None:
    segments = (
        MovementSupportSegment(0, 200_000_000),
        MovementSupportSegment(NS, 1_200_000_000),
    )
    movement = _kernel(
        _channel(
            "stick",
            support_segments=segments,
            turning_points=(
                MovementTurningPoint(100_000_000, 0.0),
                MovementTurningPoint(1_100_000_000, 10.0),
            ),
        )
    )

    result = _compute_kernel(movement, ("stick",))

    assert result.status == "computed"
    assert result.total_reversal_count == 0
    assert result.reversal_rate_hz == pytest.approx(0.0)


def test_o7_assigns_a_shared_phase_boundary_to_the_later_support_segment() -> None:
    movement = _kernel(
        _channel(
            "stick",
            support_segments=(
                MovementSupportSegment(0, NS),
                MovementSupportSegment(NS, 2 * NS),
            ),
            turning_points=(
                MovementTurningPoint(100_000_000, 0.0),
                MovementTurningPoint(NS, 2.0),
                MovementTurningPoint(NS + MIN_SEPARATION_NS, 0.0),
            ),
        )
    )

    result = _compute_kernel(movement, ("stick",))

    assert result.status == "computed"
    assert result.total_reversal_count == 1
    assert result.reversal_rate_hz == pytest.approx(0.5)


def test_o7_uses_each_channel_support_denominator_and_session_maximum() -> None:
    movement = _kernel(
        _channel(
            "pedals",
            support_segments=(MovementSupportSegment(0, 2 * NS),),
            turning_points=_turning_points(2),
        ),
        _channel("stick", turning_points=_turning_points(4)),
    )

    result = _compute_kernel(movement, ("pedals", "stick"))

    assert result.status == "computed"
    assert tuple((item.channel_id, item.rate_hz) for item in result.channel_rates) == (
        ("pedals", pytest.approx(1.0)),
        ("stick", pytest.approx(4.0)),
    )
    assert result.reversal_rate_hz == pytest.approx(4.0)


def test_o7_zero_reversal_is_computed_but_missing_channel_is_not_computable() -> None:
    movement = _kernel(_channel("stick"))

    zero = _compute_kernel(movement, ("stick",))
    missing = _compute_kernel(movement, ("pedals", "stick"))

    assert zero.status == "computed"
    assert zero.reversal_rate_hz == pytest.approx(0.0)
    assert missing.status == "not_computable"
    assert missing.reason == "configured-channel-missing"


def _rows(
    *,
    reversal_count: int = 1,
    omit_phase_2_support: bool = False,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for phase_index, phase_id in enumerate(("phase-1", "phase-2")):
        phase_start = phase_index * NS
        for channel_id in ("cyclic", "unused"):
            if omit_phase_2_support and phase_id == "phase-2":
                continue
            rows.extend(
                (
                    {
                        "phase_id": phase_id,
                        "channel_id": channel_id,
                        "event_t_ns": phase_start,
                        "event_id": f"{phase_id}-{channel_id}-support-start",
                        "event_kind": "support-start",
                        "amplitude": 0.0,
                    },
                    {
                        "phase_id": phase_id,
                        "channel_id": channel_id,
                        "event_t_ns": phase_start + NS,
                        "event_id": f"{phase_id}-{channel_id}-support-end",
                        "event_kind": "support-end",
                        "amplitude": 0.0,
                    },
                )
            )
        if omit_phase_2_support and phase_id == "phase-2":
            continue
        for index, point in enumerate(_turning_points(reversal_count, start_t_ns=phase_start)):
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": "cyclic",
                    "event_t_ns": point.t_ns,
                    "event_id": f"{phase_id}-cyclic-turning-{index:06d}",
                    "event_kind": "turning-point",
                    "amplitude": point.value_pct,
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "phase_id": pl.String,
            "channel_id": pl.String,
            "event_t_ns": pl.Int64,
            "event_id": pl.String,
            "event_kind": pl.String,
            "amplitude": pl.Float64,
        },
    ).sort(["phase_id", "channel_id", "event_t_ns", "event_id"], maintain_order=True)


def _dependency(frame: pl.DataFrame) -> ResolvedPreprocessingDependency:
    descriptor = {
        "type": "table",
        "fields": [
            {"name": "phase_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "channel_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "event_t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "event_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "event_kind", "dtype": "utf8", "unit": "id", "nullable": False},
            {
                "name": "amplitude",
                "dtype": "f64",
                "unit": "percent_full_travel",
                "nullable": False,
            },
        ],
        "canonical_order_keys": ["phase_id", "channel_id", "event_t_ns", "event_id"],
    }
    payload = ReadOnlyTabularPayload(
        schema_id="movement-events-v1-output-v0.1",
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
        artifact_kind="movement-events-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=2 * NS,
        logical_content_sha256=SHA_A,
    )
    identity = PreprocessingArtifactIdentity(
        recipe_id="movement-events-v1",
        recipe_version="0.1.0",
        provider_id="movement-events-v1",
        provider_version="1.0.0",
        implementation_digest=SHA_A,
        parameter_schema_id="movement-events-v1-parameters-0.1",
        parameter_schema_sha256=SHA_B,
        parameter_hash=SHA_A,
        scope_kind="session",
        scope_id="session-1",
        scope_start_t_ns=0,
        scope_end_t_ns=2 * NS,
        phase_id=None,
        event_id=None,
        window_id=None,
        schema_id=payload.schema_id,
        schema_sha256=schema_descriptor_sha256(payload.schema_id, descriptor),
        artifact_kind=payload.artifact_kind,
        payload_kind="table",
        logical_content_sha256=SHA_A,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    return ResolvedPreprocessingDependency(identity=identity, payload=payload)


def _context() -> AnchorPluginContext:
    mappings = (_mapping("cyclic"), _mapping("unused"))
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=2 * NS, source="master-clock-x-mapped-coverage-v1"),
        streams={},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.control_mappings": [item.model_dump(mode="json") for item in mappings]
            }
        ),
    )


def _temporal_recipe() -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "o7",
        "scope_ids": ["phase-1", "phase-2"],
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": 0,
                "end_t_ns": NS,
                "include_session_terminal_point": False,
            },
            {
                "phase_id": "phase-2",
                "start_t_ns": NS,
                "end_t_ns": 2 * NS,
                "include_session_terminal_point": True,
            },
        ],
        "control_mapping_ids": ["mapping-cyclic", "mapping-unused"],
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
            producer_anchor_id="O7",
            producer_plugin_id="o7-control-reversal-rate",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A,),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O7 is table-only
        raise AssertionError((artifact_id, payload))


def _compute_plugin(frame: pl.DataFrame):
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(),
        {
            "minimum_reversal_amplitude_pct": 2.0,
            "minimum_reversal_separation_ns": MIN_SEPARATION_NS,
        },
        _temporal_recipe(),
        ResolvedDependencies(
            results={},
            artifacts={},
            algorithm_profiles={},
            preprocessing={"movement-events": _dependency(frame)},
        ),
        emitter,
    )
    return measurement, emitter


def test_o7_definition_reuses_the_exact_o5_movement_provider_dependency() -> None:
    from pilot_assessment.anchors.plugins.o5_workload_rate import create_plugin as create_o5

    definition = create_plugin().definition()

    assert definition.anchor_id == "O7"
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == ("semantic.control_mappings",)
    assert definition.dependencies == create_o5().definition().dependencies
    assert tuple(item.dependency_id for item in definition.dependencies) == ("movement-events",)


def test_o7_plugin_aggregates_all_phases_by_channel_max_and_publishes_only_reversals() -> None:
    measurement, emitter = _compute_plugin(_rows())

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(1.0)
    assert tuple(item.primary_value.value for item in measurement.phase_results) == pytest.approx(
        (1.0, 1.0)
    )
    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "reversal-events"
    assert payload.frame.height == 2
    assert set(payload.frame["channel_id"].to_list()) == {"cyclic"}
    assert payload.frame["amplitude"].to_list() == pytest.approx([2.0, 2.0])


def test_o7_plugin_refuses_a_partial_session_score() -> None:
    measurement, emitter = _compute_plugin(_rows(omit_phase_2_support=True))

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert tuple(item.calculation_status.value for item in measurement.phase_results) == (
        "computed",
        "missing_input",
    )
    assert emitter.payloads == []


def test_o7_plugin_extreme_finite_rate_is_computed_unacceptable() -> None:
    measurement, _emitter = _compute_plugin(_rows(reversal_count=4))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(4.0)
    assert _state(measurement.primary_value.value) is EvidenceState.UNACCEPTABLE


def test_o7_plugin_zero_reversals_is_computed_without_an_empty_artifact() -> None:
    measurement, emitter = _compute_plugin(_rows(reversal_count=0))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(0.0)
    assert tuple(item.primary_value.value for item in measurement.phase_results) == pytest.approx(
        (0.0, 0.0)
    )
    assert emitter.payloads == []


def test_o7_plugin_calls_the_shared_reversal_kernel_for_each_phase_and_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pilot_assessment.anchors.plugins import o7_control_reversal_rate

    real_kernel = o7_control_reversal_rate.compute_o7_kernel
    calls: list[tuple[str, ...]] = []

    def spy_kernel(
        movement, channel_ids, minimum_reversal_amplitude_pct, minimum_reversal_separation_ns
    ):
        calls.append(channel_ids)
        return real_kernel(
            movement,
            channel_ids,
            minimum_reversal_amplitude_pct,
            minimum_reversal_separation_ns,
        )

    monkeypatch.setattr(o7_control_reversal_rate, "compute_o7_kernel", spy_kernel)

    measurement, _emitter = _compute_plugin(_rows())

    assert measurement.calculation_status.value == "computed"
    assert calls == [("cyclic", "unused")] * 3
