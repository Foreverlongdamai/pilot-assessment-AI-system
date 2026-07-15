"""Reusable scalar statistics and aggregation operators."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from numbers import Real

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


class StatisticsOperatorError(ValueError):
    """Technical error in a reusable statistics operator."""


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


def register_statistics_operators(registry: OperatorRegistry) -> None:
    registry.register(mean_definition(), MeanOperator())
    registry.register(sum_duration_definition(), SumDurationOperator())
    registry.register(ratio_definition(), RatioOperator())
    registry.register(event_aggregation_definition(), EventAggregationOperator())


__all__ = [
    "EventAggregationOperator",
    "MeanOperator",
    "RatioOperator",
    "StatisticsOperatorError",
    "SumDurationOperator",
    "event_aggregation_definition",
    "mean_definition",
    "ratio_definition",
    "register_statistics_operators",
    "sum_duration_definition",
]
