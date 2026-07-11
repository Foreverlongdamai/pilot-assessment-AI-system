"""Exact physical Parquet-table and EEG-sidecar inspection."""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NoReturn, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.common import INT64_MAX, INT64_MIN
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError
from pilot_assessment.ingestion.parquet_io import read_profiled_parquet_metadata
from pilot_assessment.ingestion.profiles import (
    JsonFieldType,
    JsonProfile,
    PhysicalDType,
    TableProfile,
)

_CONTRACT_VERSION = "0.1.0"
_GAP_MULTIPLIER = 1.5
_VALIDITY_COLUMNS = (
    "signal_valid",
    "frame_valid",
    "binocular_valid",
    "fixation_valid",
)
_NULLABLE_MEASUREMENT_GUARD = "signal_valid_false_or_artifact_code_present"


class _DuplicateJsonKey(ValueError):
    pass


def inspect_parquet_table(path: str | Path, profile: TableProfile) -> pl.DataFrame:
    """Read one immutable Parquet artifact only after exact profile validation."""

    source = Path(path)
    metadata = _read_metadata(source)
    if metadata != {
        "contract_version": _CONTRACT_VERSION,
        "schema_id": profile.schema_id,
    }:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Parquet contract metadata does not match the selected table profile",
            source,
            remediation="Export the table with the selected schema ID and contract version.",
            diagnostics={
                "expected_schema_id": profile.schema_id,
                "actual_schema_id": metadata["schema_id"],
            },
        )

    expected_schema = list(profile.polars_schema().items())
    try:
        physical_schema = list(pl.read_parquet_schema(source).items())
    except (OSError, pl.exceptions.PolarsError) as error:
        _format_failure(source, error, "Parquet physical schema cannot be read")
    if physical_schema != expected_schema:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Parquet ordered columns or physical dtypes do not match the profile",
            source,
            remediation="Export the exact ordered columns and physical dtypes in the profile.",
            diagnostics={
                "expected_schema": _schema_diagnostics(expected_schema),
                "actual_schema": _schema_diagnostics(physical_schema),
            },
        )

    try:
        frame = pl.read_parquet(source)
    except (OSError, pl.exceptions.PolarsError) as error:
        _format_failure(source, error, "Parquet content cannot be read")
    if list(frame.schema.items()) != expected_schema:
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "Parquet schema changed while content inspection was running",
            source,
            remediation="Re-run Session Bundle integrity and readiness inspection.",
        )
    if frame.is_empty():
        _fail(
            "STREAM_EMPTY",
            "Parquet table contains no rows",
            source,
            remediation="Export at least one profiled row.",
        )

    _validate_column_values(frame, profile, source)
    _validate_nullable_measurement_guard(frame, profile, source)
    _validate_valid_fraction(frame, profile, source)
    _validate_sort_key(frame, profile, source)
    _validate_sample_rate(frame, profile, source)
    return frame


