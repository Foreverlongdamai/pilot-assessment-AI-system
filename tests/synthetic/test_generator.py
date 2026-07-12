from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from pilot_assessment.contracts.session import (
    CORE_MODALITIES,
    SessionManifest,
    StreamStatus,
)
from pilot_assessment.ingestion import readiness as readiness_module
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError
from pilot_assessment.ingestion.manifest_loader import ManifestLoader
from pilot_assessment.ingestion.parquet_io import read_profiled_parquet_metadata
from pilot_assessment.synthetic.generator import generate_synthetic_bundle, main

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


def _write_simulator_csv(
    path: Path,
    *,
    duration_s: float = 2.0,
    control_lon: Callable[[float], float] | None = None,
) -> bytes:
    count = round(duration_s * 100.0) + 1
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADERS)
    for index in range(count):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        writer.writerow(
            [
                str(time_s),
                str(0.75 * time_s),
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
                str(
                    control_lon(time_s) if control_lon is not None else -100.0 * index / (count - 1)
                ),
                "0",
                "0",
                "0.2",
                "8",
                "0.8",
            ]
        )
    payload = output.getvalue().encode("utf-8")
    path.write_bytes(payload)
    return payload


@pytest.fixture
def simulator_micro_csv(tmp_path: Path) -> Path:
    source = tmp_path / "source.csv"
    _write_simulator_csv(source)
    return source


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _manifest(root: Path) -> SessionManifest:
    return SessionManifest.model_validate_json((root / "manifest.json").read_bytes())


def _assert_clock_truth(
    manifest: SessionManifest,
    modality: str,
    *,
    offset_ns: int,
    drift_ppm: float,
) -> None:
    clock = manifest.streams[modality].clock_sync
    assert clock is not None
    assert clock.method == "synthetic-declared-truth-v0.1"
    assert clock.offset_ns == offset_ns
    assert clock.drift_ppm == drift_ppm
    assert clock.scale == pytest.approx(1.0 + drift_ppm * 1e-6)
    assert clock.residual_rms_ms == 0.0
    assert clock.residual_max_ms == 0.0


