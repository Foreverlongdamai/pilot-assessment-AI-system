from __future__ import annotations

import pytest

from pilot_assessment.evidence.builtins.statistics import (
    EventAggregationOperator,
    MeanOperator,
    RatioOperator,
    StatisticsOperatorError,
    SumDurationOperator,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="statistics-smoke",
        recipe_version=1,
        node_id="statistics",
        binding_values={},
    )


def test_statistics_operators_consume_named_many_inputs() -> None:
    context = _context()

    assert MeanOperator().execute(
        {"values": {"event-a": 1.0, "event-b": 3.0}},
        {},
        context,
    ) == {"value": 2.0}
    assert SumDurationOperator().execute(
        {"durations": {"look-a": 0.5, "look-b": 1.25}},
        {},
        context,
    ) == {"value": 1.75}


def test_ratio_and_event_aggregation_have_explicit_editable_policies() -> None:
    context = _context()

    assert RatioOperator().execute(
        {"numerator": 3.0, "denominator": 4.0},
        {"zero_denominator": "error"},
        context,
    ) == {"value": 0.75}
    assert RatioOperator().execute(
        {"numerator": 3.0, "denominator": 0.0},
        {"zero_denominator": "zero"},
        context,
    ) == {"value": 0.0}
    assert EventAggregationOperator().execute(
        {"values": {"event-a": 2.0, "event-b": 8.0}},
        {"mode": "worst", "direction": "higher_is_better"},
        context,
    ) == {"value": 2.0}
    assert EventAggregationOperator().execute(
        {"values": {"event-a": 2.0, "event-b": 8.0}},
        {"mode": "worst", "direction": "lower_is_better"},
        context,
    ) == {"value": 8.0}

    with pytest.raises(StatisticsOperatorError):
        RatioOperator().execute(
            {"numerator": 1.0, "denominator": 0.0},
            {"zero_denominator": "error"},
            context,
        )
