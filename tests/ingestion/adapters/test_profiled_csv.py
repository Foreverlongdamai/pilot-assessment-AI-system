from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from pilot_assessment.contracts.session import StreamDescriptor
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError, AdapterRequest
from pilot_assessment.ingestion.adapters.profiled_csv import ProfiledCsvAdapter
from pilot_assessment.ingestion.profiles import CsvProfile, load_builtin_profiles

HEADERS = (
    "Simulation time",
    " Xe m",
    " Ye m",
    " Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "  V_ey m/s",
    " V_ez m/s",
    "V_ex kts",
    "  V_ey kts",
    " V_ez kts",
    "V_bx m/s",
    " V_by m/s",
    " V_bz m/s",
    "phi deg",
    " theta deg",
    " psi deg",
    "p deg/s",
    " q deg/s",
    " r deg/s",
    "ax m/s^2",
    " ay m/s^2",
    " az m/s^2",
    "alpha deg",
    " beta deg",
    "Control_Mode",
    "Pilot Yaw",
    " Pilot Lon",
    " Pilot Lat",
    " Pilot Heave",
    "Time Delay s",
    " Lon Frequency rad/s",
    " Long Damping ",
)
KNOTS_PER_METRE_PER_SECOND = 1.9438444924406048


def _rows(count: int = 201) -> list[list[str]]:
    rows: list[list[str]] = []
    for index in range(count):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        rows.append(
            [
                str(time_s),
                str(time_s),
                "0",
                "-31.668",
                "21.008",
                *(str(value) for value in velocities),
                *(str(value * KNOTS_PER_METRE_PER_SECOND) for value in velocities),
                *(str(value) for value in velocities),
                "0",
                "0",
                "270",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "1",
                "0",
                str(-100.0 * index / (count - 1)),
                "0",
                "0",
                "0.2",
                "8",
                "0.8",
            ]
        )
    assert all(len(row) == len(HEADERS) for row in rows)
    return rows


def _csv_bytes(headers: tuple[str, ...], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _descriptor(modality: str, digest: str) -> StreamDescriptor:
    return StreamDescriptor(
        modality=modality,
        status="present",
        required_for_import=True,
        paths=["streams/simulator.csv"],
        format="csv",
        schema_id="cranfield-simulator-combined-csv-raw-v0.1",
        clock_id="sim_clock",
        clock_sync={
            "method": "master_clock",
            "scale": 1.0,
            "offset_ns": 0,
            "drift_ppm": 0.0,
            "residual_rms_ms": 0.0,
            "residual_max_ms": 0.0,
        },
        sample_rate_hz=100.0,
        units="profile",
        quality_summary=None,
        checksums={"streams/simulator.csv": digest},
        metadata={
            "adapter_profile_id": "cranfield-simulator-combined-csv-raw-v0.1",
            "shared_source_id": "simulator-main",
            "view_id": modality,
        },
    )


def _request(tmp_path: Path, payload: bytes) -> AdapterRequest:
    source = tmp_path / "streams" / "simulator.csv"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    profile = load_builtin_profiles()[
        "cranfield-simulator-combined-csv-raw-v0.1"
    ]
    assert isinstance(profile, CsvProfile)
    return AdapterRequest(
        bundle_root=tmp_path,
        descriptors={modality: _descriptor(modality, digest) for modality in ("X", "U")},
        source_paths=("streams/simulator.csv",),
        verified_digests={"streams/simulator.csv": digest},
        profile=profile,
    )


def test_combined_csv_produces_x_u_and_constant_context(tmp_path: Path) -> None:
    request = _request(tmp_path, _csv_bytes(HEADERS, _rows()))

    result = ProfiledCsvAdapter().inspect(request)

    assert set(result.streams) == {"X", "U"}
    assert result.streams["X"].primary_table.height == 201
    assert result.streams["U"].primary_table["control.longitudinal_raw"].min() == -100.0
    assert result.context["context.time_delay_s"] == 0.2
    assert "context.time_delay_s" not in result.streams["X"].primary_table.columns
    assert result.streams["X"].primary_table.schema["source_row_index"] == pl.UInt64
    assert request.bundle_root.joinpath(*request.source_paths[0].split("/")).read_bytes() == (
        _csv_bytes(HEADERS, _rows())
    )


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda headers, rows: (headers, [*rows[:-1], rows[-1][:-1]]), "STREAM_FORMAT_INVALID"),
        (
            lambda headers, rows: (
                tuple("Pilot Lon " if item.strip() == "Pilot Lat" else item for item in headers),
                rows,
            ),
            "STREAM_SCHEMA_MISMATCH",
        ),
        (
            lambda headers, rows: (
                tuple("Unknown Time" if item == "Simulation time" else item for item in headers),
                rows,
            ),
            "STREAM_SCHEMA_MISMATCH",
        ),
        (
            lambda headers, rows: (
                headers,
                [*rows[:10], [*rows[10][:27], "not-a-number", *rows[10][28:]], *rows[11:]],
            ),
            "STREAM_TYPE_INVALID",
        ),
        (
            lambda headers, rows: (
                headers,
                [*rows[:10], [*rows[10][:27], "NaN", *rows[10][28:]], *rows[11:]],
            ),
            "STREAM_TYPE_INVALID",
        ),
        (
            lambda headers, rows: (
                headers,
                [*rows[:10], [rows[9][0], *rows[10][1:]], *rows[11:]],
            ),
            "STREAM_TIMESTAMP_INVALID",
        ),
    ],
)
def test_csv_structure_and_required_values_return_typed_errors(
    tmp_path: Path,
    mutate: Callable[
        [tuple[str, ...], list[list[str]]],
        tuple[tuple[str, ...], list[list[str]]],
    ],
    error_code: str,
) -> None:
    headers, rows = mutate(HEADERS, _rows())
    request = _request(tmp_path, _csv_bytes(headers, rows))

    with pytest.raises(AdapterInspectionError) as caught:
        ProfiledCsvAdapter().inspect(request)

    assert caught.value.issue.error_code == error_code


