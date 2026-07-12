"""Deterministic source-clock mapping onto the signed-int64 session timeline."""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal

from pilot_assessment.contracts.session import ClockSync, StreamDescriptor, StreamStatus
from pilot_assessment.contracts.synchronization import SynchronizationPolicy

_BILLION = Decimal(1_000_000_000)
_MILLION = Decimal(1_000_000)
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def round_decimal_ns(value: Decimal) -> int:
    """Round a Decimal nanosecond value half-even and require signed int64."""

    result = int(value.to_integral_value(rounding=ROUND_HALF_EVEN))
    if not _INT64_MIN <= result <= _INT64_MAX:
        raise ValueError("TIMESTAMP_OUT_OF_INT64_RANGE")
    return result


def map_source_seconds_to_session_ns(
    source_time_s: float,
    *,
    scale: float,
    offset_ns: int,
) -> int:
    """Apply ``session = scale * source + offset`` using Decimal strings once."""

    if isinstance(source_time_s, bool) or not math.isfinite(source_time_s):
        raise ValueError("source timestamp must be finite")
    if isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("clock scale must be positive and finite")
    if type(offset_ns) is not int or not _INT64_MIN <= offset_ns <= _INT64_MAX:
        raise ValueError("offset_ns must be signed int64")
    mapped = Decimal(str(source_time_s)) * Decimal(str(scale)) * _BILLION
    return round_decimal_ns(mapped + Decimal(offset_ns))


def session_seconds_to_ns(session_time_s: float) -> int:
    """Map seconds already expressed on the session clock through the same kernel."""

    return map_source_seconds_to_session_ns(session_time_s, scale=1.0, offset_ns=0)


def validate_clock_declaration(
    clock: ClockSync,
    policy: SynchronizationPolicy,
) -> None:
    """Require declared drift and residual diagnostics to be self-consistent."""

    declared = Decimal(str(clock.drift_ppm))
    derived = (Decimal(str(clock.scale)) - Decimal(1)) * _MILLION
    tolerance = Decimal(str(policy.clock_consistency_tolerance_ppm))
    if abs(declared - derived) > tolerance:
        raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
    if clock.residual_max_ms < clock.residual_rms_ms:
        raise ValueError("CLOCK_DECLARATION_INCONSISTENT")


def validate_same_clock_mappings(descriptors: Iterable[StreamDescriptor]) -> None:
    """Validate one caller-filtered inventory of M2-ready stream descriptors.

    ``StreamDescriptor`` does not contain M2 readiness. The caller must therefore
    pass only descriptors whose M2 result is READY. Within that inventory, present
    streams sharing a clock ID must share one mapping declaration. Per-stream
    residual diagnostics are excluded from mapping identity and may differ.
    """

    mappings_by_clock_id: dict[str, tuple[str, Decimal, int, Decimal]] = {}
    for descriptor in descriptors:
        if descriptor.status is not StreamStatus.PRESENT:
            continue
        clock = descriptor.clock_sync
        if clock is None:  # Defensive guard around the public descriptor contract.
            raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
        mapping = (
            clock.method,
            Decimal(str(clock.scale)),
            clock.offset_ns,
            Decimal(str(clock.drift_ppm)),
        )
        prior = mappings_by_clock_id.setdefault(descriptor.clock_id, mapping)
        if prior != mapping:
            raise ValueError("CLOCK_DECLARATION_INCONSISTENT")


__all__ = [
    "map_source_seconds_to_session_ns",
    "round_decimal_ns",
    "session_seconds_to_ns",
    "validate_clock_declaration",
    "validate_same_clock_mappings",
]
