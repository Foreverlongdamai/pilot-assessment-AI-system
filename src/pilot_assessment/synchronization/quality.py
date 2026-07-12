"""Deterministic native-rate temporal quality and scene/gaze diagnostics."""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import NoReturn, cast

import polars as pl

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.synchronization import (
    ClockMappingSummary,
    IntervalTemporalArtifactMetrics,
    PointTemporalArtifactMetrics,
    SceneGazeMetrics,
    SessionWindow,
    SynchronizationPolicy,
)
from pilot_assessment.synchronization.bindings import TemporalAlignmentError
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
)


def _raise_temporal_issue(
    error_code: str,
    message: str,
    *,
    remediation: str,
    field_or_path: str | None = None,
) -> NoReturn:
    raise TemporalAlignmentError(
        DomainErrorData(
            error_code=error_code,
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message=message,
            field_or_path=field_or_path,
            remediation=remediation,
        )
    )


def _raise_quality_error(message: str, *, field_or_path: str | None = None) -> NoReturn:
    _raise_temporal_issue(
        "TEMPORAL_ORDER_INVALID",
        message,
        remediation="Recreate the aligned artifact from its declared temporal binding and retry.",
        field_or_path=field_or_path,
    )


def _raise_scene_structure_error(
    message: str,
    *,
    field_or_path: str | None = None,
) -> NoReturn:
    _raise_temporal_issue(
        "TEMPORAL_PARENT_KEY_INVALID",
        message,
        remediation=(
            "Recreate aligned scene and gaze artifacts with the declared frame relationship."
        ),
        field_or_path=field_or_path,
    )


def _require_columns(
    frame: pl.DataFrame,
    expected: dict[str, pl.DataType | type[pl.DataType]],
) -> None:
    for column, dtype in expected.items():
        if (
            column not in frame.columns
            or frame.schema[column] != dtype
            or frame[column].null_count()
        ):
            _raise_quality_error(
                "Aligned temporal quality columns have an invalid schema or null values.",
                field_or_path=column,
            )


def _require_stable_keys(
    frame: pl.DataFrame,
    stable_keys: tuple[str, ...],
    *,
    require_unique: bool,
) -> None:
    if any(column not in frame.columns for column in stable_keys):
        _raise_quality_error("Aligned temporal quality rows are missing stable keys.")
    stable = frame.select(stable_keys)
    if any(stable[column].null_count() for column in stable.columns):
        _raise_quality_error("Aligned temporal quality stable keys contain null values.")
    if require_unique and stable.is_duplicated().any():
        _raise_quality_error("Aligned temporal quality stable keys must identify unique rows.")


def _ordered_point_frame(
    frame: pl.DataFrame,
    binding: PointBinding | InheritBinding,
) -> pl.DataFrame:
    target = binding.target_timestamp_column
    order_columns = [target, *binding.stable_keys]
    _require_stable_keys(frame, binding.stable_keys, require_unique=True)
    if isinstance(binding, InheritBinding):
        return frame.sort(order_columns, maintain_order=True)

    rows = frame.select(order_columns).rows()
    try:
        if any(current < previous for previous, current in pairwise(rows)):
            _raise_quality_error(
                "Aligned point rows violate their mapped-time and stable-key order."
            )
    except TypeError:
        _raise_quality_error("Aligned point stable keys do not have a comparable order.")
    return frame


