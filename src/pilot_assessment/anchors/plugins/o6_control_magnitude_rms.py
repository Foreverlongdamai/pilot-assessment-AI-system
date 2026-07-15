"""O6 Control Magnitude RMS production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import left_hold_integral_v1, reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    ControlEffectMapping,
    ResolvedInputTableContract,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ComputationTrace,
    MetricValue,
    SourceWindowV2,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

O6KernelStatus = Literal["computed", "missing_input", "not_computable"]
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}


@dataclass(frozen=True, slots=True)
class O6ChannelEnergy:
    channel_id: str
    normalized_square_integral_ns: float
    observed_support_duration_ns: int
    rms_percent: float
    weight: float

    def __post_init__(self) -> None:
        if type(self.channel_id) is not str or not self.channel_id:
            raise ValueError("O6 channel_id must be non-empty")
        for value, label in (
            (self.normalized_square_integral_ns, "normalized square integral"),
            (self.rms_percent, "channel RMS"),
            (self.weight, "channel weight"),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"O6 {label} must be finite and non-negative")
        if type(self.observed_support_duration_ns) is not int or (
            self.observed_support_duration_ns <= 0
        ):
            raise ValueError("O6 channel support duration must be a positive strict integer")


@dataclass(frozen=True, slots=True)
class O6KernelResult:
    status: O6KernelStatus
    reason: str | None
    total_rms_percent: float | None
    channels: tuple[O6ChannelEnergy, ...]
    observed_support_duration_ns: int
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None

    def __post_init__(self) -> None:
        if self.status == "computed":
            if self.reason is not None or self.total_rms_percent is None or not self.channels:
                raise ValueError("computed O6 result requires a total and channel energies")
            if not math.isfinite(self.total_rms_percent) or self.total_rms_percent < 0.0:
                raise ValueError("computed O6 total must be finite and non-negative")
        elif self.reason is None or self.total_rms_percent is not None or self.channels:
            raise ValueError("non-computed O6 result requires only a reason")
        for value, label in (
            (self.observed_support_duration_ns, "observed support duration"),
            (self.sample_count, "sample count"),
            (self.gap_count, "gap count"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"O6 {label} must be a non-negative strict integer")


@dataclass(frozen=True, slots=True)
class _BoundPhase:
    phase_id: str
    window: SourceWindowV2


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O6"
    )
    return AnchorPluginDefinition(
        anchor_id=catalog_entry.anchor_id,
        definition_version=catalog_entry.definition_version,
        plugin_id=catalog_entry.plugin_id,
        plugin_version=catalog_entry.plugin_version,
        api_version="0.1.0",
        required_streams=tuple(
            value.removeprefix("stream.")
            for value in catalog_entry.required_inputs
            if value.startswith("stream.")
        ),
        required_context_paths=tuple(
            sorted(value for value in catalog_entry.required_inputs if value.startswith("context."))
        ),
        required_semantic_paths=tuple(
            sorted(
                value for value in catalog_entry.required_inputs if value.startswith("semantic.")
            )
        ),
        required_reference_ids=tuple(
            sorted(
                value.removeprefix("reference.")
                for value in catalog_entry.required_inputs
                if value.startswith("reference.")
            )
        ),
        dependencies=catalog_entry.dependencies,
        parameter_schema_id=catalog_entry.parameter_schema_id,
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=catalog_entry.artifact_recipes,
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
    if len(result) != len(set(result)) or (canonical and result != tuple(sorted(result))):
        raise ValueError(f"{label} must be unique and canonical")
    return result


def _bound_phases(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[_BoundPhase, ...]:
    if _strict_string(temporal_recipe.get("window_policy"), "window_policy") != (
        "bound-phase-windows-v1"
    ):
        raise ValueError("O6 requires window_policy=bound-phase-windows-v1")
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
            raise ValueError("O6 phase bindings require the exact four-key contract")
        binding = cast(Mapping[str, object], item)
        phase_id = _strict_string(binding["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(binding["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(binding["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = binding["include_session_terminal_point"]
        if type(terminal) is not bool or end <= start:
            raise ValueError("O6 phase bindings require a positive span and strict terminal flag")
        if start < context.session_window.start_t_ns or end > context.session_window.end_t_ns:
            raise ValueError("O6 phase binding lies outside the immutable session window")
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
        raise ValueError("O6 phase bindings must exactly match ordered scope_ids")
    if any(
        current.window.start_t_ns < previous.window.end_t_ns
        for previous, current in zip(parsed, parsed[1:], strict=False)
    ):
        raise ValueError("O6 phase bindings must not overlap")
    return tuple(parsed)


def _selected_mappings(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[ControlEffectMapping, ...]:
    mapping_ids = _strings(
        temporal_recipe.get("control_mapping_ids"), "control_mapping_ids", canonical=True
    )
    raw = context.semantic_scope.values.get("semantic.control_mappings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("semantic.control_mappings must be an ordered array")
    mappings = tuple(ControlEffectMapping.model_validate(item) for item in raw)
    by_id = {item.control_mapping_id: item for item in mappings}
    if len(by_id) != len(mappings) or any(mapping_id not in by_id for mapping_id in mapping_ids):
        raise ValueError("O6 control mapping projection is incomplete")
    by_channel: dict[str, ControlEffectMapping] = {}
    for mapping_id in mapping_ids:
        mapping = by_id[mapping_id]
        previous = by_channel.setdefault(mapping.control_channel_id, mapping)
        if (
            previous.control_unit,
            previous.lower,
            previous.trim,
            previous.upper,
        ) != (mapping.control_unit, mapping.lower, mapping.trim, mapping.upper):
            raise ValueError("O6 selected mappings disagree on one channel calibration")
    if not by_channel:
        raise ValueError("O6 requires at least one configured active channel")
    return tuple(by_channel[channel_id] for channel_id in sorted(by_channel))


def _channel_weights(
    parameters: Mapping[str, JsonValue], channel_ids: tuple[str, ...]
) -> tuple[tuple[str, float], ...]:
    if not isinstance(parameters, Mapping) or set(parameters) != {"channel_weights"}:
        raise ValueError("O6 v0.1 parameters require exactly channel_weights")
    raw = parameters["channel_weights"]
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("O6 channel_weights must be an ordered array")
    parsed: list[tuple[str, float]] = []
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"channel_id", "weight"}:
            raise ValueError("O6 weight items require exact channel_id and weight fields")
        weight_item = cast(Mapping[str, object], item)
        channel_id = weight_item["channel_id"]
        weight = weight_item["weight"]
        if (
            type(channel_id) is not str
            or not channel_id
            or isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(float(weight))
            or float(weight) < 0.0
        ):
            raise ValueError("O6 weights require stable IDs and finite non-negative values")
        parsed.append((channel_id, float(weight)))
    result = tuple(parsed)
    if tuple(channel for channel, _weight in result) != channel_ids:
        raise ValueError("O6 weights must exactly cover canonical configured channels")
    if abs(math.fsum(weight for _channel, weight in result) - 1.0) > 1e-12:
        raise ValueError("O6 channel weights must sum to one")
    return result


def _input_contract(
    context: AnchorPluginContext,
    table_role: str,
) -> ResolvedInputTableContract | None:
    matches = tuple(
        item
        for item in context.input_table_contracts
        if item.modality.value == "U" and item.table_role == table_role
    )
    return matches[0] if len(matches) == 1 else None


def _noncomputed(
    status: O6KernelStatus,
    reason: str,
    *,
    sample_count: int = 0,
    source_start_t_ns: int | None = None,
    source_end_t_ns: int | None = None,
    gap_count: int = 0,
    max_gap_ns: int | None = None,
) -> O6KernelResult:
    return O6KernelResult(
        status=status,
        reason=reason,
        total_rms_percent=None,
        channels=(),
        observed_support_duration_ns=0,
        sample_count=sample_count,
        source_start_t_ns=source_start_t_ns,
        source_end_t_ns=source_end_t_ns,
        gap_count=gap_count,
        max_gap_ns=max_gap_ns,
    )


def compute_o6_kernel(
    *,
    u_table: pl.DataFrame,
    mappings: tuple[ControlEffectMapping, ...],
    weights: tuple[tuple[str, float], ...],
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    include_session_terminal_point: bool,
    input_contract: ResolvedInputTableContract,
    temporal_recipe: Mapping[str, JsonValue],
) -> O6KernelResult:
    """Compute native-time O6 over one phase without filtering performance values."""

    if not isinstance(u_table, pl.DataFrame):
        raise TypeError("u_table must be a Polars DataFrame")
    start = _strict_int(scope_start_t_ns, "scope_start_t_ns")
    end = _strict_int(scope_end_t_ns, "scope_end_t_ns", minimum=1)
    if end <= start or type(include_session_terminal_point) is not bool:
        raise ValueError("O6 scope requires a positive span and strict terminal flag")
    if type(mappings) is not tuple or any(
        not isinstance(item, ControlEffectMapping) for item in mappings
    ):
        raise TypeError("O6 mappings must be a typed tuple")
    channel_ids = tuple(mapping.control_channel_id for mapping in mappings)
    if (
        not channel_ids
        or channel_ids != tuple(sorted(channel_ids))
        or len(set(channel_ids)) != len(channel_ids)
    ):
        raise ValueError("O6 mappings must identify canonical unique channels")
    if type(weights) is not tuple or any(
        type(channel_id) is not str
        or not channel_id
        or isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(float(weight))
        or float(weight) < 0.0
        for channel_id, weight in weights
    ):
        raise ValueError("O6 weights must be a typed finite non-negative tuple")
    if tuple(channel for channel, _weight in weights) != channel_ids:
        raise ValueError("O6 weights must match the mapping channels")
    if abs(math.fsum(float(weight) for _channel, weight in weights) - 1.0) > 1e-12:
        raise ValueError("O6 weights must sum to one")
    if not isinstance(input_contract, ResolvedInputTableContract):
        raise TypeError("input_contract must be a ResolvedInputTableContract")

    table_role = _strict_string(temporal_recipe.get("table_role"), "table_role")
    timestamp_column = _strict_string(temporal_recipe.get("timestamp_column"), "timestamp_column")
    in_session_column = _strict_string(
        temporal_recipe.get("in_session_column"), "in_session_column"
    )
    stable_keys = _strings(temporal_recipe.get("stable_keys"), "stable_keys")
    raw_gap_threshold = temporal_recipe.get("gap_threshold_ns")
    gap_threshold_ns = (
        None if raw_gap_threshold is None else _strict_int(raw_gap_threshold, "gap_threshold_ns")
    )
    if input_contract.modality.value != "U" or input_contract.table_role != table_role:
        return _noncomputed("not_computable", "input-contract-mismatch")
    fields = {field.field_name: field for field in input_contract.fields}
    if (
        timestamp_column not in fields
        or fields[timestamp_column].unit != "ns"
        or in_session_column not in fields
        or fields[in_session_column].unit != "bool"
        or any(key not in fields for key in stable_keys)
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
    required_columns = {timestamp_column, in_session_column, *stable_keys}
    if any(column not in u_table.columns for column in required_columns):
        return _noncomputed("not_computable", "temporal-field-missing")

    endpoint = (pl.col(timestamp_column) < end) | (
        pl.lit(include_session_terminal_point) & (pl.col(timestamp_column) == end)
    )
    active = u_table.filter(
        (pl.col(timestamp_column) >= start) & endpoint & pl.col(in_session_column)
    )
    if active.is_empty():
        return _noncomputed("missing_input", "no-temporal-support")
    times = cast(list[int], active[timestamp_column].to_list())
    if any(type(value) is not int or value < 0 for value in times):
        return _noncomputed("not_computable", "timestamp-invalid")
    support = reconstruct_point_support(
        active,
        timestamp_column=timestamp_column,
        stable_keys=stable_keys,
        in_session_column=in_session_column,
        gap_threshold_ns=gap_threshold_ns,
        semantic_end_t_ns=end,
    )
    if support.observed_duration_ns == 0:
        return _noncomputed(
            "not_computable",
            "zero-support-duration",
            sample_count=active.height,
            source_start_t_ns=min(times),
            source_end_t_ns=max(times),
            gap_count=support.gap_count,
            max_gap_ns=support.max_gap_ns,
        )

    weight_by_channel = dict(weights)
    channels: list[O6ChannelEnergy] = []
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
        normalized = tuple(
            (float(value) - mapping.trim) / (mapping.upper - mapping.trim)
            if float(value) >= mapping.trim
            else (float(value) - mapping.trim) / (mapping.trim - mapping.lower)
            for value in raw_values
        )
        integral = left_hold_integral_v1(tuple(value * value for value in normalized), support)
        rms_percent = 100.0 * math.sqrt(integral / support.observed_duration_ns)
        channels.append(
            O6ChannelEnergy(
                channel_id=mapping.control_channel_id,
                normalized_square_integral_ns=integral,
                observed_support_duration_ns=support.observed_duration_ns,
                rms_percent=rms_percent,
                weight=weight_by_channel[mapping.control_channel_id],
            )
        )
    total = math.sqrt(math.fsum(channel.weight * channel.rms_percent**2 for channel in channels))
    return O6KernelResult(
        status="computed",
        reason=None,
        total_rms_percent=total,
        channels=tuple(channels),
        observed_support_duration_ns=support.observed_duration_ns,
        sample_count=active.height,
        source_start_t_ns=min(times),
        source_end_t_ns=max(times),
        gap_count=support.gap_count,
        max_gap_ns=support.max_gap_ns,
    )


def _aggregate_results(
    results: tuple[O6KernelResult, ...], weights: tuple[tuple[str, float], ...]
) -> O6KernelResult:
    if not results or any(result.status != "computed" for result in results):
        raise ValueError("O6 aggregate requires non-empty computed phase results")
    channel_ids = tuple(channel for channel, _weight in weights)
    duration = sum(result.observed_support_duration_ns for result in results)
    channels: list[O6ChannelEnergy] = []
    for channel_id, weight in weights:
        phase_channels = tuple(
            next(channel for channel in result.channels if channel.channel_id == channel_id)
            for result in results
        )
        integral = math.fsum(channel.normalized_square_integral_ns for channel in phase_channels)
        channels.append(
            O6ChannelEnergy(
                channel_id=channel_id,
                normalized_square_integral_ns=integral,
                observed_support_duration_ns=duration,
                rms_percent=100.0 * math.sqrt(integral / duration),
                weight=weight,
            )
        )
    if tuple(channel.channel_id for channel in channels) != channel_ids:
        raise ValueError("O6 aggregate channel identity drifted")
    total = math.sqrt(math.fsum(channel.weight * channel.rms_percent**2 for channel in channels))
    starts = tuple(
        result.source_start_t_ns for result in results if result.source_start_t_ns is not None
    )
    ends = tuple(result.source_end_t_ns for result in results if result.source_end_t_ns is not None)
    gaps = tuple(result.max_gap_ns for result in results if result.max_gap_ns is not None)
    return O6KernelResult(
        status="computed",
        reason=None,
        total_rms_percent=total,
        channels=tuple(channels),
        observed_support_duration_ns=duration,
        sample_count=sum(result.sample_count for result in results),
        source_start_t_ns=min(starts) if starts else None,
        source_end_t_ns=max(ends) if ends else None,
        gap_count=sum(result.gap_count for result in results),
        max_gap_ns=max(gaps) if gaps else None,
    )


def _diagnostic(result: O6KernelResult, phase_id: str) -> DomainErrorData:
    assert result.reason is not None
    return DomainErrorData(
        error_code=f"anchor.o6.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=(
            f"O6 phase {phase_id} could not produce control-magnitude evidence: {result.reason}"
        ),
        field_or_path=(
            "streams.U.samples"
            if result.status == "missing_input"
            else "execution_plan.entries.O6.temporal_recipe"
        ),
        node_or_anchor_id="O6",
        remediation=(
            "Provide at least one native U support interval in the declared phase."
            if result.status == "missing_input"
            else "Correct the U contract, control calibration, weights, or temporal binding."
        ),
        diagnostics={
            "phase_id": phase_id,
            "reason": result.reason,
            "sample_count": result.sample_count,
        },
    )


def _raw_metrics(result: O6KernelResult) -> dict[str, MetricValue]:
    values: dict[str, MetricValue] = {
        "observed-support-duration": MetricValue(
            scalar_kind="integer", value=result.observed_support_duration_ns, unit="ns"
        ),
        "sample-count": MetricValue(scalar_kind="integer", value=result.sample_count, unit="count"),
        "channel-count": MetricValue(
            scalar_kind="integer", value=len(result.channels), unit="count"
        ),
        "gap-count": MetricValue(scalar_kind="integer", value=result.gap_count, unit="count"),
    }
    if result.max_gap_ns is not None:
        values["max-gap"] = MetricValue(scalar_kind="integer", value=result.max_gap_ns, unit="ns")
    return values


def _trace(
    result: O6KernelResult,
    windows: tuple[SourceWindowV2, ...],
    diagnostics: tuple[DomainErrorData, ...],
) -> ComputationTrace:
    return ComputationTrace(
        sample_count=result.sample_count,
        source_start_t_ns=result.source_start_t_ns,
        source_end_t_ns=result.source_end_t_ns,
        analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
        analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
        grid_id=None,
        window_ids=tuple(window.window_id for window in windows),
        interpolation_method="native-left-hold-v1",
        matching_method="piecewise-control-calibration-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: O6KernelResult, window: SourceWindowV2) -> AnchorBreakdownMeasurement:
    diagnostics = (
        () if result.status == "computed" else (_diagnostic(result, window.phase_id or "unknown"),)
    )
    primary = (
        MetricValue(
            scalar_kind="float",
            value=cast(float, result.total_rms_percent),
            unit="percent_full_travel",
        )
        if result.status == "computed"
        else None
    )
    return AnchorBreakdownMeasurement(
        breakdown_id=window.phase_id or window.window_id,
        calculation_status=AnchorCalculationStatusV2(result.status),
        primary_value=primary,
        primary_value_reason=None,
        raw_metrics=_raw_metrics(result),
        classification_override_candidate=None,
        trace=_trace(result, (window,), diagnostics),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[O6KernelResult, ...],
    windows: tuple[SourceWindowV2, ...],
) -> TabularArtifactPayload | None:
    rows = tuple(
        (window, channel)
        for result, window in zip(results, windows, strict=True)
        for channel in result.channels
    )
    if not rows:
        return None
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "phase_id": pl.Series(
                "phase_id", [window.phase_id for window, _channel in rows], dtype=pl.String
            ),
            "channel_id": pl.Series(
                "channel_id", [channel.channel_id for _window, channel in rows], dtype=pl.String
            ),
            "start_t_ns": pl.Series(
                "start_t_ns", [window.start_t_ns for window, _channel in rows], dtype=pl.Int64
            ),
            "end_t_ns": pl.Series(
                "end_t_ns", [window.end_t_ns for window, _channel in rows], dtype=pl.Int64
            ),
            "rms": pl.Series(
                "rms", [channel.rms_percent for _window, channel in rows], dtype=pl.Float64
            ),
            "weight": pl.Series(
                "weight", [channel.weight for _window, channel in rows], dtype=pl.Float64
            ),
        }
    ).sort(["phase_id", "channel_id", "start_t_ns", "end_t_ns"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "channel_id", "start_t_ns", "end_t_ns"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(window.start_t_ns for window in windows),
        end_t_ns=max(window.end_t_ns for window in windows),
    )


class O6ControlMagnitudeRmsPlugin:
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
        del dependencies
        phases = _bound_phases(context, temporal_recipe)
        mappings = _selected_mappings(context, temporal_recipe)
        channel_ids = tuple(mapping.control_channel_id for mapping in mappings)
        weights = _channel_weights(parameters, channel_ids)
        table_role = _strict_string(temporal_recipe.get("table_role"), "table_role")
        contract = _input_contract(context, table_role)
        u_view = context.streams.get("U")
        u_table = None if u_view is None else u_view.tables.get(table_role)

        results: list[O6KernelResult] = []
        for phase in phases:
            if contract is None or (
                u_view is not None and contract.stream_aligned_schema_id != u_view.aligned_schema_id
            ):
                results.append(_noncomputed("not_computable", "input-contract-mismatch"))
            elif u_table is None:
                results.append(_noncomputed("missing_input", "no-temporal-support"))
            else:
                results.append(
                    compute_o6_kernel(
                        u_table=u_table,
                        mappings=mappings,
                        weights=weights,
                        scope_start_t_ns=phase.window.start_t_ns,
                        scope_end_t_ns=phase.window.end_t_ns,
                        include_session_terminal_point=phase.window.include_session_terminal_point,
                        input_contract=contract,
                        temporal_recipe=temporal_recipe,
                    )
                )
        phase_results = tuple(results)
        windows = tuple(phase.window for phase in phases)
        breakdowns = tuple(
            _breakdown(result, window)
            for result, window in zip(phase_results, windows, strict=True)
        )
        noncomputed = tuple(
            AnchorCalculationStatusV2(result.status)
            for result in phase_results
            if result.status != "computed"
        )
        if not phases:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE
        elif noncomputed:
            session_status = max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED
        session_result = (
            _aggregate_results(phase_results, weights)
            if session_status is AnchorCalculationStatusV2.COMPUTED
            else None
        )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = (
            _artifact_payload(self._definition, phase_results, windows)
            if session_result is not None
            else None
        )
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("rms-contribution-trace", payload),)
        )
        primary = (
            MetricValue(
                scalar_kind="float",
                value=cast(float, session_result.total_rms_percent),
                unit="percent_full_travel",
            )
            if session_result is not None
            else None
        )
        trace_result = session_result or _noncomputed("not_computable", "session-incomplete")
        return AnchorMeasurement(
            anchor_id="O6",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason=None,
            raw_metrics=_raw_metrics(trace_result),
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=None,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=_trace(trace_result, windows, diagnostics),
            diagnostics=diagnostics,
        )


def create_plugin() -> O6ControlMagnitudeRmsPlugin:
    return O6ControlMagnitudeRmsPlugin()


__all__ = [
    "O6ChannelEnergy",
    "O6ControlMagnitudeRmsPlugin",
    "O6KernelResult",
    "compute_o6_kernel",
    "create_plugin",
]
