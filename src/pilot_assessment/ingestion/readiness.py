"""Deterministic M2 content inspection and readiness orchestration."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NoReturn, cast

import polars as pl
from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.ingestion import (
    IngestionReadinessReport,
    ReadinessDisposition,
    StreamReadiness,
    StreamReadinessResult,
    SyntheticSourceProvenance,
)
from pilot_assessment.contracts.session import SessionManifest, StreamDescriptor, StreamStatus
from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
)
from pilot_assessment.ingestion.adapters.composite import CompositeStreamAdapter
from pilot_assessment.ingestion.adapters.parquet_table import inspect_parquet_table
from pilot_assessment.ingestion.adapters.profiled_csv import ProfiledCsvAdapter
from pilot_assessment.ingestion.adapters.registry import AdapterNotFoundError, AdapterRegistry
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.models import NormalizedStream, PreparedSession
from pilot_assessment.ingestion.profiles import (
    ArtifactProfile,
    CompositeProfile,
    CsvProfile,
    TableProfile,
    load_builtin_profiles,
)

_CORE_ORDER = ("X", "U", "I", "G", "EEG", "ECG", "pilot_camera")
_DEFERRED_CHECKS = (
    "synchronization",
    "annotation_semantics",
    "anchor_availability",
    "bn_inference",
)


@dataclass(frozen=True, slots=True)
class IngestionReadinessOutcome:
    """Internal M2 result; only ``report`` crosses the future RPC boundary."""

    report: IngestionReadinessReport
    prepared_session: PreparedSession | None


class _ProfiledParquetAdapter:
    """Trusted exact-key wrapper for the standalone task-reference table."""

    adapter_id: ClassVar[str] = "profiled-parquet"
    adapter_version: ClassVar[str] = "0.1.0"
    keys: ClassVar[frozenset[tuple[str, str]]] = frozenset(
        {("parquet", "task-reference-path-raw-v0.1")}
    )

    def inspect(self, request: AdapterRequest) -> AdapterResult:
        profile = request.profile
        if not isinstance(profile, TableProfile):
            _raise_adapter_issue(
                "ADAPTER_CONFIG_INVALID",
                "Standalone profiled Parquet adapter requires a TableProfile",
                remediation="Resolve the task-reference schema through packaged profiles.",
            )
        if len(request.descriptors) != 1 or len(request.source_paths) != 1:
            _raise_adapter_issue(
                "ADAPTER_CONFIG_INVALID",
                "Task reference requires one descriptor and one Parquet path",
                remediation="Dispatch the exact standalone task-reference descriptor.",
            )
        descriptor = next(iter(request.descriptors.values()))
        if descriptor.modality != "task_reference":
            _raise_adapter_issue(
                "ADAPTER_CONFIG_INVALID",
                "Standalone profiled Parquet adapter is reserved for task_reference",
                remediation="Use the adapter only for the bundle task reference.",
            )
        relative_path = request.source_paths[0]
        source = _safe_verified_path(request.bundle_root, relative_path)
        _verify_digest(source, relative_path, request.verified_digests[relative_path])
        table = inspect_parquet_table(source, profile)
        _verify_digest(source, relative_path, request.verified_digests[relative_path])
        stream = NormalizedStream(
            modality="task_reference",
            schema_id="task-reference-normalized-v0.1",
            clock_id=descriptor.clock_id,
            source_timestamp_column=cast(str, profile.source_timestamp_column),
            primary_table_role="commanded_path",
            tables={"commanded_path": table},
            json_artifacts={},
            file_artifacts={},
            source_paths=request.source_paths,
            source_checksums=request.verified_digests,
        )
        return AdapterResult(
            streams={"task_reference": stream},
            context={},
            artifact_summaries=(
                AdapterArtifactSummary(
                    role="commanded_path",
                    paths=request.source_paths,
                    row_count=table.height,
                ),
            ),
        )


def build_default_registry() -> AdapterRegistry:
    """Build the fixed trusted-code registry; manifests never name Python classes."""

    registry = AdapterRegistry()
    registry.register(ProfiledCsvAdapter())
    registry.register(CompositeStreamAdapter())
    registry.register(_ProfiledParquetAdapter())
    return registry


def inspect_ingestion_readiness(
    bundle_root: str | Path,
    *,
    loader: ManifestLoader | None = None,
    registry: AdapterRegistry | None = None,
) -> IngestionReadinessOutcome:
    """Inspect M2 source content without aligning clocks or authorizing a run."""

    loaded = (loader or ManifestLoader()).load(bundle_root)
    active_registry = registry or build_default_registry()
    catalog = load_builtin_profiles()
    results: dict[str, StreamReadinessResult] = {}
    normalized: dict[str, NormalizedStream] = {}
    context: dict[str, JsonValue] = {}
    global_issues: list[DomainErrorData] = []
    processed: set[str] = set()

    x_descriptor = loaded.manifest.streams["X"]
    u_descriptor = loaded.manifest.streams["U"]
    if _is_shared_present_xu(x_descriptor, u_descriptor):
        group_results, adapter_result = _inspect_present_group(
            loaded,
            ("X", "U"),
            active_registry,
            catalog,
        )
        results.update(group_results)
        _merge_adapter_result(adapter_result, normalized, context, global_issues)
        processed.update({"X", "U"})

    for modality in _CORE_ORDER:
        if modality in processed:
            continue
        descriptor = loaded.manifest.streams[modality]
        if descriptor.status is StreamStatus.PRESENT:
            group_results, adapter_result = _inspect_present_group(
                loaded,
                (modality,),
                active_registry,
                catalog,
            )
            results.update(group_results)
            _merge_adapter_result(adapter_result, normalized, context, global_issues)
        else:
            results[modality] = _result_for_declared_non_ready(descriptor)

    task_result: StreamReadinessResult | None = None
    task_stream: NormalizedStream | None = None
    reference = loaded.manifest.task.reference
    if reference is not None and reference.source == "bundle":
        assert reference.stream_id == "task_reference"
        descriptor = loaded.manifest.streams["task_reference"]
        if descriptor.status is StreamStatus.PRESENT:
            task_results, adapter_result = _inspect_present_group(
                loaded,
                ("task_reference",),
                active_registry,
                catalog,
            )
            task_result = task_results["task_reference"]
            if adapter_result is not None:
                task_stream = adapter_result.streams.get("task_reference")
                global_issues.extend(adapter_result.issues)
        else:
            task_result = _result_for_declared_non_ready(descriptor)

    relationship_issue = _validate_scene_gaze_relationship(normalized)
    if relationship_issue is not None:
        global_issues.append(relationship_issue)
        gaze_result = results["G"]
        payload = gaze_result.model_dump(mode="json")
        payload["readiness"] = "invalid"
        payload["issues"] = [
            *payload["issues"],
            relationship_issue.model_dump(mode="json"),
        ]
        results["G"] = StreamReadinessResult.model_validate(payload)
        normalized.pop("G", None)

    disposition = _disposition(tuple(results.values()), task_result)
    synthetic_provenance = _synthetic_provenance(loaded.manifest)
    report = IngestionReadinessReport(
        contract_version="0.1.0",
        validation_scope="inspect_only_ingestion_content_v1",
        session_id=loaded.manifest.session_id,
        manifest_version=loaded.manifest.bundle_schema_version,
        source_classification=loaded.manifest.privacy.classification,
        synthetic_provenance=synthetic_provenance,
        disposition=disposition,
        can_continue_to_synchronization=disposition is not ReadinessDisposition.BLOCKED,
        formal_run_authorized=False,
        stream_results={modality: results[modality] for modality in _CORE_ORDER},
        task_reference_result=task_result,
        global_issues=tuple(_sort_issues(global_issues)),
        deferred_checks=_DEFERRED_CHECKS,
        source_snapshot_fingerprint=_source_fingerprint(loaded),
    )
    prepared = None
    if disposition is not ReadinessDisposition.BLOCKED:
        prepared = PreparedSession(
            streams={key: normalized[key] for key in _CORE_ORDER if key in normalized},
            context=context,
            task_reference=task_stream,
        )
    return IngestionReadinessOutcome(report=report, prepared_session=prepared)


def _inspect_present_group(
    loaded: LoadedManifest,
    modalities: tuple[str, ...],
    registry: AdapterRegistry,
    catalog: Mapping[str, ArtifactProfile],
) -> tuple[dict[str, StreamReadinessResult], AdapterResult | None]:
    descriptors = {modality: loaded.manifest.streams[modality] for modality in modalities}
    primary = descriptors[modalities[0]]
    profile = catalog.get(primary.schema_id)
    if profile is None:
        issue = _issue(
            "ADAPTER_NOT_FOUND",
            ErrorSeverity.ERROR,
            "No packaged profile exists for the declared present stream",
            remediation="Install an approved profile or correct the descriptor schema ID.",
            field_or_path=f"streams.{primary.modality}.schema_id",
        )
        return (
            {
                modality: _failed_present_result(
                    descriptor,
                    StreamReadiness.UNSUPPORTED,
                    issue,
                )
                for modality, descriptor in descriptors.items()
            },
            None,
        )
    try:
        adapter = registry.resolve(primary.format, primary.schema_id)
    except AdapterNotFoundError:
        issue = _issue(
            "ADAPTER_NOT_FOUND",
            ErrorSeverity.ERROR,
            "No trusted adapter is registered for the declared format and schema",
            remediation="Install or register an approved exact-key adapter.",
            field_or_path=f"streams.{primary.modality}",
            diagnostics={"format": primary.format, "schema_id": primary.schema_id},
        )
        return (
            {
                modality: _failed_present_result(
                    descriptor,
                    StreamReadiness.UNSUPPORTED,
                    issue,
                )
                for modality, descriptor in descriptors.items()
            },
            None,
        )

    source_paths = tuple(
        dict.fromkeys(path for item in descriptors.values() for path in item.paths)
    )
    verified = {path: loaded.verified_digests[path] for path in source_paths}
    request = AdapterRequest(
        bundle_root=loaded.bundle_root,
        descriptors=descriptors,
        source_paths=source_paths,
        verified_digests=verified,
        profile=profile,
    )
    try:
        adapter_result = adapter.inspect(request)
        if set(adapter_result.streams) != set(modalities):
            raise RuntimeError("adapter returned an unexpected logical stream inventory")
        ready = {
            modality: _ready_result(
                descriptors[modality],
                adapter_result.streams[modality],
                adapter_result,
                profile,
                adapter.adapter_id,
                adapter.adapter_version,
                catalog,
            )
            for modality in modalities
        }
        return ready, adapter_result
    except AdapterInspectionError as error:
        issue = error.issue
    except Exception as error:
        issue = _issue(
            "ADAPTER_EXECUTION_FAILED",
            ErrorSeverity.ERROR,
            "Trusted adapter failed without a domain-safe result",
            remediation="Review backend logs and repair the adapter or source artifact.",
            field_or_path=f"streams.{primary.modality}",
            diagnostics={"exception_type": type(error).__name__},
        )
    return (
        {
            modality: _failed_present_result(
                descriptor,
                StreamReadiness.INVALID,
                issue,
                adapter_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
            )
            for modality, descriptor in descriptors.items()
        },
        None,
    )


def _ready_result(
    descriptor: StreamDescriptor,
    stream: NormalizedStream,
    adapter_result: AdapterResult,
    profile: ArtifactProfile,
    adapter_id: str,
    adapter_version: str,
    catalog: Mapping[str, ArtifactProfile],
) -> StreamReadinessResult:
    table = stream.primary_table
    timestamps = cast(list[float], table[stream.source_timestamp_column].to_list())
    observed_rate = None
    if len(timestamps) >= 2:
        observed_rate = 1.0 / statistics.median(
            right - left for left, right in zip(timestamps, timestamps[1:], strict=False)
        )
    artifact_counts = {
        summary.role: summary.row_count
        for summary in adapter_result.artifact_summaries
        if summary.row_count is not None
    }
    return StreamReadinessResult(
        modality=descriptor.modality,
        declared_status=descriptor.status,
        required_for_import=descriptor.required_for_import,
        readiness=StreamReadiness.READY,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        source_paths=tuple(descriptor.paths),
        source_checksums=dict(descriptor.checksums),
        normalized_schema_id=stream.schema_id,
        row_count=table.height,
        artifact_row_counts=artifact_counts,
        source_time_start_s=min(timestamps),
        source_time_end_s=max(timestamps),
        observed_sample_rate_hz=observed_rate,
        canonical_fields=tuple(table.columns),
        units=_profile_units(profile, stream, catalog),
        quality_summary=_quality_summary(descriptor, table),
        assumptions=_profile_assumptions(profile, stream),
        issues=tuple(_sort_issues(adapter_result.issues)),
    )


def _result_for_declared_non_ready(descriptor: StreamDescriptor) -> StreamReadinessResult:
    if descriptor.status is StreamStatus.NOT_APPLICABLE:
        readiness = StreamReadiness.NOT_APPLICABLE
        issues: tuple[DomainErrorData, ...] = ()
    elif descriptor.status is StreamStatus.INVALID:
        readiness = StreamReadiness.INVALID
        issues = (
            _issue(
                "STREAM_DECLARED_INVALID",
                ErrorSeverity.ERROR,
                "Manifest declares this source artifact invalid",
                remediation="Repair and re-export the stream before formal use.",
                field_or_path=f"streams.{descriptor.modality}.status",
            ),
        )
    else:
        readiness = StreamReadiness.UNAVAILABLE
        error_code = (
            "REQUIRED_STREAM_UNAVAILABLE"
            if descriptor.required_for_import
            else "STREAM_UNAVAILABLE"
        )
        issues = (
            _issue(
                error_code,
                ErrorSeverity.ERROR if descriptor.required_for_import else ErrorSeverity.WARNING,
                "Declared stream has no readable artifact in this bundle",
                remediation="Export the stream or mark it not applicable when justified.",
                field_or_path=f"streams.{descriptor.modality}.status",
                diagnostics={"declared_status": descriptor.status.value},
            ),
        )
    return StreamReadinessResult(
        modality=descriptor.modality,
        declared_status=descriptor.status,
        required_for_import=descriptor.required_for_import,
        readiness=readiness,
        source_paths=tuple(descriptor.paths),
        source_checksums=dict(descriptor.checksums),
        issues=issues,
    )


def _failed_present_result(
    descriptor: StreamDescriptor,
    readiness: StreamReadiness,
    issue: DomainErrorData,
    *,
    adapter_id: str | None = None,
    adapter_version: str | None = None,
) -> StreamReadinessResult:
    return StreamReadinessResult(
        modality=descriptor.modality,
        declared_status=descriptor.status,
        required_for_import=descriptor.required_for_import,
        readiness=readiness,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        source_paths=tuple(descriptor.paths),
        source_checksums=dict(descriptor.checksums),
        issues=(issue,),
    )


def _merge_adapter_result(
    adapter_result: AdapterResult | None,
    normalized: dict[str, NormalizedStream],
    context: dict[str, JsonValue],
    global_issues: list[DomainErrorData],
) -> None:
    if adapter_result is None:
        return
    normalized.update(adapter_result.streams)
    for key, value in adapter_result.context.items():
        if key in context and context[key] != value:
            issue = _issue(
                "STREAM_CONTEXT_NOT_CONSTANT",
                ErrorSeverity.ERROR,
                "Adapters produced conflicting values for one session context key",
                remediation="Split the session or repair conflicting source profiles.",
                field_or_path=key,
            )
            global_issues.append(issue)
        else:
            context[key] = value
    global_issues.extend(adapter_result.issues)


def _profile_units(
    profile: ArtifactProfile,
    stream: NormalizedStream,
    catalog: Mapping[str, ArtifactProfile],
) -> dict[str, str]:
    if isinstance(profile, CsvProfile):
        return {
            column.canonical_name: column.unit
            for column in profile.columns
            if column.canonical_name in stream.primary_table.columns
        }
    table_profile: TableProfile | None = None
    if isinstance(profile, TableProfile):
        table_profile = profile
    elif isinstance(profile, CompositeProfile):
        definition = profile.artifact_roles[profile.primary_role]
        candidate = catalog.get(definition.schema_id)
        if isinstance(candidate, TableProfile):
            table_profile = candidate
    if table_profile is None:
        return {}
    return {
        column.name: column.unit
        for column in table_profile.columns
        if column.name in stream.primary_table.columns
    }


def _profile_assumptions(
    profile: ArtifactProfile,
    stream: NormalizedStream,
) -> tuple[str, ...]:
    assumptions: set[str] = set()
    if isinstance(profile, CsvProfile):
        assumptions.update(
            column.engineering_assumption
            for column in profile.columns
            if column.canonical_name in stream.primary_table.columns
            and column.engineering_assumption is not None
        )
    declared = profile.extensions.get("assumptions")
    if isinstance(declared, list):
        assumptions.update(item for item in declared if isinstance(item, str))
    return tuple(sorted(assumptions))


def _quality_summary(
    descriptor: StreamDescriptor,
    table: pl.DataFrame,
) -> dict[str, JsonValue]:
    validity_column = next(
        (
            name
            for name in ("signal_valid", "frame_valid", "binocular_valid", "fixation_valid")
            if name in table.columns
        ),
        None,
    )
    valid_fraction = 1.0
    if validity_column is not None:
        valid_fraction = float(table[validity_column].sum()) / table.height
    gap_count = 0
    if descriptor.quality_summary is not None and descriptor.quality_summary.gap_count is not None:
        gap_count = descriptor.quality_summary.gap_count
    return {"valid_fraction": valid_fraction, "gap_count": gap_count}


def _validate_scene_gaze_relationship(
    streams: Mapping[str, NormalizedStream],
) -> DomainErrorData | None:
    scene = streams.get("I")
    gaze = streams.get("G")
    if scene is None or gaze is None:
        return None
    frame_index = scene.tables.get("frame_index")
    aoi_instances = scene.tables.get("aoi_instances")
    gaze_samples = gaze.tables.get("gaze_samples")
    if frame_index is None or aoi_instances is None or gaze_samples is None:
        return _relationship_issue("Scene and gaze composite roles are incomplete")
    frame_ids = set(cast(list[int], frame_index["frame_id"].to_list()))
    gaze_frame_ids = cast(list[int], gaze_samples["scene_frame_id"].to_list())
    orphan_frames = sorted(set(gaze_frame_ids) - frame_ids)
    aoi_pairs = set(
        cast(
            list[tuple[int, str]],
            aoi_instances.select("frame_id", "aoi_id").iter_rows(),
        )
    )
    assigned = cast(list[str | None], gaze_samples["assigned_aoi_id"].to_list())
    orphan_assignments = sorted(
        {
            f"{frame_id}:{aoi_id}"
            for frame_id, aoi_id in zip(gaze_frame_ids, assigned, strict=True)
            if aoi_id is not None and (frame_id, aoi_id) not in aoi_pairs
        }
    )
    if orphan_frames or orphan_assignments:
        return _relationship_issue(
            "Gaze samples reference absent scene frames or frame-specific AOIs",
            diagnostics={
                "orphan_frame_ids": orphan_frames,
                "orphan_assignments": orphan_assignments,
            },
        )
    return None


def _relationship_issue(
    message: str,
    diagnostics: dict[str, JsonValue] | None = None,
) -> DomainErrorData:
    return _issue(
        "STREAM_RELATIONSHIP_INVALID",
        ErrorSeverity.ERROR,
        message,
        remediation="Regenerate scene and gaze artifacts from one shared frame/AOI timeline.",
        field_or_path="streams.G",
        diagnostics=diagnostics,
    )


def _disposition(
    core_results: tuple[StreamReadinessResult, ...],
    task_result: StreamReadinessResult | None,
) -> ReadinessDisposition:
    all_results = [*core_results]
    if task_result is not None:
        all_results.append(task_result)
    if any(
        result.required_for_import and result.readiness is not StreamReadiness.READY
        for result in all_results
    ):
        return ReadinessDisposition.BLOCKED
    if any(
        result.readiness
        in {StreamReadiness.UNAVAILABLE, StreamReadiness.INVALID, StreamReadiness.UNSUPPORTED}
        for result in all_results
    ):
        return ReadinessDisposition.READY_PARTIAL
    return ReadinessDisposition.READY


def _synthetic_provenance(
    manifest: SessionManifest,
) -> SyntheticSourceProvenance | None:
    if manifest.privacy.classification != "synthetic-test-data":
        return None
    raw = manifest.extensions.get("synthetic")
    if not isinstance(raw, dict):
        raise ValueError("synthetic-test-data manifest lacks synthetic provenance")
    try:
        payload = {
            field_name: raw.get(field_name) for field_name in SyntheticSourceProvenance.model_fields
        }
        return SyntheticSourceProvenance.model_validate(payload)
    except ValidationError as error:
        raise ValueError("synthetic-test-data provenance is incomplete or invalid") from error


def _source_fingerprint(loaded: LoadedManifest) -> str:
    payload = json.dumps(
        {
            "manifest": loaded.manifest.model_dump(mode="json"),
            "verified_digests": dict(sorted(loaded.verified_digests.items())),
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_shared_present_xu(x_stream: StreamDescriptor, u_stream: StreamDescriptor) -> bool:
    return (
        x_stream.status is StreamStatus.PRESENT
        and u_stream.status is StreamStatus.PRESENT
        and x_stream.paths == u_stream.paths
        and x_stream.format == u_stream.format
        and x_stream.schema_id == u_stream.schema_id
        and x_stream.metadata.get("shared_source_id") == u_stream.metadata.get("shared_source_id")
    )


def _safe_verified_path(bundle_root: Path, relative_path: str) -> Path:
    root = bundle_root.resolve()
    candidate = root.joinpath(*relative_path.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        _raise_adapter_issue(
            "SOURCE_CHANGED_DURING_READINESS",
            "Verified task-reference source is missing",
            remediation="Re-run Session Bundle integrity inspection.",
            field_or_path=relative_path,
        )
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _raise_adapter_issue(
            "SOURCE_CHANGED_DURING_READINESS",
            "Verified task-reference source is no longer a regular bundle file",
            remediation="Restore the immutable bundle artifact and retry.",
            field_or_path=relative_path,
        )
    return resolved


def _verify_digest(source: Path, relative_path: str, expected: str) -> None:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != expected:
        _raise_adapter_issue(
            "SOURCE_CHANGED_DURING_READINESS",
            "Task-reference bytes changed after M1 integrity inspection",
            remediation="Stop and restart inspection from the M1 boundary.",
            field_or_path=relative_path,
        )


def _sort_issues(issues: Iterable[DomainErrorData]) -> list[DomainErrorData]:
    values = list(issues)
    return sorted(
        values,
        key=lambda issue: (
            issue.field_or_path or "",
            issue.error_code,
            issue.severity.value,
            issue.message,
        ),
    )


def _issue(
    error_code: str,
    severity: ErrorSeverity,
    message: str,
    *,
    remediation: str,
    field_or_path: str | None = None,
    diagnostics: dict[str, JsonValue] | None = None,
) -> DomainErrorData:
    return DomainErrorData(
        error_code=error_code,
        severity=severity,
        recoverable=True,
        message=message,
        field_or_path=field_or_path,
        remediation=remediation,
        diagnostics=diagnostics or {},
    )


def _raise_adapter_issue(
    error_code: str,
    message: str,
    *,
    remediation: str,
    field_or_path: str | None = None,
) -> NoReturn:
    raise AdapterInspectionError(
        _issue(
            error_code,
            ErrorSeverity.ERROR,
            message,
            remediation=remediation,
            field_or_path=field_or_path,
        )
    )


__all__ = [
    "IngestionReadinessOutcome",
    "build_default_registry",
    "inspect_ingestion_readiness",
]
