from __future__ import annotations

import pytest

from pilot_assessment.contracts.evidence_recipe import RecipeGraph
from pilot_assessment.evidence.compiler import RecipeCompilationError, compile_recipe
from tests.evidence.runtime_support import arithmetic_recipe, arithmetic_runtime


def test_compiler_uses_stable_topological_order_and_resolved_definitions() -> None:
    recipe = arithmetic_recipe()
    registry, _ = arithmetic_runtime()

    compiled = compile_recipe(recipe, registry)

    assert tuple(node.node.node_id for node in compiled.nodes) == (
        "left",
        "right",
        "sum",
    )
    assert tuple(node.definition.operator_id for node in compiled.nodes) == (
        "constant.number",
        "constant.number",
        "math.add",
    )
    assert compiled.recipe is recipe


def test_compiler_rejects_incomplete_recipe_without_calling_operators() -> None:
    recipe = arithmetic_recipe()
    registry, implementations = arithmetic_runtime()
    incomplete = recipe.model_copy(
        update={
            "graph": RecipeGraph(nodes=recipe.graph.nodes, edges=()),
            "outputs": (),
        }
    )

    with pytest.raises(RecipeCompilationError) as captured:
        compile_recipe(incomplete, registry)

    assert captured.value.outcome.disposition == "incomplete"
    assert {
        "recipe.primary_output_missing",
        "recipe.required_input_missing",
    } <= {item.code for item in captured.value.outcome.diagnostics}
    assert all(not implementation.calls for implementation in implementations.values())
