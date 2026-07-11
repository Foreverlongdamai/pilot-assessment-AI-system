from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from PIL import Image

from pilot_assessment.contracts.session import StreamDescriptor
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError, AdapterRequest
from pilot_assessment.ingestion.adapters.composite import (
    COMPOSITE_KEYS,
    CompositeStreamAdapter,
)
from pilot_assessment.ingestion.parquet_io import write_profiled_parquet
from pilot_assessment.ingestion.profiles import (
    CompositeProfile,
    ExactPathsMatcher,
    JsonProfile,
    PathPrefixMatcher,
    PhysicalDType,
    TableProfile,
    load_builtin_profiles,
)

SCHEMA_TO_MODALITY = {
    "vr-scene-source-bundle-v0.1": "I",
    "gaze-source-bundle-v0.1": "G",
    "eeg-source-bundle-v0.1": "EEG",
    "ecg-source-bundle-v0.1": "ECG",
    "pilot-camera-source-bundle-v0.1": "pilot_camera",
}


def _profile(schema_id: str) -> CompositeProfile:
    profile = load_builtin_profiles()[schema_id]
    assert isinstance(profile, CompositeProfile)
    return profile


def _default_values(
    profile: TableProfile,
    *,
    role: str,
    image_paths: tuple[str, ...],
) -> dict[str, list[object]]:
    if profile.schema_id in {
        "vr-frame-index-raw-v0.1",
        "pilot-camera-frame-index-raw-v0.1",
        "vr-aoi-instance-raw-v0.1",
    }:
        count = 2
    elif profile.schema_id in {"gaze-fixation-raw-v0.1"}:
        count = 1
    elif profile.schema_id == "ecg-r-peak-raw-v0.1":
        count = 2
    else:
        count = 3

    rate = float(profile.expected_sample_rate_hz or 120.0)
    timestamps = [index / rate for index in range(count)]
    if profile.schema_id == "ecg-r-peak-raw-v0.1":
        timestamps = [0.0, 0.008]
    values: dict[str, list[object]] = {}
    for column in profile.columns:
        name = column.name
        if name == "image_path":
            values[name] = list(image_paths)
        elif name == "width":
            width = 48 if profile.schema_id.startswith("pilot-camera") else 64
            values[name] = [width] * count
        elif name == "height":
            height = 48 if profile.schema_id.startswith("pilot-camera") else 36
            values[name] = [height] * count
        elif name in {"source_timestamp_s", "start_source_timestamp_s"}:
            values[name] = cast(list[object], timestamps)
        elif name == "end_source_timestamp_s":
            values[name] = [timestamps[0] + (1.0 / 120.0)]
        elif name == "duration_ms":
            values[name] = [float(1000.0 / 120.0)]
        elif name == "frame_id" and role == "aoi_instances":
            values[name] = [0, 1]
        elif name == "scene_frame_id":
            values[name] = [0, 0, 1]
        elif name in {"first_scene_frame_id", "last_scene_frame_id"}:
            values[name] = [0]
        elif column.dtype in {PhysicalDType.U64, PhysicalDType.U32}:
            values[name] = list(range(count))
        elif column.dtype in {PhysicalDType.F64, PhysicalDType.F32}:
            if name == "head_qw":
                values[name] = [1.0] * count
            elif name.startswith("head_q"):
                values[name] = [0.0] * count
            else:
                values[name] = [0.5] * count
        elif column.dtype is PhysicalDType.BOOL:
            values[name] = [True] * count
        else:
            values[name] = [f"fixture-{index}" for index in range(count)]
    return values


def _table(
    profile: TableProfile,
    *,
    role: str,
    image_paths: tuple[str, ...] = (),
) -> pl.DataFrame:
    values = _default_values(profile, role=role, image_paths=image_paths)
    return pl.DataFrame(
        {
            column.name: pl.Series(
                column.name,
                values[column.name],
                dtype=column.dtype.to_polars(),
            )
            for column in profile.columns
        }
    )


def _artifact_role_metadata(profile: CompositeProfile) -> dict[str, object]:
    return {
        role: definition.model_dump(mode="json")
        for role, definition in profile.artifact_roles.items()
    }


