"""Generic constructors for tiny native-rate aligned tables used by M4 tests.

The helpers only construct input rows.  They intentionally contain no plugin
imports, expected anchor values, or assessment-state logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl


def tiny_point_table(
    *,
    id_column: str,
    timestamps_ns: Sequence[int],
    values: Mapping[str, Sequence[object]],
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    """Build one deterministic point table with an unsigned stable row ID."""

    timestamps = tuple(timestamps_ns)
    row_count = len(timestamps)
    if any(type(value) is not int for value in timestamps):
        raise TypeError("timestamps_ns must contain strict integers")
    flags = tuple(True for _ in timestamps) if in_session is None else tuple(in_session)
    if len(flags) != row_count or any(type(value) is not bool for value in flags):
        raise ValueError("in_session must contain one strict boolean per timestamp")
    if any(len(tuple(column)) != row_count for column in values.values()):
        raise ValueError("every value column must match the timestamp count")

    columns: dict[str, pl.Series] = {
        id_column: pl.Series(id_column, range(row_count), dtype=pl.UInt64),
        "t_ns": pl.Series("t_ns", timestamps, dtype=pl.Int64),
        "in_session": pl.Series("in_session", flags, dtype=pl.Boolean),
    }
    for name, raw_values in values.items():
        if name in columns:
            raise ValueError(f"duplicate point-table column: {name}")
        columns[name] = pl.Series(name, tuple(raw_values))
    return pl.DataFrame(columns)


def tiny_x_table(
    timestamps_ns: Sequence[int],
    metrics: Mapping[str, Sequence[float]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="source_row_index",
        timestamps_ns=timestamps_ns,
        values=metrics,
        in_session=in_session,
    )


def tiny_u_table(
    timestamps_ns: Sequence[int],
    channels: Mapping[str, Sequence[float]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="source_row_index",
        timestamps_ns=timestamps_ns,
        values=channels,
        in_session=in_session,
    )


def tiny_reference_table(
    timestamps_ns: Sequence[int],
    fields: Mapping[str, Sequence[float]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="reference_sample_id",
        timestamps_ns=timestamps_ns,
        values=fields,
        in_session=in_session,
    )


def tiny_i_table(
    timestamps_ns: Sequence[int],
    fields: Mapping[str, Sequence[object]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="frame_id",
        timestamps_ns=timestamps_ns,
        values=fields,
        in_session=in_session,
    )


def tiny_g_table(
    timestamps_ns: Sequence[int],
    fields: Mapping[str, Sequence[object]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="gaze_sample_id",
        timestamps_ns=timestamps_ns,
        values=fields,
        in_session=in_session,
    )


def tiny_eeg_table(
    timestamps_ns: Sequence[int],
    channels: Mapping[str, Sequence[float]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="sample_index",
        timestamps_ns=timestamps_ns,
        values=channels,
        in_session=in_session,
    )


def tiny_ecg_table(
    timestamps_ns: Sequence[int],
    channels: Mapping[str, Sequence[float]],
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="sample_index",
        timestamps_ns=timestamps_ns,
        values=channels,
        in_session=in_session,
    )


def tiny_r_peak_table(
    timestamps_ns: Sequence[int],
    fields: Mapping[str, Sequence[object]] | None = None,
    *,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    return tiny_point_table(
        id_column="peak_id",
        timestamps_ns=timestamps_ns,
        values=fields or {},
        in_session=in_session,
    )


__all__ = [
    "tiny_ecg_table",
    "tiny_eeg_table",
    "tiny_g_table",
    "tiny_i_table",
    "tiny_point_table",
    "tiny_r_peak_table",
    "tiny_reference_table",
    "tiny_u_table",
    "tiny_x_table",
]
