from __future__ import annotations

import math

import pytest

from pilot_assessment.evidence.builtins.signal import (
    ChannelSelectOperator,
    DetrendOperator,
    DifferenceOperator,
    FieldSelectOperator,
    SignalSeries,
    SmoothOperator,
    UnitConvertOperator,
)
from pilot_assessment.evidence.builtins.statistics import (
    CountOperator,
    MedianOperator,
    PercentileOperator,
    PooledRatioOperator,
    RmsOperator,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="signal-smoke",
        recipe_version=1,
        node_id="signal",
        binding_values={},
    )


def test_field_channel_and_transform_operators_share_one_signal_interface() -> None:
    context = _context()
    records = (
        {"t_ns": 0, "ecg_mv": 1.0},
        {"t_ns": 1_000_000_000, "ecg_mv": 100.0},
        {"t_ns": 2_000_000_000, "ecg_mv": -50.0},
    )
    selected = FieldSelectOperator().execute(
        {"records": records},
        {
            "time_field": "t_ns",
            "value_field": "ecg_mv",
            "series_id": "ecg",
            "unit": "mV",
        },
        context,
    )["value"]
    assert isinstance(selected, SignalSeries)

    channel = ChannelSelectOperator().execute(
        {"channels": {"ECG": selected}},
        {"channel_id": "ECG"},
        context,
    )["value"]
    converted = UnitConvertOperator().execute(
        {"signal": channel},
        {"scale": 0.001, "offset": 0.0, "target_unit": "V"},
        context,
    )["value"]
    smoothed = SmoothOperator().execute(
        {"signal": selected},
        {"window_samples": 2, "method": "mean"},
        context,
    )["value"]
    difference = DifferenceOperator().execute(
        {"signal": selected},
        {"mode": "rate_per_second"},
        context,
    )["value"]
    detrended = DetrendOperator().execute(
        {"signal": selected},
        {"method": "mean"},
        context,
    )["value"]

    assert [sample.value for sample in converted.samples] == [0.001, 0.1, -0.05]
    assert [sample.value for sample in smoothed.samples] == [1.0, 50.5, 25.0]
    assert [sample.value for sample in difference.samples] == [99.0, -150.0]
    assert math.fsum(sample.value for sample in detrended.samples) == pytest.approx(0.0)


def test_statistics_include_large_finite_physiology_values_without_quality_filtering() -> None:
    context = _context()
    selected = FieldSelectOperator().execute(
        {
            "records": (
                {"t_ns": 0, "eeg": 1.0},
                {"t_ns": 1, "eeg": 100.0},
                {"t_ns": 2, "eeg": -50.0},
            )
        },
        {"time_field": "t_ns", "value_field": "eeg", "series_id": "eeg", "unit": "uV"},
        context,
    )["value"]

    assert CountOperator().execute({"values": selected}, {}, context) == {"value": 3.0}
    assert RmsOperator().execute({"values": selected}, {}, context)["value"] == pytest.approx(
        math.sqrt((1.0 + 10_000.0 + 2_500.0) / 3.0)
    )
    assert MedianOperator().execute({"values": selected}, {}, context) == {"value": 1.0}
    assert PercentileOperator().execute(
        {"values": selected},
        {"percentile": 100.0},
        context,
    ) == {"value": 100.0}
    assert PooledRatioOperator().execute(
        {"numerators": {"a": 1.0, "b": 2.0}, "denominators": {"a": 2.0, "b": 4.0}},
        {"zero_denominator": "error"},
        context,
    ) == {"value": 0.5}
