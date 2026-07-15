from __future__ import annotations

from pilot_assessment.evidence.builtins.events import (
    HoldRunOperator,
    LatencyOperator,
    MovementOperator,
    PeakOperator,
    RecoveryOperator,
    ReversalOperator,
    ThresholdCrossingOperator,
    TurningPointOperator,
)
from pilot_assessment.evidence.builtins.signal import NumericSample, SignalSeries
from pilot_assessment.evidence.builtins.statistics import (
    CountOperator,
    DurationOperator,
    RateOperator,
)
from pilot_assessment.evidence.builtins.temporal import EventRecord
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="event-smoke",
        recipe_version=1,
        node_id="event",
        binding_values={},
    )


def _control_signal() -> SignalSeries:
    return SignalSeries(
        "control",
        "%",
        (
            NumericSample(0, 0.0),
            NumericSample(1_000_000_000, 2.0),
            NumericSample(2_000_000_000, 0.0),
            NumericSample(3_000_000_000, -3.0),
            NumericSample(4_000_000_000, 0.0),
        ),
    )


def test_event_detectors_compose_without_anchor_specific_branches() -> None:
    context = _context()
    signal = _control_signal()
    crossings = ThresholdCrossingOperator().execute(
        {"signal": signal},
        {"threshold": 1.0, "direction": "rising", "event_type": "high-control"},
        context,
    )["value"]
    peak = PeakOperator().execute(
        {"signal": signal},
        {"mode": "absolute", "event_type": "peak-control"},
        context,
    )["value"]
    turning = TurningPointOperator().execute(
        {"signal": signal},
        {"minimum_delta": 0.5, "event_type": "turning-point"},
        context,
    )["value"]
    movements = MovementOperator().execute(
        {"turning_points": turning},
        {
            "minimum_amplitude": 4.0,
            "minimum_separation_ns": 0,
            "event_type": "movement",
        },
        context,
    )["value"]
    reversals = ReversalOperator().execute(
        {"turning_points": turning},
        {
            "channel_id": "stick-x",
            "support_start_t_ns": 0,
            "support_end_t_ns": 5_000_000_000,
            "minimum_amplitude": 4.0,
            "minimum_separation_ns": 0,
            "event_type": "reversal",
        },
        context,
    )["value"]

    assert tuple(event.t_ns for event in crossings) == (1_000_000_000,)
    assert peak[0].attributes["value"] == -3.0
    assert tuple(event.attributes["value"] for event in turning) == (2.0, -3.0)
    assert movements[0].attributes["amplitude"] == 5.0
    assert reversals[0].attributes["amplitude"] == 5.0


def test_hold_duration_rate_and_recovery_keep_poor_performance_as_values() -> None:
    context = _context()
    signal = SignalSeries(
        "response",
        None,
        (
            NumericSample(0, 5.0),
            NumericSample(1_000_000_000, 2.0),
            NumericSample(2_000_000_000, 0.5),
            NumericSample(3_000_000_000, 0.2),
            NumericSample(4_000_000_000, 0.1),
        ),
    )
    holds = HoldRunOperator().execute(
        {"signal": signal},
        {
            "threshold": 1.0,
            "comparison": "lte",
            "minimum_duration_ns": 2_000_000_000,
            "observation_end_ns": 5_000_000_000,
            "interval_type": "recovered",
        },
        context,
    )["value"]
    duration = DurationOperator().execute(
        {"intervals": holds},
        {"unit": "seconds", "union_overlaps": True},
        context,
    )["value"]
    count = CountOperator().execute({"values": holds}, {}, context)["value"]
    rate = RateOperator().execute(
        {"count": count, "duration": duration},
        {"duration_unit": "seconds", "zero_duration": "error"},
        context,
    )["value"]
    recovery = RecoveryOperator().execute(
        {"signal": signal, "events": (EventRecord("disturbance-1", "disturbance", 0),)},
        {
            "target": 0.0,
            "tolerance": 1.0,
            "hold_duration_ns": 2_000_000_000,
            "horizon_ns": 5_000_000_000,
        },
        context,
    )["value"]
    never_recovered = RecoveryOperator().execute(
        {
            "signal": SignalSeries(
                "bad-response",
                None,
                (
                    NumericSample(0, 10.0),
                    NumericSample(4_000_000_000, 9.0),
                ),
            ),
            "events": (EventRecord("disturbance-1", "disturbance", 0),),
        },
        {
            "target": 0.0,
            "tolerance": 1.0,
            "hold_duration_ns": 1_000_000_000,
            "horizon_ns": 5_000_000_000,
        },
        context,
    )["value"]
    response_latency = LatencyOperator().execute(
        {
            "triggers": (EventRecord("disturbance-1", "disturbance", 0),),
            "responses": (EventRecord("response-1", "response", 1_000_000_000),),
        },
        {
            "horizon_ns": 5_000_000_000,
            "no_match_policy": "horizon",
            "fixed_latency_s": 0.0,
        },
        context,
    )["value"]

    assert duration == 3.0
    assert count == 1.0
    assert rate == 1.0 / 3.0
    assert dict(recovery) == {"disturbance-1": 2.0}
    assert dict(never_recovered) == {"disturbance-1": 5.0}
    assert dict(response_latency) == {"disturbance-1": 1.0}
