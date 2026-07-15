"""Portable event and interval operators for editable evidence recipes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"


class TemporalOperatorError(ValueError):
    """Technical error in an event or interval operator."""


def _strict_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise TemporalOperatorError(f"{label} must be a non-negative strict integer")
    return value


def _required_text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise TemporalOperatorError(f"{label} must be a non-empty string")
    return value


def _attributes(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TemporalOperatorError("interval attributes must be a mapping")
    return cast(Mapping[str, object], value)


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    event_type: str
    t_ns: int
    duration_ns: int = 0
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_type:
            raise TemporalOperatorError("event ID and type cannot be empty")
        if type(self.t_ns) is not int or self.t_ns < 0:
            raise TemporalOperatorError("event t_ns must be a non-negative integer")
        if type(self.duration_ns) is not int or self.duration_ns < 0:
            raise TemporalOperatorError("event duration_ns must be non-negative")
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(self.attributes)),
        )


@dataclass(frozen=True, slots=True)
class IntervalRecord:
    interval_id: str
    start_t_ns: int
    end_t_ns: int
    attributes: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.interval_id:
            raise TemporalOperatorError("interval ID cannot be empty")
        if (
            type(self.start_t_ns) is not int
            or type(self.end_t_ns) is not int
            or self.start_t_ns < 0
            or self.end_t_ns <= self.start_t_ns
        ):
            raise TemporalOperatorError(
                "interval bounds must be strict non-negative increasing integers"
            )
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(self.attributes)),
        )


def _port(
    port_id: str,
    *,
    value_type: str,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Temporal {port_id} port.",
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
        family=OperatorFamily.TEMPORAL,
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


def event_select_definition() -> OperatorDefinition:
    return _definition(
        "temporal.event-select",
        inputs=(_port("events", value_type="event_collection"),),
        output_type="event_collection",
        parameter_schema={
            "type": "object",
            "properties": {
                "event_types": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
            },
            "required": ["event_types"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/event_types",
                label="Event types",
                group_id="selection",
                control=ParameterControlKind.MULTI_SELECT,
                help_text="Select semantic event types that define evidence opportunities.",
                unit=None,
            ),
        ),
    )


def event_window_definition() -> OperatorDefinition:
    return _definition(
        "temporal.event-window",
        inputs=(_port("events", value_type="event_collection"),),
        output_type="interval_collection",
        parameter_schema={
            "type": "object",
            "properties": {
                "start_offset_ns": {"type": "integer"},
                "end_offset_ns": {"type": "integer"},
                "include_event_duration": {"type": "boolean"},
                "clamp_to_zero": {"type": "boolean"},
            },
            "required": [
                "start_offset_ns",
                "end_offset_ns",
                "include_event_duration",
                "clamp_to_zero",
            ],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/start_offset_ns",
                label="Start offset",
                group_id="window",
                control=ParameterControlKind.NUMBER,
                help_text="Nanoseconds from event onset to evidence-window start.",
                unit="ns",
            ),
            ParameterUiDefinition(
                parameter_path="/end_offset_ns",
                label="End offset",
                group_id="window",
                control=ParameterControlKind.NUMBER,
                help_text="Nanoseconds from event anchor to evidence-window end.",
                unit="ns",
            ),
        ),
    )


def interval_intersect_definition() -> OperatorDefinition:
    return _definition(
        "temporal.interval-intersect",
        inputs=(
            _port("left", value_type="interval_collection"),
            _port("right", value_type="interval_collection"),
        ),
        output_type="interval_collection",
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        parameter_ui=(),
    )


def event_records(value: object) -> tuple[EventRecord, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TemporalOperatorError("events must be an ordered sequence")
    records: list[EventRecord] = []
    for item in value:
        if isinstance(item, EventRecord):
            records.append(item)
        elif isinstance(item, Mapping):
            mapping = cast(Mapping[str, object], item)
            records.append(
                EventRecord(
                    event_id=_required_text(mapping.get("event_id"), "event_id"),
                    event_type=_required_text(
                        mapping.get("event_type"),
                        "event_type",
                    ),
                    t_ns=_strict_nonnegative_int(mapping.get("t_ns"), "event t_ns"),
                    duration_ns=_strict_nonnegative_int(
                        mapping.get("duration_ns", 0),
                        "event duration_ns",
                    ),
                    attributes=_attributes(mapping.get("attributes", {})),
                )
            )
        else:
            raise TemporalOperatorError("events contain an unsupported item")
    ordered = tuple(sorted(records, key=lambda item: (item.t_ns, item.event_id)))
    if len({item.event_id for item in ordered}) != len(ordered):
        raise TemporalOperatorError("event IDs must be unique")
    return ordered


def interval_records(value: object) -> tuple[IntervalRecord, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TemporalOperatorError("intervals must be an ordered sequence")
    records: list[IntervalRecord] = []
    for item in value:
        if isinstance(item, IntervalRecord):
            records.append(item)
        elif isinstance(item, Mapping):
            mapping = cast(Mapping[str, object], item)
            records.append(
                IntervalRecord(
                    interval_id=_required_text(
                        mapping.get("interval_id"),
                        "interval_id",
                    ),
                    start_t_ns=_strict_nonnegative_int(
                        mapping.get("start_t_ns"),
                        "interval start_t_ns",
                    ),
                    end_t_ns=_strict_nonnegative_int(
                        mapping.get("end_t_ns"),
                        "interval end_t_ns",
                    ),
                    attributes=_attributes(mapping.get("attributes", {})),
                )
            )
        else:
            raise TemporalOperatorError("intervals contain an unsupported item")
    ordered = tuple(
        sorted(records, key=lambda item: (item.start_t_ns, item.end_t_ns, item.interval_id))
    )
    if len({item.interval_id for item in ordered}) != len(ordered):
        raise TemporalOperatorError("interval IDs must be unique")
    return ordered


class EventSelectOperator:
    operator_id = "temporal.event-select"
    implementation_version = _VERSION
    implementation_ref = "builtin.temporal.event-select"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        selected_types = parameters.get("event_types")
        if not isinstance(selected_types, list):
            raise TemporalOperatorError("event_types must be an array")
        selected = frozenset(str(value) for value in selected_types)
        return {
            "value": tuple(
                event
                for event in event_records(inputs.get("events"))
                if event.event_type in selected
            )
        }


class EventWindowOperator:
    operator_id = "temporal.event-window"
    implementation_version = _VERSION
    implementation_ref = "builtin.temporal.event-window"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        start_offset = parameters.get("start_offset_ns")
        end_offset = parameters.get("end_offset_ns")
        if type(start_offset) is not int or type(end_offset) is not int:
            raise TemporalOperatorError("window offsets must be strict integers")
        include_duration = parameters.get("include_event_duration")
        clamp_to_zero = parameters.get("clamp_to_zero")
        if type(include_duration) is not bool or type(clamp_to_zero) is not bool:
            raise TemporalOperatorError("window boolean parameters must be strict")
        windows: list[IntervalRecord] = []
        for event in event_records(inputs.get("events")):
            start = event.t_ns + start_offset
            end_anchor = event.t_ns + (event.duration_ns if include_duration else 0)
            end = end_anchor + end_offset
            if clamp_to_zero:
                start = max(0, start)
                end = max(0, end)
            if end <= start:
                raise TemporalOperatorError(
                    f"event {event.event_id!r} produces a non-positive window"
                )
            windows.append(
                IntervalRecord(
                    interval_id=f"window-{event.event_id}",
                    start_t_ns=start,
                    end_t_ns=end,
                    attributes={
                        **event.attributes,
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                    },
                )
            )
        return {"value": tuple(windows)}


class IntervalIntersectOperator:
    operator_id = "temporal.interval-intersect"
    implementation_version = _VERSION
    implementation_ref = "builtin.temporal.interval-intersect"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        left = interval_records(inputs.get("left"))
        right = interval_records(inputs.get("right"))
        intersections: list[IntervalRecord] = []
        for left_item in left:
            for right_item in right:
                start = max(left_item.start_t_ns, right_item.start_t_ns)
                end = min(left_item.end_t_ns, right_item.end_t_ns)
                if end <= start:
                    continue
                intersections.append(
                    IntervalRecord(
                        interval_id=(
                            f"intersection-{left_item.interval_id}-{right_item.interval_id}"
                        ),
                        start_t_ns=start,
                        end_t_ns=end,
                        attributes={
                            **left_item.attributes,
                            **right_item.attributes,
                            "left_interval_id": left_item.interval_id,
                            "right_interval_id": right_item.interval_id,
                        },
                    )
                )
        return {"value": tuple(intersections)}


def register_temporal_operators(registry: OperatorRegistry) -> None:
    registry.register(event_select_definition(), EventSelectOperator())
    registry.register(event_window_definition(), EventWindowOperator())
    registry.register(interval_intersect_definition(), IntervalIntersectOperator())


__all__ = [
    "EventRecord",
    "EventSelectOperator",
    "EventWindowOperator",
    "IntervalIntersectOperator",
    "IntervalRecord",
    "TemporalOperatorError",
    "event_select_definition",
    "event_records",
    "event_window_definition",
    "interval_intersect_definition",
    "interval_records",
    "register_temporal_operators",
]
