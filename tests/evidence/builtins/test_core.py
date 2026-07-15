from __future__ import annotations

from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.builtins.core import (
    ConstantNumberOperator,
    InputBindingOperator,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry


def test_core_input_and_constant_operators_use_only_canonical_node_data() -> None:
    context = OperatorExecutionContext(
        recipe_id="core-smoke",
        recipe_version=1,
        node_id="input",
        binding_values={"flight-value": 12.5},
        input_binding_id="flight-value",
    )

    assert InputBindingOperator().execute({}, {}, context) == {"value": 12.5}
    assert ConstantNumberOperator().execute(
        {},
        {"value": -4.0},
        context,
    ) == {"value": -4.0}


def test_builtin_catalog_is_generic_and_deterministically_ordered() -> None:
    registry = OperatorRegistry()
    register_builtin_operators(registry)

    identities = tuple(
        (item.operator_id, item.implementation_version)
        for item in registry.catalog()
    )

    assert identities == tuple(sorted(identities))
    assert {
        "input.binding",
        "constant.number",
        "composition.safe-formula",
        "statistics.mean",
        "statistics.sum-duration",
        "statistics.ratio",
        "aggregation.event",
        "scoring.ordered-dau",
    } == {operator_id for operator_id, _ in identities}
