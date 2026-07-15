"""Generic target, geometry, envelope and capture operators for flight recipes."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from pydantic import JsonValue

from pilot_assessment.anchors.primitives.events import (
    CausalBooleanInterval,
    confirmed_true_runs,
)
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
from pilot_assessment.evidence.builtins.signal import (
    NumericSample,
    SignalSeries,
    signal_series,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"
_NS_PER_SECOND = 1_000_000_000.0


class FlightOperatorError(ValueError):
    """Technical error in a generic flight-geometry operator."""


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FlightOperatorError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise FlightOperatorError(f"{label} must be finite")
    return numeric


def _strict_time(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise FlightOperatorError(f"{label} must be a non-negative strict integer")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise FlightOperatorError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _number_tuple(value: object, label: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FlightOperatorError(f"{label} must be an ordered numeric array")
    return tuple(_finite(item, label) for item in value)


@dataclass(frozen=True, slots=True)
class VectorSample:
    t_ns: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        _strict_time(self.t_ns, "vector t_ns")
        if type(self.values) is not tuple or not self.values:
            raise FlightOperatorError("vector values must be a non-empty tuple")
        object.__setattr__(
            self,
            "values",
            tuple(_finite(value, "vector value") for value in self.values),
        )


@dataclass(frozen=True, slots=True)
class VectorSeries:
    series_id: str
    dimensions: tuple[str, ...]
    unit: str | None
    samples: tuple[VectorSample, ...]

    def __post_init__(self) -> None:
        _text(self.series_id, "vector series ID")
        if (
            type(self.dimensions) is not tuple
            or not self.dimensions
            or any(type(item) is not str or not item for item in self.dimensions)
            or len(self.dimensions) != len(set(self.dimensions))
        ):
            raise FlightOperatorError("vector dimensions must be unique non-empty strings")
        if self.unit is not None:
            _text(self.unit, "vector unit")
        if type(self.samples) is not tuple or any(
            not isinstance(sample, VectorSample) for sample in self.samples
        ):
            raise FlightOperatorError("vector samples must be a typed tuple")
        if any(len(sample.values) != len(self.dimensions) for sample in self.samples):
            raise FlightOperatorError("vector sample width must equal dimension count")
        times = tuple(sample.t_ns for sample in self.samples)
        if times != tuple(sorted(times)) or len(times) != len(set(times)):
            raise FlightOperatorError("vector sample times must be strictly increasing")


@dataclass(frozen=True, slots=True)
class MaskSample:
    t_ns: int
    active: bool

    def __post_init__(self) -> None:
        _strict_time(self.t_ns, "mask t_ns")
        if type(self.active) is not bool:
            raise FlightOperatorError("mask active value must be boolean")


@dataclass(frozen=True, slots=True)
class MaskSeries:
    series_id: str
    samples: tuple[MaskSample, ...]

    def __post_init__(self) -> None:
        _text(self.series_id, "mask series ID")
        if type(self.samples) is not tuple or any(
            not isinstance(sample, MaskSample) for sample in self.samples
        ):
            raise FlightOperatorError("mask samples must be a typed tuple")
        times = tuple(sample.t_ns for sample in self.samples)
        if times != tuple(sorted(times)) or len(times) != len(set(times)):
            raise FlightOperatorError("mask sample times must be strictly increasing")


def _vector_sample(value: object) -> VectorSample:
    if isinstance(value, VectorSample):
        return value
    if not isinstance(value, Mapping):
        raise FlightOperatorError("vector samples must be records")
    mapping = cast(Mapping[str, object], value)
    return VectorSample(
        t_ns=_strict_time(mapping.get("t_ns"), "vector t_ns"),
        values=_number_tuple(mapping.get("values"), "vector values"),
    )


def vector_series(value: object) -> VectorSeries:
    if isinstance(value, VectorSeries):
        return value
    if not isinstance(value, Mapping):
        raise FlightOperatorError("vector input must be a VectorSeries or mapping")
    mapping = cast(Mapping[str, object], value)
    raw_dimensions = mapping.get("dimensions")
    raw_samples = mapping.get("samples")
    if isinstance(raw_dimensions, (str, bytes)) or not isinstance(
        raw_dimensions,
        Sequence,
    ):
        raise FlightOperatorError("vector dimensions must be an ordered array")
    if isinstance(raw_samples, (str, bytes)) or not isinstance(raw_samples, Sequence):
        raise FlightOperatorError("vector samples must be an ordered array")
    dimensions = tuple(_text(item, "vector dimension") for item in raw_dimensions)
    return VectorSeries(
        series_id=_text(mapping.get("series_id"), "vector series ID"),
        dimensions=dimensions,
        unit=_optional_text(mapping.get("unit"), "vector unit"),
        samples=tuple(_vector_sample(item) for item in raw_samples),
    )


def _port(
    port_id: str,
    value_type: str,
    temporal: TemporalSemantics,
    *,
    cardinality: PortCardinality = PortCardinality.ONE,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Flight {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=cardinality,
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
        family=OperatorFamily.FLIGHT_GEOMETRY,
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


def target_error_definition() -> OperatorDefinition:
    return _definition(
        "flight.target-error",
        inputs=(
            _port("actual", "signal_series", TemporalSemantics.SAMPLED),
            _port("reference", "signal_series", TemporalSemantics.SAMPLED),
        ),
        output_type="signal_series",
        output_temporal=TemporalSemantics.SAMPLED,
        parameter_schema={
            "type": "object",
            "properties": {
                "alignment": {"type": "string", "enum": ["exact", "left_hold", "linear"]},
                "max_gap_ns": {"type": "integer", "minimum": 0},
                "error_mode": {"type": "string", "enum": ["signed", "absolute"]},
            },
            "required": ["alignment", "max_gap_ns", "error_mode"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/alignment", "Reference alignment", ParameterControlKind.SELECT),
            _ui("/max_gap_ns", "Maximum reference gap", ParameterControlKind.NUMBER, unit="ns"),
            _ui("/error_mode", "Error mode", ParameterControlKind.SELECT),
        ),
    )


def vector_compose_definition() -> OperatorDefinition:
    return _definition(
        "flight.vector-compose",
        inputs=(
            _port(
                "components",
                "signal_series",
                TemporalSemantics.SAMPLED,
                cardinality=PortCardinality.MANY,
            ),
        ),
        output_type="vector_series",
        output_temporal=TemporalSemantics.SAMPLED,
        parameter_schema={
            "type": "object",
            "properties": {
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "series_id": {"type": "string", "minLength": 1},
                "unit": {"type": ["string", "null"]},
            },
            "required": ["dimensions", "series_id", "unit"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/dimensions", "Dimensions", ParameterControlKind.TEXT),
            _ui("/series_id", "Vector series ID", ParameterControlKind.TEXT),
            _ui("/unit", "Vector unit", ParameterControlKind.TEXT),
        ),
    )


def distance_definition() -> OperatorDefinition:
    return _definition(
        "flight.distance",
        inputs=(
            _port("left", "vector_series", TemporalSemantics.SAMPLED),
            _port("right", "vector_series", TemporalSemantics.SAMPLED),
        ),
        output_type="signal_series",
        output_temporal=TemporalSemantics.SAMPLED,
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        parameter_ui=(),
    )


def angle_definition() -> OperatorDefinition:
    return _definition(
        "flight.angle",
        inputs=(
            _port("left", "vector_series", TemporalSemantics.SAMPLED),
            _port("right", "vector_series", TemporalSemantics.SAMPLED),
        ),
        output_type="signal_series",
        output_temporal=TemporalSemantics.SAMPLED,
        parameter_schema={
            "type": "object",
            "properties": {
                "unit": {"type": "string", "enum": ["deg", "rad"]},
                "zero_vector": {"type": "string", "enum": ["zero", "error"]},
            },
            "required": ["unit", "zero_vector"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/unit", "Angle unit", ParameterControlKind.SELECT),
            _ui("/zero_vector", "Zero-vector policy", ParameterControlKind.SELECT),
        ),
    )


def envelope_membership_definition() -> OperatorDefinition:
    return _definition(
        "flight.envelope-membership",
        inputs=(_port("vectors", "vector_series", TemporalSemantics.SAMPLED),),
        output_type="mask_series",
        output_temporal=TemporalSemantics.SAMPLED,
        parameter_schema={
            "type": "object",
            "properties": {
                "lower_bounds": {"type": "array", "items": {"type": "number"}},
                "upper_bounds": {"type": "array", "items": {"type": "number"}},
                "inclusive": {"type": "boolean"},
            },
            "required": ["lower_bounds", "upper_bounds", "inclusive"],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/lower_bounds", "Lower bounds", ParameterControlKind.TEXT),
            _ui("/upper_bounds", "Upper bounds", ParameterControlKind.TEXT),
            _ui("/inclusive", "Inclusive", ParameterControlKind.CHECKBOX),
        ),
    )


def capture_definition() -> OperatorDefinition:
    return _definition(
        "flight.capture",
        inputs=(_port("error", "signal_series", TemporalSemantics.SAMPLED),),
        output_type="named_numbers",
        output_temporal=TemporalSemantics.MIXED,
        parameter_schema={
            "type": "object",
            "properties": {
                "tolerance": {"type": "number", "minimum": 0.0},
                "hold_duration_ns": {"type": "integer", "minimum": 0},
                "observation_start_ns": {"type": "integer", "minimum": 0},
                "observation_end_ns": {"type": "integer", "minimum": 1},
            },
            "required": [
                "tolerance",
                "hold_duration_ns",
                "observation_start_ns",
                "observation_end_ns",
            ],
            "additionalProperties": False,
        },
        parameter_ui=(
            _ui("/tolerance", "Capture tolerance", ParameterControlKind.NUMBER),
            _ui("/hold_duration_ns", "Capture hold", ParameterControlKind.NUMBER, unit="ns"),
            _ui(
                "/observation_start_ns",
                "Observation start",
                ParameterControlKind.NUMBER,
                unit="ns",
            ),
            _ui("/observation_end_ns", "Observation end", ParameterControlKind.NUMBER, unit="ns"),
        ),
    )


def _reference_value(
    reference: SignalSeries,
    t_ns: int,
    *,
    alignment: object,
    max_gap_ns: int,
) -> float | None:
    times = tuple(sample.t_ns for sample in reference.samples)
    index = bisect_left(times, t_ns)
    if index < len(reference.samples) and reference.samples[index].t_ns == t_ns:
        return reference.samples[index].value
    if alignment == "exact":
        return None
    if alignment == "left_hold":
        left_index = bisect_right(times, t_ns) - 1
        if left_index < 0 or t_ns - times[left_index] > max_gap_ns:
            return None
        return reference.samples[left_index].value
    if alignment == "linear":
        if index == 0 or index == len(reference.samples):
            return None
        left = reference.samples[index - 1]
        right = reference.samples[index]
        gap = right.t_ns - left.t_ns
        if gap > max_gap_ns:
            return None
        ratio = (t_ns - left.t_ns) / gap
        return left.value + ratio * (right.value - left.value)
    raise FlightOperatorError("reference alignment is not supported")


class TargetErrorOperator:
    operator_id = "flight.target-error"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.target-error"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        actual = signal_series(inputs.get("actual"))
        reference = signal_series(inputs.get("reference"))
        max_gap = _strict_time(parameters.get("max_gap_ns"), "max_gap_ns")
        mode = parameters.get("error_mode")
        samples: list[NumericSample] = []
        for sample in actual.samples:
            target = _reference_value(
                reference,
                sample.t_ns,
                alignment=parameters.get("alignment"),
                max_gap_ns=max_gap,
            )
            if target is None:
                continue
            error = sample.value - target
            if mode == "absolute":
                error = abs(error)
            elif mode != "signed":
                raise FlightOperatorError("error mode is not supported")
            samples.append(NumericSample(sample.t_ns, error))
        return {
            "value": SignalSeries(
                series_id=f"{actual.series_id}-error",
                unit=actual.unit,
                samples=tuple(samples),
            )
        }


class VectorComposeOperator:
    operator_id = "flight.vector-compose"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.vector-compose"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        components = inputs.get("components")
        if not isinstance(components, Mapping):
            raise FlightOperatorError("vector components must be named incoming slots")
        typed_components = cast(Mapping[str, object], components)
        raw_dimensions = parameters.get("dimensions")
        if isinstance(raw_dimensions, (str, bytes)) or not isinstance(
            raw_dimensions,
            Sequence,
        ):
            raise FlightOperatorError("vector dimensions must be an ordered array")
        dimensions = tuple(_text(item, "vector dimension") for item in raw_dimensions)
        if len(dimensions) != len(set(dimensions)):
            raise FlightOperatorError("vector dimensions must be unique")
        if any(dimension not in typed_components for dimension in dimensions):
            raise FlightOperatorError("every vector dimension requires one named input slot")
        series = tuple(signal_series(typed_components[dimension]) for dimension in dimensions)
        unit = _optional_text(parameters.get("unit"), "vector unit")
        if any(item.unit != unit for item in series):
            raise FlightOperatorError("component units must equal the declared vector unit")
        by_time = tuple({sample.t_ns: sample.value for sample in item.samples} for item in series)
        common_times = sorted(set.intersection(*(set(values) for values in by_time)))
        return {
            "value": VectorSeries(
                series_id=_text(parameters.get("series_id"), "vector series ID"),
                dimensions=dimensions,
                unit=unit,
                samples=tuple(
                    VectorSample(
                        t_ns,
                        tuple(values[t_ns] for values in by_time),
                    )
                    for t_ns in common_times
                ),
            )
        }


def _paired_vectors(
    left: VectorSeries,
    right: VectorSeries,
) -> tuple[tuple[VectorSample, VectorSample], ...]:
    if left.dimensions != right.dimensions:
        raise FlightOperatorError("vector dimensions must match")
    if left.unit != right.unit:
        raise FlightOperatorError("vector units must match")
    right_by_time = {sample.t_ns: sample for sample in right.samples}
    return tuple(
        (sample, right_by_time[sample.t_ns])
        for sample in left.samples
        if sample.t_ns in right_by_time
    )


class DistanceOperator:
    operator_id = "flight.distance"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.distance"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del parameters, context
        left = vector_series(inputs.get("left"))
        right = vector_series(inputs.get("right"))
        return {
            "value": SignalSeries(
                series_id=f"{left.series_id}-to-{right.series_id}-distance",
                unit=left.unit,
                samples=tuple(
                    NumericSample(
                        left_sample.t_ns,
                        math.dist(left_sample.values, right_sample.values),
                    )
                    for left_sample, right_sample in _paired_vectors(left, right)
                ),
            )
        }


class AngleOperator:
    operator_id = "flight.angle"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.angle"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        left = vector_series(inputs.get("left"))
        right = vector_series(inputs.get("right"))
        unit = parameters.get("unit")
        zero_policy = parameters.get("zero_vector")
        samples: list[NumericSample] = []
        for left_sample, right_sample in _paired_vectors(left, right):
            left_norm = math.hypot(*left_sample.values)
            right_norm = math.hypot(*right_sample.values)
            if left_norm == 0.0 or right_norm == 0.0:
                if zero_policy == "zero":
                    angle = 0.0
                elif zero_policy == "error":
                    raise FlightOperatorError("angle is undefined for a zero vector")
                else:
                    raise FlightOperatorError("zero-vector policy is not supported")
            else:
                cosine = math.fsum(
                    left_value * right_value
                    for left_value, right_value in zip(
                        left_sample.values,
                        right_sample.values,
                        strict=True,
                    )
                ) / (left_norm * right_norm)
                angle = math.acos(max(-1.0, min(1.0, cosine)))
            if unit == "deg":
                angle = math.degrees(angle)
            elif unit != "rad":
                raise FlightOperatorError("angle unit is not supported")
            samples.append(NumericSample(left_sample.t_ns, angle))
        return {
            "value": SignalSeries(
                series_id=f"{left.series_id}-to-{right.series_id}-angle",
                unit=cast(str, unit),
                samples=tuple(samples),
            )
        }


class EnvelopeMembershipOperator:
    operator_id = "flight.envelope-membership"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.envelope-membership"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        vectors = vector_series(inputs.get("vectors"))
        lower = _number_tuple(parameters.get("lower_bounds"), "lower bounds")
        upper = _number_tuple(parameters.get("upper_bounds"), "upper bounds")
        if len(lower) != len(vectors.dimensions) or len(upper) != len(vectors.dimensions):
            raise FlightOperatorError("envelope bound width must equal vector dimension count")
        if any(high < low for low, high in zip(lower, upper, strict=True)):
            raise FlightOperatorError("envelope upper bounds cannot be below lower bounds")
        inclusive = parameters.get("inclusive")
        if type(inclusive) is not bool:
            raise FlightOperatorError("envelope inclusive must be boolean")
        return {
            "value": MaskSeries(
                series_id=f"{vectors.series_id}-inside-envelope",
                samples=tuple(
                    MaskSample(
                        sample.t_ns,
                        all(
                            (low <= value <= high) if inclusive else (low < value < high)
                            for value, low, high in zip(
                                sample.values,
                                lower,
                                upper,
                                strict=True,
                            )
                        ),
                    )
                    for sample in vectors.samples
                ),
            )
        }


class CaptureOperator:
    operator_id = "flight.capture"
    implementation_version = _VERSION
    implementation_ref = "builtin.flight.capture"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        error = signal_series(inputs.get("error"))
        if not error.samples:
            raise FlightOperatorError("capture requires at least one error sample")
        tolerance = _finite(parameters.get("tolerance"), "tolerance")
        if tolerance < 0.0:
            raise FlightOperatorError("capture tolerance must be non-negative")
        hold = _strict_time(parameters.get("hold_duration_ns"), "hold_duration_ns")
        start = _strict_time(parameters.get("observation_start_ns"), "observation_start_ns")
        end = _strict_time(parameters.get("observation_end_ns"), "observation_end_ns")
        if end <= start:
            raise FlightOperatorError("capture observation must have positive duration")
        selected = tuple(sample for sample in error.samples if start <= sample.t_ns <= end)
        if not selected:
            raise FlightOperatorError("capture observation contains no error samples")
        intervals = tuple(
            CausalBooleanInterval(
                start_t_ns=sample.t_ns,
                end_t_ns=(selected[index + 1].t_ns if index + 1 < len(selected) else end),
                source_row_id=index,
                active=abs(sample.value) <= tolerance,
            )
            for index, sample in enumerate(selected)
            if (selected[index + 1].t_ns if index + 1 < len(selected) else end) >= sample.t_ns
        )
        runs = confirmed_true_runs(intervals, minimum_duration_ns=hold)
        captured = bool(runs)
        latency = (
            (runs[0].onset_t_ns - start) / _NS_PER_SECOND
            if captured
            else (end - start) / _NS_PER_SECOND
        )
        return {
            "value": MappingProxyType(
                {
                    "capture_latency_s": latency,
                    "captured": 1.0 if captured else 0.0,
                    "peak_error": max(abs(sample.value) for sample in selected),
                }
            )
        }


def register_flight_operators(registry: OperatorRegistry) -> None:
    registry.register(target_error_definition(), TargetErrorOperator())
    registry.register(vector_compose_definition(), VectorComposeOperator())
    registry.register(distance_definition(), DistanceOperator())
    registry.register(angle_definition(), AngleOperator())
    registry.register(envelope_membership_definition(), EnvelopeMembershipOperator())
    registry.register(capture_definition(), CaptureOperator())


__all__ = [
    "AngleOperator",
    "CaptureOperator",
    "DistanceOperator",
    "EnvelopeMembershipOperator",
    "FlightOperatorError",
    "MaskSample",
    "MaskSeries",
    "TargetErrorOperator",
    "VectorSample",
    "VectorComposeOperator",
    "VectorSeries",
    "register_flight_operators",
    "vector_series",
]
