"""Shared O7 control-reversal kernel over the immutable movement profile."""

from __future__ import annotations

import math
from itertools import pairwise

from pilot_assessment.anchors.primitives.models import (
    O7ChannelRate,
    O7KernelResult,
    O7ReversalEvent,
)
from pilot_assessment.anchors.primitives.movement import (
    MovementKernelResult,
    MovementSupportSegment,
    MovementTurningPoint,
)

_NANOSECONDS_PER_SECOND = 1_000_000_000


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative strict integer")
    return value


def _support_segment_index(
    point: MovementTurningPoint,
    segments: tuple[MovementSupportSegment, ...],
) -> int | None:
    """Assign a shared boundary to the later support segment deterministically."""

    candidates = tuple(
        index
        for index, segment in enumerate(segments)
        if segment.start_t_ns <= point.t_ns <= segment.end_t_ns
    )
    if not candidates:
        return None
    return max(candidates, key=lambda index: (segments[index].start_t_ns, index))


def _same_support_segment(
    left: MovementTurningPoint,
    right: MovementTurningPoint,
    segments: tuple[MovementSupportSegment, ...],
) -> bool:
    left_segment = _support_segment_index(left, segments)
    return left_segment is not None and left_segment == _support_segment_index(right, segments)


def compute_o7_kernel(
    movement: MovementKernelResult,
    channel_ids: tuple[str, ...],
    minimum_reversal_amplitude_pct: float,
    minimum_reversal_separation_ns: int,
) -> O7KernelResult:
    """Count qualifying adjacent turning points using the exact O5 movement profile."""

    if not isinstance(movement, MovementKernelResult):
        raise TypeError("movement must be a MovementKernelResult")
    if (
        type(channel_ids) is not tuple
        or not channel_ids
        or any(type(channel_id) is not str or not channel_id for channel_id in channel_ids)
        or channel_ids != tuple(sorted(channel_ids))
        or len(channel_ids) != len(set(channel_ids))
    ):
        raise ValueError("channel_ids must be a non-empty canonical unique tuple")
    minimum_amplitude = _finite_nonnegative(
        minimum_reversal_amplitude_pct, "minimum_reversal_amplitude_pct"
    )
    minimum_separation = _nonnegative_int(
        minimum_reversal_separation_ns, "minimum_reversal_separation_ns"
    )
    if movement.status != "computed":
        return O7KernelResult(
            status=movement.status,
            reason=movement.reason,
            reversal_rate_hz=None,
            total_reversal_count=0,
            channel_rates=(),
        )
    by_id = {channel.channel_id: channel for channel in movement.channels}
    if any(channel_id not in by_id for channel_id in channel_ids):
        return O7KernelResult(
            status="not_computable",
            reason="configured-channel-missing",
            reversal_rate_hz=None,
            total_reversal_count=0,
            channel_rates=(),
        )

    rates: list[O7ChannelRate] = []
    for channel_id in channel_ids:
        channel = by_id[channel_id]
        if channel.observed_support_duration_ns == 0:
            return O7KernelResult(
                status="not_computable",
                reason="zero-support-duration",
                reversal_rate_hz=None,
                total_reversal_count=0,
                channel_rates=(),
            )
        events = tuple(
            O7ReversalEvent(
                event_t_ns=right.t_ns,
                amplitude_pct=abs(right.value_pct - left.value_pct),
            )
            for left, right in pairwise(channel.turning_points)
            if _same_support_segment(left, right, channel.support_segments)
            and right.t_ns - left.t_ns >= minimum_separation
            and abs(right.value_pct - left.value_pct) >= minimum_amplitude
        )
        duration_s = channel.observed_support_duration_ns / _NANOSECONDS_PER_SECOND
        rates.append(
            O7ChannelRate(
                channel_id=channel_id,
                observed_support_duration_ns=channel.observed_support_duration_ns,
                reversal_events=events,
                rate_hz=len(events) / duration_s,
            )
        )
    return O7KernelResult(
        status="computed",
        reason=None,
        reversal_rate_hz=max(channel.rate_hz for channel in rates),
        total_reversal_count=sum(len(channel.reversal_events) for channel in rates),
        channel_rates=tuple(rates),
    )


__all__ = ["compute_o7_kernel"]
