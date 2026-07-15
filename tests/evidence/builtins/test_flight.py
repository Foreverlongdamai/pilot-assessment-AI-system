from __future__ import annotations

import math

import pytest

from pilot_assessment.evidence.builtins.events import MaskRunOperator
from pilot_assessment.evidence.builtins.flight import (
    AngleOperator,
    CaptureOperator,
    DistanceOperator,
    EnvelopeMembershipOperator,
    TargetErrorOperator,
    VectorComposeOperator,
    VectorSample,
    VectorSeries,
)
from pilot_assessment.evidence.builtins.signal import NumericSample, SignalSeries
from pilot_assessment.evidence.builtins.statistics import DurationOperator, NamedSelectOperator
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="flight-smoke",
        recipe_version=1,
        node_id="flight",
        binding_values={},
    )


def test_target_distance_angle_and_envelope_use_explicit_interfaces() -> None:
    context = _context()
    actual = SignalSeries(
        "actual-altitude",
        "m",
        (
            NumericSample(0, 0.0),
            NumericSample(1_000_000_000, 2.0),
            NumericSample(2_000_000_000, 4.0),
        ),
    )
    reference = SignalSeries(
        "target-altitude",
        "m",
        (
            NumericSample(0, 0.0),
            NumericSample(2_000_000_000, 2.0),
        ),
    )
    error = TargetErrorOperator().execute(
        {"actual": actual, "reference": reference},
        {"alignment": "linear", "max_gap_ns": 2_000_000_000, "error_mode": "absolute"},
        context,
    )["value"]
    left = VectorSeries(
        "left",
        ("x", "y"),
        "m",
        (VectorSample(0, (1.0, 0.0)),),
    )
    composed = VectorComposeOperator().execute(
        {
            "components": {
                "x": SignalSeries("x", "m", (NumericSample(0, 1.0),)),
                "y": SignalSeries("y", "m", (NumericSample(0, 0.0),)),
            }
        },
        {"dimensions": ["x", "y"], "series_id": "composed", "unit": "m"},
        context,
    )["value"]
    right = VectorSeries(
        "right",
        ("x", "y"),
        "m",
        (VectorSample(0, (0.0, 1.0)),),
    )
    distance = DistanceOperator().execute({"left": left, "right": right}, {}, context)["value"]
    angle = AngleOperator().execute(
        {"left": left, "right": right},
        {"unit": "deg", "zero_vector": "error"},
        context,
    )["value"]
    envelope = EnvelopeMembershipOperator().execute(
        {"vectors": left},
        {"lower_bounds": [-1.0, -1.0], "upper_bounds": [1.0, 1.0], "inclusive": True},
        context,
    )["value"]
    inside_runs = MaskRunOperator().execute(
        {"mask": envelope},
        {
            "minimum_duration_ns": 0,
            "observation_end_ns": 1_000_000_000,
            "interval_type": "inside-envelope",
        },
        context,
    )["value"]
    inside_duration = DurationOperator().execute(
        {"intervals": inside_runs},
        {"unit": "seconds", "union_overlaps": True},
        context,
    )["value"]

    assert [sample.value for sample in error.samples] == [0.0, 1.0, 2.0]
    assert isinstance(composed, VectorSeries)
    assert composed.samples[0].values == (1.0, 0.0)
    assert distance.samples[0].value == pytest.approx(math.sqrt(2.0))
    assert angle.samples[0].value == pytest.approx(90.0)
    assert envelope.samples[0].active is True
    assert inside_duration == 1.0


def test_capture_returns_negative_evidence_when_trajectory_never_settles() -> None:
    context = _context()
    poor_error = SignalSeries(
        "poor-error",
        "m",
        (
            NumericSample(0, 5.0),
            NumericSample(1_000_000_000, 4.0),
            NumericSample(2_000_000_000, 6.0),
            NumericSample(3_000_000_000, 3.0),
        ),
    )
    capture = CaptureOperator().execute(
        {"error": poor_error},
        {
            "tolerance": 1.0,
            "hold_duration_ns": 1_000_000_000,
            "observation_start_ns": 0,
            "observation_end_ns": 4_000_000_000,
        },
        context,
    )["value"]
    latency = NamedSelectOperator().execute(
        {"values": capture},
        {"key": "capture_latency_s"},
        context,
    )["value"]

    assert dict(capture) == {
        "capture_latency_s": 4.0,
        "captured": 0.0,
        "peak_error": 6.0,
    }
    assert latency == 4.0
