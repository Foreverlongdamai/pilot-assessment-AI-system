from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

import pilot_assessment.persistence.sessions as session_persistence
from pilot_assessment.contracts.ingestion import ReadinessDisposition
from pilot_assessment.contracts.session import StreamStatus
from pilot_assessment.contracts.session_source import SessionDataSourceKind
from pilot_assessment.ingestion.manifest_loader import ManifestLoader
from pilot_assessment.ingestion.profiles import CsvProfile, load_builtin_profiles
from pilot_assessment.persistence.artifacts import ManagedArtifactStore
from pilot_assessment.persistence.project import ProjectStore
from pilot_assessment.persistence.sessions import (
    SessionImportIntegrityError,
    SessionImportPathError,
    SessionImportService,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _project(tmp_path: Path) -> ProjectStore:
    return ProjectStore.create(
        tmp_path / "project",
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )


def _service(project: ProjectStore) -> SessionImportService:
    return SessionImportService(
        project.root,
        project.database,
        project_id=project.descriptor.project_id,
        clock=lambda: NOW,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
    }


def _raw_source(tmp_path: Path) -> Path:
    root = tmp_path / "external-raw"
    (root / "streams").mkdir(parents=True)
    (root / "annotations").mkdir()
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    assert isinstance(profile, CsvProfile)
    headers = [column.source_header for column in profile.columns]
    rows: list[str] = []
    for index in range(6):
        values = ["0" for _ in headers]
        values[headers.index("Simulation time")] = f"{index / 100:.2f}"
        values[headers.index("Control_Mode")] = "1"
        values[headers.index("Time Delay s")] = "0.2"
        values[headers.index("Lon Frequency rad/s")] = "8"
        values[headers.index("Long Damping")] = "0.8"
        rows.append(",".join(values))
    (root / "streams" / "simulator.csv").write_text(
        ",".join(headers) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="",
    )
    return root


def test_external_inspect_is_read_only(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    project = _project(tmp_path)
    service = _service(project)
    before = {
        table: project.database.fetchone(f"SELECT COUNT(*) FROM {table}")[0]
        for table in (
            "sessions",
            "session_revisions",
            "session_files",
            "managed_artifacts",
            "idempotency_transactions",
            "audit_events",
        )
    }
    try:
        report = service.inspect(m4_workflow_bundle)

        assert report.disposition is ReadinessDisposition.READY
        assert report.formal_run_authorized is False
        assert {
            table: project.database.fetchone(f"SELECT COUNT(*) FROM {table}")[0] for table in before
        } == before
        assert list((project.root / "staging" / "imports").iterdir()) == []
    finally:
        project.close()


def test_import_copies_exact_bundle_replays_without_source_and_preserves_old_revision(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external-bundle"
    shutil.copytree(m4_workflow_bundle, external)
    original = _snapshot(external)
    project = _project(tmp_path)
    service = _service(project)
    artifacts = ManagedArtifactStore(project.root, project.database, clock=lambda: NOW)
    try:
        first = service.import_bundle(
            external,
            transaction_id="tx.session-first",
            imported_by="expert.one",
        )

        managed_first = service.managed_bundle_path(first.revision.session_revision_id)
        assert first.replayed is False
        assert _snapshot(managed_first) == original
        assert ManifestLoader().load(managed_first).manifest.session_id == first.session.session_id
        assert service.get(first.session.session_id) == first.session
        assert service.get_revision(first.revision.session_revision_id) == first.revision
        assert service.list_sessions() == (first.session,)
        assert service.list_revisions(first.session.session_id) == (first.revision,)
        assert service.verify_managed_revision(first.revision.session_revision_id) == first.revision
        assert artifacts.reference_count(first.revision.ingestion_readiness_ref) == 1
        assert project.database.fetchone("SELECT COUNT(*) FROM session_files")[0] == len(original)

        shutil.rmtree(external)
        replay = service.import_bundle(
            external,
            transaction_id="tx.session-first",
            imported_by="expert.one",
        )
        assert replay.replayed is True
        assert replay.session == first.session
        assert replay.revision == first.revision
        assert _snapshot(managed_first) == original

        shutil.copytree(m4_workflow_bundle, external)
        (external / "operator-notes.txt").write_bytes(b"parallel revision marker")
        second = service.import_bundle(
            external,
            transaction_id="tx.session-second",
            imported_by="expert.one",
        )

        assert second.revision.session_revision_id != first.revision.session_revision_id
        assert service.get(first.session.session_id).current_session_revision_id == (
            second.revision.session_revision_id
        )
        assert service.list_revisions(first.session.session_id) == (
            first.revision,
            second.revision,
        )
        assert _snapshot(managed_first) == original
        assert _snapshot(service.managed_bundle_path(second.revision.session_revision_id)) == (
            _snapshot(external)
        )
    finally:
        project.close()


def test_import_rejects_undeclared_reparse_style_escape(
    tmp_path: Path,
    m4_workflow_bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external = tmp_path / "external-bundle"
    shutil.copytree(m4_workflow_bundle, external)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    simulated_reparse = external / "undeclared-reparse.bin"
    simulated_reparse.write_bytes(b"link-like entry")
    original_check = session_persistence._is_link_or_junction
    monkeypatch.setattr(
        session_persistence,
        "_is_link_or_junction",
        lambda path: path == simulated_reparse or original_check(path),
    )

    project = _project(tmp_path)
    service = _service(project)
    try:
        with pytest.raises(SessionImportPathError, match="link|reparse|junction"):
            service.import_bundle(
                external,
                transaction_id="tx.session-link",
                imported_by="expert.one",
            )
        assert project.database.fetchone("SELECT COUNT(*) FROM sessions")[0] == 0
        assert outside.read_bytes() == b"outside"
    finally:
        project.close()


def test_raw_source_import_materializes_and_registers_managed_bundle(tmp_path: Path) -> None:
    external = _raw_source(tmp_path)
    original = _snapshot(external)
    project = _project(tmp_path)
    service = _service(project)
    try:
        inspected = service.inspect_source(external)
        assert inspected.source_kind is SessionDataSourceKind.SIMULATOR_RAW
        assert inspected.raw is not None

        imported = service.import_source(
            external,
            inspected_fingerprint=inspected.raw.source_snapshot_fingerprint,
            transaction_id="tx.session-raw-first",
            imported_by="expert.one",
        )

        managed = service.managed_bundle_path(imported.revision.session_revision_id)
        loaded = ManifestLoader().load(managed)
        assert imported.replayed is False
        assert _snapshot(external) == original
        assert loaded.manifest.streams["X"].status is StreamStatus.PRESENT
        assert loaded.manifest.streams["U"].units == {}
        assert loaded.manifest.streams["G"].status is StreamStatus.MISSING
        assert (managed / "_pilot_assessment" / "annotations" / "events.json").is_file()
        assert not (managed / "streams" / "gaze").exists()
        assert service.verify_managed_revision(imported.revision.session_revision_id) == (
            imported.revision
        )

        shutil.rmtree(external)
        replay = service.import_source(
            external,
            inspected_fingerprint=inspected.raw.source_snapshot_fingerprint,
            transaction_id="tx.session-raw-first",
            imported_by="expert.one",
        )
        assert replay.replayed is True
        assert replay.session == imported.session
        assert replay.revision == imported.revision
    finally:
        project.close()


def test_raw_source_import_rejects_stale_inspection(tmp_path: Path) -> None:
    external = _raw_source(tmp_path)
    project = _project(tmp_path)
    service = _service(project)
    try:
        inspected = service.inspect_source(external)
        assert inspected.raw is not None
        csv_path = external / "streams" / "simulator.csv"
        csv_path.write_bytes(csv_path.read_bytes() + b"\n")

        with pytest.raises(SessionImportIntegrityError, match="RAW_SOURCE_CHANGED"):
            service.import_source(
                external,
                inspected_fingerprint=inspected.raw.source_snapshot_fingerprint,
                transaction_id="tx.session-raw-changed",
                imported_by="expert.one",
            )
        assert project.database.fetchone("SELECT COUNT(*) FROM sessions")[0] == 0
    finally:
        project.close()
