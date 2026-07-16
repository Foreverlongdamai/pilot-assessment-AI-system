from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from pilot_assessment.contracts.project import (
    ArtifactLifecycle,
    ArtifactOwnerKind,
    ArtifactReference,
)
from pilot_assessment.persistence.artifacts import (
    ArtifactIntegrityError,
    ArtifactOwner,
    ArtifactPathError,
    ManagedArtifactStore,
)
from pilot_assessment.persistence.project import ProjectStore

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _project(tmp_path):
    return ProjectStore.create(
        tmp_path / "project",
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )


def test_artifact_put_deduplicates_bytes_and_derives_lifecycle_from_references(tmp_path) -> None:
    project = _project(tmp_path)
    store = ManagedArtifactStore(project.root, project.database, clock=lambda: NOW)
    payload = b"posterior-result"
    first_owner = ArtifactOwner(
        owner_kind=ArtifactOwnerKind.RUN_RESULT,
        owner_id="result.alpha",
        role="posterior",
    )
    second_owner = ArtifactOwner(
        owner_kind=ArtifactOwnerKind.RUN_RESULT,
        owner_id="result.beta",
        role="posterior",
    )
    try:
        first = store.put_bytes(
            payload,
            transaction_id="tx.artifact-alpha",
            media_type="application/json",
            schema_id="posterior-result-0.1.0",
            owner=first_owner,
        )
        second = store.put_bytes(
            payload,
            transaction_id="tx.artifact-beta",
            media_type="application/json",
            schema_id="posterior-result-0.1.0",
            owner=second_owner,
        )

        assert first == second
        assert first.sha256 == hashlib.sha256(payload).hexdigest()
        assert first.lifecycle is ArtifactLifecycle.ACTIVE
        assert store.reference_count(first.artifact_id) == 2
        assert project.database.fetchone("SELECT COUNT(*) FROM managed_artifacts")[0] == 1
        with store.open_verified(first.artifact_id) as stream:
            assert stream.read() == payload

        store.remove_reference(first_owner)
        assert store.get(first.artifact_id).lifecycle is ArtifactLifecycle.ACTIVE
        store.remove_reference(second_owner)
        unreferenced = store.get(first.artifact_id)
        assert unreferenced.lifecycle is ArtifactLifecycle.UNREFERENCED
        assert (project.root / unreferenced.managed_relative_path).is_file()

        store.add_reference(
            ArtifactReference(
                owner_kind=ArtifactOwnerKind.RUN_RESULT,
                owner_id="result.gamma",
                role="posterior",
                artifact_id=first.artifact_id,
            )
        )
        assert store.get(first.artifact_id).lifecycle is ArtifactLifecycle.ACTIVE
    finally:
        project.close()


def test_verified_open_and_dedup_reject_tampered_final_bytes(tmp_path) -> None:
    project = _project(tmp_path)
    store = ManagedArtifactStore(project.root, project.database, clock=lambda: NOW)
    try:
        artifact = store.put_bytes(
            b"expected",
            transaction_id="tx.expected",
            media_type="application/octet-stream",
            schema_id=None,
            owner=None,
        )
        path = project.root / artifact.managed_relative_path
        path.write_bytes(b"tampered")

        with (
            pytest.raises(ArtifactIntegrityError, match="SHA-256"),
            store.open_verified(artifact.artifact_id),
        ):
            pass
        with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
            store.put_bytes(
                b"expected",
                transaction_id="tx.expected-retry",
                media_type="application/octet-stream",
                schema_id=None,
                owner=None,
            )
    finally:
        project.close()


def test_recovery_cleans_uncommitted_files_but_keeps_registered_unreferenced_artifact(
    tmp_path,
) -> None:
    project = _project(tmp_path)
    store = ManagedArtifactStore(project.root, project.database, clock=lambda: NOW)
    try:
        retained = store.put_bytes(
            b"retained",
            transaction_id="tx.retained",
            media_type="application/octet-stream",
            schema_id=None,
            owner=None,
        )
        retained_path = project.root / retained.managed_relative_path

        orphan_bytes = b"orphan"
        orphan_hash = hashlib.sha256(orphan_bytes).hexdigest()
        orphan_relative = f"artifacts/sha256/{orphan_hash[:2]}/{orphan_hash}/payload"
        orphan_path = project.root / orphan_relative
        orphan_path.parent.mkdir(parents=True)
        orphan_path.write_bytes(orphan_bytes)
        staging_relative = "staging/artifacts/tx.crashed/payload"
        staging_path = project.root / staging_relative
        staging_path.parent.mkdir(parents=True)
        staging_path.write_bytes(orphan_bytes)
        project.database.execute(
            """
            INSERT INTO file_operation_intents(
                intent_id, transaction_id, operation, staging_relative_path,
                final_relative_path, expected_sha256, state, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "intent.crashed",
                "tx.crashed",
                "artifact.put",
                staging_relative,
                orphan_relative,
                orphan_hash,
                "prepared",
                "2026-07-16T12:00:00Z",
            ),
        )

        report = store.recover()

        assert report.cleared_intents == 1
        assert report.removed_staging_files >= 1
        assert report.removed_orphan_files >= 1
        assert not staging_path.exists()
        assert not orphan_path.exists()
        assert retained_path.is_file()
        assert store.get(retained.artifact_id).lifecycle is ArtifactLifecycle.UNREFERENCED
    finally:
        project.close()


def test_recovery_rejects_any_intent_path_outside_project_root(tmp_path) -> None:
    project = _project(tmp_path)
    store = ManagedArtifactStore(project.root, project.database, clock=lambda: NOW)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"preserve")
    try:
        project.database.execute(
            """
            INSERT INTO file_operation_intents(
                intent_id, transaction_id, operation, staging_relative_path,
                final_relative_path, expected_sha256, state, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "intent.escape",
                "tx.escape",
                "artifact.put",
                "../outside.bin",
                "artifacts/sha256/aa/" + "a" * 64 + "/payload",
                "a" * 64,
                "prepared",
                "2026-07-16T12:00:00Z",
            ),
        )

        with pytest.raises(ArtifactPathError):
            store.recover()
        assert outside.read_bytes() == b"preserve"
    finally:
        project.close()
