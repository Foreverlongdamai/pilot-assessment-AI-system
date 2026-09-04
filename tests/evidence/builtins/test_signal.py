from __future__ import annotations

import math
from types import MappingProxyType

import pytest

import pilot_assessment.evidence.builtins.signal as signal_builtins
from pilot_assessment.evidence.builtins.signal import (
    ChannelSelectOperator,
    DetrendOperator,
    DifferenceOperator,
    FieldSelectOperator,
    NumericSample,
    SignalSeries,
    SmoothOperator,
    UnitConvertOperator,
)
from pilot_assessment.evidence.builtins.statistics import (
    CorrelationOperator,
    CountOperator,
    MedianOperator,
    PercentileOperator,
    PooledRatioOperator,
    RmsOperator,
)
from pilot_assessment.evidence.builtins.temporal import EventRecord
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="signal-smoke",
        recipe_version=1,
        node_id="signal",
        binding_values={},
    )


def _sample_parameters(
    *,
    alignment: str = "exact",
    max_gap_ns: int = 0,
    no_sample_policy: str = "error",
    multiple_event_policy: str = "all",
) -> dict[str, object]:
    return {
        "alignment": alignment,
        "max_gap_ns": max_gap_ns,
        "no_sample_policy": no_sample_policy,
        "multiple_event_policy": multiple_event_policy,
    }


def test_sample_at_event_definition_declares_point_input_and_named_number_output() -> None:
    definition = signal_builtins.sample_at_event_definition()

    ports = {port.port_id: port.port_type for port in definition.input_ports}
    assert ports["signal"].value_type == "signal_series"
    assert ports["signal"].temporal_semantics.value == "sampled"
    assert ports["events"].value_type == "event_collection"
    assert ports["events"].temporal_semantics.value == "point"
    output = definition.output_ports[0].port_type
    assert output.value_type == "named_numbers"
    assert output.temporal_semantics.value == "mixed"
    assert definition.parameter_schema["properties"] == {
        "alignment": {"type": "string", "enum": ["exact", "left_hold", "linear"]},
        "max_gap_ns": {"type": "integer", "minimum": 0},
        "no_sample_policy": {"type": "string", "enum": ["omit", "error"]},
        "multiple_event_policy": {
            "type": "string",
            "enum": ["all", "first", "last", "error"],
        },
    }


def test_sample_at_event_returns_an_immutable_event_id_mapping_for_exact_samples() -> None:
    signal = SignalSeries(
        "corridor-position",
        "m",
        (NumericSample(0, -5.0), NumericSample(2_000_000_000, 7.0)),
    )
    events = (
        EventRecord("onset-late", "decel-onset", 2_000_000_000),
        EventRecord("onset-early", "decel-onset", 0),
    )

    values = signal_builtins.SampleAtEventOperator().execute(
        {"signal": signal, "events": events},
        _sample_parameters(),
        _context(),
    )["value"]

    assert isinstance(values, MappingProxyType)
    assert dict(values) == {"onset-early": -5.0, "onset-late": 7.0}


@pytest.mark.parametrize(
    ("alignment", "expected"),
    [
        ("left_hold", {"event-1": 0.0, "event-3": 4.0}),
        ("linear", {"event-1": 2.0, "event-3": 6.0}),
    ],
)
def test_sample_at_event_reuses_bounded_signal_alignment(
    alignment: str,
    expected: dict[str, float],
) -> None:
    signal = SignalSeries(
        "corridor-position",
        "m",
        (
            NumericSample(0, 0.0),
            NumericSample(2_000_000_000, 4.0),
            NumericSample(4_000_000_000, 8.0),
        ),
    )
    events = (
        EventRecord("event-3", "onset", 3_000_000_000),
        EventRecord("event-1", "onset", 1_000_000_000),
    )

    values = signal_builtins.SampleAtEventOperator().execute(
        {"signal": signal, "events": events},
        _sample_parameters(alignment=alignment, max_gap_ns=2_000_000_000),
        _context(),
    )["value"]

    assert dict(values) == expected


def test_sample_at_event_applies_omit_or_error_when_max_gap_rejects_a_sample() -> None:
    signal = SignalSeries(
        "corridor-position",
        "m",
        (NumericSample(0, 0.0), NumericSample(2_000_000_000, 4.0)),
    )
    events = (
        EventRecord("exact", "onset", 0),
        EventRecord("gap", "onset", 1_000_000_000),
    )

    omitted = signal_builtins.SampleAtEventOperator().execute(
        {"signal": signal, "events": events},
        _sample_parameters(
            alignment="linear",
            max_gap_ns=1_999_999_999,
            no_sample_policy="omit",
        ),
        _context(),
    )["value"]

    assert dict(omitted) == {"exact": 0.0}
    with pytest.raises(signal_builtins.SignalOperatorError, match="gap.*aligned signal sample"):
        signal_builtins.SampleAtEventOperator().execute(
            {"signal": signal, "events": events},
            _sample_parameters(
                alignment="linear",
                max_gap_ns=1_999_999_999,
                no_sample_policy="error",
            ),
            _context(),
        )


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("first", {"event-a": 0.0}),
        ("last", {"event-c": 2.0}),
    ],
)
def test_sample_at_event_selects_multiple_events_in_canonical_time_order(
    policy: str,
    expected: dict[str, float],
) -> None:
    signal = SignalSeries(
        "corridor-position",
        "m",
        (
            NumericSample(0, 0.0),
            NumericSample(1, 1.0),
            NumericSample(2, 2.0),
        ),
    )
    events = (
        EventRecord("event-c", "onset", 2),
        EventRecord("event-a", "onset", 0),
        EventRecord("event-b", "onset", 1),
    )

    values = signal_builtins.SampleAtEventOperator().execute(
        {"signal": signal, "events": events},
        _sample_parameters(multiple_event_policy=policy),
        _context(),
    )["value"]

    assert dict(values) == expected


def test_sample_at_event_can_reject_multiple_events() -> None:
    signal = SignalSeries("corridor-position", "m", (NumericSample(0, 0.0),))
    events = (
        EventRecord("event-a", "onset", 0),
        EventRecord("event-b", "onset", 0),
    )

    with pytest.raises(signal_builtins.SignalOperatorError, match="multiple events"):
        signal_builtins.SampleAtEventOperator().execute(
            {"signal": signal, "events": events},
            _sample_parameters(multiple_event_policy="error"),
            _context(),
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
    assert CorrelationOperator().execute(
        {"left": selected, "right": selected},
        {"absolute": True, "degenerate": "error"},
        context,
    ) == {"value": pytest.approx(1.0)}
