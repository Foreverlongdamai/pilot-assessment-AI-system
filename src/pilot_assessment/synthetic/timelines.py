"""Deterministic raw sample grids and declared synthetic clock mappings."""

from __future__ import annotations

import math
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

_BILLION = Decimal(1_000_000_000)
_MILLION = Decimal(1_000_000)
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _positive_finite(value: float, field: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{field} must be positive and finite")


def source_grid(*, duration_s: float, sample_rate_hz: float) -> tuple[float, ...]:
    """Build s_k=k/f for every raw sample whose timestamp is not after duration."""

    _positive_finite(duration_s, "duration_s")
    _positive_finite(sample_rate_hz, "sample_rate_hz")
    count = (
        int(
            (Decimal(str(duration_s)) * Decimal(str(sample_rate_hz))).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        + 1
    )
    return tuple(index / sample_rate_hz for index in range(count))


def map_source_seconds_to_session_ns(
    source_time_s: float,
    *,
    offset_ns: int,
    drift_ppm: float,
) -> int:
    """Apply session=scale*source+offset and round the result to signed int64 ns."""

    if isinstance(source_time_s, bool) or not math.isfinite(source_time_s) or source_time_s < 0.0:
        raise ValueError("source_time_s must be non-negative and finite")
    if isinstance(offset_ns, bool) or not _INT64_MIN <= offset_ns <= _INT64_MAX:
        raise ValueError("offset_ns must be a signed int64")
    if isinstance(drift_ppm, bool) or not math.isfinite(drift_ppm):
        raise ValueError("drift_ppm must be finite")
    scale = Decimal(1) + Decimal(str(drift_ppm)) / _MILLION
    if scale <= 0:
        raise ValueError("declared clock scale must be positive")
    mapped = (
        Decimal(str(source_time_s)) * scale * _BILLION + Decimal(offset_ns)
    ).to_integral_value(rounding=ROUND_HALF_EVEN)
    value = int(mapped)
    if not _INT64_MIN <= value <= _INT64_MAX:
        raise ValueError("mapped session timestamp is outside signed int64")
    return value


def in_session_window(session_t_ns: int, *, duration_s: float) -> bool:
    """Return whether an aligned timestamp lies inside the inclusive session window."""

    _positive_finite(duration_s, "duration_s")
    if isinstance(session_t_ns, bool) or not _INT64_MIN <= session_t_ns <= _INT64_MAX:
        raise ValueError("session_t_ns must be a signed int64")
    end_ns = int((Decimal(str(duration_s)) * _BILLION).to_integral_value(rounding=ROUND_HALF_EVEN))
    return 0 <= session_t_ns <= end_ns


__all__ = [
    "in_session_window",
    "map_source_seconds_to_session_ns",
    "source_grid",
]
