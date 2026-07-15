"""Reusable scalar statistics and aggregation operators."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from numbers import Real
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
from pilot_assessment.evidence.builtins.signal import SignalSeries
from pilot_assessment.evidence.builtins.temporal import interval_records
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"


class StatisticsOperatorError(ValueError):
    """Technical error in a reusable statistics operator."""


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


def _number_port(
    port_id: str,
    *,
    cardinality: PortCardinality,
    value_type: str = "number",
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Numeric {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=cardinality,
            temporal_semantics=TemporalSemantics.MIXED,
            unit=None,
        ),
    )


def _definition(
    operator_id: str,
    *,
    family: OperatorFamily,
    inputs: tuple[OperatorPortDefinition, ...],
    parameter_schema: dict[str, JsonValue],
    parameter_ui: tuple[ParameterUiDefinition, ...] = (),
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version=_VERSION,
        family=family,
        name=operator_id.replace(".", " ").replace("-", " ").title(),
        description=f"Reusable editable {operator_id} operator.",
        pseudocode=None,
        input_ports=inputs,
        output_ports=(
            _number_port("value", cardinality=PortCardinality.ONE),
        ),
        parameter_schema=parameter_schema,
        parameter_ui=parameter_ui,
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


def mean_definition() -> OperatorDefinition:
    return _definition(
        "statistics.mean",
        family=OperatorFamily.STATISTICS,
        inputs=(_number_port("values", cardinality=PortCardinality.MANY),),
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )


def sum_duration_definition() -> OperatorDefinition:
    return _definition(
        "statistics.sum-duration",
        family=OperatorFamily.STATISTICS,
        inputs=(_number_port("durations", cardinality=PortCardinality.MANY),),
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )


def ratio_definition() -> OperatorDefinition:
    return _definition(
        "statistics.ratio",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port("numerator", cardinality=PortCardinality.ONE),
            _number_port("denominator", cardinality=PortCardinality.ONE),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "zero_denominator": {
                    "type": "string",
                    "enum": ["error", "zero"],
                },
            },
            "required": ["zero_denominator"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/zero_denominator",
                label="Zero denominator",
                group_id="ratio",
                control=ParameterControlKind.SELECT,
                help_text="Choose whether a zero denominator raises an error or returns zero.",
                unit=None,
            ),
        ),
    )


def event_aggregation_definition() -> OperatorDefinition:
    return _definition(
        "aggregation.event",
        family=OperatorFamily.AGGREGATION,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="named_numbers",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["worst", "best", "mean", "median"],
                },
                "direction": {
                    "type": "string",
                    "enum": ["higher_is_better", "lower_is_better"],
                },
            },
            "required": ["mode", "direction"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/mode",
                label="Aggregation",
                group_id="aggregation",
                control=ParameterControlKind.SELECT,
                help_text="Aggregate per-event values without changing their scientific meaning.",
                unit=None,
            ),
            ParameterUiDefinition(
                parameter_path="/direction",
                label="Direction",
                group_id="aggregation",
                control=ParameterControlKind.SELECT,
                help_text="Defines worst and best for this recipe.",
                unit=None,
            ),
        ),
    )


def count_definition() -> OperatorDefinition:
    return _definition(
        "statistics.count",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )


def duration_definition() -> OperatorDefinition:
    return _definition(
        "statistics.duration",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "intervals",
                cardinality=PortCardinality.ONE,
                value_type="interval_collection",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "unit": {"type": "string", "enum": ["seconds", "nanoseconds"]},
                "union_overlaps": {"type": "boolean"},
            },
            "required": ["unit", "union_overlaps"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/unit", "Duration unit", ParameterControlKind.SELECT),
            _ui("/union_overlaps", "Union overlaps", ParameterControlKind.CHECKBOX),
        ),
    )


def rms_definition() -> OperatorDefinition:
    return _definition(
        "statistics.rms",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
        ),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


def median_definition() -> OperatorDefinition:
    return _definition(
        "statistics.median",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
        ),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


def percentile_definition() -> OperatorDefinition:
    return _definition(
        "statistics.percentile",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {"percentile": {"type": "number", "minimum": 0.0, "maximum": 100.0}},
            "required": ["percentile"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/percentile", "Percentile", ParameterControlKind.SLIDER, unit="%"),
        ),
    )


def rate_definition() -> OperatorDefinition:
    return _definition(
        "statistics.rate",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port("count", cardinality=PortCardinality.ONE),
            _number_port("duration", cardinality=PortCardinality.ONE),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "duration_unit": {"type": "string", "enum": ["seconds", "nanoseconds"]},
                "zero_duration": {"type": "string", "enum": ["zero", "error"]},
            },
            "required": ["duration_unit", "zero_duration"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/duration_unit", "Duration unit", ParameterControlKind.SELECT),
            _ui("/zero_duration", "Zero duration", ParameterControlKind.SELECT),
        ),
    )


def pooled_ratio_definition() -> OperatorDefinition:
    return _definition(
        "statistics.pooled-ratio",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "numerators",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
            _number_port(
                "denominators",
                cardinality=PortCardinality.ONE,
                value_type="any",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "zero_denominator": {"type": "string", "enum": ["zero", "error"]},
            },
            "required": ["zero_denominator"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/zero_denominator", "Zero denominator", ParameterControlKind.SELECT),
        ),
    )


def named_select_definition() -> OperatorDefinition:
    return _definition(
        "statistics.named-select",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "values",
                cardinality=PortCardinality.ONE,
                value_type="named_numbers",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {"key": {"type": "string", "minLength": 1}},
            "required": ["key"],
            "additionalProperties": False,
        },
        parameter_ui=(_ui("/key", "Value key", ParameterControlKind.TEXT),),
    )


def correlation_definition() -> OperatorDefinition:
    return _definition(
        "statistics.correlation",
        family=OperatorFamily.STATISTICS,
        inputs=(
            _number_port(
                "left",
                cardinality=PortCardinality.ONE,
                value_type="signal_series",
            ),
            _number_port(
                "right",
                cardinality=PortCardinality.ONE,
                value_type="signal_series",
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "absolute": {"type": "boolean"},
                "degenerate": {"type": "string", "enum": ["zero", "error"]},
            },
            "required": ["absolute", "degenerate"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/absolute", "Absolute correlation", ParameterControlKind.CHECKBOX),
            _ui("/degenerate", "Degenerate series", ParameterControlKind.SELECT),
        ),
    )


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise StatisticsOperatorError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise StatisticsOperatorError(f"{label} must be finite")
    return result


def _named_numbers(inputs: Mapping[str, object], port_id: str) -> list[float]:
    raw_values = inputs.get(port_id)
    if not isinstance(raw_values, Mapping):
        raise StatisticsOperatorError(f"{port_id} must be a named many-input mapping")
    values = [
        _number(value, f"{port_id}.{slot_id}")
        for slot_id, value in raw_values.items()
    ]
    if not values:
        raise StatisticsOperatorError(f"{port_id} cannot be empty")
    return values


def _numeric_values(value: object, label: str) -> list[float]:
    if isinstance(value, SignalSeries):
        values = [sample.value for sample in value.samples]
    elif isinstance(value, Mapping):
        values = [_number(item, label) for item in value.values()]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = [_number(item, label) for item in value]
    else:
        raise StatisticsOperatorError(f"{label} must be a numeric collection or signal")
    if not values:
        raise StatisticsOperatorError(f"{label} cannot be empty")
    return values


def _collection_count(value: object) -> int:
    if isinstance(value, SignalSeries):
        return len(value.samples)
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes)):
        return len(value)
    raise StatisticsOperatorError("count input must be a collection")


def _union_duration_ns(value: object, *, union_overlaps: bool) -> int:
    intervals = interval_records(value)
    if not union_overlaps:
        return sum(item.end_t_ns - item.start_t_ns for item in intervals)
    total = 0
    current_start: int | None = None
    current_end: int | None = None
    for item in intervals:
        if current_start is None:
            current_start, current_end = item.start_t_ns, item.end_t_ns
        elif current_end is not None and item.start_t_ns <= current_end:
            current_end = max(current_end, item.end_t_ns)
        else:
            assert current_end is not None
            total += current_end - current_start
            current_start, current_end = item.start_t_ns, item.end_t_ns
    if current_start is not None and current_end is not None:
        total += current_end - current_start
    return total


class MeanOperator:
    operator_id = "statistics.mean"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.mean"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        return {"value": statistics.fmean(_named_numbers(inputs, "values"))}


class SumDurationOperator:
    operator_id = "statistics.sum-duration"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.sum-duration"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        return {"value": sum(_named_numbers(inputs, "durations"))}


class RatioOperator:
    operator_id = "statistics.ratio"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.ratio"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        numerator = _number(inputs.get("numerator"), "numerator")
        denominator = _number(inputs.get("denominator"), "denominator")
        if denominator == 0.0:
            if parameters.get("zero_denominator") == "zero":
                return {"value": 0.0}
            raise StatisticsOperatorError("denominator cannot be zero")
        return {"value": numerator / denominator}


class EventAggregationOperator:
    operator_id = "aggregation.event"
    implementation_version = _VERSION
    implementation_ref = "builtin.aggregation.event"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        values = _named_numbers(inputs, "values")
        mode = parameters.get("mode")
        direction = parameters.get("direction")
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise StatisticsOperatorError("aggregation direction is not supported")
        if mode == "mean":
            value = statistics.fmean(values)
        elif mode == "median":
            value = statistics.median(values)
        elif mode == "worst":
            value = (
                min(values)
                if direction == "higher_is_better"
                else max(values)
            )
        elif mode == "best":
            value = (
                max(values)
                if direction == "higher_is_better"
                else min(values)
            )
        else:
            raise StatisticsOperatorError("aggregation mode is not supported")
        return {"value": value}


class CountOperator:
    operator_id = "statistics.count"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.count"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        return {"value": float(_collection_count(inputs.get("values")))}


class DurationOperator:
    operator_id = "statistics.duration"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.duration"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        union = parameters.get("union_overlaps")
        if type(union) is not bool:
            raise StatisticsOperatorError("union_overlaps must be boolean")
        duration_ns = _union_duration_ns(inputs.get("intervals"), union_overlaps=union)
        unit = parameters.get("unit")
        if unit == "seconds":
            return {"value": duration_ns / 1_000_000_000.0}
        if unit == "nanoseconds":
            return {"value": float(duration_ns)}
        raise StatisticsOperatorError("duration unit is not supported")


class RmsOperator:
    operator_id = "statistics.rms"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.rms"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        values = _numeric_values(inputs.get("values"), "RMS values")
        return {"value": math.sqrt(math.fsum(value * value for value in values) / len(values))}


class MedianOperator:
    operator_id = "statistics.median"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.median"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        return {"value": statistics.median(_numeric_values(inputs.get("values"), "median values"))}


class PercentileOperator:
    operator_id = "statistics.percentile"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.percentile"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        values = sorted(_numeric_values(inputs.get("values"), "percentile values"))
        percentile = _number(parameters.get("percentile"), "percentile")
        if not 0.0 <= percentile <= 100.0:
            raise StatisticsOperatorError("percentile must lie in [0, 100]")
        position = (len(values) - 1) * percentile / 100.0
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            value = values[lower]
        else:
            fraction = position - lower
            value = values[lower] + fraction * (values[upper] - values[lower])
        return {"value": value}


class RateOperator:
    operator_id = "statistics.rate"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.rate"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        count = _number(inputs.get("count"), "count")
        duration = _number(inputs.get("duration"), "duration")
        if parameters.get("duration_unit") == "nanoseconds":
            duration /= 1_000_000_000.0
        elif parameters.get("duration_unit") != "seconds":
            raise StatisticsOperatorError("rate duration unit is not supported")
        if duration == 0.0:
            if parameters.get("zero_duration") == "zero":
                return {"value": 0.0}
            raise StatisticsOperatorError("rate duration cannot be zero")
        return {"value": count / duration}


class PooledRatioOperator:
    operator_id = "statistics.pooled-ratio"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.pooled-ratio"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        numerator = math.fsum(_numeric_values(inputs.get("numerators"), "numerators"))
        denominator = math.fsum(_numeric_values(inputs.get("denominators"), "denominators"))
        if denominator == 0.0:
            if parameters.get("zero_denominator") == "zero":
                return {"value": 0.0}
            raise StatisticsOperatorError("pooled denominator cannot be zero")
        return {"value": numerator / denominator}


class NamedSelectOperator:
    operator_id = "statistics.named-select"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.named-select"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        values = inputs.get("values")
        if not isinstance(values, Mapping):
            raise StatisticsOperatorError("named values must be a mapping")
        typed_values = cast(Mapping[str, object], values)
        key = parameters.get("key")
        if type(key) is not str or not key:
            raise StatisticsOperatorError("named value key must be a non-empty string")
        if key not in typed_values:
            raise StatisticsOperatorError(f"named value {key!r} is not present")
        return {"value": _number(typed_values[key], key)}


class CorrelationOperator:
    operator_id = "statistics.correlation"
    implementation_version = _VERSION
    implementation_ref = "builtin.statistics.correlation"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        left = inputs.get("left")
        right = inputs.get("right")
        if not isinstance(left, SignalSeries) or not isinstance(right, SignalSeries):
            raise StatisticsOperatorError("correlation inputs must be SignalSeries values")
        right_by_time = {sample.t_ns: sample.value for sample in right.samples}
        pairs = tuple(
            (sample.value, right_by_time[sample.t_ns])
            for sample in left.samples
            if sample.t_ns in right_by_time
        )
        if len(pairs) < 2:
            if parameters.get("degenerate") == "zero":
                return {"value": 0.0}
            raise StatisticsOperatorError("correlation requires two aligned samples")
        left_values = [pair[0] for pair in pairs]
        right_values = [pair[1] for pair in pairs]
        left_mean = statistics.fmean(left_values)
        right_mean = statistics.fmean(right_values)
        numerator = math.fsum(
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in pairs
        )
        left_scale = math.sqrt(
            math.fsum((value - left_mean) ** 2 for value in left_values)
        )
        right_scale = math.sqrt(
            math.fsum((value - right_mean) ** 2 for value in right_values)
        )
        if left_scale == 0.0 or right_scale == 0.0:
            if parameters.get("degenerate") == "zero":
                return {"value": 0.0}
            raise StatisticsOperatorError("correlation variance is zero")
        value = numerator / (left_scale * right_scale)
        absolute = parameters.get("absolute")
        if type(absolute) is not bool:
            raise StatisticsOperatorError("absolute correlation must be boolean")
        return {"value": abs(value) if absolute else value}


def register_statistics_operators(registry: OperatorRegistry) -> None:
    registry.register(mean_definition(), MeanOperator())
    registry.register(sum_duration_definition(), SumDurationOperator())
    registry.register(ratio_definition(), RatioOperator())
    registry.register(event_aggregation_definition(), EventAggregationOperator())
    registry.register(count_definition(), CountOperator())
    registry.register(duration_definition(), DurationOperator())
    registry.register(rms_definition(), RmsOperator())
    registry.register(median_definition(), MedianOperator())
    registry.register(percentile_definition(), PercentileOperator())
    registry.register(rate_definition(), RateOperator())
    registry.register(pooled_ratio_definition(), PooledRatioOperator())
    registry.register(named_select_definition(), NamedSelectOperator())
    registry.register(correlation_definition(), CorrelationOperator())


__all__ = [
    "EventAggregationOperator",
    "CountOperator",
    "CorrelationOperator",
    "DurationOperator",
    "MeanOperator",
    "MedianOperator",
    "NamedSelectOperator",
    "PercentileOperator",
    "PooledRatioOperator",
    "RateOperator",
    "RatioOperator",
    "RmsOperator",
    "StatisticsOperatorError",
    "SumDurationOperator",
    "event_aggregation_definition",
    "mean_definition",
    "ratio_definition",
    "register_statistics_operators",
    "sum_duration_definition",
]
