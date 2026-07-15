"""Packaged reusable operators for editable evidence recipes."""

from pilot_assessment.evidence.builtins.core import (
    ConstantNumberOperator,
    InputBindingOperator,
    SafeFormulaError,
    SafeFormulaOperator,
    register_core_operators,
)
from pilot_assessment.evidence.builtins.events import (
    EventOperatorError,
    HoldRunOperator,
    LatencyOperator,
    MaskRunOperator,
    MovementOperator,
    PeakOperator,
    RecoveryOperator,
    ReversalOperator,
    ThresholdCrossingOperator,
    TurningPointOperator,
    register_event_operators,
)
from pilot_assessment.evidence.builtins.flight import (
    AngleOperator,
    CaptureOperator,
    DistanceOperator,
    EnvelopeMembershipOperator,
    FlightOperatorError,
    MaskSample,
    MaskSeries,
    TargetErrorOperator,
    VectorComposeOperator,
    VectorSample,
    VectorSeries,
    register_flight_operators,
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
from pilot_assessment.evidence.builtins.signal import (
    ChannelSelectOperator,
    DetrendOperator,
    DifferenceOperator,
    FieldSelectOperator,
    NumericSample,
    SignalOperatorError,
    SignalSeries,
    SmoothOperator,
    UnitConvertOperator,
    register_signal_operators,
)
from pilot_assessment.evidence.builtins.statistics import (
    CorrelationOperator,
    CountOperator,
    DurationOperator,
    EventAggregationOperator,
    MeanOperator,
    MedianOperator,
    NamedSelectOperator,
    PercentileOperator,
    PooledRatioOperator,
    RateOperator,
    RatioOperator,
    RmsOperator,
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
    register_signal_operators(registry)
    register_temporal_operators(registry)
    register_event_operators(registry)
    register_gaze_operators(registry)
    register_flight_operators(registry)
    register_statistics_operators(registry)
    register_scoring_operators(registry)

__all__ = [
    "AoiFilterOperator",
    "AngleOperator",
    "CaptureOperator",
    "ChannelSelectOperator",
    "ConstantNumberOperator",
    "CorrelationOperator",
    "CountOperator",
    "DetrendOperator",
    "DifferenceOperator",
    "DistanceOperator",
    "DwellRatioOperator",
    "DurationOperator",
    "EventAggregationOperator",
    "EventOperatorError",
    "EventRecord",
    "EventSelectOperator",
    "EventWindowOperator",
    "EnvelopeMembershipOperator",
    "FieldSelectOperator",
    "FirstMatchLatencyOperator",
    "FlightOperatorError",
    "GazeAoiIntervalsOperator",
    "GazeFrame",
    "GazeOperatorError",
    "HoldRunOperator",
    "InputBindingOperator",
    "IntervalIntersectOperator",
    "IntervalRecord",
    "LatencyOperator",
    "MaskSample",
    "MaskSeries",
    "MaskRunOperator",
    "MeanOperator",
    "MedianOperator",
    "MovementOperator",
    "NamedSelectOperator",
    "NumericSample",
    "OrderedDauScoringError",
    "OrderedDauScoringOperator",
    "PeakOperator",
    "PercentileOperator",
    "PooledRatioOperator",
    "RateOperator",
    "RecoveryOperator",
    "ReversalOperator",
    "RatioOperator",
    "RmsOperator",
    "SafeFormulaError",
    "SafeFormulaOperator",
    "SignalOperatorError",
    "SignalSeries",
    "SmoothOperator",
    "StatisticsOperatorError",
    "SumDurationOperator",
    "TargetErrorOperator",
    "TemporalOperatorError",
    "ThresholdCrossingOperator",
    "TurningPointOperator",
    "UnitConvertOperator",
    "VectorSample",
    "VectorSeries",
    "VectorComposeOperator",
    "register_builtin_operators",
    "register_core_operators",
    "register_event_operators",
    "register_flight_operators",
    "register_gaze_operators",
    "register_scoring_operators",
    "register_signal_operators",
    "register_statistics_operators",
    "register_temporal_operators",
]
