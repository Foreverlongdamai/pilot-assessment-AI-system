from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from decimal import Decimal

import polars as pl
import pytest

from pilot_assessment.anchors.models import AnchorRequestValidationError
from pilot_assessment.anchors.protocols import ProjectedSemanticScope
from pilot_assessment.anchors.temporal import (
    SupportInterval,
    TemporalSupport,
    build_semantic_windows_v1,
    decimal_grid_v1,
    left_hold_integral_v1,
    nearest_within_v1,
    reconstruct_point_support,
    validate_reported_gap_metrics,
)
from pilot_assessment.contracts.synchronization import PointTemporalArtifactMetrics


def _point_frame() -> pl.DataFrame:
    # Deliberately not in temporal order. The two rows at 10 ns prove that the
    # stable key, rather than input order, resolves a duplicate timestamp.
    return pl.DataFrame(
        {
            "t_ns": [20, 0, 10, 10, 51, 81, 999],
            "source_row_id": ["d", "a", "c", "b", "e", "f", "z"],
            "in_session": [True, True, True, True, True, True, False],
        },
        schema={"t_ns": pl.Int64, "source_row_id": pl.String, "in_session": pl.Boolean},
    )


def _reported_metrics(
    *, gap_count: int = 1, max_gap_ns: int | None = 31
) -> PointTemporalArtifactMetrics:
    return PointTemporalArtifactMetrics(
        artifact_role="samples",
        binding_mode="point",
        source_schema_id="x-source-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        total_rows=6,
        in_session_rows=6,
        before_session_rows=0,
        after_session_rows=0,
        first_mapped_t_ns=0,
        last_mapped_t_ns=81,
        in_session_start_t_ns=0,
        in_session_end_t_ns=81,
        in_session_span_ns=81,
        session_span_ratio=0.9,
        duplicate_timestamp_groups=1,
        duplicate_timestamp_rows=2,
        median_period_ns=20.0,
        gap_threshold_ns=30,
        gap_count=gap_count,
        max_gap_ns=max_gap_ns,
        interpolated_rows=0,
    )


def test_reconstruct_point_support_orders_stably_and_never_spans_a_gap() -> None:
    frame = _point_frame()
    original = frame.clone()

    support = reconstruct_point_support(
        frame,
        timestamp_column="t_ns",
        stable_keys=("source_row_id",),
        in_session_column="in_session",
        gap_threshold_ns=30,
        semantic_end_t_ns=90,
    )

    assert support == TemporalSupport(
        intervals=(
            SupportInterval(0, 10, 1),
            SupportInterval(10, 10, 3),
            SupportInterval(10, 20, 2),
            SupportInterval(20, 20, 0),
            SupportInterval(51, 81, 4),
            SupportInterval(81, 90, 5),
        ),
        segment_bounds=((0, 20), (51, 90)),
        observed_duration_ns=59,
        gap_count=1,
        max_gap_ns=31,
    )
    assert frame.equals(original)


def test_support_without_explicit_semantic_end_does_not_extend_the_terminal_sample() -> None:
    support = reconstruct_point_support(
        _point_frame(),
        "t_ns",
        ("source_row_id",),
        "in_session",
        30,
        None,
    )

    assert support.intervals[-1] == SupportInterval(81, 81, 5)
    assert support.segment_bounds[-1] == (51, 81)
    assert support.observed_duration_ns == 50


def test_left_hold_integral_uses_source_row_indexes_and_zero_duration_duplicates() -> None:
    support = reconstruct_point_support(
        _point_frame(),
        "t_ns",
        ("source_row_id",),
        "in_session",
        30,
        90,
    )

    assert left_hold_integral_v1([4.0, 1.0, 3.0, 2.0, 5.0, 6.0, 999.0], support) == 244.0
    with pytest.raises(ValueError, match="finite"):
        left_hold_integral_v1([4.0, 1.0, math.nan, 2.0, 5.0, 6.0], support)


@pytest.mark.parametrize(
    ("reported", "reason"),
    [
        (_reported_metrics(gap_count=0), "gap_count_mismatch"),
        (_reported_metrics(max_gap_ns=30), "max_gap_ns_mismatch"),
    ],
)
def test_reported_gap_mismatch_is_a_pre_request_failure(
    reported: PointTemporalArtifactMetrics, reason: str
) -> None:
    support = reconstruct_point_support(
        _point_frame(),
        "t_ns",
        ("source_row_id",),
        "in_session",
        30,
        90,
    )

    with pytest.raises(AnchorRequestValidationError) as caught:
        validate_reported_gap_metrics(support, reported)

    assert caught.value.code == "request_semantic_identity_mismatch"
    assert caught.value.details["reason"] == reason


