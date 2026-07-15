from __future__ import annotations

import pytest

from pilot_assessment.anchors.primitives.events import (
    CausalBooleanInterval,
    CausalNumericSample,
    clip_observation_end,
    confirmed_true_runs,
    trailing_causal_median,
)

NS = 1_000_000_000


def test_confirmed_run_keeps_causal_onset_instead_of_confirmation_time() -> None:
    runs = confirmed_true_runs(
        (
            CausalBooleanInterval(0, NS, 0, False),
            CausalBooleanInterval(NS, NS + 50_000_000, 1, True),
            CausalBooleanInterval(NS + 50_000_000, NS + 100_000_000, 2, True),
            CausalBooleanInterval(NS + 100_000_000, 2 * NS, 3, False),
        ),
        minimum_duration_ns=100_000_000,
    )

    assert len(runs) == 1
    assert runs[0].onset_t_ns == NS
    assert runs[0].confirmation_t_ns == NS + 100_000_000
    assert runs[0].end_t_ns == NS + 100_000_000


def test_false_intervals_and_temporal_gaps_break_confirmation_runs() -> None:
    intervals = (
        CausalBooleanInterval(0, 60_000_000, 0, True),
        CausalBooleanInterval(60_000_000, 70_000_000, 1, False),
        CausalBooleanInterval(70_000_000, 130_000_000, 2, True),
        CausalBooleanInterval(200_000_000, 260_000_000, 3, True),
    )

    assert confirmed_true_runs(intervals, minimum_duration_ns=100_000_000) == ()


def test_trailing_median_is_causal_inclusive_and_never_crosses_segments() -> None:
    filtered = trailing_causal_median(
        (
            CausalNumericSample(0, 0, 0, 0.0),
            CausalNumericSample(10_000_000, 1, 0, 10.0),
            CausalNumericSample(20_000_000, 2, 0, 10.0),
            CausalNumericSample(100_000_000, 3, 1, -5.0),
        ),
        window_ns=20_000_000,
    )

    assert tuple(item.value for item in filtered) == (0.0, 5.0, 10.0, -5.0)


def test_zero_duration_confirmation_uses_the_first_true_sample() -> None:
    runs = confirmed_true_runs(
        (
            CausalBooleanInterval(0, 0, 0, False),
            CausalBooleanInterval(NS, NS, 1, True),
        ),
        minimum_duration_ns=0,
    )

    assert len(runs) == 1
    assert runs[0].onset_t_ns == NS
    assert runs[0].confirmation_t_ns == NS


def test_observation_end_uses_the_earliest_declared_bound() -> None:
    assert (
        clip_observation_end(
            onset_t_ns=2 * NS,
            horizon_ns=15 * NS,
            session_end_t_ns=30 * NS,
            phase_end_t_ns=12 * NS,
            opportunity_end_t_ns=8 * NS,
        )
        == 8 * NS
    )


@pytest.mark.parametrize("invalid_end", (NS, 31 * NS))
def test_observation_end_rejects_bounds_outside_onset_and_session(invalid_end: int) -> None:
    with pytest.raises(ValueError):
        clip_observation_end(
            onset_t_ns=2 * NS,
            horizon_ns=15 * NS,
            session_end_t_ns=30 * NS,
            opportunity_end_t_ns=invalid_end,
        )