def _exact_median(values: list[int]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Decimal(ordered[middle])
    return (Decimal(ordered[middle - 1]) + Decimal(ordered[middle])) / Decimal(2)


def _period_statistics(
    times: list[int],
    policy: SynchronizationPolicy,
) -> tuple[float | None, int | None, int, int | None]:
    positive_deltas = [
        current - previous for previous, current in pairwise(times) if current > previous
    ]
    if not positive_deltas:
        return None, None, 0, None

    median = _exact_median(positive_deltas)
    threshold_decimal = median * Decimal(str(policy.gap_detection_multiplier))
    threshold = int(threshold_decimal.to_integral_value(rounding=ROUND_HALF_EVEN))
    gap_count = sum(delta > threshold for delta in positive_deltas)
    return float(median), threshold, gap_count, max(positive_deltas)


def compute_point_metrics(
    frame: pl.DataFrame,
    binding: PointBinding | InheritBinding,
    clock: ClockMappingSummary,
    window: SessionWindow,
    policy: SynchronizationPolicy,
) -> PointTemporalArtifactMetrics:
    """Report point/inherited coverage without changing native rows or clock evidence."""

    del clock  # Residual evidence remains unchanged on the caller-owned clock summary.
    try:
        target = binding.target_timestamp_column
        in_session_column = binding.in_session_column
        _require_columns(frame, {target: pl.Int64, in_session_column: pl.Boolean})
        diagnostic_frame = _ordered_point_frame(frame, binding)

        all_times = cast(list[int], frame[target].to_list())
        actual_masks = cast(list[bool], frame[in_session_column].to_list())
        expected_masks = [
            window.start_t_ns <= timestamp <= window.end_t_ns for timestamp in all_times
        ]
        if actual_masks != expected_masks:
            _raise_quality_error(
                "Aligned point session flags do not match the canonical closed session window.",
                field_or_path=in_session_column,
            )

        duplicate_counts = Counter(all_times)
        duplicate_timestamp_groups = sum(count > 1 for count in duplicate_counts.values())
        duplicate_timestamp_rows = sum(count for count in duplicate_counts.values() if count > 1)

        diagnostic_times = cast(list[int], diagnostic_frame[target].to_list())
        diagnostic_masks = cast(list[bool], diagnostic_frame[in_session_column].to_list())
        in_session_times = [
            timestamp
            for timestamp, in_session in zip(
                diagnostic_times,
                diagnostic_masks,
                strict=True,
            )
            if in_session
        ]
        median, threshold, gap_count, max_gap = _period_statistics(in_session_times, policy)

        first_mapped = min(all_times) if all_times else None
        last_mapped = max(all_times) if all_times else None
        in_session_start = min(in_session_times) if in_session_times else None
        in_session_end = max(in_session_times) if in_session_times else None
        in_session_span = (
            in_session_end - in_session_start
            if in_session_start is not None and in_session_end is not None
            else None
        )
        session_span_ratio = (
            in_session_span / (window.end_t_ns - window.start_t_ns)
            if in_session_span is not None
            else None
        )

        return PointTemporalArtifactMetrics(
            artifact_role=binding.artifact_role,
            binding_mode=binding.mode,
            source_schema_id=binding.expected_artifact_schema_id,
            aligned_schema_id=binding.aligned_artifact_schema_id,
            total_rows=frame.height,
            in_session_rows=sum(expected_masks),
            before_session_rows=sum(timestamp < window.start_t_ns for timestamp in all_times),
            after_session_rows=sum(timestamp > window.end_t_ns for timestamp in all_times),
            first_mapped_t_ns=first_mapped,
            last_mapped_t_ns=last_mapped,
            in_session_start_t_ns=in_session_start,
            in_session_end_t_ns=in_session_end,
            in_session_span_ns=in_session_span,
            session_span_ratio=session_span_ratio,
            duplicate_timestamp_groups=duplicate_timestamp_groups,
            duplicate_timestamp_rows=duplicate_timestamp_rows,
            median_period_ns=median,
            gap_threshold_ns=threshold,
            gap_count=gap_count,
            max_gap_ns=max_gap,
            interpolated_rows=0,
        )
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError):
        _raise_quality_error("Aligned point quality metrics cannot be computed safely.")


