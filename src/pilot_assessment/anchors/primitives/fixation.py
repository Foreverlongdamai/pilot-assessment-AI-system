"""Deterministic raw-gaze I-VT fixation extraction for H2."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from pilot_assessment.contracts.anchor_execution import (
    AoiDefinition,
    PreprocessingProviderDefinition,
    ResolvedPreprocessingRecipe,
)

_MAX_CONTIGUOUS_GAZE_GAP_NS = 50_000_000
_UINT64_MAX = 2**64 - 1
_GAZE_COLUMNS = {
    "gaze_sample_id",
    "t_ns",
    "in_session",
    "ray_x",
    "ray_y",
    "ray_z",
    "binocular_valid",
    "blink",
    "confidence",
    "assigned_aoi_id",
}
_OUTPUT_SCHEMA = {
    "fixation_id": pl.String,
    "start_t_ns": pl.Int64,
    "end_t_ns": pl.Int64,
    "aoi_id": pl.String,
    "role_id": pl.String,
}


@dataclass(frozen=True, slots=True)
class _Parameters:
    angular_velocity_threshold_deg_s: float
    minimum_fixation_duration_ns: int


@dataclass(frozen=True, slots=True)
class _GazeSample:
    gaze_sample_id: int
    t_ns: int
    ray: tuple[float, float, float]
    aoi_id: str


def _strict_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return normalized


def _strict_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a strict non-negative integer")
    return value


def _parameters(values: Mapping[str, JsonValue]) -> _Parameters:
    expected = {
        "angular_velocity_threshold_deg_s",
        "minimum_fixation_duration_ns",
    }
    if not isinstance(values, Mapping) or set(values) != expected:
        raise ValueError("fixation-intervals-v1 requires the exact two-key parameter profile")
    return _Parameters(
        angular_velocity_threshold_deg_s=_strict_float(
            values["angular_velocity_threshold_deg_s"],
            "angular_velocity_threshold_deg_s",
        ),
        minimum_fixation_duration_ns=_strict_int(
            values["minimum_fixation_duration_ns"],
            "minimum_fixation_duration_ns",
        ),
    )


def _typed_aois(value: object) -> tuple[AoiDefinition, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.aois must be an ordered array")
    aois = tuple(AoiDefinition.model_validate(item) for item in value)
    ids = tuple(item.aoi_id for item in aois)
    if len(ids) != len(set(ids)):
        raise ValueError("semantic AOI IDs must be unique")
    return aois


def _empty_output() -> pl.DataFrame:
    return pl.DataFrame(
        {name: pl.Series(name, [], dtype=dtype) for name, dtype in _OUTPUT_SCHEMA.items()}
    )


def _normalize(values: tuple[object, object, object]) -> tuple[float, float, float] | None:
    if any(
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        return None
    first, second, third = values
    assert isinstance(first, (int, float)) and not isinstance(first, bool)
    assert isinstance(second, (int, float)) and not isinstance(second, bool)
    assert isinstance(third, (int, float)) and not isinstance(third, bool)
    vector = (float(first), float(second), float(third))
    norm = math.sqrt(math.fsum(component * component for component in vector))
    if not math.isfinite(norm) or norm <= 0.0:
        return None
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _angular_velocity_deg_s(previous: _GazeSample, current: _GazeSample) -> float:
    delta_ns = current.t_ns - previous.t_ns
    if delta_ns <= 0:
        raise ValueError("I-VT samples must have strictly increasing timestamps")
    dot = math.fsum(left * right for left, right in zip(previous.ray, current.ray, strict=True))
    angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    return angle_deg / (delta_ns / 1_000_000_000.0)


def _sample(
    row: Mapping[str, object],
    aoi_roles: Mapping[str, str],
) -> _GazeSample | None:
    gaze_sample_id = row["gaze_sample_id"]
    t_ns = row["t_ns"]
    if type(gaze_sample_id) is not int or gaze_sample_id < 0 or gaze_sample_id > _UINT64_MAX:
        raise ValueError("G.gaze_samples.gaze_sample_id has an invalid integer domain")
    if type(t_ns) is not int or t_ns < 0:
        raise ValueError("G.gaze_samples.t_ns has an invalid integer domain")
    if row["in_session"] is not True:
        return None
    if row["binocular_valid"] is not True or row["blink"] is not False:
        return None
    ray = _normalize((row["ray_x"], row["ray_y"], row["ray_z"]))
    aoi_id = row["assigned_aoi_id"]
    if ray is None or not isinstance(aoi_id, str) or aoi_id not in aoi_roles:
        return None
    return _GazeSample(gaze_sample_id, t_ns, ray, aoi_id)


def _dominant_aoi(samples: Sequence[_GazeSample]) -> str:
    support: dict[str, int] = {}
    for current, following in zip(samples, samples[1:], strict=False):
        support[current.aoi_id] = support.get(current.aoi_id, 0) + (following.t_ns - current.t_ns)
    if not support:
        return samples[0].aoi_id
    return min(support, key=lambda aoi_id: (-support[aoi_id], aoi_id))


def _append_fixation(
    rows: list[dict[str, object]],
    run: Sequence[_GazeSample],
    parameters: _Parameters,
    aoi_roles: Mapping[str, str],
) -> None:
    if len(run) < 2:
        return
    start_t_ns = run[0].t_ns
    end_t_ns = run[-1].t_ns
    if end_t_ns - start_t_ns < parameters.minimum_fixation_duration_ns:
        return
    aoi_id = _dominant_aoi(run)
    rows.append(
        {
            "fixation_id": (
                f"fixation-{len(rows):08d}-{run[0].gaze_sample_id}-{run[-1].gaze_sample_id}"
            ),
            "start_t_ns": start_t_ns,
            "end_t_ns": end_t_ns,
            "aoi_id": aoi_id,
            "role_id": aoi_roles[aoi_id],
        }
    )


def compute_fixation_intervals(
    context: AnchorPluginContext,
    parameters: Mapping[str, JsonValue],
    *,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
) -> pl.DataFrame:
    """Recompute deterministic I-VT fixations from authoritative raw aligned gaze."""

    if type(scope_start_t_ns) is not int or type(scope_end_t_ns) is not int:
        raise TypeError("fixation scope bounds must be strict integers")
    if scope_start_t_ns < 0 or scope_end_t_ns <= scope_start_t_ns:
        raise ValueError("fixation scope must be a positive non-negative span")
    parsed = _parameters(parameters)
    aois = _typed_aois(context.semantic_scope.values.get("semantic.aois"))
    aoi_roles = {item.aoi_id: item.role for item in aois}
    gaze_view = context.streams.get("G")
    table = None if gaze_view is None else gaze_view.tables.get("gaze_samples")
    if table is None:
        return _empty_output()
    if not set(table.columns) >= _GAZE_COLUMNS:
        raise ValueError("G.gaze_samples does not expose the frozen raw I-VT interface")
    if (
        table.schema["gaze_sample_id"] != pl.UInt64
        or table.schema["t_ns"] != pl.Int64
        or table.schema["in_session"] != pl.Boolean
        or table["gaze_sample_id"].null_count()
        or table["t_ns"].null_count()
        or table["in_session"].null_count()
        or table.select("gaze_sample_id").is_duplicated().any()
    ):
        raise ValueError("G.gaze_samples has an invalid aligned identity/time schema")

    selected = table.filter(
        (pl.col("t_ns") >= scope_start_t_ns) & (pl.col("t_ns") <= scope_end_t_ns)
    ).sort(["t_ns", "gaze_sample_id"], maintain_order=True)
    timeline: list[_GazeSample | None] = []
    previous_t_ns: int | None = None
    for row in selected.iter_rows(named=True):
        t_ns = row["t_ns"]
        assert type(t_ns) is int
        if previous_t_ns == t_ns:
            continue
        previous_t_ns = t_ns
        timeline.append(_sample(row, aoi_roles))

    rows: list[dict[str, object]] = []
    run: list[_GazeSample] = []
    previous: _GazeSample | None = None
    for current in timeline:
        if current is None:
            _append_fixation(rows, run, parsed, aoi_roles)
            run = []
            previous = None
            continue
        if previous is None:
            previous = current
            continue
        delta_ns = current.t_ns - previous.t_ns
        velocity = _angular_velocity_deg_s(previous, current)
        within_velocity = velocity <= parsed.angular_velocity_threshold_deg_s or math.isclose(
            velocity,
            parsed.angular_velocity_threshold_deg_s,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
        continuous = delta_ns <= _MAX_CONTIGUOUS_GAZE_GAP_NS and within_velocity
        if continuous:
            if not run:
                run.append(previous)
            run.append(current)
        else:
            _append_fixation(rows, run, parsed, aoi_roles)
            run = []
        previous = current
    _append_fixation(rows, run, parsed, aoi_roles)

    if not rows:
        return _empty_output()
    return pl.DataFrame(rows, schema=_OUTPUT_SCHEMA).sort(
        ["start_t_ns", "end_t_ns", "fixation_id"], maintain_order=True
    )


def _provider_definition() -> PreprocessingProviderDefinition:
    identity = next(
        item
        for item in REFERENCE_PREPROCESSING_IDENTITIES
        if item["provider_id"] == "fixation-intervals-v1"
    )
    return PreprocessingProviderDefinition(
        provider_id=cast(str, identity["provider_id"]),
        provider_version=cast(str, identity["provider_version"]),
        api_version="0.1.0",
        required_streams=("G",),
        required_context_paths=(),
        required_semantic_paths=("semantic.aois",),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id=cast(str, identity["parameter_schema_id"]),
        output_schema_id=cast(str, identity["output_schema_id"]),
        output_schema_descriptor=cast(dict[str, JsonValue], identity["output_schema_descriptor"]),
        artifact_kind=cast(str, identity["artifact_kind"]),
        output_payload_kind="table",
    )


class FixationIntervalsProvider:
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
            raise ValueError("fixation-intervals-v1 has no provider dependencies")
        if recipe.provider_id != self._definition.provider_id:
            raise ValueError("fixation provider recipe identity mismatch")
        if scope.kind != "session":
            raise ValueError("fixation-intervals-v1 v0.1 requires one session scope")
        frame = compute_fixation_intervals(
            context,
            recipe.parameters,
            scope_start_t_ns=scope.start_t_ns,
            scope_end_t_ns=scope.end_t_ns,
        )
        return TabularArtifactPayload(
            schema_id=recipe.output_schema_id,
            schema_descriptor=recipe.output_schema_descriptor,
            frame=frame,
            order_keys=("start_t_ns", "end_t_ns", "fixation_id"),
            artifact_kind=recipe.artifact_kind,
            grid_hash=None,
            start_t_ns=scope.start_t_ns,
            end_t_ns=scope.end_t_ns,
        )


def create_provider() -> FixationIntervalsProvider:
    return FixationIntervalsProvider()


__all__ = [
    "FixationIntervalsProvider",
    "compute_fixation_intervals",
    "create_provider",
]
