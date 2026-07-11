"""Trusted, profile-routed validation for M2 composite modality sources."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.session import StreamDescriptor
from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
)
from pilot_assessment.ingestion.adapters.image_sequence import inspect_image_sequence
from pilot_assessment.ingestion.adapters.parquet_table import (
    inspect_eeg_sidecar,
    inspect_parquet_table,
)
from pilot_assessment.ingestion.models import NormalizedStream
from pilot_assessment.ingestion.profiles import (
    ArtifactRoleProfile,
    CompositeProfile,
    ExactPathsMatcher,
    ImageProfile,
    JsonProfile,
    PathPrefixMatcher,
    TableProfile,
    load_builtin_profiles,
)

COMPOSITE_KEYS = frozenset(
    {
        ("image_sequence+parquet_index", "vr-scene-source-bundle-v0.1"),
        ("parquet", "gaze-source-bundle-v0.1"),
        ("parquet+json_sidecar", "eeg-source-bundle-v0.1"),
        ("parquet", "ecg-source-bundle-v0.1"),
        ("image_sequence+parquet_index", "pilot-camera-source-bundle-v0.1"),
    }
)

_SCHEMA_MODALITIES = {
    "vr-scene-source-bundle-v0.1": "I",
    "gaze-source-bundle-v0.1": "G",
    "eeg-source-bundle-v0.1": "EEG",
    "ecg-source-bundle-v0.1": "ECG",
    "pilot-camera-source-bundle-v0.1": "pilot_camera",
}


class CompositeStreamAdapter:
    """Inspect one trusted composite descriptor without guessing artifact roles."""

    adapter_id = "composite-stream"
    adapter_version = "0.1.0"
    keys = COMPOSITE_KEYS

    def inspect(self, request: AdapterRequest) -> AdapterResult:
        profile = request.profile
        if not isinstance(profile, CompositeProfile):
            _fail(
                "ADAPTER_CONFIG_INVALID",
                "Composite adapter requires a CompositeProfile",
                remediation="Resolve the descriptor schema to its packaged composite profile.",
            )
        descriptor = _validate_request(request, profile)
        role_paths = _route_roles(request.source_paths, descriptor, profile)

        resolved_paths = {
            relative_path: _safe_source_path(request.bundle_root, relative_path)
            for relative_path in request.source_paths
        }
        _verify_snapshot(resolved_paths, request.verified_digests)

        catalog = load_builtin_profiles()
        tables: dict[str, pl.DataFrame] = {}
        json_artifacts: dict[str, Mapping[str, JsonValue]] = {}
        file_artifacts: dict[str, tuple[str, ...]] = {}
        summaries: list[AdapterArtifactSummary] = []

        for role, definition in profile.artifact_roles.items():
            artifact_profile = catalog.get(definition.schema_id)
            paths = role_paths[role]
            if isinstance(artifact_profile, TableProfile):
                if len(paths) != 1:
                    _adapter_config_failure(
                        profile,
                        role,
                        "table roles must resolve to exactly one physical path",
                    )
                table = inspect_parquet_table(resolved_paths[paths[0]], artifact_profile)
                tables[role] = table
                summaries.append(
                    AdapterArtifactSummary(role=role, paths=paths, row_count=table.height)
                )

        for role, definition in profile.artifact_roles.items():
            artifact_profile = catalog.get(definition.schema_id)
            paths = role_paths[role]
            if isinstance(artifact_profile, JsonProfile):
                if profile.schema_id != "eeg-source-bundle-v0.1" or len(paths) != 1:
                    _adapter_config_failure(
                        profile,
                        role,
                        "v0.1 supports only one strict EEG JSON sidecar role",
                    )
                samples = tables.get("samples")
                if samples is None:
                    _adapter_config_failure(
                        profile,
                        role,
                        "EEG sidecar validation requires the samples table role",
                    )
                generator_id, seed = _synthetic_provenance(descriptor)
                channel_order = tuple(
                    name.removesuffix("_uV") for name in samples.columns if name.endswith("_uV")
                )
                payload = inspect_eeg_sidecar(
                    resolved_paths[paths[0]],
                    artifact_profile,
                    expected_clock_id=descriptor.clock_id,
                    expected_channel_order=channel_order,
                    expected_channel_units={channel: "uV" for channel in channel_order},
                    expected_sample_rate_hz=cast(float, descriptor.sample_rate_hz),
                    expected_generator_id=generator_id,
                    expected_seed=seed,
                )
                json_artifacts[role] = payload
                summaries.append(AdapterArtifactSummary(role=role, paths=paths, row_count=None))

        for role, definition in profile.artifact_roles.items():
            artifact_profile = catalog.get(definition.schema_id)
            paths = role_paths[role]
            if isinstance(artifact_profile, ImageProfile):
                index = tables.get("frame_index")
                if index is None:
                    _adapter_config_failure(
                        profile,
                        role,
                        "image roles require a validated frame_index table",
                    )
                inspected = inspect_image_sequence(
                    bundle_root=request.bundle_root,
                    frame_index=index,
                    declared_paths=paths,
                    profile=artifact_profile,
                )
                file_artifacts[role] = inspected
                summaries.append(AdapterArtifactSummary(role=role, paths=paths, row_count=None))

        _validate_cross_file_relationships(profile.schema_id, tables)
        _verify_snapshot(resolved_paths, request.verified_digests)

        primary_definition = profile.artifact_roles[profile.primary_role]
        primary_profile = catalog.get(primary_definition.schema_id)
        if not isinstance(primary_profile, TableProfile):
            _adapter_config_failure(
                profile,
                profile.primary_role,
                "composite primary role must resolve to a table profile",
            )
        timestamp_column = primary_profile.source_timestamp_column
        if timestamp_column is None:
            _adapter_config_failure(
                profile,
                profile.primary_role,
                "composite primary table requires a source timestamp column",
            )

        stream = NormalizedStream(
            modality=descriptor.modality,
            schema_id=profile.schema_id,
            clock_id=descriptor.clock_id,
            source_timestamp_column=timestamp_column,
            primary_table_role=profile.primary_role,
            tables=tables,
            json_artifacts=json_artifacts,
            file_artifacts=file_artifacts,
            source_paths=request.source_paths,
            source_checksums=request.verified_digests,
        )
        return AdapterResult(
            streams={descriptor.modality: stream},
            context={},
            artifact_summaries=tuple(summaries),
            issues=(),
        )


def _validate_request(
    request: AdapterRequest,
    profile: CompositeProfile,
) -> StreamDescriptor:
    if len(request.descriptors) != 1:
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "A composite adapter request must contain exactly one logical descriptor",
            remediation="Dispatch each composite modality as its own verified source group.",
        )
    descriptor = next(iter(request.descriptors.values()))
    expected_modality = _SCHEMA_MODALITIES.get(profile.schema_id)
    if (
        (descriptor.format, descriptor.schema_id) not in COMPOSITE_KEYS
        or descriptor.format != profile.format
        or descriptor.schema_id != profile.schema_id
        or descriptor.modality != expected_modality
    ):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Composite descriptor identity does not match the trusted adapter key",
            remediation="Use the exact format, schema ID, and modality mapping from the registry.",
        )
    if set(descriptor.paths) != set(request.source_paths):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Adapter request paths do not exactly match the composite descriptor",
            remediation=(
                "Dispatch the verified descriptor inventory without adding or dropping paths."
            ),
        )

    expected_roles = {
        role: definition.model_dump(mode="json")
        for role, definition in profile.artifact_roles.items()
    }
    if descriptor.metadata.get("artifact_roles") != expected_roles:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Descriptor artifact_roles do not exactly match the packaged composite registry",
            remediation="Copy the exact matcher, media type, schema ID, and required flags.",
            field_or_path=f"streams.{descriptor.modality}.metadata.artifact_roles",
        )

    primary_role = profile.artifact_roles[profile.primary_role]
    primary_profile = load_builtin_profiles().get(primary_role.schema_id)
    if isinstance(primary_profile, TableProfile):
        expected_rate = primary_profile.expected_sample_rate_hz
        if expected_rate is not None and descriptor.sample_rate_hz != expected_rate:
            _fail(
                "SAMPLE_RATE_MISMATCH",
                "Descriptor sample rate disagrees with its primary table profile",
                remediation="Declare the exact primary artifact sample rate.",
                field_or_path=f"streams.{descriptor.modality}.sample_rate_hz",
                diagnostics={
                    "expected_hz": expected_rate,
                    "actual_hz": descriptor.sample_rate_hz,
                },
            )
    return descriptor


def _route_roles(
    source_paths: tuple[str, ...],
    descriptor: StreamDescriptor,
    profile: CompositeProfile,
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {role: [] for role in profile.artifact_roles}
    for path in source_paths:
        matches = [
            role
            for role, definition in profile.artifact_roles.items()
            if _matches(path, definition)
        ]
        if len(matches) != 1:
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "Every composite path must match exactly one declared artifact role",
                remediation=(
                    "Repair exact_paths/path_prefix matchers; never infer roles by filename."
                ),
                field_or_path=path,
                diagnostics={"matching_roles": matches},
            )
        grouped[matches[0]].append(path)
    for role, definition in profile.artifact_roles.items():
        if definition.required and not grouped[role]:
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "A required composite artifact role has no physical path",
                remediation="Export at least one path for every required registry role.",
                field_or_path=f"streams.{descriptor.modality}.metadata.artifact_roles.{role}",
            )
    return {role: tuple(paths) for role, paths in grouped.items()}


def _matches(path: str, definition: ArtifactRoleProfile) -> bool:
    matcher = definition.matcher
    if isinstance(matcher, ExactPathsMatcher):
        return path in matcher.paths
    if isinstance(matcher, PathPrefixMatcher):
        return path.startswith(matcher.path_prefix) and len(path) > len(matcher.path_prefix)
    return False


def _safe_source_path(bundle_root: Path, relative_path: str) -> Path:
    root = bundle_root.resolve()
    candidate = root.joinpath(*relative_path.split("/"))
    current = root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            _source_changed(relative_path, "source path resolves through a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        _source_changed(relative_path, "verified composite source is missing")
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _source_changed(relative_path, "verified source is not a regular bundle file")
    return resolved


def _verify_snapshot(
    resolved_paths: Mapping[str, Path],
    expected_digests: Mapping[str, str],
) -> None:
    for relative_path, source in resolved_paths.items():
        try:
            digest = _sha256_file(source)
        except OSError:
            _source_changed(relative_path, "verified composite source cannot be read")
        if digest != expected_digests[relative_path]:
            _source_changed(relative_path, "composite source digest changed during readiness")


def _sha256_file(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as payload:
        for chunk in iter(lambda: payload.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _synthetic_provenance(descriptor: StreamDescriptor) -> tuple[str, int]:
    generator_id = descriptor.metadata.get("generator_id")
    seed = descriptor.metadata.get("seed")
    if type(generator_id) is not str or not generator_id or type(seed) is not int:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Synthetic EEG descriptor must declare generator_id and integer seed provenance",
            remediation="Copy generator_id and seed from the owning synthetic bundle provenance.",
            field_or_path=f"streams.{descriptor.modality}.metadata",
        )
    return generator_id, seed


def _validate_cross_file_relationships(
    schema_id: str,
    tables: Mapping[str, pl.DataFrame],
) -> None:
    if schema_id == "vr-scene-source-bundle-v0.1":
        frames = set(cast(list[int], tables["frame_index"]["frame_id"].to_list()))
        aoi_frames = set(cast(list[int], tables["aoi_instances"]["frame_id"].to_list()))
        if not aoi_frames.issubset(frames):
            _relationship_failure(
                "AOI instances reference frame IDs absent from the scene frame index",
                diagnostics={"orphan_frame_ids": sorted(aoi_frames - frames)},
            )
    elif schema_id == "gaze-source-bundle-v0.1":
        _validate_gaze_relationships(tables["gaze_samples"], tables["fixations"])
    elif schema_id == "ecg-source-bundle-v0.1":
        sample_times = cast(list[float], tables["samples"]["source_timestamp_s"].to_list())
        peak_times = cast(list[float], tables["r_peaks"]["source_timestamp_s"].to_list())
        if peak_times and (
            min(peak_times) < min(sample_times) or max(peak_times) > max(sample_times)
        ):
            _relationship_failure(
                "ECG R-peak timestamps fall outside the retained sample time range",
                diagnostics={
                    "sample_min_s": min(sample_times),
                    "sample_max_s": max(sample_times),
                    "peak_min_s": min(peak_times),
                    "peak_max_s": max(peak_times),
                },
            )


def _validate_gaze_relationships(samples: pl.DataFrame, fixations: pl.DataFrame) -> None:
    sample_times = cast(list[float], samples["source_timestamp_s"].to_list())
    scene_ids = cast(list[int], samples["scene_frame_id"].to_list())
    for row in fixations.iter_rows(named=True):
        start = cast(float, row["start_source_timestamp_s"])
        end = cast(float, row["end_source_timestamp_s"])
        duration_ms = cast(float, row["duration_ms"])
        first_frame = cast(int, row["first_scene_frame_id"])
        last_frame = cast(int, row["last_scene_frame_id"])
        invalid = (
            start > end
            or start < min(sample_times)
            or end > max(sample_times)
            or first_frame > last_frame
            or first_frame < min(scene_ids)
            or last_frame > max(scene_ids)
            or not math.isclose(duration_ms, (end - start) * 1000.0, abs_tol=0.001)
        )
        if invalid:
            _relationship_failure(
                "Gaze fixation interval or scene-frame range disagrees with gaze samples",
                diagnostics={"fixation_id": cast(int, row["fixation_id"])},
            )


def _relationship_failure(
    message: str,
    *,
    diagnostics: dict[str, JsonValue],
) -> NoReturn:
    _fail(
        "STREAM_RELATIONSHIP_INVALID",
        message,
        remediation="Regenerate related artifacts from one consistent source timeline.",
        diagnostics=diagnostics,
    )


def _source_changed(relative_path: str, message: str) -> NoReturn:
    _fail(
        "SOURCE_CHANGED_DURING_READINESS",
        message,
        remediation="Stop ingestion and re-run Session Bundle integrity inspection.",
        field_or_path=relative_path,
    )


def _adapter_config_failure(
    profile: CompositeProfile,
    role: str,
    message: str,
) -> NoReturn:
    _fail(
        "ADAPTER_CONFIG_INVALID",
        message,
        remediation="Repair the packaged composite profile and trusted adapter registration.",
        field_or_path=f"{profile.schema_id}.{role}",
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


__all__ = ["COMPOSITE_KEYS", "CompositeStreamAdapter"]