def compute_interval_metrics(
    frame: pl.DataFrame,
    binding: IntervalBinding,
    clock: ClockMappingSummary,
    window: SessionWindow,
) -> IntervalTemporalArtifactMetrics:
    """Report closed-window interval coverage without changing native interval rows."""

    del clock  # Residual evidence remains unchanged on the caller-owned clock summary.
    try:
        start_column = binding.target_start_column
        end_column = binding.target_end_column
        overlap_column = binding.overlaps_session_column
        full_column = binding.fully_in_session_column
        _require_columns(
            frame,
            {
                start_column: pl.Int64,
                end_column: pl.Int64,
                overlap_column: pl.Boolean,
                full_column: pl.Boolean,
            },
        )
        _require_stable_keys(frame, binding.stable_keys, require_unique=True)

        starts = cast(list[int], frame[start_column].to_list())
        ends = cast(list[int], frame[end_column].to_list())
        if any(end <= start for start, end in zip(starts, ends, strict=True)):
            _raise_quality_error("Aligned interval endpoints are not strictly ordered.")

        expected_overlaps = [
            end >= window.start_t_ns and start <= window.end_t_ns
            for start, end in zip(starts, ends, strict=True)
        ]
        expected_fully_inside = [
            start >= window.start_t_ns and end <= window.end_t_ns
            for start, end in zip(starts, ends, strict=True)
        ]
        actual_overlaps = cast(list[bool], frame[overlap_column].to_list())
        actual_fully_inside = cast(list[bool], frame[full_column].to_list())
        if actual_overlaps != expected_overlaps or actual_fully_inside != expected_fully_inside:
            _raise_quality_error(
                "Aligned interval relation flags do not match the canonical closed session window."
            )

        return IntervalTemporalArtifactMetrics(
            artifact_role=binding.artifact_role,
            binding_mode="interval",
            source_schema_id=binding.expected_artifact_schema_id,
            aligned_schema_id=binding.aligned_artifact_schema_id,
            total_rows=frame.height,
            before_session_rows=sum(end < window.start_t_ns for end in ends),
            after_session_rows=sum(start > window.end_t_ns for start in starts),
            overlapping_session_rows=sum(expected_overlaps),
            fully_in_session_rows=sum(expected_fully_inside),
            first_start_t_ns=min(starts) if starts else None,
            last_end_t_ns=max(ends) if ends else None,
            interpolated_rows=0,
        )
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError):
        _raise_quality_error("Aligned interval quality metrics cannot be computed safely.")


def _require_scene_gaze_column(
    frame: pl.DataFrame,
    column: str,
    dtype: pl.DataType | type[pl.DataType],
    *,
    allow_null: bool = False,
) -> None:
    if (
        column not in frame.columns
        or frame.schema[column] != dtype
        or (not allow_null and frame[column].null_count())
    ):
        _raise_scene_structure_error(
            "Aligned scene/gaze relationship columns have an invalid schema or null values.",
            field_or_path=column,
        )


def _validate_scene_gaze_structure(
    scene_frames: pl.DataFrame,
    gaze_samples: pl.DataFrame,
    window: SessionWindow,
) -> None:
    for column, dtype in {
        "frame_id": pl.UInt64,
        "t_ns": pl.Int64,
        "in_session": pl.Boolean,
    }.items():
        _require_scene_gaze_column(scene_frames, column, dtype)
    for column, dtype in {
        "gaze_sample_id": pl.UInt64,
        "t_ns": pl.Int64,
        "in_session": pl.Boolean,
    }.items():
        _require_scene_gaze_column(gaze_samples, column, dtype)
    _require_scene_gaze_column(
        gaze_samples,
        "scene_frame_id",
        pl.UInt64,
        allow_null=True,
    )

    if scene_frames.select("frame_id").is_duplicated().any():
        _raise_scene_structure_error("Scene frame IDs must be unique.", field_or_path="frame_id")
    if gaze_samples.select("gaze_sample_id").is_duplicated().any():
        _raise_scene_structure_error(
            "Gaze sample IDs must be unique.",
            field_or_path="gaze_sample_id",
        )

    scene_order = scene_frames.select("t_ns", "frame_id").rows()
    gaze_order = gaze_samples.select("t_ns", "gaze_sample_id").rows()
    try:
        if any(current < previous for previous, current in pairwise(scene_order)):
            _raise_scene_structure_error("Scene frames violate mapped-time and frame-ID order.")
        if any(current < previous for previous, current in pairwise(gaze_order)):
            _raise_scene_structure_error("Gaze samples violate mapped-time and sample-ID order.")
    except TypeError:
        _raise_scene_structure_error("Scene/gaze stable IDs do not have a comparable order.")

    for frame, label in ((scene_frames, "scene"), (gaze_samples, "gaze")):
        times = cast(list[int], frame["t_ns"].to_list())
        masks = cast(list[bool], frame["in_session"].to_list())
        expected = [window.start_t_ns <= value <= window.end_t_ns for value in times]
        if masks != expected:
            _raise_scene_structure_error(
                f"Aligned {label} session flags do not match the canonical closed window.",
                field_or_path="in_session",
            )


