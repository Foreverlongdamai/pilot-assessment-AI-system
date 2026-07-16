"""Transport-neutral contracts for exact assessment runs and durable results."""

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
    NonNegativeInt,
    Sha256Digest,
    StableId,
    StrictContractModel,
    freeze_json_mapping,
)
from pilot_assessment.contracts.model_components import (
    ComponentKind,
    PinnedComponentRef,
)
from pilot_assessment.contracts.project import ArtifactIdRef, SessionRevisionRef

HumanMessage = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
JsonPointer = Annotated[str, StringConstraints(min_length=1, max_length=2048, pattern=r"^/")]
VersionLabel = Annotated[str, StringConstraints(min_length=1, max_length=128)]
PositiveSequence = Annotated[int, Field(strict=True, gt=0)]


class RunPurpose(StrEnum):
    PREVIEW = "preview"
    SOFTWARE_TEST = "software_test"
    ASSESSMENT = "assessment"


class TechnicalDisposition(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class RunDiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunStage(StrEnum):
    QUEUED = "queued"
    SNAPSHOT_VALIDATION = "snapshot_validation"
    INGESTION = "ingestion"
    SYNCHRONIZATION = "synchronization"
    EVIDENCE = "evidence"
    INFERENCE = "inference"
    REPORTING = "reporting"
    COMPLETED = "completed"


class RunScientificStatus(StrEnum):
    NOT_SUPPORTED = "not_supported"
    ENGINEERING_DEFAULT = "engineering_default"
    EXPERT_REVIEWED = "expert_reviewed"
    CALIBRATED = "calibrated"
    INTERNALLY_VALIDATED = "internally_validated"
    EXTERNALLY_VALIDATED = "externally_validated"


def _pinned_key(reference: PinnedComponentRef) -> str:
    return f"{reference.kind.value}:{reference.version_id}"


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


class RunDiagnostic(StrictContractModel):
    code: StableId
    severity: RunDiagnosticSeverity
    location: JsonPointer
    message: HumanMessage
    details: dict[str, JsonValue]

    @field_validator("details")
    @classmethod
    def freeze_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return freeze_json_mapping(value)


class ExecutableIdentity(StrictContractModel):
    identity_id: StableId
    version: VersionLabel
    content_hash: Sha256Digest


class RunPreflightReport(StrictContractModel):
    contract_id: Literal["run-preflight-report"] = "run-preflight-report"
    contract_version: Literal["0.1.0"] = "0.1.0"
    preflight_id: StableId
    session_revision_ref: SessionRevisionRef
    scheme_ref: PinnedComponentRef
    technical_disposition: TechnicalDisposition
    formal_run_authorized: StrictBool
    synthetic_data: StrictBool
    locked_component_refs: tuple[PinnedComponentRef, ...]
    diagnostics: tuple[RunDiagnostic, ...]
    preflight_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_preflight(self) -> Self:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        _require_unique(
            tuple(_pinned_key(reference) for reference in self.locked_component_refs),
            "locked component refs",
        )
        has_error = any(
            diagnostic.severity is RunDiagnosticSeverity.ERROR for diagnostic in self.diagnostics
        )
        if self.technical_disposition is TechnicalDisposition.BLOCKED and not has_error:
            raise ValueError("blocked preflight requires an error diagnostic")
        if self.technical_disposition is TechnicalDisposition.READY and has_error:
            raise ValueError("ready preflight cannot contain error diagnostics")
        if self.formal_run_authorized and (
            self.technical_disposition is not TechnicalDisposition.READY or self.synthetic_data
        ):
            raise ValueError("formal authorization requires ready non-synthetic input")
        return self


class RunSnapshot(StrictContractModel):
    contract_id: Literal["run-snapshot"] = "run-snapshot"
    contract_version: Literal["0.1.0"] = "0.1.0"
    run_id: StableId
    purpose: RunPurpose
    session_revision_ref: SessionRevisionRef
    scheme_ref: PinnedComponentRef
    locked_component_refs: tuple[PinnedComponentRef, ...]
    locked_source_refs: tuple[PinnedComponentRef, ...]
    locked_operator_identities: tuple[ExecutableIdentity, ...]
    engine_identity: ExecutableIdentity
    numeric_runtime_identities: tuple[ExecutableIdentity, ...]
    runtime_parameters_hash: Sha256Digest
    preflight_hash: Sha256Digest
    snapshot_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        _require_unique(
            tuple(_pinned_key(reference) for reference in self.locked_component_refs),
            "locked component refs",
        )
        _require_unique(
            tuple(_pinned_key(reference) for reference in self.locked_source_refs),
            "locked source refs",
        )
        if any(
            reference.kind is not ComponentKind.SOURCE_DESCRIPTOR
            for reference in self.locked_source_refs
        ):
            raise ValueError("locked_source_refs must identify source descriptors")
        _require_unique(
            tuple(identity.identity_id for identity in self.locked_operator_identities),
            "locked operator identities",
        )
        _require_unique(
            tuple(identity.identity_id for identity in self.numeric_runtime_identities),
            "numeric runtime identities",
        )
        return self


class AssessmentRun(StrictContractModel):
    contract_id: Literal["assessment-run"] = "assessment-run"
    contract_version: Literal["0.1.0"] = "0.1.0"
    run_id: StableId
    snapshot: RunSnapshot
    state: RunState
    stage: RunStage
    progress_sequence: NonNegativeInt
    requested_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    cancellation_requested_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.snapshot.run_id != self.run_id:
            raise ValueError("run_id must match the frozen snapshot")
        if self.started_at is not None and self.started_at < self.requested_at:
            raise ValueError("started_at cannot precede requested_at")
        if self.finished_at is not None and (
            self.started_at is None or self.finished_at < self.started_at
        ):
            raise ValueError("finished_at requires and cannot precede started_at")
        if (
            self.cancellation_requested_at is not None
            and self.cancellation_requested_at < self.requested_at
        ):
            raise ValueError("cancellation_requested_at cannot precede requested_at")

        if self.state is RunState.QUEUED:
            if self.stage is not RunStage.QUEUED or any(
                value is not None
                for value in (
                    self.started_at,
                    self.finished_at,
                    self.cancellation_requested_at,
                )
            ):
                raise ValueError("queued runs require queued stage and no lifecycle timestamps")
        elif self.state is RunState.RUNNING:
            if (
                self.started_at is None
                or self.finished_at is not None
                or self.cancellation_requested_at is not None
                or self.stage in {RunStage.QUEUED, RunStage.COMPLETED}
            ):
                raise ValueError("running run lifecycle fields are inconsistent")
        elif self.state is RunState.CANCELLING:
            if (
                self.started_at is None
                or self.finished_at is not None
                or self.cancellation_requested_at is None
                or self.stage in {RunStage.QUEUED, RunStage.COMPLETED}
            ):
                raise ValueError("cancelling run lifecycle fields are inconsistent")
        else:
            if self.started_at is None or self.finished_at is None:
                raise ValueError("terminal runs require start and finish timestamps")
            if self.state is RunState.COMPLETED and self.stage is not RunStage.COMPLETED:
                raise ValueError("completed runs require completed stage")
            if self.state is not RunState.COMPLETED and self.stage is RunStage.COMPLETED:
                raise ValueError("only completed runs may use completed stage")
            if self.state is RunState.CANCELLED and self.cancellation_requested_at is None:
                raise ValueError("cancelled runs require a cancellation request timestamp")
        return self


class RunEvent(StrictContractModel):
    contract_id: Literal["run-event"] = "run-event"
    contract_version: Literal["0.1.0"] = "0.1.0"
    event_id: StableId
    run_id: StableId
    sequence: PositiveSequence
    state: RunState
    stage: RunStage
    completed_units: NonNegativeInt
    total_units: NonNegativeInt
    message: HumanMessage
    occurred_at: AwareDatetime
    details: dict[str, JsonValue]

    @field_validator("details")
    @classmethod
    def freeze_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return freeze_json_mapping(value)

    @model_validator(mode="after")
    def validate_progress(self) -> Self:
        if self.completed_units > self.total_units:
            raise ValueError("completed_units cannot exceed total_units")
        return self


class RunResultEnvelope(StrictContractModel):
    contract_id: Literal["run-result-envelope"] = "run-result-envelope"
    contract_version: Literal["0.1.0"] = "0.1.0"
    result_id: StableId
    run_id: StableId
    snapshot_hash: Sha256Digest
    evidence_result_refs: tuple[ArtifactIdRef, ...]
    evidence_trace_refs: tuple[ArtifactIdRef, ...]
    observation_set_ref: ArtifactIdRef
    posterior_ref: ArtifactIdRef
    inference_trace_ref: ArtifactIdRef
    reporting_refs: tuple[ArtifactIdRef, ...]
    coverage_refs: tuple[ArtifactIdRef, ...]
    scientific_status: RunScientificStatus
    result_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_artifact_refs(self) -> Self:
        references = (
            *self.evidence_result_refs,
            *self.evidence_trace_refs,
            self.observation_set_ref,
            self.posterior_ref,
            self.inference_trace_ref,
            *self.reporting_refs,
            *self.coverage_refs,
        )
        _require_unique(
            tuple(reference.artifact_id for reference in references),
            "result artifact IDs",
        )
        return self


__all__ = [
    "AssessmentRun",
    "ExecutableIdentity",
    "RunDiagnostic",
    "RunDiagnosticSeverity",
    "RunEvent",
    "RunPreflightReport",
    "RunPurpose",
    "RunResultEnvelope",
    "RunScientificStatus",
    "RunSnapshot",
    "RunStage",
    "RunState",
    "TechnicalDisposition",
]
