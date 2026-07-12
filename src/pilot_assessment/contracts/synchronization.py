"""Public contracts for M3 native-rate session-time synchronization."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
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
    NonNegativeInt64,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.ingestion import StreamReadiness, SyntheticSourceProvenance
from pilot_assessment.contracts.session import CORE_MODALITIES, StreamStatus

NonEmptyString = Annotated[str, StringConstraints(min_length=1, max_length=512)]
BLOCKING_SYNCHRONIZATION_ERROR_CODES = frozenset(
    {
        "SYNCHRONIZATION_INPUT_BLOCKED",
        "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        "SYNCHRONIZATION_INTERNAL_ERROR",
    }
)


class SynchronizationDisposition(StrEnum):
    READY = "ready"
    READY_PARTIAL = "ready_partial"
    BLOCKED = "blocked"


class SynchronizationItemStatus(StrEnum):
    ALIGNED = "aligned"
    NOT_ATTEMPTED = "not_attempted"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"
    DEFERRED_MODEL_BUNDLE_RESOLUTION = "deferred_model_bundle_resolution"


class SessionWindow(StrictContractModel):
    start_t_ns: Literal[0] = 0
    end_t_ns: NonNegativeInt64
    source: Literal["master-clock-x-mapped-coverage-v1"]

    @field_validator("start_t_ns", mode="before")
    @classmethod
    def require_strict_integer_zero(cls, value: object) -> object:
        if value.__class__ is not int:
            raise ValueError("start_t_ns must be an integer zero")
        return value

    @model_validator(mode="after")
    def require_positive_end(self) -> Self:
        if self.end_t_ns <= 0:
            raise ValueError("session end must be positive")
        return self


class SynchronizationPolicy(StrictContractModel):
    contract_version: Literal["0.1.0"] = "0.1.0"
    policy_id: Literal["native-alignment-engineering-v0.1"] = "native-alignment-engineering-v0.1"
    # Float Literal is intentionally used as a Pydantic runtime constant even though
    # the Python typing specification limits Literal to a narrower scalar set.
    gap_detection_multiplier: Literal[5.0] = 5.0  # ty: ignore[invalid-type-form]
    clock_consistency_tolerance_ppm: Literal[0.000001] = (  # ty: ignore[invalid-type-form]
        0.000001
    )


class ClockMappingSummary(StrictContractModel):
    clock_id: StableId
    method: StableId
    scale: Annotated[float, Field(strict=True, gt=0.0, allow_inf_nan=False)]
    offset_ns: Int64
    drift_ppm: FiniteFloat
    residual_rms_ms: NonNegativeFiniteFloat
    residual_max_ms: NonNegativeFiniteFloat
    declaration_consistent: StrictBool


class SessionInterval(StrictContractModel):
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64

    @model_validator(mode="after")
    def require_positive_interval(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("end_t_ns must be greater than start_t_ns")
        return self


class PhaseInterval(SessionInterval):
    phase_id: StableId
    label: NonEmptyString | None = None
    source: StableId | None = None
    confidence: UnitInterval | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class EventMarker(StrictContractModel):
    event_id: StableId
    event_type: StableId
    t_ns: NonNegativeInt64
    duration_ns: NonNegativeInt64 | None = None
    source: StableId | None = None
    confidence: UnitInterval | None = None
    response_mapping: dict[str, JsonValue] | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_zero_duration(self) -> Self:
        if self.duration_ns is not None and self.duration_ns <= 0:
            raise ValueError("duration_ns must be positive when present")
        return self


class BaselineInterval(SessionInterval):
    interval_id: StableId
    condition: StableId | None = None
    valid: StrictBool | None = None
    exclusion_reason: NonEmptyString | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_invalid_reason(self) -> Self:
        if self.valid is False and self.exclusion_reason is None:
            raise ValueError("invalid baseline requires exclusion_reason")
        return self


class PointTemporalArtifactMetrics(StrictContractModel):
    artifact_role: StableId
    binding_mode: Literal["point", "inherit"]
    source_schema_id: StableId
    aligned_schema_id: StableId
    total_rows: NonNegativeInt
    in_session_rows: NonNegativeInt
    before_session_rows: NonNegativeInt
    after_session_rows: NonNegativeInt
    first_mapped_t_ns: Int64 | None = None
    last_mapped_t_ns: Int64 | None = None
    in_session_start_t_ns: NonNegativeInt64 | None = None
    in_session_end_t_ns: NonNegativeInt64 | None = None
    in_session_span_ns: NonNegativeInt64 | None = None
    session_span_ratio: UnitInterval | None = None
    duplicate_timestamp_groups: NonNegativeInt = 0
    duplicate_timestamp_rows: NonNegativeInt = 0
    median_period_ns: NonNegativeFiniteFloat | None = None
    gap_threshold_ns: NonNegativeInt64 | None = None
    gap_count: NonNegativeInt = 0
    max_gap_ns: NonNegativeInt64 | None = None
    interpolated_rows: Literal[0] = 0

    @field_validator("interpolated_rows", mode="before")
    @classmethod
    def require_strict_integer_zero(cls, value: object) -> object:
        if value.__class__ is not int:
            raise ValueError("interpolated_rows must be an integer zero")
        return value

    @model_validator(mode="after")
    def validate_point_metrics(self) -> Self:
        partitions = self.in_session_rows + self.before_session_rows + self.after_session_rows
        if partitions != self.total_rows:
            raise ValueError("point row partitions must sum to total_rows")
        if not self.aligned_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned_schema_id must end with -aligned-v0.1")
        if self.duplicate_timestamp_rows > self.total_rows:
            raise ValueError("duplicate_timestamp_rows cannot exceed total_rows")
        if self.duplicate_timestamp_groups == 0 and self.duplicate_timestamp_rows != 0:
            raise ValueError("duplicate rows require duplicate groups")
        if (
            self.duplicate_timestamp_groups > 0
            and self.duplicate_timestamp_rows < 2 * self.duplicate_timestamp_groups
        ):
            raise ValueError("each duplicate group must contain at least two rows")
        first, last = self.first_mapped_t_ns, self.last_mapped_t_ns
        if self.total_rows == 0 and (first is not None or last is not None):
            raise ValueError("empty artifacts cannot claim mapped bounds")
        if self.total_rows > 0 and (first is None or last is None or first > last):
            raise ValueError("non-empty artifacts require ordered mapped bounds")
        inner = (
            self.in_session_start_t_ns,
            self.in_session_end_t_ns,
            self.in_session_span_ns,
            self.session_span_ratio,
        )
        if self.in_session_rows == 0 and any(value is not None for value in inner):
            raise ValueError("no in-session rows means no in-session bounds")
        if self.in_session_rows > 0:
            if any(value is None for value in inner):
                raise ValueError("in-session rows require bounds, span, and ratio")
            start = self.in_session_start_t_ns
            end = self.in_session_end_t_ns
            span = self.in_session_span_ns
            assert start is not None and end is not None and span is not None
            if end < start or span != end - start:
                raise ValueError("in-session span must match ordered bounds")
        if self.median_period_ns is None:
            if self.gap_threshold_ns is not None or self.max_gap_ns is not None or self.gap_count:
                raise ValueError("gap statistics require a median period")
        elif self.gap_threshold_ns is None or self.max_gap_ns is None:
            raise ValueError("median period requires threshold and max gap")
        return self


class IntervalTemporalArtifactMetrics(StrictContractModel):
    artifact_role: StableId
    binding_mode: Literal["interval"]
    source_schema_id: StableId
    aligned_schema_id: StableId
    total_rows: NonNegativeInt
    before_session_rows: NonNegativeInt
    after_session_rows: NonNegativeInt
    overlapping_session_rows: NonNegativeInt
    fully_in_session_rows: NonNegativeInt
    first_start_t_ns: Int64 | None = None
    last_end_t_ns: Int64 | None = None
    interpolated_rows: Literal[0] = 0

    @field_validator("interpolated_rows", mode="before")
    @classmethod
    def require_strict_integer_zero(cls, value: object) -> object:
        if value.__class__ is not int:
            raise ValueError("interpolated_rows must be an integer zero")
        return value

    @model_validator(mode="after")
    def validate_interval_metrics(self) -> Self:
        partitions = (
            self.before_session_rows + self.after_session_rows + self.overlapping_session_rows
        )
        if partitions != self.total_rows:
            raise ValueError("interval row partitions must sum to total_rows")
        if self.fully_in_session_rows > self.overlapping_session_rows:
            raise ValueError("fully in-session intervals must overlap the session")
        if not self.aligned_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned_schema_id must end with -aligned-v0.1")
        first, last = self.first_start_t_ns, self.last_end_t_ns
        if self.total_rows == 0 and (first is not None or last is not None):
            raise ValueError("empty interval artifacts cannot claim bounds")
        if self.total_rows > 0 and (first is None or last is None or first >= last):
            raise ValueError("non-empty interval artifacts require ordered bounds")
        return self


TemporalArtifactMetrics = Annotated[
    PointTemporalArtifactMetrics | IntervalTemporalArtifactMetrics,
    Field(discriminator="binding_mode"),
]


class SceneGazeMetrics(StrictContractModel):
    evaluated_in_session_gaze_rows: NonNegativeInt
    valid_association_rows: NonNegativeInt
    invalid_association_count: NonNegativeInt
    gaze_minus_frame_start_min_ns: NonNegativeInt64 | None = None
    gaze_minus_frame_start_max_ns: NonNegativeInt64 | None = None
    bounded_invalid_gaze_sample_ids: tuple[NonNegativeInt, ...] = ()

    @model_validator(mode="after")
    def validate_scene_gaze_metrics(self) -> Self:
        partition = self.valid_association_rows + self.invalid_association_count
        if partition != self.evaluated_in_session_gaze_rows:
            raise ValueError("valid and invalid scene/gaze rows must partition evaluated rows")
        if len(self.bounded_invalid_gaze_sample_ids) > 10:
            raise ValueError("scene/gaze examples are bounded at ten IDs")
        bounds = (
            self.gaze_minus_frame_start_min_ns,
            self.gaze_minus_frame_start_max_ns,
        )
        if self.valid_association_rows == 0 and any(value is not None for value in bounds):
            raise ValueError("no valid associations means no delta bounds")
        if self.valid_association_rows > 0:
            low, high = bounds
            if low is None or high is None or low > high:
                raise ValueError("valid associations require ordered delta bounds")
        return self


class StreamSynchronizationResult(StrictContractModel):
    modality: StableId
    declared_status: StreamStatus
    required_for_import: StrictBool
    input_readiness: StreamReadiness
    synchronization_status: SynchronizationItemStatus
    clock: ClockMappingSummary | None = None
    source_schema_id: StableId | None = None
    aligned_schema_id: StableId | None = None
    artifacts: dict[StableId, TemporalArtifactMetrics] = Field(default_factory=dict)
    scene_gaze_metrics: SceneGazeMetrics | None = None
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_stream_result(self) -> Self:
        if (
            self.synchronization_status
            is SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
        ):
            raise ValueError("core stream cannot defer model-bundle resolution")
        if any(key != value.artifact_role for key, value in self.artifacts.items()):
            raise ValueError("artifact keys must match artifact_role")
        aligned = self.synchronization_status is SynchronizationItemStatus.ALIGNED
        if aligned:
            if (
                self.declared_status is not StreamStatus.PRESENT
                or self.input_readiness is not StreamReadiness.READY
            ):
                raise ValueError("aligned stream requires present/ready M2 input")
            if (
                self.clock is None
                or self.source_schema_id is None
                or self.aligned_schema_id is None
                or not self.artifacts
            ):
                raise ValueError("aligned stream requires clock, schemas, and artifacts")
            if not self.clock.declaration_consistent:
                raise ValueError("aligned stream requires a consistent clock declaration")
            if not self.aligned_schema_id.endswith("-aligned-v0.1"):
                raise ValueError("stream aligned_schema_id must end with -aligned-v0.1")
            if self.modality == "G" and self.scene_gaze_metrics is None:
                raise ValueError("aligned gaze requires scene/gaze relationship metrics")
            if self.modality != "G" and self.scene_gaze_metrics is not None:
                raise ValueError("scene/gaze metrics belong only to modality G")
        else:
            if self.aligned_schema_id is not None or self.artifacts:
                raise ValueError("non-aligned stream cannot claim aligned schema or artifacts")
            if self.scene_gaze_metrics is not None and (
                self.modality != "G"
                or self.synchronization_status is not SynchronizationItemStatus.INVALID
            ):
                raise ValueError("only invalid gaze may retain relationship diagnostics")
        return self


class TaskReferenceSynchronizationResult(StrictContractModel):
    reference_id: StableId
    source: Literal["bundle", "model_bundle"]
    declared_status: StreamStatus | None = None
    required_for_import: StrictBool | None = None
    input_readiness: StreamReadiness | None = None
    synchronization_status: SynchronizationItemStatus
    clock: ClockMappingSummary | None = None
    source_schema_id: StableId | None = None
    aligned_schema_id: StableId | None = None
    source_checksums: dict[BundleRelativePath, Sha256Digest] = Field(default_factory=dict)
    artifacts: dict[StableId, TemporalArtifactMetrics] = Field(default_factory=dict)
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_reference_result(self) -> Self:
        if any(key != value.artifact_role for key, value in self.artifacts.items()):
            raise ValueError("reference artifact keys must match artifact_role")
        if self.source == "model_bundle":
            if (
                self.synchronization_status
                is not SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
            ):
                raise ValueError("model_bundle reference must be deferred in M3")
            claimed = (
                self.required_for_import,
                self.input_readiness,
                self.declared_status,
                self.clock,
                self.source_schema_id,
                self.aligned_schema_id,
            )
            if (
                any(value is not None for value in claimed)
                or self.source_checksums
                or self.artifacts
            ):
                raise ValueError("deferred model reference cannot claim bundle alignment")
            return self
        if (
            self.synchronization_status
            is SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
        ):
            raise ValueError("bundle reference cannot use deferred model status")
        if (
            self.required_for_import is None
            or self.input_readiness is None
            or self.declared_status is None
        ):
            raise ValueError("bundle reference requires declared/import/readiness state")
        aligned = self.synchronization_status is SynchronizationItemStatus.ALIGNED
        if aligned:
            if (
                self.declared_status is not StreamStatus.PRESENT
                or self.input_readiness is not StreamReadiness.READY
            ):
                raise ValueError("aligned bundle reference requires present/ready M2 input")
            if (
                self.clock is None
                or self.source_schema_id is None
                or self.aligned_schema_id is None
                or not self.source_checksums
                or not self.artifacts
            ):
                raise ValueError("aligned bundle reference requires complete alignment provenance")
            if not self.clock.declaration_consistent:
                raise ValueError("aligned bundle reference requires a consistent clock declaration")
            if not self.aligned_schema_id.endswith("-aligned-v0.1"):
                raise ValueError("reference aligned_schema_id must end with -aligned-v0.1")
        elif self.aligned_schema_id is not None or self.artifacts:
            raise ValueError("non-aligned bundle reference cannot claim aligned output")
        return self


class AnnotationSynchronizationResult(StrictContractModel):
    synchronization_status: SynchronizationItemStatus
    revision: StableId | None = None
    phase_schema_id: StableId | None = None
    event_schema_id: StableId | None = None
    baseline_schema_id: StableId | None = None
    phase_count: NonNegativeInt | None = None
    event_count: NonNegativeInt | None = None
    baseline_count: NonNegativeInt | None = None
    unannotated_intervals: tuple[SessionInterval, ...] = ()
    synthetic_semantics_unvalidated: StrictBool | None = None
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_annotation_result(self) -> Self:
        allowed = {
            SynchronizationItemStatus.ALIGNED,
            SynchronizationItemStatus.NOT_ATTEMPTED,
            SynchronizationItemStatus.INVALID,
            SynchronizationItemStatus.UNSUPPORTED,
        }
        if self.synchronization_status not in allowed:
            raise ValueError("unsupported annotation synchronization status")
        content = (
            self.revision,
            self.phase_schema_id,
            self.event_schema_id,
            self.baseline_schema_id,
            self.phase_count,
            self.event_count,
            self.baseline_count,
            self.synthetic_semantics_unvalidated,
        )
        if self.synchronization_status is SynchronizationItemStatus.ALIGNED:
            if any(value is None for value in content):
                raise ValueError("aligned annotations require schemas, counts, and provenance")
        elif any(value is not None for value in content[4:]) or self.unannotated_intervals:
            raise ValueError("non-aligned annotations cannot claim aligned counts or intervals")
        return self


class SynchronizationReport(StrictContractModel):
    contract_version: Literal["0.1.0"]
    validation_scope: Literal["native_rate_session_time_alignment_v1"]
    session_id: StableId
    source_snapshot_fingerprint: Sha256Digest
    source_classification: StableId
    synthetic_provenance: SyntheticSourceProvenance | None
    policy: SynchronizationPolicy
    policy_fingerprint: Sha256Digest
    binding_catalog_fingerprint: Sha256Digest
    session_window: SessionWindow | None
    disposition: SynchronizationDisposition
    can_continue_to_anchor_availability: StrictBool
    formal_run_authorized: Literal[False]
    stream_results: dict[StableId, StreamSynchronizationResult]
    task_reference_result: TaskReferenceSynchronizationResult | None
    annotation_result: AnnotationSynchronizationResult | None
    global_issues: tuple[DomainErrorData, ...] = ()
    synchronization_fingerprint: Sha256Digest

    @field_validator("formal_run_authorized", mode="before")
    @classmethod
    def require_strict_boolean_authorization(cls, value: object) -> object:
        if value.__class__ is not bool:
            raise ValueError("formal_run_authorized must be a boolean")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        synthetic = self.source_classification == "synthetic-test-data"
        if synthetic != (self.synthetic_provenance is not None):
            raise ValueError("synthetic classification and provenance must appear together")
        if set(self.stream_results) != set(CORE_MODALITIES):
            raise ValueError("synchronization report requires exactly seven core modalities")
        if any(key != result.modality for key, result in self.stream_results.items()):
            raise ValueError("stream result keys must match modality")
        required_core_failed = any(
            result.required_for_import
            and result.synchronization_status is not SynchronizationItemStatus.ALIGNED
            for result in self.stream_results.values()
        )
        optional_degraded = any(
            not result.required_for_import
            and result.synchronization_status
            in {
                SynchronizationItemStatus.NOT_ATTEMPTED,
                SynchronizationItemStatus.UNAVAILABLE,
                SynchronizationItemStatus.INVALID,
                SynchronizationItemStatus.UNSUPPORTED,
            }
            for result in self.stream_results.values()
        )
        annotation_failed = (
            self.annotation_result is None
            or self.annotation_result.synchronization_status
            is not SynchronizationItemStatus.ALIGNED
        )
        reference_blocked = False
        reference_degraded = False
        reference = self.task_reference_result
        if reference is not None and reference.source == "bundle":
            reference_aligned = (
                reference.synchronization_status is SynchronizationItemStatus.ALIGNED
            )
            reference_blocked = bool(reference.required_for_import) and not reference_aligned
            reference_degraded = (
                reference.required_for_import is False
                and not reference_aligned
                and reference.synchronization_status is not SynchronizationItemStatus.NOT_APPLICABLE
            )
        global_blocking = any(
            issue.error_code in BLOCKING_SYNCHRONIZATION_ERROR_CODES for issue in self.global_issues
        )
        blocked = (
            self.session_window is None
            or required_core_failed
            or annotation_failed
            or reference_blocked
            or global_blocking
        )
        expected = (
            SynchronizationDisposition.BLOCKED
            if blocked
            else SynchronizationDisposition.READY_PARTIAL
            if optional_degraded or reference_degraded
            else SynchronizationDisposition.READY
        )
        if self.disposition is not expected:
            raise ValueError("disposition must match synchronization item states")
        if self.can_continue_to_anchor_availability != (not blocked):
            raise ValueError("only non-blocked reports can continue")
        return self


__all__ = [
    "BLOCKING_SYNCHRONIZATION_ERROR_CODES",
    "AnnotationSynchronizationResult",
    "BaselineInterval",
    "ClockMappingSummary",
    "EventMarker",
    "IntervalTemporalArtifactMetrics",
    "PhaseInterval",
    "PointTemporalArtifactMetrics",
    "SceneGazeMetrics",
    "SessionInterval",
    "SessionWindow",
    "StreamSynchronizationResult",
    "SynchronizationDisposition",
    "SynchronizationItemStatus",
    "SynchronizationPolicy",
    "SynchronizationReport",
    "TaskReferenceSynchronizationResult",
    "TemporalArtifactMetrics",
]
