from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

import polars as pl
import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.session import StreamDescriptor, StreamStatus
from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
)
from pilot_assessment.ingestion.adapters.registry import (
    AdapterNotFoundError,
    AdapterRegistry,
    DuplicateAdapterRegistrationError,
)
from pilot_assessment.ingestion.models import NormalizedStream, PreparedSession
from pilot_assessment.ingestion.profiles import (
    CompositeProfile,
    CsvProfile,
    ExactPathsMatcher,
    ImageProfile,
    PathPrefixMatcher,
    ProfileCatalog,
    TableProfile,
    load_builtin_profiles,
)

EXPECTED_TABLE_COLUMNS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "vr-frame-index-raw-v0.1": (
        ("frame_id", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("image_path", "utf8", False),
        ("width", "u32", False),
        ("height", "u32", False),
        ("head_x_m", "f32", False),
        ("head_y_m", "f32", False),
        ("head_z_m", "f32", False),
        ("head_qx", "f32", False),
        ("head_qy", "f32", False),
        ("head_qz", "f32", False),
        ("head_qw", "f32", False),
        ("horizontal_fov_deg", "f32", False),
        ("vertical_fov_deg", "f32", False),
        ("phase_id", "utf8", False),
        ("frame_valid", "bool", False),
        ("generator_version", "utf8", False),
    ),
    "vr-aoi-instance-raw-v0.1": (
        ("frame_id", "u64", False),
        ("aoi_id", "utf8", False),
        ("taxonomy_version", "utf8", False),
        ("bbox_x_norm", "f32", False),
        ("bbox_y_norm", "f32", False),
        ("bbox_w_norm", "f32", False),
        ("bbox_h_norm", "f32", False),
        ("visible", "bool", False),
        ("confidence", "f32", False),
    ),
    "gaze-sample-raw-v0.1": (
        ("gaze_sample_id", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("scene_frame_id", "u64", False),
        ("viewport_x_norm", "f32", True),
        ("viewport_y_norm", "f32", True),
        ("origin_x_m", "f32", True),
        ("origin_y_m", "f32", True),
        ("origin_z_m", "f32", True),
        ("ray_x", "f32", True),
        ("ray_y", "f32", True),
        ("ray_z", "f32", True),
        ("left_pupil_mm", "f32", True),
        ("right_pupil_mm", "f32", True),
        ("binocular_valid", "bool", False),
        ("confidence", "f32", False),
        ("blink", "bool", False),
        ("assigned_aoi_id", "utf8", True),
        ("assignment_confidence", "f32", True),
    ),
    "gaze-fixation-raw-v0.1": (
        ("fixation_id", "u64", False),
        ("start_source_timestamp_s", "f64", False),
        ("end_source_timestamp_s", "f64", False),
        ("duration_ms", "f32", False),
        ("centroid_x_norm", "f32", False),
        ("centroid_y_norm", "f32", False),
        ("ray_x", "f32", False),
        ("ray_y", "f32", False),
        ("ray_z", "f32", False),
        ("first_scene_frame_id", "u64", False),
        ("last_scene_frame_id", "u64", False),
        ("aoi_id", "utf8", True),
        ("fixation_valid", "bool", False),
        ("confidence", "f32", False),
        ("detector_version", "utf8", False),
    ),
    "eeg-sample-raw-v0.1": (
        ("sample_index", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("Fp1_uV", "f32", True),
        ("Fp2_uV", "f32", True),
        ("F3_uV", "f32", True),
        ("F4_uV", "f32", True),
        ("C3_uV", "f32", True),
        ("C4_uV", "f32", True),
        ("P3_uV", "f32", True),
        ("P4_uV", "f32", True),
        ("signal_valid", "bool", False),
        ("artifact_code", "utf8", True),
    ),
    "ecg-sample-raw-v0.1": (
        ("sample_index", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("synthetic_lead_ii_mV", "f32", True),
        ("signal_valid", "bool", False),
        ("artifact_code", "utf8", True),
    ),
    "ecg-r-peak-raw-v0.1": (
        ("peak_id", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("rr_interval_ms", "f32", True),
        ("detection_confidence", "f32", False),
        ("generator_version", "utf8", False),
    ),
    "pilot-camera-frame-index-raw-v0.1": (
        ("frame_id", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("image_path", "utf8", False),
        ("width", "u32", False),
        ("height", "u32", False),
        ("head_bbox_x_norm", "f32", False),
        ("head_bbox_y_norm", "f32", False),
        ("head_bbox_w_norm", "f32", False),
        ("head_bbox_h_norm", "f32", False),
        ("left_eye_bbox_x_norm", "f32", False),
        ("left_eye_bbox_y_norm", "f32", False),
        ("left_eye_bbox_w_norm", "f32", False),
        ("left_eye_bbox_h_norm", "f32", False),
        ("right_eye_bbox_x_norm", "f32", False),
        ("right_eye_bbox_y_norm", "f32", False),
        ("right_eye_bbox_w_norm", "f32", False),
        ("right_eye_bbox_h_norm", "f32", False),
        ("frame_valid", "bool", False),
        ("privacy_class", "utf8", False),
        ("generator_version", "utf8", False),
    ),
    "task-reference-path-raw-v0.1": (
        ("reference_sample_id", "u64", False),
        ("source_timestamp_s", "f64", False),
        ("target_x_m", "f32", False),
        ("target_y_m", "f32", False),
        ("target_z_m", "f32", False),
        ("target_vx_m_s", "f32", False),
        ("target_vy_m_s", "f32", False),
        ("target_vz_m_s", "f32", False),
        ("target_roll_deg", "f32", False),
        ("target_pitch_deg", "f32", False),
        ("target_yaw_deg", "f32", False),
        ("envelope_profile_id", "utf8", False),
    ),
}


def _descriptor() -> StreamDescriptor:
    return StreamDescriptor(
        modality="X",
        status=StreamStatus.PRESENT,
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
        checksums={"streams/simulator.csv": "a" * 64},
        metadata={"shared_source_id": "simulator-main", "view_id": "X"},
    )


def _issue() -> DomainErrorData:
    return DomainErrorData(
        error_code="STREAM_SCHEMA_MISMATCH",
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message="fixture mismatch",
        remediation="repair fixture",
    )


def test_builtin_catalog_covers_all_approved_artifact_and_composite_schemas() -> None:
    catalog = load_builtin_profiles()
    expected = {
        "cranfield-simulator-combined-csv-raw-v0.1",
        *EXPECTED_TABLE_COLUMNS,
        "png-rgb8-v0.1",
        "eeg-sidecar-v0.1",
        "vr-scene-source-bundle-v0.1",
        "gaze-source-bundle-v0.1",
        "eeg-source-bundle-v0.1",
        "ecg-source-bundle-v0.1",
        "pilot-camera-source-bundle-v0.1",
    }
    assert set(catalog) == expected


def test_all_table_profiles_freeze_order_dtype_and_nullability() -> None:
    catalog = load_builtin_profiles()
    for schema_id, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        profile = catalog[schema_id]
        assert isinstance(profile, TableProfile)
        actual = tuple(
            (column.name, column.dtype.value, column.nullable) for column in profile.columns
        )
        assert actual == expected_columns
        assert profile.allow_extra_columns is False


def test_csv_profile_freezes_all_headers_views_context_and_quality_checks() -> None:
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    assert isinstance(profile, CsvProfile)
    assert len(profile.columns) == 33
    assert profile.header_normalization == "trim_outer_ascii_whitespace_v1"
    assert profile.source_timestamp_column == "source_time_s"
    assert profile.expected_sample_rate_hz == 100.0
    assert profile.sample_rate_tolerance_fraction == 0.01
    mapping = {
        column.source_header: (column.canonical_name, column.role.value)
        for column in profile.columns
    }
    assert mapping["Pilot Lon"] == ("control.longitudinal_raw", "U")
    assert mapping["Time Delay s"] == ("context.time_delay_s", "context")
    assert mapping["V_ex kts"] == ("quality.velocity.earth.x_kt", "quality_check")
    assert profile.context_columns == (
        "context.control_mode_raw",
        "context.time_delay_s",
        "context.longitudinal_frequency_rad_s",
        "context.longitudinal_damping_ratio",
    )
    assert len(profile.unit_consistency_checks) == 3
    assert profile.unit_consistency_checks[0].warning_tolerance == 0.002
    assert profile.unit_consistency_checks[0].invalid_tolerance == 0.02


def test_composite_profiles_freeze_exact_roles_and_matchers() -> None:
    catalog = load_builtin_profiles()
    scene = catalog["vr-scene-source-bundle-v0.1"]
    assert isinstance(scene, CompositeProfile)
    assert scene.primary_role == "frame_index"
    assert set(scene.artifact_roles) == {"frame_index", "aoi_instances", "frame_images"}
    assert isinstance(scene.artifact_roles["frame_index"].matcher, ExactPathsMatcher)
    assert scene.artifact_roles["frame_index"].matcher.paths == (
        "streams/vr_scene/frame_index.parquet",
    )
    assert isinstance(scene.artifact_roles["frame_images"].matcher, PathPrefixMatcher)
    assert scene.artifact_roles["frame_images"].matcher.path_prefix == ("streams/vr_scene/frames/")

    expected_roles = {
        "gaze-source-bundle-v0.1": {"gaze_samples", "fixations"},
        "eeg-source-bundle-v0.1": {"samples", "sidecar"},
        "ecg-source-bundle-v0.1": {"samples", "r_peaks"},
        "pilot-camera-source-bundle-v0.1": {"frame_index", "frame_images"},
    }
    for schema_id, roles in expected_roles.items():
        profile = catalog[schema_id]
        assert isinstance(profile, CompositeProfile)
        assert set(profile.artifact_roles) == roles


def test_image_profile_freezes_synthetic_sizes_and_generic_safety_ceiling() -> None:
    profile = load_builtin_profiles()["png-rgb8-v0.1"]
    assert isinstance(profile, ImageProfile)
    assert tuple((item.width, item.height) for item in profile.allowed_dimensions) == (
        (64, 36),
        (48, 48),
    )
    assert profile.max_pixels == 16_000_000


def test_catalog_rejects_duplicate_schema_ids() -> None:
    valid = load_builtin_profiles()["vr-frame-index-raw-v0.1"].model_dump(mode="json")
    with pytest.raises(ValidationError, match="schema IDs must be unique"):
        ProfileCatalog.model_validate({"catalog_version": "0.1.0", "profiles": [valid, valid]})


def test_normalized_stream_retains_multiple_artifact_kinds_without_pixels() -> None:
    samples = pl.DataFrame({"sample_index": [0], "source_timestamp_s": [0.0]})
    peaks = pl.DataFrame({"peak_id": [0], "source_timestamp_s": [0.0]})
    stream = NormalizedStream(
        modality="ECG",
        schema_id="ecg-source-bundle-v0.1",
        clock_id="ecg_clock",
        source_timestamp_column="source_timestamp_s",
        primary_table_role="samples",
        tables={"samples": samples, "r_peaks": peaks},
        json_artifacts={"sidecar": {"schema_id": "fixture-v0.1"}},
        file_artifacts={"frame_images": ("streams/images/000000.png",)},
        source_paths=("streams/ecg/samples.parquet",),
        source_checksums={"streams/ecg/samples.parquet": "b" * 64},
    )
    assert stream.primary_table is samples
    assert stream.tables["r_peaks"] is peaks
    assert stream.json_artifacts["sidecar"]["schema_id"] == "fixture-v0.1"
    assert stream.file_artifacts["frame_images"] == ("streams/images/000000.png",)
    with pytest.raises(TypeError):
        cast(dict[str, pl.DataFrame], stream.tables)["another"] = samples


def test_prepared_session_and_adapter_boundary_preserve_typed_artifacts(tmp_path: Path) -> None:
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    descriptor = _descriptor()
    request = AdapterRequest(
        bundle_root=tmp_path,
        descriptors={"X": descriptor},
        source_paths=("streams/simulator.csv",),
        verified_digests={"streams/simulator.csv": "a" * 64},
        profile=profile,
    )
    frame = pl.DataFrame(
        {"source_row_index": pl.Series([0], dtype=pl.UInt64), "source_time_s": [0.0]}
    )
    stream = NormalizedStream(
        modality="X",
        schema_id="cranfield-simulator-combined-csv-raw-v0.1",
        clock_id="sim_clock",
        source_timestamp_column="source_time_s",
        primary_table_role="samples",
        tables={"samples": frame},
        json_artifacts={},
        file_artifacts={},
        source_paths=request.source_paths,
        source_checksums=request.verified_digests,
    )
    result = AdapterResult(
        streams={"X": stream},
        context={"context.time_delay_s": 0.2},
        artifact_summaries=(
            AdapterArtifactSummary(
                role="samples", paths=request.source_paths, row_count=frame.height
            ),
        ),
    )
    prepared = PreparedSession(
        streams=result.streams,
        context=result.context,
        task_reference=None,
    )
    assert request.descriptors["X"] is descriptor
    assert prepared.streams["X"].primary_table.schema["source_row_index"] == pl.UInt64
    assert prepared.context["context.time_delay_s"] == 0.2


def test_adapter_inspection_error_keeps_structured_issue() -> None:
    issue = _issue()
    error = AdapterInspectionError(issue)
    assert str(error) == issue.message
    assert error.issue is issue


class FakeAdapter:
    adapter_id: ClassVar[str] = "fixture-adapter"
    adapter_version: ClassVar[str] = "0.1.0"
    keys: ClassVar[frozenset[tuple[str, str]]] = frozenset({("csv", "fixture-v0.1")})

    def inspect(self, request: AdapterRequest) -> AdapterResult:
        raise AdapterInspectionError(_issue())


def test_registry_resolves_only_exact_trusted_keys() -> None:
    registry = AdapterRegistry()
    adapter = FakeAdapter()
    registry.register(adapter)
    assert registry.resolve("csv", "fixture-v0.1") is adapter
    with pytest.raises(AdapterNotFoundError):
        registry.resolve("CSV", "fixture-v0.1")
    with pytest.raises(AdapterNotFoundError):
        registry.resolve("csv", "unregistered-v0.1")
    with pytest.raises(DuplicateAdapterRegistrationError):
        registry.register(FakeAdapter())


def test_packaged_profile_resource_is_a_real_file() -> None:
    from importlib.resources import as_file, files

    resource = files("pilot_assessment.ingestion.profile_data").joinpath("m2-profiles-0.1.json")
    with as_file(resource) as path:
        assert Path(path).is_file()
