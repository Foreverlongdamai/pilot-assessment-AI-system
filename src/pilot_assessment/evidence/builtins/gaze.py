"""Assigned-label and simplified geometry-hit gaze/AOI operators."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    OperatorDefinition,
    OperatorFamily,
    OperatorImplementationSource,
    OperatorPortDefinition,
    ParameterControlKind,
    ParameterUiDefinition,
    PortCardinality,
    PortType,
    TemporalSemantics,
    TraceCapability,
)
from pilot_assessment.evidence.builtins.temporal import (
    IntervalRecord,
    interval_records,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"
_NS_PER_SECOND = 1_000_000_000.0


class GazeOperatorError(ValueError):
    """Technical error in a gaze/AOI operator."""


def _strict_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise GazeOperatorError(f"{label} must be a non-negative strict integer")
    return value


def _required_text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise GazeOperatorError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _geometry_hits(value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise GazeOperatorError("geometry_hits must be an AOI-to-depth mapping")
    normalized: dict[str, float] = {}
    for raw_aoi_id, raw_depth in value.items():
        aoi_id = _required_text(raw_aoi_id, "geometry AOI ID")
        if isinstance(raw_depth, bool) or not isinstance(raw_depth, (int, float)):
            raise GazeOperatorError("geometry depth must be numeric")
        normalized[aoi_id] = float(raw_depth)
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class GazeFrame:
    frame_id: str
    start_t_ns: int
    end_t_ns: int
    assigned_aoi_id: str | None
    geometry_hits: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.frame_id:
            raise GazeOperatorError("gaze frame ID cannot be empty")
        if (
            type(self.start_t_ns) is not int
            or type(self.end_t_ns) is not int
            or self.start_t_ns < 0
            or self.end_t_ns <= self.start_t_ns
        ):
            raise GazeOperatorError("gaze frame bounds are invalid")
        if self.assigned_aoi_id is not None and (
            type(self.assigned_aoi_id) is not str or not self.assigned_aoi_id
        ):
            raise GazeOperatorError("assigned AOI ID must be a non-empty string or null")
        if not isinstance(self.geometry_hits, Mapping):
            raise GazeOperatorError("geometry hits must be an AOI-to-depth mapping")
        normalized: dict[str, float] = {}
        for aoi_id, depth in self.geometry_hits.items():
            numeric = float(depth)
            if not aoi_id or not math.isfinite(numeric) or numeric < 0.0:
                raise GazeOperatorError("geometry hits require finite non-negative depth")
            normalized[aoi_id] = numeric
        object.__setattr__(self, "geometry_hits", MappingProxyType(normalized))


def _port(
    port_id: str,
    *,
    value_type: str,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Gaze {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.INTERVAL,
            unit=None,
        ),
    )


def _definition(
    operator_id: str,
    *,
    inputs: tuple[OperatorPortDefinition, ...],
    output_type: str,
    parameter_schema: dict[str, JsonValue],
    parameter_ui: tuple[ParameterUiDefinition, ...],
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version=_VERSION,
        family=OperatorFamily.GAZE_VISION,
        name=operator_id.replace(".", " ").replace("-", " ").title(),
        description=f"Reusable editable {operator_id} operator.",
        pseudocode=None,
        input_ports=inputs,
        output_ports=(_port("value", value_type=output_type),),
        parameter_schema=parameter_schema,
        parameter_ui=parameter_ui,
        trace_capability=TraceCapability.FULL,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


def gaze_aoi_intervals_definition() -> OperatorDefinition:
    return _definition(
        "gaze.aoi-intervals",
        inputs=(_port("frames", value_type="gaze_frame_collection"),),
        output_type="interval_collection",
        parameter_schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["assigned_label", "geometry_association"],
                },
                "merge_adjacent": {"type": "boolean"},
            },
            "required": ["mode", "merge_adjacent"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/mode",
                label="AOI association mode",
                group_id="association",
                control=ParameterControlKind.SELECT,
                help_text="Use per-frame labels or nearest positive geometry hit.",
                unit=None,
            ),
        ),
    )


def aoi_filter_definition() -> OperatorDefinition:
    return _definition(
        "gaze.aoi-filter",
        inputs=(_port("intervals", value_type="interval_collection"),),
        output_type="interval_collection",
        parameter_schema={
            "type": "object",
            "properties": {
                "aoi_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
            },
            "required": ["aoi_ids"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/aoi_ids",
                label="Target AOIs",
                group_id="selection",
                control=ParameterControlKind.MULTI_SELECT,
                help_text="AOIs treated as matching evidence for this recipe.",
                unit=None,
            ),
        ),
    )


def first_match_latency_definition() -> OperatorDefinition:
    return _definition(
        "gaze.first-match-latency",
        inputs=(
            _port("windows", value_type="interval_collection"),
            _port("matches", value_type="interval_collection"),
        ),
        output_type="named_numbers",
        parameter_schema={
            "type": "object",
            "properties": {
                "no_match_policy": {
                    "type": "string",
                    "enum": ["window_end", "fixed"],
                },
                "fixed_latency_s": {"type": "number", "minimum": 0.0},
            },
            "required": ["no_match_policy", "fixed_latency_s"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/no_match_policy",
                label="No-match value",
                group_id="negative_evidence",
                control=ParameterControlKind.SELECT,
                help_text="No gaze match remains computed negative evidence.",
                unit=None,
            ),
            ParameterUiDefinition(
                parameter_path="/fixed_latency_s",
                label="Fixed no-match latency",
                group_id="negative_evidence",
                control=ParameterControlKind.NUMBER,
                help_text="Used only when no_match_policy is fixed.",
                unit="s",
            ),
        ),
    )


def dwell_ratio_definition() -> OperatorDefinition:
    return _definition(
        "gaze.dwell-ratio",
        inputs=(
            _port("windows", value_type="interval_collection"),
            _port("matches", value_type="interval_collection"),
        ),
        output_type="named_numbers",
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        parameter_ui=(),
    )


def _gaze_frames(value: object) -> tuple[GazeFrame, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise GazeOperatorError("gaze frames must be an ordered sequence")
    frames: list[GazeFrame] = []
    for item in value:
        if isinstance(item, GazeFrame):
            frames.append(item)
        elif isinstance(item, Mapping):
            mapping = cast(Mapping[str, object], item)
            frames.append(
                GazeFrame(
                    frame_id=_required_text(mapping.get("frame_id"), "frame_id"),
                    start_t_ns=_strict_nonnegative_int(
                        mapping.get("start_t_ns"),
                        "gaze start_t_ns",
                    ),
                    end_t_ns=_strict_nonnegative_int(
                        mapping.get("end_t_ns"),
                        "gaze end_t_ns",
                    ),
                    assigned_aoi_id=_optional_text(
                        mapping.get("assigned_aoi_id"),
                        "assigned_aoi_id",
                    ),
                    geometry_hits=_geometry_hits(mapping.get("geometry_hits", {})),
                )
            )
        else:
            raise GazeOperatorError("gaze frames contain an unsupported item")
    ordered = tuple(sorted(frames, key=lambda item: (item.start_t_ns, item.frame_id)))
    if len({item.frame_id for item in ordered}) != len(ordered):
        raise GazeOperatorError("gaze frame IDs must be unique")
    return ordered


def _associated_aoi(frame: GazeFrame, mode: object) -> str | None:
    if mode == "assigned_label":
        return frame.assigned_aoi_id
    if mode == "geometry_association":
        if not frame.geometry_hits:
            return None
        return min(frame.geometry_hits, key=lambda aoi_id: (frame.geometry_hits[aoi_id], aoi_id))
    raise GazeOperatorError("gaze AOI association mode is not supported")


class GazeAoiIntervalsOperator:
    operator_id = "gaze.aoi-intervals"
    implementation_version = _VERSION
    implementation_ref = "builtin.gaze.aoi-intervals"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        mode = parameters.get("mode")
        merge_adjacent = parameters.get("merge_adjacent")
        if type(merge_adjacent) is not bool:
            raise GazeOperatorError("merge_adjacent must be boolean")
        intervals: list[IntervalRecord] = []
        for frame in _gaze_frames(inputs.get("frames")):
            aoi_id = _associated_aoi(frame, mode)
            if aoi_id is None:
                continue
            if (
                merge_adjacent
                and intervals
                and intervals[-1].attributes.get("aoi_id") == aoi_id
                and intervals[-1].end_t_ns == frame.start_t_ns
            ):
                previous = intervals[-1]
                intervals[-1] = IntervalRecord(
                    interval_id=previous.interval_id,
                    start_t_ns=previous.start_t_ns,
                    end_t_ns=frame.end_t_ns,
                    attributes=previous.attributes,
                )
                continue
            intervals.append(
                IntervalRecord(
                    interval_id=f"gaze-{frame.frame_id}",
                    start_t_ns=frame.start_t_ns,
                    end_t_ns=frame.end_t_ns,
                    attributes={"aoi_id": aoi_id},
                )
            )
        return {"value": tuple(intervals)}


class AoiFilterOperator:
    operator_id = "gaze.aoi-filter"
    implementation_version = _VERSION
    implementation_ref = "builtin.gaze.aoi-filter"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        raw_ids = parameters.get("aoi_ids")
        if not isinstance(raw_ids, list):
            raise GazeOperatorError("aoi_ids must be an array")
        selected = frozenset(str(value) for value in raw_ids)
        return {
            "value": tuple(
                interval
                for interval in interval_records(inputs.get("intervals"))
                if interval.attributes.get("aoi_id") in selected
            )
        }


def _overlap_duration(window: IntervalRecord, matches: tuple[IntervalRecord, ...]) -> int:
    spans = sorted(
        (
            max(window.start_t_ns, match.start_t_ns),
            min(window.end_t_ns, match.end_t_ns),
        )
        for match in matches
        if min(window.end_t_ns, match.end_t_ns) > max(window.start_t_ns, match.start_t_ns)
    )
    total = 0
    current_start: int | None = None
    current_end: int | None = None
    for start, end in spans:
        if current_start is None:
            current_start, current_end = start, end
        elif current_end is not None and start <= current_end:
            current_end = max(current_end, end)
        else:
            assert current_end is not None
            total += current_end - current_start
            current_start, current_end = start, end
    if current_start is not None and current_end is not None:
        total += current_end - current_start
    return total


class FirstMatchLatencyOperator:
    operator_id = "gaze.first-match-latency"
    implementation_version = _VERSION
    implementation_ref = "builtin.gaze.first-match-latency"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        windows = interval_records(inputs.get("windows"))
        matches = interval_records(inputs.get("matches"))
        policy = parameters.get("no_match_policy")
        fixed = parameters.get("fixed_latency_s")
        if isinstance(fixed, bool) or not isinstance(fixed, (int, float)):
            raise GazeOperatorError("fixed_latency_s must be numeric")
        fixed_value = float(fixed)
        if not math.isfinite(fixed_value) or fixed_value < 0.0:
            raise GazeOperatorError("fixed_latency_s must be finite and non-negative")
        values: dict[str, float] = {}
        for window in windows:
            starts = [
                max(window.start_t_ns, match.start_t_ns)
                for match in matches
                if min(window.end_t_ns, match.end_t_ns) > max(window.start_t_ns, match.start_t_ns)
            ]
            if starts:
                value = (min(starts) - window.start_t_ns) / _NS_PER_SECOND
            elif policy == "window_end":
                value = (window.end_t_ns - window.start_t_ns) / _NS_PER_SECOND
            elif policy == "fixed":
                value = fixed_value
            else:
                raise GazeOperatorError("no-match policy is not supported")
            values[window.interval_id] = value
        return {"value": MappingProxyType(values)}


class DwellRatioOperator:
    operator_id = "gaze.dwell-ratio"
    implementation_version = _VERSION
    implementation_ref = "builtin.gaze.dwell-ratio"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        windows = interval_records(inputs.get("windows"))
        matches = interval_records(inputs.get("matches"))
        values = {
            window.interval_id: (
                _overlap_duration(window, matches) / (window.end_t_ns - window.start_t_ns)
            )
            for window in windows
        }
        return {"value": MappingProxyType(values)}


def register_gaze_operators(registry: OperatorRegistry) -> None:
    registry.register(gaze_aoi_intervals_definition(), GazeAoiIntervalsOperator())
    registry.register(aoi_filter_definition(), AoiFilterOperator())
    registry.register(first_match_latency_definition(), FirstMatchLatencyOperator())
    registry.register(dwell_ratio_definition(), DwellRatioOperator())


__all__ = [
    "AoiFilterOperator",
    "DwellRatioOperator",
    "FirstMatchLatencyOperator",
    "GazeAoiIntervalsOperator",
    "GazeFrame",
    "GazeOperatorError",
    "aoi_filter_definition",
    "dwell_ratio_definition",
    "first_match_latency_definition",
    "gaze_aoi_intervals_definition",
    "register_gaze_operators",
]
