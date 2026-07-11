"""Profile-driven adapter for the legacy combined simulator X/U CSV."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import statistics
from pathlib import Path
from typing import NoReturn

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
)
from pilot_assessment.ingestion.adapters.limits import (
    DEFAULT_ADAPTER_RESOURCE_LIMITS,
    AdapterResourceLimits,
    enforce_resource_limit,
)
from pilot_assessment.ingestion.models import NormalizedStream
from pilot_assessment.ingestion.profiles import CsvColumnRole, CsvProfile


class ProfiledCsvAdapter:
    """Read one verified combined simulator source into logical X and U views."""

    adapter_id = "profiled-csv"
    adapter_version = "0.1.0"
    keys = frozenset({("csv", "cranfield-simulator-combined-csv-raw-v0.1")})

    def __init__(
        self,
        limits: AdapterResourceLimits = DEFAULT_ADAPTER_RESOURCE_LIMITS,
    ) -> None:
        self._limits = limits

    def inspect(self, request: AdapterRequest) -> AdapterResult:
        profile = request.profile
        if not isinstance(profile, CsvProfile):
            _fail(
                "ADAPTER_CONFIG_INVALID",
                "Profiled CSV adapter requires a CsvProfile",
                remediation="Register the CSV schema ID with its packaged CsvProfile.",
            )
        if set(request.descriptors) != {"X", "U"} or len(request.source_paths) != 1:
            _fail(
                "ADAPTER_CONFIG_INVALID",
                "Combined simulator CSV requires exactly the X and U logical descriptors",
                remediation="Dispatch the shared source once with both X and U descriptors.",
            )

        relative_path = request.source_paths[0]
        source_path = _safe_source_path(request.bundle_root, relative_path)
        payload = _read_bounded_csv(source_path, relative_path, self._limits)
        expected_digest = request.verified_digests[relative_path]
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            _fail(
                "SOURCE_CHANGED_DURING_READINESS",
                "CSV bytes changed after the integrity inspection",
                field_or_path=relative_path,
                remediation="Stop ingestion and re-run Session Bundle integrity inspection.",
            )

        raw_headers = _validate_csv_structure(
            payload,
            profile,
            relative_path,
            self._limits,
        )
        frame = _read_numeric_frame(payload, raw_headers, relative_path)
        canonical = _canonicalize_and_validate(frame, raw_headers, profile, relative_path)
        context = _extract_context(canonical, profile, relative_path)
        issues = _validate_unit_consistency(canonical, profile, relative_path)
        streams = _build_views(canonical, request, profile)

        try:
            changed_during_read = (
                _read_bounded_csv(source_path, relative_path, self._limits) != payload
            )
        except AdapterInspectionError as error:
            if error.issue.error_code == "ADAPTER_RESOURCE_LIMIT_EXCEEDED":
                raise
            changed_during_read = True
        if changed_during_read:
            _fail(
                "SOURCE_CHANGED_DURING_READINESS",
                "CSV source changed while readiness inspection was running",
                field_or_path=relative_path,
                remediation="Stop ingestion and restart from the M1 integrity boundary.",
            )

        return AdapterResult(
            streams=streams,
            context=context,
            artifact_summaries=(
                AdapterArtifactSummary(
                    role="simulator_csv",
                    paths=request.source_paths,
                    row_count=canonical.height,
                ),
            ),
            issues=issues,
        )


def _safe_source_path(bundle_root: Path, relative_path: str) -> Path:
    root = bundle_root.resolve()
    candidate = root.joinpath(*relative_path.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "Verified CSV source is missing",
            field_or_path=relative_path,
            remediation="Re-run Session Bundle integrity inspection.",
        )
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "Verified CSV source no longer resolves to a regular bundle file",
            field_or_path=relative_path,
            remediation="Remove links or special files and re-run integrity inspection.",
        )
    return resolved


def _validate_csv_structure(
    payload: bytes,
    profile: CsvProfile,
    relative_path: str,
    limits: AdapterResourceLimits,
) -> tuple[str, ...]:
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        _fail(
            "STREAM_FORMAT_INVALID",
            "Simulator CSV must be strict UTF-8 or UTF-8 with BOM",
            field_or_path=relative_path,
            remediation="Export the source as UTF-8 CSV.",
            diagnostics={"exception_type": type(error).__name__},
        )
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        raw_headers = tuple(next(rows))
        enforce_resource_limit(
            limit_name="max_csv_columns",
            limit=limits.max_csv_columns,
            observed=len(raw_headers),
            field_or_path=relative_path,
        )
        header_bytes = len(",".join(raw_headers).encode("utf-8"))
        enforce_resource_limit(
            limit_name="max_csv_header_bytes",
            limit=limits.max_csv_header_bytes,
            observed=header_bytes,
            field_or_path=relative_path,
        )
        longest_header = max((len(header) for header in raw_headers), default=0)
        enforce_resource_limit(
            limit_name="max_csv_field_chars",
            limit=limits.max_csv_field_chars,
            observed=longest_header,
            field_or_path=relative_path,
        )
        normalized = tuple(header.strip(" \t") for header in raw_headers)
        if not raw_headers or any(not header for header in normalized):
            raise ValueError("CSV header contains an empty normalized name")
        if len(normalized) != len(set(normalized)):
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "CSV headers collide after required outer-whitespace normalization",
                field_or_path=relative_path,
                remediation="Rename colliding source columns before import.",
                diagnostics={"normalized_headers": list(normalized)},
            )
        expected = {column.source_header for column in profile.columns if column.required}
        missing = sorted(expected - set(normalized))
        if missing:
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "CSV is missing required profiled columns",
                field_or_path=relative_path,
                remediation="Export all required simulator columns.",
                diagnostics={"missing_headers": missing},
            )
        for row_number, row in enumerate(rows, start=2):
            enforce_resource_limit(
                limit_name="max_csv_rows",
                limit=limits.max_csv_rows,
                observed=row_number - 1,
                field_or_path=relative_path,
            )
            if len(row) != len(raw_headers):
                _fail(
                    "STREAM_FORMAT_INVALID",
                    "CSV row width does not match the header width",
                    field_or_path=relative_path,
                    remediation="Repair the ragged CSV row and retry.",
                    diagnostics={
                        "row_number": row_number,
                        "expected_columns": len(raw_headers),
                        "actual_columns": len(row),
                    },
                )
            longest_field = max((len(value) for value in row), default=0)
            enforce_resource_limit(
                limit_name="max_csv_field_chars",
                limit=limits.max_csv_field_chars,
                observed=longest_field,
                field_or_path=relative_path,
            )
    except (csv.Error, StopIteration, ValueError) as error:
        _fail(
            "STREAM_FORMAT_INVALID",
            "Simulator CSV structure is invalid or empty",
            field_or_path=relative_path,
            remediation="Export a non-empty RFC 4180-compatible CSV.",
            diagnostics={"exception_type": type(error).__name__},
        )
    return raw_headers


def _read_bounded_csv(
    source_path: Path,
    relative_path: str,
    limits: AdapterResourceLimits,
) -> bytes:
    try:
        observed_size = source_path.stat().st_size
        enforce_resource_limit(
            limit_name="max_csv_bytes",
            limit=limits.max_csv_bytes,
            observed=observed_size,
            field_or_path=relative_path,
        )
        with source_path.open("rb") as source:
            payload = source.read(limits.max_csv_bytes + 1)
    except AdapterInspectionError:
        raise
    except OSError as error:
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "Verified CSV source can no longer be read",
            field_or_path=relative_path,
            remediation="Re-run Session Bundle integrity inspection.",
            diagnostics={"exception_type": type(error).__name__},
        )
    enforce_resource_limit(
        limit_name="max_csv_bytes",
        limit=limits.max_csv_bytes,
        observed=len(payload),
        field_or_path=relative_path,
    )
    return payload


def _read_numeric_frame(
    payload: bytes,
    raw_headers: tuple[str, ...],
    relative_path: str,
) -> pl.DataFrame:
    try:
        return pl.read_csv(
            io.BytesIO(payload),
            has_header=True,
            schema_overrides={header: pl.Float64 for header in raw_headers},
            row_index_name="source_row_index",
            try_parse_dates=False,
            truncate_ragged_lines=False,
            raise_if_empty=True,
        ).with_columns(pl.col("source_row_index").cast(pl.UInt64))
    except Exception as error:
        _fail(
            "STREAM_TYPE_INVALID",
            "CSV contains a value that cannot be parsed as the profiled numeric type",
            field_or_path=relative_path,
            remediation="Replace non-numeric or empty required cells with finite numbers.",
            diagnostics={"exception_type": type(error).__name__},
        )


def _canonicalize_and_validate(
    frame: pl.DataFrame,
    raw_headers: tuple[str, ...],
    profile: CsvProfile,
    relative_path: str,
) -> pl.DataFrame:
    by_source = {column.source_header: column for column in profile.columns}
    rename: dict[str, str] = {}
    for raw_header in raw_headers:
        normalized = raw_header.strip(" \t")
        column = by_source.get(normalized)
        if column is not None:
            rename[raw_header] = column.canonical_name
    canonical = frame.rename(rename)

    profiled_names = [column.canonical_name for column in profile.columns]
    for name in profiled_names:
        series = canonical[name]
        if series.null_count() or not series.is_finite().all():
            _fail(
                "STREAM_TYPE_INVALID",
                "CSV required numeric cells must be finite and non-null",
                field_or_path=name,
                remediation="Repair null, NaN, or infinite source values.",
            )

    timestamps = canonical[profile.source_timestamp_column].to_list()
    if not timestamps:
        _fail(
            "STREAM_EMPTY",
            "Simulator CSV contains no data rows",
            field_or_path=relative_path,
            remediation="Export at least two ordered simulator samples.",
        )
    if any(value < 0.0 for value in timestamps):
        _timestamp_failure(relative_path, "source timestamps must be non-negative")
    deltas = [right - left for left, right in zip(timestamps, timestamps[1:], strict=False)]
    if not deltas or any(delta <= 0.0 or not math.isfinite(delta) for delta in deltas):
        _timestamp_failure(
            relative_path,
            "source timestamps must be finite and strictly increasing",
        )
    median_delta = statistics.median(deltas)
    observed_rate = 1.0 / median_delta
    relative_error = abs(observed_rate - profile.expected_sample_rate_hz) / (
        profile.expected_sample_rate_hz
    )
    if relative_error > profile.sample_rate_tolerance_fraction:
        _fail(
            "SAMPLE_RATE_MISMATCH",
            "Observed CSV sample rate is outside the packaged profile tolerance",
            field_or_path=profile.source_timestamp_column,
            remediation="Confirm the simulator export rate or select the correct profile.",
            diagnostics={
                "expected_hz": profile.expected_sample_rate_hz,
                "observed_hz": observed_rate,
            },
        )
    if any(delta > profile.gap_multiplier * median_delta for delta in deltas):
        _timestamp_failure(relative_path, "source timeline contains a gap above the profile limit")
    return canonical


def _extract_context(
    frame: pl.DataFrame,
    profile: CsvProfile,
    relative_path: str,
) -> dict[str, float]:
    context: dict[str, float] = {}
    for name in profile.context_columns:
        if frame[name].n_unique() != 1:
            _fail(
                "STREAM_CONTEXT_NOT_CONSTANT",
                "A profiled session-context column changes within the session",
                field_or_path=name,
                remediation="Split mixed-condition data into separate sessions.",
                diagnostics={"source_path": relative_path},
            )
        context[name] = float(frame[name][0])
    return context


def _validate_unit_consistency(
    frame: pl.DataFrame,
    profile: CsvProfile,
    relative_path: str,
) -> tuple[DomainErrorData, ...]:
    warnings: list[DomainErrorData] = []
    for check in profile.unit_consistency_checks:
        residual = (
            frame[check.source_metric_column] * check.comparison_per_metric
            - frame[check.comparison_column]
        ).abs()
        maximum_value = residual.max()
        if not isinstance(maximum_value, (int, float)):
            _fail(
                "STREAM_TYPE_INVALID",
                "Unit consistency check did not produce a numeric residual",
                field_or_path=check.comparison_column,
                remediation="Repair the profiled numeric columns.",
            )
        maximum = float(maximum_value)
        if maximum > check.invalid_tolerance:
            _fail(
                "STREAM_UNIT_MISMATCH",
                "Metric and comparison-unit velocity columns disagree",
                field_or_path=check.comparison_column,
                remediation="Repair the source units or select the correct engineering profile.",
                diagnostics={
                    "source_path": relative_path,
                    "max_residual": maximum,
                    "invalid_tolerance": check.invalid_tolerance,
                    "tolerance_unit": check.tolerance_unit,
                },
            )
        if maximum > check.warning_tolerance:
            warnings.append(
                DomainErrorData(
                    error_code="STREAM_UNIT_MISMATCH",
                    severity=ErrorSeverity.WARNING,
                    recoverable=True,
                    message="Velocity unit cross-check exceeds the warning tolerance",
                    field_or_path=check.comparison_column,
                    remediation="Confirm the exported engineering-unit conversion.",
                    diagnostics={
                        "source_path": relative_path,
                        "max_residual": maximum,
                        "warning_tolerance": check.warning_tolerance,
                        "tolerance_unit": check.tolerance_unit,
                    },
                )
            )
    return tuple(warnings)


def _build_views(
    frame: pl.DataFrame,
    request: AdapterRequest,
    profile: CsvProfile,
) -> dict[str, NormalizedStream]:
    streams: dict[str, NormalizedStream] = {}
    normalized_ids = {
        "X": "flight-state-normalized-v0.1",
        "U": "control-input-normalized-v0.1",
    }
    for modality, role in (("X", CsvColumnRole.X), ("U", CsvColumnRole.U)):
        selected = ["source_row_index", profile.source_timestamp_column]
        selected.extend(
            column.canonical_name
            for column in profile.columns
            if column.role is role and column.canonical_name != profile.source_timestamp_column
        )
        stream_frame = frame.select(selected)
        descriptor = request.descriptors[modality]
        streams[modality] = NormalizedStream(
            modality=modality,
            schema_id=normalized_ids[modality],
            clock_id=descriptor.clock_id,
            source_timestamp_column=profile.source_timestamp_column,
            primary_table_role="samples",
            tables={"samples": stream_frame},
            json_artifacts={},
            file_artifacts={},
            source_paths=request.source_paths,
            source_checksums=request.verified_digests,
        )
    return streams


def _timestamp_failure(relative_path: str, detail: str) -> NoReturn:
    _fail(
        "STREAM_TIMESTAMP_INVALID",
        f"Simulator CSV {detail}",
        field_or_path=relative_path,
        remediation="Repair or re-export the source timeline.",
    )


def _fail(
    error_code: str,
    message: str,
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
            field_or_path=field_or_path,
            remediation=remediation,
            diagnostics=diagnostics or {},
        )
    )


__all__ = ["ProfiledCsvAdapter"]
