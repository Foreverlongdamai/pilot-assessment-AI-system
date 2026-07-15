"""Deterministic, gap-aware temporal primitives for M4 anchor calculations.

All spans in this module are half-open.  Point support is reconstructed from
the aligned rows without applying a data-quality threshold: a declared M3 gap
only prevents an interval from crossing an unobserved span.  Durations remain
in nanoseconds so callers must make any unit conversion explicit.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import Any

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.models import AnchorRequestValidationError
from pilot_assessment.anchors.protocols import ProjectedSemanticScope
from pilot_assessment.contracts.anchor_v2 import SourceWindowV2
from pilot_assessment.contracts.synchronization import PointTemporalArtifactMetrics

_NANOSECONDS_PER_SECOND = Decimal(1_000_000_000)
_SEMANTIC_PATHS = {
    "semantic.phases",
    "semantic.baselines",
    "semantic.events",
}
_WINDOW_POLICIES = {
    "semantic-span-v1",
    "fixed-full-with-end-tail-v1",
}


def _strict_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be a strict integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def _strict_optional_int(value: object, *, label: str, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    return _strict_int(value, label=label, minimum=minimum)


def _strict_string(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class SupportInterval:
    """Left-hold support contributed by one source row."""

    start_t_ns: int
    end_t_ns: int
    source_row_index: int

    def __post_init__(self) -> None:
        _strict_int(self.start_t_ns, label="start_t_ns", minimum=0)
        _strict_int(self.end_t_ns, label="end_t_ns", minimum=0)
        _strict_int(self.source_row_index, label="source_row_index", minimum=0)
        if self.end_t_ns < self.start_t_ns:
            raise ValueError("support interval end must not precede its start")


@dataclass(frozen=True, slots=True)
class TemporalSupport:
    """Immutable point support plus the M3-compatible gap summary."""

    intervals: tuple[SupportInterval, ...]
    segment_bounds: tuple[tuple[int, int], ...]
    observed_duration_ns: int
    gap_count: int
    max_gap_ns: int | None

    def __post_init__(self) -> None:
        if type(self.intervals) is not tuple or any(
            not isinstance(item, SupportInterval) for item in self.intervals
        ):
            raise TypeError("intervals must be a tuple of SupportInterval values")
        if type(self.segment_bounds) is not tuple:
            raise TypeError("segment_bounds must be a tuple")
        normalized_bounds: list[tuple[int, int]] = []
        for index, bound in enumerate(self.segment_bounds):
            if type(bound) is not tuple or len(bound) != 2:
                raise TypeError("each segment bound must be a two-integer tuple")
            start = _strict_int(bound[0], label=f"segment_bounds[{index}].start", minimum=0)
            end = _strict_int(bound[1], label=f"segment_bounds[{index}].end", minimum=0)
            if end < start:
                raise ValueError("segment end must not precede its start")
            normalized_bounds.append((start, end))
        if any(current[0] < previous[1] for previous, current in pairwise(normalized_bounds)):
            raise ValueError("segment bounds must be in non-overlapping temporal order")
        if any(
            current.start_t_ns < previous.end_t_ns for previous, current in pairwise(self.intervals)
        ):
            raise ValueError("support intervals must be in non-overlapping temporal order")
        source_indexes = tuple(item.source_row_index for item in self.intervals)
        if len(source_indexes) != len(set(source_indexes)):
            raise ValueError("each source row may contribute at most one support interval")
        duration = sum(item.end_t_ns - item.start_t_ns for item in self.intervals)
        _strict_int(self.observed_duration_ns, label="observed_duration_ns", minimum=0)
        if self.observed_duration_ns != duration:
            raise ValueError("observed_duration_ns must equal the interval duration sum")
        _strict_int(self.gap_count, label="gap_count", minimum=0)
        _strict_optional_int(self.max_gap_ns, label="max_gap_ns", minimum=1)


def _validate_point_frame(
    frame: pl.DataFrame,
    *,
    timestamp_column: str,
    stable_keys: tuple[str, ...],
    in_session_column: str,
) -> None:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("frame must be a Polars DataFrame")
    if len({timestamp_column, in_session_column, *stable_keys}) != len(stable_keys) + 2:
        raise ValueError("timestamp, in-session, and stable-key columns must be distinct")
    expected = {
        timestamp_column: pl.Int64,
        in_session_column: pl.Boolean,
    }
    for column, dtype in expected.items():
        if column not in frame.columns:
            raise ValueError(f"frame is missing required column {column}")
        if frame.schema[column] != dtype or frame[column].null_count():
            raise ValueError(f"column {column} has an invalid temporal schema")
    for column in stable_keys:
        if column not in frame.columns or frame[column].null_count():
            raise ValueError(f"stable key {column} is missing or contains null values")
    if frame.select(stable_keys).is_duplicated().any():
        raise ValueError("stable keys must identify unique source rows")


def reconstruct_point_support(
    frame: pl.DataFrame,
    timestamp_column: str,
    stable_keys: Sequence[str],
    in_session_column: str,
    gap_threshold_ns: int | None,
    semantic_end_t_ns: int | None,
) -> TemporalSupport:
    """Reconstruct left-hold support in stable temporal order.

    ``source_row_index`` always addresses the caller's original frame order.
    A positive delta splits support only when it is strictly greater than the
    declared M3 threshold.  Only the final segment may be extended, and only
    when an explicit semantic end is supplied.
    """

    timestamp_column = _strict_string(timestamp_column, label="timestamp_column")
    in_session_column = _strict_string(in_session_column, label="in_session_column")
    if isinstance(stable_keys, (str, bytes)) or not isinstance(stable_keys, Sequence):
        raise TypeError("stable_keys must be a non-string sequence")
    normalized_keys = tuple(
        _strict_string(value, label=f"stable_keys[{index}]")
        for index, value in enumerate(stable_keys)
    )
    if not normalized_keys or len(normalized_keys) != len(set(normalized_keys)):
        raise ValueError("stable_keys must be non-empty and unique")
    threshold = _strict_optional_int(
        gap_threshold_ns,
        label="gap_threshold_ns",
        minimum=0,
    )
    semantic_end = _strict_optional_int(
        semantic_end_t_ns,
        label="semantic_end_t_ns",
        minimum=0,
    )
    _validate_point_frame(
        frame,
        timestamp_column=timestamp_column,
        stable_keys=normalized_keys,
        in_session_column=in_session_column,
    )

    row_index_column = "__m4_source_row_index"
    if row_index_column in frame.columns:
        raise ValueError(f"reserved temporal column {row_index_column} already exists")
    try:
        ordered = (
            frame.with_row_index(row_index_column)
            .filter(pl.col(in_session_column))
            .sort([timestamp_column, *normalized_keys], maintain_order=True)
        )
    except (TypeError, ValueError, pl.exceptions.PolarsError) as error:
        raise ValueError("point rows cannot be ordered by their temporal stable keys") from error

    times = ordered[timestamp_column].to_list()
    source_indexes = ordered[row_index_column].to_list()
    if any(type(value) is not int or value < 0 for value in times):
        raise ValueError("in-session timestamps must be non-negative strict integers")
    if not times:
        return TemporalSupport((), (), 0, 0, None)
    if semantic_end is not None and semantic_end < times[-1]:
        raise ValueError("semantic_end_t_ns cannot precede the final in-session row")

    positive_deltas = [
        current - previous for previous, current in pairwise(times) if current > previous
    ]
    max_gap = max(positive_deltas) if positive_deltas else None
    split_after = {
        index
        for index, (current, following) in enumerate(pairwise(times))
        if threshold is not None and following - current > threshold
    }

    intervals: list[SupportInterval] = []
    for index, (timestamp, source_index) in enumerate(zip(times, source_indexes, strict=True)):
        if index + 1 < len(times) and index not in split_after:
            interval_end = times[index + 1]
        elif index + 1 == len(times) and semantic_end is not None:
            interval_end = semantic_end
        else:
            interval_end = timestamp
        intervals.append(SupportInterval(timestamp, interval_end, int(source_index)))

    segment_bounds: list[tuple[int, int]] = []
    segment_start = times[0]
    for index in sorted(split_after):
        segment_bounds.append((segment_start, times[index]))
        segment_start = times[index + 1]
    segment_bounds.append((segment_start, intervals[-1].end_t_ns))

    return TemporalSupport(
        intervals=tuple(intervals),
        segment_bounds=tuple(segment_bounds),
        observed_duration_ns=sum(item.end_t_ns - item.start_t_ns for item in intervals),
        gap_count=len(split_after),
        max_gap_ns=max_gap,
    )


def validate_reported_gap_metrics(
    support: TemporalSupport,
    reported: PointTemporalArtifactMetrics,
) -> None:
    """Require the M4 reconstruction to agree with the immutable M3 report."""

    if not isinstance(support, TemporalSupport):
        raise TypeError("support must be TemporalSupport")
    if not isinstance(reported, PointTemporalArtifactMetrics):
        raise TypeError("reported must be PointTemporalArtifactMetrics")
    field_prefix = f"synchronization_report.{reported.artifact_role}"
    if support.gap_count != reported.gap_count:
        raise AnchorRequestValidationError(
            "request_semantic_identity_mismatch",
            {"field": f"{field_prefix}.gap_count", "reason": "gap_count_mismatch"},
        )
    if support.max_gap_ns != reported.max_gap_ns:
        raise AnchorRequestValidationError(
            "request_semantic_identity_mismatch",
            {"field": f"{field_prefix}.max_gap_ns", "reason": "max_gap_ns_mismatch"},
        )


def decimal_grid_v1(
    start_t_ns: int,
    end_t_ns: int,
    rate_hz: Decimal,
) -> tuple[int, ...]:
    """Build an absolute-time half-open grid using Decimal round-half-even."""

    start = _strict_int(start_t_ns, label="start_t_ns", minimum=0)
    end = _strict_int(end_t_ns, label="end_t_ns", minimum=0)
    if end < start:
        raise ValueError("end_t_ns must not precede start_t_ns")
    if not isinstance(rate_hz, Decimal):
        raise TypeError("rate_hz must be Decimal")
    if not rate_hz.is_finite() or rate_hz <= 0:
        raise ValueError("rate_hz must be finite and positive")
    if rate_hz > _NANOSECONDS_PER_SECOND:
        raise ValueError("rate_hz exceeds the one-nanosecond timestamp resolution")
    if start == end:
        return ()

    period_ns = _NANOSECONDS_PER_SECOND / rate_hz
    points: list[int] = []
    index = 0
    while True:
        exact = Decimal(start) + Decimal(index) * period_ns
        point = int(exact.to_integral_value(rounding=ROUND_HALF_EVEN))
        if point >= end:
            break
        if points and point <= points[-1]:
            raise ValueError("rate_hz does not produce a strictly increasing integer grid")
        points.append(point)
        index += 1
    return tuple(points)


def left_hold_integral_v1(
    values: Sequence[float],
    support: TemporalSupport,
) -> float:
    """Integrate caller-order values over source-indexed support in ns."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("values must be a non-string sequence")
    if not isinstance(support, TemporalSupport):
        raise TypeError("support must be TemporalSupport")
    if support.intervals and max(item.source_row_index for item in support.intervals) >= len(
        values
    ):
        raise ValueError("values do not cover every support source row index")

    contributions: list[float] = []
    for interval in support.intervals:
        raw_value = values[interval.source_row_index]
        if isinstance(raw_value, bool):
            raise TypeError("left-hold values must be numeric and not boolean")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise TypeError("left-hold values must be numeric") from error
        if not math.isfinite(value):
            raise ValueError("left-hold values must be finite")
        contributions.append(value * (interval.end_t_ns - interval.start_t_ns))
    result = math.fsum(contributions)
    if not math.isfinite(result):
        raise ValueError("left-hold integral must remain finite")
    return result


