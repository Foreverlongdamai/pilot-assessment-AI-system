from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest

from pilot_assessment.contracts.ingestion import StreamReadiness
from pilot_assessment.contracts.session import ClockSync
from pilot_assessment.contracts.synchronization import (
    MAX_SESSION_END_NS_V0_1,
    SessionWindow,
)
from pilot_assessment.synchronization.bindings import (
    TemporalAlignmentError,
    apply_point_window,
    derive_session_window,
    inherit_point_time,
    map_interval_artifact,
    map_point_artifact,
    preserve_untimed_artifact,
)
from pilot_assessment.synchronization.models import SynchronizationInput
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
    UntimedBinding,
    load_builtin_temporal_catalog,
)


def _point_binding(*, stable_keys: tuple[str, ...] = ("sample_id",)) -> PointBinding:
    return PointBinding(
        mode="point",
        artifact_role="samples",
        expected_artifact_schema_id="fixture-source-v0.1",
        aligned_artifact_schema_id="fixture-aligned-v0.1",
        source_timestamp_column="source_timestamp_s",
        stable_keys=stable_keys,
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


def _clock() -> ClockSync:
    return ClockSync(
        method="fixture-declared-v0.1",
        scale=1.0,
        offset_ns=0,
        drift_ppm=0.0,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
    )


def _session_window(end_t_ns: int = 10) -> SessionWindow:
    return SessionWindow(
        end_t_ns=end_t_ns,
        source="master-clock-x-mapped-coverage-v1",
    )


def _synchronization_input(
    *,
    origin: str = "session_start",
    master_clock_id: str = "sim_clock",
    x_clock_id: str = "sim_clock",
    x_readiness: StreamReadiness = StreamReadiness.READY,
    synthetic_duration_s: float = 999.0,
    include_x_in_prepared_inventory: bool = True,
) -> SynchronizationInput:
    manifest = SimpleNamespace(
        session_timebase=SimpleNamespace(
            origin=origin,
            master_clock_id=master_clock_id,
        ),
        extensions={"synthetic": {"duration_s": synthetic_duration_s}},
    )
    value = SimpleNamespace(
        loaded_manifest=SimpleNamespace(manifest=manifest),
        readiness_report=SimpleNamespace(
            stream_results={"X": SimpleNamespace(readiness=x_readiness)}
        ),
        prepared_session=SimpleNamespace(
            streams=(
                {"X": SimpleNamespace(clock_id=x_clock_id)}
                if include_x_in_prepared_inventory
                else {}
            )
        ),
    )
    return cast(SynchronizationInput, value)


def test_point_binding_appends_int64_time_and_boolean_mask_without_mutating_raw() -> None:
    source = pl.DataFrame(
        {
            "sample_id": [0, 1, 2, 3],
            "source_timestamp_s": [-0.000000001, 0.0, 0.000000010, 0.000000011],
            "value": [11.0, 12.0, 13.0, 14.0],
        }
    )
    original = source.clone()
    binding = _point_binding()
    window = _session_window()

    mapped = map_point_artifact(source, binding, _clock())
    aligned = apply_point_window(mapped, binding, window)

    assert source.equals(original)
    assert mapped.columns == [*source.columns, "t_ns"]
    assert aligned.columns == [*source.columns, "t_ns", "in_session"]
    assert aligned.schema["t_ns"] == pl.Int64
    assert aligned.schema["in_session"] == pl.Boolean
    assert aligned["t_ns"].to_list() == [-1, 0, 10, 11]
    assert aligned["in_session"].to_list() == [False, True, True, False]
    assert aligned.height == source.height


def test_point_binding_preserves_raw_column_order_values_and_row_count() -> None:
    source = pl.DataFrame(
        {
            "source_timestamp_s": [0.0, 0.25, 0.5],
            "sample_id": [7, 8, 9],
            "label": ["a", "b", "c"],
            "valid": [True, False, True],
        }
    )

    aligned = apply_point_window(
        map_point_artifact(source, _point_binding(), _clock()),
        _point_binding(),
        _session_window(500_000_000),
    )

    assert aligned.columns == [*source.columns, "t_ns", "in_session"]
    assert aligned.select(source.columns).equals(source)
    assert aligned.height == source.height


def test_point_binding_uses_closed_session_window() -> None:
    source = pl.DataFrame(
        {
            "sample_id": [0, 1],
            "source_timestamp_s": [0.0, 0.000000010],
        }
    )

    aligned = apply_point_window(
        map_point_artifact(source, _point_binding(), _clock()),
        _point_binding(),
        _session_window(),
    )

    assert aligned["t_ns"].to_list() == [0, 10]
    assert aligned["in_session"].to_list() == [True, True]


def test_point_binding_keeps_before_and_after_session_rows() -> None:
    source = pl.DataFrame(
        {
            "sample_id": [0, 1, 2],
            "source_timestamp_s": [-0.000000001, 0.000000005, 0.000000011],
        }
    )

    aligned = apply_point_window(
        map_point_artifact(source, _point_binding(), _clock()),
        _point_binding(),
        _session_window(),
    )

    assert aligned["sample_id"].to_list() == [0, 1, 2]
    assert aligned["t_ns"].to_list() == [-1, 5, 11]
    assert aligned["in_session"].to_list() == [False, True, False]
    assert aligned.height == 3


def test_point_binding_preserves_duplicate_mapped_ns_in_stable_key_order() -> None:
    source = pl.DataFrame(
        {
            "sample_id": [10, 11, 12],
            "source_timestamp_s": [0.0, 0.0000000004, 0.0000000015],
            "value": [1.0, 2.0, 3.0],
        }
    )

    aligned = map_point_artifact(source, _point_binding(), _clock())

    assert aligned["t_ns"].to_list() == [0, 0, 2]
    assert aligned["sample_id"].to_list() == [10, 11, 12]
    assert aligned["value"].to_list() == [1.0, 2.0, 3.0]

    duplicate_key = source.with_columns(pl.Series("sample_id", [10, 10, 12]))
    with pytest.raises(TemporalAlignmentError) as caught:
        map_point_artifact(duplicate_key, _point_binding(), _clock())
    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_point_binding_requires_declared_stable_keys() -> None:
    source = pl.DataFrame({"source_timestamp_s": [0.0, 0.1]})

    with pytest.raises(TemporalAlignmentError) as caught:
        map_point_artifact(source, _point_binding(), _clock())
    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_session_window_uses_max_mapped_x_time_not_synthetic_duration() -> None:
    binding = _point_binding()
    aligned_x = pl.DataFrame(
        {
            "sample_id": [0, 1, 2],
            "source_timestamp_s": [-1.0, 0.0, 0.000000010],
            "t_ns": pl.Series([-1_000_000_000, 0, 10], dtype=pl.Int64),
        }
    )

    window = derive_session_window(
        _synchronization_input(synthetic_duration_s=123_456.0),
        aligned_x,
        binding,
    )

    assert window.start_t_ns == 0
    assert window.end_t_ns == 10
    assert window.source == "master-clock-x-mapped-coverage-v1"


def test_session_window_requires_session_start_origin() -> None:
    aligned_x = pl.DataFrame({"t_ns": pl.Series([0, 10], dtype=pl.Int64)})

    with pytest.raises(ValueError, match="SESSION_WINDOW_UNAVAILABLE"):
        derive_session_window(
            _synchronization_input(origin="first_x_sample"),
            aligned_x,
            _point_binding(),
        )


def test_session_window_requires_x_clock_to_match_master_clock() -> None:
    aligned_x = pl.DataFrame({"t_ns": pl.Series([0, 10], dtype=pl.Int64)})

    with pytest.raises(ValueError, match="SESSION_WINDOW_UNAVAILABLE"):
        derive_session_window(
            _synchronization_input(x_clock_id="device_clock"),
            aligned_x,
            _point_binding(),
        )


@pytest.mark.parametrize(
    "mapped",
    [
        pl.Series([], dtype=pl.Int64),
        pl.Series([-1, 0], dtype=pl.Int64),
    ],
)
def test_session_window_requires_positive_end(mapped: pl.Series) -> None:
    aligned_x = pl.DataFrame({"t_ns": mapped})

    with pytest.raises(ValueError, match="SESSION_WINDOW_UNAVAILABLE"):
        derive_session_window(
            _synchronization_input(),
            aligned_x,
            _point_binding(),
        )


def test_session_window_rejects_x_beyond_v0_1_exact_metrics_bound() -> None:
    aligned_x = pl.DataFrame(
        {
            "t_ns": pl.Series(
                [0, MAX_SESSION_END_NS_V0_1 + 1],
                dtype=pl.Int64,
            )
        }
    )

    with pytest.raises(ValueError, match="^SESSION_WINDOW_UNAVAILABLE$"):
        derive_session_window(
            _synchronization_input(),
            aligned_x,
            _point_binding(),
        )


def test_shared_xu_have_identical_time_columns_and_masks() -> None:
    # This locks the point executor only. Task 11 must exercise D-011 with the
    # two actual X/U tables produced by the M2 PreparedSession integration.
    catalog = load_builtin_temporal_catalog()
    x_binding = cast(
        PointBinding,
        catalog.streams_by_schema["flight-state-normalized-v0.1"].bindings_by_role["samples"],
    )
    u_binding = cast(
        PointBinding,
        catalog.streams_by_schema["control-input-normalized-v0.1"].bindings_by_role["samples"],
    )
    shared = pl.DataFrame(
        {
            "source_row_index": [0, 1, 2, 3],
            "source_time_s": [-0.01, 0.0, 0.01, 0.02],
        }
    )
    window = _session_window(10_000_000)

    aligned_x = apply_point_window(
        map_point_artifact(shared, x_binding, _clock()), x_binding, window
    )
    aligned_u = apply_point_window(
        map_point_artifact(shared, u_binding, _clock()), u_binding, window
    )

    assert aligned_x["t_ns"].equals(aligned_u["t_ns"])
    assert aligned_x["in_session"].equals(aligned_u["in_session"])


@pytest.mark.parametrize("bad_time", [None, float("nan"), float("inf"), -float("inf")])
def test_point_binding_rejects_null_or_nonfinite_source_times(bad_time: float | None) -> None:
    source = pl.DataFrame(
        {
            "sample_id": [0, 1],
            "source_timestamp_s": pl.Series([0.0, bad_time], dtype=pl.Float64),
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        map_point_artifact(source, _point_binding(), _clock())
    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_point_binding_rejects_non_float64_source_time_and_null_stable_key() -> None:
    integer_time = pl.DataFrame(
        {
            "sample_id": [0, 1],
            "source_timestamp_s": pl.Series([0, 1], dtype=pl.Int64),
        }
    )
    with pytest.raises(TemporalAlignmentError) as integer_caught:
        map_point_artifact(integer_time, _point_binding(), _clock())
    assert integer_caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"

    null_key = pl.DataFrame(
        {
            "sample_id": pl.Series([0, None], dtype=pl.Int64),
            "source_timestamp_s": [0.0, 0.1],
        }
    )
    with pytest.raises(TemporalAlignmentError) as null_caught:
        map_point_artifact(null_key, _point_binding(), _clock())
    assert null_caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


@pytest.mark.parametrize("existing_column", ["t_ns", "in_session"])
def test_point_binding_rejects_output_column_collisions(existing_column: str) -> None:
    source = pl.DataFrame(
        {
            "sample_id": [0],
            "source_timestamp_s": [0.0],
            existing_column: [0],
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        map_point_artifact(source, _point_binding(), _clock())
    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_point_binding_accepts_empty_typed_table_and_rejects_int64_overflow() -> None:
    empty = pl.DataFrame(
        {
            "sample_id": pl.Series([], dtype=pl.Int64),
            "source_timestamp_s": pl.Series([], dtype=pl.Float64),
        }
    )
    mapped = map_point_artifact(empty, _point_binding(), _clock())
    assert mapped.height == 0
    assert mapped.schema["t_ns"] == pl.Int64

    overflow = pl.DataFrame(
        {
            "sample_id": [0],
            "source_timestamp_s": [float(2**63)],
        }
    )
    with pytest.raises(TemporalAlignmentError) as caught:
        map_point_artifact(overflow, _point_binding(), _clock())
    assert caught.value.issue.error_code == "TIMESTAMP_OUT_OF_INT64_RANGE"


def test_point_binding_rejects_nonmonotonic_time_or_stable_key_order() -> None:
    nonmonotonic_time = pl.DataFrame(
        {
            "sample_id": [0, 1],
            "source_timestamp_s": [1.0, 0.0],
        }
    )
    with pytest.raises(TemporalAlignmentError) as time_caught:
        map_point_artifact(nonmonotonic_time, _point_binding(), _clock())
    assert time_caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"

    unstable_collision = pl.DataFrame(
        {
            "sample_id": [2, 1],
            "source_timestamp_s": [0.0, 0.0000000004],
        }
    )
    with pytest.raises(TemporalAlignmentError) as key_caught:
        map_point_artifact(unstable_collision, _point_binding(), _clock())
    assert key_caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_session_window_rejects_nonready_x_and_non_int64_mapped_time() -> None:
    aligned_x = pl.DataFrame({"t_ns": pl.Series([0, 10], dtype=pl.Int64)})
    with pytest.raises(ValueError, match="SESSION_WINDOW_UNAVAILABLE"):
        derive_session_window(
            _synchronization_input(x_readiness=StreamReadiness.INVALID),
            aligned_x,
            _point_binding(),
        )

    wrong_dtype = pl.DataFrame({"t_ns": pl.Series([0.0, 10.0], dtype=pl.Float64)})
    with pytest.raises(ValueError, match="SESSION_WINDOW_UNAVAILABLE"):
        derive_session_window(
            _synchronization_input(),
            wrong_dtype,
            _point_binding(),
        )


def test_session_window_rejects_nonready_x_with_absent_prepared_inventory() -> None:
    sync_input = _synchronization_input(
        x_readiness=StreamReadiness.INVALID,
        include_x_in_prepared_inventory=False,
    )
    aligned_x = pl.DataFrame({"t_ns": pl.Series([0, 10], dtype=pl.Int64)})

    with pytest.raises(ValueError, match="^SESSION_WINDOW_UNAVAILABLE$"):
        derive_session_window(sync_input, aligned_x, _point_binding())


def test_session_window_rejects_null_mapped_time_with_stable_domain_error() -> None:
    null_time = pl.DataFrame({"t_ns": pl.Series([0, None, 10], dtype=pl.Int64)})

    with pytest.raises(ValueError, match="^SESSION_WINDOW_UNAVAILABLE$"):
        derive_session_window(
            _synchronization_input(),
            null_time,
            _point_binding(),
        )


def test_fixation_interval_maps_both_endpoints_and_classifies_window_relation() -> None:
    source = pl.DataFrame(
        {
            "fixation_id": [0, 1, 2, 3, 4],
            "start_source_timestamp_s": [
                -0.000000002,
                -0.000000001,
                0.0,
                0.000000009,
                0.000000010,
            ],
            "end_source_timestamp_s": [
                -0.000000001,
                0.0,
                0.000000005,
                0.000000011,
                0.000000011,
            ],
        }
    )

    aligned = map_interval_artifact(
        source,
        _interval_binding(),
        _clock(),
        _session_window(),
    )

    assert aligned["start_t_ns"].to_list() == [-2, -1, 0, 9, 10]
    assert aligned["end_t_ns"].to_list() == [-1, 0, 5, 11, 11]
    assert aligned["overlaps_session"].to_list() == [False, True, True, True, True]
    assert aligned["fully_in_session"].to_list() == [False, False, True, False, False]


def test_fixation_interval_preserves_source_duration_and_row_count() -> None:
    source = pl.DataFrame(
        {
            "fixation_id": [8, 9, 10],
            "start_source_timestamp_s": [0.1, 0.3, 0.8],
            "end_source_timestamp_s": [0.2, 0.7, 1.1],
            "duration_s": [0.1, 0.4, 0.3],
            "label": ["first", "second", "third"],
        }
    )

    aligned = map_interval_artifact(
        source,
        _interval_binding(),
        _clock(),
        _session_window(1_000_000_000),
    )

    assert aligned.columns == [
        *source.columns,
        "start_t_ns",
        "end_t_ns",
        "overlaps_session",
        "fully_in_session",
    ]
    assert aligned.select(source.columns).equals(source)
    assert aligned["duration_s"].to_list() == [0.1, 0.4, 0.3]
    assert aligned.height == source.height


@pytest.mark.parametrize(
    ("start_s", "end_s"),
    [(0.1, 0.1), (0.2, 0.1), (0.0, 0.0000000004)],
)
def test_interval_binding_rejects_end_not_after_start(start_s: float, end_s: float) -> None:
    source = pl.DataFrame(
        {
            "fixation_id": [0],
            "start_source_timestamp_s": [start_s],
            "end_source_timestamp_s": [end_s],
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        map_interval_artifact(source, _interval_binding(), _clock(), _session_window())

    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


@pytest.mark.parametrize(
    "source",
    [
        pl.DataFrame(
            {
                "fixation_id": [0],
                "start_source_timestamp_s": pl.Series([0], dtype=pl.Int64),
                "end_source_timestamp_s": [0.1],
            }
        ),
        pl.DataFrame(
            {
                "fixation_id": [0],
                "start_source_timestamp_s": [0.0],
                "end_source_timestamp_s": [float("nan")],
            }
        ),
        pl.DataFrame(
            {
                "fixation_id": [0],
                "start_source_timestamp_s": [0.0],
                "end_source_timestamp_s": [0.1],
                "start_t_ns": [0],
            }
        ),
    ],
    ids=["non-float64", "nonfinite", "output-collision"],
)
def test_interval_binding_translates_invalid_structure(source: pl.DataFrame) -> None:
    with pytest.raises(TemporalAlignmentError) as caught:
        map_interval_artifact(source, _interval_binding(), _clock(), _session_window())

    assert caught.value.issue.error_code == "TEMPORAL_ORDER_INVALID"


def test_interval_binding_translates_mapped_int64_overflow() -> None:
    source = pl.DataFrame(
        {
            "fixation_id": [0],
            "start_source_timestamp_s": [float(2**63)],
            "end_source_timestamp_s": [float(2**63) + 4096.0],
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        map_interval_artifact(source, _interval_binding(), _clock(), _session_window())

    assert caught.value.issue.error_code == "TIMESTAMP_OUT_OF_INT64_RANGE"


def test_ecg_r_peaks_are_aligned_as_an_independent_point_role() -> None:
    catalog = load_builtin_temporal_catalog()
    ecg = catalog.streams_by_schema["ecg-source-bundle-v0.1"]
    binding = cast(PointBinding, ecg.bindings_by_role["r_peaks"])
    peaks = pl.DataFrame(
        {
            "peak_id": [41, 42, 43],
            "source_timestamp_s": [0.25, 0.75, 1.25],
            "rr_interval_s": [0.8, 0.5, 0.5],
        }
    )

    aligned = apply_point_window(
        map_point_artifact(peaks, binding, _clock()),
        binding,
        _session_window(1_000_000_000),
    )

    assert binding.artifact_role == "r_peaks"
    assert binding.aligned_artifact_schema_id == "ecg-r-peak-aligned-v0.1"
    assert aligned["peak_id"].to_list() == [41, 42, 43]
    assert aligned["t_ns"].to_list() == [250_000_000, 750_000_000, 1_250_000_000]
    assert aligned["in_session"].to_list() == [True, True, False]
    assert aligned.height == peaks.height


def test_aoi_rows_inherit_frame_time_without_reordering_children() -> None:
    parent = pl.DataFrame(
        {
            "frame_id": [10, 11, 12],
            "t_ns": pl.Series([100, 200, 300], dtype=pl.Int64),
            "in_session": [True, True, False],
        }
    )
    child = pl.DataFrame(
        {
            "frame_id": [11, 10, 12, 11],
            "aoi_id": ["panel-b", "panel-a", "outside", "panel-a"],
            "x_min": [20, 10, 0, 15],
        }
    )

    aligned = inherit_point_time(child, parent, _inherit_binding())

    assert aligned.columns == [*child.columns, "t_ns", "in_session"]
    assert aligned.select(child.columns).equals(child)
    assert aligned["frame_id"].to_list() == [11, 10, 12, 11]
    assert aligned["aoi_id"].to_list() == ["panel-b", "panel-a", "outside", "panel-a"]
    assert aligned["t_ns"].to_list() == [200, 100, 300, 200]
    assert aligned["in_session"].to_list() == [True, True, False, True]


def test_inherit_binding_rejects_missing_parent_key() -> None:
    parent = pl.DataFrame(
        {
            "frame_id": [10],
            "t_ns": pl.Series([100], dtype=pl.Int64),
            "in_session": [True],
        }
    )
    child = pl.DataFrame({"frame_id": [10, 11], "aoi_id": ["a", "b"]})

    with pytest.raises(TemporalAlignmentError) as caught:
        inherit_point_time(child, parent, _inherit_binding())

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


def test_inherit_binding_rejects_duplicate_parent_key() -> None:
    parent = pl.DataFrame(
        {
            "frame_id": [10, 10],
            "t_ns": pl.Series([100, 101], dtype=pl.Int64),
            "in_session": [True, True],
        }
    )
    child = pl.DataFrame({"frame_id": [10], "aoi_id": ["a"]})

    with pytest.raises(TemporalAlignmentError) as caught:
        inherit_point_time(child, parent, _inherit_binding())

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


def test_inherit_binding_rejects_null_child_stable_key() -> None:
    parent = pl.DataFrame(
        {
            "frame_id": [10],
            "t_ns": pl.Series([100], dtype=pl.Int64),
            "in_session": [True],
        }
    )
    child = pl.DataFrame(
        {
            "frame_id": [10],
            "aoi_id": pl.Series([None], dtype=pl.String),
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        inherit_point_time(child, parent, _inherit_binding())

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


@pytest.mark.parametrize(
    ("foreign_key", "foreign_dtype"),
    [
        (1, pl.UInt64),
        (1.0, pl.Float64),
        (True, pl.Boolean),
    ],
    ids=["uint64-vs-int64", "float64-vs-int64", "boolean-vs-int64"],
)
def test_inherit_binding_rejects_parent_child_key_dtype_mismatch(
    foreign_key: int | float | bool,
    foreign_dtype: type[pl.DataType],
) -> None:
    parent = pl.DataFrame(
        {
            "frame_id": pl.Series([1], dtype=pl.Int64),
            "t_ns": pl.Series([100], dtype=pl.Int64),
            "in_session": [True],
        }
    )
    child = pl.DataFrame(
        {
            "frame_id": pl.Series([foreign_key], dtype=foreign_dtype),
            "aoi_id": ["a"],
        }
    )

    with pytest.raises(TemporalAlignmentError) as caught:
        inherit_point_time(child, parent, _inherit_binding())

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


@pytest.mark.parametrize(
    ("parent", "child"),
    [
        (
            pl.DataFrame(
                {
                    "frame_id": [10],
                    "t_ns": pl.Series([100.0], dtype=pl.Float64),
                    "in_session": [True],
                }
            ),
            pl.DataFrame({"frame_id": [10], "aoi_id": ["a"]}),
        ),
        (
            pl.DataFrame(
                {
                    "frame_id": [10],
                    "t_ns": pl.Series([100], dtype=pl.Int64),
                    "in_session": pl.Series([None], dtype=pl.Boolean),
                }
            ),
            pl.DataFrame({"frame_id": [10], "aoi_id": ["a"]}),
        ),
        (
            pl.DataFrame(
                {
                    "frame_id": [10],
                    "t_ns": pl.Series([100], dtype=pl.Int64),
                    "in_session": [True],
                }
            ),
            pl.DataFrame(
                {
                    "frame_id": [10],
                    "aoi_id": ["a"],
                    "t_ns": pl.Series([100], dtype=pl.Int64),
                }
            ),
        ),
    ],
    ids=["parent-time-dtype", "parent-mask-null", "output-collision"],
)
def test_inherit_binding_translates_invalid_structure(
    parent: pl.DataFrame,
    child: pl.DataFrame,
) -> None:
    with pytest.raises(TemporalAlignmentError) as caught:
        inherit_point_time(child, parent, _inherit_binding())

    assert caught.value.issue.error_code == "TEMPORAL_PARENT_KEY_INVALID"


def test_untimed_sidecars_and_image_paths_remain_byte_and_value_identical() -> None:
    catalog = load_builtin_temporal_catalog()
    eeg_sidecar_binding = cast(
        UntimedBinding,
        catalog.streams_by_schema["eeg-source-bundle-v0.1"].bindings_by_role["sidecar"],
    )
    image_binding = cast(
        UntimedBinding,
        catalog.streams_by_schema["vr-scene-source-bundle-v0.1"].bindings_by_role["frame_images"],
    )
    sidecar = {"schema_id": "eeg-sidecar-v0.1", "channel_order": ("Fz", "Cz")}
    sidecar_bytes = b'{"schema_id":"eeg-sidecar-v0.1"}'
    image_paths = ("streams/vr_scene/frames/000000.png", "streams/vr_scene/frames/000001.png")
    source_checksums = {
        "streams/eeg/eeg_sidecar.json": "a" * 64,
        "streams/vr_scene/frames/000000.png": "b" * 64,
    }

    assert preserve_untimed_artifact(sidecar, eeg_sidecar_binding) == sidecar
    assert preserve_untimed_artifact(sidecar_bytes, eeg_sidecar_binding) == sidecar_bytes
    assert preserve_untimed_artifact(image_paths, image_binding) == image_paths
    assert preserve_untimed_artifact(source_checksums, image_binding) == source_checksums
    assert not hasattr(eeg_sidecar_binding, "aligned_artifact_schema_id")
    assert not hasattr(image_binding, "aligned_artifact_schema_id")
