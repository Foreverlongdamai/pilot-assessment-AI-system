from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from pilot_assessment.anchors.catalog import (
    parameter_schema_sha256,
)
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    preprocessing_definition_fingerprint,
    schema_descriptor_sha256,
)
from pilot_assessment.anchors.primitives import movement
from pilot_assessment.anchors.primitives.movement import (
    MovementChannelResult,
    MovementEvent,
    MovementKernelResult,
    MovementSupportSegment,
    compute_o5_kernel,
    detect_movement_events,
)
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ProjectedSemanticScope,
)
from pilot_assessment.contracts.anchor_execution import (
    ControlEffectMapping,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedPreprocessingRecipe,
    SemanticPhase,
)
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView
from tests.anchors.test_dag import _schema_defaults
from tests.m4_support.micro_inputs import tiny_u_table

NS = 1_000_000_000
SHA_A = "a" * 64


def _parameters(**updates: object) -> dict[str, object]:
    values = _schema_defaults("movement-events-v1-parameters-0.1")
    values.update(updates)
    return values


def _mapping(channel_id: str, mapping_id: str | None = None) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=mapping_id or f"mapping-{channel_id}",
        state_axis_id=f"axis-{channel_id}",
        control_channel_id=channel_id,
        correct_sign=1,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=1.0,
    )


def _contract(*channels: str, table_role: str = "samples") -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="U",
        table_role=table_role,
        stream_aligned_schema_id="u-aligned-v0.1",
        table_aligned_schema_id=f"u-{table_role}-aligned-v0.1",
        coordinate_frame_id="cockpit-controls",
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
                    field_name=channel, dtype_id="f64", unit="ratio", nullable=False
                )
                for channel in channels
            ),
        ),
    )


def _channel(result: MovementKernelResult, channel_id: str) -> MovementChannelResult:
    return next(item for item in result.channels if item.channel_id == channel_id)


def test_movement_detector_uses_exact_filter_contract_and_retains_zero_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = tuple(range(0, NS + 10_000_000, 10_000_000))
    seconds = np.asarray(times, dtype=np.float64) / NS
    table = tiny_u_table(
        times,
        {
            "cyclic": tuple(0.8 * np.sin(2.0 * np.pi * 2.0 * seconds)),
            "unused": tuple(0.0 for _ in times),
        },
    )
    calls: list[tuple[str | None, int | None, int]] = []
    real = movement.signal.sosfiltfilt

    def spy(sos, values, *, padtype=None, padlen=None):
        calls.append((padtype, padlen, len(values)))
        return real(sos, values, padtype=padtype, padlen=padlen)

    monkeypatch.setattr(movement.signal, "sosfiltfilt", spy)
    result = detect_movement_events(
        table,
        (_mapping("cyclic"), _mapping("unused")),
        0,
        NS,
        (_contract("cyclic", "unused"),),
        _parameters(),
    )

    assert result.status == "computed"
    assert tuple(item.channel_id for item in result.channels) == ("cyclic", "unused")
    assert _channel(result, "unused").movements == ()
    assert _channel(result, "unused").observed_support_duration_ns == NS
    assert calls == [("odd", 15, 100), ("odd", 15, 100)]


def test_short_segment_bypasses_filter_but_still_computes_support() -> None:
    table = tiny_u_table((0, 10_000_000, 20_000_000), {"stick": (0.0, 0.1, 0.2)})

    result = detect_movement_events(
        table,
        (_mapping("stick"),),
        0,
        20_000_000,
        (_contract("stick"),),
        _parameters(),
    )

    channel = _channel(result, "stick")
    assert result.status == "computed"
    assert channel.grid_sample_count == 2
    assert channel.short_filter_bypass_count == 1
    assert channel.observed_support_duration_ns == 20_000_000


def test_detector_selects_the_declared_u_samples_contract_not_a_field_shape_guess() -> None:
    table = tiny_u_table((0, 10_000_000, 20_000_000), {"stick": (0.0, 0.1, 0.2)})

    result = detect_movement_events(
        table,
        (_mapping("stick"),),
        0,
        30_000_000,
        (
            _contract("stick", table_role="diagnostics"),
            _contract("stick"),
        ),
        _parameters(),
    )

    assert result.status == "computed"
    assert _channel(result, "stick").observed_support_duration_ns == 30_000_000


