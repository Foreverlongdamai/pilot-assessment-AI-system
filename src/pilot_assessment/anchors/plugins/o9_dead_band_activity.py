"""O9 Dead-band Activity production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives.movement import (
    MovementChannelResult,
    MovementSupportSegment,
    movement_kernel_from_table,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import nearest_within_v1, reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import AnchorPluginDefinition
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ClassificationOverride,
    ComputationTrace,
    MetricValue,
    SourceWindowV2,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

_NANOSECONDS_PER_SECOND = 1_000_000_000
_O1_MASK_SCHEMA = {
    "phase_id": pl.String,
    "t_ns": pl.Int64,
    "source_row_id": pl.Int64,
    "axis_order": pl.Int64,
    "axis_id": pl.String,
    "inside": pl.Boolean,
}
_O4_MASK_SCHEMA = {
    "phase_id": pl.String,
    "t_ns": pl.Int64,
    "source_row_id": pl.Int64,
    "stable": pl.Boolean,
}


@dataclass(frozen=True, slots=True)
class _BoundPhase:
    phase_id: str
    window: SourceWindowV2


@dataclass(frozen=True, slots=True)
class _Span:
    start_t_ns: int
    end_t_ns: int

    def __post_init__(self) -> None:
        if (
            type(self.start_t_ns) is not int
            or type(self.end_t_ns) is not int
            or self.start_t_ns < 0
            or self.end_t_ns <= self.start_t_ns
        ):
            raise ValueError("O9 spans require a positive non-negative interval")


@dataclass(frozen=True, slots=True)
class _MicroEvent:
    phase_id: str
    channel_id: str
    event_t_ns: int
    event_id: str
    amplitude_pct: float


@dataclass(frozen=True, slots=True)
class _ChannelMeasurement:
    channel_id: str
    matched_duration_ns: int
    micro_movement_count: int
    rate_hz: float
    events: tuple[_MicroEvent, ...]


@dataclass(frozen=True, slots=True)
class _PhaseMeasurement:
    phase: _BoundPhase
    status: AnchorCalculationStatusV2
    reason: str | None
    stable_duration_ns: int
    matched_sample_count: int
    matched_source_start_t_ns: int | None
    matched_source_end_t_ns: int | None
    channels: tuple[_ChannelMeasurement, ...]

    @property
    def winner(self) -> _ChannelMeasurement | None:
        if not self.channels:
            return None
        return sorted(self.channels, key=lambda item: (-item.rate_hz, item.channel_id))[0]


def _definition() -> AnchorPluginDefinition:
    entry = next(item for item in load_packaged_catalog().entries if item.anchor_id == "O9")
    return AnchorPluginDefinition(
        anchor_id=entry.anchor_id,
        definition_version=entry.definition_version,
        plugin_id=entry.plugin_id,
        plugin_version=entry.plugin_version,
        api_version="0.1.0",
        required_streams=tuple(
            value.removeprefix("stream.")
            for value in entry.required_inputs
            if value.startswith("stream.")
        ),
        required_context_paths=tuple(
            sorted(value for value in entry.required_inputs if value.startswith("context."))
        ),
        required_semantic_paths=tuple(
            sorted(value for value in entry.required_inputs if value.startswith("semantic."))
        ),
        required_reference_ids=tuple(
            sorted(
                value.removeprefix("reference.")
                for value in entry.required_inputs
                if value.startswith("reference.")
            )
        ),
        dependencies=entry.dependencies,
        parameter_schema_id=entry.parameter_schema_id,
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=entry.artifact_recipes,
    )


def _strict_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _strings(value: object, label: str, *, canonical: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered string array")
    result = tuple(_strict_string(item, f"{label}[{index}]") for index, item in enumerate(value))
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must be non-empty and unique")
    if canonical and result != tuple(sorted(result)):
        raise ValueError(f"{label} must be canonically ordered")
    return result


def _bound_phases(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[_BoundPhase, ...]:
    policy = _strict_string(temporal_recipe.get("window_policy"), "window_policy")
    if policy != "bound-phase-windows-v1":
        raise ValueError("O9 requires window_policy=bound-phase-windows-v1")
    prefix = _strict_string(temporal_recipe.get("window_id_prefix"), "window_id_prefix")
    scope_ids = _strings(temporal_recipe.get("scope_ids"), "scope_ids")
    raw = temporal_recipe.get("phase_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("phase_bindings must be an ordered array")
    parsed: list[_BoundPhase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "phase_id",
            "start_t_ns",
            "end_t_ns",
            "include_session_terminal_point",
        }:
            raise ValueError("O9 phase bindings require the exact four-key contract")
        binding = cast(Mapping[str, object], item)
        phase_id = _strict_string(binding["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(binding["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(binding["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = binding["include_session_terminal_point"]
        if type(terminal) is not bool or end <= start:
            raise ValueError("O9 phase bindings require a positive span and strict terminal flag")
        if start < context.session_window.start_t_ns or end > context.session_window.end_t_ns:
            raise ValueError("O9 phase binding lies outside the immutable session window")
        parsed.append(
            _BoundPhase(
                phase_id=phase_id,
                window=SourceWindowV2(
                    window_id=f"{prefix}-{phase_id}",
                    start_t_ns=start,
                    end_t_ns=end,
                    phase_id=phase_id,
                    event_id=None,
                    include_session_terminal_point=terminal,
                ),
            )
        )
    if tuple(item.phase_id for item in parsed) != scope_ids:
        raise ValueError("O9 phase bindings must exactly match ordered scope_ids")
    if any(
        current.window.start_t_ns < previous.window.end_t_ns
        for previous, current in zip(parsed, parsed[1:], strict=False)
    ):
        raise ValueError("O9 phase bindings must not overlap")
    return tuple(parsed)


def _parameters(parameters: Mapping[str, JsonValue]) -> tuple[float, int]:
    if not isinstance(parameters, Mapping) or set(parameters) != {
        "micro_movement_max_amplitude_pct",
        "nearest_match_tolerance_ns",
    }:
        raise ValueError("O9 v0.1 parameters require exact amplitude and tolerance fields")
    maximum = parameters["micro_movement_max_amplitude_pct"]
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, (int, float))
        or not math.isfinite(float(maximum))
        or float(maximum) < 0.0
    ):
        raise ValueError("O9 maximum micro-movement amplitude must be finite and non-negative")
    tolerance = _strict_int(parameters["nearest_match_tolerance_ns"], "nearest_match_tolerance_ns")
    return float(maximum), tolerance


def _validate_mask(frame: pl.DataFrame, expected: Mapping[str, object], label: str) -> None:
    if not isinstance(frame, pl.DataFrame) or frame.schema != expected:
        raise ValueError(f"{label} has an invalid exact schema")
    if any(frame[column].null_count() for column in frame.columns):
        raise ValueError(f"{label} contains null values")


def _phase_mask(o1_frame: pl.DataFrame, o4_frame: pl.DataFrame, phase_id: str) -> pl.DataFrame:
    _validate_mask(o1_frame, _O1_MASK_SCHEMA, "O1 desired mask")
    _validate_mask(o4_frame, _O4_MASK_SCHEMA, "O4 stable-hover mask")
    keys = ["phase_id", "t_ns", "source_row_id"]
    o1_rows = o1_frame.filter(pl.col("phase_id") == phase_id)
    o4_rows = o4_frame.filter(pl.col("phase_id") == phase_id)
    if o1_rows.select([*keys, "axis_order", "axis_id"]).is_duplicated().any():
        raise ValueError("O1 desired mask contains duplicate axis rows")
    if o4_rows.select(keys).is_duplicated().any():
        raise ValueError("O4 stable-hover mask contains duplicate sample rows")
    desired = (
        o1_rows.group_by(keys, maintain_order=True)
        .agg(pl.col("inside").all().alias("desired"))
        .sort(keys, maintain_order=True)
    )
    stable = o4_rows.select([*keys, "stable"]).sort(keys, maintain_order=True)
    if desired.is_empty() or stable.is_empty():
        raise ValueError("O9 phase has no O1/O4 mask sample inventory")
    if desired.select(keys).rows() != stable.select(keys).rows():
        raise ValueError("O1 and O4 mask sample inventories do not match for the O9 phase")
    return desired.join(stable, on=keys, how="inner", validate="1:1").sort(
        ["t_ns", "source_row_id"], maintain_order=True
    )


def _merge_spans(spans: Sequence[_Span]) -> tuple[_Span, ...]:
    ordered = sorted(spans, key=lambda item: (item.start_t_ns, item.end_t_ns))
    merged: list[_Span] = []
    for span in ordered:
        if merged and span.start_t_ns <= merged[-1].end_t_ns:
            previous = merged[-1]
            merged[-1] = _Span(previous.start_t_ns, max(previous.end_t_ns, span.end_t_ns))
        else:
            merged.append(span)
    return tuple(merged)


def _intersect_support(
    spans: tuple[_Span, ...], support: tuple[MovementSupportSegment, ...]
) -> tuple[_Span, ...]:
    intersections = []
    for span in spans:
        for segment in support:
            start = max(span.start_t_ns, segment.start_t_ns)
            end = min(span.end_t_ns, segment.end_t_ns)
            if end > start:
                intersections.append(_Span(start, end))
    return _merge_spans(intersections)


def _contains(spans: tuple[_Span, ...], timestamp: int) -> bool:
    return any(span.start_t_ns <= timestamp < span.end_t_ns for span in spans)


def _u_rows(
    context: AnchorPluginContext,
    temporal_recipe: Mapping[str, JsonValue],
    phase: _BoundPhase,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    table_role = _strict_string(temporal_recipe.get("table_role"), "table_role")
    timestamp_column = _strict_string(temporal_recipe.get("timestamp_column"), "timestamp_column")
    in_session_column = _strict_string(
        temporal_recipe.get("in_session_column"), "in_session_column"
    )
    stable_keys = _strings(temporal_recipe.get("stable_keys"), "stable_keys")
    stream = context.streams.get("U")
    table = None if stream is None else stream.tables.get(table_role)
    if table is None:
        return (), ()
    if timestamp_column not in table.columns or table.schema[timestamp_column] != pl.Int64:
        raise ValueError("O9 U timestamp column must be non-null Int64")
    if in_session_column not in table.columns or table.schema[in_session_column] != pl.Boolean:
        raise ValueError("O9 U in-session column must be non-null Boolean")
    required = (timestamp_column, in_session_column, *stable_keys)
    if any(column not in table.columns or table[column].null_count() for column in required):
        raise ValueError("O9 U temporal identity columns are missing or contain null values")
    if table.select(stable_keys).is_duplicated().any():
        raise ValueError("O9 U stable keys must identify unique rows")
    end_condition = pl.col(timestamp_column) < phase.window.end_t_ns
    if phase.window.include_session_terminal_point:
        end_condition = pl.col(timestamp_column) <= phase.window.end_t_ns
    selected = table.filter(
        pl.col(in_session_column)
        & (pl.col(timestamp_column) >= phase.window.start_t_ns)
        & end_condition
    )
    times = tuple(int(value) for value in selected[timestamp_column].to_list())
    if any(value < 0 for value in times):
        raise ValueError("O9 U timestamps must be non-negative")
    stable_ids = tuple(repr(tuple(row)) for row in selected.select(stable_keys).iter_rows())
    if len(stable_ids) != len(set(stable_ids)):
        raise ValueError("O9 U stable-key serialization is not unique")
    return times, stable_ids


def _phase_measurement(
    *,
    phase: _BoundPhase,
    o1_frame: pl.DataFrame,
    o4_frame: pl.DataFrame,
    movement_frame: pl.DataFrame,
    channel_ids: tuple[str, ...],
    maximum_amplitude_pct: float,
    tolerance_ns: int,
    mask_gap_threshold_ns: int | None,
    context: AnchorPluginContext,
    temporal_recipe: Mapping[str, JsonValue],
) -> _PhaseMeasurement:
    mask = _phase_mask(o1_frame, o4_frame, phase.phase_id)
    support_frame = mask.select(["t_ns", "source_row_id"]).with_columns(
        pl.lit(True, dtype=pl.Boolean).alias("in_session")
    )
    support = reconstruct_point_support(
        support_frame,
        timestamp_column="t_ns",
        stable_keys=("source_row_id",),
        in_session_column="in_session",
        gap_threshold_ns=mask_gap_threshold_ns,
        semantic_end_t_ns=phase.window.end_t_ns,
    )
    qualifies = tuple(bool(row["desired"] and row["stable"]) for row in mask.iter_rows(named=True))
    stable_intervals = tuple(
        interval
        for interval in support.intervals
        if interval.end_t_ns > interval.start_t_ns and qualifies[interval.source_row_index]
    )
    stable_duration_ns = sum(item.end_t_ns - item.start_t_ns for item in stable_intervals)
    if stable_duration_ns == 0:
        return _PhaseMeasurement(
            phase=phase,
            status=AnchorCalculationStatusV2.COMPUTED,
            reason="no_stable_hover",
            stable_duration_ns=0,
            matched_sample_count=0,
            matched_source_start_t_ns=None,
            matched_source_end_t_ns=None,
            channels=(),
        )

    u_times, u_stable_ids = _u_rows(context, temporal_recipe, phase)
    mask_times = tuple(int(value) for value in mask["t_ns"].to_list())
    matches = nearest_within_v1(mask_times, u_times, u_stable_ids, tolerance_ns)
    matched_intervals = tuple(
        _Span(interval.start_t_ns, interval.end_t_ns)
        for interval in support.intervals
        if interval.end_t_ns > interval.start_t_ns
        and qualifies[interval.source_row_index]
        and matches[interval.source_row_index] is not None
    )
    matched_spans = _merge_spans(matched_intervals)
    if not matched_spans:
        return _PhaseMeasurement(
            phase=phase,
            status=AnchorCalculationStatusV2.MISSING_INPUT,
            reason="no_temporal_support_U",
            stable_duration_ns=stable_duration_ns,
            matched_sample_count=0,
            matched_source_start_t_ns=None,
            matched_source_end_t_ns=None,
            channels=(),
        )

    movement = movement_kernel_from_table(
        movement_frame,
        phase_ids=(phase.phase_id,),
        channel_ids=channel_ids,
    )
    if movement.status != "computed":
        return _PhaseMeasurement(
            phase=phase,
            status=AnchorCalculationStatusV2.MISSING_INPUT,
            reason="no_temporal_support_U",
            stable_duration_ns=stable_duration_ns,
            matched_sample_count=0,
            matched_source_start_t_ns=None,
            matched_source_end_t_ns=None,
            channels=(),
        )

    matched_indexes = tuple(
        cast(int, matches[interval.source_row_index])
        for interval in support.intervals
        if interval.end_t_ns > interval.start_t_ns
        and qualifies[interval.source_row_index]
        and matches[interval.source_row_index] is not None
    )
    matched_source_times = tuple(u_times[index] for index in matched_indexes)
    channel_results: list[_ChannelMeasurement] = []
    by_channel = {item.channel_id: item for item in movement.channels}
    for channel_id in channel_ids:
        channel: MovementChannelResult = by_channel[channel_id]
        channel_spans = _intersect_support(matched_spans, channel.support_segments)
        duration_ns = sum(item.end_t_ns - item.start_t_ns for item in channel_spans)
        if duration_ns == 0:
            return _PhaseMeasurement(
                phase=phase,
                status=AnchorCalculationStatusV2.MISSING_INPUT,
                reason="no_temporal_support_U",
                stable_duration_ns=stable_duration_ns,
                matched_sample_count=0,
                matched_source_start_t_ns=None,
                matched_source_end_t_ns=None,
                channels=(),
            )
        events = []
        selected_events = movement_frame.filter(
            (pl.col("phase_id") == phase.phase_id)
            & (pl.col("channel_id") == channel_id)
            & (pl.col("event_kind") == "movement")
        ).sort(["event_t_ns", "event_id"], maintain_order=True)
        for row in selected_events.iter_rows(named=True):
            timestamp = int(row["event_t_ns"])
            amplitude = float(row["amplitude"])
            if amplitude <= maximum_amplitude_pct and _contains(channel_spans, timestamp):
                events.append(
                    _MicroEvent(
                        phase_id=phase.phase_id,
                        channel_id=channel_id,
                        event_t_ns=timestamp,
                        event_id=str(row["event_id"]),
                        amplitude_pct=amplitude,
                    )
                )
        count = len(events)
        rate = count / (duration_ns / _NANOSECONDS_PER_SECOND)
        channel_results.append(
            _ChannelMeasurement(
                channel_id=channel_id,
                matched_duration_ns=duration_ns,
                micro_movement_count=count,
                rate_hz=rate,
                events=tuple(events),
            )
        )
    return _PhaseMeasurement(
        phase=phase,
        status=AnchorCalculationStatusV2.COMPUTED,
        reason=None,
        stable_duration_ns=stable_duration_ns,
        matched_sample_count=len(matched_indexes),
        matched_source_start_t_ns=min(matched_source_times),
        matched_source_end_t_ns=max(matched_source_times),
        channels=tuple(channel_results),
    )


def _diagnostic(result: _PhaseMeasurement) -> DomainErrorData:
    assert result.reason == "no_temporal_support_U"
    return DomainErrorData(
        error_code="anchor.o9.no_temporal_support_U",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O9 phase {result.phase.phase_id} has stable hover but no matched U support.",
        field_or_path="streams.U",
        node_or_anchor_id="O9",
        remediation="Provide U timestamps within the configured nearest-match tolerance.",
        diagnostics={
            "phase_id": result.phase.phase_id,
            "stable_duration_ns": result.stable_duration_ns,
        },
    )


def _raw_metrics(
    stable_duration_ns: int,
    winner: _ChannelMeasurement | None,
    channel_count: int,
) -> dict[str, MetricValue]:
    return {
        "stable-opportunity-duration": MetricValue(
            scalar_kind="float",
            value=float(stable_duration_ns / _NANOSECONDS_PER_SECOND),
            unit="s",
        ),
        "matched-stable-duration": MetricValue(
            scalar_kind="float",
            value=float(
                0.0 if winner is None else winner.matched_duration_ns / _NANOSECONDS_PER_SECOND
            ),
            unit="s",
        ),
        "micro-movement-count": MetricValue(
            scalar_kind="integer",
            value=0 if winner is None else winner.micro_movement_count,
            unit="count",
        ),
        "channel-count": MetricValue(
            scalar_kind="integer",
            value=channel_count,
            unit="count",
        ),
    }


def _override(result: _PhaseMeasurement) -> ClassificationOverride | None:
    if result.reason != "no_stable_hover":
        return None
    return ClassificationOverride(
        code="no_stable_hover",
        details={"phase_id": result.phase.phase_id, "stable_duration_ns": 0},
    )


def _trace(
    results: tuple[_PhaseMeasurement, ...],
    diagnostics: tuple[DomainErrorData, ...],
) -> ComputationTrace:
    starts = tuple(
        result.matched_source_start_t_ns
        for result in results
        if result.matched_source_start_t_ns is not None
    )
    ends = tuple(
        result.matched_source_end_t_ns
        for result in results
        if result.matched_source_end_t_ns is not None
    )
    windows = tuple(result.phase.window for result in results)
    return ComputationTrace(
        sample_count=sum(result.matched_sample_count for result in results),
        source_start_t_ns=min(starts) if starts else None,
        source_end_t_ns=max(ends) if ends else None,
        analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
        analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
        grid_id="movement-grid-100hz-phase-start-v1",
        window_ids=tuple(window.window_id for window in windows),
        interpolation_method="native-mask-left-hold-v1",
        matching_method="o1-o4-mask-nearest-within-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: _PhaseMeasurement, channel_count: int) -> AnchorBreakdownMeasurement:
    diagnostic = (
        () if result.status is AnchorCalculationStatusV2.COMPUTED else (_diagnostic(result),)
    )
    winner = result.winner
    return AnchorBreakdownMeasurement(
        breakdown_id=result.phase.phase_id,
        calculation_status=result.status,
        primary_value=(
            MetricValue(scalar_kind="float", value=float(winner.rate_hz), unit="Hz")
            if winner is not None
            else None
        ),
        primary_value_reason="no_stable_hover" if result.reason == "no_stable_hover" else None,
        raw_metrics=_raw_metrics(result.stable_duration_ns, winner, channel_count),
        classification_override_candidate=_override(result),
        trace=_trace((result,), diagnostic),
        diagnostics=diagnostic,
    )


def _aggregate_channels(
    results: tuple[_PhaseMeasurement, ...], channel_ids: tuple[str, ...]
) -> tuple[_ChannelMeasurement, ...]:
    aggregated = []
    for channel_id in channel_ids:
        members = tuple(
            channel
            for result in results
            for channel in result.channels
            if channel.channel_id == channel_id
        )
        duration_ns = sum(item.matched_duration_ns for item in members)
        if duration_ns == 0:
            continue
        events = tuple(event for item in members for event in item.events)
        count = sum(item.micro_movement_count for item in members)
        aggregated.append(
            _ChannelMeasurement(
                channel_id=channel_id,
                matched_duration_ns=duration_ns,
                micro_movement_count=count,
                rate_hz=count / (duration_ns / _NANOSECONDS_PER_SECOND),
                events=events,
            )
        )
    return tuple(aggregated)


def _artifact_payload(
    definition: AnchorPluginDefinition,
    channels: tuple[_ChannelMeasurement, ...],
    windows: tuple[SourceWindowV2, ...],
) -> TabularArtifactPayload | None:
    rows = tuple(event for channel in channels for event in channel.events)
    if not rows:
        return None
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "phase_id": pl.Series("phase_id", [row.phase_id for row in rows], dtype=pl.String),
            "channel_id": pl.Series(
                "channel_id", [row.channel_id for row in rows], dtype=pl.String
            ),
            "event_t_ns": pl.Series("event_t_ns", [row.event_t_ns for row in rows], dtype=pl.Int64),
            "event_id": pl.Series("event_id", [row.event_id for row in rows], dtype=pl.String),
            "amplitude": pl.Series(
                "amplitude", [row.amplitude_pct for row in rows], dtype=pl.Float64
            ),
        }
    ).sort(["phase_id", "channel_id", "event_t_ns", "event_id"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(window.start_t_ns for window in windows),
        end_t_ns=max(window.end_t_ns for window in windows),
    )


class O9DeadBandActivityPlugin:
    def __init__(self) -> None:
        self._definition = _definition()

    def definition(self) -> AnchorPluginDefinition:
        return self._definition

    def compute(
        self,
        context: AnchorPluginContext,
        parameters: Mapping[str, JsonValue],
        temporal_recipe: Mapping[str, JsonValue],
        dependencies: ResolvedDependencies,
        artifacts: AnchorArtifactEmitter,
    ) -> AnchorMeasurement:
        maximum_amplitude, tolerance_ns = _parameters(parameters)
        phases = _bound_phases(context, temporal_recipe)
        channel_ids = _strings(
            temporal_recipe.get("control_channel_ids"),
            "control_channel_ids",
            canonical=True,
        )
        if "mask_gap_threshold_ns" not in temporal_recipe:
            raise ValueError("O9 requires an explicit mask_gap_threshold_ns binding")
        raw_gap = temporal_recipe["mask_gap_threshold_ns"]
        mask_gap_threshold_ns = (
            None if raw_gap is None else _strict_int(raw_gap, "mask_gap_threshold_ns", minimum=0)
        )
        o1_dependency = dependencies.artifacts.get("o1-mask")
        o4_dependency = dependencies.artifacts.get("o4-mask")
        movement_dependency = dependencies.preprocessing.get("movement-events")
        if (
            o1_dependency is None
            or not isinstance(o1_dependency.payload, ReadOnlyTabularPayload)
            or o4_dependency is None
            or not isinstance(o4_dependency.payload, ReadOnlyTabularPayload)
            or movement_dependency is None
            or not isinstance(movement_dependency.payload, ReadOnlyTabularPayload)
        ):
            raise ValueError("O9 requires resolved O1/O4 mask and movement table dependencies")
        o1_frame = o1_dependency.payload.frame
        o4_frame = o4_dependency.payload.frame
        movement_frame = movement_dependency.payload.frame
        phase_results = tuple(
            _phase_measurement(
                phase=phase,
                o1_frame=o1_frame,
                o4_frame=o4_frame,
                movement_frame=movement_frame,
                channel_ids=channel_ids,
                maximum_amplitude_pct=maximum_amplitude,
                tolerance_ns=tolerance_ns,
                mask_gap_threshold_ns=mask_gap_threshold_ns,
                context=context,
                temporal_recipe=temporal_recipe,
            )
            for phase in phases
        )
        windows = tuple(item.window for item in phases)
        breakdowns = tuple(_breakdown(result, len(channel_ids)) for result in phase_results)
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        stable_duration_ns = sum(result.stable_duration_ns for result in phase_results)
        session_channels = _aggregate_channels(phase_results, channel_ids)
        session_winner = (
            sorted(session_channels, key=lambda item: (-item.rate_hz, item.channel_id))[0]
            if session_channels
            else None
        )

        if stable_duration_ns == 0:
            session_status = AnchorCalculationStatusV2.COMPUTED
            primary = None
            primary_reason = "no_stable_hover"
            override = ClassificationOverride(
                code="no_stable_hover",
                details={
                    "phase_ids": [result.phase.phase_id for result in phase_results],
                    "stable_duration_ns": 0,
                },
            )
        elif session_winner is None:
            session_status = AnchorCalculationStatusV2.MISSING_INPUT
            primary = None
            primary_reason = None
            override = None
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED
            primary = MetricValue(
                scalar_kind="float", value=float(session_winner.rate_hz), unit="Hz"
            )
            primary_reason = None
            override = None

        payload = (
            _artifact_payload(self._definition, session_channels, windows)
            if session_winner is not None
            else None
        )
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("micro-movement-events", payload),)
        )
        return AnchorMeasurement(
            anchor_id="O9",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason=primary_reason,
            raw_metrics=_raw_metrics(stable_duration_ns, session_winner, len(channel_ids)),
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=override,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=_trace(phase_results, diagnostics),
            diagnostics=diagnostics,
        )


def create_plugin() -> O9DeadBandActivityPlugin:
    return O9DeadBandActivityPlugin()


__all__ = ["O9DeadBandActivityPlugin", "create_plugin"]
