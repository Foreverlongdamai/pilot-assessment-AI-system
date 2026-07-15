from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    OperatorDefinition,
    OperatorFamily,
    OperatorImplementationSource,
    OperatorPortDefinition,
    PortCardinality,
    PortType,
    TemporalSemantics,
    TraceCapability,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError


def _definition(
    operator_id: str,
    *,
    version: str = "0.1.0",
    implementation_ref: str | None = None,
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version=version,
        family=OperatorFamily.INPUT,
        name=operator_id,
        description="Test-only operator definition.",
        pseudocode=None,
        input_ports=(),
        output_ports=(
            OperatorPortDefinition(
                port_id="value",
                name="Value",
                description="Test output.",
                port_type=PortType(
                    value_type="number",
                    cardinality=PortCardinality.ONE,
                    temporal_semantics=TemporalSemantics.TIMELESS,
                    unit=None,
                ),
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        parameter_ui=(),
        trace_capability=TraceCapability.NONE,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=implementation_ref or f"builtin.{operator_id}",
    )


@dataclass(frozen=True)
class _Implementation:
    operator_id: str
    implementation_version: str = "0.1.0"
    implementation_ref: str | None = None

    def __post_init__(self) -> None:
        if self.implementation_ref is None:
            object.__setattr__(self, "implementation_ref", f"builtin.{self.operator_id}")

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del inputs, parameters, context
        return {"value": 1.0}


def test_registry_resolves_exact_definition_and_implementation() -> None:
    registry = OperatorRegistry()
    definition = _definition("constant.number")
    implementation = _Implementation("constant.number")

    registry.register(definition, implementation)

    assert registry.definition("constant.number", "0.1.0") is definition
    assert registry.implementation("constant.number", "0.1.0") is implementation


def test_registry_catalog_is_sorted_by_operator_identity() -> None:
    registry = OperatorRegistry()
    for operator_id, version in (
        ("statistics.mean", "0.2.0"),
        ("constant.number", "0.1.0"),
        ("statistics.mean", "0.1.0"),
    ):
        registry.register(
            _definition(operator_id, version=version),
            _Implementation(operator_id, implementation_version=version),
        )

    assert tuple(
        (item.operator_id, item.implementation_version) for item in registry.catalog()
    ) == (
        ("constant.number", "0.1.0"),
        ("statistics.mean", "0.1.0"),
        ("statistics.mean", "0.2.0"),
    )


def test_registry_rejects_duplicate_identity() -> None:
    registry = OperatorRegistry()
    definition = _definition("constant.number")
    implementation = _Implementation("constant.number")
    registry.register(definition, implementation)

    with pytest.raises(OperatorRegistryError, match="already registered"):
        registry.register(definition, implementation)


@pytest.mark.parametrize(
    "implementation",
    [
        _Implementation("wrong.operator"),
        _Implementation("constant.number", implementation_version="9.9.9"),
        _Implementation("constant.number", implementation_ref="builtin.wrong"),
    ],
)
def test_registry_rejects_definition_implementation_identity_mismatch(
    implementation: _Implementation,
) -> None:
    registry = OperatorRegistry()

    with pytest.raises(OperatorRegistryError, match="identity does not match"):
        registry.register(_definition("constant.number"), implementation)


def test_registry_reports_unknown_operator_without_dynamic_resolution() -> None:
    registry = OperatorRegistry()

    with pytest.raises(OperatorRegistryError, match="not registered"):
        registry.definition("unknown.operator", "0.1.0")
    with pytest.raises(OperatorRegistryError, match="not registered"):
        registry.implementation("unknown.operator", "0.1.0")
