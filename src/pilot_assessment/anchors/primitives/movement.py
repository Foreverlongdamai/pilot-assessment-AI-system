"""Deterministic shared control-movement detector and O5 workload kernel."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import Literal, cast

import numpy as np
import polars as pl
from pydantic import JsonValue
from scipy import signal

from pilot_assessment.anchors.catalog import REFERENCE_PREPROCESSING_IDENTITIES
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    ControlEffectMapping,
    PreprocessingProviderDefinition,
    ResolvedInputTableContract,
    ResolvedPreprocessingRecipe,
    SemanticPhase,
)

_NANOSECONDS_PER_SECOND = 1_000_000_000
_STRUCTURAL_COLUMNS = ("source_row_index", "t_ns", "in_session")
_MOVEMENT_EVENT_KINDS = frozenset(
    {
        "support-start",
        "support-end",
        "turning-point",
        "movement",
        "diagnostic.short-filter-bypass",
    }
)
MovementStatus = Literal["computed", "missing_input", "not_computable"]


@dataclass(frozen=True, slots=True)
class MovementSupportSegment:
    start_t_ns: int
    end_t_ns: int

    def __post_init__(self) -> None:
        if (
            type(self.start_t_ns) is not int
            or type(self.end_t_ns) is not int
            or self.start_t_ns < 0
            or self.end_t_ns <= self.start_t_ns
        ):
            raise ValueError("movement support segments require a positive non-negative span")


@dataclass(frozen=True, slots=True)
class MovementTurningPoint:
    t_ns: int
    value_pct: float

    def __post_init__(self) -> None:
        if type(self.t_ns) is not int or self.t_ns < 0:
            raise ValueError("turning-point time must be a non-negative strict integer")
        if not math.isfinite(self.value_pct):
            raise ValueError("turning-point value must be finite")


@dataclass(frozen=True, slots=True)
class MovementEvent:
    event_t_ns: int
    amplitude_pct: float

    def __post_init__(self) -> None:
        if type(self.event_t_ns) is not int or self.event_t_ns < 0:
            raise ValueError("movement-event time must be a non-negative strict integer")
        if not math.isfinite(self.amplitude_pct) or self.amplitude_pct < 0.0:
            raise ValueError("movement amplitude must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class MovementChannelResult:
    channel_id: str
    observed_support_duration_ns: int
    support_segments: tuple[MovementSupportSegment, ...]
    turning_points: tuple[MovementTurningPoint, ...]
    movements: tuple[MovementEvent, ...]
    grid_sample_count: int
    short_filter_bypass_count: int

    def __post_init__(self) -> None:
        if type(self.channel_id) is not str or not self.channel_id:
            raise ValueError("movement channel_id must be non-empty")
        for value, label in (
            (self.observed_support_duration_ns, "observed_support_duration_ns"),
            (self.grid_sample_count, "grid_sample_count"),
            (self.short_filter_bypass_count, "short_filter_bypass_count"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative strict integer")
        if self.observed_support_duration_ns != sum(
            segment.end_t_ns - segment.start_t_ns for segment in self.support_segments
        ):
            raise ValueError("channel support duration must equal its segment duration sum")
        if tuple(
            sorted(self.support_segments, key=lambda item: (item.start_t_ns, item.end_t_ns))
        ) != (self.support_segments):
            raise ValueError("movement support segments must be canonical")
        if tuple(sorted(self.turning_points, key=lambda item: item.t_ns)) != self.turning_points:
            raise ValueError("turning points must be canonical")
        if tuple(sorted(self.movements, key=lambda item: item.event_t_ns)) != self.movements:
            raise ValueError("movement events must be canonical")


@dataclass(frozen=True, slots=True)
class MovementKernelResult:
    status: MovementStatus
    reason: str | None
    channels: tuple[MovementChannelResult, ...]
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None

    def __post_init__(self) -> None:
        if self.status not in {"computed", "missing_input", "not_computable"}:
            raise ValueError("unsupported movement-kernel status")
        if (self.status == "computed") != (self.reason is None):
            raise ValueError("computed movement results alone omit a reason")
        if type(self.sample_count) is not int or self.sample_count < 0:
            raise ValueError("sample_count must be a non-negative strict integer")
        if type(self.gap_count) is not int or self.gap_count < 0:
            raise ValueError("gap_count must be a non-negative strict integer")
        if self.max_gap_ns is not None and (
            type(self.max_gap_ns) is not int or self.max_gap_ns <= 0
        ):
            raise ValueError("max_gap_ns must be a positive strict integer when present")
        if (self.source_start_t_ns is None) != (self.source_end_t_ns is None):
            raise ValueError("source bounds require both endpoints")
        if self.source_start_t_ns is not None and (
            type(self.source_start_t_ns) is not int
            or type(self.source_end_t_ns) is not int
            or self.source_start_t_ns < 0
            or self.source_end_t_ns < self.source_start_t_ns
        ):
            raise ValueError("source bounds must be ordered non-negative integers")
        ids = tuple(item.channel_id for item in self.channels)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("movement channels must be unique and canonical")


@dataclass(frozen=True, slots=True)
class O5ChannelRate:
    channel_id: str
    movement_count: int
    observed_support_duration_ns: int
    rate_hz: float


@dataclass(frozen=True, slots=True)
class O5KernelResult:
    status: MovementStatus
    reason: str | None
    workload_ratio: float | None
    workload_rate_hz: float | None
    total_movement_count: int
    channel_rates: tuple[O5ChannelRate, ...]


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _finite_number(
    value: object, label: str, *, minimum: float | None = None, strict_minimum: bool = False
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and (numeric < minimum or (strict_minimum and numeric == minimum)):
        comparison = "greater than" if strict_minimum else "at least"
        raise ValueError(f"{label} must be {comparison} {minimum}")
    return numeric


@dataclass(frozen=True, slots=True)
class _MovementParameters:
    grid_period_ns: int
    lowpass_cutoff_hz: float
    lowpass_order: int
    filtfilt_padtype: str
    filtfilt_padlen_cap_samples: int
    minimum_filter_sample_count: int
    derivative_deadband_pct_per_s: float
    minimum_sign_run_ns: int
    minimum_movement_amplitude_pct: float


def _parameters(values: Mapping[str, JsonValue]) -> _MovementParameters:
    expected = {
        "grid_period_ns",
        "lowpass_cutoff_hz",
        "lowpass_order",
        "filtfilt_padtype",
        "filtfilt_padlen_cap_samples",
        "minimum_filter_sample_count",
        "derivative_deadband_pct_per_s",
        "minimum_sign_run_ns",
        "minimum_movement_amplitude_pct",
    }
    if not isinstance(values, Mapping) or set(values) != expected:
        raise ValueError("movement-events-v1 requires its exact nine-key parameter profile")
    padtype = values["filtfilt_padtype"]
    if type(padtype) is not str or padtype not in {"constant", "even", "odd"}:
        raise ValueError("filtfilt_padtype must be constant, even, or odd")
    parsed = _MovementParameters(
        grid_period_ns=_strict_int(values["grid_period_ns"], "grid_period_ns", minimum=1),
        lowpass_cutoff_hz=_finite_number(
            values["lowpass_cutoff_hz"], "lowpass_cutoff_hz", minimum=0.0, strict_minimum=True
        ),
        lowpass_order=_strict_int(values["lowpass_order"], "lowpass_order", minimum=1),
        filtfilt_padtype=padtype,
        filtfilt_padlen_cap_samples=_strict_int(
            values["filtfilt_padlen_cap_samples"], "filtfilt_padlen_cap_samples"
        ),
        minimum_filter_sample_count=_strict_int(
            values["minimum_filter_sample_count"], "minimum_filter_sample_count", minimum=1
        ),
        derivative_deadband_pct_per_s=_finite_number(
            values["derivative_deadband_pct_per_s"],
            "derivative_deadband_pct_per_s",
            minimum=0.0,
        ),
        minimum_sign_run_ns=_strict_int(values["minimum_sign_run_ns"], "minimum_sign_run_ns"),
        minimum_movement_amplitude_pct=_finite_number(
            values["minimum_movement_amplitude_pct"],
            "minimum_movement_amplitude_pct",
            minimum=0.0,
        ),
    )
    sample_rate_hz = _NANOSECONDS_PER_SECOND / parsed.grid_period_ns
    if parsed.lowpass_cutoff_hz >= sample_rate_hz / 2.0:
        raise ValueError("lowpass_cutoff_hz must be below the movement-grid Nyquist")
    return parsed


def _canonical_mappings(
    values: tuple[ControlEffectMapping, ...],
) -> tuple[ControlEffectMapping, ...]:
    if type(values) is not tuple or any(
        not isinstance(item, ControlEffectMapping) for item in values
    ):
        raise TypeError("control_mappings must be a typed tuple")
    by_channel: dict[str, ControlEffectMapping] = {}
    for mapping in sorted(values, key=lambda item: item.control_mapping_id):
        previous = by_channel.get(mapping.control_channel_id)
        if previous is not None and (
            previous.control_unit,
            previous.lower,
            previous.trim,
            previous.upper,
        ) != (mapping.control_unit, mapping.lower, mapping.trim, mapping.upper):
            raise ValueError(
                f"control channel {mapping.control_channel_id} has conflicting calibration"
            )
        by_channel.setdefault(mapping.control_channel_id, mapping)
    return tuple(by_channel[channel] for channel in sorted(by_channel))


def _u_contract(
    contracts: tuple[ResolvedInputTableContract, ...], frame: pl.DataFrame
) -> ResolvedInputTableContract | None:
    if type(contracts) is not tuple or any(
        not isinstance(item, ResolvedInputTableContract) for item in contracts
    ):
        raise TypeError("input_contracts must be a typed tuple")
    matches = tuple(
        item
        for item in contracts
        if item.modality.value == "U"
        and item.table_role == "samples"
        and all(field.field_name in frame.columns for field in item.fields)
    )
    return matches[0] if len(matches) == 1 else None


def _noncomputed(status: MovementStatus, reason: str) -> MovementKernelResult:
    return MovementKernelResult(
        status=status,
        reason=reason,
        channels=(),
        sample_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        gap_count=0,
        max_gap_ns=None,
    )


def _round_half_even_midpoint(left: int, right: int) -> int:
    return int(
        ((Decimal(left) + Decimal(right)) / Decimal(2)).to_integral_value(rounding=ROUND_HALF_EVEN)
    )


def _qualifying_sign_runs_v1(
    *,
    times_ns: np.ndarray,
    signs: np.ndarray,
    minimum_sign_run_ns: int,
) -> tuple[tuple[int, int, int], ...]:
    """Return qualifying ``(sign,start_index,end_index)`` runs.

    Duration is the sum of labelled left-hold grid intervals. A zero label
    terminates a run, and the last grid sample never invents an interval.
    """

    minimum = _strict_int(minimum_sign_run_ns, "minimum_sign_run_ns")
    if times_ns.ndim != 1 or signs.ndim != 1 or len(times_ns) != len(signs):
        raise ValueError("times and signs must be equal one-dimensional arrays")
    times = tuple(int(value) for value in times_ns.tolist())
    if any(right <= left for left, right in pairwise(times)):
        raise ValueError("movement grid timestamps must be strictly increasing")
    runs: list[tuple[int, int, int]] = []
    index = 0
    while index < len(signs):
        sign_value = int(signs[index])
        if sign_value == 0:
            index += 1
            continue
        end = index
        while end + 1 < len(signs) and int(signs[end + 1]) == sign_value:
            end += 1
        duration = sum(
            times[row + 1] - times[row] for row in range(index, min(end, len(times) - 2) + 1)
        )
        if duration >= minimum:
            runs.append((sign_value, index, end))
        index = end + 1
    return tuple(runs)


def _turning_points_v1(
    *,
    times_ns: np.ndarray,
    filtered: np.ndarray,
    qualifying_runs: tuple[tuple[int, int, int], ...],
) -> tuple[MovementTurningPoint, ...]:
    if times_ns.ndim != 1 or filtered.ndim != 1 or len(times_ns) != len(filtered):
        raise ValueError("times and filtered values must be equal one-dimensional arrays")
    result: list[MovementTurningPoint] = []
    for left, right in zip(qualifying_runs, qualifying_runs[1:], strict=False):
        left_sign, _left_start, left_end = left
        right_sign, right_start, _right_end = right
        if left_sign == right_sign:
            continue
        region = filtered[left_end : right_start + 1]
        extreme = float(np.max(region) if left_sign > 0 else np.min(region))
        matches = np.flatnonzero(region == extreme)
        first = left_end + int(matches[0])
        last = left_end + int(matches[-1])
        result.append(
            MovementTurningPoint(
                t_ns=_round_half_even_midpoint(int(times_ns[first]), int(times_ns[last])),
                value_pct=extreme,
            )
        )
    return tuple(result)


def _positive_median_gap_threshold(times: Sequence[int]) -> int | None:
    deltas = sorted(right - left for left, right in pairwise(times) if right > left)
    if not deltas:
        return None
    middle = len(deltas) // 2
    median = (
        Decimal(deltas[middle])
        if len(deltas) % 2
        else (Decimal(deltas[middle - 1]) + Decimal(deltas[middle])) / Decimal(2)
    )
    return int((median * Decimal("5.0")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _normalize(values: np.ndarray, mapping: ControlEffectMapping) -> np.ndarray:
    upper = 100.0 * (values - mapping.trim) / (mapping.upper - mapping.trim)
    lower = 100.0 * (values - mapping.trim) / (mapping.trim - mapping.lower)
    return np.where(values >= mapping.trim, upper, lower)


def _grid_times(scope_start: int, segment: MovementSupportSegment, period: int) -> np.ndarray:
    delta = segment.start_t_ns - scope_start
    first_k = max(0, (delta + period - 1) // period)
    first = scope_start + first_k * period
    if first >= segment.end_t_ns:
        return np.asarray((), dtype=np.int64)
    return np.arange(first, segment.end_t_ns, period, dtype=np.int64)


def detect_movement_events(
    u_table: pl.DataFrame,
    control_mappings: tuple[ControlEffectMapping, ...],
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    input_contracts: tuple[ResolvedInputTableContract, ...],
    provider_parameters: Mapping[str, JsonValue],
) -> MovementKernelResult:
    """Detect movement events over one exact phase/window without crossing gaps."""

    if not isinstance(u_table, pl.DataFrame):
        raise TypeError("u_table must be a Polars DataFrame")
    start = _strict_int(scope_start_t_ns, "scope_start_t_ns")
    end = _strict_int(scope_end_t_ns, "scope_end_t_ns", minimum=1)
    if end <= start:
        raise ValueError("movement scope must have positive duration")
    parameters = _parameters(provider_parameters)
    mappings = _canonical_mappings(control_mappings)
    if not mappings:
        return _noncomputed("not_computable", "no-configured-control-channels")
    contract = _u_contract(input_contracts, u_table)
    if contract is None:
        return _noncomputed("not_computable", "input-contract-missing")
    fields = {field.field_name: field for field in contract.fields}
    if any(column not in fields for column in _STRUCTURAL_COLUMNS):
        return _noncomputed("not_computable", "temporal-field-missing")
    if (
        fields["t_ns"].unit != "ns"
        or fields["in_session"].unit != "bool"
        or fields["source_row_index"].unit != "index"
    ):
        return _noncomputed("not_computable", "temporal-contract-mismatch")
    for mapping in mappings:
        field = fields.get(mapping.control_channel_id)
        if (
            field is None
            or field.unit != mapping.control_unit
            or mapping.control_channel_id not in u_table.columns
        ):
            return _noncomputed("not_computable", "control-contract-mismatch")

    active = u_table.filter(
        (pl.col("t_ns") >= start) & (pl.col("t_ns") < end) & pl.col("in_session")
    ).sort(["t_ns", "source_row_index"], maintain_order=True)
    if active.is_empty():
        return _noncomputed("missing_input", "no-temporal-support")
    times = cast(list[int], active["t_ns"].to_list())
    if any(type(value) is not int or value < 0 for value in times):
        return _noncomputed("not_computable", "timestamp-invalid")
    threshold = _positive_median_gap_threshold(times)
    support = reconstruct_point_support(
        active,
        timestamp_column="t_ns",
        stable_keys=("source_row_index",),
        in_session_column="in_session",
        gap_threshold_ns=threshold,
        semantic_end_t_ns=end,
    )
    if support.observed_duration_ns == 0:
        return MovementKernelResult(
            status="missing_input",
            reason="no-temporal-support",
            channels=(),
            sample_count=active.height,
            source_start_t_ns=min(times),
            source_end_t_ns=max(times),
            gap_count=support.gap_count,
            max_gap_ns=support.max_gap_ns,
        )
    segments = tuple(
        MovementSupportSegment(segment_start, segment_end)
        for segment_start, segment_end in support.segment_bounds
        if segment_end > segment_start
    )
    sos = signal.butter(
        parameters.lowpass_order,
        parameters.lowpass_cutoff_hz,
        btype="lowpass",
        fs=_NANOSECONDS_PER_SECOND / parameters.grid_period_ns,
        output="sos",
    )
    channels: list[MovementChannelResult] = []
    for mapping in mappings:
        raw_values = active[mapping.control_channel_id].to_list()
        if any(
            value is None
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in raw_values
        ):
            return _noncomputed("not_computable", "control-value-invalid")
        all_turning: list[MovementTurningPoint] = []
        all_movements: list[MovementEvent] = []
        grid_count = 0
        bypass_count = 0
        for segment in segments:
            source = active.filter(
                (pl.col("t_ns") >= segment.start_t_ns) & (pl.col("t_ns") <= segment.end_t_ns)
            ).unique(subset=["t_ns"], keep="first", maintain_order=True)
            source_times = np.asarray(source["t_ns"].to_list(), dtype=np.int64)
            source_values = np.asarray(
                source[mapping.control_channel_id].to_list(), dtype=np.float64
            )
            grid = _grid_times(start, segment, parameters.grid_period_ns)
            grid_count += len(grid)
            if len(grid) == 0:
                bypass_count += 1
                continue
            normalized = _normalize(source_values, mapping)
            interpolated = np.interp(grid.astype(np.float64), source_times, normalized)
            if len(interpolated) < parameters.minimum_filter_sample_count:
                filtered = interpolated
                bypass_count += 1
            else:
                filtered = signal.sosfiltfilt(
                    sos,
                    interpolated,
                    padtype=parameters.filtfilt_padtype,
                    padlen=min(parameters.filtfilt_padlen_cap_samples, len(interpolated) - 1),
                )
            derivative = np.zeros_like(filtered)
            if len(filtered) > 1:
                time_seconds = grid.astype(np.float64) / _NANOSECONDS_PER_SECOND
                derivative[0] = (filtered[1] - filtered[0]) / (time_seconds[1] - time_seconds[0])
                derivative[-1] = (filtered[-1] - filtered[-2]) / (
                    time_seconds[-1] - time_seconds[-2]
                )
                if len(filtered) > 2:
                    derivative[1:-1] = (filtered[2:] - filtered[:-2]) / (
                        time_seconds[2:] - time_seconds[:-2]
                    )
            signs = np.where(
                derivative > parameters.derivative_deadband_pct_per_s,
                1,
                np.where(derivative < -parameters.derivative_deadband_pct_per_s, -1, 0),
            ).astype(np.int8)
            runs = _qualifying_sign_runs_v1(
                times_ns=grid,
                signs=signs,
                minimum_sign_run_ns=parameters.minimum_sign_run_ns,
            )
            turning = _turning_points_v1(
                times_ns=grid,
                filtered=filtered,
                qualifying_runs=runs,
            )
            all_turning.extend(turning)
            all_movements.extend(
                MovementEvent(
                    event_t_ns=right.t_ns,
                    amplitude_pct=abs(right.value_pct - left.value_pct),
                )
                for left, right in zip(turning, turning[1:], strict=False)
                if abs(right.value_pct - left.value_pct)
                >= parameters.minimum_movement_amplitude_pct
            )
        channels.append(
            MovementChannelResult(
                channel_id=mapping.control_channel_id,
                observed_support_duration_ns=support.observed_duration_ns,
                support_segments=segments,
                turning_points=tuple(sorted(all_turning, key=lambda item: item.t_ns)),
                movements=tuple(sorted(all_movements, key=lambda item: item.event_t_ns)),
                grid_sample_count=grid_count,
                short_filter_bypass_count=bypass_count,
            )
        )
    return MovementKernelResult(
        status="computed",
        reason=None,
        channels=tuple(channels),
        sample_count=active.height,
        source_start_t_ns=min(times),
        source_end_t_ns=max(times),
        gap_count=support.gap_count,
        max_gap_ns=support.max_gap_ns,
    )


def compute_o5_kernel(
    movement: MovementKernelResult,
    channel_ids: tuple[str, ...],
    w_min_hz: float,
) -> O5KernelResult:
    """Compute O5 by averaging every configured channel's supported movement rate."""

    if not isinstance(movement, MovementKernelResult):
        raise TypeError("movement must be a MovementKernelResult")
    if (
        type(channel_ids) is not tuple
        or any(type(value) is not str or not value for value in channel_ids)
        or channel_ids != tuple(sorted(channel_ids))
        or len(channel_ids) != len(set(channel_ids))
        or not channel_ids
    ):
        raise ValueError("channel_ids must be a non-empty canonical unique tuple")
    reference = _finite_number(w_min_hz, "w_min_hz", minimum=0.0, strict_minimum=True)
    if movement.status != "computed":
        return O5KernelResult(
            status=movement.status,
            reason=movement.reason,
            workload_ratio=None,
            workload_rate_hz=None,
            total_movement_count=0,
            channel_rates=(),
        )
    by_id = {item.channel_id: item for item in movement.channels}
    if any(channel_id not in by_id for channel_id in channel_ids):
        return O5KernelResult(
            status="missing_input",
            reason="configured-channel-missing",
            workload_ratio=None,
            workload_rate_hz=None,
            total_movement_count=0,
            channel_rates=(),
        )
    rates: list[O5ChannelRate] = []
    for channel_id in channel_ids:
        channel = by_id[channel_id]
        if channel.observed_support_duration_ns == 0:
            return O5KernelResult(
                status="not_computable",
                reason="zero-support-duration",
                workload_ratio=None,
                workload_rate_hz=None,
                total_movement_count=0,
                channel_rates=(),
            )
        duration_s = channel.observed_support_duration_ns / _NANOSECONDS_PER_SECOND
        rates.append(
            O5ChannelRate(
                channel_id=channel_id,
                movement_count=len(channel.movements),
                observed_support_duration_ns=channel.observed_support_duration_ns,
                rate_hz=len(channel.movements) / duration_s,
            )
        )
    workload_rate = math.fsum(item.rate_hz for item in rates) / len(rates)
    return O5KernelResult(
        status="computed",
        reason=None,
        workload_ratio=workload_rate / reference,
        workload_rate_hz=workload_rate,
        total_movement_count=sum(item.movement_count for item in rates),
        channel_rates=tuple(rates),
    )


