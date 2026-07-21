"""Copyable, engineering-only operator extension example.

This file is not imported by the product and is not part of the starter assessment model.  Copy it
to ``backend/src/pilot_assessment/evidence/extensions`` and register it explicitly before use.
"""

from __future__ import annotations

import math
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

OPERATOR_ID = "extension.example.scalar-offset"
IMPLEMENTATION_VERSION = "0.1.0"
IMPLEMENTATION_REF = "extension.example.scalar-offset"


def _number_port(port_id: str) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.title(),
        description=f"Numeric {port_id} value.",
        port_type=PortType(
            value_type="number",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.TIMELESS,
            unit=None,
        ),
    )


def operator_definition() -> OperatorDefinition:
    """Return metadata used by validation, the catalog, and the generic WinUI form."""

    return OperatorDefinition(
        operator_id=OPERATOR_ID,
        implementation_version=IMPLEMENTATION_VERSION,
        family=OperatorFamily.COMPOSITION,
        name="Example scalar offset",
        description="Adds one editable offset to a numeric input.",
        pseudocode="output = input + offset",
        input_ports=(_number_port("value"),),
        output_ports=(_number_port("value"),),
        parameter_schema={
            "type": "object",
            "properties": {
                "offset": {
                    "type": "number",
                    "description": "Finite value added to the input.",
                }
            },
            "required": ["offset"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/offset",
                label="Offset",
                group_id="calculation",
                control=ParameterControlKind.NUMBER,
                help_text="Finite value added to the input.",
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.TRUSTED_EXTENSION,
        implementation_ref=IMPLEMENTATION_REF,
    )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


class ExampleScalarOffsetOperator:
    operator_id = OPERATOR_ID
    implementation_version = IMPLEMENTATION_VERSION
    implementation_ref = IMPLEMENTATION_REF

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        value = _finite_number(inputs.get("value"), "value")
        offset = _finite_number(parameters.get("offset"), "offset")
        return {"value": value + offset}


def register_example_scalar_offset(registry: OperatorRegistry) -> None:
    registry.register(operator_definition(), ExampleScalarOffsetOperator())


__all__ = [
    "ExampleScalarOffsetOperator",
    "register_example_scalar_offset",
    "operator_definition",
]
