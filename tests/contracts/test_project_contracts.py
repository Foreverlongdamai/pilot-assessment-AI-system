from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.project import (
    ArtifactLifecycle,
    ArtifactOwnerKind,
    ArtifactReference,
    AuditEvent,
    ManagedArtifact,
    ProjectDescriptor,
    SessionLifecycle,
    SessionRecord,
    SessionRevision,
    SessionRevisionRef,
    SessionSourceKind,
    TransactionReceipt,
    TransactionStatus,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def test_project_descriptor_is_strict_frozen_and_requires_aware_time() -> None:
    descriptor = ProjectDescriptor(
        project_id="project.alpha",
        format_version="0.1.0",
        name="Alpha project",
        created_at=NOW,
    )

    assert descriptor.model_dump(mode="json")["created_at"] == "2026-07-16T12:00:00Z"
    with pytest.raises(ValidationError):
        ProjectDescriptor(
            project_id="project.alpha",
            format_version="0.1.0",
            name="Alpha project",
            created_at=datetime(2026, 7, 16, 12, 0),
        )
    with pytest.raises(ValidationError):
        ProjectDescriptor.model_validate({**descriptor.model_dump(), "absolute_root": "C:/data"})
    with pytest.raises(ValidationError):
        descriptor.name = "changed"  # type: ignore[misc]


def test_session_contracts_bind_one_exact_managed_revision() -> None:
    revision = SessionRevision(
        session_revision_id="session.alpha.rev1",
        session_id="session.alpha",
        managed_bundle_path="sessions/session.alpha/session.alpha.rev1/bundle",
        manifest_hash=HASH_A.upper(),
        bundle_root_hash=HASH_B,
        file_inventory_hash=HASH_C,
        source_kind=SessionSourceKind.MANAGED_IMPORT,
        imported_at=NOW,
        imported_by="expert.alpha",
        ingestion_readiness_ref="artifact.readiness",
        synchronization_ref=None,
    )
    record = SessionRecord(
        session_id="session.alpha",
        project_id="project.alpha",
        participant_id="pilot.pseudonym",
        lifecycle=SessionLifecycle.ACTIVE,
        current_session_revision_id=revision.session_revision_id,
        created_at=NOW,
    )
    reference = SessionRevisionRef(
        session_id=record.session_id,
        session_revision_id=revision.session_revision_id,
        bundle_root_hash=revision.bundle_root_hash,
    )

    assert revision.manifest_hash == HASH_A
    assert reference.bundle_root_hash == HASH_B
    with pytest.raises(ValidationError):
        SessionRevision.model_validate(
            {**revision.model_dump(), "managed_bundle_path": "../external"}
        )


def test_artifact_and_owner_reference_are_typed_and_hash_bound() -> None:
    artifact = ManagedArtifact(
        artifact_id="artifact.posterior",
        sha256=HASH_A,
        byte_size=128,
        media_type="application/json",
        schema_id="posterior-result-0.1.0",
        managed_relative_path=("artifacts/sha256/aa/" + HASH_A + "/payload"),
        lifecycle=ArtifactLifecycle.ACTIVE,
        created_at=NOW,
    )
    reference = ArtifactReference(
        owner_kind=ArtifactOwnerKind.RUN_RESULT,
        owner_id="result.alpha",
        role="posterior",
        artifact_id=artifact.artifact_id,
    )

    assert artifact.byte_size == 128
    assert reference.owner_kind is ArtifactOwnerKind.RUN_RESULT
    with pytest.raises(ValidationError):
        ManagedArtifact.model_validate({**artifact.model_dump(), "media_type": "json"})


def test_transaction_receipt_enforces_prepared_and_completed_shapes() -> None:
    prepared = TransactionReceipt(
        transaction_id="tx.alpha",
        method="session.import",
        request_hash=HASH_A,
        status=TransactionStatus.PREPARED,
        response_payload=None,
        audit_event_id=None,
        completed_at=None,
    )
    completed = TransactionReceipt(
        transaction_id="tx.beta",
        method="scheme.draft.publish",
        request_hash=HASH_B,
        status=TransactionStatus.COMPLETED,
        response_payload={"scheme_version_id": "scheme.alpha.v2"},
        audit_event_id="audit.beta",
        completed_at=NOW,
    )

    assert prepared.completed_at is None
    with pytest.raises(TypeError):
        completed.response_payload["scheme_version_id"] = "changed"  # type: ignore[index]
    with pytest.raises(ValidationError):
        TransactionReceipt.model_validate({**prepared.model_dump(), "status": "completed"})
    with pytest.raises(ValidationError):
        TransactionReceipt.model_validate(
            {
                **completed.model_dump(),
                "status": "prepared",
            }
        )


def test_audit_event_freezes_details_without_storing_payload_bytes() -> None:
    event = AuditEvent(
        audit_event_id="audit.alpha",
        event_type="session.imported",
        actor_id="expert.alpha",
        occurred_at=NOW,
        subject_kind="session_revision",
        subject_id="session.alpha.rev1",
        transaction_id="tx.alpha",
        details={"bundle_root_hash": HASH_A, "file_count": 7},
    )

    assert event.details["file_count"] == 7
    with pytest.raises(TypeError):
        event.details["file_count"] = 8  # type: ignore[index]
