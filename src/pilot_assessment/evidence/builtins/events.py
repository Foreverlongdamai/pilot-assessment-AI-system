"""Generic event detectors and legacy-kernel wrappers for editable recipes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise
from types import MappingProxyType

from pydantic import JsonValue

from pilot_assessment.anchors.primitives.events import (
    CausalBooleanInterval,
    confirmed_true_runs,
)
from pilot_assessment.anchors.primitives.movement import (
    MovementChannelResult,
    MovementKernelResult,
    MovementSupportSegment,
    MovementTurningPoint,
)
from pilot_assessment.anchors.primitives.reversal import compute_o7_kernel
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
from pilot_assessment.evidence.builtins.flight import MaskSeries
from pilot_assessment.evidence.builtins.signal import SignalSeries, signal_series
from pilot_assessment.evidence.builtins.temporal import (
    EventRecord,
    IntervalRecord,
    event_records,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"
_NS_PER_SECOND = 1_000_000_000.0


class EventOperatorError(ValueError):
    """Technical error in a generic event operator."""


def _finite(value: object, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventOperatorError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or (minimum is not None and numeric < minimum):
        raise EventOperatorError(f"{label} must be finite and at least {minimum}")
    return numeric


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EventOperatorError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise EventOperatorError(f"{label} must be a non-empty string")
    return value


def _port(
    port_id: str,
    value_type: str,
    temporal: TemporalSemantics,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Event {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=PortCardinality.ONE,
            temporal_semantics=temporal,
            unit=None,
        ),
    )


def _ui(
    path: str,
    label: str,
    control: ParameterControlKind,
    *,
    unit: str | None = None,
) -> ParameterUiDefinition:
    return ParameterUiDefinition(
        parameter_path=path,
        label=label,
        group_id="parameters",
        control=control,
        help_text="Editable recipe parameter; the initial value is not an expert standard.",
        unit=unit,
    )


def _definition(
    operator_id: str,
    *,
    inputs: tuple[OperatorPortDefinition, ...],
    output_type: str,
    output_temporal: TemporalSemantics,
    parameter_schema: dict[str, JsonValue],
    parameter_ui: tuple[ParameterUiDefinition, ...],
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version=_VERSION,
        family=OperatorFamily.EVENT,
        name=operator_id.replace(".", " ").replace("-", " ").title(),
        description=f"Reusable editable {operator_id} operator.",
        pseudocode=None,
        input_ports=inputs,
        output_ports=(_port("value", output_type, output_temporal),),
        parameter_schema=parameter_schema,
        parameter_ui=parameter_ui,
        trace_capability=TraceCapability.FULL,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


def _event_type_schema() -> dict[str, JsonValue]:
    return {"type": "string", "minLength": 1}


def threshold_crossing_definition() -> OperatorDefinition:
    return _definition(
        "event.threshold-crossing",
        inputs=(_port("signal", "signal_series", TemporalSemantics.SAMPLED),),
        output_type="event_collection",
        output_temporal=TemporalSemantics.POINT,
        parameter_schema={
            "type": "object",
            "properties": {
                "threshold": {"type": "number"},
                "direction": {"type": "string", "enum": ["rising", "falling", "either"]},
                "event_type": _event_type_schema(),
            },
            "required": ["threshold", "direction", "event_type"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/threshold", "Threshold", ParameterControlKind.NUMBER),
            _ui("/direction", "Direction", ParameterControlKind.SELECT),
            _ui("/event_type", "Event type", ParameterControlKind.TEXT),
        ),
    )


def hold_run_definition() -> OperatorDefinition:
    return _definition(
        "event.hold-run",
        inputs=(_port("signal", "signal_series", TemporalSemantics.SAMPLED),),
        output_type="interval_collection",
        output_temporal=TemporalSemantics.INTERVAL,
        parameter_schema={
            "type": "object",
            "properties": {
                "threshold": {"type": "number"},
                "comparison": {"type": "string", "enum": ["gt", "gte", "lt", "lte"]},
                "minimum_duration_ns": {"type": "integer", "minimum": 0},
                "observation_end_ns": {"type": "integer", "minimum": 1},
                "interval_type": _event_type_schema(),
            },
            "required": [
                "threshold",
                "comparison",
                "minimum_duration_ns",
                "observation_end_ns",
                "interval_type",
            ],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/threshold", "Threshold", ParameterControlKind.NUMBER),
            _ui("/comparison", "Comparison", ParameterControlKind.SELECT),
            _ui(
                "/minimum_duration_ns",
                "Minimum duration",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui(
                "/observation_end_ns",
                "Observation end",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui("/interval_type", "Interval type", ParameterControlKind.TEXT),
        ),
    )


def mask_run_definition() -> OperatorDefinition:
    return _definition(
        "event.mask-run",
        inputs=(_port("mask", "mask_series", TemporalSemantics.SAMPLED),),
        output_type="interval_collection",
        output_temporal=TemporalSemantics.INTERVAL,
        parameter_schema={
            "type": "object",
            "properties": {
                "minimum_duration_ns": {"type": "integer", "minimum": 0},
                "observation_end_ns": {"type": "integer", "minimum": 1},
                "interval_type": _event_type_schema(),
            },
            "required": ["minimum_duration_ns", "observation_end_ns", "interval_type"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui(
                "/minimum_duration_ns",
                "Minimum duration",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui(
                "/observation_end_ns",
                "Observation end",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui("/interval_type", "Interval type", ParameterControlKind.TEXT),
        ),
    )


def peak_definition() -> OperatorDefinition:
    return _definition(
        "event.peak",
        inputs=(_port("signal", "signal_series", TemporalSemantics.SAMPLED),),
        output_type="event_collection",
        output_temporal=TemporalSemantics.POINT,
        parameter_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["maximum", "minimum", "absolute"]},
                "event_type": _event_type_schema(),
            },
            "required": ["mode", "event_type"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/mode", "Peak mode", ParameterControlKind.SELECT),
            _ui("/event_type", "Event type", ParameterControlKind.TEXT),
        ),
    )


def turning_point_definition() -> OperatorDefinition:
    return _definition(
        "event.turning-point",
        inputs=(_port("signal", "signal_series", TemporalSemantics.SAMPLED),),
        output_type="event_collection",
        output_temporal=TemporalSemantics.POINT,
        parameter_schema={
            "type": "object",
            "properties": {
                "minimum_delta": {"type": "number", "minimum": 0.0},
                "event_type": _event_type_schema(),
            },
            "required": ["minimum_delta", "event_type"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/minimum_delta", "Minimum delta", ParameterControlKind.NUMBER),
            _ui("/event_type", "Event type", ParameterControlKind.TEXT),
        ),
    )


def movement_definition() -> OperatorDefinition:
    return _definition(
        "event.movement",
        inputs=(_port("turning_points", "event_collection", TemporalSemantics.POINT),),
        output_type="event_collection",
        output_temporal=TemporalSemantics.POINT,
        parameter_schema={
            "type": "object",
            "properties": {
                "minimum_amplitude": {"type": "number", "minimum": 0.0},
                "minimum_separation_ns": {"type": "integer", "minimum": 0},
                "event_type": _event_type_schema(),
            },
            "required": ["minimum_amplitude", "minimum_separation_ns", "event_type"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/minimum_amplitude", "Minimum amplitude", ParameterControlKind.NUMBER),
            _ui(
                "/minimum_separation_ns",
                "Minimum separation",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui("/event_type", "Event type", ParameterControlKind.TEXT),
        ),
    )


def reversal_definition() -> OperatorDefinition:
    return _definition(
        "event.reversal",
        inputs=(_port("turning_points", "event_collection", TemporalSemantics.POINT),),
        output_type="event_collection",
        output_temporal=TemporalSemantics.POINT,
        parameter_schema={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "minLength": 1},
                "support_start_t_ns": {"type": "integer", "minimum": 0},
                "support_end_t_ns": {"type": "integer", "minimum": 1},
                "minimum_amplitude": {"type": "number", "minimum": 0.0},
                "minimum_separation_ns": {"type": "integer", "minimum": 0},
                "event_type": _event_type_schema(),
            },
            "required": [
                "channel_id",
                "support_start_t_ns",
                "support_end_t_ns",
                "minimum_amplitude",
                "minimum_separation_ns",
                "event_type",
            ],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/channel_id", "Channel", ParameterControlKind.TEXT),
            _ui("/support_start_t_ns", "Support start", ParameterControlKind.NUMBER, unit="ns"),
            _ui("/support_end_t_ns", "Support end", ParameterControlKind.NUMBER, unit="ns"),
            _ui("/minimum_amplitude", "Minimum amplitude", ParameterControlKind.NUMBER),
            _ui(
                "/minimum_separation_ns",
                "Minimum separation",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui("/event_type", "Event type", ParameterControlKind.TEXT),
        ),
    )


def recovery_definition() -> OperatorDefinition:
    return _definition(
        "event.recovery",
        inputs=(
            _port("signal", "signal_series", TemporalSemantics.SAMPLED),
            _port("events", "event_collection", TemporalSemantics.POINT),
        ),
        output_type="named_numbers",
        output_temporal=TemporalSemantics.MIXED,
        parameter_schema={
            "type": "object",
            "properties": {
                "target": {"type": "number"},
                "tolerance": {"type": "number", "minimum": 0.0},
                "hold_duration_ns": {"type": "integer", "minimum": 0},
                "horizon_ns": {"type": "integer", "minimum": 1},
            },
            "required": ["target", "tolerance", "hold_duration_ns", "horizon_ns"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/target", "Recovery target", ParameterControlKind.NUMBER),
            _ui("/tolerance", "Tolerance", ParameterControlKind.NUMBER),
            _ui("/hold_duration_ns", "Hold duration", ParameterControlKind.NUMBER, unit="ns"),
            _ui("/horizon_ns", "Horizon", ParameterControlKind.NUMBER, unit="ns"),
        ),
    )


def latency_definition() -> OperatorDefinition:
    return _definition(
        "event.latency",
        inputs=(
            _port("triggers", "event_collection", TemporalSemantics.POINT),
            _port("responses", "event_collection", TemporalSemantics.POINT),
        ),
        output_type="named_numbers",
        output_temporal=TemporalSemantics.MIXED,
        parameter_schema={
            "type": "object",
            "properties": {
                "horizon_ns": {"type": "integer", "minimum": 1},
                "no_match_policy": {"type": "string", "enum": ["horizon", "fixed"]},
                "fixed_latency_s": {"type": "number", "minimum": 0.0},
            },
            "required": ["horizon_ns", "no_match_policy", "fixed_latency_s"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/horizon_ns", "Response horizon", ParameterControlKind.NUMBER, unit="ns"),
            _ui("/no_match_policy", "No-match value", ParameterControlKind.SELECT),
            _ui(
                "/fixed_latency_s",
                "Fixed no-match latency",
                ParameterControlKind.NUMBER,
                unit="s",
            ),
        ),
    )


def _crossed(previous: float, current: float, threshold: float, direction: object) -> bool:
    rising = previous < threshold <= current
    falling = previous > threshold >= current
    if direction == "rising":
        return rising
    if direction == "falling":
        return falling
    if direction == "either":
        return rising or falling
    raise EventOperatorError("crossing direction is not supported")


def _compare(value: float, threshold: float, comparison: object) -> bool:
    if comparison == "gt":
        return value > threshold
    if comparison == "gte":
        return value >= threshold
    if comparison == "lt":
        return value < threshold
    if comparison == "lte":
        return value <= threshold
    raise EventOperatorError("threshold comparison is not supported")


def _event_value(event: EventRecord) -> float:
    return _finite(event.attributes.get("value"), "turning-point value")


class ThresholdCrossingOperator:
    operator_id = "event.threshold-crossing"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.threshold-crossing"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        series = signal_series(inputs.get("signal"))
        threshold = _finite(parameters.get("threshold"), "threshold")
        event_type = _text(parameters.get("event_type"), "event_type")
        events = tuple(
            EventRecord(
                event_id=f"{event_type}-{index:06d}",
                event_type=event_type,
                t_ns=current.t_ns,
                attributes={
                    "previous_value": previous.value,
                    "value": current.value,
                    "threshold": threshold,
                },
            )
            for index, (previous, current) in enumerate(
                zip(series.samples, series.samples[1:], strict=False)
            )
            if _crossed(previous.value, current.value, threshold, parameters.get("direction"))
        )
        return {"value": events}


class HoldRunOperator:
    operator_id = "event.hold-run"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.hold-run"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        series = signal_series(inputs.get("signal"))
        threshold = _finite(parameters.get("threshold"), "threshold")
        minimum = _strict_int(parameters.get("minimum_duration_ns"), "minimum_duration_ns")
        observation_end = _strict_int(
            parameters.get("observation_end_ns"),
            "observation_end_ns",
            minimum=1,
        )
        if series.samples and observation_end < series.samples[-1].t_ns:
            raise EventOperatorError("observation end cannot precede the last signal sample")
        intervals = tuple(
            CausalBooleanInterval(
                start_t_ns=sample.t_ns,
                end_t_ns=(
                    series.samples[index + 1].t_ns
                    if index + 1 < len(series.samples)
                    else observation_end
                ),
                source_row_id=index,
                active=_compare(
                    sample.value,
                    threshold,
                    parameters.get("comparison"),
                ),
            )
            for index, sample in enumerate(series.samples)
            if (
                series.samples[index + 1].t_ns
                if index + 1 < len(series.samples)
                else observation_end
            )
            >= sample.t_ns
        )
        interval_type = _text(parameters.get("interval_type"), "interval_type")
        return {
            "value": tuple(
                IntervalRecord(
                    interval_id=f"{interval_type}-{index:06d}",
                    start_t_ns=run.onset_t_ns,
                    end_t_ns=run.end_t_ns,
                    attributes={
                        "interval_type": interval_type,
                        "confirmation_t_ns": run.confirmation_t_ns,
                        "threshold": threshold,
                    },
                )
                for index, run in enumerate(
                    confirmed_true_runs(intervals, minimum_duration_ns=minimum)
                )
                if run.end_t_ns > run.onset_t_ns
            )
        }


class MaskRunOperator:
    operator_id = "event.mask-run"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.mask-run"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        mask = inputs.get("mask")
        if not isinstance(mask, MaskSeries):
            raise EventOperatorError("mask-run requires a MaskSeries")
        observation_end = _strict_int(
            parameters.get("observation_end_ns"),
            "observation_end_ns",
            minimum=1,
        )
        if mask.samples and observation_end < mask.samples[-1].t_ns:
            raise EventOperatorError("observation end cannot precede the last mask sample")
        intervals = tuple(
            CausalBooleanInterval(
                sample.t_ns,
                (
                    mask.samples[index + 1].t_ns
                    if index + 1 < len(mask.samples)
                    else observation_end
                ),
                index,
                sample.active,
            )
            for index, sample in enumerate(mask.samples)
            if (mask.samples[index + 1].t_ns if index + 1 < len(mask.samples) else observation_end)
            >= sample.t_ns
        )
        minimum = _strict_int(parameters.get("minimum_duration_ns"), "minimum_duration_ns")
        interval_type = _text(parameters.get("interval_type"), "interval_type")
        return {
            "value": tuple(
                IntervalRecord(
                    f"{interval_type}-{index:06d}",
                    run.onset_t_ns,
                    run.end_t_ns,
                    {
                        "interval_type": interval_type,
                        "confirmation_t_ns": run.confirmation_t_ns,
                    },
                )
                for index, run in enumerate(
                    confirmed_true_runs(intervals, minimum_duration_ns=minimum)
                )
                if run.end_t_ns > run.onset_t_ns
            )
        }


class PeakOperator:
    operator_id = "event.peak"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.peak"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        series = signal_series(inputs.get("signal"))
        if not series.samples:
            raise EventOperatorError("peak requires at least one sample")
        mode = parameters.get("mode")
        if mode == "maximum":
            selected = max(series.samples, key=lambda sample: (sample.value, -sample.t_ns))
        elif mode == "minimum":
            selected = min(series.samples, key=lambda sample: (sample.value, sample.t_ns))
        elif mode == "absolute":
            selected = max(series.samples, key=lambda sample: (abs(sample.value), -sample.t_ns))
        else:
            raise EventOperatorError("peak mode is not supported")
        event_type = _text(parameters.get("event_type"), "event_type")
        return {
            "value": (
                EventRecord(
                    event_id=f"{event_type}-000000",
                    event_type=event_type,
                    t_ns=selected.t_ns,
                    attributes={"value": selected.value, "mode": mode},
                ),
            )
        }


class TurningPointOperator:
    operator_id = "event.turning-point"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.turning-point"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        series = signal_series(inputs.get("signal"))
        minimum = _finite(parameters.get("minimum_delta"), "minimum_delta", minimum=0.0)
        event_type = _text(parameters.get("event_type"), "event_type")
        points: list[EventRecord] = []
        for previous, current, following in zip(
            series.samples,
            series.samples[1:],
            series.samples[2:],
            strict=False,
        ):
            left = current.value - previous.value
            right = following.value - current.value
            if left * right >= 0.0 or min(abs(left), abs(right)) < minimum:
                continue
            points.append(
                EventRecord(
                    event_id=f"{event_type}-{len(points):06d}",
                    event_type=event_type,
                    t_ns=current.t_ns,
                    attributes={
                        "value": current.value,
                        "left_delta": left,
                        "right_delta": right,
                    },
                )
            )
        return {"value": tuple(points)}


class MovementOperator:
    operator_id = "event.movement"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.movement"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        points = event_records(inputs.get("turning_points"))
        amplitude_minimum = _finite(
            parameters.get("minimum_amplitude"),
            "minimum_amplitude",
            minimum=0.0,
        )
        separation = _strict_int(
            parameters.get("minimum_separation_ns"),
            "minimum_separation_ns",
        )
        event_type = _text(parameters.get("event_type"), "event_type")
        events: list[EventRecord] = []
        for left, right in pairwise(points):
            amplitude = abs(_event_value(right) - _event_value(left))
            if right.t_ns - left.t_ns < separation or amplitude < amplitude_minimum:
                continue
            events.append(
                EventRecord(
                    event_id=f"{event_type}-{len(events):06d}",
                    event_type=event_type,
                    t_ns=right.t_ns,
                    attributes={"amplitude": amplitude},
                )
            )
        return {"value": tuple(events)}


class ReversalOperator:
    operator_id = "event.reversal"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.reversal"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        points = event_records(inputs.get("turning_points"))
        channel_id = _text(parameters.get("channel_id"), "channel_id")
        start = _strict_int(parameters.get("support_start_t_ns"), "support_start_t_ns")
        end = _strict_int(
            parameters.get("support_end_t_ns"),
            "support_end_t_ns",
            minimum=1,
        )
        if end <= start:
            raise EventOperatorError("reversal support must have positive duration")
        typed_points = tuple(
            MovementTurningPoint(point.t_ns, _event_value(point)) for point in points
        )
        movement = MovementKernelResult(
            status="computed",
            reason=None,
            channels=(
                MovementChannelResult(
                    channel_id=channel_id,
                    observed_support_duration_ns=end - start,
                    support_segments=(MovementSupportSegment(start, end),),
                    turning_points=typed_points,
                    movements=(),
                    grid_sample_count=len(points),
                    short_filter_bypass_count=0,
                ),
            ),
            sample_count=len(points),
            source_start_t_ns=start,
            source_end_t_ns=end,
            gap_count=0,
            max_gap_ns=None,
        )
        result = compute_o7_kernel(
            movement,
            (channel_id,),
            _finite(
                parameters.get("minimum_amplitude"),
                "minimum_amplitude",
                minimum=0.0,
            ),
            _strict_int(
                parameters.get("minimum_separation_ns"),
                "minimum_separation_ns",
            ),
        )
        event_type = _text(parameters.get("event_type"), "event_type")
        events = tuple(
            EventRecord(
                event_id=f"{event_type}-{index:06d}",
                event_type=event_type,
                t_ns=event.event_t_ns,
                attributes={
                    "amplitude": event.amplitude_pct,
                    "channel_id": channel_id,
                },
            )
            for index, event in enumerate(result.channel_rates[0].reversal_events)
        )
        return {"value": events}


def _recovery_intervals(
    series: SignalSeries,
    event: EventRecord,
    *,
    target: float,
    tolerance: float,
    horizon_ns: int,
) -> tuple[CausalBooleanInterval, ...]:
    end = event.t_ns + horizon_ns
    selected = tuple(sample for sample in series.samples if event.t_ns <= sample.t_ns <= end)
    intervals: list[CausalBooleanInterval] = []
    for index, sample in enumerate(selected):
        interval_end = selected[index + 1].t_ns if index + 1 < len(selected) else end
        if interval_end < sample.t_ns:
            continue
        intervals.append(
            CausalBooleanInterval(
                start_t_ns=sample.t_ns,
                end_t_ns=interval_end,
                source_row_id=index,
                active=abs(sample.value - target) <= tolerance,
            )
        )
    return tuple(intervals)


class RecoveryOperator:
    operator_id = "event.recovery"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.recovery"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        series = signal_series(inputs.get("signal"))
        events = event_records(inputs.get("events"))
        target = _finite(parameters.get("target"), "target")
        tolerance = _finite(parameters.get("tolerance"), "tolerance", minimum=0.0)
        hold = _strict_int(parameters.get("hold_duration_ns"), "hold_duration_ns")
        horizon = _strict_int(parameters.get("horizon_ns"), "horizon_ns", minimum=1)
        values: dict[str, float] = {}
        for event in events:
            runs = confirmed_true_runs(
                _recovery_intervals(
                    series,
                    event,
                    target=target,
                    tolerance=tolerance,
                    horizon_ns=horizon,
                ),
                minimum_duration_ns=hold,
            )
            latency_ns = runs[0].onset_t_ns - event.t_ns if runs else horizon
            values[event.event_id] = latency_ns / _NS_PER_SECOND
        return {"value": MappingProxyType(values)}


class LatencyOperator:
    operator_id = "event.latency"
    implementation_version = _VERSION
    implementation_ref = "builtin.event.latency"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        triggers = event_records(inputs.get("triggers"))
        responses = event_records(inputs.get("responses"))
        horizon = _strict_int(parameters.get("horizon_ns"), "horizon_ns", minimum=1)
        policy = parameters.get("no_match_policy")
        fixed = _finite(parameters.get("fixed_latency_s"), "fixed_latency_s", minimum=0.0)
        values: dict[str, float] = {}
        for trigger in triggers:
            matching = tuple(
                response
                for response in responses
                if trigger.t_ns <= response.t_ns <= trigger.t_ns + horizon
            )
            if matching:
                latency = (matching[0].t_ns - trigger.t_ns) / _NS_PER_SECOND
            elif policy == "horizon":
                latency = horizon / _NS_PER_SECOND
            elif policy == "fixed":
                latency = fixed
            else:
                raise EventOperatorError("latency no-match policy is not supported")
            values[trigger.event_id] = latency
        return {"value": MappingProxyType(values)}


def register_event_operators(registry: OperatorRegistry) -> None:
    registry.register(threshold_crossing_definition(), ThresholdCrossingOperator())
    registry.register(hold_run_definition(), HoldRunOperator())
    registry.register(mask_run_definition(), MaskRunOperator())
    registry.register(peak_definition(), PeakOperator())
    registry.register(turning_point_definition(), TurningPointOperator())
    registry.register(movement_definition(), MovementOperator())
    registry.register(reversal_definition(), ReversalOperator())
    registry.register(recovery_definition(), RecoveryOperator())
    registry.register(latency_definition(), LatencyOperator())


__all__ = [
    "EventOperatorError",
    "HoldRunOperator",
    "LatencyOperator",
    "MovementOperator",
    "MaskRunOperator",
    "PeakOperator",
    "RecoveryOperator",
    "ReversalOperator",
    "ThresholdCrossingOperator",
    "TurningPointOperator",
    "register_event_operators",
]
