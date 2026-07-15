"""Deterministic first-person gaze-to-AOI interval association for H1/H3."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import REFERENCE_PREPROCESSING_IDENTITIES
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AoiDefinition,
    AoiGeometryKind,
    PreprocessingProviderDefinition,
    ResolvedInputTableContract,
    ResolvedPreprocessingRecipe,
    SemanticPhase,
)

_FRAME_COLUMNS = {
    "frame_id",
    "t_ns",
    "in_session",
    "width",
    "height",
    "head_x_m",
    "head_y_m",
    "head_z_m",
    "head_qx",
    "head_qy",
    "head_qz",
    "head_qw",
    "horizontal_fov_deg",
    "vertical_fov_deg",
    "frame_valid",
}
_GAZE_COLUMNS = {
    "gaze_sample_id",
    "t_ns",
    "in_session",
    "scene_frame_id",
    "viewport_x_norm",
    "viewport_y_norm",
    "origin_x_m",
    "origin_y_m",
    "origin_z_m",
    "ray_x",
    "ray_y",
    "ray_z",
    "binocular_valid",
    "confidence",
    "blink",
    "assigned_aoi_id",
    "assignment_confidence",
}
_INT64_MAX = 2**63 - 1


@dataclass(frozen=True, slots=True)
class _FramePresentation:
    frame_id: int
    start_t_ns: int
    end_t_ns: int
    row: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _FrameTimeline:
    presentations: tuple[_FramePresentation, ...]
    starts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _GazeGeometry:
    viewport: tuple[float, float] | None
    world_origin: tuple[float, float, float] | None
    world_ray: tuple[float, float, float] | None
    camera_ray: tuple[float, float, float] | None


_DynamicGeometryKey = tuple[str, str, str, int, str]
_DynamicGeometryIndex = Mapping[_DynamicGeometryKey, Mapping[str, object]]


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered array")
    return value


def _typed_aois(value: object) -> tuple[AoiDefinition, ...]:
    return tuple(AoiDefinition.model_validate(item) for item in _sequence(value, "semantic.aois"))


def _typed_phases(value: object) -> tuple[SemanticPhase, ...]:
    return tuple(SemanticPhase.model_validate(item) for item in _sequence(value, "semantic.phases"))


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _finite_tuple(values: Sequence[object], length: int) -> tuple[float, ...] | None:
    if len(values) != length:
        return None
    parsed = tuple(_finite(value) for value in values)
    if any(value is None for value in parsed):
        return None
    return cast(tuple[float, ...], parsed)


def _positive_median_gap_threshold(times: Sequence[int]) -> int | None:
    deltas = sorted(
        current - previous for previous, current in pairwise(sorted(times)) if current > previous
    )
    if not deltas:
        return None
    middle = len(deltas) // 2
    median = (
        Decimal(deltas[middle])
        if len(deltas) % 2
        else (Decimal(deltas[middle - 1]) + Decimal(deltas[middle])) / Decimal(2)
    )
    return int((median * Decimal("5.0")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _require_temporal_table(
    frame: pl.DataFrame, *, id_column: str, required_columns: set[str], label: str
) -> None:
    if not isinstance(frame, pl.DataFrame) or not required_columns <= set(frame.columns):
        raise ValueError(f"{label} does not expose the frozen aligned interface")
    expected = {
        id_column: pl.UInt64,
        "t_ns": pl.Int64,
        "in_session": pl.Boolean,
    }
    for column, dtype in expected.items():
        if frame.schema[column] != dtype or frame[column].null_count():
            raise ValueError(f"{label}.{column} has an invalid aligned schema")
    if frame.select(id_column).is_duplicated().any():
        raise ValueError(f"{label}.{id_column} must identify unique rows")


def _frame_presentations(frame: pl.DataFrame, end_t_ns: int) -> _FrameTimeline:
    _require_temporal_table(
        frame,
        id_column="frame_id",
        required_columns=_FRAME_COLUMNS,
        label="I.frame_index",
    )
    active_times = cast(list[int], frame.filter(pl.col("in_session"))["t_ns"].to_list())
    support = reconstruct_point_support(
        frame,
        timestamp_column="t_ns",
        stable_keys=("frame_id",),
        in_session_column="in_session",
        gap_threshold_ns=_positive_median_gap_threshold(active_times),
        semantic_end_t_ns=end_t_ns,
    )
    rows = tuple(frame.iter_rows(named=True))
    presentations: list[_FramePresentation] = []
    for interval in support.intervals:
        if interval.end_t_ns <= interval.start_t_ns:
            continue
        row = rows[interval.source_row_index]
        frame_id = row["frame_id"]
        if type(frame_id) is not int or frame_id < 0 or frame_id > _INT64_MAX:
            raise ValueError("I.frame_index.frame_id exceeds the supported integer domain")
        presentations.append(
            _FramePresentation(
                frame_id=frame_id,
                start_t_ns=interval.start_t_ns,
                end_t_ns=interval.end_t_ns,
                row=row,
            )
        )
    frozen = tuple(presentations)
    return _FrameTimeline(
        presentations=frozen,
        starts=tuple(item.start_t_ns for item in frozen),
    )


def _presentation_at(timeline: _FrameTimeline, t_ns: int) -> _FramePresentation | None:
    if not timeline.presentations:
        return None
    index = bisect_right(timeline.starts, t_ns) - 1
    if index < 0:
        return None
    candidate = timeline.presentations[index]
    return candidate if candidate.start_t_ns <= t_ns < candidate.end_t_ns else None


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    norm = math.sqrt(math.fsum(component * component for component in vector))
    if not math.isfinite(norm) or norm <= 0.0:
        return None
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _camera_ray(
    world_ray: tuple[float, float, float], frame: Mapping[str, object]
) -> tuple[float, float, float] | None:
    quaternion = _finite_tuple(
        (
            frame.get("head_qx"),
            frame.get("head_qy"),
            frame.get("head_qz"),
            frame.get("head_qw"),
        ),
        4,
    )
    if quaternion is None:
        return None
    qx, qy, qz, qw = quaternion
    q_norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if not math.isfinite(q_norm) or q_norm <= 0.0:
        return None
    qx, qy, qz, qw = (value / q_norm for value in (qx, qy, qz, qw))

    # The frame quaternion rotates camera-local vectors into world coordinates.
    # Multiplication by its conjugate therefore maps the measured world ray back
    # into the current first-person camera frame.
    vx, vy, vz = world_ray
    tx = 2.0 * (-qy * vz + qz * vy)
    ty = 2.0 * (-qz * vx + qx * vz)
    tz = 2.0 * (-qx * vy + qy * vx)
    local = (
        vx + qw * tx + (-qy * tz + qz * ty),
        vy + qw * ty + (-qz * tx + qx * tz),
        vz + qw * tz + (-qx * ty + qy * tx),
    )
    return _normalize(local)


def _project_ray(
    camera_ray: tuple[float, float, float] | None, frame: Mapping[str, object]
) -> tuple[float, float] | None:
    if camera_ray is None or camera_ray[2] <= 0.0:
        return None
    horizontal = _finite(frame.get("horizontal_fov_deg"))
    vertical = _finite(frame.get("vertical_fov_deg"))
    if (
        horizontal is None
        or vertical is None
        or not 0.0 < horizontal < 180.0
        or not 0.0 < vertical < 180.0
    ):
        return None
    tan_h = math.tan(math.radians(horizontal) / 2.0)
    tan_v = math.tan(math.radians(vertical) / 2.0)
    if tan_h <= 0.0 or tan_v <= 0.0:
        return None
    x = 0.5 + camera_ray[0] / (2.0 * camera_ray[2] * tan_h)
    y = 0.5 - camera_ray[1] / (2.0 * camera_ray[2] * tan_v)
    if not math.isfinite(x) or not math.isfinite(y) or not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (x, y)


def _gaze_geometry(gaze: Mapping[str, object], frame: Mapping[str, object]) -> _GazeGeometry:
    world_ray_values = _finite_tuple((gaze.get("ray_x"), gaze.get("ray_y"), gaze.get("ray_z")), 3)
    world_ray = (
        None
        if world_ray_values is None
        else _normalize(cast(tuple[float, float, float], world_ray_values))
    )
    origin_values = _finite_tuple(
        (gaze.get("origin_x_m"), gaze.get("origin_y_m"), gaze.get("origin_z_m")), 3
    )
    origin = cast(tuple[float, float, float] | None, origin_values)
    camera_ray = None if world_ray is None else _camera_ray(world_ray, frame)
    viewport_values = _finite_tuple((gaze.get("viewport_x_norm"), gaze.get("viewport_y_norm")), 2)
    viewport = cast(tuple[float, float] | None, viewport_values)
    if viewport is not None and not all(0.0 <= value <= 1.0 for value in viewport):
        viewport = None
    if viewport is None:
        viewport = _project_ray(camera_ray, frame)
    return _GazeGeometry(
        viewport=viewport,
        world_origin=origin,
        world_ray=world_ray,
        camera_ray=camera_ray,
    )


def _point_for_unit(
    viewport: tuple[float, float] | None,
    unit: str,
    frame: Mapping[str, object],
) -> tuple[float, float] | None:
    if viewport is None:
        return None
    if unit in {"normalized", "ratio", "dimensionless"}:
        return viewport
    if unit in {"px", "pixel"}:
        width = _finite(frame.get("width"))
        height = _finite(frame.get("height"))
        if width is None or height is None or width <= 0.0 or height <= 0.0:
            return None
        return (viewport[0] * width, viewport[1] * height)
    return None


def _point_on_segment(
    point: tuple[float, float], left: tuple[float, float], right: tuple[float, float]
) -> bool:
    cross = (point[1] - left[1]) * (right[0] - left[0]) - (point[0] - left[0]) * (
        right[1] - left[1]
    )
    tolerance = 1e-12 * max(1.0, *(abs(value) for value in (*point, *left, *right)))
    if abs(cross) > tolerance:
        return False
    return (
        min(left[0], right[0]) - tolerance <= point[0] <= max(left[0], right[0]) + tolerance
        and min(left[1], right[1]) - tolerance <= point[1] <= max(left[1], right[1]) + tolerance
    )


def _inside_polygon(point: tuple[float, float], vertices: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    for left, right in zip(vertices, (*vertices[1:], vertices[0]), strict=True):
        if _point_on_segment(point, left, right):
            return True
        if (left[1] > point[1]) != (right[1] > point[1]):
            crossing_x = left[0] + (point[1] - left[1]) * (right[0] - left[0]) / (
                right[1] - left[1]
            )
            if point[0] < crossing_x:
                inside = not inside
    return inside


def _ray_box_depth(
    origin: tuple[float, float, float] | None,
    ray: tuple[float, float, float] | None,
    lower: tuple[float, float, float],
    upper: tuple[float, float, float],
) -> float | None:
    if (
        origin is None
        or ray is None
        or any(high <= low for low, high in zip(lower, upper, strict=True))
    ):
        return None
    entry = -math.inf
    exit_ = math.inf
    for position, direction, low, high in zip(origin, ray, lower, upper, strict=True):
        if abs(direction) <= 1e-15:
            if position < low or position > high:
                return None
            continue
        first = (low - position) / direction
        second = (high - position) / direction
        near, far = min(first, second), max(first, second)
        entry = max(entry, near)
        exit_ = min(exit_, far)
        if exit_ < entry:
            return None
    if entry > 0.0:
        return entry
    return exit_ if exit_ > 0.0 else None


def _dynamic_contract(
    context: AnchorPluginContext, aoi: AoiDefinition
) -> ResolvedInputTableContract:
    source = aoi.dynamic_source
    assert source is not None
    matches = tuple(
        contract
        for contract in context.input_table_contracts
        if contract.modality.value == "I" and contract.table_role == source.table_role
    )
    if len(matches) != 1:
        raise ValueError(f"dynamic AOI {aoi.aoi_id} requires one exact I table contract")
    contract = matches[0]
    fields = {field.field_name: field for field in contract.fields}
    if (
        contract.table_aligned_schema_id != source.aligned_schema_id
        or contract.coordinate_frame_id != source.coordinate_frame_id
        or any(field not in fields for field in (source.frame_id_field, source.aoi_id_field))
        or any(
            field not in fields or fields[field].unit != source.unit
            for field in source.geometry_field_ids
        )
    ):
        raise ValueError(f"dynamic AOI {aoi.aoi_id} does not match its resolved contract")
    return contract


def _dynamic_geometry_index(
    context: AnchorPluginContext,
    aois: tuple[AoiDefinition, ...],
) -> dict[_DynamicGeometryKey, Mapping[str, object]]:
    groups: dict[tuple[str, str, str], list[AoiDefinition]] = {}
    for aoi in aois:
        if aoi.geometry_kind not in {AoiGeometryKind.DYNAMIC_2D, AoiGeometryKind.DYNAMIC_3D}:
            continue
        source = aoi.dynamic_source
        assert source is not None
        _dynamic_contract(context, aoi)
        signature = (source.table_role, source.frame_id_field, source.aoi_id_field)
        groups.setdefault(signature, []).append(aoi)

    scene = context.streams.get("I")
    index: dict[_DynamicGeometryKey, Mapping[str, object]] = {}
    for (table_role, frame_field, aoi_field), definitions in groups.items():
        table = None if scene is None else scene.tables.get(table_role)
        if table is None:
            raise ValueError(f"dynamic AOI table {table_role} is absent")
        geometry_fields: set[str] = set()
        for definition in definitions:
            source = definition.dynamic_source
            assert source is not None
            geometry_fields.update(source.geometry_field_ids)
        required = {frame_field, aoi_field, *geometry_fields}
        if not required <= set(table.columns):
            raise ValueError(f"dynamic AOI table {table_role} is incomplete")
        aoi_ids = {definition.aoi_id for definition in definitions}
        selected = table.filter(pl.col(aoi_field).is_in(sorted(aoi_ids)))
        for row in selected.iter_rows(named=True):
            frame_id = row[frame_field]
            aoi_id = row[aoi_field]
            if type(frame_id) is not int or frame_id < 0 or frame_id > _INT64_MAX:
                raise ValueError(f"dynamic AOI table {table_role} has an invalid frame ID")
            if not isinstance(aoi_id, str) or aoi_id not in aoi_ids:
                raise ValueError(f"dynamic AOI table {table_role} has an invalid AOI ID")
            key = (table_role, frame_field, aoi_field, frame_id, aoi_id)
            if key in index:
                raise ValueError(
                    f"dynamic AOI {aoi_id} has duplicate geometry for frame {frame_id}"
                )
            index[key] = row
    return index


def _dynamic_row(
    index: _DynamicGeometryIndex,
    aoi: AoiDefinition,
    frame_id: int,
) -> Mapping[str, object] | None:
    source = aoi.dynamic_source
    assert source is not None
    row = index.get(
        (
            source.table_role,
            source.frame_id_field,
            source.aoi_id_field,
            frame_id,
            aoi.aoi_id,
        )
    )
    if row is None:
        return None
    if "visible" in row and row["visible"] is False:
        return None
    return row


def _dynamic_2d_bounds(
    row: Mapping[str, object], fields: tuple[str, ...]
) -> tuple[float, float, float, float] | None:
    if len(fields) != 4:
        return None
    values = _finite_tuple(tuple(row.get(field) for field in fields), 4)
    if values is None:
        return None
    first, second, third, fourth = values
    width_height = any(token in fields[2].lower() for token in ("width", "_w", "w_")) or any(
        token in fields[3].lower() for token in ("height", "_h", "h_")
    )
    return (
        (first, second, first + third, second + fourth)
        if width_height
        else (first, second, third, fourth)
    )


def _dynamic_3d_bounds(
    row: Mapping[str, object], fields: tuple[str, ...]
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if len(fields) != 6:
        return None
    values = _finite_tuple(tuple(row.get(field) for field in fields), 6)
    if values is None:
        return None
    return (
        cast(tuple[float, float, float], values[:3]),
        cast(tuple[float, float, float], values[3:]),
    )


def _hit_2d(
    dynamic_geometry: _DynamicGeometryIndex,
    aoi: AoiDefinition,
    geometry: _GazeGeometry,
    presentation: _FramePresentation,
) -> bool:
    if aoi.geometry_kind is AoiGeometryKind.POLYGON_2D:
        first = aoi.vertices[0]
        point = _point_for_unit(geometry.viewport, first.unit, presentation.row)
        vertices = tuple(cast(tuple[float, float], vertex.values) for vertex in aoi.vertices)
        return point is not None and _inside_polygon(point, vertices)
    if aoi.geometry_kind is not AoiGeometryKind.DYNAMIC_2D:
        return False
    source = aoi.dynamic_source
    assert source is not None
    point = _point_for_unit(geometry.viewport, source.unit, presentation.row)
    row = _dynamic_row(dynamic_geometry, aoi, presentation.frame_id)
    bounds = None if row is None else _dynamic_2d_bounds(row, source.geometry_field_ids)
    return (
        point is not None
        and bounds is not None
        and bounds[0] <= point[0] <= bounds[2]
        and bounds[1] <= point[1] <= bounds[3]
    )


def _hit_3d_depth(
    dynamic_geometry: _DynamicGeometryIndex,
    aoi: AoiDefinition,
    geometry: _GazeGeometry,
    presentation: _FramePresentation,
) -> float | None:
    if aoi.geometry_kind is AoiGeometryKind.BOX_3D:
        lower = cast(tuple[float, float, float], aoi.vertices[0].values)
        upper = cast(tuple[float, float, float], aoi.vertices[1].values)
    elif aoi.geometry_kind is AoiGeometryKind.DYNAMIC_3D:
        source = aoi.dynamic_source
        assert source is not None
        row = _dynamic_row(dynamic_geometry, aoi, presentation.frame_id)
        bounds = None if row is None else _dynamic_3d_bounds(row, source.geometry_field_ids)
        if bounds is None:
            return None
        lower, upper = bounds
    else:
        return None
    return _ray_box_depth(geometry.world_origin, geometry.world_ray, lower, upper)


def _selected_aoi(
    dynamic_geometry: _DynamicGeometryIndex,
    taxonomy: tuple[AoiDefinition, ...],
    gaze: Mapping[str, object],
    presentation: _FramePresentation | None,
) -> tuple[AoiDefinition, bool]:
    catch_all = next(item for item in taxonomy if item.geometry_kind is AoiGeometryKind.CATCH_ALL)
    if presentation is None:
        return catch_all, False
    declared_frame = gaze.get("scene_frame_id")
    frame_valid = presentation.row.get("frame_valid") is True
    tracking_valid = gaze.get("binocular_valid") is True and gaze.get("blink") is False
    if declared_frame != presentation.frame_id or not frame_valid or not tracking_valid:
        return catch_all, False

    geometry = _gaze_geometry(gaze, presentation.row)
    if geometry.viewport is None and geometry.world_ray is None:
        return catch_all, False
    noncatch = tuple(
        item for item in taxonomy if item.geometry_kind is not AoiGeometryKind.CATCH_ALL
    )
    hits_3d = tuple(
        (depth, -item.priority, item.aoi_id, item)
        for item in noncatch
        if (depth := _hit_3d_depth(dynamic_geometry, item, geometry, presentation)) is not None
    )
    if hits_3d:
        return min(hits_3d, key=lambda item: (item[0], item[1], item[2]))[3], True
    hits_2d = tuple(
        item for item in noncatch if _hit_2d(dynamic_geometry, item, geometry, presentation)
    )
    if hits_2d:
        return min(hits_2d, key=lambda item: (-item.priority, item.aoi_id)), True
    if geometry.viewport is None:
        return catch_all, False
    return catch_all, True


def _taxonomies(aois: tuple[AoiDefinition, ...]) -> tuple[tuple[AoiDefinition, ...], ...]:
    grouped: dict[str, list[AoiDefinition]] = {}
    for aoi in sorted(aois, key=lambda item: item.aoi_id):
        grouped.setdefault(aoi.taxonomy_id, []).append(aoi)
    result: list[tuple[AoiDefinition, ...]] = []
    for taxonomy_id in sorted(grouped):
        taxonomy = tuple(grouped[taxonomy_id])
        if sum(item.geometry_kind is AoiGeometryKind.CATCH_ALL for item in taxonomy) != 1:
            raise ValueError(f"AOI taxonomy {taxonomy_id} requires exactly one catch-all")
        result.append(taxonomy)
    return tuple(result)


def _output_frame(rows: Sequence[Mapping[str, object]]) -> pl.DataFrame:
    schema = {
        "interval_id": pl.String,
        "start_t_ns": pl.Int64,
        "end_t_ns": pl.Int64,
        "gaze_source_row_id": pl.Int64,
        "frame_id": pl.String,
        "aoi_id": pl.String,
        "role_id": pl.String,
        "association_valid": pl.Boolean,
    }
    if not rows:
        return pl.DataFrame(
            {name: pl.Series(name, [], dtype=dtype) for name, dtype in schema.items()}
        )
    return pl.DataFrame(rows, schema=schema).sort(
        ["start_t_ns", "end_t_ns", "interval_id"], maintain_order=True
    )


def compute_gaze_aoi_intervals(
    context: AnchorPluginContext,
    *,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
) -> pl.DataFrame:
    """Associate every nonzero or diagnostic zero gaze support interval per AOI taxonomy."""

    if type(scope_start_t_ns) is not int or type(scope_end_t_ns) is not int:
        raise TypeError("gaze-AOI scope bounds must be strict integers")
    if scope_start_t_ns < 0 or scope_end_t_ns <= scope_start_t_ns:
        raise ValueError("gaze-AOI scope must be a positive non-negative span")
    aois = _typed_aois(context.semantic_scope.values.get("semantic.aois"))
    phases = _typed_phases(context.semantic_scope.values.get("semantic.phases"))
    taxonomies = _taxonomies(aois)
    scene = context.streams.get("I")
    gaze_view = context.streams.get("G")
    frame_table = None if scene is None else scene.tables.get("frame_index")
    gaze_table = None if gaze_view is None else gaze_view.tables.get("gaze_samples")
    if frame_table is None or gaze_table is None:
        return _output_frame(())
    _require_temporal_table(
        gaze_table,
        id_column="gaze_sample_id",
        required_columns=_GAZE_COLUMNS,
        label="G.gaze_samples",
    )
    frame_timeline = _frame_presentations(frame_table, scope_end_t_ns)
    dynamic_geometry = _dynamic_geometry_index(context, aois)
    active_gaze_times = cast(list[int], gaze_table.filter(pl.col("in_session"))["t_ns"].to_list())
    gap_threshold = _positive_median_gap_threshold(active_gaze_times)
    rows: list[dict[str, object]] = []
    interval_ordinal = 0
    for phase_index, phase in enumerate(phases):
        phase_start = max(scope_start_t_ns, phase.start_t_ns)
        phase_end = min(scope_end_t_ns, phase.end_t_ns)
        if phase_end <= phase_start:
            continue
        selected = gaze_table.filter(
            pl.col("in_session")
            & (pl.col("t_ns") >= phase_start)
            & (
                (pl.col("t_ns") < phase_end)
                | (phase.include_session_terminal_point & (pl.col("t_ns") == phase_end))
            )
        )
        if selected.is_empty():
            continue
        support = reconstruct_point_support(
            selected,
            timestamp_column="t_ns",
            stable_keys=("gaze_sample_id",),
            in_session_column="in_session",
            gap_threshold_ns=gap_threshold,
            semantic_end_t_ns=phase_end,
        )
        selected_rows = tuple(selected.iter_rows(named=True))
        for interval in support.intervals:
            gaze_row = selected_rows[interval.source_row_index]
            gaze_id = gaze_row["gaze_sample_id"]
            if type(gaze_id) is not int or gaze_id < 0 or gaze_id > _INT64_MAX:
                raise ValueError("G.gaze_samples.gaze_sample_id exceeds the i64 output domain")
            presentation = _presentation_at(frame_timeline, interval.start_t_ns)
            for taxonomy_index, taxonomy in enumerate(taxonomies):
                aoi, association_valid = _selected_aoi(
                    dynamic_geometry,
                    taxonomy,
                    gaze_row,
                    presentation,
                )
                rows.append(
                    {
                        "interval_id": (
                            f"gaze-{gaze_id}-{phase_index:04d}-{taxonomy_index:04d}-"
                            f"{interval_ordinal:08d}"
                        ),
                        "start_t_ns": interval.start_t_ns,
                        "end_t_ns": interval.end_t_ns,
                        "gaze_source_row_id": gaze_id,
                        "frame_id": (
                            "unassociated" if presentation is None else str(presentation.frame_id)
                        ),
                        "aoi_id": aoi.aoi_id,
                        "role_id": aoi.role,
                        "association_valid": association_valid,
                    }
                )
                interval_ordinal += 1
    return _output_frame(rows)


def _provider_definition() -> PreprocessingProviderDefinition:
    identity = next(
        item
        for item in REFERENCE_PREPROCESSING_IDENTITIES
        if item["provider_id"] == "gaze-aoi-intervals-v1"
    )
    return PreprocessingProviderDefinition(
        provider_id=cast(str, identity["provider_id"]),
        provider_version=cast(str, identity["provider_version"]),
        api_version="0.1.0",
        required_streams=("I", "G"),
        required_context_paths=(),
        required_semantic_paths=("semantic.aois", "semantic.phases"),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id=cast(str, identity["parameter_schema_id"]),
        output_schema_id=cast(str, identity["output_schema_id"]),
        output_schema_descriptor=cast(dict[str, JsonValue], identity["output_schema_descriptor"]),
        artifact_kind=cast(str, identity["artifact_kind"]),
        output_payload_kind="table",
    )


class GazeAoiIntervalsProvider:
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
            raise ValueError("gaze-aoi-intervals-v1 has no provider dependencies")
        if recipe.provider_id != self._definition.provider_id:
            raise ValueError("gaze-AOI provider recipe identity mismatch")
        if recipe.parameters:
            raise ValueError("gaze-aoi-intervals-v1 has an exact empty parameter profile")
        if scope.kind != "session":
            raise ValueError("gaze-aoi-intervals-v1 v0.1 requires one session scope")
        frame = compute_gaze_aoi_intervals(
            context,
            scope_start_t_ns=scope.start_t_ns,
            scope_end_t_ns=scope.end_t_ns,
        )
        return TabularArtifactPayload(
            schema_id=recipe.output_schema_id,
            schema_descriptor=recipe.output_schema_descriptor,
            frame=frame,
            order_keys=("start_t_ns", "end_t_ns", "interval_id"),
            artifact_kind=recipe.artifact_kind,
            grid_hash=None,
            start_t_ns=scope.start_t_ns,
            end_t_ns=scope.end_t_ns,
        )


def create_provider() -> GazeAoiIntervalsProvider:
    return GazeAoiIntervalsProvider()


__all__ = [
    "GazeAoiIntervalsProvider",
    "compute_gaze_aoi_intervals",
    "create_provider",
]
