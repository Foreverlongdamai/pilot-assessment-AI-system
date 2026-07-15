"""Deterministic time-aligned reference join used by O2.

The kernel works only from frozen table/frame/unit contracts and an explicit
versioned affine frame transform.  It never infers a commanded path from X,
falls back to nearest-path matching, extrapolates, or bridges a reference gap.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.anchor_execution import (
    ReferenceTableContract,
    ResolvedInputTableContract,
    SemanticPhase,
)

O2KernelStatus = Literal["computed", "missing_input", "not_computable"]

_SIGNED_INT64_MAX = 2**63 - 1
_LENGTH_TO_METERS = {
    "m": 1.0,
    "km": 1_000.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "in": 0.0254,
}
_METERS_PER_FOOT = 0.3048


def _strict_nonnegative_int(value: int, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative strict integer")


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


@dataclass(frozen=True, slots=True)
class O2TrackingErrorRow:
    phase_id: str
    t_ns: int
    source_row_id: int
    reference_row_id: int
    error_x_ft: float
    error_y_ft: float
    error_z_ft: float
    error_norm_ft: float

    def __post_init__(self) -> None:
        if type(self.phase_id) is not str or not self.phase_id:
            raise ValueError("phase_id must be a non-empty string")
        for value, label in (
            (self.t_ns, "t_ns"),
            (self.source_row_id, "source_row_id"),
            (self.reference_row_id, "reference_row_id"),
        ):
            _strict_nonnegative_int(value, label)
        components = (self.error_x_ft, self.error_y_ft, self.error_z_ft)
        if any(not math.isfinite(value) for value in (*components, self.error_norm_ft)):
            raise ValueError("tracking errors must be finite")
        expected = math.hypot(*components)
        if not math.isclose(self.error_norm_ft, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("error_norm_ft must equal the 3D component norm")


@dataclass(frozen=True, slots=True)
class O2KernelResult:
    status: O2KernelStatus
    reason: str | None
    peak_excursion_ft: float | None
    peak_t_ns: int | None
    peak_source_row_id: int | None
    candidate_point_count: int
    joined_point_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    reference_start_t_ns: int | None
    reference_end_t_ns: int | None
    trace_rows: tuple[O2TrackingErrorRow, ...]

    def __post_init__(self) -> None:
        if self.status not in {"computed", "missing_input", "not_computable"}:
            raise ValueError("unsupported O2 kernel status")
        peak_values = (self.peak_excursion_ft, self.peak_t_ns, self.peak_source_row_id)
        if self.status == "computed":
            if self.reason is not None or any(value is None for value in peak_values):
                raise ValueError("computed O2 results require a complete peak and no reason")
            if not self.trace_rows:
                raise ValueError("computed O2 results require at least one trace row")
        elif self.reason is None or any(value is not None for value in peak_values):
            raise ValueError("non-computed O2 results require a reason and no peak")
        if self.peak_excursion_ft is not None and (
            not math.isfinite(self.peak_excursion_ft) or self.peak_excursion_ft < 0
        ):
            raise ValueError("peak_excursion_ft must be finite and non-negative")
        for value, label in (
            (self.candidate_point_count, "candidate_point_count"),
            (self.joined_point_count, "joined_point_count"),
        ):
            _strict_nonnegative_int(value, label)
        if self.joined_point_count != len(self.trace_rows):
            raise ValueError("joined point count must equal the trace row count")
        if self.joined_point_count > self.candidate_point_count:
            raise ValueError("joined points cannot exceed candidate X points")
        for start, end, label in (
            (self.source_start_t_ns, self.source_end_t_ns, "source"),
            (self.reference_start_t_ns, self.reference_end_t_ns, "reference"),
        ):
            if (start is None) != (end is None):
                raise ValueError(f"{label} bounds must be both present or both absent")
            if start is not None and end is not None:
                _strict_nonnegative_int(start, f"{label}_start_t_ns")
                _strict_nonnegative_int(end, f"{label}_end_t_ns")
                if end < start:
                    raise ValueError(f"{label} bounds must be ordered")
        canonical_rows = tuple(
            sorted(self.trace_rows, key=lambda row: (row.t_ns, row.source_row_id))
        )
        if self.trace_rows != canonical_rows:
            raise ValueError("O2 trace rows must use timestamp/stable-row order")


@dataclass(frozen=True, slots=True)
class _AxisBinding:
    axis_id: str
    x_field: str
    reference_field: str


@dataclass(frozen=True, slots=True)
class _AffineTransform:
    transform_id: str
    source_frame_id: str
    target_frame_id: str
    matrix: tuple[float, ...]
    translation_m: tuple[float, ...]

    def apply(self, vector_m: tuple[float, float, float]) -> tuple[float, float, float]:
        return cast(
            tuple[float, float, float],
            tuple(
                sum(self.matrix[row * 3 + column] * vector_m[column] for column in range(3))
                + self.translation_m[row]
                for row in range(3)
            ),
        )


@dataclass(frozen=True, slots=True)
class _ReferencePoint:
    t_ns: int
    row_id: int
    position_m: tuple[float, float, float]


def _axis_bindings(recipe: Mapping[str, JsonValue]) -> tuple[_AxisBinding, ...]:
    raw = recipe.get("axis_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.axis_bindings must be an ordered array")
    bindings: list[_AxisBinding] = []
    expected_keys = {"axis_id", "x_field", "reference_field"}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != expected_keys:
            raise ValueError(f"axis binding {index} must use the exact three-key contract")
        typed_item = cast(Mapping[str, object], item)
        values = tuple(typed_item[key] for key in ("axis_id", "x_field", "reference_field"))
        if any(type(value) is not str or not value for value in values):
            raise ValueError(f"axis binding {index} values must be non-empty strings")
        bindings.append(_AxisBinding(*cast(tuple[str, str, str], values)))
    if tuple(binding.axis_id for binding in bindings) != ("x", "y", "z"):
        raise ValueError("O2 axis bindings must be exactly ordered x, y, z")
    if (
        len({binding.x_field for binding in bindings}) != 3
        or len({binding.reference_field for binding in bindings}) != 3
    ):
        raise ValueError("O2 axis fields must be unique")
    return tuple(bindings)


def _sequence_numbers(value: object, *, length: int, label: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered numeric array")
    result = tuple(_finite_number(item, label) for item in value)
    if len(result) != length:
        raise ValueError(f"{label} must contain exactly {length} values")
    return result


def _coordinate_transform(
    recipe: Mapping[str, JsonValue],
    *,
    source_frame_id: str,
    target_frame_id: str,
) -> tuple[_AffineTransform | None, str | None]:
    raw = recipe.get("coordinate_transform")
    if raw is None:
        return None, "coordinate_transform_missing"
    expected_keys = {
        "transform_id",
        "source_frame_id",
        "target_frame_id",
        "matrix_row_major",
        "translation_m",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected_keys:
        raise ValueError("temporal_recipe.coordinate_transform has an invalid shape")
    typed_raw = cast(Mapping[str, object], raw)
    transform_id = typed_raw["transform_id"]
    source = typed_raw["source_frame_id"]
    target = typed_raw["target_frame_id"]
    if any(type(value) is not str or not value for value in (transform_id, source, target)):
        raise ValueError("coordinate transform IDs must be non-empty strings")
    if source != source_frame_id or target != target_frame_id:
        return None, "coordinate_transform_contract_mismatch"
    return (
        _AffineTransform(
            transform_id=cast(str, transform_id),
            source_frame_id=cast(str, source),
            target_frame_id=cast(str, target),
            matrix=_sequence_numbers(
                typed_raw["matrix_row_major"], length=9, label="coordinate transform matrix"
            ),
            translation_m=_sequence_numbers(
                typed_raw["translation_m"],
                length=3,
                label="coordinate transform translation",
            ),
        ),
        None,
    )


def _field_factors(
    bindings: tuple[_AxisBinding, ...],
    x_contract: ResolvedInputTableContract,
    reference_contract: ReferenceTableContract,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    numeric_dtypes = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}
    x_fields = {field.field_name: field for field in x_contract.fields}
    reference_fields = {field.field_name: field for field in reference_contract.fields}
    x_factors: list[float] = []
    reference_factors: list[float] = []
    for binding in bindings:
        x_field = x_fields.get(binding.x_field)
        reference_field = reference_fields.get(binding.reference_field)
        if (
            x_field is None
            or reference_field is None
            or x_field.dtype_id not in numeric_dtypes
            or reference_field.dtype_id not in numeric_dtypes
            or x_field.nullable
            or reference_field.nullable
            or x_field.unit not in _LENGTH_TO_METERS
            or reference_field.unit not in _LENGTH_TO_METERS
        ):
            return None
        x_factors.append(_LENGTH_TO_METERS[x_field.unit])
        reference_factors.append(_LENGTH_TO_METERS[reference_field.unit])
    return (
        cast(tuple[float, float, float], tuple(x_factors)),
        cast(tuple[float, float, float], tuple(reference_factors)),
    )


def _noncomputed(
    *,
    status: O2KernelStatus,
    reason: str,
    candidate_count: int,
    source_bounds: tuple[int, int] | None,
    reference_bounds: tuple[int, int] | None,
) -> O2KernelResult:
    return O2KernelResult(
        status=status,
        reason=reason,
        peak_excursion_ft=None,
        peak_t_ns=None,
        peak_source_row_id=None,
        candidate_point_count=candidate_count,
        joined_point_count=0,
        source_start_t_ns=None if source_bounds is None else source_bounds[0],
        source_end_t_ns=None if source_bounds is None else source_bounds[1],
        reference_start_t_ns=None if reference_bounds is None else reference_bounds[0],
        reference_end_t_ns=None if reference_bounds is None else reference_bounds[1],
        trace_rows=(),
    )


def _reference_points(
    table: pl.DataFrame,
    contract: ReferenceTableContract,
    bindings: tuple[_AxisBinding, ...],
    factors: tuple[float, float, float],
    transform: _AffineTransform,
) -> tuple[_ReferencePoint, ...]:
    time_field = contract.session_time_field
    in_session_field = contract.in_session_field
    row_field = contract.stable_row_id_field
    required = (
        time_field,
        in_session_field,
        row_field,
        *(item.reference_field for item in bindings),
    )
    if any(field not in table.columns for field in required):
        return ()
    ordered = table.filter(pl.col(in_session_field)).sort(
        [time_field, row_field], maintain_order=True
    )
    points: list[_ReferencePoint] = []
    seen_times: set[int] = set()
    for row in ordered.iter_rows(named=True):
        t_ns = _strict_row_id(row[time_field], "reference t_ns")
        if t_ns in seen_times:
            continue
        seen_times.add(t_ns)
        row_id = _strict_row_id(row[row_field], "reference stable row ID")
        raw_position = cast(
            tuple[float, float, float],
            tuple(
                _finite_number(row[binding.reference_field], binding.reference_field)
                * factors[index]
                for index, binding in enumerate(bindings)
            ),
        )
        points.append(
            _ReferencePoint(
                t_ns=t_ns,
                row_id=row_id,
                position_m=transform.apply(raw_position),
            )
        )
    return tuple(points)


def _interpolated_reference(
    t_ns: int,
    points: tuple[_ReferencePoint, ...],
    times: tuple[int, ...],
    gap_threshold_ns: int,
) -> tuple[tuple[float, float, float], int] | None:
    index = bisect_left(times, t_ns)
    if index < len(points) and points[index].t_ns == t_ns:
        point = points[index]
        return point.position_m, point.row_id
    if index == 0 or index == len(points):
        return None
    left = points[index - 1]
    right = points[index]
    delta = right.t_ns - left.t_ns
    if delta <= 0 or delta > gap_threshold_ns:
        return None
    ratio = (t_ns - left.t_ns) / delta
    return (
        cast(
            tuple[float, float, float],
            tuple(
                left.position_m[axis] + ratio * (right.position_m[axis] - left.position_m[axis])
                for axis in range(3)
            ),
        ),
        left.row_id,
    )


def compute_o2_kernel(
    x_table: pl.DataFrame,
    reference_table: pl.DataFrame,
    phase: SemanticPhase,
    x_contract: ResolvedInputTableContract,
    reference_contract: ReferenceTableContract,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    temporal_recipe: Mapping[str, JsonValue],
) -> O2KernelResult:
    """Compute the phase-local 3D peak excursion on native X timestamps."""

    if not isinstance(x_table, pl.DataFrame) or not isinstance(reference_table, pl.DataFrame):
        raise TypeError("O2 inputs must be Polars DataFrames")
    if not isinstance(phase, SemanticPhase):
        raise TypeError("phase must be a SemanticPhase")
    if not isinstance(x_contract, ResolvedInputTableContract) or not isinstance(
        reference_contract, ReferenceTableContract
    ):
        raise TypeError("O2 table contracts must use the typed contract models")
    if x_contract.modality.value != "X":
        raise ValueError("x_contract must describe modality X")
    if not isinstance(temporal_recipe, Mapping):
        raise TypeError("temporal_recipe must be a mapping")
    if type(scope_start_t_ns) is not int or type(scope_end_t_ns) is not int:
        raise TypeError("O2 scope bounds must be strict integers")
    start = max(scope_start_t_ns, phase.start_t_ns)
    end = min(scope_end_t_ns, phase.end_t_ns)
    if start < 0 or end <= start:
        raise ValueError("O2 scope must overlap the semantic phase")

    timestamp_column = _recipe_string(temporal_recipe, "timestamp_column")
    in_session_column = _recipe_string(temporal_recipe, "in_session_column")
    stable_keys = _recipe_strings(temporal_recipe, "stable_keys")
    gap_threshold_raw = temporal_recipe.get("reference_gap_threshold_ns")
    if type(gap_threshold_raw) is not int or gap_threshold_raw < 0:
        raise ValueError("temporal_recipe.reference_gap_threshold_ns must be non-negative")
    gap_threshold = gap_threshold_raw
    bindings = _axis_bindings(temporal_recipe)

    transform, transform_reason = _coordinate_transform(
        temporal_recipe,
        source_frame_id=reference_contract.coordinate_frame_id,
        target_frame_id=x_contract.coordinate_frame_id,
    )
    factors = _field_factors(bindings, x_contract, reference_contract)
    if transform is None or factors is None:
        return _noncomputed(
            status="not_computable",
            reason=transform_reason or "position_contract_incompatible",
            candidate_count=0,
            source_bounds=None,
            reference_bounds=None,
        )
    x_factors, reference_factors = factors

    structural_x = (timestamp_column, in_session_column, *stable_keys)
    if any(field not in x_table.columns for field in structural_x) or any(
        binding.x_field not in x_table.columns for binding in bindings
    ):
        return _noncomputed(
            status="not_computable",
            reason="position_contract_incompatible",
            candidate_count=0,
            source_bounds=None,
            reference_bounds=None,
        )
    terminal = phase.include_session_terminal_point and end == phase.end_t_ns
    time_expression = (pl.col(timestamp_column) >= start) & (
        (pl.col(timestamp_column) <= end) if terminal else (pl.col(timestamp_column) < end)
    )
    active_x = x_table.filter(time_expression & pl.col(in_session_column)).sort(
        [timestamp_column, *stable_keys], maintain_order=True
    )
    if active_x.is_empty():
        return _noncomputed(
            status="missing_input",
            reason="no_temporal_support",
            candidate_count=0,
            source_bounds=None,
            reference_bounds=None,
        )
    x_times = tuple(_strict_row_id(value, "X t_ns") for value in active_x[timestamp_column])
    source_bounds = (min(x_times), max(x_times))

    points = _reference_points(
        reference_table,
        reference_contract,
        bindings,
        reference_factors,
        transform,
    )
    reference_bounds = None if not points else (points[0].t_ns, points[-1].t_ns)
    if not points:
        return _noncomputed(
            status="not_computable",
            reason="no_reference_overlap",
            candidate_count=active_x.height,
            source_bounds=source_bounds,
            reference_bounds=None,
        )
    reference_times = tuple(point.t_ns for point in points)

    trace_rows: list[O2TrackingErrorRow] = []
    for row in active_x.iter_rows(named=True):
        t_ns = _strict_row_id(row[timestamp_column], "X t_ns")
        joined = _interpolated_reference(t_ns, points, reference_times, gap_threshold)
        if joined is None:
            continue
        reference_position_m, reference_row_id = joined
        source_row_id = _strict_row_id(row[stable_keys[0]], "X stable row ID")
        actual_position_m = cast(
            tuple[float, float, float],
            tuple(
                _finite_number(row[binding.x_field], binding.x_field) * x_factors[index]
                for index, binding in enumerate(bindings)
            ),
        )
        errors_ft = cast(
            tuple[float, float, float],
            tuple(
                (actual_position_m[index] - reference_position_m[index]) / _METERS_PER_FOOT
                for index in range(3)
            ),
        )
        trace_rows.append(
            O2TrackingErrorRow(
                phase_id=phase.phase_id,
                t_ns=t_ns,
                source_row_id=source_row_id,
                reference_row_id=reference_row_id,
                error_x_ft=errors_ft[0],
                error_y_ft=errors_ft[1],
                error_z_ft=errors_ft[2],
                error_norm_ft=math.hypot(*errors_ft),
            )
        )
    rows = tuple(sorted(trace_rows, key=lambda row: (row.t_ns, row.source_row_id)))
    if not rows:
        return _noncomputed(
            status="not_computable",
            reason="no_reference_overlap",
            candidate_count=active_x.height,
            source_bounds=source_bounds,
            reference_bounds=reference_bounds,
        )
    peak_excursion = max(row.error_norm_ft for row in rows)
    peak = min(
        (row for row in rows if row.error_norm_ft == peak_excursion),
        key=lambda row: (row.t_ns, row.source_row_id),
    )
    return O2KernelResult(
        status="computed",
        reason=None,
        peak_excursion_ft=peak_excursion,
        peak_t_ns=peak.t_ns,
        peak_source_row_id=peak.source_row_id,
        candidate_point_count=active_x.height,
        joined_point_count=len(rows),
        source_start_t_ns=source_bounds[0],
        source_end_t_ns=source_bounds[1],
        reference_start_t_ns=reference_bounds[0] if reference_bounds is not None else None,
        reference_end_t_ns=reference_bounds[1] if reference_bounds is not None else None,
        trace_rows=rows,
    )


__all__ = [
    "O2KernelResult",
    "O2KernelStatus",
    "O2TrackingErrorRow",
    "compute_o2_kernel",
]