def test_finite_extreme_control_values_remain_computed_evidence() -> None:
    table = tiny_u_table(
        (0, 10_000_000, 20_000_000),
        {"stick": (1e100, 1e100, 1e100)},
    )

    result = detect_movement_events(
        table,
        (_mapping("stick"),),
        0,
        30_000_000,
        (_contract("stick"),),
        _parameters(minimum_filter_sample_count=999),
    )

    assert result.status == "computed"
    assert _channel(result, "stick").movements == ()


def test_zero_samples_terminate_sign_runs_instead_of_joining_them() -> None:
    runs = movement._qualifying_sign_runs_v1(
        times_ns=np.asarray((0, 10, 20, 30, 40), dtype=np.int64),
        signs=np.asarray((1, 1, 0, 1, 1), dtype=np.int8),
        minimum_sign_run_ns=30,
    )

    assert runs == ()


def test_flat_extreme_midpoint_uses_round_half_even_nanoseconds() -> None:
    turning = movement._turning_points_v1(
        times_ns=np.asarray((0, 1, 2, 3, 4, 5, 6), dtype=np.int64),
        filtered=np.asarray((0.0, 1.0, 2.0, 2.0, 1.0, 0.0, -1.0)),
        qualifying_runs=((1, 0, 2), (-1, 4, 6)),
    )

    assert len(turning) == 1
    assert turning[0].t_ns == 2  # midpoint 2.5 rounds to the even integer 2
    assert turning[0].value_pct == 2.0


def test_detector_never_forms_turning_points_across_m3_gaps() -> None:
    times = (
        *(index * 10_000_000 for index in range(11)),
        *(500_000_000 + index * 10_000_000 for index in range(11)),
        *(1_000_000_000 + index * 10_000_000 for index in range(11)),
    )
    values = (
        *(index / 10 for index in range(11)),
        *(1.0 - index / 10 for index in range(11)),
        *(index / 10 for index in range(11)),
    )
    result = detect_movement_events(
        tiny_u_table(times, {"stick": values}),
        (_mapping("stick"),),
        0,
        1_100_000_000,
        (_contract("stick"),),
        _parameters(minimum_filter_sample_count=999),
    )

    channel = _channel(result, "stick")
    assert result.gap_count == 2
    assert len(channel.support_segments) == 3
    assert channel.turning_points == ()
    assert channel.movements == ()


def _kernel_channel(
    channel_id: str,
    *,
    duration_ns: int,
    movement_count: int,
) -> MovementChannelResult:
    return MovementChannelResult(
        channel_id=channel_id,
        observed_support_duration_ns=duration_ns,
        support_segments=(MovementSupportSegment(0, duration_ns),) if duration_ns else (),
        turning_points=(),
        movements=tuple(
            MovementEvent(event_t_ns=index + 1, amplitude_pct=1.0)
            for index in range(movement_count)
        ),
        grid_sample_count=max(1, movement_count + 1),
        short_filter_bypass_count=0,
    )


def test_o5_kernel_means_configured_channel_rates_including_zero_movement() -> None:
    movement_result = MovementKernelResult(
        status="computed",
        reason=None,
        channels=(
            _kernel_channel("cyclic", duration_ns=NS, movement_count=2),
            _kernel_channel("unused", duration_ns=NS, movement_count=0),
        ),
        sample_count=100,
        source_start_t_ns=0,
        source_end_t_ns=NS,
        gap_count=0,
        max_gap_ns=10_000_000,
    )

    result = compute_o5_kernel(movement_result, ("cyclic", "unused"), 1.0)

    assert result.status == "computed"
    assert result.workload_rate_hz == pytest.approx(1.0)
    assert result.workload_ratio == pytest.approx(1.0)
    assert tuple(item.rate_hz for item in result.channel_rates) == pytest.approx((2.0, 0.0))


def test_o5_kernel_zero_support_is_not_computable_not_zero_workload() -> None:
    movement_result = MovementKernelResult(
        status="computed",
        reason=None,
        channels=(_kernel_channel("stick", duration_ns=0, movement_count=0),),
        sample_count=1,
        source_start_t_ns=0,
        source_end_t_ns=0,
        gap_count=0,
        max_gap_ns=None,
    )

    result = compute_o5_kernel(movement_result, ("stick",), 1.0)

    assert result.status == "not_computable"
    assert result.reason == "zero-support-duration"
    assert result.workload_ratio is None


