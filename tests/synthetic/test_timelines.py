from __future__ import annotations

import pytest

import pilot_assessment.synthetic.timelines as timelines
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


def test_synthetic_clock_wrapper_delegates_to_shared_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, float | int] = {}

    def fake_mapper(source_time_s: float, *, scale: float, offset_ns: int) -> int:
        received.update(
            source_time_s=source_time_s,
            scale=scale,
            offset_ns=offset_ns,
        )
        return 123

    monkeypatch.setattr(timelines, "_map_source_seconds_to_session_ns", fake_mapper)

    assert (
        timelines.map_source_seconds_to_session_ns(
            4.25,
            offset_ns=7_000_000,
            drift_ppm=20.0,
        )
        == 123
    )
    assert received == {
        "source_time_s": 4.25,
        "scale": 1.00002,
        "offset_ns": 7_000_000,
    }


def test_in_session_window_keeps_boundaries() -> None:
    assert in_session_window(0, duration_s=2.0)
    assert in_session_window(2_000_000_000, duration_s=2.0)
    assert not in_session_window(-1, duration_s=2.0)
    assert not in_session_window(2_000_000_001, duration_s=2.0)