def nearest_within_v1(
    left_t_ns: Sequence[int],
    right_t_ns: Sequence[int],
    right_stable_ids: Sequence[str],
    tolerance_ns: int,
) -> tuple[int | None, ...]:
    """Return original right-side indexes for deterministic nearest matches."""

    for values, label in (
        (left_t_ns, "left_t_ns"),
        (right_t_ns, "right_t_ns"),
        (right_stable_ids, "right_stable_ids"),
    ):
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise TypeError(f"{label} must be a non-string sequence")
    tolerance = _strict_int(tolerance_ns, label="tolerance_ns", minimum=0)
    left = tuple(
        _strict_int(value, label=f"left_t_ns[{index}]") for index, value in enumerate(left_t_ns)
    )
    right = tuple(
        _strict_int(value, label=f"right_t_ns[{index}]") for index, value in enumerate(right_t_ns)
    )
    stable_ids = tuple(
        _strict_string(value, label=f"right_stable_ids[{index}]")
        for index, value in enumerate(right_stable_ids)
    )
    if len(right) != len(stable_ids):
        raise ValueError("right timestamps and stable IDs must have equal length")
    if len(stable_ids) != len(set(stable_ids)):
        raise ValueError("right stable IDs must identify unique rows")
    if not right:
        return tuple(None for _ in left)

    minimum, maximum = min(right), max(right)
    indexed_right = tuple(zip(range(len(right)), right, stable_ids, strict=True))
    matches: list[int | None] = []
    for timestamp in left:
        if timestamp < minimum or timestamp > maximum:
            matches.append(None)
            continue
        candidates = [
            (abs(candidate_t - timestamp), candidate_t, stable_id, original_index)
            for original_index, candidate_t, stable_id in indexed_right
            if abs(candidate_t - timestamp) <= tolerance
        ]
        matches.append(min(candidates)[3] if candidates else None)
    return tuple(matches)


