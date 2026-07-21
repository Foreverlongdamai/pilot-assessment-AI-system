from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.run import CurrentModelRunSnapshotV3, RunPurpose
from pilot_assessment.runtime import ProjectApplication, SystemApplication

NOW = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)


def _product_root(root: Path) -> Path:
    package = root / "src" / "pilot_assessment"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("SOURCE_MARKER = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='run-provenance-fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return root


def _prepare_run(
    application: ProjectApplication,
    *,
    session_revision_id: str,
    run_id: str,
) -> CurrentModelRunSnapshotV3:
    scheme = application.current_model.get_scheme(application.current_starter_scheme_id)
    report = application.current_preflight.prepare(
        session_revision_id=session_revision_id,
        scheme_id=scheme.scheme_id,
        purpose=RunPurpose.SOFTWARE_TEST,
        runtime_parameters={},
    )
    run = application.current_preflight.create_run(
        report.preflight_id,
        run_id=run_id,
        expected_scheme_revision=scheme.semantic_revision,
        requested_at=NOW,
    )
    assert isinstance(run.snapshot, CurrentModelRunSnapshotV3)
    return run.snapshot


def test_restart_after_source_edit_creates_new_identity_without_rewriting_old_run(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    product_root = _product_root(tmp_path / "product")
    system_root = tmp_path / "system"
    project_root = tmp_path / "project"
    external = tmp_path / "external"
    shutil.copytree(m4_workflow_bundle, external)

    first_system = SystemApplication.open_or_create(
        system_root,
        model_library_id="model-library.source-boundary",
        product_root=product_root,
        clock=lambda: NOW,
    )
    first_app = ProjectApplication.create(
        project_root,
        system=first_system,
        project_id="project.source-boundary",
        name="Source boundary",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        imported = first_app.sessions.import_bundle(
            external,
            transaction_id="tx.source-boundary-import",
            imported_by="expert.test",
        )
        revision_id = imported.revision.session_revision_id
        first_snapshot = _prepare_run(
            first_app,
            session_revision_id=revision_id,
            run_id="run.source-before",
        )
        first_snapshot_bytes = first_snapshot.model_dump_json()
    finally:
        first_app.close()
        first_system.close()

    (product_root / "src" / "pilot_assessment" / "__init__.py").write_text(
        "SOURCE_MARKER = 2\n",
        encoding="utf-8",
    )

    second_system = SystemApplication.open_or_create(
        system_root,
        model_library_id="model-library.source-boundary",
        product_root=product_root,
        clock=lambda: NOW,
    )
    second_app = ProjectApplication.open(project_root, system=second_system, clock=lambda: NOW)
    try:
        old_run = second_app.runs.get("run.source-before")
        assert old_run.snapshot.model_dump_json() == first_snapshot_bytes

        second_snapshot = _prepare_run(
            second_app,
            session_revision_id=revision_id,
            run_id="run.source-after",
        )
        assert (
            second_snapshot.backend_source_identity.source_tree_sha256
            != first_snapshot.backend_source_identity.source_tree_sha256
        )
        assert second_snapshot.source_snapshot_ref != first_snapshot.source_snapshot_ref
        assert second_app.artifacts.get(first_snapshot.source_snapshot_ref.artifact_id)
        assert second_app.artifacts.get(second_snapshot.source_snapshot_ref.artifact_id)
    finally:
        second_app.close()
        second_system.close()