def validate_scene_gaze_time(
    scene_frames: pl.DataFrame,
    gaze_samples: pl.DataFrame,
    window: SessionWindow,
    *,
    max_examples: int = 10,
) -> SceneGazeMetrics:
    """Validate gaze foreign keys against scene-frame presentation intervals."""

    if max_examples.__class__ is not int or not 0 <= max_examples <= 10:
        _raise_temporal_issue(
            "SYNCHRONIZATION_INTERNAL_ERROR",
            "Scene/gaze diagnostic example limit is outside the supported contract.",
            remediation=(
                "Call scene/gaze validation with an integer max_examples from 0 through 10."
            ),
            field_or_path="max_examples",
        )

    try:
        _validate_scene_gaze_structure(scene_frames, gaze_samples, window)
        frame_ids = cast(list[int], scene_frames["frame_id"].to_list())
        frame_times = cast(list[int], scene_frames["t_ns"].to_list())
        terminal_active_index = next(
            (
                index
                for index in range(len(frame_times) - 1, -1, -1)
                if frame_times[index] <= window.end_t_ns
            ),
            None,
        )

        presentation_by_frame: dict[int, tuple[int, int | None, bool]] = {}
        for index, (frame_id, frame_time) in enumerate(zip(frame_ids, frame_times, strict=True)):
            if index == terminal_active_index:
                presentation_by_frame[frame_id] = (frame_time, window.end_t_ns, True)
            elif index + 1 < len(frame_times):
                presentation_by_frame[frame_id] = (
                    frame_time,
                    frame_times[index + 1],
                    False,
                )
            else:
                presentation_by_frame[frame_id] = (frame_time, None, False)

        sample_ids = cast(list[int], gaze_samples["gaze_sample_id"].to_list())
        referenced_frames = cast(list[int | None], gaze_samples["scene_frame_id"].to_list())
        gaze_times = cast(list[int], gaze_samples["t_ns"].to_list())
        gaze_masks = cast(list[bool], gaze_samples["in_session"].to_list())

        evaluated = 0
        valid = 0
        invalid_sample_ids: list[int] = []
        valid_deltas: list[int] = []
        for sample_id, referenced_frame, gaze_time, in_session in zip(
            sample_ids,
            referenced_frames,
            gaze_times,
            gaze_masks,
            strict=True,
        ):
            if not in_session:
                continue
            evaluated += 1
            interval = (
                presentation_by_frame.get(referenced_frame)
                if referenced_frame is not None
                else None
            )
            association_valid = False
            frame_start: int | None = None
            if interval is not None:
                frame_start, frame_end, inclusive_end = interval
                if frame_end is not None:
                    association_valid = (
                        frame_start <= gaze_time <= frame_end
                        if inclusive_end
                        else frame_start <= gaze_time < frame_end
                    )
            if association_valid:
                assert frame_start is not None
                valid += 1
                valid_deltas.append(gaze_time - frame_start)
            else:
                invalid_sample_ids.append(sample_id)

        return SceneGazeMetrics(
            evaluated_in_session_gaze_rows=evaluated,
            valid_association_rows=valid,
            invalid_association_count=len(invalid_sample_ids),
            gaze_minus_frame_start_min_ns=min(valid_deltas) if valid_deltas else None,
            gaze_minus_frame_start_max_ns=max(valid_deltas) if valid_deltas else None,
            bounded_invalid_gaze_sample_ids=tuple(invalid_sample_ids[:max_examples]),
        )
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError):
        _raise_scene_structure_error(
            "Aligned scene/gaze presentation intervals cannot be validated safely."
        )


__all__ = [
    "compute_interval_metrics",
    "compute_point_metrics",
    "validate_scene_gaze_time",
]