def _event_frame(rows: Sequence[Mapping[str, object]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            {
                "phase_id": pl.Series("phase_id", [], dtype=pl.String),
                "channel_id": pl.Series("channel_id", [], dtype=pl.String),
                "event_t_ns": pl.Series("event_t_ns", [], dtype=pl.Int64),
                "event_id": pl.Series("event_id", [], dtype=pl.String),
                "event_kind": pl.Series("event_kind", [], dtype=pl.String),
                "amplitude": pl.Series("amplitude", [], dtype=pl.Float64),
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


def _serialize_kernel(
    phase_id: str,
    kernel: MovementKernelResult,
    channel_ids: tuple[str, ...],
    phase_start_t_ns: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if kernel.status != "computed":
        for channel_id in channel_ids:
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": channel_id,
                    "event_t_ns": phase_start_t_ns,
                    "event_id": f"{phase_id}-{channel_id}-diagnostic-{kernel.reason}",
                    "event_kind": f"diagnostic.{kernel.reason}",
                    "amplitude": 0.0,
                }
            )
        return rows
    for channel in kernel.channels:
        for index, segment in enumerate(channel.support_segments):
            for suffix, event_kind, timestamp in (
                ("start", "support-start", segment.start_t_ns),
                ("end", "support-end", segment.end_t_ns),
            ):
                rows.append(
                    {
                        "phase_id": phase_id,
                        "channel_id": channel.channel_id,
                        "event_t_ns": timestamp,
                        "event_id": f"{phase_id}-{channel.channel_id}-support-{index:06d}-{suffix}",
                        "event_kind": event_kind,
                        "amplitude": 0.0,
                    }
                )
        for index in range(channel.short_filter_bypass_count):
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": channel.channel_id,
                    "event_t_ns": channel.support_segments[
                        min(index, len(channel.support_segments) - 1)
                    ].start_t_ns,
                    "event_id": f"{phase_id}-{channel.channel_id}-filter-bypass-{index:06d}",
                    "event_kind": "diagnostic.short-filter-bypass",
                    "amplitude": 0.0,
                }
            )
        for index, point in enumerate(channel.turning_points):
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": channel.channel_id,
                    "event_t_ns": point.t_ns,
                    "event_id": f"{phase_id}-{channel.channel_id}-turning-{index:06d}",
                    "event_kind": "turning-point",
                    "amplitude": point.value_pct,
                }
            )
        for index, event in enumerate(channel.movements):
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": channel.channel_id,
                    "event_t_ns": event.event_t_ns,
                    "event_id": f"{phase_id}-{channel.channel_id}-movement-{index:06d}",
                    "event_kind": "movement",
                    "amplitude": event.amplitude_pct,
                }
            )
    return rows


