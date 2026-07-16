"""Portable project, managed-session, artifact, transaction, and audit contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, JsonValue, StringConstraints, field_validator, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    NonNegativeInt64,
    Sha256Digest,
    StableId,
    StrictContractModel,
    freeze_json_mapping,
)

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
MediaType = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$",
    ),
]


class SessionLifecycle(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SessionSourceKind(StrEnum):
    MANAGED_IMPORT = "managed_import"


class ArtifactLifecycle(StrEnum):
    ACTIVE = "active"
    UNREFERENCED = "unreferenced"
    QUARANTINED = "quarantined"


class ArtifactOwnerKind(StrEnum):
    SESSION_REVISION = "session_revision"
    RUN_PREFLIGHT = "run_preflight"
    RUN = "run"
    RUN_RESULT = "run_result"
    EXPORT = "export"


class TransactionStatus(StrEnum):
    PREPARED = "prepared"
    COMPLETED = "completed"


class ProjectDescriptor(StrictContractModel):
    contract_id: Literal["project-descriptor"] = "project-descriptor"
    contract_version: Literal["0.1.0"] = "0.1.0"
    project_id: StableId
    format_version: Literal["0.1.0"]
    name: HumanLabel
    created_at: AwareDatetime


class SessionRecord(StrictContractModel):
    contract_id: Literal["session-record"] = "session-record"
    contract_version: Literal["0.1.0"] = "0.1.0"
    session_id: StableId
    project_id: StableId
    participant_id: StableId
    lifecycle: SessionLifecycle
    current_session_revision_id: StableId
    created_at: AwareDatetime


class SessionRevisionRef(StrictContractModel):
    session_id: StableId
    session_revision_id: StableId
    bundle_root_hash: Sha256Digest


class SessionRevision(StrictContractModel):
    contract_id: Literal["session-revision"] = "session-revision"
    contract_version: Literal["0.1.0"] = "0.1.0"
    session_revision_id: StableId
    session_id: StableId
    managed_bundle_path: BundleRelativePath
    manifest_hash: Sha256Digest
    bundle_root_hash: Sha256Digest
    file_inventory_hash: Sha256Digest
    source_kind: SessionSourceKind
    imported_at: AwareDatetime
    imported_by: StableId
    ingestion_readiness_ref: StableId
    synchronization_ref: StableId | None


class ArtifactIdRef(StrictContractModel):
    artifact_id: StableId
    sha256: Sha256Digest


class ManagedArtifact(StrictContractModel):
    contract_id: Literal["managed-artifact"] = "managed-artifact"
    contract_version: Literal["0.1.0"] = "0.1.0"
    artifact_id: StableId
    sha256: Sha256Digest
    byte_size: NonNegativeInt64
    media_type: MediaType
    schema_id: StableId | None
    managed_relative_path: BundleRelativePath
    lifecycle: ArtifactLifecycle
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_content_address(self) -> Self:
        expected = f"artifacts/sha256/{self.sha256[:2]}/{self.sha256}/payload"
        if self.managed_relative_path != expected:
            raise ValueError("managed artifact path must be derived from its SHA-256 digest")
        return self


class ArtifactReference(StrictContractModel):
    contract_id: Literal["artifact-reference"] = "artifact-reference"
    contract_version: Literal["0.1.0"] = "0.1.0"
    owner_kind: ArtifactOwnerKind
    owner_id: StableId
    role: StableId
    artifact_id: StableId


class TransactionReceipt(StrictContractModel):
    contract_id: Literal["transaction-receipt"] = "transaction-receipt"
    contract_version: Literal["0.1.0"] = "0.1.0"
    transaction_id: StableId
    method: StableId
    request_hash: Sha256Digest
    status: TransactionStatus
    response_payload: dict[str, JsonValue] | None
    audit_event_id: StableId | None
    completed_at: AwareDatetime | None

    @field_validator("response_payload")
    @classmethod
    def freeze_response(cls, value: dict[str, JsonValue] | None) -> dict[str, JsonValue] | None:
        return None if value is None else freeze_json_mapping(value)

    @model_validator(mode="after")
    def validate_status_shape(self) -> Self:
        completion_fields = (
            self.response_payload,
            self.audit_event_id,
            self.completed_at,
        )
        if self.status is TransactionStatus.PREPARED and any(
            value is not None for value in completion_fields
        ):
            raise ValueError("prepared transactions cannot claim a response or completion")
        if self.status is TransactionStatus.COMPLETED and any(
            value is None for value in completion_fields
        ):
            raise ValueError("completed transactions require response, audit event, and time")
        return self


class AuditEvent(StrictContractModel):
    contract_id: Literal["audit-event"] = "audit-event"
    contract_version: Literal["0.1.0"] = "0.1.0"
    audit_event_id: StableId
    event_type: StableId
    actor_id: StableId
    occurred_at: AwareDatetime
    subject_kind: StableId
    subject_id: StableId
    transaction_id: StableId | None
    details: dict[str, JsonValue]

    @field_validator("details")
    @classmethod
    def freeze_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return freeze_json_mapping(value)


__all__ = [
    "ArtifactIdRef",
    "ArtifactLifecycle",
    "ArtifactOwnerKind",
    "ArtifactReference",
    "AuditEvent",
    "ManagedArtifact",
    "ProjectDescriptor",
    "SessionLifecycle",
    "SessionRecord",
    "SessionRevision",
    "SessionRevisionRef",
    "SessionSourceKind",
    "TransactionReceipt",
    "TransactionStatus",
]
