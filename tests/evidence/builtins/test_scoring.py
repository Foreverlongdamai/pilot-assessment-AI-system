from __future__ import annotations

from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.evidence_recipe import (
    NodePortReference,
    OutputRole,
    RecipeGraph,
    RecipeOutputBinding,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.builtins.scoring import (
    OrderedDauScoringError,
    OrderedDauScoringOperator,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import execute_recipe
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import validate_recipe
from tests.evidence.runtime_support import arithmetic_recipe


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="scoring-test",
        recipe_version=1,
        node_id="scoring",
        binding_values={},
    )


def _parameters(direction: str = "higher_is_better") -> dict[str, object]:
    return {
        "direction": direction,
        "desired_boundary": 8.0 if direction == "higher_is_better" else 2.0,
        "adequate_boundary": 4.0 if direction == "higher_is_better" else 6.0,
        "likelihood_strength": 0.9,
    }


def test_ordered_dau_scoring_preserves_poor_performance_as_unacceptable() -> None:
    operator = OrderedDauScoringOperator()

    desired = operator.execute({"value": 10.0}, _parameters(), _context())
    adequate = operator.execute({"value": 5.0}, _parameters(), _context())
    unacceptable = operator.execute({"value": -1000.0}, _parameters(), _context())

    assert desired["state"] is EvidenceState.DESIRED
    assert desired["likelihood"].values == (0.05, 0.05, 0.9)
    assert adequate["state"] is EvidenceState.ADEQUATE
    assert adequate["likelihood"].values == (0.05, 0.9, 0.05)
    assert unacceptable["state"] is EvidenceState.UNACCEPTABLE
    assert unacceptable["likelihood"].values == (0.9, 0.05, 0.05)


def test_ordered_dau_supports_lower_is_better_and_rejects_reversed_boundaries() -> None:
    operator = OrderedDauScoringOperator()

    desired = operator.execute(
        {"value": 1.0},
        _parameters("lower_is_better"),
        _context(),
    )
    unacceptable = operator.execute(
        {"value": 1000.0},
        _parameters("lower_is_better"),
        _context(),
    )

    assert desired["state"] is EvidenceState.DESIRED
    assert unacceptable["state"] is EvidenceState.UNACCEPTABLE

    invalid = _parameters()
    invalid["desired_boundary"] = 1.0
    invalid["adequate_boundary"] = 2.0
    try:
        operator.execute({"value": 1.0}, invalid, _context())
    except OrderedDauScoringError:
        pass
    else:  # pragma: no cover - assertion branch
        raise AssertionError("reversed higher-is-better boundaries must fail")


def test_executor_runs_recipe_scoring_from_the_same_editable_parameters() -> None:
    base = arithmetic_recipe()
    constant = next(node for node in base.graph.nodes if node.node_id == "left")
    constant = constant.model_copy(update={"parameters": {"value": 5.0}})
    value_ref = NodePortReference(node_id=constant.node_id, port_id="value")
    recipe = base.model_copy(
        update={
            "graph": RecipeGraph(nodes=(constant,), edges=()),
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
                update={"input": value_ref, "parameters": _parameters()}
            ),
        }
    )
    registry = OperatorRegistry()
    register_builtin_operators(registry)

    result = execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values={},
    )

    assert result.outputs == {"primary": 5.0}
    assert result.scoring_outputs["state"] is EvidenceState.ADEQUATE

    reversed_scoring = recipe.scoring.model_copy(
        update={
            "parameters": {
                **_parameters(),
                "desired_boundary": 1.0,
                "adequate_boundary": 2.0,
            }
        }
    )
    invalid = recipe.model_copy(update={"scoring": reversed_scoring})
    outcome = validate_recipe(invalid, registry)
    assert outcome.disposition == "incomplete"
    assert "recipe.operator_parameters_invalid" in {
        item.code for item in outcome.diagnostics
    }
