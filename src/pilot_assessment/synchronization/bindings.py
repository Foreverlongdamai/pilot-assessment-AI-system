"""Native-rate temporal binding executors."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import NoReturn, TypeVar, cast

import polars as pl

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.ingestion import StreamReadiness
from pilot_assessment.contracts.session import ClockSync
from pilot_assessment.contracts.synchronization import (
    MAX_SESSION_END_NS_V0_1,
    SessionWindow,
)
from pilot_assessment.synchronization.clock import map_source_seconds_to_session_ns
from pilot_assessment.synchronization.models import SynchronizationInput
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
    UntimedBinding,
)

_ArtifactT = TypeVar("_ArtifactT")


class TemporalAlignmentError(Exception):
    """A bounded temporal-binding failure safe for service translation."""

    def __init__(self, issue: DomainErrorData) -> None:
        self.issue = issue
        super().__init__(issue.message)


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


def _raise_structural_issue(
    error: BaseException,
    *,
    error_code: str,
    message: str,
    remediation: str,
) -> NoReturn:
    if isinstance(error, TemporalAlignmentError):
        raise error
    _raise_temporal_issue(
        error_code,
        message,
        remediation=remediation,
    )


def _map_source_values(
    values: list[float],
    clock: ClockSync,
    *,
    field_or_path: str,
) -> list[int]:
    try:
        return [
            map_source_seconds_to_session_ns(
                value,
                scale=clock.scale,
                offset_ns=clock.offset_ns,
            )
            for value in values
        ]
    except ValueError as error:
        if str(error) == "TIMESTAMP_OUT_OF_INT64_RANGE":
            _raise_temporal_issue(
                "TIMESTAMP_OUT_OF_INT64_RANGE",
                "Mapped timestamp is outside the signed Int64 range.",
                remediation="Correct the source timestamp or clock mapping and synchronize again.",
                field_or_path=field_or_path,
            )
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Source timestamps cannot be mapped by the declared temporal binding.",
            remediation="Provide finite Float64 timestamps and a valid declared clock mapping.",
            field_or_path=field_or_path,
        )


def _validate_point_source(frame: pl.DataFrame, binding: PointBinding) -> list[float]:
    source_column = binding.source_timestamp_column
    if source_column not in frame.columns or frame.schema[source_column] != pl.Float64:
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Point source timestamps must be finite Float64 values.",
            remediation="Export the declared point timestamp column as finite Float64 values.",
            field_or_path=source_column,
        )
    if (
        binding.target_timestamp_column in frame.columns
        or binding.in_session_column in frame.columns
    ):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Point binding output columns already exist.",
            remediation=(
                "Remove pre-existing alignment columns from the normalized source artifact."
            ),
        )

    missing_keys = [key for key in binding.stable_keys if key not in frame.columns]
    if missing_keys or any(frame[key].null_count() for key in binding.stable_keys if key in frame):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Point stable keys must be present and non-null.",
            remediation="Provide every declared stable key with one non-null value per row.",
        )

    values = cast(list[float | None], frame[source_column].to_list())
    if any(value is None or not math.isfinite(value) for value in values):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Point source timestamps must be finite Float64 values.",
            remediation="Replace null, NaN, or infinite point timestamps before synchronization.",
            field_or_path=source_column,
        )
    return cast(list[float], values)


def _validate_point_order(frame: pl.DataFrame, binding: PointBinding) -> None:
    order_columns = [binding.target_timestamp_column, *binding.stable_keys]
    rows = frame.select(order_columns).rows()
    try:
        invalid = any(current <= previous for previous, current in pairwise(rows))
    except TypeError as error:
        _raise_structural_issue(
            error,
            error_code="TEMPORAL_ORDER_INVALID",
            message="Mapped point rows do not have a comparable stable order.",
            remediation="Use consistently typed stable keys and monotonic source timestamps.",
        )
    if invalid:
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Mapped point rows violate timestamp and stable-key order.",
            remediation=(
                "Export rows in strict mapped-time and stable-key order without duplicates."
            ),
        )


def map_point_artifact(
    frame: pl.DataFrame,
    binding: PointBinding,
    clock: ClockSync,
) -> pl.DataFrame:
    """Append mapped Int64 time while preserving every native row and column."""

    try:
        source_values = _validate_point_source(frame, binding)
        mapped = _map_source_values(
            source_values,
            clock,
            field_or_path=binding.source_timestamp_column,
        )
        aligned = frame.with_columns(
            pl.Series(binding.target_timestamp_column, mapped, dtype=pl.Int64)
        )
        _validate_point_order(aligned, binding)
        return aligned
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
        _raise_structural_issue(
            error,
            error_code="TEMPORAL_ORDER_INVALID",
            message="Point artifact does not satisfy its declared temporal binding.",
            remediation="Correct the point schema, stable keys, and source timestamp order.",
        )


def apply_point_window(
    frame: pl.DataFrame,
    binding: PointBinding,
    window: SessionWindow,
) -> pl.DataFrame:
    """Append a closed-session-window mask without filtering native rows."""

    try:
        target = binding.target_timestamp_column
        if (
            target not in frame.columns
            or frame.schema[target] != pl.Int64
            or frame[target].null_count()
        ):
            _raise_temporal_issue(
                "TEMPORAL_ORDER_INVALID",
                "Mapped point timestamps must be non-null Int64 values.",
                remediation="Map the normalized point artifact before applying the session window.",
                field_or_path=target,
            )
        if binding.in_session_column in frame.columns:
            _raise_temporal_issue(
                "TEMPORAL_ORDER_INVALID",
                "Point binding output columns already exist.",
                remediation="Apply the session window exactly once to each mapped artifact.",
            )

        mapped = cast(list[int], frame[target].to_list())
        inside = [window.start_t_ns <= value <= window.end_t_ns for value in mapped]
        return frame.with_columns(pl.Series(binding.in_session_column, inside, dtype=pl.Boolean))
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
        _raise_structural_issue(
            error,
            error_code="TEMPORAL_ORDER_INVALID",
            message="Mapped point artifact cannot be classified against the session window.",
            remediation="Correct the mapped timestamp column and retry synchronization.",
        )


def _validate_interval_source(
    frame: pl.DataFrame,
    binding: IntervalBinding,
) -> tuple[list[float], list[float]]:
    source_columns = (binding.source_start_column, binding.source_end_column)
    if any(
        column not in frame.columns or frame.schema[column] != pl.Float64
        for column in source_columns
    ):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Interval endpoints must be finite Float64 values.",
            remediation="Export both declared interval endpoint columns as finite Float64 values.",
        )

    output_columns = (
        binding.target_start_column,
        binding.target_end_column,
        binding.overlaps_session_column,
        binding.fully_in_session_column,
    )
    if any(column in frame.columns for column in output_columns):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Interval binding output columns already exist.",
            remediation=(
                "Remove pre-existing alignment columns from the normalized interval artifact."
            ),
        )

    if any(key not in frame.columns for key in binding.stable_keys) or any(
        frame[key].null_count() for key in binding.stable_keys if key in frame.columns
    ):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Interval stable keys must be present and non-null.",
            remediation=(
                "Provide every declared interval stable key with one non-null value per row."
            ),
        )
    if frame.select(binding.stable_keys).is_duplicated().any():
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Interval stable keys must identify unique rows.",
            remediation="Remove duplicate interval stable-key rows before synchronization.",
        )

    starts = cast(list[float | None], frame[binding.source_start_column].to_list())
    ends = cast(list[float | None], frame[binding.source_end_column].to_list())
    if any(value is None or not math.isfinite(value) for value in [*starts, *ends]):
        _raise_temporal_issue(
            "TEMPORAL_ORDER_INVALID",
            "Interval endpoints must be finite Float64 values.",
            remediation="Replace null, NaN, or infinite interval endpoints before synchronization.",
        )
    return cast(list[float], starts), cast(list[float], ends)


def map_interval_artifact(
    frame: pl.DataFrame,
    binding: IntervalBinding,
    clock: ClockSync,
    window: SessionWindow,
) -> pl.DataFrame:
    """Map native interval endpoints and append closed-window relation flags."""

    try:
        source_starts, source_ends = _validate_interval_source(frame, binding)
        starts = _map_source_values(
            source_starts,
            clock,
            field_or_path=binding.source_start_column,
        )
        ends = _map_source_values(
            source_ends,
            clock,
            field_or_path=binding.source_end_column,
        )
        if any(end <= start for start, end in zip(starts, ends, strict=True)):
            _raise_temporal_issue(
                "TEMPORAL_ORDER_INVALID",
                "Every mapped interval end must be strictly after its mapped start.",
                remediation=(
                    "Correct or increase interval endpoint precision before synchronization."
                ),
            )

        overlaps = [
            end >= window.start_t_ns and start <= window.end_t_ns
            for start, end in zip(starts, ends, strict=True)
        ]
        fully_inside = [
            start >= window.start_t_ns and end <= window.end_t_ns
            for start, end in zip(starts, ends, strict=True)
        ]
        return frame.with_columns(
            pl.Series(binding.target_start_column, starts, dtype=pl.Int64),
            pl.Series(binding.target_end_column, ends, dtype=pl.Int64),
            pl.Series(binding.overlaps_session_column, overlaps, dtype=pl.Boolean),
            pl.Series(binding.fully_in_session_column, fully_inside, dtype=pl.Boolean),
        )
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
        _raise_structural_issue(
            error,
            error_code="TEMPORAL_ORDER_INVALID",
            message="Interval artifact does not satisfy its declared temporal binding.",
            remediation="Correct interval columns, stable keys, and endpoint order.",
        )


def inherit_point_time(
    child: pl.DataFrame,
    parent: pl.DataFrame,
    binding: InheritBinding,
) -> pl.DataFrame:
    """Append a unique parent row's mapped time without reordering child rows."""

    try:
        parent_required = (
            *binding.parent_key_columns,
            binding.target_timestamp_column,
            binding.in_session_column,
        )
        child_required = (*binding.foreign_key_columns, *binding.stable_keys)
        if any(column not in parent.columns for column in parent_required) or any(
            column not in child.columns for column in child_required
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited time requires every declared parent and child key column.",
                remediation="Export complete parent keys and matching child foreign keys.",
            )
        if any(
            parent.schema[parent_key] != child.schema[foreign_key]
            for parent_key, foreign_key in zip(
                binding.parent_key_columns,
                binding.foreign_key_columns,
                strict=True,
            )
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited parent and child key columns must have identical data types.",
                remediation="Export each child foreign key with its parent key's exact data type.",
            )
        child_stable_frame = child.select(binding.stable_keys)
        if (
            any(child_stable_frame[column].null_count() for column in child_stable_frame.columns)
            or child_stable_frame.is_duplicated().any()
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited child stable keys must be non-null and unique.",
                remediation="Provide one complete stable key for every inherited child row.",
            )
        if (
            parent.schema[binding.target_timestamp_column] != pl.Int64
            or parent.schema[binding.in_session_column] != pl.Boolean
            or parent[binding.target_timestamp_column].null_count()
            or parent[binding.in_session_column].null_count()
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited parent time must contain non-null Int64 time and Boolean mask columns.",
                remediation="Map and window the parent point artifact before inheriting time.",
            )
        if (
            binding.target_timestamp_column in child.columns
            or binding.in_session_column in child.columns
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited binding output columns already exist on the child artifact.",
                remediation="Apply inherited time exactly once to each child artifact.",
            )

        parent_key_frame = parent.select(binding.parent_key_columns)
        child_key_frame = child.select(binding.foreign_key_columns)
        if any(parent_key_frame[column].null_count() for column in parent_key_frame.columns) or any(
            child_key_frame[column].null_count() for column in child_key_frame.columns
        ):
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Parent and child temporal keys must be non-null.",
                remediation="Replace null temporal relationship keys and synchronize again.",
            )

        parent_keys = parent_key_frame.rows()
        parent_times = cast(list[int], parent[binding.target_timestamp_column].to_list())
        parent_masks = cast(list[bool], parent[binding.in_session_column].to_list())
        parent_time_by_key: dict[tuple[object, ...], tuple[int, bool]] = {}
        for key, timestamp, in_session in zip(
            parent_keys,
            parent_times,
            parent_masks,
            strict=True,
        ):
            if key in parent_time_by_key:
                _raise_temporal_issue(
                    "TEMPORAL_PARENT_KEY_INVALID",
                    "Inherited parent keys must be unique.",
                    remediation="Deduplicate the parent key timeline before synchronization.",
                )
            parent_time_by_key[key] = (timestamp, in_session)

        inherited_times: list[int] = []
        inherited_masks: list[bool] = []
        for foreign_key in child_key_frame.rows():
            inherited = parent_time_by_key.get(foreign_key)
            if inherited is None:
                _raise_temporal_issue(
                    "TEMPORAL_PARENT_KEY_INVALID",
                    "A child foreign key has no unique parent time row.",
                    remediation=(
                        "Provide exactly one mapped parent row for every child foreign key."
                    ),
                )
            timestamp, in_session = inherited
            inherited_times.append(timestamp)
            inherited_masks.append(in_session)

        aligned = child.with_columns(
            pl.Series(binding.target_timestamp_column, inherited_times, dtype=pl.Int64),
            pl.Series(binding.in_session_column, inherited_masks, dtype=pl.Boolean),
        )
        if aligned.height != child.height or aligned.select(child.columns).equals(child) is False:
            _raise_temporal_issue(
                "TEMPORAL_PARENT_KEY_INVALID",
                "Inherited time changed child row order or source values.",
                remediation="Preserve child rows exactly while appending inherited time.",
            )
        return aligned
    except TemporalAlignmentError:
        raise
    except (KeyError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
        _raise_structural_issue(
            error,
            error_code="TEMPORAL_PARENT_KEY_INVALID",
            message="Child artifact cannot inherit time from its declared parent role.",
            remediation="Correct parent keys, child foreign keys, and mapped parent columns.",
        )


def preserve_untimed_artifact(
    artifact: _ArtifactT,
    binding: UntimedBinding,
) -> _ArtifactT:
    """Return an untimed JSON/file artifact unchanged and without an aligned schema."""

    del binding
    return artifact


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
    if not mapped_x_times:
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    end_t_ns = max(mapped_x_times)
    if not 0 < end_t_ns <= MAX_SESSION_END_NS_V0_1:
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    return SessionWindow(
        start_t_ns=0,
        end_t_ns=end_t_ns,
        source="master-clock-x-mapped-coverage-v1",
    )


__all__ = [
    "TemporalAlignmentError",
    "apply_point_window",
    "derive_session_window",
    "inherit_point_time",
    "map_interval_artifact",
    "map_point_artifact",
    "preserve_untimed_artifact",
]
