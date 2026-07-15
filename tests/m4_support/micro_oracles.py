"""Independent scalar helpers for hand-calculated M4 micro tests."""

from __future__ import annotations


def duration_percent(numerator_ns: int, denominator_ns: int) -> float:
    if denominator_ns <= 0:
        raise ValueError("denominator_ns must be positive")
    if numerator_ns < 0 or numerator_ns > denominator_ns:
        raise ValueError("numerator_ns must lie inside the denominator")
    return 100.0 * numerator_ns / denominator_ns


def higher_is_better_state(
    value: float,
    *,
    desired_at_least: float,
    adequate_at_least: float,
) -> str:
    if desired_at_least < adequate_at_least:
        raise ValueError("desired threshold must be at least the adequate threshold")
    if value >= desired_at_least:
        return "desired"
    if value >= adequate_at_least:
        return "adequate"
    return "unacceptable"


__all__ = ["duration_percent", "higher_is_better_state"]
