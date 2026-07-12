"""M1-to-M3 native-rate synchronization orchestration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast

import polars as pl

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.ingestion import (
    IngestionReadinessReport,
    StreamReadiness,
    StreamReadinessResult,
)
from pilot_assessment.contracts.session import ClockSync, StreamDescriptor
from pilot_assessment.contracts.synchronization import (
    BLOCKING_SYNCHRONIZATION_ERROR_CODES,
    AnnotationSynchronizationResult,
    ClockMappingSummary,
    SceneGazeMetrics,
    SessionWindow,
    StreamSynchronizationResult,
    SynchronizationDisposition,
    SynchronizationItemStatus,
    SynchronizationPolicy,
    SynchronizationReport,
    TaskReferenceSynchronizationResult,
    TemporalArtifactMetrics,
)
from pilot_assessment.ingestion.adapters.registry import AdapterRegistry
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.models import NormalizedStream
from pilot_assessment.ingestion.readiness import inspect_loaded_ingestion_readiness
from pilot_assessment.synchronization.annotations import (
    AnnotationAlignmentError,
    align_annotations,
)
from pilot_assessment.synchronization.bindings import (
    TemporalAlignmentError,
    apply_point_window,
    derive_session_window,
    inherit_point_time,
    map_interval_artifact,
    map_point_artifact,
    preserve_untimed_artifact,
)
from pilot_assessment.synchronization.clock import (
    validate_clock_declaration,
    validate_same_clock_mappings,
)
from pilot_assessment.synchronization.fingerprint import (
    HashWriter,
    canonical_json_bytes,
    encode_boolean_values,
    encode_int64_values,
    fingerprint_policy,
    fingerprint_synchronization,
)
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedSession,
    AlignedStreamView,
    SynchronizationInput,
    SynchronizationOutcome,
)
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
    TemporalBindingCatalog,
    TemporalStreamProfile,
    UntimedBinding,
    builtin_temporal_catalog_fingerprint,
    load_builtin_temporal_catalog,
)
from pilot_assessment.synchronization.quality import (
    compute_interval_metrics,
    compute_point_metrics,
    validate_scene_gaze_time,
)

_CORE_ORDER = ("X", "U", "I", "G", "EEG", "ECG", "pilot_camera")


class _MissingTemporalBinding(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _AlignedWork:
    view: AlignedStreamView
    artifacts: dict[str, TemporalArtifactMetrics]
    time_parts: dict[str, bytes]


def _item_status_from_readiness(
    readiness: StreamReadiness,
    *,
    attempted: bool,
) -> SynchronizationItemStatus:
    if readiness is StreamReadiness.READY:
        if attempted:
            raise ValueError("attempted ready inputs require an explicit M3 result")
        return SynchronizationItemStatus.NOT_ATTEMPTED
    return {
        StreamReadiness.UNAVAILABLE: SynchronizationItemStatus.UNAVAILABLE,
        StreamReadiness.INVALID: SynchronizationItemStatus.INVALID,
        StreamReadiness.UNSUPPORTED: SynchronizationItemStatus.UNSUPPORTED,
        StreamReadiness.NOT_APPLICABLE: SynchronizationItemStatus.NOT_APPLICABLE,
    }[readiness]


def _derive_disposition(
    *,
    session_window: SessionWindow | None,
    streams: Mapping[str, StreamSynchronizationResult],
    task_reference: TaskReferenceSynchronizationResult | None,
    annotations: AnnotationSynchronizationResult | None,
    global_issues: tuple[DomainErrorData, ...],
) -> SynchronizationDisposition:
    required_core_failed = any(
        result.required_for_import
        and result.synchronization_status is not SynchronizationItemStatus.ALIGNED
        for result in streams.values()
    )
    optional_core_failed = any(
        not result.required_for_import
        and result.synchronization_status
        not in {SynchronizationItemStatus.ALIGNED, SynchronizationItemStatus.NOT_APPLICABLE}
        for result in streams.values()
    )
    reference_blocked = bool(
        task_reference is not None
        and task_reference.source == "bundle"
        and task_reference.required_for_import
        and task_reference.synchronization_status is not SynchronizationItemStatus.ALIGNED
    )
    reference_degraded = bool(
        task_reference is not None
        and task_reference.source == "bundle"
        and task_reference.required_for_import is False
        and task_reference.synchronization_status
        not in {SynchronizationItemStatus.ALIGNED, SynchronizationItemStatus.NOT_APPLICABLE}
    )
    annotation_failed = (
        annotations is None
        or annotations.synchronization_status is not SynchronizationItemStatus.ALIGNED
    )
    global_blocking = any(
        issue.error_code in BLOCKING_SYNCHRONIZATION_ERROR_CODES for issue in global_issues
    )
    if (
        session_window is None
        or required_core_failed
        or reference_blocked
        or annotation_failed
        or global_blocking
    ):
        return SynchronizationDisposition.BLOCKED
    if optional_core_failed or reference_degraded:
        return SynchronizationDisposition.READY_PARTIAL
    return SynchronizationDisposition.READY


def synchronize_session(
    sync_input: SynchronizationInput,
    *,
    policy: SynchronizationPolicy | None = None,
) -> SynchronizationOutcome:
    active_policy = policy or SynchronizationPolicy()
    return _synchronize_valid_input(sync_input, active_policy)


def synchronize_bundle(
    bundle_root: str | Path,
    *,
    policy: SynchronizationPolicy | None = None,
    loader: ManifestLoader | None = None,
    registry: AdapterRegistry | None = None,
) -> SynchronizationOutcome:
    active_loader = loader or ManifestLoader()
    loaded = active_loader.load(bundle_root)
    ingestion = inspect_loaded_ingestion_readiness(loaded, registry=registry)
    active_policy = policy or SynchronizationPolicy()
    if ingestion.prepared_session is None:
        try:
            return _blocked_from_ingestion(loaded, ingestion.report, active_policy)
        except Exception:
            return _internal_failure_from_readiness(loaded, ingestion.report, active_policy)
    try:
        sync_input = SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=ingestion.report,
            prepared_session=ingestion.prepared_session,
        )
    except Exception:
        return _internal_failure_from_readiness(loaded, ingestion.report, active_policy)
    return synchronize_session(sync_input, policy=active_policy)


def _blocked_from_ingestion(
    loaded: LoadedManifest,
    readiness: IngestionReadinessReport,
    policy: SynchronizationPolicy,
) -> SynchronizationOutcome:
    stream_results = {
        modality: _unattempted_core_result(readiness.stream_results[modality])
        for modality in _CORE_ORDER
    }
    reference = loaded.manifest.task.reference
    reference_result: TaskReferenceSynchronizationResult | None = None
    if reference is not None and reference.source == "model_bundle":
        reference_result = TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="model_bundle",
            synchronization_status=(SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION),
        )
    elif reference is not None and readiness.task_reference_result is not None:
        item = readiness.task_reference_result
        reference_result = TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="bundle",
            declared_status=item.declared_status,
            required_for_import=item.required_for_import,
            input_readiness=item.readiness,
            synchronization_status=_item_status_from_readiness(
                item.readiness,
                attempted=False,
            ),
            source_schema_id=item.normalized_schema_id,
            source_checksums=dict(item.source_checksums),
            issues=tuple(_sort_issues(item.issues)),
        )

    blocked_issue = DomainErrorData(
        error_code="SYNCHRONIZATION_INPUT_BLOCKED",
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message="M2 ingestion readiness does not permit native-rate synchronization.",
        field_or_path="ingestion_readiness",
        remediation="Resolve required M2 readiness failures and inspect the bundle again.",
    )
    annotation_result = AnnotationSynchronizationResult(
        synchronization_status=SynchronizationItemStatus.NOT_ATTEMPTED,
        revision=loaded.manifest.annotations.revision,
        issues=(blocked_issue,),
    )
    global_issues = tuple(_sort_issues(readiness.global_issues))
    policy_fingerprint = fingerprint_policy(policy)
    catalog_fingerprint = builtin_temporal_catalog_fingerprint()
    statuses = _status_payload(
        stream_results=stream_results,
        task_reference=reference_result,
        annotations=annotation_result,
        global_issues=global_issues,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue=False,
    )
    synchronization_fingerprint = fingerprint_synchronization(
        source_snapshot_fingerprint=readiness.source_snapshot_fingerprint,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        aligned_time_parts={},
        aligned_annotations_json=canonical_json_bytes(None),
        statuses_and_issues_json=canonical_json_bytes(statuses),
    )
    report = SynchronizationReport(
        contract_version="0.1.0",
        validation_scope="native_rate_session_time_alignment_v1",
        session_id=readiness.session_id,
        source_snapshot_fingerprint=readiness.source_snapshot_fingerprint,
        source_classification=readiness.source_classification,
        synthetic_provenance=readiness.synthetic_provenance,
        policy=policy,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue_to_anchor_availability=False,
        formal_run_authorized=False,
        stream_results=stream_results,
        task_reference_result=reference_result,
        annotation_result=annotation_result,
        global_issues=global_issues,
        synchronization_fingerprint=synchronization_fingerprint,
    )
    return SynchronizationOutcome(report=report, aligned_session=None)


def _unattempted_core_result(item: object) -> StreamSynchronizationResult:
    if not isinstance(item, StreamReadinessResult):
        raise TypeError("core readiness inventory is invalid")
    return StreamSynchronizationResult(
        modality=item.modality,
        declared_status=item.declared_status,
        required_for_import=item.required_for_import,
        input_readiness=item.readiness,
        synchronization_status=_item_status_from_readiness(item.readiness, attempted=False),
        source_schema_id=item.normalized_schema_id,
        issues=tuple(_sort_issues(item.issues)),
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
            canonical_json_bytes(issue.model_dump(mode="json")),
        ),
    )


def _status_payload(
    *,
    stream_results: Mapping[str, StreamSynchronizationResult],
    task_reference: TaskReferenceSynchronizationResult | None,
    annotations: AnnotationSynchronizationResult | None,
    global_issues: tuple[DomainErrorData, ...],
    session_window: SessionWindow | None,
    disposition: SynchronizationDisposition,
    can_continue: bool,
) -> dict[str, object]:
    return {
        "streams": {
            key: stream_results[key].model_dump(mode="json") for key in sorted(stream_results)
        },
        "task_reference": (
            task_reference.model_dump(mode="json") if task_reference is not None else None
        ),
        "annotations": annotations.model_dump(mode="json") if annotations is not None else None,
        "global_issues": [issue.model_dump(mode="json") for issue in global_issues],
        "session_window": (
            session_window.model_dump(mode="json") if session_window is not None else None
        ),
        "disposition": disposition.value,
        "can_continue_to_anchor_availability": can_continue,
        "formal_run_authorized": False,
    }


def _synchronize_valid_input(
    sync_input: SynchronizationInput,
    policy: SynchronizationPolicy,
) -> SynchronizationOutcome:
    try:
        return _synchronize_valid_input_impl(sync_input, policy)
    except Exception:
        return _internal_failure_from_input(sync_input, policy)


def _synchronize_valid_input_impl(
    sync_input: SynchronizationInput,
    policy: SynchronizationPolicy,
) -> SynchronizationOutcome:
    catalog = load_builtin_temporal_catalog()
    catalog_fingerprint = builtin_temporal_catalog_fingerprint()
    policy_fingerprint = fingerprint_policy(policy)
    clock_issues = _validate_ready_clock_inventory(sync_input, policy)
    readiness = sync_input.readiness_report
    stream_results: dict[str, StreamSynchronizationResult] = {}
    works: dict[str, _AlignedWork] = {}
    global_issues = tuple(_sort_issues(readiness.global_issues))

    for modality in _CORE_ORDER:
        item = readiness.stream_results[modality]
        if item.readiness is not StreamReadiness.READY:
            stream_results[modality] = _unattempted_core_result(item)

    x_item = readiness.stream_results["X"]
    x_stream = sync_input.prepared_session.streams.get("X")
    x_descriptor = sync_input.loaded_manifest.manifest.streams["X"]
    window: SessionWindow | None = None
    premapped_x: pl.DataFrame | None = None
    if x_item.readiness is StreamReadiness.READY and x_stream is not None:
        x_issue = clock_issues.get("X")
        if x_issue is not None:
            stream_results["X"] = _failed_core_result(
                x_item,
                x_descriptor,
                SynchronizationItemStatus.INVALID,
                x_issue,
            )
        else:
            try:
                x_profile = _profile_for_stream(catalog, x_stream)
                x_binding = x_profile.bindings_by_role.get("samples")
                if not isinstance(x_binding, PointBinding):
                    raise _MissingTemporalBinding
                clock = _required_clock(x_descriptor)
                premapped_x = map_point_artifact(
                    x_stream.tables["samples"],
                    x_binding,
                    clock,
                )
                try:
                    window = derive_session_window(sync_input, premapped_x, x_binding)
                except ValueError as error:
                    if str(error) != "SESSION_WINDOW_UNAVAILABLE":
                        raise
                    stream_results["X"] = _failed_core_result(
                        x_item,
                        x_descriptor,
                        SynchronizationItemStatus.INVALID,
                        _issue(
                            "SESSION_WINDOW_UNAVAILABLE",
                            "Master-clock X cannot establish the canonical session window.",
                            field_or_path="streams.X",
                            remediation="Correct X coverage and the declared master clock.",
                        ),
                    )
                else:
                    works["X"] = _align_stream_work(
                        logical_id="X",
                        stream=x_stream,
                        descriptor=x_descriptor,
                        profile=x_profile,
                        window=window,
                        policy=policy,
                        premapped_points={"samples": premapped_x},
                    )
                    stream_results["X"] = _aligned_core_result(
                        x_item,
                        x_descriptor,
                        works["X"],
                    )
            except _MissingTemporalBinding:
                stream_results["X"] = _failed_core_result(
                    x_item,
                    x_descriptor,
                    SynchronizationItemStatus.UNSUPPORTED,
                    _binding_issue("X"),
                )
            except TemporalAlignmentError as error:
                stream_results["X"] = _failed_core_result(
                    x_item,
                    x_descriptor,
                    SynchronizationItemStatus.INVALID,
                    error.issue,
                )

    if window is None:
        for modality in _CORE_ORDER:
            if modality in stream_results:
                continue
            item = readiness.stream_results[modality]
            descriptor = sync_input.loaded_manifest.manifest.streams[modality]
            clock_issue = clock_issues.get(modality)
            stream_results[modality] = (
                _failed_core_result(
                    item,
                    descriptor,
                    SynchronizationItemStatus.INVALID,
                    clock_issue,
                )
                if clock_issue is not None
                else _unattempted_core_result(item)
            )
        reference_result = _unattempted_reference(sync_input)
        reference = sync_input.loaded_manifest.manifest.task.reference
        reference_clock_issue = clock_issues.get("task_reference")
        reference_item = readiness.task_reference_result
        if (
            reference is not None
            and reference.source == "bundle"
            and reference_clock_issue is not None
            and reference_item is not None
        ):
            reference_result = _failed_reference(
                reference.reference_id,
                reference_item,
                _reference_descriptor(sync_input),
                reference_clock_issue,
            )
        return _finalize_valid_input(
            sync_input=sync_input,
            policy=policy,
            policy_fingerprint=policy_fingerprint,
            catalog_fingerprint=catalog_fingerprint,
            window=None,
            stream_results=stream_results,
            works={},
            reference_result=reference_result,
            reference_work=None,
            annotations=None,
            annotation_result=_not_attempted_annotations(sync_input),
            global_issues=global_issues,
        )

    for modality in _CORE_ORDER[1:]:
        item = readiness.stream_results[modality]
        if item.readiness is not StreamReadiness.READY:
            continue
        descriptor = sync_input.loaded_manifest.manifest.streams[modality]
        clock_issue = clock_issues.get(modality)
        if clock_issue is not None:
            stream_results[modality] = _failed_core_result(
                item,
                descriptor,
                SynchronizationItemStatus.INVALID,
                clock_issue,
            )
            continue
        stream = sync_input.prepared_session.streams[modality]
        try:
            profile = _profile_for_stream(catalog, stream)
            work = _align_stream_work(
                logical_id=modality,
                stream=stream,
                descriptor=descriptor,
                profile=profile,
                window=window,
                policy=policy,
            )
            works[modality] = work
            if modality != "G":
                stream_results[modality] = _aligned_core_result(item, descriptor, work)
        except _MissingTemporalBinding:
            stream_results[modality] = _failed_core_result(
                item,
                descriptor,
                SynchronizationItemStatus.UNSUPPORTED,
                _binding_issue(modality),
            )
        except TemporalAlignmentError as error:
            stream_results[modality] = _failed_core_result(
                item,
                descriptor,
                SynchronizationItemStatus.INVALID,
                error.issue,
            )

    _finish_gaze_result(
        sync_input=sync_input,
        window=window,
        works=works,
        stream_results=stream_results,
    )
    reference_result, reference_work = _align_reference(
        sync_input,
        catalog,
        window,
        policy,
        clock_issues.get("task_reference"),
    )
    try:
        annotations, annotation_result = align_annotations(sync_input, window)
    except AnnotationAlignmentError as error:
        annotations = None
        annotation_result = AnnotationSynchronizationResult(
            synchronization_status=(
                SynchronizationItemStatus.UNSUPPORTED
                if error.issue.error_code == "ANNOTATION_SCHEMA_UNSUPPORTED"
                else SynchronizationItemStatus.INVALID
            ),
            revision=sync_input.loaded_manifest.manifest.annotations.revision,
            issues=(error.issue,),
        )
    return _finalize_valid_input(
        sync_input=sync_input,
        policy=policy,
        policy_fingerprint=policy_fingerprint,
        catalog_fingerprint=catalog_fingerprint,
        window=window,
        stream_results=stream_results,
        works=works,
        reference_result=reference_result,
        reference_work=reference_work,
        annotations=annotations,
        annotation_result=annotation_result,
        global_issues=global_issues,
    )


def _validate_ready_clock_inventory(
    sync_input: SynchronizationInput,
    policy: SynchronizationPolicy,
) -> dict[str, DomainErrorData]:
    inventory: list[tuple[str, StreamDescriptor]] = []
    manifest = sync_input.loaded_manifest.manifest
    for modality in _CORE_ORDER:
        if sync_input.readiness_report.stream_results[modality].readiness is StreamReadiness.READY:
            inventory.append((modality, manifest.streams[modality]))
    reference = manifest.task.reference
    reference_readiness = sync_input.readiness_report.task_reference_result
    if (
        reference is not None
        and reference.source == "bundle"
        and reference_readiness is not None
        and reference_readiness.readiness is StreamReadiness.READY
    ):
        assert reference.stream_id is not None
        inventory.append(("task_reference", manifest.streams[reference.stream_id]))

    issues: dict[str, DomainErrorData] = {}
    for logical_id, descriptor in inventory:
        clock = descriptor.clock_sync
        try:
            if clock is None:
                raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
            validate_clock_declaration(clock, policy)
            stream = (
                sync_input.prepared_session.task_reference
                if logical_id == "task_reference"
                else sync_input.prepared_session.streams.get(logical_id)
            )
            if stream is None or stream.clock_id != descriptor.clock_id:
                raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
        except ValueError:
            issues[logical_id] = _clock_issue(logical_id)

    groups: dict[str, list[tuple[str, StreamDescriptor]]] = {}
    for logical_id, descriptor in inventory:
        groups.setdefault(descriptor.clock_id, []).append((logical_id, descriptor))
    for clock_id in sorted(groups):
        group = groups[clock_id]
        try:
            validate_same_clock_mappings(tuple(descriptor for _logical, descriptor in group))
        except ValueError:
            for logical_id, _descriptor in group:
                issues[logical_id] = _clock_issue(logical_id)
    return issues


def _profile_for_stream(
    catalog: TemporalBindingCatalog,
    stream: NormalizedStream,
) -> TemporalStreamProfile:
    profile = catalog.streams_by_schema.get(stream.schema_id)
    if profile is None:
        raise _MissingTemporalBinding
    source_roles = set(stream.tables) | set(stream.json_artifacts) | set(stream.file_artifacts)
    if set(profile.bindings_by_role) != source_roles:
        raise _MissingTemporalBinding
    primary_binding = profile.bindings_by_role.get(stream.primary_table_role)
    if (
        not isinstance(primary_binding, PointBinding)
        or primary_binding.source_timestamp_column != stream.source_timestamp_column
    ):
        raise _MissingTemporalBinding
    return profile


def _align_stream_work(
    *,
    logical_id: str,
    stream: NormalizedStream,
    descriptor: StreamDescriptor,
    profile: TemporalStreamProfile,
    window: SessionWindow,
    policy: SynchronizationPolicy,
    premapped_points: Mapping[str, pl.DataFrame] | None = None,
) -> _AlignedWork:
    clock = _required_clock(descriptor)
    aligned_tables: dict[str, pl.DataFrame] = {}
    artifacts: dict[str, TemporalArtifactMetrics] = {}
    time_parts: dict[str, bytes] = {}
    premapped = premapped_points or {}
    for binding in profile.bindings:
        role = binding.artifact_role
        if isinstance(binding, PointBinding):
            source = stream.tables.get(role)
            if source is None:
                raise _MissingTemporalBinding
            mapped = premapped.get(role)
            if mapped is None:
                mapped = map_point_artifact(source, binding, clock)
            aligned = apply_point_window(mapped, binding, window)
            aligned_tables[role] = aligned
            summary = _clock_summary(descriptor, declaration_consistent=True)
            artifacts[role] = compute_point_metrics(aligned, binding, summary, window, policy)
            _add_point_time_parts(time_parts, logical_id, role, aligned, binding)
        elif isinstance(binding, IntervalBinding):
            source = stream.tables.get(role)
            if source is None:
                raise _MissingTemporalBinding
            aligned = map_interval_artifact(source, binding, clock, window)
            aligned_tables[role] = aligned
            summary = _clock_summary(descriptor, declaration_consistent=True)
            artifacts[role] = compute_interval_metrics(aligned, binding, summary, window)
            _add_interval_time_parts(time_parts, logical_id, role, aligned, binding)
        elif isinstance(binding, InheritBinding):
            source = stream.tables.get(role)
            parent = aligned_tables.get(binding.parent_role)
            if source is None or parent is None:
                raise _MissingTemporalBinding
            aligned = inherit_point_time(source, parent, binding)
            aligned_tables[role] = aligned
            summary = _clock_summary(descriptor, declaration_consistent=True)
            artifacts[role] = compute_point_metrics(aligned, binding, summary, window, policy)
            _add_point_time_parts(time_parts, logical_id, role, aligned, binding)
        elif isinstance(binding, UntimedBinding):
            if role in stream.tables:
                aligned_tables[role] = preserve_untimed_artifact(stream.tables[role], binding)
            elif role in stream.json_artifacts:
                preserve_untimed_artifact(stream.json_artifacts[role], binding)
            elif role in stream.file_artifacts:
                preserve_untimed_artifact(stream.file_artifacts[role], binding)
            else:
                raise _MissingTemporalBinding
    view = AlignedStreamView(
        modality=logical_id,
        source_schema_id=stream.schema_id,
        aligned_schema_id=profile.aligned_stream_schema_id,
        clock_id=stream.clock_id,
        tables=aligned_tables,
        json_artifacts=stream.json_artifacts,
        file_artifacts=stream.file_artifacts,
        source_checksums=stream.source_checksums,
    )
    return _AlignedWork(view=view, artifacts=artifacts, time_parts=time_parts)


def _add_point_time_parts(
    destination: dict[str, bytes],
    logical_id: str,
    role: str,
    frame: pl.DataFrame,
    binding: PointBinding | InheritBinding,
) -> None:
    destination[f"{logical_id}/{role}/{binding.target_timestamp_column}"] = encode_int64_values(
        cast(list[int], frame[binding.target_timestamp_column].to_list())
    )
    destination[f"{logical_id}/{role}/{binding.in_session_column}"] = encode_boolean_values(
        cast(list[bool], frame[binding.in_session_column].to_list())
    )


def _add_interval_time_parts(
    destination: dict[str, bytes],
    logical_id: str,
    role: str,
    frame: pl.DataFrame,
    binding: IntervalBinding,
) -> None:
    for column in (binding.target_start_column, binding.target_end_column):
        destination[f"{logical_id}/{role}/{column}"] = encode_int64_values(
            cast(list[int], frame[column].to_list())
        )
    for column in (binding.overlaps_session_column, binding.fully_in_session_column):
        destination[f"{logical_id}/{role}/{column}"] = encode_boolean_values(
            cast(list[bool], frame[column].to_list())
        )


def _finish_gaze_result(
    *,
    sync_input: SynchronizationInput,
    window: SessionWindow,
    works: dict[str, _AlignedWork],
    stream_results: dict[str, StreamSynchronizationResult],
) -> None:
    gaze_work = works.get("G")
    if gaze_work is None:
        return
    gaze = gaze_work.view.tables["gaze_samples"]
    scene_work = works.get("I")
    scene = (
        scene_work.view.tables["frame_index"]
        if scene_work is not None
        else pl.DataFrame(
            schema={"frame_id": pl.UInt64, "t_ns": pl.Int64, "in_session": pl.Boolean}
        )
    )
    item = sync_input.readiness_report.stream_results["G"]
    descriptor = sync_input.loaded_manifest.manifest.streams["G"]
    try:
        metrics = validate_scene_gaze_time(scene, gaze, window)
    except TemporalAlignmentError as error:
        stream_results["G"] = _failed_core_result(
            item,
            descriptor,
            SynchronizationItemStatus.INVALID,
            error.issue,
        )
        works.pop("G", None)
        return
    if metrics.invalid_association_count:
        issue = _issue(
            "SCENE_GAZE_TIME_MISMATCH",
            "One or more in-session gaze samples fall outside their frame presentation interval.",
            field_or_path="streams.G",
            remediation="Correct scene-frame references or their declared clock mappings.",
        )
        stream_results["G"] = _failed_core_result(
            item,
            descriptor,
            SynchronizationItemStatus.INVALID,
            issue,
            scene_gaze_metrics=metrics,
        )
        works.pop("G", None)
        return
    stream_results["G"] = _aligned_core_result(
        item,
        descriptor,
        gaze_work,
        scene_gaze_metrics=metrics,
    )


def _align_reference(
    sync_input: SynchronizationInput,
    catalog: TemporalBindingCatalog,
    window: SessionWindow,
    policy: SynchronizationPolicy,
    clock_issue: DomainErrorData | None,
) -> tuple[TaskReferenceSynchronizationResult | None, _AlignedWork | None]:
    reference = sync_input.loaded_manifest.manifest.task.reference
    if reference is None:
        return None, None
    if reference.source == "model_bundle":
        return (
            TaskReferenceSynchronizationResult(
                reference_id=reference.reference_id,
                source="model_bundle",
                synchronization_status=(SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION),
            ),
            None,
        )
    item = sync_input.readiness_report.task_reference_result
    if item is None:
        raise ValueError("bundle reference is missing from the M2 readiness inventory")
    if item.readiness is not StreamReadiness.READY:
        return _unattempted_reference(sync_input), None
    descriptor = _reference_descriptor(sync_input)
    stream = sync_input.prepared_session.task_reference
    assert stream is not None
    if clock_issue is not None:
        return (
            _failed_reference(reference.reference_id, item, descriptor, clock_issue),
            None,
        )
    try:
        profile = _profile_for_stream(catalog, stream)
        work = _align_stream_work(
            logical_id="task_reference",
            stream=stream,
            descriptor=descriptor,
            profile=profile,
            window=window,
            policy=policy,
        )
    except _MissingTemporalBinding:
        return (
            _failed_reference(
                reference.reference_id,
                item,
                descriptor,
                _binding_issue("task_reference"),
                status=SynchronizationItemStatus.UNSUPPORTED,
            ),
            None,
        )
    except TemporalAlignmentError as error:
        return _failed_reference(reference.reference_id, item, descriptor, error.issue), None
    primary = work.artifacts.get("commanded_path")
    if primary is None or getattr(primary, "in_session_rows", 0) == 0:
        return (
            _failed_reference(
                reference.reference_id,
                item,
                descriptor,
                _issue(
                    "REFERENCE_ALIGNMENT_FAILED",
                    "Bundle task reference has no samples in the canonical session window.",
                    field_or_path="task.reference",
                    remediation="Provide a reference covering the master-clock X session window.",
                ),
            ),
            None,
        )
    result = TaskReferenceSynchronizationResult(
        reference_id=reference.reference_id,
        source="bundle",
        declared_status=item.declared_status,
        required_for_import=item.required_for_import,
        input_readiness=item.readiness,
        synchronization_status=SynchronizationItemStatus.ALIGNED,
        clock=_clock_summary(descriptor, declaration_consistent=True),
        source_schema_id=stream.schema_id,
        aligned_schema_id=work.view.aligned_schema_id,
        source_checksums=dict(stream.source_checksums),
        artifacts=work.artifacts,
        issues=tuple(_sort_issues(item.issues)),
    )
    return result, work


def _aligned_core_result(
    item: StreamReadinessResult,
    descriptor: StreamDescriptor,
    work: _AlignedWork,
    *,
    scene_gaze_metrics: SceneGazeMetrics | None = None,
) -> StreamSynchronizationResult:
    return StreamSynchronizationResult(
        modality=item.modality,
        declared_status=item.declared_status,
        required_for_import=item.required_for_import,
        input_readiness=item.readiness,
        synchronization_status=SynchronizationItemStatus.ALIGNED,
        clock=_clock_summary(descriptor, declaration_consistent=True),
        source_schema_id=work.view.source_schema_id,
        aligned_schema_id=work.view.aligned_schema_id,
        artifacts=work.artifacts,
        scene_gaze_metrics=scene_gaze_metrics,
        issues=tuple(_sort_issues(item.issues)),
    )


def _failed_core_result(
    item: StreamReadinessResult,
    descriptor: StreamDescriptor,
    status: SynchronizationItemStatus,
    issue: DomainErrorData,
    *,
    scene_gaze_metrics: SceneGazeMetrics | None = None,
) -> StreamSynchronizationResult:
    return StreamSynchronizationResult(
        modality=item.modality,
        declared_status=item.declared_status,
        required_for_import=item.required_for_import,
        input_readiness=item.readiness,
        synchronization_status=status,
        clock=_clock_summary(
            descriptor,
            declaration_consistent=(issue.error_code != "CLOCK_DECLARATION_INCONSISTENT"),
        ),
        source_schema_id=item.normalized_schema_id,
        scene_gaze_metrics=scene_gaze_metrics,
        issues=tuple(_sort_issues((*item.issues, issue))),
    )


def _failed_reference(
    reference_id: str,
    item: StreamReadinessResult,
    descriptor: StreamDescriptor,
    issue: DomainErrorData,
    *,
    status: SynchronizationItemStatus = SynchronizationItemStatus.INVALID,
) -> TaskReferenceSynchronizationResult:
    stream = item
    return TaskReferenceSynchronizationResult(
        reference_id=reference_id,
        source="bundle",
        declared_status=stream.declared_status,
        required_for_import=stream.required_for_import,
        input_readiness=stream.readiness,
        synchronization_status=status,
        clock=_clock_summary(
            descriptor,
            declaration_consistent=(issue.error_code != "CLOCK_DECLARATION_INCONSISTENT"),
        ),
        source_schema_id=stream.normalized_schema_id,
        source_checksums=dict(stream.source_checksums),
        issues=tuple(_sort_issues((*stream.issues, issue))),
    )


def _unattempted_reference(
    sync_input: SynchronizationInput,
) -> TaskReferenceSynchronizationResult | None:
    reference = sync_input.loaded_manifest.manifest.task.reference
    if reference is None:
        return None
    if reference.source == "model_bundle":
        return TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="model_bundle",
            synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
        )
    item = sync_input.readiness_report.task_reference_result
    if item is None:
        descriptor = _reference_descriptor(sync_input)
        return TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="bundle",
            declared_status=descriptor.status,
            required_for_import=descriptor.required_for_import,
            input_readiness=StreamReadiness.INVALID,
            synchronization_status=SynchronizationItemStatus.INVALID,
            issues=(
                _issue(
                    "SYNCHRONIZATION_INTERNAL_ERROR",
                    "Bundle task-reference readiness is missing from the M3 input snapshot.",
                    field_or_path="task.reference",
                    remediation="Rebuild the M2 readiness snapshot and retry synchronization.",
                ),
            ),
        )
    return TaskReferenceSynchronizationResult(
        reference_id=reference.reference_id,
        source="bundle",
        declared_status=item.declared_status,
        required_for_import=item.required_for_import,
        input_readiness=item.readiness,
        synchronization_status=_item_status_from_readiness(item.readiness, attempted=False),
        source_schema_id=item.normalized_schema_id,
        source_checksums=dict(item.source_checksums),
        issues=tuple(_sort_issues(item.issues)),
    )


def _not_attempted_annotations(
    sync_input: SynchronizationInput,
) -> AnnotationSynchronizationResult:
    return AnnotationSynchronizationResult(
        synchronization_status=SynchronizationItemStatus.NOT_ATTEMPTED,
        revision=sync_input.loaded_manifest.manifest.annotations.revision,
        issues=(
            _issue(
                "SYNCHRONIZATION_INPUT_BLOCKED",
                "Annotations were not attempted because the session window is unavailable.",
                field_or_path="annotations",
                remediation="Correct required synchronization inputs and retry.",
            ),
        ),
    )


def _finalize_valid_input(
    *,
    sync_input: SynchronizationInput,
    policy: SynchronizationPolicy,
    policy_fingerprint: str,
    catalog_fingerprint: str,
    window: SessionWindow | None,
    stream_results: dict[str, StreamSynchronizationResult],
    works: dict[str, _AlignedWork],
    reference_result: TaskReferenceSynchronizationResult | None,
    reference_work: _AlignedWork | None,
    annotations: AlignedAnnotations | None,
    annotation_result: AnnotationSynchronizationResult,
    global_issues: tuple[DomainErrorData, ...],
) -> SynchronizationOutcome:
    sorted_globals = tuple(_sort_issues(global_issues))
    disposition = _derive_disposition(
        session_window=window,
        streams=stream_results,
        task_reference=reference_result,
        annotations=annotation_result,
        global_issues=sorted_globals,
    )
    aligned_time_parts = {
        key: payload
        for modality in _CORE_ORDER
        if modality in works
        for key, payload in works[modality].time_parts.items()
    }
    if reference_work is not None:
        aligned_time_parts.update(reference_work.time_parts)
    annotation_payload = _annotations_payload(annotations)
    statuses = _status_payload(
        stream_results=stream_results,
        task_reference=reference_result,
        annotations=annotation_result,
        global_issues=sorted_globals,
        session_window=window,
        disposition=disposition,
        can_continue=disposition is not SynchronizationDisposition.BLOCKED,
    )
    synchronization_fingerprint = fingerprint_synchronization(
        source_snapshot_fingerprint=sync_input.readiness_report.source_snapshot_fingerprint,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        aligned_time_parts=aligned_time_parts,
        aligned_annotations_json=canonical_json_bytes(annotation_payload),
        statuses_and_issues_json=canonical_json_bytes(statuses),
    )
    report = SynchronizationReport(
        contract_version="0.1.0",
        validation_scope="native_rate_session_time_alignment_v1",
        session_id=sync_input.readiness_report.session_id,
        source_snapshot_fingerprint=sync_input.readiness_report.source_snapshot_fingerprint,
        source_classification=sync_input.readiness_report.source_classification,
        synthetic_provenance=sync_input.readiness_report.synthetic_provenance,
        policy=policy,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        session_window=window,
        disposition=disposition,
        can_continue_to_anchor_availability=(disposition is not SynchronizationDisposition.BLOCKED),
        formal_run_authorized=False,
        stream_results={modality: stream_results[modality] for modality in _CORE_ORDER},
        task_reference_result=reference_result,
        annotation_result=annotation_result,
        global_issues=sorted_globals,
        synchronization_fingerprint=synchronization_fingerprint,
    )
    aligned_session = None
    if disposition is not SynchronizationDisposition.BLOCKED:
        assert window is not None and annotations is not None
        aligned_session = AlignedSession(
            session_id=sync_input.readiness_report.session_id,
            window=window,
            streams={
                modality: works[modality].view for modality in _CORE_ORDER if modality in works
            },
            context=sync_input.prepared_session.context,
            annotations=annotations,
            task_reference=reference_work.view if reference_work is not None else None,
            source_snapshot_fingerprint=sync_input.readiness_report.source_snapshot_fingerprint,
            synchronization_fingerprint=synchronization_fingerprint,
        )
    return SynchronizationOutcome(report=report, aligned_session=aligned_session)


def _internal_failure_from_input(
    sync_input: SynchronizationInput,
    policy: SynchronizationPolicy,
) -> SynchronizationOutcome:
    issue = _issue(
        "SYNCHRONIZATION_INTERNAL_ERROR",
        "Native-rate synchronization failed inside a bounded backend operation.",
        field_or_path="synchronization",
        remediation="Review protected backend logs, repair the implementation, and retry.",
    )
    results = {
        modality: _unattempted_core_result(sync_input.readiness_report.stream_results[modality])
        for modality in _CORE_ORDER
    }
    annotations = AnnotationSynchronizationResult(
        synchronization_status=SynchronizationItemStatus.NOT_ATTEMPTED,
        revision=sync_input.loaded_manifest.manifest.annotations.revision,
        issues=(),
    )
    reference = _unattempted_reference(sync_input)
    global_issues = tuple(_sort_issues((*sync_input.readiness_report.global_issues, issue)))
    policy_fingerprint = _safe_policy_fingerprint(policy)
    catalog_fingerprint = _safe_catalog_fingerprint()
    emergency_status = _status_payload(
        stream_results=results,
        task_reference=reference,
        annotations=annotations,
        global_issues=global_issues,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue=False,
    )
    synchronization_fingerprint = _safe_synchronization_fingerprint(
        source_snapshot_fingerprint=(sync_input.readiness_report.source_snapshot_fingerprint),
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        statuses_and_issues_json=_independent_canonical_json_bytes(emergency_status),
    )
    report = SynchronizationReport(
        contract_version="0.1.0",
        validation_scope="native_rate_session_time_alignment_v1",
        session_id=sync_input.readiness_report.session_id,
        source_snapshot_fingerprint=sync_input.readiness_report.source_snapshot_fingerprint,
        source_classification=sync_input.readiness_report.source_classification,
        synthetic_provenance=sync_input.readiness_report.synthetic_provenance,
        policy=policy,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue_to_anchor_availability=False,
        formal_run_authorized=False,
        stream_results=results,
        task_reference_result=reference,
        annotation_result=annotations,
        global_issues=global_issues,
        synchronization_fingerprint=synchronization_fingerprint,
    )
    return SynchronizationOutcome(report=report, aligned_session=None)


def _internal_failure_from_readiness(
    loaded: LoadedManifest,
    readiness: IngestionReadinessReport,
    policy: SynchronizationPolicy,
) -> SynchronizationOutcome:
    issue = _issue(
        "SYNCHRONIZATION_INTERNAL_ERROR",
        "Native-rate synchronization failed inside a bounded backend operation.",
        field_or_path="synchronization",
        remediation="Review protected backend logs, repair the implementation, and retry.",
    )
    results = {
        modality: _unattempted_core_result(readiness.stream_results[modality])
        for modality in _CORE_ORDER
    }
    reference = loaded.manifest.task.reference
    reference_result: TaskReferenceSynchronizationResult | None = None
    if reference is not None and reference.source == "model_bundle":
        reference_result = TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="model_bundle",
            synchronization_status=(SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION),
        )
    elif reference is not None and readiness.task_reference_result is not None:
        item = readiness.task_reference_result
        reference_result = TaskReferenceSynchronizationResult(
            reference_id=reference.reference_id,
            source="bundle",
            declared_status=item.declared_status,
            required_for_import=item.required_for_import,
            input_readiness=item.readiness,
            synchronization_status=_item_status_from_readiness(
                item.readiness,
                attempted=False,
            ),
            source_schema_id=item.normalized_schema_id,
            source_checksums=dict(item.source_checksums),
            issues=tuple(_sort_issues(item.issues)),
        )
    annotations = AnnotationSynchronizationResult(
        synchronization_status=SynchronizationItemStatus.NOT_ATTEMPTED,
        revision=loaded.manifest.annotations.revision,
        issues=(),
    )
    global_issues = tuple(_sort_issues((*readiness.global_issues, issue)))
    policy_fingerprint = _safe_policy_fingerprint(policy)
    catalog_fingerprint = _safe_catalog_fingerprint()
    status_payload = _status_payload(
        stream_results=results,
        task_reference=reference_result,
        annotations=annotations,
        global_issues=global_issues,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue=False,
    )
    synchronization_fingerprint = _safe_synchronization_fingerprint(
        source_snapshot_fingerprint=readiness.source_snapshot_fingerprint,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        statuses_and_issues_json=_independent_canonical_json_bytes(status_payload),
    )
    report = SynchronizationReport(
        contract_version="0.1.0",
        validation_scope="native_rate_session_time_alignment_v1",
        session_id=readiness.session_id,
        source_snapshot_fingerprint=readiness.source_snapshot_fingerprint,
        source_classification=readiness.source_classification,
        synthetic_provenance=readiness.synthetic_provenance,
        policy=policy,
        policy_fingerprint=policy_fingerprint,
        binding_catalog_fingerprint=catalog_fingerprint,
        session_window=None,
        disposition=SynchronizationDisposition.BLOCKED,
        can_continue_to_anchor_availability=False,
        formal_run_authorized=False,
        stream_results=results,
        task_reference_result=reference_result,
        annotation_result=annotations,
        global_issues=global_issues,
        synchronization_fingerprint=synchronization_fingerprint,
    )
    return SynchronizationOutcome(report=report, aligned_session=None)


def _emergency_digest(tag: str, *parts: str) -> str:
    """Return a deterministic digest without depending on M3 fingerprint helpers."""

    hasher = hashlib.sha256()
    for value in (tag, *parts):
        payload = value.encode("utf-8")
        hasher.update(len(payload).to_bytes(8, "big", signed=False))
        hasher.update(payload)
    return hasher.hexdigest()


def _independent_canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _independent_hash_part(
    hasher: HashWriter,
    *,
    tag: str,
    payload: bytes,
) -> None:
    tag_bytes = tag.encode("utf-8")
    hasher.update(len(tag_bytes).to_bytes(4, "big", signed=False))
    hasher.update(tag_bytes)
    hasher.update(len(payload).to_bytes(8, "big", signed=False))
    hasher.update(payload)


def _safe_policy_fingerprint(policy: SynchronizationPolicy) -> str:
    try:
        return fingerprint_policy(policy)
    except Exception:
        try:
            hasher = hashlib.sha256()
            _independent_hash_part(
                hasher,
                tag="synchronization-policy",
                payload=_independent_canonical_json_bytes(policy.model_dump(mode="json")),
            )
            return hasher.hexdigest()
        except Exception:
            return _emergency_digest("policy-unavailable", policy.model_dump_json())


def _safe_catalog_fingerprint() -> str:
    try:
        return builtin_temporal_catalog_fingerprint()
    except Exception:
        try:
            payload = (
                files("pilot_assessment.synchronization.profile_data")
                .joinpath("m3-temporal-bindings-0.1.json")
                .read_bytes()
            )
            return hashlib.sha256(payload).hexdigest()
        except Exception:
            return _emergency_digest(
                "catalog-unavailable",
                "m3-temporal-bindings-0.1.json",
            )


def _safe_synchronization_fingerprint(
    *,
    source_snapshot_fingerprint: str,
    policy_fingerprint: str,
    binding_catalog_fingerprint: str,
    statuses_and_issues_json: bytes,
) -> str:
    try:
        return fingerprint_synchronization(
            source_snapshot_fingerprint=source_snapshot_fingerprint,
            policy_fingerprint=policy_fingerprint,
            binding_catalog_fingerprint=binding_catalog_fingerprint,
            aligned_time_parts={},
            aligned_annotations_json=b"null",
            statuses_and_issues_json=statuses_and_issues_json,
        )
    except Exception:
        try:
            hasher = hashlib.sha256()
            for tag, payload in (
                (
                    "source-snapshot-fingerprint",
                    source_snapshot_fingerprint.encode("ascii"),
                ),
                ("policy-fingerprint", policy_fingerprint.encode("ascii")),
                (
                    "binding-catalog-fingerprint",
                    binding_catalog_fingerprint.encode("ascii"),
                ),
                ("aligned-annotations", b"null"),
                ("statuses-and-issues", statuses_and_issues_json),
            ):
                _independent_hash_part(hasher, tag=tag, payload=payload)
            return hasher.hexdigest()
        except Exception:
            return _emergency_digest(
                "synchronization-unavailable",
                source_snapshot_fingerprint,
                policy_fingerprint,
                binding_catalog_fingerprint,
                statuses_and_issues_json.hex(),
            )


def _annotations_payload(annotations: AlignedAnnotations | None) -> object:
    if annotations is None:
        return None
    return {
        "revision": annotations.revision,
        "phases": [item.model_dump(mode="json") for item in annotations.phases],
        "events": [item.model_dump(mode="json") for item in annotations.events],
        "baseline_intervals": [
            item.model_dump(mode="json") for item in annotations.baseline_intervals
        ],
        "source_schema_ids": dict(annotations.source_schema_ids),
        "synthetic_semantics_unvalidated": annotations.synthetic_semantics_unvalidated,
    }


def _required_clock(descriptor: StreamDescriptor) -> ClockSync:
    if descriptor.clock_sync is None:
        raise TemporalAlignmentError(_clock_issue(descriptor.modality))
    return descriptor.clock_sync


def _clock_summary(
    descriptor: StreamDescriptor,
    *,
    declaration_consistent: bool,
) -> ClockMappingSummary:
    clock = descriptor.clock_sync
    if clock is None:
        raise ValueError("present descriptor has no clock")
    return ClockMappingSummary(
        clock_id=descriptor.clock_id,
        method=clock.method,
        scale=clock.scale,
        offset_ns=clock.offset_ns,
        drift_ppm=clock.drift_ppm,
        residual_rms_ms=clock.residual_rms_ms,
        residual_max_ms=clock.residual_max_ms,
        declaration_consistent=declaration_consistent,
    )


def _reference_descriptor(sync_input: SynchronizationInput) -> StreamDescriptor:
    reference = sync_input.loaded_manifest.manifest.task.reference
    assert reference is not None and reference.source == "bundle" and reference.stream_id
    return sync_input.loaded_manifest.manifest.streams[reference.stream_id]


def _clock_issue(logical_id: str) -> DomainErrorData:
    return _issue(
        "CLOCK_DECLARATION_INCONSISTENT",
        "A ready input has an inconsistent clock mapping declaration.",
        field_or_path=f"streams.{logical_id}.clock_sync",
        remediation="Use one method/scale/offset/drift mapping per ready clock ID.",
    )


def _binding_issue(logical_id: str) -> DomainErrorData:
    return _issue(
        "TEMPORAL_BINDING_NOT_FOUND",
        "No trusted temporal binding covers this ready schema and artifact inventory.",
        field_or_path=f"streams.{logical_id}.schema_id",
        remediation="Install the approved binding catalog or correct the source schema.",
    )


def _issue(
    error_code: str,
    message: str,
    *,
    field_or_path: str,
    remediation: str,
) -> DomainErrorData:
    return DomainErrorData(
        error_code=error_code,
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message=message,
        field_or_path=field_or_path,
        remediation=remediation,
    )


__all__ = [
    "synchronize_bundle",
    "synchronize_session",
]