@dataclass(frozen=True, slots=True)
class _SemanticSpan:
    scope_id: str
    start_t_ns: int
    end_t_ns: int
    original_end_t_ns: int
    phase_id: str | None
    event_id: str | None
    include_session_terminal_point: bool


def _mapping_value(entry: Mapping[str, Any], key: str, *, label: str) -> Any:
    if key not in entry:
        raise ValueError(f"{label} is missing {key}")
    return entry[key]


def _semantic_span_from_entry(
    semantic_path: str,
    entry: Mapping[str, Any],
    *,
    event_span: str,
) -> _SemanticSpan:
    if semantic_path == "semantic.phases":
        scope_id = _strict_string(
            _mapping_value(entry, "phase_id", label="semantic phase"),
            label="phase_id",
        )
        start = _strict_int(
            _mapping_value(entry, "start_t_ns", label="semantic phase"),
            label="start_t_ns",
            minimum=0,
        )
        end = _strict_int(
            _mapping_value(entry, "end_t_ns", label="semantic phase"),
            label="end_t_ns",
            minimum=0,
        )
        terminal = entry.get("include_session_terminal_point", False)
        if type(terminal) is not bool:
            raise TypeError("include_session_terminal_point must be boolean")
        phase_id, event_id = scope_id, None
    elif semantic_path == "semantic.baselines":
        scope_id = _strict_string(
            _mapping_value(entry, "baseline_id", label="semantic baseline"),
            label="baseline_id",
        )
        start = _strict_int(
            _mapping_value(entry, "start_t_ns", label="semantic baseline"),
            label="start_t_ns",
            minimum=0,
        )
        end = _strict_int(
            _mapping_value(entry, "end_t_ns", label="semantic baseline"),
            label="end_t_ns",
            minimum=0,
        )
        terminal = False
        phase_id, event_id = None, None
    else:
        scope_id = _strict_string(
            _mapping_value(entry, "event_id", label="semantic event"),
            label="event_id",
        )
        start = _strict_int(
            _mapping_value(entry, "t_ns", label="semantic event"),
            label="t_ns",
            minimum=0,
        )
        duration = _strict_optional_int(
            entry.get("duration_ns"),
            label="duration_ns",
            minimum=1,
        )
        opportunity_end = _strict_optional_int(
            entry.get("opportunity_end_t_ns"),
            label="opportunity_end_t_ns",
            minimum=0,
        )
        if event_span == "duration":
            if duration is None:
                raise ValueError("duration event windows require duration_ns")
            end = start + duration
        elif event_span == "opportunity":
            if opportunity_end is None:
                raise ValueError("opportunity event windows require opportunity_end_t_ns")
            end = opportunity_end
        elif opportunity_end is not None:
            end = opportunity_end
        elif duration is not None:
            end = start + duration
        else:
            raise ValueError("event span requires duration or opportunity end")
        terminal = False
        phase = entry.get("phase_id")
        phase_id = None if phase is None else _strict_string(phase, label="phase_id")
        event_id = scope_id
    if end <= start:
        raise ValueError("semantic scopes must have positive half-open spans")
    return _SemanticSpan(scope_id, start, end, end, phase_id, event_id, terminal)


