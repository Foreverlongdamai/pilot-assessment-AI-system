from __future__ import annotations

from decimal import Decimal

import pytest

from pilot_assessment.contracts.session import ClockSync, StreamDescriptor, StreamStatus
from pilot_assessment.contracts.synchronization import SynchronizationPolicy
from pilot_assessment.synchronization.clock import (
    map_source_seconds_to_session_ns,
    round_decimal_ns,
    session_seconds_to_ns,
    validate_clock_declaration,
    validate_same_clock_mappings,
)


def _clock(
    *,
    method: str = "fixture-declared-v0.1",
    scale: float = 1.0,
    offset_ns: int = 0,
    drift_ppm: float = 0.0,
    residual_rms_ms: float = 0.0,
    residual_max_ms: float = 0.0,
) -> ClockSync:
    return ClockSync(
        method=method,
        scale=scale,
        offset_ns=offset_ns,
        drift_ppm=drift_ppm,
        residual_rms_ms=residual_rms_ms,
        residual_max_ms=residual_max_ms,
    )


def _descriptor(*, modality: str, clock_id: str, clock: ClockSync) -> StreamDescriptor:
    path = f"streams/{modality.lower()}.csv"
    return StreamDescriptor(
        modality=modality,
        status=StreamStatus.PRESENT,
        required_for_import=True,
        paths=[path],
        format="csv",
        schema_id=f"{modality.lower()}-normalized-v0.1",
        clock_id=clock_id,
        clock_sync=clock,
        sample_rate_hz=100.0,
        units="mixed",
        quality_summary=None,
        checksums={path: "a" * 64},
        metadata={},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0.5"), 0),
        (Decimal("1.5"), 2),
        (Decimal("2.5"), 2),
        (Decimal("-0.5"), 0),
        (Decimal("-1.5"), -2),
        (Decimal("-2.5"), -2),
    ],
)
def test_round_decimal_ns_uses_half_even_ties(value: Decimal, expected: int) -> None:
    assert round_decimal_ns(value) == expected


def test_round_decimal_ns_accepts_exact_signed_int64_boundaries() -> None:
    assert round_decimal_ns(Decimal(-(2**63))) == -(2**63)
    assert round_decimal_ns(Decimal(2**63 - 1)) == 2**63 - 1


@pytest.mark.parametrize("value", [Decimal(-(2**63) - 1), Decimal(2**63)])
def test_round_decimal_ns_rejects_signed_int64_overflow(value: Decimal) -> None:
    with pytest.raises(ValueError, match="TIMESTAMP_OUT_OF_INT64_RANGE"):
        round_decimal_ns(value)


def test_clock_mapping_uses_scale_exactly_once() -> None:
    assert (
        map_source_seconds_to_session_ns(
            10.0,
            scale=1.00002,
            offset_ns=0,
        )
        == 10_000_200_000
    )


def test_clock_mapping_uses_decimal_string_semantics() -> None:
    assert (
        map_source_seconds_to_session_ns(
            29.008333333333333,
            scale=1.00002,
            offset_ns=7_000_000,
        )
        == 29_015_913_500
    )


def test_session_seconds_to_ns_uses_the_same_kernel() -> None:
    assert session_seconds_to_ns(0.0000000005) == 0
    assert session_seconds_to_ns(0.0000000015) == 2


@pytest.mark.parametrize("source_time_s", [True, float("nan"), float("inf")])
def test_clock_mapping_rejects_nonfinite_or_boolean_source_time(source_time_s: float) -> None:
    with pytest.raises(ValueError, match="source timestamp must be finite"):
        map_source_seconds_to_session_ns(source_time_s, scale=1.0, offset_ns=0)


@pytest.mark.parametrize("scale", [True, 0.0, -1.0, float("nan"), float("inf")])
def test_clock_mapping_rejects_nonpositive_nonfinite_or_boolean_scale(scale: float) -> None:
    with pytest.raises(ValueError, match="clock scale must be positive and finite"):
        map_source_seconds_to_session_ns(0.0, scale=scale, offset_ns=0)


@pytest.mark.parametrize("offset_ns", [True, 0.0, 0.5, 1.0, -(2**63) - 1, 2**63])
def test_clock_mapping_rejects_non_int64_or_boolean_offset(offset_ns: object) -> None:
    with pytest.raises(ValueError, match="offset_ns must be signed int64"):
        map_source_seconds_to_session_ns(0.0, scale=1.0, offset_ns=offset_ns)  # type: ignore[arg-type]


def test_clock_declaration_accepts_exact_consistency_tolerance() -> None:
    validate_clock_declaration(
        _clock(scale=1.000020000001, drift_ppm=20.0),
        SynchronizationPolicy(),
    )


def test_clock_declaration_rejects_over_consistency_tolerance() -> None:
    with pytest.raises(ValueError, match="CLOCK_DECLARATION_INCONSISTENT"):
        validate_clock_declaration(
            _clock(scale=1.000020000002, drift_ppm=20.0),
            SynchronizationPolicy(),
        )


def test_clock_declaration_rejects_residual_max_below_rms() -> None:
    with pytest.raises(ValueError, match="CLOCK_DECLARATION_INCONSISTENT"):
        validate_clock_declaration(
            _clock(residual_rms_ms=0.2, residual_max_ms=0.1),
            SynchronizationPolicy(),
        )


def test_same_clock_mapping_mismatch_is_rejected() -> None:
    descriptors = [
        _descriptor(modality="X", clock_id="sim_clock", clock=_clock()),
        _descriptor(
            modality="U",
            clock_id="sim_clock",
            clock=_clock(method="other-declared-v0.1"),
        ),
    ]

    with pytest.raises(ValueError, match="CLOCK_DECLARATION_INCONSISTENT"):
        validate_same_clock_mappings(descriptors)


def test_same_clock_different_residuals_are_accepted() -> None:
    descriptors = [
        _descriptor(
            modality="X",
            clock_id="sim_clock",
            clock=_clock(residual_rms_ms=0.1, residual_max_ms=0.2),
        ),
        _descriptor(
            modality="U",
            clock_id="sim_clock",
            clock=_clock(residual_rms_ms=0.2, residual_max_ms=0.3),
        ),
    ]

    validate_same_clock_mappings(descriptors)


def test_same_clock_validation_requires_caller_filtered_m2_ready_inventory() -> None:
    m2_ready = _descriptor(modality="X", clock_id="sim_clock", clock=_clock())
    # StreamDescriptor cannot carry this hypothetical descriptor's non-ready M2
    # outcome. Task 11 must exclude it before calling the clock helper.
    m2_not_ready = _descriptor(
        modality="U",
        clock_id="sim_clock",
        clock=_clock(method="untrusted-declared-v0.1"),
    )

    validate_same_clock_mappings([m2_ready])
    with pytest.raises(ValueError, match="CLOCK_DECLARATION_INCONSISTENT"):
        validate_same_clock_mappings([m2_ready, m2_not_ready])
