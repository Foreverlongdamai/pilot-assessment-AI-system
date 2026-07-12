from __future__ import annotations

from typing import cast

import polars as pl
import pytest

from pilot_assessment.contracts.session import ClockSync
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.bindings import (
    TemporalAlignmentError,
    apply_point_window,
    map_point_artifact,
)
from pilot_assessment.synchronization.profiles import (
    PointBinding,
    load_builtin_temporal_catalog,
)
from pilot_assessment.synchronization.quality import validate_scene_gaze_time
from pilot_assessment.synthetic.modalities import build_gaze, build_scene


def _window(end_t_ns: int = 100) -> SessionWindow:
    return SessionWindow(
        end_t_ns=end_t_ns,
        source="master-clock-x-mapped-coverage-v1",
    )


def _scene(frame_ids: list[int], times: list[int], *, window: SessionWindow) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "frame_id": pl.Series(frame_ids, dtype=pl.UInt64),
            "t_ns": pl.Series(times, dtype=pl.Int64),
            "in_session": pl.Series(
                [window.start_t_ns <= value <= window.end_t_ns for value in times],
                dtype=pl.Boolean,
            ),
        }
    )


def _gaze(
    sample_ids: list[int],
    frame_ids: list[int | None],
    times: list[int],
    *,
    window: SessionWindow,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series(sample_ids, dtype=pl.UInt64),
            "scene_frame_id": pl.Series(frame_ids, dtype=pl.UInt64),
            "t_ns": pl.Series(times, dtype=pl.Int64),
            "in_session": pl.Series(
                [window.start_t_ns <= value <= window.end_t_ns for value in times],
                dtype=pl.Boolean,
            ),
        }
    )


def test_scene_gaze_uses_half_open_intervals_and_inclusive_last_frame_endpoint() -> None:
    window = _window()
    scene = _scene([10, 11, 12], [0, 40, 100], window=window)
    gaze = _gaze(
        list(range(7)),
        [10, 10, 10, 11, 11, 11, 12],
        [0, 39, 40, 40, 99, 100, 100],
        window=window,
    )
    original_scene = scene.clone()
    original_gaze = gaze.clone()

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.evaluated_in_session_gaze_rows == 7
    assert metrics.valid_association_rows == 5
    assert metrics.invalid_association_count == 2
    assert metrics.gaze_minus_frame_start_min_ns == 0
    assert metrics.gaze_minus_frame_start_max_ns == 59
    assert metrics.bounded_invalid_gaze_sample_ids == (2, 5)
    assert scene.equals(original_scene)
    assert gaze.equals(original_gaze)


