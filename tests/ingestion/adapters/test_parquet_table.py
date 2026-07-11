from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest
from pydantic import JsonValue

from pilot_assessment.ingestion.adapters.base import AdapterInspectionError
from pilot_assessment.ingestion.adapters.parquet_table import (
    inspect_eeg_sidecar,
    inspect_parquet_table,
)
from pilot_assessment.ingestion.parquet_io import write_profiled_parquet
from pilot_assessment.ingestion.profiles import (
    JsonProfile,
    TableProfile,
    load_builtin_profiles,
)

CHANNELS = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4")
CHANNEL_UNITS = {channel: "uV" for channel in CHANNELS}


def _table_profile(schema_id: str) -> TableProfile:
    profile = load_builtin_profiles()[schema_id]
    assert isinstance(profile, TableProfile)
    return profile


def _sidecar_profile() -> JsonProfile:
    profile = load_builtin_profiles()["eeg-sidecar-v0.1"]
    assert isinstance(profile, JsonProfile)
    return profile


def _gaze_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series([0, 1, 2], dtype=pl.UInt64),
            "source_timestamp_s": pl.Series([0.0, 1.0 / 120.0, 2.0 / 120.0], dtype=pl.Float64),
            "scene_frame_id": pl.Series([0, 0, 1], dtype=pl.UInt64),
            "viewport_x_norm": pl.Series([0.2, None, 0.8], dtype=pl.Float32),
            "viewport_y_norm": pl.Series([0.3, None, 0.7], dtype=pl.Float32),
            "origin_x_m": pl.Series([0.0, None, 0.0], dtype=pl.Float32),
            "origin_y_m": pl.Series([0.0, None, 0.0], dtype=pl.Float32),
            "origin_z_m": pl.Series([0.0, None, 0.0], dtype=pl.Float32),
            "ray_x": pl.Series([0.1, None, 0.1], dtype=pl.Float32),
            "ray_y": pl.Series([0.2, None, 0.2], dtype=pl.Float32),
            "ray_z": pl.Series([0.97, None, 0.97], dtype=pl.Float32),
            "left_pupil_mm": pl.Series([3.1, None, 3.2], dtype=pl.Float32),
            "right_pupil_mm": pl.Series([3.0, None, 3.1], dtype=pl.Float32),
            "binocular_valid": pl.Series([True, True, True], dtype=pl.Boolean),
            "confidence": pl.Series([0.9, 0.0, 0.95], dtype=pl.Float32),
            "blink": pl.Series([False, True, False], dtype=pl.Boolean),
            "assigned_aoi_id": pl.Series(["PFD", None, "PFD"], dtype=pl.String),
            "assignment_confidence": pl.Series([0.8, None, 0.9], dtype=pl.Float32),
        }
    )


def _eeg_frame(row_count: int = 3) -> pl.DataFrame:
    indices = list(range(row_count))
    values = [float(index) for index in indices]
    data: dict[str, pl.Series] = {
        "sample_index": pl.Series(indices, dtype=pl.UInt64),
        "source_timestamp_s": pl.Series([index / 256.0 for index in indices], dtype=pl.Float64),
    }
    for channel in CHANNELS:
        data[f"{channel}_uV"] = pl.Series(values, dtype=pl.Float32)
    data["signal_valid"] = pl.Series([True] * row_count, dtype=pl.Boolean)
    data["artifact_code"] = pl.Series([None] * row_count, dtype=pl.String)
    return pl.DataFrame(data)


def _write_table(
    path: Path,
    frame: pl.DataFrame,
    schema_id: str,
    *,
    contract_version: str = "0.1.0",
) -> None:
    frame.write_parquet(
        path,
        metadata={"contract_version": contract_version, "schema_id": schema_id},
    )


def test_parquet_table_accepts_exact_profile_and_nullable_measurements(tmp_path: Path) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    frame = _gaze_frame()
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    inspected = inspect_parquet_table(path, profile)

    assert inspected.equals(frame)