def _optional_recipe_int(
    recipe: Mapping[str, JsonValue],
    key: str,
) -> int | None:
    return _strict_optional_int(recipe.get(key), label=key, minimum=0)


def _clip_span(
    span: _SemanticSpan,
    *,
    clip_start_t_ns: int | None,
    clip_end_t_ns: int | None,
) -> _SemanticSpan | None:
    start = (
        max(span.start_t_ns, clip_start_t_ns) if clip_start_t_ns is not None else span.start_t_ns
    )
    end = min(span.end_t_ns, clip_end_t_ns) if clip_end_t_ns is not None else span.end_t_ns
    if end <= start:
        return None
    return _SemanticSpan(
        scope_id=span.scope_id,
        start_t_ns=start,
        end_t_ns=end,
        original_end_t_ns=span.original_end_t_ns,
        phase_id=span.phase_id,
        event_id=span.event_id,
        include_session_terminal_point=(
            span.include_session_terminal_point and end == span.original_end_t_ns
        ),
    )


def _fixed_window_bounds(
    span: _SemanticSpan, length_ns: int, step_ns: int
) -> tuple[tuple[int, int], ...]:
    if span.end_t_ns - span.start_t_ns <= length_ns:
        return ((span.start_t_ns, span.end_t_ns),)
    bounds: list[tuple[int, int]] = []
    start = span.start_t_ns
    while start + length_ns <= span.end_t_ns:
        bounds.append((start, start + length_ns))
        start += step_ns
    tail = (span.end_t_ns - length_ns, span.end_t_ns)
    if tail not in bounds:
        bounds.append(tail)
    return tuple(sorted(bounds))