def test_rate_gap_and_context_rules_are_enforced(tmp_path: Path) -> None:
    rate_rows = _rows()
    for index, row in enumerate(rate_rows):
        row[0] = str(index / 50.0)
    rate_request = _request(tmp_path / "rate", _csv_bytes(HEADERS, rate_rows))
    with pytest.raises(AdapterInspectionError) as rate_error:
        ProfiledCsvAdapter().inspect(rate_request)
    assert rate_error.value.issue.error_code == "SAMPLE_RATE_MISMATCH"

    gap_rows = _rows()
    for index in range(100, len(gap_rows)):
        gap_rows[index][0] = str(float(gap_rows[index][0]) + 0.1)
    gap_request = _request(tmp_path / "gap", _csv_bytes(HEADERS, gap_rows))
    with pytest.raises(AdapterInspectionError) as gap_error:
        ProfiledCsvAdapter().inspect(gap_request)
    assert gap_error.value.issue.error_code == "STREAM_TIMESTAMP_INVALID"

    context_rows = _rows()
    context_rows[100][30] = "0.3"
    context_request = _request(tmp_path / "context", _csv_bytes(HEADERS, context_rows))
    with pytest.raises(AdapterInspectionError) as context_error:
        ProfiledCsvAdapter().inspect(context_request)
    assert context_error.value.issue.error_code == "STREAM_CONTEXT_NOT_CONSTANT"


def test_unit_residual_has_warning_and_invalid_thresholds(tmp_path: Path) -> None:
    warning_rows = _rows()
    warning_rows[50][8] = str(float(warning_rows[50][8]) + 0.003)
    warning_result = ProfiledCsvAdapter().inspect(
        _request(tmp_path / "warning", _csv_bytes(HEADERS, warning_rows))
    )
    assert [issue.error_code for issue in warning_result.issues] == [
        "STREAM_UNIT_MISMATCH"
    ]

    invalid_rows = _rows()
    invalid_rows[50][8] = str(float(invalid_rows[50][8]) + 0.03)
    with pytest.raises(AdapterInspectionError) as caught:
        ProfiledCsvAdapter().inspect(
            _request(tmp_path / "invalid", _csv_bytes(HEADERS, invalid_rows))
        )
    assert caught.value.issue.error_code == "STREAM_UNIT_MISMATCH"


def test_source_digest_change_is_rejected(tmp_path: Path) -> None:
    request = _request(tmp_path, _csv_bytes(HEADERS, _rows()))
    request.bundle_root.joinpath(*request.source_paths[0].split("/")).write_bytes(
        b"changed"
    )

    with pytest.raises(AdapterInspectionError) as caught:
        ProfiledCsvAdapter().inspect(request)

    assert caught.value.issue.error_code == "SOURCE_CHANGED_DURING_READINESS"