def inspect_eeg_sidecar(
    path: str | Path,
    profile: JsonProfile,
    *,
    expected_clock_id: str,
    expected_channel_order: tuple[str, ...],
    expected_channel_units: Mapping[str, str],
    expected_sample_rate_hz: float,
    expected_generator_id: str,
    expected_seed: int,
) -> dict[str, JsonValue]:
    """Validate the strict M2 synthetic EEG sidecar and its table linkage."""

    source = Path(path)
    payload = _parse_profiled_json(source, profile)
    if payload["schema_id"] != profile.schema_id:
        _sidecar_mismatch(source, "schema_id", profile.schema_id, payload["schema_id"])

    actual_order = payload["channel_order"]
    if actual_order != list(expected_channel_order):
        _sidecar_mismatch(
            source,
            "channel_order",
            list(expected_channel_order),
            actual_order,
        )
    if len(expected_channel_order) != len(set(expected_channel_order)):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Expected EEG channel order contains duplicate labels",
            source,
            remediation="Use a unique ordered EEG channel declaration.",
        )

    expected_units = dict(expected_channel_units)
    if set(expected_units) != set(expected_channel_order):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Expected EEG channel units do not exactly cover the channel order",
            source,
            remediation="Declare exactly one unit for every expected EEG channel.",
        )
    if payload["channel_units"] != expected_units:
        _sidecar_mismatch(source, "channel_units", expected_units, payload["channel_units"])

    actual_rate = payload["sample_rate_hz"]
    if actual_rate != expected_sample_rate_hz:
        _fail(
            "SAMPLE_RATE_MISMATCH",
            "EEG sidecar sample rate does not match the samples profile",
            source,
            remediation="Use the same exact sample rate in the table profile and sidecar.",
            field_or_path="sample_rate_hz",
            diagnostics={
                "expected_hz": expected_sample_rate_hz,
                "actual_hz": cast(float, actual_rate),
            },
        )
    comparisons: tuple[tuple[str, JsonValue], ...] = (
        ("clock_id", expected_clock_id),
        ("generator_id", expected_generator_id),
        ("seed", expected_seed),
        ("synthetic_not_neurophysiological", True),
    )
    for field_name, expected_value in comparisons:
        if payload[field_name] != expected_value:
            _sidecar_mismatch(source, field_name, expected_value, payload[field_name])
    return payload


def _read_metadata(source: Path) -> dict[str, str]:
    try:
        return read_profiled_parquet_metadata(source)
    except ValueError as error:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Parquet contract metadata is missing or invalid",
            source,
            remediation="Write contract_version and schema_id through the profiled writer.",
            diagnostics={"exception_type": type(error).__name__},
        )
    except (OSError, pl.exceptions.PolarsError) as error:
        _format_failure(source, error, "Parquet metadata cannot be read")


def _validate_column_values(
    frame: pl.DataFrame,
    profile: TableProfile,
    source: Path,
) -> None:
    for column in profile.columns:
        values = frame[column.name]
        if not column.nullable and values.null_count() > 0:
            _fail(
                "STREAM_TYPE_INVALID",
                "A non-nullable Parquet column contains null values",
                source,
                remediation="Populate every required physical cell.",
                field_or_path=column.name,
            )

        non_null = values.drop_nulls()
        if (
            column.dtype in {PhysicalDType.F32, PhysicalDType.F64}
            and column.finite
            and non_null.len()
            and not non_null.is_finite().all()
        ):
            _fail(
                "STREAM_TYPE_INVALID",
                "A profiled floating-point column contains NaN or infinity",
                source,
                remediation=(
                    "Represent unavailable values as permitted nulls, never NaN or infinity."
                ),
                field_or_path=column.name,
            )
        if non_null.is_empty():
            continue
        minimum = non_null.min()
        maximum = non_null.max()
        if column.minimum is not None and cast(float | int, minimum) < column.minimum:
            _range_failure(source, column.name, column.minimum, column.maximum)
        if column.maximum is not None and cast(float | int, maximum) > column.maximum:
            _range_failure(source, column.name, column.minimum, column.maximum)


def _validate_nullable_measurement_guard(
    frame: pl.DataFrame,
    profile: TableProfile,
    source: Path,
) -> None:
    guard = profile.extensions.get("nullable_measurement_guard")
    if guard is None:
        return
    if guard != _NULLABLE_MEASUREMENT_GUARD:
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Table profile declares an unsupported nullable-measurement guard",
            source,
            remediation="Use a guard implemented by this adapter version.",
        )
    required_guard_columns = {"signal_valid", "artifact_code"}
    if not required_guard_columns.issubset(frame.columns):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Nullable-measurement guard requires signal_valid and artifact_code columns",
            source,
            remediation="Repair the packaged table profile.",
        )
    measurement_columns = [
        column.name
        for column in profile.columns
        if column.nullable and column.name != "artifact_code"
    ]
    if not measurement_columns:
        return
    has_null = frame[measurement_columns[0]].is_null()
    for column_name in measurement_columns[1:]:
        has_null = has_null | frame[column_name].is_null()
    artifact_present = frame["artifact_code"].fill_null("").str.len_chars() > 0
    guarded = (~frame["signal_valid"]) | artifact_present
    if (has_null & ~guarded).any():
        _fail(
            "STREAM_TYPE_INVALID",
            "A nullable signal measurement lacks an invalid flag or artifact code",
            source,
            remediation="Set signal_valid=false or provide a non-empty artifact_code.",
        )


