from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    InputBindingKind,
    NodePortReference,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeGraph,
    RecipeInputBinding,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScoring,
    ScoringMode,
    TemporalSemantics,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import RecipeExecutionError, execute_recipe
from pilot_assessment.evidence.operators import OperatorExecutionContext
from tests.evidence.runtime_support import (
    RuntimeImplementation,
    arithmetic_recipe,
    arithmetic_runtime,
    definition,
    registry_with,
)


def test_executor_propagates_ports_and_captures_selected_node_trace() -> None:
    recipe = arithmetic_recipe()
    registry, implementations = arithmetic_runtime()

    result = execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values={},
        trace_node_ids={"sum"},
    )

    assert result.outputs == {"primary": 5.0}
    assert result.scoring_input == 5.0
    assert tuple(trace.node_id for trace in result.traces) == (
        "left",
        "right",
        "sum",
    )
    sum_trace = result.traces[-1]
    assert sum_trace.captured_inputs == {"left": 2.0, "right": 3.0}
    assert sum_trace.captured_outputs == {"value": 5.0}
    assert len(implementations["constant.number"].calls) == 2
    assert len(implementations["math.add"].calls) == 1


def _binding_recipe() -> tuple[EvidenceRecipe, object]:
    recipe = arithmetic_recipe()
    binding = RecipeInputBinding(
        binding_id="external-number",
        kind=InputBindingKind.STREAM,
        source_id="X",
        name="External number",
        declared_type=PortType(
            value_type="number",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.TIMELESS,
            unit=None,
        ),
        selector={},
    )
    node = RecipeNode(
        node_id="external",
        operator_id="input.binding",
        operator_version="0.1.0",
        input_binding_id=binding.binding_id,
        parameters={},
    )
    value_ref = NodePortReference(node_id=node.node_id, port_id="value")
    candidate = recipe.model_copy(
        update={
            "inputs": (binding,),
            "graph": RecipeGraph(nodes=(node,), edges=()),
            "outputs": (
                RecipeOutputBinding(
                    output_id="primary",
                    role=OutputRole.PRIMARY_VALUE,
                    name="Primary",
                    source=value_ref,
                    unit=None,
                ),
            ),
            "scoring": RecipeScoring(
                mode=ScoringMode.ORDERED_DAU,
                input=value_ref,
                parameters={},
                custom_operator_id=None,
                custom_operator_version=None,
            ),
        }
    )

    def read_binding(
        _inputs: Mapping[str, object],
        _parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        assert context.input_binding_id is not None
        return {"value": context.binding_values[context.input_binding_id]}

    implementation = RuntimeImplementation("input.binding", read_binding)
    registry = registry_with(
        (definition("input.binding"), implementation),
    )
    return candidate, registry


def test_executor_exposes_declared_external_binding_to_input_operator() -> None:
    recipe, registry = _binding_recipe()

    result = execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values={"external-number": 8.5},
    )

    assert result.outputs == {"primary": 8.5}


def test_executor_localizes_missing_binding_and_operator_failure() -> None:
    recipe, registry = _binding_recipe()
    compiled = compile_recipe(recipe, registry)

    with pytest.raises(RecipeExecutionError) as missing:
        execute_recipe(compiled, registry, binding_values={})

    assert missing.value.code == "recipe.execution.binding_value_missing"
    assert missing.value.node_id == "external"

    def explode(
        _inputs: Mapping[str, object],
        _parameters: Mapping[str, JsonValue],
        _context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        raise RuntimeError("operator exploded")

    broken_registry = registry_with(
        (
            definition(
                "constant.number",
                parameter_schema={
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            ),
            RuntimeImplementation("constant.number", explode),
        ),
        (
            definition(
                "math.add",
                inputs=(
                    definition("identity.left")
                    .output_ports[0]
                    .model_copy(update={"port_id": "left"}),
                    definition("identity.right")
                    .output_ports[0]
                    .model_copy(update={"port_id": "right"}),
                ),
            ),
            RuntimeImplementation(
                "math.add",
                lambda inputs, _parameters, _context: {
                    "value": float(inputs["left"]) + float(inputs["right"])
                },
            ),
        ),
    )

    with pytest.raises(RecipeExecutionError) as failed:
        execute_recipe(
            compile_recipe(arithmetic_recipe(), broken_registry),
            broken_registry,
            binding_values={},
        )

    assert failed.value.code == "recipe.execution.operator_failed"
    assert failed.value.node_id == "left"
    assert failed.value.operator_id == "constant.number"
