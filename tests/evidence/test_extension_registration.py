from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue

import pilot_assessment.runtime.system_application as system_application_module
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
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.extensions import register_extension_operators
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError
from pilot_assessment.runtime import SystemApplication

_OPERATOR_ID = "extension.test.scalar-offset"
_VERSION = "0.1.0"
_IMPLEMENTATION_REF = "extension.test.scalar-offset"


def _number_port(port_id: str) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.title(),
        description=f"Test-only {port_id} port.",
        port_type=PortType(
            value_type="number",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.TIMELESS,
            unit=None,
        ),
    )


def _definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=_OPERATOR_ID,
        implementation_version=_VERSION,
        family=OperatorFamily.COMPOSITION,
        name="Test scalar offset",
        description="Adds an editable offset for an engineering extension-path test.",
        pseudocode="output = input + offset",
        input_ports=(_number_port("value"),),
        output_ports=(_number_port("value"),),
        parameter_schema={
            "type": "object",
            "properties": {"offset": {"type": "number"}},
            "required": ["offset"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/offset",
                label="Offset",
                group_id="calculation",
                control=ParameterControlKind.NUMBER,
                help_text="Test-only scalar offset.",
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.TRUSTED_EXTENSION,
        implementation_ref=_IMPLEMENTATION_REF,
    )


class _ScalarOffsetOperator:
    operator_id = _OPERATOR_ID
    implementation_version = _VERSION
    implementation_ref = _IMPLEMENTATION_REF

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        return {"value": float(inputs["value"]) + float(parameters["offset"])}


def _register_test_extension(registry: OperatorRegistry) -> None:
    registry.register(_definition(), _ScalarOffsetOperator())


def test_clean_extension_entry_is_explicit_and_does_not_change_builtin_catalog() -> None:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    builtin_catalog = registry.catalog()

    register_extension_operators(registry)

    assert registry.catalog() == builtin_catalog


def test_extension_uses_same_registry_and_duplicate_identity_fails_clearly() -> None:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    _register_test_extension(registry)

    definition = registry.definition(_OPERATOR_ID, _VERSION)
    implementation = registry.implementation(_OPERATOR_ID, _VERSION)
    result = implementation.execute(
        {"value": 2.0},
        {"offset": 0.75},
        OperatorExecutionContext(
            recipe_id="recipe.extension-test",
            recipe_version=1,
            node_id="offset",
            binding_values={},
        ),
    )

    assert definition.implementation_source is OperatorImplementationSource.TRUSTED_EXTENSION
    assert result == {"value": 2.75}
    with pytest.raises(OperatorRegistryError, match="is already registered"):
        _register_test_extension(registry)


def test_system_composition_registers_extensions_before_freezing_operator_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        system_application_module,
        "register_extension_operators",
        _register_test_extension,
    )

    application = SystemApplication.open_or_create(
        tmp_path / "system",
        model_library_id="model-library.extension-test",
    )
    try:
        assert application.operator_registry.definition(_OPERATOR_ID, _VERSION) == _definition()
        assert application.source_provenance.loaded_identity.operator_catalog.operator_count == 46
    finally:
        application.close()
