from __future__ import annotations

import csv
import io
from pathlib import Path

from pilot_assessment.contracts.synchronization import (
    IntervalTemporalArtifactMetrics,
    PointTemporalArtifactMetrics,
    SessionWindow,
    SynchronizationDisposition,
    SynchronizationItemStatus,
)
from pilot_assessment.ingestion.manifest_loader import ManifestLoader
from pilot_assessment.synchronization import synchronize_bundle
from pilot_assessment.synthetic import generate_synthetic_bundle

_HEADERS = (
    "Simulation time",
    "Xe m",
    "Ye m",
    "Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "V_ey m/s",
    "V_ez m/s",
    "V_ex kts",
    "V_ey kts",
    "V_ez kts",
    "V_bx m/s",
    "V_by m/s",
    "V_bz m/s",
    "phi deg",
    "theta deg",
    "psi deg",
    "p deg/s",
    "q deg/s",
    "r deg/s",
    "ax m/s^2",
    "ay m/s^2",
    "az m/s^2",
    "alpha deg",
    "beta deg",
    "Control_Mode",
    "Pilot Yaw",
    "Pilot Lon",
    "Pilot Lat",
    "Pilot Heave",
    "Time Delay s",
    "Lon Frequency rad/s",
    "Long Damping",
)
_KNOTS_PER_METRE_PER_SECOND = 1.9438444924406048


def _write_micro_csv(path: Path) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_HEADERS)
    for index in range(201):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        writer.writerow(
            [
                time_s,
                0.75 * time_s,
                0,
                -31.668,
                21.008,
                *velocities,
                *(value * _KNOTS_PER_METRE_PER_SECOND for value in velocities),
                *velocities,
                0,
                0,
                270,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                -100.0 * index / 200,
                0,
                0,
                0.2,
                8,
                0.8,
            ]
        )
    path.write_bytes(output.getvalue().encode("utf-8"))


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def test_micro_bundle_runs_through_full_m3_without_mutating_raw_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "simulator_micro.csv"
    _write_micro_csv(source)
    source_before = source.read_bytes()
    bundle = generate_synthetic_bundle(source, tmp_path / "bundle", seed=20260711)
    bundle_before = _snapshot_files(bundle)
    manifest = ManifestLoader().load(bundle).manifest

    outcome = synchronize_bundle(bundle)

    assert outcome.report.session_window == SessionWindow(
        start_t_ns=0,
        end_t_ns=2_000_000_000,
        source="master-clock-x-mapped-coverage-v1",
    )
    assert outcome.report.disposition is SynchronizationDisposition.READY
    assert outcome.report.can_continue_to_anchor_availability is True
    assert outcome.report.formal_run_authorized is False
    assert outcome.aligned_session is not None
    assert outcome.report.synchronization_fingerprint == (
        outcome.aligned_session.synchronization_fingerprint
    )

    primary_roles = {
        "X": ("samples", 201, 201),
        "U": ("samples", 201, 201),
        "I": ("frame_index", 61, 60),
        "G": ("gaze_samples", 241, 240),
        "EEG": ("samples", 513, 509),
        "ECG": ("samples", 501, 498),
        "pilot_camera": ("frame_index", 31, 30),
    }
    for modality, (role, expected_total, expected_in_session) in primary_roles.items():
        result = outcome.report.stream_results[modality]
        assert result.synchronization_status is SynchronizationItemStatus.ALIGNED
        metrics = result.artifacts[role]
        assert isinstance(metrics, PointTemporalArtifactMetrics)
        assert metrics.total_rows == expected_total
        assert metrics.in_session_rows == expected_in_session
        assert metrics.interpolated_rows == 0
        assert outcome.aligned_session.streams[modality].tables[role].height == expected_total

    reference = outcome.report.task_reference_result
    assert reference is not None
    assert reference.synchronization_status is SynchronizationItemStatus.ALIGNED
    reference_metrics = reference.artifacts["commanded_path"]
    assert isinstance(reference_metrics, PointTemporalArtifactMetrics)
    assert reference_metrics.total_rows == 201
    assert reference_metrics.in_session_rows == 201
    assert reference_metrics.interpolated_rows == 0
    assert outcome.aligned_session.task_reference is not None
    assert outcome.aligned_session.task_reference.tables["commanded_path"].height == 201

    aoi = outcome.report.stream_results["I"].artifacts["aoi_instances"]
    assert isinstance(aoi, PointTemporalArtifactMetrics)
    assert aoi.total_rows == 122
    assert aoi.in_session_rows == 120
    assert aoi.interpolated_rows == 0
    assert outcome.aligned_session.streams["I"].tables["aoi_instances"].height == 122
    fixations = outcome.report.stream_results["G"].artifacts["fixations"]
    assert isinstance(fixations, IntervalTemporalArtifactMetrics)
    assert fixations.total_rows == 4
    assert fixations.overlapping_session_rows == 4
    assert fixations.fully_in_session_rows == 3
    assert fixations.interpolated_rows == 0
    assert outcome.aligned_session.streams["G"].tables["fixations"].height == 4
    r_peaks = outcome.report.stream_results["ECG"].artifacts["r_peaks"]
    assert isinstance(r_peaks, PointTemporalArtifactMetrics)
    assert r_peaks.total_rows == 3
    assert r_peaks.in_session_rows == 3
    assert r_peaks.interpolated_rows == 0
    assert outcome.aligned_session.streams["ECG"].tables["r_peaks"].height == 3
    scene_gaze = outcome.report.stream_results["G"].scene_gaze_metrics
    assert scene_gaze is not None
    assert scene_gaze.evaluated_in_session_gaze_rows == 240
    assert scene_gaze.valid_association_rows == 240
    assert scene_gaze.invalid_association_count == 0

    assert outcome.report.source_classification == "synthetic-test-data"
    assert outcome.report.synthetic_provenance is not None
    assert outcome.report.synthetic_provenance.scientific_validation_status == "not_supported"
    assert outcome.report.synthetic_provenance.formal_assessment_supported is False
    assert outcome.report.annotation_result is not None
    assert outcome.report.annotation_result.synchronization_status is (
        SynchronizationItemStatus.ALIGNED
    )
    assert outcome.report.annotation_result.synthetic_semantics_unvalidated is True
    assert manifest.source_session.extensions["task_validity"] == "not_asserted"
    assert manifest.source_session.extensions["ground_truth_status"] == "absent"
    task_reference = manifest.streams["task_reference"]
    assert task_reference.metadata["reference_validity"] == "synthetic-format-fixture-only"
    assert task_reference.metadata["trajectory_standard_status"] == "not_asserted"

    assert source.read_bytes() == source_before
    assert (bundle / "streams" / "simulator.csv").read_bytes() == source_before
    assert _snapshot_files(bundle) == bundle_before