def movement_kernel_from_table(
    frame: pl.DataFrame,
    *,
    phase_ids: tuple[str, ...],
    channel_ids: tuple[str, ...],
) -> MovementKernelResult:
    """Rehydrate a provider product while enforcing complete phase/channel support."""

    if not isinstance(frame, pl.DataFrame):
        raise TypeError("movement dependency must be a Polars DataFrame")
    expected_schema = {
        "phase_id": pl.String,
        "channel_id": pl.String,
        "event_t_ns": pl.Int64,
        "event_id": pl.String,
        "event_kind": pl.String,
        "amplitude": pl.Float64,
    }
    if frame.schema != expected_schema or any(
        frame[column].null_count() for column in frame.columns
    ):
        raise ValueError("movement dependency table has an invalid exact schema")
    if (
        phase_ids != tuple(dict.fromkeys(phase_ids))
        or channel_ids != tuple(sorted(set(channel_ids)))
        or not phase_ids
        or not channel_ids
    ):
        raise ValueError("phase_ids/channel_ids must be non-empty canonical inventories")
    selected = frame.filter(
        pl.col("phase_id").is_in(phase_ids) & pl.col("channel_id").is_in(channel_ids)
    ).sort(["phase_id", "channel_id", "event_t_ns", "event_id"], maintain_order=True)
    kinds = set(selected["event_kind"].to_list())
    if any(not (kind in _MOVEMENT_EVENT_KINDS or kind.startswith("diagnostic.")) for kind in kinds):
        raise ValueError("movement dependency contains an unknown event kind")
    amplitudes = selected["amplitude"].to_list()
    if any(not math.isfinite(float(value)) for value in amplitudes):
        raise ValueError("movement dependency amplitudes must be finite")
    channels: list[MovementChannelResult] = []
    gap_count = 0
    max_gap: int | None = None
    for channel_id in channel_ids:
        support_segments: list[MovementSupportSegment] = []
        turning: list[MovementTurningPoint] = []
        events: list[MovementEvent] = []
        bypass_count = 0
        for phase_id in phase_ids:
            subset = selected.filter(
                (pl.col("phase_id") == phase_id) & (pl.col("channel_id") == channel_id)
            )
            starts = sorted(
                int(value)
                for value in subset.filter(pl.col("event_kind") == "support-start")[
                    "event_t_ns"
                ].to_list()
            )
            ends = sorted(
                int(value)
                for value in subset.filter(pl.col("event_kind") == "support-end")[
                    "event_t_ns"
                ].to_list()
            )
            if len(starts) != len(ends) or not starts:
                return _noncomputed("missing_input", "no-temporal-support")
            phase_segments = [
                MovementSupportSegment(start, end) for start, end in zip(starts, ends, strict=True)
            ]
            support_segments.extend(phase_segments)
            phase_gaps = [
                right.start_t_ns - left.end_t_ns
                for left, right in zip(phase_segments, phase_segments[1:], strict=False)
            ]
            gap_count += len(phase_gaps) if channel_id == channel_ids[0] else 0
            if phase_gaps and channel_id == channel_ids[0]:
                max_gap = max(max_gap or 0, *phase_gaps)
            turning.extend(
                MovementTurningPoint(int(row["event_t_ns"]), float(row["amplitude"]))
                for row in subset.filter(pl.col("event_kind") == "turning-point").iter_rows(
                    named=True
                )
            )
            events.extend(
                MovementEvent(int(row["event_t_ns"]), float(row["amplitude"]))
                for row in subset.filter(pl.col("event_kind") == "movement").iter_rows(named=True)
            )
            bypass_count += subset.filter(
                pl.col("event_kind") == "diagnostic.short-filter-bypass"
            ).height
        channels.append(
            MovementChannelResult(
                channel_id=channel_id,
                observed_support_duration_ns=sum(
                    item.end_t_ns - item.start_t_ns for item in support_segments
                ),
                support_segments=tuple(sorted(support_segments, key=lambda item: item.start_t_ns)),
                turning_points=tuple(sorted(turning, key=lambda item: item.t_ns)),
                movements=tuple(sorted(events, key=lambda item: item.event_t_ns)),
                grid_sample_count=0,
                short_filter_bypass_count=bypass_count,
            )
        )
    starts = [segment.start_t_ns for channel in channels for segment in channel.support_segments]
    ends = [segment.end_t_ns for channel in channels for segment in channel.support_segments]
    return MovementKernelResult(
        status="computed",
        reason=None,
        channels=tuple(channels),
        sample_count=selected.height,
        source_start_t_ns=min(starts),
        source_end_t_ns=max(ends),
        gap_count=gap_count,
        max_gap_ns=max_gap,
    )


