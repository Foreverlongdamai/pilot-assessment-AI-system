"""Native-rate temporal binding executors."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import cast

import polars as pl

from pilot_assessment.contracts.ingestion import StreamReadiness
from pilot_assessment.contracts.session import ClockSync
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.clock import map_source_seconds_to_session_ns
from pilot_assessment.synchronization.models import SynchronizationInput
from pilot_assessment.synchronization.profiles import PointBinding


def _validate_point_source(frame: pl.DataFrame, binding: PointBinding) -> list[float]:
    source_column = binding.source_timestamp_column
    if source_column not in frame.columns or frame.schema[source_column] != pl.Float64:
        raise ValueError("source timestamps must be finite Float64")
    if (
        binding.target_timestamp_column in frame.columns
        or binding.in_session_column in frame.columns
    ):
        raise ValueError("point binding output columns already exist")

    missing_keys = [key for key in binding.stable_keys if key not in frame.columns]
    if missing_keys or any(frame[key].null_count() for key in binding.stable_keys if key in frame):
        raise ValueError("TEMPORAL_ORDER_INVALID: point stable keys must be present and non-null")

    values = cast(list[float | None], frame[source_column].to_list())
    if any(value is None or not math.isfinite(value) for value in values):
        raise ValueError("source timestamps must be finite Float64")
    return cast(list[float], values)


def _validate_point_order(frame: pl.DataFrame, binding: PointBinding) -> None:
    order_columns = [binding.target_timestamp_column, *binding.stable_keys]
    rows = frame.select(order_columns).rows()
    try:
        invalid = any(current <= previous for previous, current in pairwise(rows))
    except TypeError as error:
        raise ValueError("TEMPORAL_ORDER_INVALID") from error
    if invalid:
        raise ValueError("TEMPORAL_ORDER_INVALID")


def map_point_artifact(
    frame: pl.DataFrame,
    binding: PointBinding,
    clock: ClockSync,
) -> pl.DataFrame:
    """Append mapped Int64 time while preserving every native row and column."""

    source_values = _validate_point_source(frame, binding)
    mapped = [
        map_source_seconds_to_session_ns(
            value,
            scale=clock.scale,
            offset_ns=clock.offset_ns,
        )
        for value in source_values
    ]
    aligned = frame.with_columns(pl.Series(binding.target_timestamp_column, mapped, dtype=pl.Int64))
    _validate_point_order(aligned, binding)
    return aligned


def apply_point_window(
    frame: pl.DataFrame,
    binding: PointBinding,
    window: SessionWindow,
) -> pl.DataFrame:
    """Append a closed-session-window mask without filtering native rows."""

    target = binding.target_timestamp_column
    if (
        target not in frame.columns
        or frame.schema[target] != pl.Int64
        or frame[target].null_count()
    ):
        raise ValueError("mapped point timestamps must be non-null Int64")
    if binding.in_session_column in frame.columns:
        raise ValueError("point binding output columns already exist")

    mapped = cast(list[int], frame[target].to_list())
    inside = [window.start_t_ns <= value <= window.end_t_ns for value in mapped]
    return frame.with_columns(pl.Series(binding.in_session_column, inside, dtype=pl.Boolean))


def derive_session_window(
    sync_input: SynchronizationInput,
    aligned_x: pl.DataFrame,
    binding: PointBinding,
) -> SessionWindow:
    """Derive D-018's closed window from already-mapped master-clock X coverage."""

    manifest = sync_input.loaded_manifest.manifest
    if manifest.session_timebase.origin != "session_start":
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    x_result = sync_input.readiness_report.stream_results["X"]
    if (
        x_result.readiness is not StreamReadiness.READY
        or "X" not in sync_input.prepared_session.streams
    ):
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    x_stream = sync_input.prepared_session.streams["X"]
    target = binding.target_timestamp_column
    if (
        x_stream.clock_id != manifest.session_timebase.master_clock_id
        or target not in aligned_x.columns
        or aligned_x.schema[target] != pl.Int64
        or aligned_x[target].null_count()
    ):
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    mapped_x_times = cast(list[int], aligned_x[target].to_list())
    if not mapped_x_times or max(mapped_x_times) <= 0:
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    return SessionWindow(
        start_t_ns=0,
        end_t_ns=max(mapped_x_times),
        source="master-clock-x-mapped-coverage-v1",
    )


__all__ = ["apply_point_window", "derive_session_window", "map_point_artifact"]
