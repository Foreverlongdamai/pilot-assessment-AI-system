from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

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

FORMAT_SAMPLE_CSV_ENV = "PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV"
EXPECTED_FORMAT_SAMPLE_CSV_SHA256 = (
    "19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52"
)


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


@pytest.mark.skipif(
    not os.environ.get(FORMAT_SAMPLE_CSV_ENV),
    reason="repository-external captured format-sample simulator CSV not configured",
)
def test_format_sample_runs_through_m3_without_mutating_raw_artifacts(
    tmp_path: Path,
) -> None:
    source = Path(os.environ[FORMAT_SAMPLE_CSV_ENV])
    source_before = source.read_bytes()
    assert hashlib.sha256(source_before).hexdigest() == EXPECTED_FORMAT_SAMPLE_CSV_SHA256
    bundle = generate_synthetic_bundle(source, tmp_path / "bundle", seed=20260711)
    bundle_before = _snapshot_files(bundle)
    manifest = ManifestLoader().load(bundle).manifest

    outcome = synchronize_bundle(bundle)

    assert outcome.report.session_window == SessionWindow(
        start_t_ns=0,
        end_t_ns=29_010_000_000,
        source="master-clock-x-mapped-coverage-v1",
    )
    assert outcome.report.validation_scope == "native_rate_session_time_alignment_v1"
    assert outcome.report.disposition is SynchronizationDisposition.READY
    assert outcome.report.can_continue_to_anchor_availability is True
    assert outcome.report.formal_run_authorized is False
    assert outcome.aligned_session is not None
    assert outcome.report.synchronization_fingerprint == (
        outcome.aligned_session.synchronization_fingerprint
    )

    primary_roles = {
        "X": ("samples", 2_902, 2_902),
        "U": ("samples", 2_902, 2_902),
        "I": ("frame_index", 871, 871),
        "G": ("gaze_samples", 3_482, 3_481),
        "EEG": ("samples", 7_427, 7_423),
        "ECG": ("samples", 7_253, 7_251),
        "pilot_camera": ("frame_index", 436, 435),
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
    assert reference_metrics.total_rows == 2_902
    assert reference_metrics.in_session_rows == 2_902
    assert reference_metrics.interpolated_rows == 0
    assert outcome.aligned_session.task_reference is not None
    assert outcome.aligned_session.task_reference.tables["commanded_path"].height == 2_902

    aoi = outcome.report.stream_results["I"].artifacts["aoi_instances"]
    assert isinstance(aoi, PointTemporalArtifactMetrics)
    assert aoi.total_rows == 1_742
    assert aoi.in_session_rows == 1_742
    assert aoi.interpolated_rows == 0
    assert outcome.aligned_session.streams["I"].tables["aoi_instances"].height == 1_742
    fixations = outcome.report.stream_results["G"].artifacts["fixations"]
    assert isinstance(fixations, IntervalTemporalArtifactMetrics)
    assert fixations.total_rows == 59
    assert fixations.overlapping_session_rows == 59
    assert fixations.fully_in_session_rows == 58
    assert fixations.interpolated_rows == 0
    assert outcome.aligned_session.streams["G"].tables["fixations"].height == 59
    r_peaks = outcome.report.stream_results["ECG"].artifacts["r_peaks"]
    assert isinstance(r_peaks, PointTemporalArtifactMetrics)
    assert r_peaks.total_rows == 37
    assert r_peaks.in_session_rows == 37
    assert r_peaks.interpolated_rows == 0
    assert outcome.aligned_session.streams["ECG"].tables["r_peaks"].height == 37
    scene_gaze = outcome.report.stream_results["G"].scene_gaze_metrics
    assert scene_gaze is not None
    assert scene_gaze.evaluated_in_session_gaze_rows == 3_481
    assert scene_gaze.valid_association_rows == 3_481
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
    assert manifest.source_session.extensions["source_artifact_role"] == (
        "captured-format-sample-xu"
    )
    assert manifest.source_session.extensions["task_validity"] == "not_asserted"
    assert manifest.source_session.extensions["ground_truth_status"] == "absent"
    task_reference = manifest.streams["task_reference"]
    assert task_reference.metadata["reference_validity"] == "synthetic-format-fixture-only"
    assert task_reference.metadata["trajectory_standard_status"] == "not_asserted"

    assert source.read_bytes() == source_before
    assert (bundle / "streams" / "simulator.csv").read_bytes() == source_before
    assert _snapshot_files(bundle) == bundle_before
