"""Immutable in-process inputs and native-rate aligned session views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.ingestion import (
    IngestionReadinessReport,
    ReadinessDisposition,
    StreamReadiness,
    StreamReadinessResult,
)
from pilot_assessment.contracts.session import CORE_MODALITIES, StreamDescriptor
from pilot_assessment.contracts.synchronization import (
    BaselineInterval,
    EventMarker,
    PhaseInterval,
    SessionWindow,
    SynchronizationReport,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest
from pilot_assessment.ingestion.models import NormalizedStream, PreparedSession
from pilot_assessment.ingestion.readiness import source_snapshot_fingerprint


def _freeze_tables(values: Mapping[str, pl.DataFrame]) -> Mapping[str, pl.DataFrame]:
    return MappingProxyType(dict(values))


def _freeze_json_artifacts(
    values: Mapping[str, Mapping[str, JsonValue]],
) -> Mapping[str, Mapping[str, JsonValue]]:
    return MappingProxyType(
        {role: _freeze_json_mapping(payload) for role, payload in values.items()}
    )


def _freeze_file_artifacts(
    values: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType({role: tuple(paths) for role, paths in values.items()})


def _freeze_strings(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values))


def _freeze_json_mapping(values: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return MappingProxyType({key: _freeze_json_value(value) for key, value in values.items()})


def _freeze_json_value(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings")
            frozen[key] = _freeze_json_value(item)
        return cast(JsonValue, MappingProxyType(frozen))
    if isinstance(value, (list, tuple)):
        return cast(JsonValue, tuple(_freeze_json_value(item) for item in value))
    if value is None or type(value) in {str, bool, int, float}:
        return cast(JsonValue, value)
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _validate_ready_stream_snapshot(
    *,
    modality: str,
    stream: NormalizedStream,
    result: StreamReadinessResult,
    descriptor: StreamDescriptor,
    verified_digests: Mapping[str, str],
) -> None:
    if stream.clock_id != descriptor.clock_id:
        raise ValueError("prepared stream clock must match loaded manifest descriptor")

    descriptor_paths = tuple(descriptor.paths)
    try:
        loaded_checksums = {path: verified_digests[path] for path in descriptor_paths}
    except KeyError as error:
        raise ValueError(
            "prepared session and report ready inventory source identity must match "
            "loaded manifest verified files"
        ) from error
    if (
        tuple(stream.source_paths) != descriptor_paths
        or result.source_paths != descriptor_paths
        or dict(stream.source_checksums) != loaded_checksums
        or result.source_checksums != loaded_checksums
    ):
        raise ValueError(
            "prepared session and report ready inventory source identity must match "
            "loaded manifest snapshot"
        )

    if stream.schema_id != result.normalized_schema_id:
        raise ValueError("prepared session and report ready inventory schemas must match")
    if (
        tuple(stream.source_paths) != result.source_paths
        or dict(stream.source_checksums) != result.source_checksums
    ):
        raise ValueError("prepared session and report ready inventory source identity must match")
    if stream.primary_table.height != result.row_count:
        raise ValueError("prepared session and report ready inventory row counts must match")
    if tuple(stream.primary_table.columns) != result.canonical_fields:
        raise ValueError("prepared session and report ready inventory columns must match")

    actual_counts = {role: table.height for role, table in stream.tables.items()}
    reported_counts = dict(result.artifact_row_counts)
    if actual_counts == reported_counts:
        return

    # M2 freezes shared physical X/U CSV inspection under ``simulator_csv`` while
    # PreparedSession exposes its two normalized logical views under ``samples``.
    # This is one exact physical-to-logical role mapping, not heuristic fallback.
    xu_schema = {
        "X": "flight-state-normalized-v0.1",
        "U": "control-input-normalized-v0.1",
    }
    compatible_shared_csv = (
        modality in xu_schema
        and stream.schema_id == xu_schema[modality]
        and set(stream.tables) == {"samples"}
        and set(reported_counts) == {"simulator_csv"}
        and actual_counts["samples"] == reported_counts["simulator_csv"]
    )
    if not compatible_shared_csv:
        raise ValueError("prepared session and report ready inventory artifact counts must match")


@dataclass(frozen=True, slots=True)
class SynchronizationInput:
    """One exact non-blocked M1/M2 snapshot accepted by M3."""

    loaded_manifest: LoadedManifest
    readiness_report: IngestionReadinessReport
    prepared_session: PreparedSession

    def __post_init__(self) -> None:
        report = self.readiness_report
        if (
            report.disposition is ReadinessDisposition.BLOCKED
            or not report.can_continue_to_synchronization
        ):
            raise ValueError("blocked readiness cannot construct SynchronizationInput")
        if report.session_id != self.loaded_manifest.manifest.session_id:
            raise ValueError("loaded manifest and readiness report session IDs must match")
        if report.source_snapshot_fingerprint != source_snapshot_fingerprint(self.loaded_manifest):
            raise ValueError("readiness report source snapshot fingerprint does not match")

        ready_results = {
            modality: result
            for modality, result in report.stream_results.items()
            if result.readiness is StreamReadiness.READY
        }
        if set(self.prepared_session.streams) != set(ready_results):
            raise ValueError("prepared session and report ready inventory must match exactly")
        for modality, stream in self.prepared_session.streams.items():
            _validate_ready_stream_snapshot(
                modality=modality,
                stream=stream,
                result=ready_results[modality],
                descriptor=self.loaded_manifest.manifest.streams[modality],
                verified_digests=self.loaded_manifest.verified_digests,
            )

        reference_result = report.task_reference_result
        reference_is_ready = (
            reference_result is not None and reference_result.readiness is StreamReadiness.READY
        )
        prepared_reference = self.prepared_session.task_reference
        if reference_is_ready != (prepared_reference is not None):
            raise ValueError("prepared task reference and report ready inventory must match")
        if reference_is_ready and prepared_reference is not None and reference_result is not None:
            reference_descriptor = self.loaded_manifest.manifest.streams.get("task_reference")
            if reference_descriptor is None:
                raise ValueError(
                    "prepared task reference and report ready inventory must match "
                    "loaded manifest descriptor"
                )
            _validate_ready_stream_snapshot(
                modality="task_reference",
                stream=prepared_reference,
                result=reference_result,
                descriptor=reference_descriptor,
                verified_digests=self.loaded_manifest.verified_digests,
            )


@dataclass(frozen=True, slots=True)
class AlignedStreamView:
    """Read-only artifact inventory whose DataFrames retain object identity."""

    modality: str
    source_schema_id: str
    aligned_schema_id: str
    clock_id: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", _freeze_tables(self.tables))
        object.__setattr__(self, "json_artifacts", _freeze_json_artifacts(self.json_artifacts))
        object.__setattr__(self, "file_artifacts", _freeze_file_artifacts(self.file_artifacts))
        object.__setattr__(self, "source_checksums", _freeze_strings(self.source_checksums))


@dataclass(frozen=True, slots=True)
class AlignedAnnotations:
    revision: str
    phases: tuple[PhaseInterval, ...]
    events: tuple[EventMarker, ...]
    baseline_intervals: tuple[BaselineInterval, ...]
    source_schema_ids: Mapping[str, str]
    synthetic_semantics_unvalidated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "phases", tuple(self.phases))
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "baseline_intervals", tuple(self.baseline_intervals))
        object.__setattr__(self, "source_schema_ids", _freeze_strings(self.source_schema_ids))


@dataclass(frozen=True, slots=True)
class AlignedSession:
    session_id: str
    window: SessionWindow
    streams: Mapping[str, AlignedStreamView]
    context: Mapping[str, JsonValue]
    annotations: AlignedAnnotations
    task_reference: AlignedStreamView | None
    source_snapshot_fingerprint: str
    synchronization_fingerprint: str

    def __post_init__(self) -> None:
        invalid_keys = set(self.streams) - set(CORE_MODALITIES)
        if "task_reference" in invalid_keys:
            raise ValueError("task_reference must use the dedicated task_reference field")
        if invalid_keys:
            raise ValueError(f"aligned session contains non-core streams: {sorted(invalid_keys)}")
        mismatched = [
            stream_id for stream_id, stream in self.streams.items() if stream_id != stream.modality
        ]
        if mismatched:
            raise ValueError(f"aligned stream keys must match modality: {sorted(mismatched)}")
        if self.task_reference is not None and self.task_reference.modality != "task_reference":
            raise ValueError("task_reference must have modality 'task_reference'")
        object.__setattr__(self, "streams", MappingProxyType(dict(self.streams)))
        object.__setattr__(self, "context", _freeze_json_mapping(self.context))


@dataclass(frozen=True, slots=True)
class SynchronizationOutcome:
    report: SynchronizationReport
    aligned_session: AlignedSession | None


__all__ = [
    "AlignedAnnotations",
    "AlignedSession",
    "AlignedStreamView",
    "SynchronizationInput",
    "SynchronizationOutcome",
]
