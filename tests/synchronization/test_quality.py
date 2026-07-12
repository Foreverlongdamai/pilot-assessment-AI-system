from __future__ import annotations

import polars as pl
import pytest

from pilot_assessment.contracts.synchronization import (
    MAX_SESSION_END_NS_V0_1,
    ClockMappingSummary,
    SessionWindow,
    SynchronizationPolicy,
)
from pilot_assessment.synchronization.bindings import TemporalAlignmentError
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
)
from pilot_assessment.synchronization.quality import (
    compute_interval_metrics,
    compute_point_metrics,
)


def _point_binding() -> PointBinding:
    return PointBinding(
        mode="point",
        artifact_role="samples",
        expected_artifact_schema_id="fixture-source-v0.1",
        aligned_artifact_schema_id="fixture-aligned-v0.1",
        source_timestamp_column="source_timestamp_s",
        stable_keys=("sample_id",),
    )


def _inherit_binding() -> InheritBinding:
    return InheritBinding(
        mode="inherit",
        artifact_role="aoi_instances",
        expected_artifact_schema_id="fixture-child-source-v0.1",
        aligned_artifact_schema_id="fixture-child-aligned-v0.1",
        parent_role="frame_index",
        parent_key_columns=("frame_id",),
        foreign_key_columns=("frame_id",),
        stable_keys=("frame_id", "aoi_id"),
    )


def _interval_binding() -> IntervalBinding:
    return IntervalBinding(
        mode="interval",
        artifact_role="fixations",
        expected_artifact_schema_id="fixture-interval-source-v0.1",
        aligned_artifact_schema_id="fixture-interval-aligned-v0.1",
        source_start_column="start_source_timestamp_s",
        source_end_column="end_source_timestamp_s",
        stable_keys=("fixation_id",),
    )


def _clock() -> ClockMappingSummary:
    return ClockMappingSummary(
        clock_id="fixture_clock",
        method="fixture-declared-v0.1",
        scale=1.0,
        offset_ns=0,
        drift_ppm=0.0,
        residual_rms_ms=0.125,
        residual_max_ms=0.5,
        declaration_consistent=True,
    )


def _window(end_t_ns: int = 100) -> SessionWindow:
    return SessionWindow(
        end_t_ns=end_t_ns,
        source="master-clock-x-mapped-coverage-v1",
    )


def _point_frame(times: list[int], *, window: SessionWindow) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "sample_id": range(len(times)),
            "t_ns": pl.Series(times, dtype=pl.Int64),
            "in_session": pl.Series(
                [window.start_t_ns <= value <= window.end_t_ns for value in times],
                dtype=pl.Boolean,
            ),
        }
    )


def test_point_metrics_report_exact_partitions_bounds_span_and_schema_identity() -> None:
    window = _window()
    frame = _point_frame([-5, 0, 25, 100, 101], window=window)
    original = frame.clone()

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.artifact_role == "samples"
    assert metrics.binding_mode == "point"
    assert metrics.source_schema_id == "fixture-source-v0.1"
    assert metrics.aligned_schema_id == "fixture-aligned-v0.1"
    assert metrics.total_rows == 5
    assert metrics.in_session_rows == 3
    assert metrics.before_session_rows == 1
    assert metrics.after_session_rows == 1
    assert metrics.first_mapped_t_ns == -5
    assert metrics.last_mapped_t_ns == 101
    assert metrics.in_session_start_t_ns == 0
    assert metrics.in_session_end_t_ns == 100
    assert metrics.in_session_span_ns == 100
    assert metrics.session_span_ratio == 1.0
    assert metrics.interpolated_rows == 0
    assert frame.equals(original)


