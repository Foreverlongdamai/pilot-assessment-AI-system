"""Transport-neutral contracts for exact assessment runs and durable results."""

from __future__ import annotations

from datetime import datetime, timedelta
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
from pilot_assessment.contracts.model_workspace import (
    ModelNode,
    ModelNodeKind,
    ModelObjectLifecycle,
    TaskScheme,
)
from pilot_assessment.contracts.project import ArtifactIdRef, SessionRevisionRef
from pilot_assessment.contracts.source_provenance import BackendSourceIdentity

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


class ModelNodeSnapshotRef(StrictContractModel):
    """Exact current-node identity used by current-model preflight."""

    node_id: StableId
    node_kind: ModelNodeKind
    semantic_revision: NonNegativeInt
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


class CurrentModelRunPreflightReport(StrictContractModel):
    """Technical preflight for one autosaved current TaskScheme revision."""

    contract_id: Literal["current-model-run-preflight-report"] = (
        "current-model-run-preflight-report"
    )
    contract_version: Literal["0.1.0"] = "0.1.0"
    preflight_id: StableId
    session_revision_ref: SessionRevisionRef
    scheme_id: StableId
    scheme_semantic_revision: NonNegativeInt
    scheme_content_hash: Sha256Digest
    active_node_refs: tuple[ModelNodeSnapshotRef, ...]
    technical_disposition: TechnicalDisposition
    formal_run_authorized: StrictBool
    synthetic_data: StrictBool
    diagnostics: tuple[RunDiagnostic, ...]
    execution_preflight: RunPreflightReport | None
    preflight_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_current_preflight(self) -> Self:
        node_ids = tuple(reference.node_id for reference in self.active_node_refs)
        _require_unique(node_ids, "active node refs")
        if node_ids != tuple(sorted(node_ids)):
            raise ValueError("active node refs must use canonical node order")

        has_error = any(
            diagnostic.severity is RunDiagnosticSeverity.ERROR for diagnostic in self.diagnostics
        )
        if self.technical_disposition is TechnicalDisposition.BLOCKED and not has_error:
            raise ValueError("blocked current preflight requires an error diagnostic")
        if self.technical_disposition is TechnicalDisposition.READY and has_error:
            raise ValueError("ready current preflight cannot contain error diagnostics")
        if self.formal_run_authorized and (
            self.technical_disposition is not TechnicalDisposition.READY or self.synthetic_data
        ):
            raise ValueError("formal authorization requires ready non-synthetic input")

        if self.technical_disposition is TechnicalDisposition.READY:
            if self.execution_preflight is None:
                raise ValueError("ready current preflight requires a ready execution preflight")
            if self.execution_preflight.technical_disposition is not TechnicalDisposition.READY:
                raise ValueError("ready current preflight requires a ready execution preflight")
        if self.execution_preflight is not None:
            if self.execution_preflight.session_revision_ref != self.session_revision_ref:
                raise ValueError("execution preflight must lock the same session revision")
            if self.execution_preflight.synthetic_data is not self.synthetic_data:
                raise ValueError("execution preflight synthetic-data state must match")
            if self.execution_preflight.formal_run_authorized is not self.formal_run_authorized:
                raise ValueError("execution preflight formal authorization must match")
        return self


class CurrentModelRunPreflightReportV2(CurrentModelRunPreflightReport):
    """Current-model preflight carrying the process-frozen Python backend identity."""

    contract_version: Literal["0.2.0"] = "0.2.0"
    backend_source_identity: BackendSourceIdentity
    source_snapshot_ref: ArtifactIdRef | None

    @model_validator(mode="after")
    def validate_source_provenance(self) -> Self:
        if (
            self.technical_disposition is TechnicalDisposition.READY
            and self.source_snapshot_ref is None
        ):
            raise ValueError("ready current preflight requires a backend source snapshot")
        if self.source_snapshot_ref is not None and (
            self.source_snapshot_ref.artifact_id != f"artifact.{self.source_snapshot_ref.sha256}"
        ):
            raise ValueError("source snapshot artifact ID must match its SHA-256")
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