@pytest.mark.parametrize(
    ("metadata", "error_code"),
    [
        ({"contract_version": "0.1.0", "schema_id": "wrong-v0.1"}, "STREAM_SCHEMA_MISMATCH"),
        (
            {"contract_version": "9.9.9", "schema_id": "gaze-sample-raw-v0.1"},
            "STREAM_SCHEMA_MISMATCH",
        ),
        ({"contract_version": "0.1.0"}, "STREAM_SCHEMA_MISMATCH"),
    ],
)
def test_parquet_table_requires_exact_embedded_contract_metadata(
    tmp_path: Path,
    metadata: dict[str, str],
    error_code: str,
) -> None:
    path = tmp_path / "gaze_samples.parquet"
    _gaze_frame().write_parquet(path, metadata=metadata)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, _table_profile("gaze-sample-raw-v0.1"))

    assert caught.value.issue.error_code == error_code


@pytest.mark.parametrize(
    "mutate",
    [
        lambda frame: frame.select(list(reversed(frame.columns))),
        lambda frame: frame.drop("confidence"),
        lambda frame: frame.with_columns(pl.col("gaze_sample_id").cast(pl.UInt32)),
    ],
    ids=["ordered-columns", "missing-column", "exact-dtype"],
)
def test_parquet_table_requires_exact_ordered_columns_and_dtypes(
    tmp_path: Path,
    mutate: Callable[[pl.DataFrame], pl.DataFrame],
) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(mutate(_gaze_frame()), path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_parquet_table_rejects_null_in_required_column(tmp_path: Path) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    frame = _gaze_frame().with_columns(pl.Series("confidence", [0.9, None, 0.95], dtype=pl.Float32))
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_TYPE_INVALID"


@pytest.mark.parametrize("failure", ["duplicate", "out_of_order"])
def test_parquet_table_requires_unique_ordered_composite_sort_key(
    tmp_path: Path,
    failure: str,
) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    frame = _gaze_frame()
    if failure == "duplicate":
        frame = frame.with_columns(
            pl.Series("gaze_sample_id", [0, 0, 2], dtype=pl.UInt64),
            pl.Series(
                "source_timestamp_s",
                [0.0, 0.0, 2.0 / 120.0],
                dtype=pl.Float64,
            ),
        )
    else:
        frame = frame[[0, 2, 1]]
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_TIMESTAMP_INVALID"


@pytest.mark.parametrize(
    ("column", "values"),
    [
        ("viewport_x_norm", [0.2, None, 1.1]),
        ("confidence", [0.9, float("nan"), 0.95]),
        ("source_timestamp_s", [0.0, float("inf"), 2.0 / 120.0]),
    ],
    ids=["normalized-range", "nan", "infinity"],
)
def test_parquet_table_rejects_out_of_range_or_non_finite_values(
    tmp_path: Path,
    column: str,
    values: list[float | None],
) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    dtype = _gaze_frame().schema[column]
    frame = _gaze_frame().with_columns(pl.Series(column, values, dtype=dtype))
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_TYPE_INVALID"


def test_parquet_table_rejects_sample_rate_outside_profile_tolerance(tmp_path: Path) -> None:
    profile = _table_profile("gaze-sample-raw-v0.1")
    frame = _gaze_frame().with_columns(
        pl.Series("source_timestamp_s", [0.0, 0.01, 0.02], dtype=pl.Float64)
    )
    path = tmp_path / "gaze_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "SAMPLE_RATE_MISMATCH"


def test_parquet_table_rejects_unguarded_nullable_measurement(tmp_path: Path) -> None:
    profile = _table_profile("eeg-sample-raw-v0.1")
    frame = _eeg_frame().with_columns(pl.Series("Fp1_uV", [0.0, None, 2.0], dtype=pl.Float32))
    path = tmp_path / "eeg_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_TYPE_INVALID"


def test_parquet_table_accepts_null_measurement_with_nonempty_artifact_code(
    tmp_path: Path,
) -> None:
    profile = _table_profile("eeg-sample-raw-v0.1")
    frame = _eeg_frame().with_columns(
        pl.Series("Fp1_uV", [0.0, None, 2.0], dtype=pl.Float32),
        pl.Series("artifact_code", [None, "motion", None], dtype=pl.String),
    )
    path = tmp_path / "eeg_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    assert inspect_parquet_table(path, profile).equals(frame)


def test_parquet_table_enforces_minimum_valid_fraction(tmp_path: Path) -> None:
    profile = _table_profile("eeg-sample-raw-v0.1")
    frame = _eeg_frame().with_columns(
        pl.Series("signal_valid", [True, False, True], dtype=pl.Boolean)
    )
    path = tmp_path / "eeg_samples.parquet"
    write_profiled_parquet(frame, path, schema_id=profile.schema_id)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, profile)

    assert caught.value.issue.error_code == "STREAM_TYPE_INVALID"


