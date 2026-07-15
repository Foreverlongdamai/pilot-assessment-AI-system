"""Reusable causal interval and event primitives for O10 through O12."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from statistics import median


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class CausalBooleanInterval:
    """One left-hold boolean observation over a half-open interval."""

    start_t_ns: int
    end_t_ns: int
    source_row_id: int
    active: bool

    def __post_init__(self) -> None:
        _strict_int(self.start_t_ns, "start_t_ns")
        _strict_int(self.end_t_ns, "end_t_ns")
        _strict_int(self.source_row_id, "source_row_id")
        if self.end_t_ns < self.start_t_ns:
            raise ValueError("causal interval end must not precede its start")
        if type(self.active) is not bool:
            raise TypeError("active must be a strict boolean")


@dataclass(frozen=True, slots=True)
class ConfirmedBooleanRun:
    """A true run whose causal onset is retained after later confirmation."""

    onset_t_ns: int
    confirmation_t_ns: int
    end_t_ns: int

    def __post_init__(self) -> None:
        _strict_int(self.onset_t_ns, "onset_t_ns")
        _strict_int(self.confirmation_t_ns, "confirmation_t_ns")
        _strict_int(self.end_t_ns, "end_t_ns")
        if not self.onset_t_ns <= self.confirmation_t_ns <= self.end_t_ns:
            raise ValueError("confirmed run bounds must be ordered")


@dataclass(frozen=True, slots=True)
class CausalNumericSample:
    """One numeric observation with an explicit continuous-support segment."""

    t_ns: int
    source_row_id: int
    segment_id: int
    value: float

    def __post_init__(self) -> None:
        _strict_int(self.t_ns, "t_ns")
        _strict_int(self.source_row_id, "source_row_id")
        _strict_int(self.segment_id, "segment_id")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("causal numeric value must be a real number")
        if not math.isfinite(float(self.value)):
            raise ValueError("causal numeric value must be finite")


def _validated_numeric_samples(
    samples: Sequence[CausalNumericSample],
) -> tuple[CausalNumericSample, ...]:
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence):
        raise TypeError("samples must be a non-string sequence")
    normalized = tuple(samples)
    if any(not isinstance(item, CausalNumericSample) for item in normalized):
        raise TypeError("samples must contain CausalNumericSample values")
    if normalized != tuple(sorted(normalized, key=lambda item: (item.t_ns, item.source_row_id))):
        raise ValueError("causal numeric samples must use canonical temporal order")
    source_ids = tuple(item.source_row_id for item in normalized)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("causal numeric sample source rows must be unique")
    segment_ids = tuple(item.segment_id for item in normalized)
    if any(current < previous for previous, current in pairwise(segment_ids)):
        raise ValueError("causal numeric segment IDs must be monotonic")
    seen: set[int] = set()
    previous: int | None = None
    for segment_id in segment_ids:
        if segment_id != previous:
            if segment_id in seen:
                raise ValueError("causal numeric segments must be contiguous")
            seen.add(segment_id)
            previous = segment_id
    return normalized


def trailing_causal_median(
    samples: Sequence[CausalNumericSample],
    *,
    window_ns: int,
) -> tuple[CausalNumericSample, ...]:
    """Apply a timestamp-based trailing median without crossing support gaps."""

    window = _strict_int(window_ns, "window_ns", minimum=1)
    normalized = _validated_numeric_samples(samples)
    filtered: list[CausalNumericSample] = []
    segment_start = 0
    for index, current in enumerate(normalized):
        if index == 0 or current.segment_id != normalized[index - 1].segment_id:
            segment_start = index
        lower_t_ns = current.t_ns - window
        values = [
            float(candidate.value)
            for candidate in normalized[segment_start : index + 1]
            if candidate.t_ns >= lower_t_ns
        ]
        filtered.append(
            CausalNumericSample(
                t_ns=current.t_ns,
                source_row_id=current.source_row_id,
                segment_id=current.segment_id,
                value=float(median(values)),
            )
        )
    return tuple(filtered)


def _validated_intervals(
    intervals: Sequence[CausalBooleanInterval],
) -> tuple[CausalBooleanInterval, ...]:
    if isinstance(intervals, (str, bytes)) or not isinstance(intervals, Sequence):
        raise TypeError("intervals must be a non-string sequence")
    normalized = tuple(intervals)
    if any(not isinstance(item, CausalBooleanInterval) for item in normalized):
        raise TypeError("intervals must contain CausalBooleanInterval values")
    expected = tuple(
        sorted(
            normalized,
            key=lambda item: (item.start_t_ns, item.end_t_ns, item.source_row_id),
        )
    )
    if normalized != expected:
        raise ValueError("causal intervals must use canonical temporal order")
    if any(current.start_t_ns < previous.end_t_ns for previous, current in pairwise(normalized)):
        raise ValueError("causal intervals must not overlap")
    source_ids = tuple(item.source_row_id for item in normalized)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("causal interval source rows must be unique")
    return normalized


def clip_boolean_intervals(
    intervals: Sequence[CausalBooleanInterval],
    *,
    start_t_ns: int,
    end_t_ns: int,
) -> tuple[CausalBooleanInterval, ...]:
    """Clip observations to one half-open window without bridging gaps."""

    start = _strict_int(start_t_ns, "start_t_ns")
    end = _strict_int(end_t_ns, "end_t_ns")
    if end <= start:
        raise ValueError("clip window must have positive duration")
    clipped: list[CausalBooleanInterval] = []
    for item in _validated_intervals(intervals):
        left = max(start, item.start_t_ns)
        right = min(end, item.end_t_ns)
        if right > left or (right == left and start <= item.start_t_ns < end):
            clipped.append(CausalBooleanInterval(left, right, item.source_row_id, item.active))
    return tuple(clipped)


def confirmed_true_runs(
    intervals: Sequence[CausalBooleanInterval],
    *,
    minimum_duration_ns: int,
) -> tuple[ConfirmedBooleanRun, ...]:
    """Return every true run that causally reaches the inclusive duration bound."""

    minimum = _strict_int(minimum_duration_ns, "minimum_duration_ns")
    normalized = _validated_intervals(intervals)
    runs: list[ConfirmedBooleanRun] = []
    run_start: int | None = None
    run_end: int | None = None

    def finalize() -> None:
        nonlocal run_start, run_end
        if run_start is not None and run_end is not None and run_end - run_start >= minimum:
            runs.append(
                ConfirmedBooleanRun(
                    onset_t_ns=run_start,
                    confirmation_t_ns=run_start + minimum,
                    end_t_ns=run_end,
                )
            )
        run_start = None
        run_end = None

    for interval in normalized:
        if not interval.active:
            finalize()
            continue
        if run_start is None or run_end != interval.start_t_ns:
            finalize()
            run_start = interval.start_t_ns
        run_end = interval.end_t_ns
    finalize()
    return tuple(runs)


def clip_observation_end(
    *,
    onset_t_ns: int,
    horizon_ns: int,
    session_end_t_ns: int,
    phase_end_t_ns: int | None = None,
    opportunity_end_t_ns: int | None = None,
) -> int:
    """Return the earliest valid event horizon, phase, opportunity, or session end."""

    onset = _strict_int(onset_t_ns, "onset_t_ns")
    horizon = _strict_int(horizon_ns, "horizon_ns", minimum=1)
    session_end = _strict_int(session_end_t_ns, "session_end_t_ns", minimum=1)
    if session_end <= onset:
        raise ValueError("session end must be greater than event onset")
    bounds = [onset + horizon, session_end]
    for value, label in (
        (phase_end_t_ns, "phase_end_t_ns"),
        (opportunity_end_t_ns, "opportunity_end_t_ns"),
    ):
        if value is None:
            continue
        bound = _strict_int(value, label, minimum=1)
        if bound <= onset or bound > session_end:
            raise ValueError(f"{label} must lie after onset and within the session")
        bounds.append(bound)
    return min(bounds)


__all__ = [
    "CausalBooleanInterval",
    "CausalNumericSample",
    "ConfirmedBooleanRun",
    "clip_boolean_intervals",
    "clip_observation_end",
    "confirmed_true_runs",
    "trailing_causal_median",
]
