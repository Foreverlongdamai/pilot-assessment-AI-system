"""Native-rate envelope kernels shared by trajectory-performance anchors."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.primitives.models import (
    O1AxisSummary,
    O1KernelResult,
    O1KernelStatus,
    O1MaskRow,
)
from pilot_assessment.anchors.temporal import (
    left_hold_integral_v1,
    reconstruct_point_support,
)
from pilot_assessment.contracts.anchor_execution import (
    EnvelopeDefinition,
    ResolvedInputTableContract,
    SemanticEvent,
    SemanticPhase,
    TaskTargetDefinition,
)

_SIGNED_INT64_MAX = 2**63 - 1
_NANOSECONDS_PER_SECOND = 1_000_000_000
_METERS_PER_FOOT = 0.3048
_LENGTH_TO_METERS = {
    "m": 1.0,
    "km": 1_000.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": _METERS_PER_FOOT,
    "in": 0.0254,
}
_NUMERIC_DTYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}

O3KernelStatus = Literal["computed", "missing_input", "not_computable"]


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _recipe_string(recipe: Mapping[str, JsonValue], key: str) -> str:
    value = recipe.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"temporal_recipe.{key} must be a non-empty string")
    return value


def _recipe_strings(recipe: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = recipe.get(key)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"temporal_recipe.{key} must be an ordered string array")
    normalized = tuple(value)
    if not normalized or any(type(item) is not str or not item for item in normalized):
        raise ValueError(f"temporal_recipe.{key} must contain non-empty strings")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"temporal_recipe.{key} must be unique")
    return cast(tuple[str, ...], normalized)


def _noncomputed(
    *,
    status: O1KernelStatus,
    reason: str,
    phase_duration_ns: int,
    sample_count: int = 0,
    source_start_t_ns: int | None = None,
    source_end_t_ns: int | None = None,
    gap_count: int = 0,
    max_gap_ns: int | None = None,
    observed_support_duration_ns: int = 0,
    mask_rows: tuple[O1MaskRow, ...] = (),
) -> O1KernelResult:
    return O1KernelResult(
        status=status,
        reason=reason,
        precision_percent=None,
        phase_duration_ns=phase_duration_ns,
        observed_support_duration_ns=observed_support_duration_ns,
        desired_joint_duration_ns=0,
        sample_count=sample_count,
        source_start_t_ns=source_start_t_ns,
        source_end_t_ns=source_end_t_ns,
        gap_count=gap_count,
        max_gap_ns=max_gap_ns,
        axis_summaries=(),
        mask_rows=mask_rows,
    )


def _x_contract(
    input_contracts: tuple[ResolvedInputTableContract, ...], table_role: str
) -> ResolvedInputTableContract | None:
    matches = tuple(
        contract
        for contract in input_contracts
        if contract.modality.value == "X" and contract.table_role == table_role
    )
    if len(matches) > 1:
        raise ValueError("input contracts contain duplicate X table roles")
    return matches[0] if matches else None


def compute_o1_kernel(
    x_table: pl.DataFrame,
    phase: SemanticPhase,
    envelope: EnvelopeDefinition,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    input_contracts: tuple[ResolvedInputTableContract, ...],
    parameters: Mapping[str, JsonValue],
    temporal_recipe: Mapping[str, JsonValue],
) -> O1KernelResult:
    """Compute desired-envelope precision without staging artifacts or scoring.

    Finite values are always assessed, including arbitrarily poor values.  The
    only absent-data outcome is a true lack of mathematical temporal support;
    no coverage threshold or data-quality classification is applied.
    """

    if not isinstance(x_table, pl.DataFrame):
        raise TypeError("x_table must be a Polars DataFrame")
    if not isinstance(phase, SemanticPhase) or not isinstance(envelope, EnvelopeDefinition):
        raise TypeError("phase and envelope must use the typed semantic contracts")
    if not isinstance(input_contracts, tuple) or any(
        not isinstance(item, ResolvedInputTableContract) for item in input_contracts
    ):
        raise TypeError("input_contracts must be a typed tuple")
    if not isinstance(parameters, Mapping) or parameters:
        raise ValueError("O1 v0.1 parameters must be the exact empty object")
    if not isinstance(temporal_recipe, Mapping):
        raise TypeError("temporal_recipe must be a mapping")

    scope_start = _strict_int(scope_start_t_ns, "scope_start_t_ns")
    scope_end = _strict_int(scope_end_t_ns, "scope_end_t_ns", minimum=1)
    start = max(scope_start, phase.start_t_ns)
    end = min(scope_end, phase.end_t_ns)
    if end <= start:
        raise ValueError("O1 scope must overlap the semantic phase")
    phase_duration = end - start

    table_role = _recipe_string(temporal_recipe, "table_role")
    timestamp_column = _recipe_string(temporal_recipe, "timestamp_column")
    in_session_column = _recipe_string(temporal_recipe, "in_session_column")
    stable_keys = _recipe_strings(temporal_recipe, "stable_keys")
    gap_threshold = _strict_int(
        temporal_recipe.get("gap_threshold_ns"), "temporal_recipe.gap_threshold_ns"
    )
    contract = _x_contract(input_contracts, table_role)
    if contract is None:
        return _noncomputed(
            status="not_computable",
            reason="input-contract-missing",
            phase_duration_ns=phase_duration,
        )

    fields = {field.field_name: field for field in contract.fields}
    structural_columns = (timestamp_column, in_session_column, *stable_keys)
    if any(column not in fields or column not in x_table.columns for column in structural_columns):
        return _noncomputed(
            status="not_computable",
            reason="temporal-field-missing",
            phase_duration_ns=phase_duration,
        )
    for limit in envelope.axis_limits:
        field = fields.get(limit.metric_id)
        if field is None or limit.metric_id not in x_table.columns or field.unit != limit.unit:
            return _noncomputed(
                status="not_computable",
                reason="envelope-contract-mismatch",
                phase_duration_ns=phase_duration,
            )

    terminal = phase.include_session_terminal_point and end == phase.end_t_ns
    time_expression = (pl.col(timestamp_column) >= start) & (
        (pl.col(timestamp_column) <= end) if terminal else (pl.col(timestamp_column) < end)
    )
    active = (
        x_table.filter(time_expression & pl.col(in_session_column))
        .sort([timestamp_column, *stable_keys], maintain_order=True)
        .select(x_table.columns)
    )
    if active.is_empty():
        return _noncomputed(
            status="missing_input",
            reason="no-temporal-support",
            phase_duration_ns=phase_duration,
        )

    times = cast(list[int], active[timestamp_column].to_list())
    source_start, source_end = min(times), max(times)
    support = reconstruct_point_support(
        active,
        timestamp_column=timestamp_column,
        stable_keys=stable_keys,
        in_session_column=in_session_column,
        gap_threshold_ns=gap_threshold,
        semantic_end_t_ns=end,
    )
    if support.observed_duration_ns == 0:
        return _noncomputed(
            status="missing_input",
            reason="no-temporal-support",
            phase_duration_ns=phase_duration,
            sample_count=active.height,
            source_start_t_ns=source_start,
            source_end_t_ns=source_end,
            gap_count=support.gap_count,
            max_gap_ns=support.max_gap_ns,
        )

    source_ids_raw = active[stable_keys[0]].to_list()
    source_ids: list[int] = []
    for value in source_ids_raw:
        if type(value) is not int or value < 0 or value > _SIGNED_INT64_MAX:
            return _noncomputed(
                status="not_computable",
                reason="source-row-id-invalid",
                phase_duration_ns=phase_duration,
                sample_count=active.height,
                source_start_t_ns=source_start,
                source_end_t_ns=source_end,
                gap_count=support.gap_count,
                max_gap_ns=support.max_gap_ns,
                observed_support_duration_ns=support.observed_duration_ns,
            )
        source_ids.append(value)

    axis_masks: list[tuple[str, int, tuple[bool, ...]]] = []
    for axis_order, limit in enumerate(envelope.axis_limits):
        raw_values = active[limit.metric_id].to_list()
        if any(value is None for value in raw_values):
            return _noncomputed(
                status="missing_input",
                reason="metric-value-missing",
                phase_duration_ns=phase_duration,
                sample_count=active.height,
                source_start_t_ns=source_start,
                source_end_t_ns=source_end,
                gap_count=support.gap_count,
                max_gap_ns=support.max_gap_ns,
                observed_support_duration_ns=support.observed_duration_ns,
            )
        values: list[float] = []
        for value in raw_values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return _noncomputed(
                    status="not_computable",
                    reason="metric-value-nonnumeric",
                    phase_duration_ns=phase_duration,
                    sample_count=active.height,
                    source_start_t_ns=source_start,
                    source_end_t_ns=source_end,
                    gap_count=support.gap_count,
                    max_gap_ns=support.max_gap_ns,
                    observed_support_duration_ns=support.observed_duration_ns,
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                return _noncomputed(
                    status="not_computable",
                    reason="metric-value-nonfinite",
                    phase_duration_ns=phase_duration,
                    sample_count=active.height,
                    source_start_t_ns=source_start,
                    source_end_t_ns=source_end,
                    gap_count=support.gap_count,
                    max_gap_ns=support.max_gap_ns,
                    observed_support_duration_ns=support.observed_duration_ns,
                )
            values.append(numeric)
        axis_masks.append(
            (
                limit.metric_id,
                axis_order,
                tuple(abs(value) <= limit.desired_abs_max for value in values),
            )
        )

    joint_mask = tuple(
        all(axis_mask[row_index] for _axis_id, _axis_order, axis_mask in axis_masks)
        for row_index in range(active.height)
    )
    axis_summaries = tuple(
        O1AxisSummary(
            axis_id=axis_id,
            axis_order=axis_order,
            desired_duration_ns=int(
                left_hold_integral_v1(
                    tuple(1.0 if inside else 0.0 for inside in axis_mask), support
                )
            ),
        )
        for axis_id, axis_order, axis_mask in axis_masks
    )
    joint_duration = int(
        left_hold_integral_v1(tuple(1.0 if inside else 0.0 for inside in joint_mask), support)
    )
    mask_rows = tuple(
        O1MaskRow(
            phase_id=phase.phase_id,
            t_ns=timestamp,
            source_row_id=source_id,
            axis_order=axis_order,
            axis_id=axis_id,
            inside=axis_mask[row_index],
        )
        for row_index, (timestamp, source_id) in enumerate(zip(times, source_ids, strict=True))
        for axis_id, axis_order, axis_mask in (
            *axis_masks,
            ("joint", len(axis_masks), joint_mask),
        )
    )
    return O1KernelResult(
        status="computed",
        reason=None,
        precision_percent=100.0 * joint_duration / phase_duration,
        phase_duration_ns=phase_duration,
        observed_support_duration_ns=support.observed_duration_ns,
        desired_joint_duration_ns=joint_duration,
        sample_count=active.height,
        source_start_t_ns=source_start,
        source_end_t_ns=source_end,
        gap_count=support.gap_count,
        max_gap_ns=support.max_gap_ns,
        axis_summaries=axis_summaries,
        mask_rows=mask_rows,
    )


@dataclass(frozen=True, slots=True)
class O3CaptureTraceRow:
    event_id: str
    t_ns: int
    source_row_id: int
    overshoot_ft: float
    inside_hover: bool

    def __post_init__(self) -> None:
        if type(self.event_id) is not str or not self.event_id:
            raise ValueError("event_id must be a non-empty string")
        for value, label in (
            (self.t_ns, "t_ns"),
            (self.source_row_id, "source_row_id"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative strict integer")
        if not math.isfinite(self.overshoot_ft) or self.overshoot_ft < 0:
            raise ValueError("overshoot_ft must be finite and non-negative")
        if type(self.inside_hover) is not bool:
            raise TypeError("inside_hover must be a strict boolean")


@dataclass(frozen=True, slots=True)
class O3KernelResult:
    status: O3KernelStatus
    reason: str | None
    overshoot_ft: float | None
    settling_time_s: float | None
    observed_wait_s: float | None
    capture_missed: bool
    capture_hold_start_t_ns: int | None
    capture_hold_end_t_ns: int | None
    observation_duration_ns: int
    observed_support_duration_ns: int
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None
    trace_rows: tuple[O3CaptureTraceRow, ...]

    def __post_init__(self) -> None:
        if self.status not in {"computed", "missing_input", "not_computable"}:
            raise ValueError("unsupported O3 kernel status")
        if type(self.capture_missed) is not bool:
            raise TypeError("capture_missed must be a strict boolean")
        if self.status == "computed":
            if self.reason is not None or self.overshoot_ft is None or not self.trace_rows:
                raise ValueError("computed O3 results require an overshoot trace and no reason")
            if self.capture_missed:
                if (
                    self.settling_time_s is not None
                    or self.observed_wait_s is None
                    or self.capture_hold_start_t_ns is not None
                    or self.capture_hold_end_t_ns is not None
                ):
                    raise ValueError("missed O3 capture has an invalid metric shape")
            elif (
                self.settling_time_s is None
                or self.observed_wait_s is not None
                or self.capture_hold_start_t_ns is None
                or self.capture_hold_end_t_ns is None
            ):
                raise ValueError("captured O3 results require settling and hold bounds")
        elif (
            self.reason is None
            or self.overshoot_ft is not None
            or self.settling_time_s is not None
            or self.observed_wait_s is not None
            or self.capture_missed
            or self.capture_hold_start_t_ns is not None
            or self.capture_hold_end_t_ns is not None
            or self.trace_rows
        ):
            raise ValueError("non-computed O3 results have an invalid metric shape")

        for value, label in (
            (self.observation_duration_ns, "observation_duration_ns"),
            (self.observed_support_duration_ns, "observed_support_duration_ns"),
            (self.sample_count, "sample_count"),
            (self.gap_count, "gap_count"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative strict integer")
        if self.observation_duration_ns <= 0:
            raise ValueError("observation_duration_ns must be positive")
        if self.observed_support_duration_ns > self.observation_duration_ns:
            raise ValueError("observed support cannot exceed the observation duration")
        if len(self.trace_rows) > self.sample_count:
            raise ValueError("trace rows cannot exceed the candidate sample count")
        for value, label in (
            (self.overshoot_ft, "overshoot_ft"),
            (self.settling_time_s, "settling_time_s"),
            (self.observed_wait_s, "observed_wait_s"),
        ):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{label} must be finite and non-negative")
        if (self.source_start_t_ns is None) != (self.source_end_t_ns is None):
            raise ValueError("source bounds must be both present or both absent")
        if (
            self.source_start_t_ns is not None
            and self.source_end_t_ns is not None
            and (
                type(self.source_start_t_ns) is not int
                or type(self.source_end_t_ns) is not int
                or self.source_start_t_ns < 0
                or self.source_end_t_ns < self.source_start_t_ns
            )
        ):
            raise ValueError("source bounds must be ordered non-negative integers")
        if self.max_gap_ns is not None and (
            type(self.max_gap_ns) is not int or self.max_gap_ns <= 0
        ):
            raise ValueError("max_gap_ns must be a positive strict integer when present")
        if (
            self.capture_hold_start_t_ns is not None
            and self.capture_hold_end_t_ns is not None
            and self.capture_hold_end_t_ns < self.capture_hold_start_t_ns
        ):
            raise ValueError("capture hold bounds must be ordered")
        canonical = tuple(sorted(self.trace_rows, key=lambda row: (row.t_ns, row.source_row_id)))
        if self.trace_rows != canonical:
            raise ValueError("O3 trace rows must use timestamp/stable-row order")


@dataclass(frozen=True, slots=True)
class _PositionBinding:
    axis_id: str
    x_field: str
    target_component_index: int


def _strict_row_id(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > _SIGNED_INT64_MAX:
        raise ValueError(f"{label} must be a non-negative signed-int64 integer")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _position_bindings(recipe: Mapping[str, JsonValue]) -> tuple[_PositionBinding, ...]:
    raw = recipe.get("position_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.position_bindings must be an ordered array")
    bindings: list[_PositionBinding] = []
    expected_keys = {"axis_id", "x_field", "target_component_index"}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != expected_keys:
            raise ValueError(f"position binding {index} must use the exact three-key contract")
        typed_item = cast(Mapping[str, object], item)
        axis_id = typed_item["axis_id"]
        x_field = typed_item["x_field"]
        component = typed_item["target_component_index"]
        if type(axis_id) is not str or not axis_id or type(x_field) is not str or not x_field:
            raise ValueError("position binding IDs must be non-empty strings")
        if type(component) is not int:
            raise ValueError("target_component_index must be a strict integer")
        bindings.append(_PositionBinding(axis_id, x_field, component))
    if tuple(binding.target_component_index for binding in bindings) != (0, 1, 2):
        raise ValueError("O3 position bindings must be ordered target components 0, 1, 2")
    if (
        len({binding.axis_id for binding in bindings}) != 3
        or len({binding.x_field for binding in bindings}) != 3
    ):
        raise ValueError("O3 position binding axes and fields must be unique")
    return tuple(bindings)


def _o3_noncomputed(
    *,
    status: O3KernelStatus,
    reason: str,
    observation_duration_ns: int,
    sample_count: int = 0,
    source_bounds: tuple[int, int] | None = None,
    observed_support_duration_ns: int = 0,
    gap_count: int = 0,
    max_gap_ns: int | None = None,
) -> O3KernelResult:
    return O3KernelResult(
        status=status,
        reason=reason,
        overshoot_ft=None,
        settling_time_s=None,
        observed_wait_s=None,
        capture_missed=False,
        capture_hold_start_t_ns=None,
        capture_hold_end_t_ns=None,
        observation_duration_ns=observation_duration_ns,
        observed_support_duration_ns=observed_support_duration_ns,
        sample_count=sample_count,
        source_start_t_ns=None if source_bounds is None else source_bounds[0],
        source_end_t_ns=None if source_bounds is None else source_bounds[1],
        gap_count=gap_count,
        max_gap_ns=max_gap_ns,
        trace_rows=(),
    )


def _o3_position_factors(
    bindings: tuple[_PositionBinding, ...],
    contract: ResolvedInputTableContract,
    target: TaskTargetDefinition,
    envelope: EnvelopeDefinition,
) -> tuple[tuple[float, float, float], float, dict[str, float]] | None:
    fields = {field.field_name: field for field in contract.fields}
    x_factors: list[float] = []
    for binding in bindings:
        field = fields.get(binding.x_field)
        if (
            field is None
            or field.dtype_id not in _NUMERIC_DTYPES
            or field.nullable
            or field.unit not in _LENGTH_TO_METERS
        ):
            return None
        x_factors.append(_LENGTH_TO_METERS[field.unit])
    target_factor = _LENGTH_TO_METERS.get(target.position.unit)
    if target_factor is None:
        return None
    limit_factors: dict[str, float] = {}
    binding_ids = {binding.axis_id for binding in bindings}
    for limit in envelope.axis_limits:
        factor = _LENGTH_TO_METERS.get(limit.unit)
        if factor is None or limit.metric_id not in binding_ids:
            return None
        limit_factors[limit.metric_id] = factor
    return cast(tuple[float, float, float], tuple(x_factors)), target_factor, limit_factors


def compute_o3_kernel(
    x_table: pl.DataFrame,
    event: SemanticEvent,
    target: TaskTargetDefinition,
    envelope: EnvelopeDefinition,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    input_contracts: tuple[ResolvedInputTableContract, ...],
    parameters: Mapping[str, JsonValue],
    temporal_recipe: Mapping[str, JsonValue],
) -> O3KernelResult:
    """Measure directional overshoot and the first fully confirmed hover hold."""

    if not isinstance(x_table, pl.DataFrame):
        raise TypeError("x_table must be a Polars DataFrame")
    if not isinstance(event, SemanticEvent):
        raise TypeError("event must be a SemanticEvent")
    if not isinstance(target, TaskTargetDefinition) or not isinstance(envelope, EnvelopeDefinition):
        raise TypeError("target and envelope must use typed semantic contracts")
    if not isinstance(input_contracts, tuple) or any(
        not isinstance(item, ResolvedInputTableContract) for item in input_contracts
    ):
        raise TypeError("input_contracts must be a typed tuple")
    if not isinstance(parameters, Mapping) or set(parameters) != {"capture_hold_ns"}:
        raise ValueError("O3 v0.1 parameters require exactly capture_hold_ns")
    capture_hold = parameters["capture_hold_ns"]
    if type(capture_hold) is not int or capture_hold < 0:
        raise ValueError("capture_hold_ns must be a non-negative strict integer")
    if not isinstance(temporal_recipe, Mapping):
        raise TypeError("temporal_recipe must be a mapping")
    if type(scope_start_t_ns) is not int or type(scope_end_t_ns) is not int:
        raise TypeError("O3 scope bounds must be strict integers")
    start = max(scope_start_t_ns, event.t_ns)
    end = scope_end_t_ns
    if start < 0 or end <= start:
        raise ValueError("O3 scope must be a positive event observation span")
    observation_duration = end - start

    table_role = _recipe_string(temporal_recipe, "table_role")
    timestamp_column = _recipe_string(temporal_recipe, "timestamp_column")
    in_session_column = _recipe_string(temporal_recipe, "in_session_column")
    stable_keys = _recipe_strings(temporal_recipe, "stable_keys")
    if len(stable_keys) != 1:
        raise ValueError("O3 v0.1 requires exactly one stable row key")
    gap_threshold = _strict_int(
        temporal_recipe.get("gap_threshold_ns"),
        "temporal_recipe.gap_threshold_ns",
    )
    bindings = _position_bindings(temporal_recipe)
    contract = _x_contract(input_contracts, table_role)
    if contract is None:
        return _o3_noncomputed(
            status="not_computable",
            reason="input-contract-missing",
            observation_duration_ns=observation_duration,
        )
    if target.arrival_axis is None:
        return _o3_noncomputed(
            status="not_computable",
            reason="arrival-axis-missing",
            observation_duration_ns=observation_duration,
        )
    if contract.coordinate_frame_id != target.position.coordinate_frame_id:
        return _o3_noncomputed(
            status="not_computable",
            reason="coordinate-frame-mismatch",
            observation_duration_ns=observation_duration,
        )
    if envelope.target_id != target.target_id or event.target_id != target.target_id:
        return _o3_noncomputed(
            status="not_computable",
            reason="target-envelope-mismatch",
            observation_duration_ns=observation_duration,
        )
    factors = _o3_position_factors(bindings, contract, target, envelope)
    if factors is None:
        return _o3_noncomputed(
            status="not_computable",
            reason="position-contract-incompatible",
            observation_duration_ns=observation_duration,
        )
    x_factors, target_factor, limit_factors = factors

    required_columns = (
        timestamp_column,
        in_session_column,
        *stable_keys,
        *(binding.x_field for binding in bindings),
    )
    contract_fields = {field.field_name for field in contract.fields}
    if any(
        column not in contract_fields or column not in x_table.columns
        for column in required_columns
    ):
        return _o3_noncomputed(
            status="not_computable",
            reason="position-contract-incompatible",
            observation_duration_ns=observation_duration,
        )
    active = x_table.filter(
        (pl.col(timestamp_column) >= start)
        & (pl.col(timestamp_column) < end)
        & pl.col(in_session_column)
    ).sort([timestamp_column, *stable_keys], maintain_order=True)
    if active.is_empty():
        return _o3_noncomputed(
            status="missing_input",
            reason="no-temporal-support",
            observation_duration_ns=observation_duration,
        )

    times = tuple(_strict_row_id(value, "X t_ns") for value in active[timestamp_column])
    source_ids = tuple(_strict_row_id(value, "X stable row ID") for value in active[stable_keys[0]])
    source_bounds = (times[0], times[-1])
    support = reconstruct_point_support(
        active,
        timestamp_column=timestamp_column,
        stable_keys=stable_keys,
        in_session_column=in_session_column,
        gap_threshold_ns=gap_threshold,
        semantic_end_t_ns=end,
    )

    target_position_m = tuple(
        _finite_number(value, "target position") * target_factor for value in target.position.values
    )
    arrival_axis = tuple(
        _finite_number(value, "arrival axis") for value in target.arrival_axis.values
    )
    axis_norm = math.hypot(*arrival_axis)
    if not math.isfinite(axis_norm) or axis_norm <= 0:
        return _o3_noncomputed(
            status="not_computable",
            reason="arrival-axis-invalid",
            observation_duration_ns=observation_duration,
            sample_count=active.height,
            source_bounds=source_bounds,
            observed_support_duration_ns=support.observed_duration_ns,
            gap_count=support.gap_count,
            max_gap_ns=support.max_gap_ns,
        )
    unit_axis = tuple(value / axis_norm for value in arrival_axis)
    binding_index = {binding.axis_id: index for index, binding in enumerate(bindings)}

    all_rows: list[O3CaptureTraceRow] = []
    for row_index, row in enumerate(active.iter_rows(named=True)):
        position_m = tuple(
            _finite_number(row[binding.x_field], binding.x_field) * x_factors[index]
            for index, binding in enumerate(bindings)
        )
        displacement_m = tuple(position_m[index] - target_position_m[index] for index in range(3))
        try:
            directional_m = math.fsum(
                unit_axis[index] * displacement_m[index] for index in range(3)
            )
        except OverflowError:
            directional_m = math.inf
        overshoot_ft = max(0.0, directional_m / _METERS_PER_FOOT)
        if not math.isfinite(overshoot_ft):
            return _o3_noncomputed(
                status="not_computable",
                reason="position-value-nonfinite",
                observation_duration_ns=observation_duration,
                sample_count=active.height,
                source_bounds=source_bounds,
                observed_support_duration_ns=support.observed_duration_ns,
                gap_count=support.gap_count,
                max_gap_ns=support.max_gap_ns,
            )
        inside_hover = all(
            abs(displacement_m[binding_index[limit.metric_id]])
            <= limit.desired_abs_max * limit_factors[limit.metric_id]
            for limit in envelope.axis_limits
        )
        all_rows.append(
            O3CaptureTraceRow(
                event_id=event.event_id,
                t_ns=times[row_index],
                source_row_id=source_ids[row_index],
                overshoot_ft=overshoot_ft,
                inside_hover=inside_hover,
            )
        )

    hold_start: int | None = None
    hold_end: int | None = None
    if capture_hold == 0:
        for interval in support.intervals:
            if all_rows[interval.source_row_index].inside_hover:
                hold_start = interval.start_t_ns
                hold_end = hold_start
                break
    else:
        run_start: int | None = None
        run_end: int | None = None
        for interval in support.intervals:
            if interval.end_t_ns <= interval.start_t_ns:
                continue
            inside = all_rows[interval.source_row_index].inside_hover
            if not inside:
                run_start = None
                run_end = None
                continue
            if run_start is None or run_end != interval.start_t_ns:
                run_start = interval.start_t_ns
            run_end = interval.end_t_ns
            if run_end - run_start >= capture_hold:
                hold_start = run_start
                hold_end = run_start + capture_hold
                break

    if hold_end is None:
        trace_rows = tuple(all_rows)
    elif capture_hold == 0:
        trace_rows = tuple(row for row in all_rows if row.t_ns <= hold_end)
    else:
        trace_rows = tuple(row for row in all_rows if row.t_ns < hold_end)
    overshoot = max(row.overshoot_ft for row in trace_rows)
    missed = hold_start is None or hold_end is None
    return O3KernelResult(
        status="computed",
        reason=None,
        overshoot_ft=overshoot,
        settling_time_s=(None if missed else (hold_start - start) / _NANOSECONDS_PER_SECOND),
        observed_wait_s=(observation_duration / _NANOSECONDS_PER_SECOND if missed else None),
        capture_missed=missed,
        capture_hold_start_t_ns=None if missed else hold_start,
        capture_hold_end_t_ns=None if missed else hold_end,
        observation_duration_ns=observation_duration,
        observed_support_duration_ns=support.observed_duration_ns,
        sample_count=active.height,
        source_start_t_ns=trace_rows[0].t_ns,
        source_end_t_ns=trace_rows[-1].t_ns,
        gap_count=support.gap_count,
        max_gap_ns=support.max_gap_ns,
        trace_rows=trace_rows,
    )


__all__ = [
    "O3CaptureTraceRow",
    "O3KernelResult",
    "O3KernelStatus",
    "compute_o1_kernel",
    "compute_o3_kernel",
]