def _validate_valid_fraction(
    frame: pl.DataFrame,
    profile: TableProfile,
    source: Path,
) -> None:
    validity_column = next((name for name in _VALIDITY_COLUMNS if name in frame.columns), None)
    if validity_column is None:
        return
    valid_fraction = frame[validity_column].sum() / frame.height
    if valid_fraction < profile.min_valid_fraction:
        _fail(
            "STREAM_TYPE_INVALID",
            "Table valid-row fraction is below the profile threshold",
            source,
            remediation="Repair invalid samples or export a higher-quality stream.",
            field_or_path=validity_column,
            diagnostics={
                "minimum_valid_fraction": profile.min_valid_fraction,
                "observed_valid_fraction": float(valid_fraction),
            },
        )


def _validate_sort_key(frame: pl.DataFrame, profile: TableProfile, source: Path) -> None:
    sort_key = list(profile.sort_key)
    key_frame = frame.select(sort_key)
    if key_frame.is_duplicated().any():
        _fail(
            "STREAM_TIMESTAMP_INVALID",
            "Parquet composite sort key contains duplicate values",
            source,
            remediation="Export one unique row per declared composite sort key.",
            diagnostics={"sort_key": sort_key},
        )
    if not key_frame.equals(frame.sort(sort_key).select(sort_key)):
        _fail(
            "STREAM_TIMESTAMP_INVALID",
            "Parquet rows are not ordered by the declared composite sort key",
            source,
            remediation="Sort the physical table by the profile sort key before export.",
            diagnostics={"sort_key": sort_key},
        )


def _validate_sample_rate(frame: pl.DataFrame, profile: TableProfile, source: Path) -> None:
    timestamp_column = profile.source_timestamp_column
    expected_rate = profile.expected_sample_rate_hz
    if timestamp_column is None:
        return
    timestamps = cast(list[float], frame[timestamp_column].to_list())
    deltas = [right - left for left, right in zip(timestamps, timestamps[1:], strict=False)]
    if any(not math.isfinite(delta) or delta <= 0.0 for delta in deltas):
        _fail(
            "STREAM_TIMESTAMP_INVALID",
            "Source timestamps must be finite and strictly increasing",
            source,
            remediation="Repair duplicate, decreasing, or non-finite source timestamps.",
            field_or_path=timestamp_column,
        )
    if expected_rate is None:
        return
    if not deltas:
        _fail(
            "SAMPLE_RATE_MISMATCH",
            "At least two rows are required to verify the fixed sample rate",
            source,
            remediation="Export enough rows to establish the profiled sample interval.",
            field_or_path=timestamp_column,
        )
    median_delta = statistics.median(deltas)
    observed_rate = 1.0 / median_delta
    relative_error = abs(observed_rate - expected_rate) / expected_rate
    if relative_error > profile.sample_rate_tolerance_fraction:
        _fail(
            "SAMPLE_RATE_MISMATCH",
            "Observed Parquet sample rate is outside the profile tolerance",
            source,
            remediation="Confirm the device export rate or select the correct profile.",
            field_or_path=timestamp_column,
            diagnostics={
                "expected_hz": expected_rate,
                "observed_hz": observed_rate,
            },
        )
    if any(delta > _GAP_MULTIPLIER * median_delta for delta in deltas):
        _fail(
            "STREAM_TIMESTAMP_INVALID",
            "Source timeline contains a gap above 1.5 times the median interval",
            source,
            remediation="Repair dropped samples or split the stream at the gap.",
            field_or_path=timestamp_column,
        )


