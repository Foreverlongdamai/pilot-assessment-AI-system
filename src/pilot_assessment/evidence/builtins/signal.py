"""Generic sampled-signal operators shared by flight, control, EEG and ECG recipes."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
_NS_PER_SECOND = 1_000_000_000.0


class SignalOperatorError(ValueError):
    """Technical error in a generic sampled-signal operator."""


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SignalOperatorError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise SignalOperatorError(f"{label} must be finite")
    return numeric


def _strict_time(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SignalOperatorError(f"{label} must be a non-negative strict integer")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise SignalOperatorError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


@dataclass(frozen=True, slots=True)
class NumericSample:
    t_ns: int
    value: float

    def __post_init__(self) -> None:
        _strict_time(self.t_ns, "sample t_ns")
        object.__setattr__(self, "value", _finite(self.value, "sample value"))


@dataclass(frozen=True, slots=True)
class SignalSeries:
    series_id: str
    unit: str | None
    samples: tuple[NumericSample, ...]

    def __post_init__(self) -> None:
        _text(self.series_id, "series ID")
        if self.unit is not None:
            _text(self.unit, "series unit")
        if type(self.samples) is not tuple or any(
            not isinstance(sample, NumericSample) for sample in self.samples
        ):
            raise SignalOperatorError("signal samples must be a typed tuple")
        times = tuple(sample.t_ns for sample in self.samples)
        if times != tuple(sorted(times)) or len(times) != len(set(times)):
            raise SignalOperatorError("signal sample times must be strictly increasing")


def _sample(value: object) -> NumericSample:
    if isinstance(value, NumericSample):
        return value
    if not isinstance(value, Mapping):
        raise SignalOperatorError("signal samples must be records")
    mapping = cast(Mapping[str, object], value)
    return NumericSample(
        t_ns=_strict_time(mapping.get("t_ns"), "sample t_ns"),
        value=_finite(mapping.get("value"), "sample value"),
    )


def signal_series(value: object) -> SignalSeries:
    """Normalize the small runtime interface accepted by all signal operators."""

    if isinstance(value, SignalSeries):
        return value
    if not isinstance(value, Mapping):
        raise SignalOperatorError("signal input must be a SignalSeries or mapping")
    mapping = cast(Mapping[str, object], value)
    raw_samples = mapping.get("samples")
    if isinstance(raw_samples, (str, bytes)) or not isinstance(raw_samples, Sequence):
        raise SignalOperatorError("signal samples must be an ordered sequence")
    return SignalSeries(
        series_id=_text(mapping.get("series_id"), "series ID"),
        unit=_optional_text(mapping.get("unit"), "series unit"),
        samples=tuple(_sample(item) for item in raw_samples),
    )


def _port(port_id: str, value_type: str) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Signal {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.SAMPLED,
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
    parameter_schema: dict[str, JsonValue],
    parameter_ui: tuple[ParameterUiDefinition, ...],
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version=_VERSION,
        family=OperatorFamily.SIGNAL,
        name=operator_id.replace(".", " ").replace("-", " ").title(),
        description=f"Reusable editable {operator_id} operator.",
        pseudocode=None,
        input_ports=inputs,
        output_ports=(_port("value", output_type),),
        parameter_schema=parameter_schema,
        parameter_ui=parameter_ui,
        trace_capability=TraceCapability.FULL,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


def field_select_definition() -> OperatorDefinition:
    return _definition(
        "signal.field-select",
        inputs=(_port("records", "record_collection"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {
                "time_field": {"type": "string", "minLength": 1},
                "value_field": {"type": "string", "minLength": 1},
                "series_id": {"type": "string", "minLength": 1},
                "unit": {"type": ["string", "null"]},
            },
            "required": ["time_field", "value_field", "series_id", "unit"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/time_field", "Time field", ParameterControlKind.TEXT),
            _ui("/value_field", "Value field", ParameterControlKind.TEXT),
            _ui("/series_id", "Series ID", ParameterControlKind.TEXT),
            _ui("/unit", "Unit", ParameterControlKind.TEXT),
        ),
    )


def channel_select_definition() -> OperatorDefinition:
    return _definition(
        "signal.channel-select",
        inputs=(_port("channels", "signal_bundle"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {"channel_id": {"type": "string", "minLength": 1}},
            "required": ["channel_id"],
            "additionalProperties": False,
        },
        parameter_ui=(_ui("/channel_id", "Channel", ParameterControlKind.TEXT),),
    )


def unit_convert_definition() -> OperatorDefinition:
    return _definition(
        "signal.unit-convert",
        inputs=(_port("signal", "signal_series"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {
                "scale": {"type": "number"},
                "offset": {"type": "number"},
                "target_unit": {"type": ["string", "null"]},
            },
            "required": ["scale", "offset", "target_unit"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/scale", "Scale", ParameterControlKind.NUMBER),
            _ui("/offset", "Offset", ParameterControlKind.NUMBER),
            _ui("/target_unit", "Target unit", ParameterControlKind.TEXT),
        ),
    )


def difference_definition() -> OperatorDefinition:
    return _definition(
        "signal.difference",
        inputs=(_port("signal", "signal_series"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["delta", "rate_per_second"]},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
        parameter_ui=(_ui("/mode", "Difference mode", ParameterControlKind.SELECT),),
    )


def smooth_definition() -> OperatorDefinition:
    return _definition(
        "signal.smooth",
        inputs=(_port("signal", "signal_series"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {
                "window_samples": {"type": "integer", "minimum": 1},
                "method": {"type": "string", "enum": ["mean", "median"]},
            },
            "required": ["window_samples", "method"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/window_samples", "Window samples", ParameterControlKind.NUMBER),
            _ui("/method", "Method", ParameterControlKind.SELECT),
        ),
    )


def detrend_definition() -> OperatorDefinition:
    return _definition(
        "signal.detrend",
        inputs=(_port("signal", "signal_series"),),
        output_type="signal_series",
        parameter_schema={
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["mean", "linear"]},
            },
            "required": ["method"],
            "additionalProperties": False,
        },
        parameter_ui=(_ui("/method", "Detrend method", ParameterControlKind.SELECT),),
    )


class FieldSelectOperator:
    operator_id = "signal.field-select"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.field-select"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        raw_records = inputs.get("records")
        if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Sequence):
            raise SignalOperatorError("records must be an ordered sequence")
        time_field = _text(parameters.get("time_field"), "time_field")
        value_field = _text(parameters.get("value_field"), "value_field")
        samples: list[NumericSample] = []
        for item in raw_records:
            if not isinstance(item, Mapping):
                raise SignalOperatorError("each signal record must be a mapping")
            record = cast(Mapping[str, object], item)
            samples.append(
                NumericSample(
                    _strict_time(record.get(time_field), time_field),
                    _finite(record.get(value_field), value_field),
                )
            )
        return {
            "value": SignalSeries(
                series_id=_text(parameters.get("series_id"), "series_id"),
                unit=_optional_text(parameters.get("unit"), "unit"),
                samples=tuple(samples),
            )
        }


class ChannelSelectOperator:
    operator_id = "signal.channel-select"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.channel-select"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        channels = inputs.get("channels")
        if not isinstance(channels, Mapping):
            raise SignalOperatorError("channels must be a signal bundle mapping")
        typed_channels = cast(Mapping[str, object], channels)
        channel_id = _text(parameters.get("channel_id"), "channel_id")
        if channel_id not in typed_channels:
            raise SignalOperatorError(f"channel {channel_id!r} is not present")
        return {"value": signal_series(typed_channels[channel_id])}


class UnitConvertOperator:
    operator_id = "signal.unit-convert"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.unit-convert"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        source = signal_series(inputs.get("signal"))
        scale = _finite(parameters.get("scale"), "scale")
        offset = _finite(parameters.get("offset"), "offset")
        target_unit = _optional_text(parameters.get("target_unit"), "target_unit")
        return {
            "value": SignalSeries(
                series_id=source.series_id,
                unit=target_unit,
                samples=tuple(
                    NumericSample(sample.t_ns, sample.value * scale + offset)
                    for sample in source.samples
                ),
            )
        }


class DifferenceOperator:
    operator_id = "signal.difference"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.difference"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        source = signal_series(inputs.get("signal"))
        mode = parameters.get("mode")
        samples: list[NumericSample] = []
        for previous, current in zip(source.samples, source.samples[1:], strict=False):
            delta = current.value - previous.value
            if mode == "rate_per_second":
                delta /= (current.t_ns - previous.t_ns) / _NS_PER_SECOND
            elif mode != "delta":
                raise SignalOperatorError("difference mode is not supported")
            samples.append(NumericSample(current.t_ns, delta))
        unit = f"{source.unit}/s" if mode == "rate_per_second" and source.unit else source.unit
        return {
            "value": SignalSeries(
                series_id=f"{source.series_id}-difference",
                unit=unit,
                samples=tuple(samples),
            )
        }


class SmoothOperator:
    operator_id = "signal.smooth"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.smooth"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        source = signal_series(inputs.get("signal"))
        window = parameters.get("window_samples")
        if type(window) is not int or window < 1:
            raise SignalOperatorError("window_samples must be a positive strict integer")
        method = parameters.get("method")
        samples: list[NumericSample] = []
        for index, sample in enumerate(source.samples):
            values = [item.value for item in source.samples[max(0, index - window + 1) : index + 1]]
            if method == "mean":
                value = statistics.fmean(values)
            elif method == "median":
                value = statistics.median(values)
            else:
                raise SignalOperatorError("smooth method is not supported")
            samples.append(NumericSample(sample.t_ns, value))
        return {
            "value": SignalSeries(
                series_id=f"{source.series_id}-smoothed",
                unit=source.unit,
                samples=tuple(samples),
            )
        }


class DetrendOperator:
    operator_id = "signal.detrend"
    implementation_version = _VERSION
    implementation_ref = "builtin.signal.detrend"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        source = signal_series(inputs.get("signal"))
        if not source.samples:
            return {"value": source}
        values = [sample.value for sample in source.samples]
        method = parameters.get("method")
        if method == "mean" or len(source.samples) < 2:
            center = statistics.fmean(values)
            trend = [center] * len(values)
        elif method == "linear":
            origin = source.samples[0].t_ns
            times = [(sample.t_ns - origin) / _NS_PER_SECOND for sample in source.samples]
            mean_t = statistics.fmean(times)
            mean_v = statistics.fmean(values)
            denominator = math.fsum((value - mean_t) ** 2 for value in times)
            slope = (
                0.0
                if denominator == 0.0
                else math.fsum(
                    (time - mean_t) * (value - mean_v)
                    for time, value in zip(times, values, strict=True)
                )
                / denominator
            )
            intercept = mean_v - slope * mean_t
            trend = [intercept + slope * time for time in times]
        else:
            raise SignalOperatorError("detrend method is not supported")
        return {
            "value": SignalSeries(
                series_id=f"{source.series_id}-detrended",
                unit=source.unit,
                samples=tuple(
                    NumericSample(sample.t_ns, sample.value - trend[index])
                    for index, sample in enumerate(source.samples)
                ),
            )
        }


def register_signal_operators(registry: OperatorRegistry) -> None:
    registry.register(field_select_definition(), FieldSelectOperator())
    registry.register(channel_select_definition(), ChannelSelectOperator())
    registry.register(unit_convert_definition(), UnitConvertOperator())
    registry.register(difference_definition(), DifferenceOperator())
    registry.register(smooth_definition(), SmoothOperator())
    registry.register(detrend_definition(), DetrendOperator())


__all__ = [
    "ChannelSelectOperator",
    "DetrendOperator",
    "DifferenceOperator",
    "FieldSelectOperator",
    "NumericSample",
    "SignalOperatorError",
    "SignalSeries",
    "SmoothOperator",
    "UnitConvertOperator",
    "register_signal_operators",
    "signal_series",
]
