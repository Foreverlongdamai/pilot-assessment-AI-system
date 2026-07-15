"""Frozen JSON-safe result records returned by shared anchor kernels."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

O1KernelStatus = Literal["computed", "missing_input", "not_computable"]


def _strict_nonnegative_int(value: int, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative strict integer")


@dataclass(frozen=True, slots=True)
class O1MaskRow:
    phase_id: str
    t_ns: int
    source_row_id: int
    axis_order: int
    axis_id: str
    inside: bool

    def __post_init__(self) -> None:
        if not self.phase_id or not self.axis_id:
            raise ValueError("mask row IDs must be non-empty")
        for value, label in (
            (self.t_ns, "t_ns"),
            (self.source_row_id, "source_row_id"),
            (self.axis_order, "axis_order"),
        ):
            _strict_nonnegative_int(value, label)
        if type(self.inside) is not bool:
            raise TypeError("inside must be a strict boolean")


@dataclass(frozen=True, slots=True)
class O1AxisSummary:
    axis_id: str
    axis_order: int
    desired_duration_ns: int

    def __post_init__(self) -> None:
        if not self.axis_id:
            raise ValueError("axis_id must be non-empty")
        _strict_nonnegative_int(self.axis_order, "axis_order")
        _strict_nonnegative_int(self.desired_duration_ns, "desired_duration_ns")


@dataclass(frozen=True, slots=True)
class O1KernelResult:
    status: O1KernelStatus
    reason: str | None
    precision_percent: float | None
    phase_duration_ns: int
    observed_support_duration_ns: int
    desired_joint_duration_ns: int
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None
    axis_summaries: tuple[O1AxisSummary, ...]
    mask_rows: tuple[O1MaskRow, ...]

    def __post_init__(self) -> None:
        if self.status not in {"computed", "missing_input", "not_computable"}:
            raise ValueError("unsupported O1 kernel status")
        if self.status == "computed":
            if self.reason is not None or self.precision_percent is None:
                raise ValueError("computed O1 results require a precision and no reason")
        elif self.reason is None or self.precision_percent is not None:
            raise ValueError("non-computed O1 results require a reason and no precision")
        if self.precision_percent is not None and (
            not math.isfinite(self.precision_percent) or not 0.0 <= self.precision_percent <= 100.0
        ):
            raise ValueError("precision_percent must be finite and lie in [0, 100]")
        for value, label in (
            (self.phase_duration_ns, "phase_duration_ns"),
            (self.observed_support_duration_ns, "observed_support_duration_ns"),
            (self.desired_joint_duration_ns, "desired_joint_duration_ns"),
            (self.sample_count, "sample_count"),
            (self.gap_count, "gap_count"),
        ):
            _strict_nonnegative_int(value, label)
        if self.phase_duration_ns <= 0:
            raise ValueError("phase_duration_ns must be positive")
        if self.desired_joint_duration_ns > self.observed_support_duration_ns:
            raise ValueError("desired duration cannot exceed observed support")
        if self.observed_support_duration_ns > self.phase_duration_ns:
            raise ValueError("observed support cannot exceed the phase duration")
        if (self.source_start_t_ns is None) != (self.source_end_t_ns is None):
            raise ValueError("source bounds must be both present or both absent")
        if self.source_start_t_ns is not None and self.source_end_t_ns is not None:
            _strict_nonnegative_int(self.source_start_t_ns, "source_start_t_ns")
            _strict_nonnegative_int(self.source_end_t_ns, "source_end_t_ns")
            if self.source_end_t_ns < self.source_start_t_ns:
                raise ValueError("source bounds must be ordered")
        if self.max_gap_ns is not None:
            _strict_nonnegative_int(self.max_gap_ns, "max_gap_ns")
            if self.max_gap_ns == 0:
                raise ValueError("max_gap_ns must be positive when present")
        if tuple(item.axis_order for item in self.axis_summaries) != tuple(
            range(len(self.axis_summaries))
        ):
            raise ValueError("axis summaries must use contiguous canonical order")


__all__ = ["O1AxisSummary", "O1KernelResult", "O1KernelStatus", "O1MaskRow"]
