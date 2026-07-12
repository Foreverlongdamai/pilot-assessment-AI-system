"""Public contracts for inspect-only multimodal ingestion readiness."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, JsonValue, StrictBool, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
)
from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.session import (
    CORE_MODALITIES,
    BundleSchemaVersion,
    StreamStatus,
    SyntheticSourceProvenance,
)


class StreamReadiness(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


class ReadinessDisposition(StrEnum):
    READY = "ready"
    READY_PARTIAL = "ready_partial"
    BLOCKED = "blocked"


class StreamReadinessResult(StrictContractModel):
    modality: StableId
    declared_status: StreamStatus
    required_for_import: StrictBool
    readiness: StreamReadiness
    adapter_id: StableId | None = None
    adapter_version: StableId | None = None
    source_paths: tuple[BundleRelativePath, ...]
    source_checksums: dict[BundleRelativePath, Sha256Digest]
    normalized_schema_id: StableId | None = None
    row_count: NonNegativeInt | None = None
    artifact_row_counts: dict[StableId, NonNegativeInt] = Field(default_factory=dict)
    source_time_start_s: NonNegativeFiniteFloat | None = None
    source_time_end_s: NonNegativeFiniteFloat | None = None
    observed_sample_rate_hz: PositiveFiniteFloat | None = None
    canonical_fields: tuple[StableId, ...] = ()
    units: dict[str, str] = Field(default_factory=dict)
    quality_summary: dict[str, JsonValue] = Field(default_factory=dict)
    assumptions: tuple[StableId, ...] = ()
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_readiness_payload(self) -> Self:
        if self.readiness is StreamReadiness.READY:
            if self.adapter_id is None or self.adapter_version is None:
                raise ValueError("ready results require adapter identity")
            if self.row_count is None or self.normalized_schema_id is None:
                raise ValueError("ready results require normalized content summary")

        if self.readiness in {
            StreamReadiness.UNAVAILABLE,
            StreamReadiness.UNSUPPORTED,
            StreamReadiness.NOT_APPLICABLE,
        }:
            claimed = (
                self.adapter_id,
                self.adapter_version,
                self.normalized_schema_id,
                self.row_count,
                self.source_time_start_s,
                self.source_time_end_s,
                self.observed_sample_rate_hz,
            )
            if any(value is not None for value in claimed) or self.artifact_row_counts:
                raise ValueError("uninspected results must not claim normalized content")
        return self


class IngestionReadinessReport(StrictContractModel):
    contract_version: Literal["0.1.0"]
    validation_scope: Literal["inspect_only_ingestion_content_v1"]
    session_id: StableId
    manifest_version: BundleSchemaVersion
    source_classification: StableId
    synthetic_provenance: SyntheticSourceProvenance | None
    disposition: ReadinessDisposition
    can_continue_to_synchronization: StrictBool
    formal_run_authorized: Literal[False]
    stream_results: dict[StableId, StreamReadinessResult]
    task_reference_result: StreamReadinessResult | None
    global_issues: tuple[DomainErrorData, ...] = ()
    deferred_checks: tuple[StableId, ...]
    source_snapshot_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        is_synthetic = self.source_classification == "synthetic-test-data"
        if is_synthetic != (self.synthetic_provenance is not None):
            raise ValueError(
                "synthetic-test-data classification and provenance must appear together"
            )
        if set(self.stream_results) != set(CORE_MODALITIES):
            raise ValueError("readiness report requires exactly seven core modalities")
        if any(key != result.modality for key, result in self.stream_results.items()):
            raise ValueError("stream result keys must match modality")
        if (
            self.task_reference_result is not None
            and self.task_reference_result.modality != "task_reference"
        ):
            raise ValueError("task_reference_result must describe task_reference")

        results = list(self.stream_results.values())
        if self.task_reference_result is not None:
            results.append(self.task_reference_result)
        blocked = any(
            result.required_for_import and result.readiness is not StreamReadiness.READY
            for result in results
        )
        degraded = any(
            result.readiness
            in {
                StreamReadiness.UNAVAILABLE,
                StreamReadiness.INVALID,
                StreamReadiness.UNSUPPORTED,
            }
            for result in self.stream_results.values()
        )
        if self.task_reference_result is not None:
            degraded = degraded or self.task_reference_result.readiness is not StreamReadiness.READY

        expected = (
            ReadinessDisposition.BLOCKED
            if blocked
            else ReadinessDisposition.READY_PARTIAL
            if degraded
            else ReadinessDisposition.READY
        )
        if self.disposition is not expected:
            raise ValueError("disposition must match stream readiness")
        if self.can_continue_to_synchronization == blocked:
            raise ValueError("blocked reports cannot continue to synchronization")
        return self


__all__ = [
    "IngestionReadinessReport",
    "ReadinessDisposition",
    "StreamReadiness",
    "StreamReadinessResult",
    "SyntheticSourceProvenance",
]