def test_six_hz_violent_control_remains_a_finite_computed_ratio() -> None:
    movement_result = MovementKernelResult(
        status="computed",
        reason=None,
        channels=(_kernel_channel("stick", duration_ns=NS, movement_count=6),),
        sample_count=100,
        source_start_t_ns=0,
        source_end_t_ns=NS,
        gap_count=0,
        max_gap_ns=10_000_000,
    )

    result = compute_o5_kernel(movement_result, ("stick",), 1.0)

    assert result.status == "computed"
    assert result.workload_ratio == pytest.approx(6.0)
    assert math.isfinite(result.workload_ratio)


def test_production_provider_declares_positive_projection_serializes_support_and_reuses_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = movement.create_provider()
    definition = provider.definition()
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == (
        "semantic.control_mappings",
        "semantic.phases",
    )
    assert definition.dependencies == ()
    assert definition.output_schema_id == "movement-events-v1-output-v0.1"

    mappings = (_mapping("cyclic"), _mapping("unused"))
    phase = SemanticPhase(
        phase_id="phase-1",
        phase_type="translation",
        start_t_ns=0,
        end_t_ns=NS,
        include_session_terminal_point=True,
    )
    times = tuple(range(0, NS + 10_000_000, 10_000_000))
    seconds = np.asarray(times, dtype=np.float64) / NS
    table = tiny_u_table(
        times,
        {
            "cyclic": tuple(0.8 * np.sin(2.0 * np.pi * 2.0 * seconds)),
            "unused": tuple(0.0 for _ in times),
        },
    )
    view = AlignedStreamView(
        modality="U",
        source_schema_id="u-raw-v0.1",
        aligned_schema_id="u-aligned-v0.1",
        clock_id="sim-clock",
        tables={"diagnostics": table, "samples": table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/u.parquet": SHA_A},
    )
    context = AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=NS, source="master-clock-x-mapped-coverage-v1"),
        streams={"U": view},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.control_mappings": [item.model_dump(mode="json") for item in mappings],
                "semantic.phases": [phase.model_dump(mode="json")],
            }
        ),
        input_table_contracts=(
            _contract("cyclic", "unused", table_role="diagnostics"),
            _contract("cyclic", "unused"),
        ),
    )
    parameters = _parameters()
    recipe = ResolvedPreprocessingRecipe(
        recipe_id="movement-events-v1",
        recipe_version="0.1.0",
        provider_id=definition.provider_id,
        provider_version=definition.provider_version,
        api_version="0.1.0",
        definition_fingerprint=preprocessing_definition_fingerprint(definition),
        implementation_digest=SHA_A,
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=definition.required_streams,
        required_context_paths=definition.required_context_paths,
        required_semantic_paths=definition.required_semantic_paths,
        required_reference_ids=definition.required_reference_ids,
        dependency_specs=definition.dependencies,
        dependency_bindings=(),
        output_schema_id=definition.output_schema_id,
        output_schema_descriptor=definition.output_schema_descriptor,
        output_schema_sha256=schema_descriptor_sha256(
            definition.output_schema_id, definition.output_schema_descriptor
        ),
        artifact_kind=definition.artifact_kind,
        output_payload_kind="table",
        scope_policy="session",
    )
    real_detector = movement.detect_movement_events
    detector_calls: list[tuple[int, int]] = []

    def spy_detector(*args, **kwargs):
        detector_calls.append((args[2], args[3]))
        return real_detector(*args, **kwargs)

    monkeypatch.setattr(movement, "detect_movement_events", spy_detector)
    payload = provider.compute(
        context,
        recipe,
        PreprocessingScope(
            kind="session",
            scope_id="session-1",
            start_t_ns=0,
            end_t_ns=NS,
            phase_id=None,
            event_id=None,
            window_id=None,
        ),
        {},
    )

    assert isinstance(payload.frame, pl.DataFrame)
    assert set(payload.frame["channel_id"].to_list()) == {"cyclic", "unused"}
    assert {"support-start", "support-end"} <= set(payload.frame["event_kind"].to_list())
    assert payload.order_keys == ("phase_id", "channel_id", "event_t_ns", "event_id")
    assert detector_calls == [(0, NS)]