def _eeg_sidecar(clock_id: str) -> dict[str, object]:
    channels = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4")
    return {
        "schema_id": "eeg-sidecar-v0.1",
        "montage_id": "synthetic-10-20-eight-channel-v0.1",
        "reference": "synthetic-average-reference-v0.1",
        "channel_order": list(channels),
        "channel_units": {channel: "uV" for channel in channels},
        "sample_rate_hz": 256.0,
        "clock_id": clock_id,
        "generator_id": "synthetic-multimodal-generator-v0.1",
        "seed": 20_260_711,
        "synthetic_not_neurophysiological": True,
    }


def _build_request(
    root: Path,
    schema_id: str,
    *,
    mutate_tables: Callable[[dict[str, pl.DataFrame]], None] | None = None,
    mutate_sidecar: Callable[[dict[str, object]], None] | None = None,
) -> AdapterRequest:
    composite = _profile(schema_id)
    catalog = load_builtin_profiles()
    clock_id = f"{SCHEMA_TO_MODALITY[schema_id].lower()}-clock"
    role_paths: dict[str, tuple[str, ...]] = {}
    tables: dict[str, pl.DataFrame] = {}
    sidecars: dict[str, dict[str, object]] = {}

    for role, definition in composite.artifact_roles.items():
        matcher = definition.matcher
        artifact_profile = catalog[definition.schema_id]
        if isinstance(matcher, ExactPathsMatcher):
            role_paths[role] = matcher.paths
        else:
            assert isinstance(matcher, PathPrefixMatcher)
            role_paths[role] = (
                f"{matcher.path_prefix}frame_000000.png",
                f"{matcher.path_prefix}frame_000001.png",
            )

        if isinstance(artifact_profile, TableProfile):
            image_paths = next(
                (paths for image_role, paths in role_paths.items() if image_role == "frame_images"),
                (),
            )
            if role == "frame_index" and not image_paths:
                image_role = composite.artifact_roles.get("frame_images")
                assert image_role is not None
                image_matcher = image_role.matcher
                assert isinstance(image_matcher, PathPrefixMatcher)
                image_paths = (
                    f"{image_matcher.path_prefix}frame_000000.png",
                    f"{image_matcher.path_prefix}frame_000001.png",
                )
            tables[role] = _table(
                artifact_profile,
                role=role,
                image_paths=image_paths,
            )
        elif isinstance(artifact_profile, JsonProfile):
            sidecars[role] = _eeg_sidecar(clock_id)

    if mutate_tables is not None:
        mutate_tables(tables)
    if mutate_sidecar is not None:
        for sidecar in sidecars.values():
            mutate_sidecar(sidecar)

    all_paths: list[str] = []
    for role, definition in composite.artifact_roles.items():
        paths = role_paths[role]
        all_paths.extend(paths)
        artifact_profile = catalog[definition.schema_id]
        if isinstance(artifact_profile, TableProfile):
            assert len(paths) == 1
            target = root.joinpath(*paths[0].split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            write_profiled_parquet(
                tables[role],
                target,
                schema_id=artifact_profile.schema_id,
            )
        elif isinstance(artifact_profile, JsonProfile):
            assert len(paths) == 1
            target = root.joinpath(*paths[0].split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(sidecars[role], sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
        else:
            for path in paths:
                target = root.joinpath(*path.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                size = (48, 48) if SCHEMA_TO_MODALITY[schema_id] == "pilot_camera" else (64, 36)
                Image.new("RGB", size, color=(12, 34, 56)).save(
                    target,
                    format="PNG",
                    compress_level=9,
                    optimize=False,
                )

    checksums = {
        path: hashlib.sha256(root.joinpath(*path.split("/")).read_bytes()).hexdigest()
        for path in all_paths
    }
    modality = SCHEMA_TO_MODALITY[schema_id]
    primary_definition = composite.artifact_roles[composite.primary_role]
    primary_profile = catalog[primary_definition.schema_id]
    assert isinstance(primary_profile, TableProfile)
    descriptor = StreamDescriptor(
        modality=modality,
        status="present",
        required_for_import=True,
        paths=all_paths,
        format=composite.format,
        schema_id=schema_id,
        clock_id=clock_id,
        clock_sync={
            "method": "synthetic-declared-truth-v0.1",
            "scale": 1.0,
            "offset_ns": 0,
            "drift_ppm": 0.0,
            "residual_rms_ms": 0.0,
            "residual_max_ms": 0.0,
        },
        sample_rate_hz=primary_profile.expected_sample_rate_hz,
        units="profile",
        quality_summary=None,
        checksums=checksums,
        metadata={
            "artifact_roles": _artifact_role_metadata(composite),
            "generator_id": "synthetic-multimodal-generator-v0.1",
            "seed": 20_260_711,
        },
    )
    return AdapterRequest(
        bundle_root=root,
        descriptors={modality: descriptor},
        source_paths=tuple(all_paths),
        verified_digests=checksums,
        profile=composite,
    )


@pytest.mark.parametrize("schema_id", tuple(SCHEMA_TO_MODALITY))
def test_trusted_composite_adapter_routes_every_approved_modality(
    tmp_path: Path,
    schema_id: str,
) -> None:
    request = _build_request(tmp_path, schema_id)

    result = CompositeStreamAdapter().inspect(request)

    modality = SCHEMA_TO_MODALITY[schema_id]
    stream = result.streams[modality]
    profile = _profile(schema_id)
    assert stream.primary_table_role == profile.primary_role
    assert set(stream.tables) == {
        role
        for role, definition in profile.artifact_roles.items()
        if definition.media_type == "application/vnd.apache.parquet"
    }
    assert set(stream.json_artifacts) == {
        role
        for role, definition in profile.artifact_roles.items()
        if definition.media_type == "application/json"
    }
    assert set(stream.file_artifacts) == {
        role
        for role, definition in profile.artifact_roles.items()
        if definition.media_type == "image/png"
    }
    assert {summary.role for summary in result.artifact_summaries} == set(profile.artifact_roles)
    assert not result.context
    assert not result.issues


def test_composite_adapter_registers_only_the_five_approved_exact_keys() -> None:
    assert (
        CompositeStreamAdapter.keys
        == COMPOSITE_KEYS
        == frozenset(
            {
                ("image_sequence+parquet_index", "vr-scene-source-bundle-v0.1"),
                ("parquet", "gaze-source-bundle-v0.1"),
                ("parquet+json_sidecar", "eeg-source-bundle-v0.1"),
                ("parquet", "ecg-source-bundle-v0.1"),
                ("image_sequence+parquet_index", "pilot-camera-source-bundle-v0.1"),
            }
        )
    )


def _replace_inventory(
    request: AdapterRequest,
    paths: tuple[str, ...],
    *,
    metadata: dict[str, object] | None = None,
    profile: CompositeProfile | None = None,
) -> AdapterRequest:
    descriptor = next(iter(request.descriptors.values()))
    digests = {path: request.verified_digests.get(path, "0" * 64) for path in paths}
    replaced = descriptor.model_copy(
        update={
            "paths": list(paths),
            "checksums": digests,
            "metadata": metadata if metadata is not None else descriptor.metadata,
        }
    )
    return AdapterRequest(
        bundle_root=request.bundle_root,
        descriptors={replaced.modality: replaced},
        source_paths=paths,
        verified_digests=digests,
        profile=profile or request.profile,
    )


def test_declared_roles_must_exactly_match_registry_and_required_roles(tmp_path: Path) -> None:
    request = _build_request(tmp_path, "gaze-source-bundle-v0.1")
    profile = _profile("gaze-source-bundle-v0.1")
    metadata = _artifact_role_metadata(profile)
    metadata.pop("fixations")
    with pytest.raises(AdapterInspectionError) as metadata_error:
        CompositeStreamAdapter().inspect(
            _replace_inventory(request, request.source_paths, metadata={"artifact_roles": metadata})
        )
    assert metadata_error.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"

    without_fixations = tuple(
        path for path in request.source_paths if not path.endswith("fixations.parquet")
    )
    with pytest.raises(AdapterInspectionError) as missing_role:
        CompositeStreamAdapter().inspect(_replace_inventory(request, without_fixations))
    assert missing_role.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_paths_are_routed_only_by_exact_or_prefix_matchers(tmp_path: Path) -> None:
    request = _build_request(tmp_path, "gaze-source-bundle-v0.1")
    renamed = tuple(
        "streams/gaze/looks-like-gaze_samples.parquet"
        if path.endswith("gaze_samples.parquet")
        else path
        for path in request.source_paths
    )
    with pytest.raises(AdapterInspectionError) as no_filename_guessing:
        CompositeStreamAdapter().inspect(_replace_inventory(request, renamed))
    assert no_filename_guessing.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"

    profile = _profile("gaze-source-bundle-v0.1")
    shadow_definition = profile.artifact_roles["gaze_samples"].model_copy(
        update={
            "matcher": PathPrefixMatcher(
                kind="path_prefix",
                path_prefix="streams/gaze/",
            ),
            "required": False,
        }
    )
    overlapping = profile.model_copy(
        update={"artifact_roles": {**profile.artifact_roles, "shadow": shadow_definition}}
    )
    overlap_metadata: dict[str, object] = {
        "artifact_roles": _artifact_role_metadata(overlapping),
    }
    with pytest.raises(AdapterInspectionError) as multiple_roles:
        CompositeStreamAdapter().inspect(
            _replace_inventory(
                request,
                request.source_paths,
                metadata=overlap_metadata,
                profile=overlapping,
            )
        )
    assert multiple_roles.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_scene_aoi_frame_ids_must_exist_in_frame_index(tmp_path: Path) -> None:
    def orphan_aoi(tables: dict[str, pl.DataFrame]) -> None:
        tables["aoi_instances"] = tables["aoi_instances"].with_columns(
            pl.Series("frame_id", [0, 99], dtype=pl.UInt64)
        )

    request = _build_request(
        tmp_path,
        "vr-scene-source-bundle-v0.1",
        mutate_tables=orphan_aoi,
    )
    with pytest.raises(AdapterInspectionError) as caught:
        CompositeStreamAdapter().inspect(request)
    assert caught.value.issue.error_code == "STREAM_RELATIONSHIP_INVALID"


def test_gaze_fixation_time_and_frame_ranges_are_consistent(tmp_path: Path) -> None:
    def invalid_fixation(tables: dict[str, pl.DataFrame]) -> None:
        tables["fixations"] = tables["fixations"].with_columns(
            pl.lit(10.0).cast(pl.Float64).alias("end_source_timestamp_s"),
            pl.lit(2).cast(pl.UInt64).alias("first_scene_frame_id"),
            pl.lit(1).cast(pl.UInt64).alias("last_scene_frame_id"),
        )

    request = _build_request(
        tmp_path,
        "gaze-source-bundle-v0.1",
        mutate_tables=invalid_fixation,
    )
    with pytest.raises(AdapterInspectionError) as caught:
        CompositeStreamAdapter().inspect(request)
    assert caught.value.issue.error_code == "STREAM_RELATIONSHIP_INVALID"


def test_eeg_sidecar_channels_units_rate_and_clock_match_samples(tmp_path: Path) -> None:
    def wrong_channel(sidecar: dict[str, object]) -> None:
        channel_order = cast(list[object], sidecar["channel_order"])
        assert isinstance(channel_order, list)
        channel_order[-1] = "Oz"

    request = _build_request(
        tmp_path,
        "eeg-source-bundle-v0.1",
        mutate_sidecar=wrong_channel,
    )
    with pytest.raises(AdapterInspectionError) as caught:
        CompositeStreamAdapter().inspect(request)
    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_ecg_peaks_must_stay_inside_sample_time_range(tmp_path: Path) -> None:
    def out_of_range_peak(tables: dict[str, pl.DataFrame]) -> None:
        tables["r_peaks"] = tables["r_peaks"].with_columns(
            pl.Series("source_timestamp_s", [0.0, 10.0], dtype=pl.Float64)
        )

    request = _build_request(
        tmp_path,
        "ecg-source-bundle-v0.1",
        mutate_tables=out_of_range_peak,
    )
    with pytest.raises(AdapterInspectionError) as caught:
        CompositeStreamAdapter().inspect(request)
    assert caught.value.issue.error_code == "STREAM_RELATIONSHIP_INVALID"


def test_camera_frame_index_must_reference_exactly_the_declared_pngs(tmp_path: Path) -> None:
    def undeclared_frame(tables: dict[str, pl.DataFrame]) -> None:
        tables["frame_index"] = tables["frame_index"].with_columns(
            pl.Series(
                "image_path",
                [
                    "streams/pilot_camera/frames/frame_000000.png",
                    "streams/pilot_camera/frames/not_declared.png",
                ],
                dtype=pl.String,
            )
        )

    request = _build_request(
        tmp_path,
        "pilot-camera-source-bundle-v0.1",
        mutate_tables=undeclared_frame,
    )
    with pytest.raises(AdapterInspectionError) as caught:
        CompositeStreamAdapter().inspect(request)
    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"
