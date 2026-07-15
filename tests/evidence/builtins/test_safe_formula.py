from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    NodePortReference,
    OutputRole,
    RecipeEdge,
    RecipeGraph,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScoring,
    ScoringMode,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.builtins.core import (
    SafeFormulaError,
    SafeFormulaOperator,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import execute_recipe
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import validate_recipe
from tests.evidence.runtime_support import arithmetic_recipe


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="safe-formula-test",
        recipe_version=1,
        node_id="formula",
        binding_values={},
    )


def _execute(
    formula: str,
    *,
    variables: Mapping[str, object] | None = None,
    constants: Mapping[str, JsonValue] | None = None,
) -> object:
    result = SafeFormulaOperator().execute(
        {"variables": variables or {}},
        {
            "formula": formula,
            "constants": dict(constants or {}),
        },
        _context(),
    )
    return result["value"]


def test_safe_formula_supports_bounded_arithmetic_logic_and_named_functions() -> None:
    assert (
        _execute(
            "clip(x * gain + y, lower, upper)",
            variables={"x": 2.0, "y": 1.0},
            constants={"gain": 3.0, "lower": 0.0, "upper": 5.0},
        )
        == 5.0
    )
    assert _execute("x > 2 and y <= 4", variables={"x": 3.0, "y": 4.0}) is True
    assert _execute("max(abs(x), y)", variables={"x": -3.0, "y": 2.0}) == 3.0


@pytest.mark.parametrize(
    "formula",
    [
        "__import__('os')",
        "x.__class__",
        "x[0]",
        "[item for item in x]",
        "(lambda value: value)(x)",
    ],
)
def test_safe_formula_rejects_code_escape_syntax(formula: str) -> None:
    with pytest.raises(SafeFormulaError):
        _execute(formula, variables={"x": 1.0})


def test_safe_formula_rejects_unknown_names_collisions_and_nonfinite_results() -> None:
    with pytest.raises(SafeFormulaError, match="unknown name"):
        _execute("missing + 1")
    with pytest.raises(SafeFormulaError, match="defined twice"):
        _execute("x", variables={"x": 1.0}, constants={"x": 2.0})
    with pytest.raises(SafeFormulaError):
        _execute("1 / 0")


def test_formula_many_port_uses_edge_slot_names_and_parameter_edits() -> None:
    base = arithmetic_recipe()
    x = RecipeNode(
        node_id="x",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 2.0},
    )
    y = RecipeNode(
        node_id="y",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 1.0},
    )
    formula = RecipeNode(
        node_id="formula",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        parameters={"formula": "x * gain + y", "constants": {"gain": 3.0}},
    )
    value_ref = NodePortReference(node_id="formula", port_id="value")
    recipe = base.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=(formula, y, x),
                edges=(
                    RecipeEdge(
                        edge_id="x-variable",
                        source=NodePortReference(node_id="x", port_id="value"),
                        target=NodePortReference(node_id="formula", port_id="variables"),
                        target_slot_id="x",
                    ),
                    RecipeEdge(
                        edge_id="y-variable",
                        source=NodePortReference(node_id="y", port_id="value"),
                        target=NodePortReference(node_id="formula", port_id="variables"),
                        target_slot_id="y",
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
            "scoring": RecipeScoring(
                mode=ScoringMode.ORDERED_DAU,
                input=value_ref,
                parameters={
                    "direction": "higher_is_better",
                    "desired_boundary": 10.0,
                    "adequate_boundary": 0.0,
                    "likelihood_strength": 0.9,
                },
                custom_operator_id=None,
                custom_operator_version=None,
            ),
        }
    )
    registry = OperatorRegistry()
    register_builtin_operators(registry)

    first = execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values={},
    )
    edited_formula = formula.model_copy(
        update={"parameters": {"formula": "x * gain + y", "constants": {"gain": 4.0}}}
    )
    edited = recipe.model_copy(
        update={
            "recipe_version": 2,
            "graph": RecipeGraph(nodes=(edited_formula, y, x), edges=recipe.graph.edges),
        }
    )
    second = execute_recipe(
        compile_recipe(edited, registry),
        registry,
        binding_values={},
    )

    assert first.outputs == {"primary": 7.0}
    assert second.outputs == {"primary": 9.0}


def test_recipe_validation_blocks_unsafe_formula_before_apply() -> None:
    base = arithmetic_recipe()
    formula = RecipeNode(
        node_id="formula",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        parameters={"formula": "__import__('os')", "constants": {}},
    )
    value_ref = NodePortReference(node_id="formula", port_id="value")
    assert base.scoring is not None
    candidate = base.model_copy(
        update={
            "graph": RecipeGraph(nodes=(formula,), edges=()),
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
                        "desired_boundary": 1.0,
                        "adequate_boundary": 0.0,
                        "likelihood_strength": 0.9,
                    },
                }
            ),
        }
    )
    registry = OperatorRegistry()
    register_builtin_operators(registry)

    outcome = validate_recipe(candidate, registry)

    assert outcome.disposition == "incomplete"
    assert "recipe.operator_parameters_invalid" in {item.code for item in outcome.diagnostics}