def _valid_sidecar() -> dict[str, object]:
    return {
        "schema_id": "eeg-sidecar-v0.1",
        "montage_id": "synthetic-10-20-eight-channel-v0.1",
        "reference": "common-average",
        "channel_order": list(CHANNELS),
        "channel_units": dict(CHANNEL_UNITS),
        "sample_rate_hz": 256.0,
        "clock_id": "eeg_clock",
        "generator_id": "synthetic-multimodal-generator-v0.1",
        "seed": 20260711,
        "synthetic_not_neurophysiological": True,
    }


def _inspect_sidecar(path: Path) -> dict[str, JsonValue]:
    return inspect_eeg_sidecar(
        path,
        _sidecar_profile(),
        expected_clock_id="eeg_clock",
        expected_channel_order=CHANNELS,
        expected_channel_units=CHANNEL_UNITS,
        expected_sample_rate_hz=256.0,
        expected_generator_id="synthetic-multimodal-generator-v0.1",
        expected_seed=20260711,
    )


def test_eeg_sidecar_accepts_exact_strict_synthetic_contract(tmp_path: Path) -> None:
    path = tmp_path / "eeg_sidecar.json"
    payload = _valid_sidecar()
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")

    assert _inspect_sidecar(path) == payload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: {key: value for key, value in payload.items() if key != "reference"},
        lambda payload: {**payload, "extra": "forbidden"},
        lambda payload: {**payload, "sample_rate_hz": "256.0"},
        lambda payload: {**payload, "seed": True},
    ],
    ids=["missing-field", "extra-field", "wrong-float-type", "bool-is-not-int"],
)
def test_eeg_sidecar_requires_exact_fields_and_json_types(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], dict[str, object]],
) -> None:
    path = tmp_path / "eeg_sidecar.json"
    path.write_text(json.dumps(mutate(_valid_sidecar())), encoding="utf-8")

    with pytest.raises(AdapterInspectionError) as caught:
        _inspect_sidecar(path)

    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("schema_id", "wrong-sidecar-v0.1", "STREAM_SCHEMA_MISMATCH"),
        ("channel_order", [*CHANNELS[:-1], "O1"], "STREAM_SCHEMA_MISMATCH"),
        ("channel_units", {**CHANNEL_UNITS, "Fp1": "mV"}, "STREAM_SCHEMA_MISMATCH"),
        ("sample_rate_hz", 250.0, "SAMPLE_RATE_MISMATCH"),
        ("clock_id", "wrong_clock", "STREAM_SCHEMA_MISMATCH"),
        ("generator_id", "wrong-generator-v0.1", "STREAM_SCHEMA_MISMATCH"),
        ("seed", 7, "STREAM_SCHEMA_MISMATCH"),
        ("synthetic_not_neurophysiological", False, "STREAM_SCHEMA_MISMATCH"),
    ],
)
def test_eeg_sidecar_requires_exact_table_and_synthetic_provenance(
    tmp_path: Path,
    field: str,
    value: object,
    error_code: str,
) -> None:
    payload = _valid_sidecar()
    payload[field] = value
    path = tmp_path / "eeg_sidecar.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AdapterInspectionError) as caught:
        _inspect_sidecar(path)

    assert caught.value.issue.error_code == error_code


@pytest.mark.parametrize(
    "payload",
    [
        b'\xff{"schema_id":"eeg-sidecar-v0.1"}',
        b'{"schema_id":"eeg-sidecar-v0.1","schema_id":"duplicate-v0.1"}',
        b'{"schema_id":"eeg-sidecar-v0.1","sample_rate_hz":NaN}',
    ],
    ids=["invalid-utf8", "duplicate-key", "non-standard-number"],
)
def test_eeg_sidecar_rejects_non_strict_json(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "eeg_sidecar.json"
    path.write_bytes(payload)

    with pytest.raises(AdapterInspectionError) as caught:
        _inspect_sidecar(path)

    assert caught.value.issue.error_code == "STREAM_FORMAT_INVALID"