def test_last_in_session_frame_extends_to_window_end_even_with_after_session_frame() -> None:
    window = _window()
    scene = _scene([1, 2, 3], [0, 50, 110], window=window)
    gaze = _gaze([7], [2], [100], window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.valid_association_rows == 1
    assert metrics.invalid_association_count == 0
    assert metrics.gaze_minus_frame_start_min_ns == 50
    assert metrics.gaze_minus_frame_start_max_ns == 50


def test_before_session_frame_can_cover_in_session_gaze_until_its_next_frame() -> None:
    window = _window()
    scene = _scene([1, 2, 3], [-10, 10, 30], window=window)
    gaze = _gaze([0, 1, 2], [1, 1, 2], [0, 10, 10], window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.valid_association_rows == 2
    assert metrics.invalid_association_count == 1
    assert metrics.gaze_minus_frame_start_min_ns == 0
    assert metrics.gaze_minus_frame_start_max_ns == 10
    assert metrics.bounded_invalid_gaze_sample_ids == (1,)


def test_only_before_session_terminal_frame_remains_active_through_window_end() -> None:
    window = _window()
    scene = _scene([1], [-10], window=window)
    gaze = _gaze([0, 1], [1, 1], [0, 100], window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.evaluated_in_session_gaze_rows == 2
    assert metrics.valid_association_rows == 2
    assert metrics.invalid_association_count == 0
    assert metrics.gaze_minus_frame_start_min_ns == 10
    assert metrics.gaze_minus_frame_start_max_ns == 110


def test_out_of_session_gaze_is_excluded_even_when_reference_is_unknown() -> None:
    window = _window()
    scene = _scene([1, 2], [0, 100], window=window)
    gaze = _gaze([0, 1, 2], [999, 1, 999], [-1, 0, 101], window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.evaluated_in_session_gaze_rows == 1
    assert metrics.valid_association_rows == 1
    assert metrics.invalid_association_count == 0
    assert metrics.bounded_invalid_gaze_sample_ids == ()


def test_unknown_and_null_frame_references_are_invalid_associations() -> None:
    window = _window()
    scene = _scene([1, 2], [0, 100], window=window)
    gaze = _gaze([5, 6], [999, None], [10, 20], window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window)

    assert metrics.evaluated_in_session_gaze_rows == 2
    assert metrics.valid_association_rows == 0
    assert metrics.invalid_association_count == 2
    assert metrics.gaze_minus_frame_start_min_ns is None
    assert metrics.gaze_minus_frame_start_max_ns is None
    assert metrics.bounded_invalid_gaze_sample_ids == (5, 6)


def test_invalid_examples_are_bounded_by_caller_limit_in_input_order() -> None:
    window = _window()
    scene = _scene([1], [0], window=window)
    sample_ids = list(range(20, 8, -1))
    gaze = _gaze(sample_ids, [999] * 12, list(range(12)), window=window)

    metrics = validate_scene_gaze_time(scene, gaze, window, max_examples=3)
    no_examples = validate_scene_gaze_time(scene, gaze, window, max_examples=0)

    assert metrics.invalid_association_count == 12
    assert metrics.bounded_invalid_gaze_sample_ids == (20, 19, 18)
    assert no_examples.bounded_invalid_gaze_sample_ids == ()


@pytest.mark.parametrize("max_examples", [True, 1.0, -1, 11])
def test_max_examples_requires_exact_integer_between_zero_and_ten(max_examples: object) -> None:
    window = _window()
    scene = _scene([1], [0], window=window)
    gaze = _gaze([1], [1], [0], window=window)

    with pytest.raises(TemporalAlignmentError) as caught:
        validate_scene_gaze_time(
            scene,
            gaze,
            window,
            max_examples=max_examples,  # ty: ignore[invalid-argument-type]
        )

    assert caught.value.issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"


@pytest.mark.parametrize(
    "bad_scene",
    [
        pl.DataFrame(
            {
                "t_ns": pl.Series([0], dtype=pl.Int64),
                "in_session": pl.Series([True], dtype=pl.Boolean),
            }
        ),
        pl.DataFrame(
            {
                "frame_id": pl.Series([1], dtype=pl.Int64),
                "t_ns": pl.Series([0], dtype=pl.Int64),
                "in_session": pl.Series([True], dtype=pl.Boolean),
            }
        ),
        pl.DataFrame(
            {
                "frame_id": pl.Series([None], dtype=pl.UInt64),
                "t_ns": pl.Series([0], dtype=pl.Int64),
                "in_session": pl.Series([True], dtype=pl.Boolean),
            }
        ),
        pl.DataFrame(
            {
                "frame_id": pl.Series([1, 1], dtype=pl.UInt64),
                "t_ns": pl.Series([0, 10], dtype=pl.Int64),
                "in_session": pl.Series([True, True], dtype=pl.Boolean),
            }
        ),
    ],
    ids=["missing-frame-id", "wrong-frame-id-dtype", "null-frame-id", "duplicate-frame-id"],
)
def test_invalid_scene_structure_raises_stable_domain_error(bad_scene: pl.DataFrame) -> None:
    window = _window()
    gaze = _gaze([1], [1], [0], window=window)

    with pytest.raises(TemporalAlignmentError) as caught:
        validate_scene_gaze_time(bad_scene, gaze, window)

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


def test_invalid_gaze_schema_or_mask_raises_stable_domain_error() -> None:
    window = _window()
    scene = _scene([1], [0], window=window)
    wrong_dtype = _gaze([1], [1], [0], window=window).with_columns(pl.col("t_ns").cast(pl.UInt64))
    corrupt_mask = _gaze([1], [1], [0], window=window).with_columns(
        pl.lit(False).alias("in_session")
    )

    for bad_gaze in (wrong_dtype, corrupt_mask):
        with pytest.raises(TemporalAlignmentError) as caught:
            validate_scene_gaze_time(scene, bad_gaze, window)
        assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


@pytest.mark.parametrize(
    ("duration_s", "expected_evaluated"),
    [(2.0, 240), (29.01, 3_481)],
)
def test_synthetic_gaze_has_zero_invalid_in_session_associations(
    duration_s: float,
    expected_evaluated: int,
) -> None:
    scene = build_scene(duration_s=duration_s, seed=20260711)
    gaze = build_gaze(duration_s=duration_s, seed=20260711, scene=scene)
    catalog = load_builtin_temporal_catalog()
    scene_binding = cast(
        PointBinding,
        catalog.streams_by_schema["vr-scene-source-bundle-v0.1"].bindings_by_role["frame_index"],
    )
    gaze_binding = cast(
        PointBinding,
        catalog.streams_by_schema["gaze-source-bundle-v0.1"].bindings_by_role["gaze_samples"],
    )
    window = _window(end_t_ns=round(duration_s * 1_000_000_000))
    scene_clock = ClockSync(
        method="synthetic-declared-v0.1",
        scale=1.0,
        offset_ns=4_000_000,
        drift_ppm=0.0,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
    )
    gaze_clock = ClockSync(
        method="synthetic-declared-v0.1",
        scale=1.00002,
        offset_ns=7_000_000,
        drift_ppm=20.0,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
    )
    aligned_scene = apply_point_window(
        map_point_artifact(scene.frame_index, scene_binding, scene_clock),
        scene_binding,
        window,
    )
    aligned_gaze = apply_point_window(
        map_point_artifact(gaze.samples, gaze_binding, gaze_clock),
        gaze_binding,
        window,
    )

    metrics = validate_scene_gaze_time(aligned_scene, aligned_gaze, window)

    assert metrics.evaluated_in_session_gaze_rows == expected_evaluated
    assert metrics.valid_association_rows == expected_evaluated
    assert metrics.invalid_association_count == 0
    assert metrics.bounded_invalid_gaze_sample_ids == ()