def build_semantic_windows_v1(
    semantic_scope: ProjectedSemanticScope,
    temporal_recipe: Mapping[str, JsonValue],
) -> tuple[SourceWindowV2, ...]:
    """Build canonical half-open windows from a positive semantic projection.

    The v1 recipe requires ``semantic_path``, ``window_policy`` and
    ``window_id_prefix``.  ``semantic-span-v1`` emits one clipped window per
    scope. ``fixed-full-with-end-tail-v1`` additionally requires positive
    ``window_length_ns`` and ``window_step_ns``; short scopes stay whole and a
    single deduplicated end-aligned tail closes an uncovered suffix.
    """

    if not isinstance(semantic_scope, ProjectedSemanticScope):
        raise TypeError("semantic_scope must be ProjectedSemanticScope")
    if not isinstance(temporal_recipe, Mapping):
        raise TypeError("temporal_recipe must be a mapping")
    semantic_path = _strict_string(
        temporal_recipe.get("semantic_path"),
        label="semantic_path",
    )
    if semantic_path not in _SEMANTIC_PATHS:
        raise ValueError("semantic_path is not supported by semantic windows v1")
    policy = _strict_string(
        temporal_recipe.get("window_policy"),
        label="window_policy",
    )
    if policy not in _WINDOW_POLICIES:
        raise ValueError("window_policy is not supported by semantic windows v1")
    prefix = _strict_string(
        temporal_recipe.get("window_id_prefix"),
        label="window_id_prefix",
    )
    raw_entries = semantic_scope.values.get(semantic_path)
    if not isinstance(raw_entries, (tuple, list)):
        raise ValueError(f"semantic scope does not contain a sequence at {semantic_path}")

    event_span_raw = temporal_recipe.get("event_span", "auto")
    event_span = _strict_string(event_span_raw, label="event_span")
    if event_span not in {"auto", "duration", "opportunity"}:
        raise ValueError("event_span must be auto, duration, or opportunity")
    spans: list[_SemanticSpan] = []
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, Mapping):
            raise TypeError(f"{semantic_path}[{index}] must be a mapping")
        spans.append(
            _semantic_span_from_entry(
                semantic_path,
                raw_entry,
                event_span=event_span,
            )
        )
    if len({item.scope_id for item in spans}) != len(spans):
        raise ValueError("semantic scope IDs must be unique")

    raw_scope_ids = temporal_recipe.get("scope_ids")
    if raw_scope_ids is None:
        selected_ids = {item.scope_id for item in spans}
    else:
        if isinstance(raw_scope_ids, (str, bytes)) or not isinstance(raw_scope_ids, (tuple, list)):
            raise TypeError("scope_ids must be an ordered sequence")
        normalized_scope_ids = tuple(
            _strict_string(value, label=f"scope_ids[{index}]")
            for index, value in enumerate(raw_scope_ids)
        )
        if len(normalized_scope_ids) != len(set(normalized_scope_ids)):
            raise ValueError("scope_ids must be unique")
        selected_ids = set(normalized_scope_ids)
        missing = selected_ids - {item.scope_id for item in spans}
        if missing:
            raise ValueError("scope_ids contain identities absent from the semantic projection")

    clip_start = _optional_recipe_int(temporal_recipe, "clip_start_t_ns")
    clip_end = _optional_recipe_int(temporal_recipe, "clip_end_t_ns")
    if clip_start is not None and clip_end is not None and clip_end <= clip_start:
        raise ValueError("clip bounds must define a positive half-open span")
    clipped = [
        value
        for span in spans
        if span.scope_id in selected_ids
        and (
            value := _clip_span(
                span,
                clip_start_t_ns=clip_start,
                clip_end_t_ns=clip_end,
            )
        )
        is not None
    ]
    clipped.sort(key=lambda item: (item.start_t_ns, item.end_t_ns, item.scope_id))

    length_ns: int | None = None
    step_ns: int | None = None
    if policy == "fixed-full-with-end-tail-v1":
        length_ns = _strict_int(
            temporal_recipe.get("window_length_ns"),
            label="window_length_ns",
            minimum=1,
        )
        step_ns = _strict_int(
            temporal_recipe.get("window_step_ns"),
            label="window_step_ns",
            minimum=1,
        )

    windows: list[SourceWindowV2] = []
    for span in clipped:
        if policy == "semantic-span-v1":
            bounds = ((span.start_t_ns, span.end_t_ns),)
        else:
            assert length_ns is not None and step_ns is not None
            bounds = _fixed_window_bounds(span, length_ns, step_ns)
        for local_index, (start, end) in enumerate(bounds):
            windows.append(
                SourceWindowV2(
                    window_id=f"{prefix}-{span.scope_id}-{local_index:04d}",
                    start_t_ns=start,
                    end_t_ns=end,
                    phase_id=span.phase_id,
                    event_id=span.event_id,
                    include_session_terminal_point=(
                        span.include_session_terminal_point and end == span.original_end_t_ns
                    ),
                )
            )
    return tuple(windows)


__all__ = [
    "SupportInterval",
    "TemporalSupport",
    "build_semantic_windows_v1",
    "decimal_grid_v1",
    "left_hold_integral_v1",
    "nearest_within_v1",
    "reconstruct_point_support",
    "validate_reported_gap_metrics",
]