def _parse_profiled_json(source: Path, profile: JsonProfile) -> dict[str, JsonValue]:
    try:
        text = source.read_bytes().decode("utf-8", errors="strict")
        raw = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey) as error:
        _format_failure(source, error, "EEG sidecar is not strict UTF-8 JSON")
    if not isinstance(raw, dict):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "EEG sidecar root must be a JSON object",
            source,
            remediation="Export the sidecar as one object matching its profile.",
        )
    payload = cast(dict[str, JsonValue], raw)
    declared_fields = {field.name: field for field in profile.fields}
    required_fields = {field.name for field in profile.fields if field.required}
    if not required_fields.issubset(payload) or set(payload) - set(declared_fields):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "EEG sidecar has missing required fields or undeclared extra fields",
            source,
            remediation="Export exactly the fields declared by the JSON profile.",
            diagnostics={
                "missing_fields": sorted(required_fields - set(payload)),
                "extra_fields": sorted(set(payload) - set(declared_fields)),
            },
        )
    for field_name, value in payload.items():
        field = declared_fields[field_name]
        if not _matches_json_field_type(value, field.field_type):
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "EEG sidecar field has the wrong strict JSON type",
                source,
                remediation="Export every sidecar field with its declared JSON type.",
                field_or_path=field_name,
            )
    return payload


def _matches_json_field_type(value: JsonValue, field_type: JsonFieldType) -> bool:
    if field_type is JsonFieldType.UTF8:
        return type(value) is str and bool(value)
    if field_type is JsonFieldType.STRING_LIST:
        return (
            type(value) is list
            and bool(value)
            and all(type(item) is str and bool(item) for item in value)
            and len(value) == len(set(cast(list[str], value)))
        )
    if field_type is JsonFieldType.STRING_MAP:
        return (
            type(value) is dict
            and bool(value)
            and all(
                type(key) is str and bool(key) and type(item) is str and bool(item)
                for key, item in value.items()
            )
        )
    if field_type is JsonFieldType.F64:
        return type(value) is float and math.isfinite(value)
    if field_type is JsonFieldType.I64:
        return type(value) is int and INT64_MIN <= value <= INT64_MAX
    if field_type is JsonFieldType.BOOL:
        return type(value) is bool
    return False


def _object_without_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise _DuplicateJsonKey(f"non-standard JSON constant: {value}")


def _schema_diagnostics(schema: Iterable[tuple[str, object]]) -> list[dict[str, str]]:
    return [{"name": name, "dtype": str(dtype)} for name, dtype in schema]


def _range_failure(
    source: Path,
    column_name: str,
    minimum: float | None,
    maximum: float | None,
) -> NoReturn:
    _fail(
        "STREAM_TYPE_INVALID",
        "A Parquet value is outside the physical range declared by the profile",
        source,
        remediation=(
            "Clamp only at the source when scientifically valid; otherwise repair the export."
        ),
        field_or_path=column_name,
        diagnostics={"minimum": minimum, "maximum": maximum},
    )


def _sidecar_mismatch(
    source: Path,
    field_name: str,
    expected: JsonValue,
    actual: JsonValue,
) -> NoReturn:
    _fail(
        "STREAM_SCHEMA_MISMATCH",
        "EEG sidecar content disagrees with its table or synthetic provenance",
        source,
        remediation="Regenerate the EEG table and sidecar from one consistent configuration.",
        field_or_path=field_name,
        diagnostics={"expected": expected, "actual": actual},
    )


def _format_failure(source: Path, error: Exception, message: str) -> NoReturn:
    _fail(
        "STREAM_FORMAT_INVALID",
        message,
        source,
        remediation="Replace the artifact with a valid immutable export.",
        diagnostics={"exception_type": type(error).__name__},
    )


def _fail(
    error_code: str,
    message: str,
    source: Path,
    *,
    remediation: str,
    field_or_path: str | None = None,
    diagnostics: dict[str, JsonValue] | None = None,
) -> NoReturn:
    raise AdapterInspectionError(
        DomainErrorData(
            error_code=error_code,
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message=message,
            field_or_path=field_or_path or str(source),
            remediation=remediation,
            diagnostics=diagnostics or {},
        )
    )


__all__ = ["inspect_eeg_sidecar", "inspect_parquet_table"]