class CurrentModelRunSnapshot(StrictContractModel):
    """Immutable full current-model state paired with a legacy execution snapshot."""

    contract_id: Literal["current-model-run-snapshot"] = "current-model-run-snapshot"
    contract_version: Literal["0.1.0"] = "0.1.0"
    run_id: StableId
    purpose: RunPurpose
    session_revision_ref: SessionRevisionRef
    scheme: TaskScheme
    active_nodes: tuple[ModelNode, ...]
    locked_operator_identities: tuple[ExecutableIdentity, ...]
    engine_identity: ExecutableIdentity
    numeric_runtime_identities: tuple[ExecutableIdentity, ...]
    runtime_parameters_hash: Sha256Digest
    preflight_hash: Sha256Digest
    execution_snapshot: RunSnapshot
    snapshot_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_current_snapshot(self) -> Self:
        node_ids = tuple(node.node_id for node in self.active_nodes)
        _require_unique(node_ids, "active current-model nodes")
        if node_ids != tuple(sorted(node_ids)):
            raise ValueError("active current-model nodes must use canonical node order")
        if node_ids != self.scheme.computed_active_closure:
            raise ValueError("active nodes must exactly match the frozen scheme active closure")
        if any(node.lifecycle is not ModelObjectLifecycle.ACTIVE for node in self.active_nodes):
            raise ValueError("frozen active closure cannot contain archived nodes")
        _require_unique(
            tuple(identity.identity_id for identity in self.locked_operator_identities),
            "locked operator identities",
        )
        _require_unique(
            tuple(identity.identity_id for identity in self.numeric_runtime_identities),
            "numeric runtime identities",
        )

        execution = self.execution_snapshot
        if execution.run_id != self.run_id:
            raise ValueError("execution snapshot run_id must match current snapshot")
        if execution.purpose is not self.purpose:
            raise ValueError("execution snapshot purpose must match current snapshot")
        if execution.session_revision_ref != self.session_revision_ref:
            raise ValueError("execution snapshot must lock the same session revision")
        if execution.locked_operator_identities != self.locked_operator_identities:
            raise ValueError("execution snapshot operator identities must match")
        if execution.engine_identity != self.engine_identity:
            raise ValueError("execution snapshot engine identity must match")
        if execution.numeric_runtime_identities != self.numeric_runtime_identities:
            raise ValueError("execution snapshot numeric runtime identities must match")
        if execution.runtime_parameters_hash != self.runtime_parameters_hash:
            raise ValueError("execution snapshot runtime parameters must match")
        return self


class CurrentModelRunSnapshotV2(CurrentModelRunSnapshot):
    """Current-model run snapshot with immutable Python backend provenance."""

    contract_version: Literal["0.2.0"] = "0.2.0"
    backend_source_identity: BackendSourceIdentity
    source_snapshot_ref: ArtifactIdRef

    @model_validator(mode="after")
    def validate_source_snapshot(self) -> Self:
        if self.source_snapshot_ref.artifact_id != f"artifact.{self.source_snapshot_ref.sha256}":
            raise ValueError("source snapshot artifact ID must match its SHA-256")
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


class AssessmentRunV2(StrictContractModel):
    """Run lifecycle whose immutable snapshot uses current M7 model definitions."""

    contract_id: Literal["assessment-run"] = "assessment-run"
    contract_version: Literal["0.2.0"] = "0.2.0"
    run_id: StableId
    snapshot: CurrentModelRunSnapshot | CurrentModelRunSnapshotV2
    state: RunState
    stage: RunStage
    progress_sequence: NonNegativeInt
    requested_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    cancellation_requested_at: AwareDatetime | None

    @field_validator(
        "requested_at",
        "started_at",
        "finished_at",
        "cancellation_requested_at",
    )
    @classmethod
    def validate_utc_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must use UTC offset +00:00")
        return value

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
    "AssessmentRunV2",
    "CurrentModelRunPreflightReport",
    "CurrentModelRunPreflightReportV2",
    "CurrentModelRunSnapshot",
    "CurrentModelRunSnapshotV2",
    "ExecutableIdentity",
    "ModelNodeSnapshotRef",
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
