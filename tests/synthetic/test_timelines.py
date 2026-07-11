from __future__ import annotations

import pytest

from pilot_assessment.synthetic.timelines import (
    in_session_window,
    map_source_seconds_to_session_ns,
    source_grid,
)


def test_source_grid_includes_last_sample_not_after_duration() -> None:
    grid = source_grid(duration_s=2.0, sample_rate_hz=120.0)
    assert len(grid) == 241
    assert grid[0] == 0.0
    assert grid[-1] == 2.0


def test_source_grid_uses_floor_endpoint_rule() -> None:
    grid = source_grid(duration_s=29.01, sample_rate_hz=256.0)
    assert len(grid) == 7_427
    assert grid[-1] <= 29.01
    assert grid[-1] + (1 / 256) > 29.01


@pytest.mark.parametrize(
    ("duration_s", "sample_rate_hz"),
    [(0.0, 120.0), (-1.0, 120.0), (1.0, 0.0), (1.0, float("inf"))],
)
def test_source_grid_rejects_nonpositive_contract_values(
    duration_s: float, sample_rate_hz: float
) -> None:
    with pytest.raises(ValueError):
        source_grid(duration_s=duration_s, sample_rate_hz=sample_rate_hz)


def test_clock_mapping_uses_declared_offset_drift_and_half_even_rounding() -> None:
    assert (
        map_source_seconds_to_session_ns(
            0.0,
            offset_ns=-12_000_000,
            drift_ppm=-15.0,
        )
        == -12_000_000
    )
    assert (
        map_source_seconds_to_session_ns(
            1.0,
            offset_ns=-12_000_000,
            drift_ppm=-15.0,
        )
        == 987_985_000
    )
    assert map_source_seconds_to_session_ns(0.0000000005, offset_ns=0, drift_ppm=0.0) == 0
    assert map_source_seconds_to_session_ns(0.0000000015, offset_ns=0, drift_ppm=0.0) == 2


def test_in_session_window_keeps_boundaries() -> None:
    assert in_session_window(0, duration_s=2.0)
    assert in_session_window(2_000_000_000, duration_s=2.0)
    assert not in_session_window(-1, duration_s=2.0)
    assert not in_session_window(2_000_000_001, duration_s=2.0)