def test_reported_gap_metrics_accept_the_same_reconstruction() -> None:
    support = reconstruct_point_support(
        _point_frame(),
        "t_ns",
        ("source_row_id",),
        "in_session",
        30,
        90,
    )
    validate_reported_gap_metrics(support, _reported_metrics())


def test_decimal_grid_uses_absolute_decimal_round_half_even_and_is_half_open() -> None:
    assert decimal_grid_v1(0, 9, Decimal("400000000")) == (0, 2, 5, 8)
    assert decimal_grid_v1(1, 9, Decimal("400000000")) == (1, 4, 6, 8)
    assert decimal_grid_v1(5, 5, Decimal("100")) == ()


def test_nearest_matching_uses_earlier_time_then_stable_id_without_extrapolation() -> None:
    right_times = [20, 10, 10, 30]
    right_ids = ["z", "b", "a", "c"]

    assert nearest_within_v1([5, 10, 15, 25, 35], right_times, right_ids, tolerance_ns=10) == (
        None,
        2,
        2,
        0,
        None,
    )
    assert right_times == [20, 10, 10, 30]
    assert right_ids == ["z", "b", "a", "c"]


def test_semantic_span_windows_are_chronological_and_half_open_clipped() -> None:
    scope = ProjectedSemanticScope(
        values={
            "semantic.phases": [
                {
                    "phase_id": "phase-b",
                    "start_t_ns": 20,
                    "end_t_ns": 50,
                    "include_session_terminal_point": True,
                },
                {
                    "phase_id": "phase-a",
                    "start_t_ns": 0,
                    "end_t_ns": 20,
                    "include_session_terminal_point": False,
                },
            ]
        }
    )

    windows = build_semantic_windows_v1(
        scope,
        {
            "semantic_path": "semantic.phases",
            "window_policy": "semantic-span-v1",
            "window_id_prefix": "analysis",
            "clip_start_t_ns": 5,
            "clip_end_t_ns": 40,
        },
    )

    assert [window.model_dump(mode="json") for window in windows] == [
        {
            "window_id": "analysis-phase-a-0000",
            "start_t_ns": 5,
            "end_t_ns": 20,
            "phase_id": "phase-a",
            "event_id": None,
            "include_session_terminal_point": False,
        },
        {
            "window_id": "analysis-phase-b-0000",
            "start_t_ns": 20,
            "end_t_ns": 40,
            "phase_id": "phase-b",
            "event_id": None,
            "include_session_terminal_point": False,
        },
    ]


def test_fixed_windows_keep_short_span_and_add_one_deduplicated_end_tail() -> None:
    scope = ProjectedSemanticScope(
        values={
            "semantic.phases": [
                {
                    "phase_id": "short",
                    "start_t_ns": 0,
                    "end_t_ns": 3,
                    "include_session_terminal_point": False,
                },
                {
                    "phase_id": "long",
                    "start_t_ns": 10,
                    "end_t_ns": 21,
                    "include_session_terminal_point": True,
                },
            ]
        }
    )

    windows = build_semantic_windows_v1(
        scope,
        {
            "semantic_path": "semantic.phases",
            "window_policy": "fixed-full-with-end-tail-v1",
            "window_id_prefix": "window",
            "window_length_ns": 4,
            "window_step_ns": 3,
        },
    )

    assert [(item.start_t_ns, item.end_t_ns) for item in windows] == [
        (0, 3),
        (10, 14),
        (13, 17),
        (16, 20),
        (17, 21),
    ]
    assert windows[-1].include_session_terminal_point is True
    assert len({item.window_id for item in windows}) == len(windows)


def test_temporal_models_and_scope_inputs_remain_immutable() -> None:
    interval = SupportInterval(0, 1, 0)
    with pytest.raises(FrozenInstanceError):
        interval.end_t_ns = 2  # type: ignore[misc]

    phase = {
        "phase_id": "phase-a",
        "start_t_ns": 0,
        "end_t_ns": 10,
        "include_session_terminal_point": False,
    }
    scope = ProjectedSemanticScope(values={"semantic.phases": [phase]})
    phase["end_t_ns"] = 20
    windows = build_semantic_windows_v1(
        scope,
        {
            "semantic_path": "semantic.phases",
            "window_policy": "semantic-span-v1",
            "window_id_prefix": "immutable",
        },
    )
    assert windows[0].end_t_ns == 10