def test_generator_writes_a_complete_deterministic_bundle(
    tmp_path: Path,
    simulator_micro_csv: Path,
) -> None:
    source_bytes = simulator_micro_csv.read_bytes()
    first = generate_synthetic_bundle(
        simulator_micro_csv,
        tmp_path / "first",
        seed=20260711,
    )
    second = generate_synthetic_bundle(
        simulator_micro_csv,
        tmp_path / "second",
        seed=20260711,
    )

    assert _snapshot(first) == _snapshot(second)
    assert simulator_micro_csv.read_bytes() == source_bytes
    assert (first / "streams" / "simulator.csv").read_bytes() == source_bytes

    manifest = _manifest(first)
    assert manifest.streams["X"].paths == manifest.streams["U"].paths
    assert manifest.streams["X"].checksums == manifest.streams["U"].checksums
    source_extensions = manifest.source_session.extensions
    assert source_extensions["source_artifact_role"] == "captured-format-sample-xu"
    assert source_extensions["task_validity"] == "not_asserted"
    assert source_extensions["ground_truth_status"] == "absent"
    assert manifest.task.task_profile_id == "synthetic-interface-fixture-v0.1"
    assert manifest.task.scenario_id == "synthetic-format-sample-01"
    assert manifest.task.reference is not None
    assert manifest.task.reference.reference_id == "synthetic-format-fixture-path-v0.1"
    assert manifest.task.reference.stream_id == "task_reference"
    reference = manifest.streams["task_reference"]
    assert reference.paths == ["references/commanded_path.parquet"]
    assert reference.schema_id == "task-reference-path-raw-v0.1"
    assert reference.metadata["reference_validity"] == "synthetic-format-fixture-only"
    assert reference.metadata["trajectory_standard_status"] == "not_asserted"
    assert all(manifest.streams[key].status is StreamStatus.PRESENT for key in CORE_MODALITIES)
    assert manifest.privacy.classification == "synthetic-test-data"
    assert manifest.privacy.contains_biometric_data is False
    assert manifest.privacy.biometric_modalities_export_pending == []
    synthetic = manifest.extensions["synthetic"]
    assert isinstance(synthetic, dict)
    assert synthetic["scientific_validation_status"] == "not_supported"
    assert synthetic["seed"] == 20260711
    assert synthetic["lock_fingerprint"]
    assert synthetic["source_xu_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert synthetic["parameters"]["control_activity_definition"] == (
        "min(1,abs(control.longitudinal_raw)/100)"
    )
    assert synthetic["parameters"]["control_activity_role"] == "synthetic_control_driver"
    assert synthetic["parameters"]["control_activity_scientific_semantics"] == "none"
    assert synthetic["parameters"]["control_activity_not_ground_truth_for"] == [
        "workload",
        "control_quality",
        "physiology",
        "O13",
        "performance",
    ]
    assert synthetic["parameters"]["physiology_activity_resampling"] == ("linear-clamped-v0.1")
    assert synthetic["provenance_scope"] == ("captured-format-sample-xu-plus-synthetic-modalities")

    expected_clocks = {
        "X": (0, 0.0),
        "U": (0, 0.0),
        "I": (4_000_000, 0.0),
        "G": (7_000_000, 20.0),
        "EEG": (-12_000_000, -15.0),
        "ECG": (9_000_000, 10.0),
        "pilot_camera": (15_000_000, 0.0),
        "task_reference": (0, 0.0),
    }
    for modality, (offset_ns, drift_ppm) in expected_clocks.items():
        _assert_clock_truth(
            manifest,
            modality,
            offset_ns=offset_ns,
            drift_ppm=drift_ppm,
        )

    assert set(manifest.streams["I"].metadata["artifact_roles"]) == {
        "frame_index",
        "aoi_instances",
        "frame_images",
    }
    assert read_profiled_parquet_metadata(
        first / "streams" / "vr_scene" / "frame_index.parquet"
    ) == {
        "contract_version": "0.1.0",
        "schema_id": "vr-frame-index-raw-v0.1",
    }
    sidecar = json.loads(
        (first / "streams" / "eeg" / "eeg_sidecar.json").read_text(encoding="utf-8")
    )
    assert sidecar["seed"] == 20260711
    assert sidecar["synthetic_not_neurophysiological"] is True

    loaded = ManifestLoader().load(first)
    assert loaded.manifest == manifest
    checksum_lines = (
        (first / "integrity" / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    )
    checksum_paths = [line.split("  ", maxsplit=1)[1] for line in checksum_lines]
    assert checksum_paths == sorted(set(checksum_paths))
    assert set(checksum_paths) == set(loaded.verified_paths)


def test_seed_changes_content_and_provenance_but_not_inventory(
    tmp_path: Path,
    simulator_micro_csv: Path,
) -> None:
    first = generate_synthetic_bundle(simulator_micro_csv, tmp_path / "first", seed=7)
    second = generate_synthetic_bundle(simulator_micro_csv, tmp_path / "second", seed=8)

    first_manifest = _manifest(first)
    second_manifest = _manifest(second)
    assert _snapshot(first) != _snapshot(second)
    assert first_manifest.session_id != second_manifest.session_id
    assert set(first_manifest.streams) == set(second_manifest.streams)
    for stream_id in first_manifest.streams:
        assert first_manifest.streams[stream_id].paths == second_manifest.streams[stream_id].paths
        assert (
            first_manifest.streams[stream_id].schema_id
            == second_manifest.streams[stream_id].schema_id
        )
    assert (first / "streams" / "simulator.csv").read_bytes() == (
        second / "streams" / "simulator.csv"
    ).read_bytes()


def test_generator_uses_source_controls_only_as_a_synthetic_signal_driver(
    tmp_path: Path,
) -> None:
    source = tmp_path / "activity-step.csv"
    _write_simulator_csv(
        source,
        duration_s=8.0,
        control_lon=lambda time_s: 0.0 if time_s < 4.0 else -100.0,
    )

    bundle = generate_synthetic_bundle(source, tmp_path / "bundle", seed=20260711)
    eeg = pl.read_parquet(bundle / "streams" / "eeg" / "eeg_samples.parquet")
    peaks = pl.read_parquet(bundle / "streams" / "ecg" / "r_peaks.parquet")

    low_eeg = eeg.filter(pl.col("source_timestamp_s").is_between(1.0, 3.0, closed="both"))["Fp1_uV"]
    high_eeg = eeg.filter(pl.col("source_timestamp_s").is_between(5.0, 7.0, closed="both"))[
        "Fp1_uV"
    ]
    low_rms = float((low_eeg.cast(pl.Float64).pow(2).mean()) ** 0.5)
    high_rms = float((high_eeg.cast(pl.Float64).pow(2).mean()) ** 0.5)
    assert high_rms > 2.0 * low_rms

    low_rr = peaks.filter(pl.col("source_timestamp_s") < 3.5)["rr_interval_ms"]
    high_rr = peaks.filter(pl.col("source_timestamp_s") > 4.5)["rr_interval_ms"]
    assert float(low_rr.mean()) == pytest.approx(60_000.0 / 70.0, abs=1.0)
    assert float(high_rr.mean()) == pytest.approx(60_000.0 / 90.0, abs=1.0)


def test_generator_runs_the_m2_readiness_self_check(
    tmp_path: Path,
    simulator_micro_csv: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    original = readiness_module.inspect_ingestion_readiness

    def counted(bundle_root: str | Path) -> object:
        calls.append(Path(bundle_root))
        return original(bundle_root)

    monkeypatch.setattr(readiness_module, "inspect_ingestion_readiness", counted)
    bundle = generate_synthetic_bundle(
        simulator_micro_csv,
        tmp_path / "self-checked",
        seed=20260711,
    )

    assert calls == [bundle]


def test_generator_rejects_nonempty_output_without_modifying_it(
    tmp_path: Path,
    simulator_micro_csv: Path,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("owner-data", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output directory is not empty"):
        generate_synthetic_bundle(simulator_micro_csv, output)

    assert marker.read_text(encoding="utf-8") == "owner-data"
    assert list(output.iterdir()) == [marker]


def test_generator_rejects_bad_csv_before_creating_output(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("Simulation time,Pilot Lon\n0,0\n", encoding="utf-8")
    output = tmp_path / "bundle"

    with pytest.raises(AdapterInspectionError):
        generate_synthetic_bundle(source, output)

    assert not output.exists()


def test_generator_rejects_bundle_that_would_exceed_m1_path_budget(
    tmp_path: Path,
) -> None:
    source = tmp_path / "long.csv"
    _write_simulator_csv(source, duration_s=223.0)

    with pytest.raises(ValueError, match="declared path budget"):
        generate_synthetic_bundle(source, tmp_path / "bundle")

    assert not (tmp_path / "bundle").exists()


@pytest.mark.parametrize("seed", [-1, 2**63])
def test_generator_rejects_out_of_range_seed(
    tmp_path: Path,
    simulator_micro_csv: Path,
    seed: int,
) -> None:
    with pytest.raises(ValueError, match="seed"):
        generate_synthetic_bundle(simulator_micro_csv, tmp_path / str(seed), seed=seed)


def test_module_cli_generates_the_same_valid_bundle(
    tmp_path: Path,
    simulator_micro_csv: Path,
) -> None:
    output = tmp_path / "cli-bundle"

    exit_code = main(
        [
            "--xu-csv",
            str(simulator_micro_csv),
            "--output",
            str(output),
            "--seed",
            "20260711",
            "--duration-mode",
            "source",
        ]
    )

    assert exit_code == 0
    assert ManifestLoader().load(output).manifest.session_id == _manifest(output).session_id
