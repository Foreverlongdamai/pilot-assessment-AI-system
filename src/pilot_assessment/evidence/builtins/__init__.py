"""Packaged reusable operators for editable evidence recipes."""

from pilot_assessment.evidence.builtins.core import (
    ConstantNumberOperator,
    InputBindingOperator,
    SafeFormulaError,
    SafeFormulaOperator,
    register_core_operators,
)
from pilot_assessment.evidence.builtins.gaze import (
    AoiFilterOperator,
    DwellRatioOperator,
    FirstMatchLatencyOperator,
    GazeAoiIntervalsOperator,
    GazeFrame,
    GazeOperatorError,
    register_gaze_operators,
)
from pilot_assessment.evidence.builtins.scoring import (
    OrderedDauScoringError,
    OrderedDauScoringOperator,
    register_scoring_operators,
)
from pilot_assessment.evidence.builtins.statistics import (
    EventAggregationOperator,
    MeanOperator,
    RatioOperator,
    StatisticsOperatorError,
    SumDurationOperator,
    register_statistics_operators,
)
from pilot_assessment.evidence.builtins.temporal import (
    EventRecord,
    EventSelectOperator,
    EventWindowOperator,
    IntervalIntersectOperator,
    IntervalRecord,
    TemporalOperatorError,
    register_temporal_operators,
)
from pilot_assessment.evidence.registry import OperatorRegistry


def register_builtin_operators(registry: OperatorRegistry) -> None:
    """Register the currently packaged built-in operator families."""

    register_core_operators(registry)
    register_temporal_operators(registry)
    register_gaze_operators(registry)
    register_statistics_operators(registry)
    register_scoring_operators(registry)

__all__ = [
    "AoiFilterOperator",
    "ConstantNumberOperator",
    "DwellRatioOperator",
    "EventAggregationOperator",
    "EventRecord",
    "EventSelectOperator",
    "EventWindowOperator",
    "FirstMatchLatencyOperator",
    "GazeAoiIntervalsOperator",
    "GazeFrame",
    "GazeOperatorError",
    "InputBindingOperator",
    "IntervalIntersectOperator",
    "IntervalRecord",
    "MeanOperator",
    "OrderedDauScoringError",
    "OrderedDauScoringOperator",
    "RatioOperator",
    "SafeFormulaError",
    "SafeFormulaOperator",
    "StatisticsOperatorError",
    "SumDurationOperator",
    "TemporalOperatorError",
    "register_builtin_operators",
    "register_core_operators",
    "register_gaze_operators",
    "register_scoring_operators",
    "register_statistics_operators",
    "register_temporal_operators",
]