def test_duplicate_metrics_count_groups_and_every_participating_row_before_zero_removal() -> None:
    window = _window(end_t_ns=2)
    frame = _point_frame([0, 0, 1, 2, 2, 2], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.duplicate_timestamp_groups == 2
    assert metrics.duplicate_timestamp_rows == 5
    assert metrics.median_period_ns == 1.0
    assert metrics.gap_threshold_ns == 5
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns == 1


def test_duplicate_metrics_include_before_and_after_rows() -> None:
    window = _window(end_t_ns=10)
    frame = _point_frame([-2, -2, 0, 10, 12, 12], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.duplicate_timestamp_groups == 2
    assert metrics.duplicate_timestamp_rows == 4
    assert metrics.median_period_ns == 10.0
    assert metrics.max_gap_ns == 10


def test_gap_rule_is_strict_and_does_not_count_delta_equal_to_threshold() -> None:
    window = _window(end_t_ns=131)
    frame = _point_frame([0, 10, 20, 30, 80, 131], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.median_period_ns == 10.0
    assert metrics.gap_threshold_ns == 50
    assert metrics.gap_count == 1
    assert metrics.max_gap_ns == 51


def test_even_positive_delta_sample_uses_exact_half_median_and_half_even_threshold() -> None:
    window = _window(end_t_ns=3)
    frame = _point_frame([0, 1, 3], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.median_period_ns == 1.5
    assert metrics.gap_threshold_ns == 8
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns == 2


def test_half_even_threshold_rounds_twelve_point_five_down_to_twelve() -> None:
    window = _window(end_t_ns=5)
    frame = _point_frame([0, 2, 5], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.median_period_ns == 2.5
    assert metrics.gap_threshold_ns == 12


def test_largest_session_window_preserves_half_ns_median_and_safe_threshold() -> None:
    maximum_end_t_ns = MAX_SESSION_END_NS_V0_1
    first_delta = 2**51 - 1
    window = _window(end_t_ns=maximum_end_t_ns)
    frame = _point_frame([0, first_delta, maximum_end_t_ns], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.median_period_ns == 2_251_799_813_685_247.5
    assert metrics.gap_threshold_ns == 11_258_999_068_426_238
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns == 2**51


def test_single_in_session_row_has_zero_span_and_null_period_statistics() -> None:
    window = _window()
    frame = _point_frame([50], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.in_session_span_ns == 0
    assert metrics.session_span_ratio == 0.0
    assert metrics.median_period_ns is None
    assert metrics.gap_threshold_ns is None
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns is None


def test_only_zero_deltas_have_null_period_statistics_without_losing_duplicates() -> None:
    window = _window()
    frame = _point_frame([10, 10], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.duplicate_timestamp_groups == 1
    assert metrics.duplicate_timestamp_rows == 2
    assert metrics.median_period_ns is None
    assert metrics.gap_threshold_ns is None
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns is None


def test_no_in_session_rows_have_no_inner_bounds_or_period_statistics() -> None:
    window = _window()
    frame = _point_frame([-2, -1, 101, 102], window=window)

    metrics = compute_point_metrics(
        frame,
        _point_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.in_session_rows == 0
    assert metrics.before_session_rows == 2
    assert metrics.after_session_rows == 2
    assert metrics.in_session_start_t_ns is None
    assert metrics.in_session_end_t_ns is None
    assert metrics.in_session_span_ns is None
    assert metrics.session_span_ratio is None
    assert metrics.median_period_ns is None
    assert metrics.gap_threshold_ns is None
    assert metrics.gap_count == 0
    assert metrics.max_gap_ns is None


def test_inherit_metrics_use_inherited_time_without_changing_binding_mode() -> None:
    window = _window(end_t_ns=10)
    frame = pl.DataFrame(
        {
            "frame_id": pl.Series([0, 0, 1], dtype=pl.UInt64),
            "aoi_id": ["a", "b", "a"],
            "t_ns": pl.Series([0, 0, 10], dtype=pl.Int64),
            "in_session": pl.Series([True, True, True], dtype=pl.Boolean),
        }
    )

    metrics = compute_point_metrics(
        frame,
        _inherit_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.binding_mode == "inherit"
    assert metrics.duplicate_timestamp_groups == 1
    assert metrics.duplicate_timestamp_rows == 2
    assert metrics.median_period_ns == 10.0


def test_inherit_metrics_use_sorted_diagnostic_copy_for_nonadjacent_duplicates() -> None:
    window = _window(end_t_ns=20)
    frame = pl.DataFrame(
        {
            "frame_id": pl.Series([2, 0, 1], dtype=pl.UInt64),
            "aoi_id": ["a", "a", "a"],
            "t_ns": pl.Series([10, 0, 10], dtype=pl.Int64),
            "in_session": pl.Series([True, True, True], dtype=pl.Boolean),
        }
    )
    original = frame.clone()

    metrics = compute_point_metrics(
        frame,
        _inherit_binding(),
        _clock(),
        window,
        SynchronizationPolicy(),
    )

    assert metrics.duplicate_timestamp_groups == 1
    assert metrics.duplicate_timestamp_rows == 2
    assert metrics.median_period_ns == 10.0
    assert metrics.max_gap_ns == 10
    assert frame.equals(original)


def test_point_metrics_reject_negative_delta_without_sorting_source_rows() -> None:
    window = _window()
    frame = _point_frame([0, 10, 5], window=window)

    with pytest.raises(TemporalAlignmentError) as caught:
        compute_point_metrics(
            frame,
            _point_binding(),
            _clock(),
            window,
            SynchronizationPolicy(),
        )

    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_point_metrics_reject_corrupt_session_mask_with_stable_domain_error() -> None:
    window = _window()
    frame = _point_frame([-1, 0, 101], window=window).with_columns(
        pl.Series("in_session", [True, False, True], dtype=pl.Boolean)
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        compute_point_metrics(
            frame,
            _point_binding(),
            _clock(),
            window,
            SynchronizationPolicy(),
        )

    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_quality_computation_preserves_descriptor_clock_residuals() -> None:
    window = _window()
    frame = _point_frame([0, 10], window=window)
    clock = _clock()
    original_clock = clock.model_dump(mode="json")

    compute_point_metrics(
        frame,
        _point_binding(),
        clock,
        window,
        SynchronizationPolicy(),
    )

    assert clock.residual_rms_ms == 0.125
    assert clock.residual_max_ms == 0.5
    assert clock.model_dump(mode="json") == original_clock


def test_interval_metrics_report_exact_partitions_bounds_and_no_interpolation() -> None:
    window = _window()
    frame = pl.DataFrame(
        {
            "fixation_id": [0, 1, 2, 3],
            "start_t_ns": pl.Series([-10, 0, 80, 101], dtype=pl.Int64),
            "end_t_ns": pl.Series([-1, 100, 120, 110], dtype=pl.Int64),
            "overlaps_session": pl.Series([False, True, True, False], dtype=pl.Boolean),
            "fully_in_session": pl.Series([False, True, False, False], dtype=pl.Boolean),
        }
    )
    original = frame.clone()
    clock = _clock()

    metrics = compute_interval_metrics(frame, _interval_binding(), clock, window)

    assert metrics.artifact_role == "fixations"
    assert metrics.binding_mode == "interval"
    assert metrics.source_schema_id == "fixture-interval-source-v0.1"
    assert metrics.aligned_schema_id == "fixture-interval-aligned-v0.1"
    assert metrics.total_rows == 4
    assert metrics.before_session_rows == 1
    assert metrics.after_session_rows == 1
    assert metrics.overlapping_session_rows == 2
    assert metrics.fully_in_session_rows == 1
    assert metrics.first_start_t_ns == -10
    assert metrics.last_end_t_ns == 120
    assert metrics.interpolated_rows == 0
    assert clock.residual_rms_ms == 0.125
    assert clock.residual_max_ms == 0.5
    assert frame.equals(original)


def test_interval_metrics_treat_closed_session_boundaries_as_overlap() -> None:
    window = _window()
    frame = pl.DataFrame(
        {
            "fixation_id": [0, 1],
            "start_t_ns": pl.Series([-10, 100], dtype=pl.Int64),
            "end_t_ns": pl.Series([0, 110], dtype=pl.Int64),
            "overlaps_session": pl.Series([True, True], dtype=pl.Boolean),
            "fully_in_session": pl.Series([False, False], dtype=pl.Boolean),
        }
    )

    metrics = compute_interval_metrics(frame, _interval_binding(), _clock(), window)

    assert metrics.before_session_rows == 0
    assert metrics.after_session_rows == 0
    assert metrics.overlapping_session_rows == 2
    assert metrics.fully_in_session_rows == 0


def test_interval_metrics_reject_corrupt_relation_flags_with_stable_domain_error() -> None:
    frame = pl.DataFrame(
        {
            "fixation_id": [0],
            "start_t_ns": pl.Series([0], dtype=pl.Int64),
            "end_t_ns": pl.Series([10], dtype=pl.Int64),
            "overlaps_session": pl.Series([False], dtype=pl.Boolean),
            "fully_in_session": pl.Series([True], dtype=pl.Boolean),
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        compute_interval_metrics(frame, _interval_binding(), _clock(), _window())

    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_empty_interval_artifact_has_null_bounds() -> None:
    frame = pl.DataFrame(
        schema={
            "fixation_id": pl.Int64,
            "start_t_ns": pl.Int64,
            "end_t_ns": pl.Int64,
            "overlaps_session": pl.Boolean,
            "fully_in_session": pl.Boolean,
        }
    )

    metrics = compute_interval_metrics(frame, _interval_binding(), _clock(), _window())

    assert metrics.total_rows == 0
    assert metrics.first_start_t_ns is None
    assert metrics.last_end_t_ns is None
    assert metrics.interpolated_rows == 0