def _provider_definition() -> PreprocessingProviderDefinition:
    identity = next(
        item
        for item in REFERENCE_PREPROCESSING_IDENTITIES
        if item["provider_id"] == "movement-events-v1"
    )
    return PreprocessingProviderDefinition(
        provider_id=cast(str, identity["provider_id"]),
        provider_version=cast(str, identity["provider_version"]),
        api_version="0.1.0",
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=("semantic.control_mappings", "semantic.phases"),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id=cast(str, identity["parameter_schema_id"]),
        output_schema_id=cast(str, identity["output_schema_id"]),
        output_schema_descriptor=cast(dict[str, JsonValue], identity["output_schema_descriptor"]),
        artifact_kind=cast(str, identity["artifact_kind"]),
        output_payload_kind="table",
    )


def _typed_sequence(value: object, model_type: type[SemanticPhase] | type[ControlEffectMapping]):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic provider projection must be an ordered array")
    return tuple(model_type.model_validate(item) for item in value)


class MovementEventsProvider:
    def __init__(self) -> None:
        self._definition = _provider_definition()

    def definition(self) -> PreprocessingProviderDefinition:
        return self._definition

    def compute(
        self,
        context: AnchorPluginContext,
        recipe: ResolvedPreprocessingRecipe,
        scope: PreprocessingScope,
        dependencies: Mapping[str, ResolvedPreprocessingDependency],
    ) -> TabularArtifactPayload:
        if dependencies:
            raise ValueError("movement-events-v1 has no provider dependencies")
        if recipe.provider_id != self._definition.provider_id:
            raise ValueError("movement provider recipe identity mismatch")
        if scope.kind != "session":
            raise ValueError("movement-events-v1 v0.1 requires one session scope")
        mappings = cast(
            tuple[ControlEffectMapping, ...],
            _typed_sequence(
                context.semantic_scope.values.get("semantic.control_mappings"),
                ControlEffectMapping,
            ),
        )
        phases = cast(
            tuple[SemanticPhase, ...],
            _typed_sequence(context.semantic_scope.values.get("semantic.phases"), SemanticPhase),
        )
        canonical_mappings = _canonical_mappings(mappings)
        channel_ids = tuple(item.control_channel_id for item in canonical_mappings)
        contracts = tuple(
            item
            for item in context.input_table_contracts
            if item.modality.value == "U" and item.table_role == "samples"
        )
        u_view = context.streams.get("U")
        if u_view is None or len(contracts) != 1 or "samples" not in u_view.tables:
            raise ValueError("movement provider requires one exact U/samples table projection")
        table = u_view.tables["samples"]
        rows: list[dict[str, object]] = []
        selected_phases = tuple(
            sorted(
                (
                    phase
                    for phase in phases
                    if min(phase.end_t_ns, scope.end_t_ns) > max(phase.start_t_ns, scope.start_t_ns)
                ),
                key=lambda item: (item.start_t_ns, item.end_t_ns, item.phase_id),
            )
        )
        for phase in selected_phases:
            phase_start = max(phase.start_t_ns, scope.start_t_ns)
            phase_end = min(phase.end_t_ns, scope.end_t_ns)
            kernel = detect_movement_events(
                table,
                canonical_mappings,
                phase_start,
                phase_end,
                contracts,
                recipe.parameters,
            )
            rows.extend(_serialize_kernel(phase.phase_id, kernel, channel_ids, phase_start))
        frame = _event_frame(rows)
        return TabularArtifactPayload(
            schema_id=recipe.output_schema_id,
            schema_descriptor=recipe.output_schema_descriptor,
            frame=frame,
            order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
            artifact_kind=recipe.artifact_kind,
            grid_hash=None,
            start_t_ns=scope.start_t_ns,
            end_t_ns=scope.end_t_ns,
        )


def create_provider() -> MovementEventsProvider:
    return MovementEventsProvider()


__all__ = [
    "MovementChannelResult",
    "MovementEvent",
    "MovementEventsProvider",
    "MovementKernelResult",
    "MovementSupportSegment",
    "MovementTurningPoint",
    "O5ChannelRate",
    "O5KernelResult",
    "compute_o5_kernel",
    "create_provider",
    "detect_movement_events",
    "movement_kernel_from_table",
]
