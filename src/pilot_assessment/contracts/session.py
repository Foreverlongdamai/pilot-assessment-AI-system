"""Versioned contracts for a multimodal assessment session bundle."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    FiniteFloat,
    Int64,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)

SUPPORTED_BUNDLE_SCHEMA_MAJOR = 0
BUNDLE_SCHEMA_VERSION_PATTERN = r"^0\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
BundleSchemaVersion = Annotated[
    str,
    StringConstraints(pattern=BUNDLE_SCHEMA_VERSION_PATTERN),
]
NonEmptyString = Annotated[str, Field(min_length=1, max_length=512)]


class CoreModality(StrEnum):
    """Modalities that every v0.x manifest must explicitly describe."""

    X = "X"
    U = "U"
    SCENE = "I"
    G = "G"
    EEG = "EEG"
    ECG = "ECG"
    PILOT_CAMERA = "pilot_camera"


CORE_MODALITIES = frozenset(modality.value for modality in CoreModality)
BIOMETRIC_MODALITIES = frozenset({"G", "EEG", "ECG", "pilot_camera"})


class StreamStatus(StrEnum):
    PRESENT = "present"
    EXPORT_PENDING = "export_pending"
    MISSING = "missing"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class ClockSync(StrictContractModel):
    method: StableId
    scale: PositiveFiniteFloat
    offset_ns: Int64
    drift_ppm: FiniteFloat
    residual_rms_ms: NonNegativeFiniteFloat
    residual_max_ms: NonNegativeFiniteFloat
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class QualitySummary(StrictContractModel):
    coverage_ratio: UnitInterval | None = None
    gap_count: NonNegativeInt | None = None
    validity_ratio: UnitInterval | None = None
    artifact_ratio: UnitInterval | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class StreamDescriptor(StrictContractModel):
    modality: StableId
    status: StreamStatus
    required_for_import: StrictBool
    paths: list[BundleRelativePath]
    format: NonEmptyString
    schema_id: StableId
    clock_id: StableId
    clock_sync: ClockSync | None
    sample_rate_hz: PositiveFiniteFloat | None
    units: NonEmptyString | dict[str, NonEmptyString]
    quality_summary: QualitySummary | None
    checksums: dict[BundleRelativePath, Sha256Digest]
    metadata: dict[str, JsonValue]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_and_files(self) -> Self:
        normalized_paths = [path.casefold() for path in self.paths]
        if len(normalized_paths) != len(set(normalized_paths)):
            raise ValueError("stream paths must be unique under Windows case folding")

        if self.status in {StreamStatus.PRESENT, StreamStatus.INVALID}:
            if not self.paths:
                raise ValueError(f"{self.status.value} streams require at least one path")
            if set(self.paths) != set(self.checksums):
                raise ValueError(
                    f"{self.status.value} stream checksums must match paths exactly"
                )
            if self.status is StreamStatus.PRESENT and self.clock_sync is None:
                raise ValueError("present streams require a clock_sync mapping")
        else:
            if self.paths or self.checksums:
                raise ValueError(
                    f"{self.status.value} streams must not claim exported files"
                )
            if self.quality_summary is not None:
                raise ValueError(
                    f"{self.status.value} streams must not claim a quality summary"
                )
            if (
                self.status in {StreamStatus.MISSING, StreamStatus.NOT_APPLICABLE}
                and self.clock_sync is not None
            ):
                raise ValueError(
                    f"{self.status.value} streams must not claim clock sync"
                )
            if (
                self.status is StreamStatus.NOT_APPLICABLE
                and self.required_for_import
            ):
                raise ValueError("not_applicable streams cannot be required for import")
        return self


class SourceSession(StrictContractModel):
    system: StableId
    source_id: StableId
    campaign: StableId
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Participant(StrictContractModel):
    pseudonymous_id: StableId
    research_attributes: dict[str, JsonValue] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class TaskReference(StrictContractModel):
    source: Literal["bundle", "model_bundle"]
    reference_id: StableId
    stream_id: StableId | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.source == "bundle" and self.stream_id is None:
            raise ValueError("bundle references require stream_id")
        if self.source == "model_bundle" and self.stream_id is not None:
            raise ValueError("model_bundle references must not declare stream_id")
        return self


class TaskDefinition(StrictContractModel):
    task_profile_id: StableId
    scenario_id: StableId
    expected_phases: list[StableId]
    reference: TaskReference | None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class SessionTimebase(StrictContractModel):
    origin: StableId
    unit: Literal["ns"]
    master_clock_id: StableId
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class AnnotationReferences(StrictContractModel):
    revision: StableId
    phases: BundleRelativePath
    events: BundleRelativePath
    baseline_intervals: BundleRelativePath
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class IntegrityDefinition(StrictContractModel):
    algorithm: Literal["sha256"]
    manifest_canonicalization: StableId
    checksum_file: BundleRelativePath
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class PrivacyDefinition(StrictContractModel):
    classification: StableId
    direct_identifiers_removed: StrictBool
    contains_biometric_data: StrictBool
    biometric_modalities_export_pending: list[StableId]
    permitted_use: StableId
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("biometric_modalities_export_pending")
    @classmethod
    def require_unique_pending_modalities(cls, value: list[StableId]) -> list[StableId]:
        if len(value) != len(set(value)):
            raise ValueError("pending biometric modalities must be unique")
        return value


class SessionManifest(StrictContractModel):
    bundle_schema_version: BundleSchemaVersion
    session_id: StableId
    created_at: AwareDatetime
    source_session: SourceSession
    participant: Participant
    task: TaskDefinition
    session_timebase: SessionTimebase
    streams: dict[StableId, StreamDescriptor]
    annotations: AnnotationReferences
    integrity: IntegrityDefinition
    privacy: PrivacyDefinition
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("created_at", mode="before")
    @classmethod
    def require_rfc3339_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("created_at must be an RFC 3339 string with timezone")
        return value

    @model_validator(mode="after")
    def validate_stream_inventory(self) -> Self:
        stream_ids = set(self.streams)
        missing = CORE_MODALITIES - stream_ids
        if missing:
            raise ValueError(f"missing core stream descriptors: {sorted(missing)}")
        if "P" in stream_ids:
            raise ValueError("P is a physiology concept group, not a stream modality")
        mismatched = [
            stream_id
            for stream_id, descriptor in self.streams.items()
            if stream_id != descriptor.modality
        ]
        if mismatched:
            raise ValueError(f"stream keys must match descriptor modality: {mismatched}")

        reference = self.task.reference
        if reference is not None and reference.source == "bundle":
            assert reference.stream_id is not None
            descriptor = self.streams.get(reference.stream_id)
            if descriptor is None:
                raise ValueError("bundle reference stream_id does not exist")
            if descriptor.modality != "task_reference":
                raise ValueError(
                    "bundle reference stream_id must resolve to task_reference"
                )
            outside_references = [
                path for path in descriptor.paths if not path.startswith("references/")
            ]
            if outside_references:
                raise ValueError(
                    "bundle task reference paths must stay below references/"
                )

        expected_pending = {
            modality
            for modality in BIOMETRIC_MODALITIES
            if self.streams[modality].status is StreamStatus.EXPORT_PENDING
        }
        declared_pending = set(self.privacy.biometric_modalities_export_pending)
        if declared_pending != expected_pending:
            raise ValueError(
                "pending biometric modalities must exactly match export_pending streams"
            )

        synthetic = self.privacy.classification == "synthetic-test-data"
        exported_biometrics = any(
            self.streams[modality].status
            in {StreamStatus.PRESENT, StreamStatus.INVALID}
            for modality in BIOMETRIC_MODALITIES
        )
        if synthetic:
            if self.privacy.contains_biometric_data:
                raise ValueError("synthetic test data cannot claim real biometric data")
            if declared_pending:
                raise ValueError(
                    "synthetic test data cannot claim pending real biometric modalities"
                )
        elif exported_biometrics and not self.privacy.contains_biometric_data:
            raise ValueError(
                "non-synthetic biometric artifacts require contains_biometric_data=true"
            )
        return self


__all__ = [
    "CORE_MODALITIES",
    "BUNDLE_SCHEMA_VERSION_PATTERN",
    "BundleSchemaVersion",
    "AnnotationReferences",
    "ClockSync",
    "CoreModality",
    "IntegrityDefinition",
    "Participant",
    "PrivacyDefinition",
    "QualitySummary",
    "SessionManifest",
    "SessionTimebase",
    "SourceSession",
    "StreamDescriptor",
    "StreamStatus",
    "TaskDefinition",
    "TaskReference",
]
