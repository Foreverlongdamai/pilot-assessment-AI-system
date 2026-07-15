from __future__ import annotations

from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.evidence_recipe import (
    InputBindingKind,
    NodePortReference,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeEdge,
    RecipeGraph,
    RecipeInputBinding,
    RecipeNode,
    RecipeOutputBinding,
    TemporalSemantics,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import execute_recipe
from pilot_assessment.evidence.registry import OperatorRegistry
from tests.evidence.runtime_support import arithmetic_recipe


def _editable_formula_recipe(gain: float, version: int):
    base = arithmetic_recipe()
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
    input_node = RecipeNode(
        node_id="input",
        operator_id="input.binding",
        operator_version="0.1.0",
        input_binding_id=binding.binding_id,
        parameters={},
    )
    formula = RecipeNode(
        node_id="formula",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        parameters={
            "formula": "x * gain",
            "constants": {"gain": gain},
        },
    )
    value_ref = NodePortReference(node_id=formula.node_id, port_id="value")
    assert base.scoring is not None
    return base.model_copy(
        update={
            "recipe_version": version,
            "inputs": (binding,),
            "graph": RecipeGraph(
                nodes=(formula, input_node),
                edges=(
                    RecipeEdge(
                        edge_id="input-to-formula",
                        source=NodePortReference(
                            node_id=input_node.node_id,
                            port_id="value",
                        ),
                        target=NodePortReference(
                            node_id=formula.node_id,
                            port_id="variables",
                        ),
                        target_slot_id="x",
                    ),
                ),
            ),
            "outputs": (
                RecipeOutputBinding(
                    output_id="primary",
                    role=OutputRole.PRIMARY_VALUE,
                    name="Primary",
                    source=value_ref,
                    unit=None,
                ),
            ),
            "scoring": base.scoring.model_copy(
                update={
                    "input": value_ref,
                    "parameters": {
                        "direction": "higher_is_better",
                        "desired_boundary": 8.0,
                        "adequate_boundary": 4.0,
                        "likelihood_strength": 0.9,
                    },
                }
            ),
        }
    )


def test_parameter_edit_changes_backend_result_without_new_python_operator() -> None:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    identities_before = tuple(
        (item.operator_id, item.implementation_version)
        for item in registry.catalog()
    )

    first = execute_recipe(
        compile_recipe(_editable_formula_recipe(0.5, 1), registry),
        registry,
        binding_values={"external-number": 5.0},
    )
    second = execute_recipe(
        compile_recipe(_editable_formula_recipe(2.0, 2), registry),
        registry,
        binding_values={"external-number": 5.0},
    )

    assert first.outputs == {"primary": 2.5}
    assert first.scoring_outputs["state"] is EvidenceState.UNACCEPTABLE
    assert second.outputs == {"primary": 10.0}
    assert second.scoring_outputs["state"] is EvidenceState.DESIRED
    assert tuple(
        (item.operator_id, item.implementation_version)
        for item in registry.catalog()
    ) == identities_before
