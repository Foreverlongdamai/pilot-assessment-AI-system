from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.runtime import SystemApplication

NOW = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)
RELEASE_TOOLS = Path(__file__).resolve().parents[2] / "tools" / "release"
sys.path.insert(0, str(RELEASE_TOOLS))


def _capture_api():
    from system_model_capture import (
        SystemCaptureError,
        capture_current_system,
        inspect_system_source,
    )

    return SystemCaptureError, capture_current_system, inspect_system_source


def _create_closed_system(root: Path) -> Path:
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    app.close()
    return root


def _create_saved_dynamic_system(root: Path) -> tuple[Path, int, int]:
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    base_node = app.editable_model.list_nodes()[0]
    base_scheme = app.editable_model.list_schemes()[0]
    app.editable_model.copy_node(
        base_node.node_id,
        transaction_id="tx.m8d.copy-node",
        actor_id="expert.test",
    )
    app.editable_model.copy_scheme(
        base_scheme.scheme_id,
        new_scheme_id="task-scheme.m8d.parallel",
        name_zh=None,
        name_en="M8D Parallel",
        transaction_id="tx.m8d.copy-scheme",
        actor_id="expert.test",
    )
    app.model_edits.commit(
        transaction_id="tx.m8d.save",
        actor_id="expert.test",
    )
    node_count = len(app.current_model.list_nodes())
    scheme_count = len(app.current_model.list_schemes())
    app.close()
    return root, node_count, scheme_count


def test_capture_preserves_saved_dynamic_model_and_rebuilds_clean_workspace(
    tmp_path: Path,
) -> None:
    _, capture_current_system, inspect_system_source = _capture_api()

    source, expected_nodes, expected_schemes = _create_saved_dynamic_system(
        tmp_path / "source-system"
    )
    target = tmp_path / "captured-system"

    source_report = capture_current_system(source, target)
    captured = SystemApplication.open_or_create(target, clock=lambda: NOW)
    captured.close()
    target_report = inspect_system_source(target)

    assert target_report.model_library_id == source_report.model_library_id
    assert target_report.model_identity_sha256 == source_report.model_identity_sha256
    assert (target_report.node_count, target_report.scheme_count) == (
        expected_nodes,
        expected_schemes,
    )
    assert target_report.user_owned_row_counts == source_report.user_owned_row_counts
    assert not any(target_report.user_owned_row_counts.values())


def test_v2_baseline_and_verifier_accept_dynamic_captured_facts(tmp_path: Path) -> None:
    from build_portable import _sha256, _system_model_baseline, _write_json
    from verify_portable import _verify_system_model_baseline

    _, capture_current_system, _ = _capture_api()
    source, node_count, scheme_count = _create_saved_dynamic_system(
        tmp_path / "source-system"
    )
    package_root = tmp_path / "package"
    target = package_root / "system"
    report = capture_current_system(source, target)
    captured = SystemApplication.open_or_create(target, clock=lambda: NOW)
    captured.close()
    (target / ".system-writer.lock").unlink()

    baseline = _system_model_baseline(package_root, capture_report=report)
    assert baseline["schema_version"] == "pilot-assessment-system-model-baseline-v2"
    assert baseline["capture_mode"] == "explicit-current-system"
    assert baseline["node_count"] == node_count
    assert baseline["scheme_count"] == scheme_count
    assert baseline["model_identity_sha256"] == report.model_identity_sha256
    baseline_path = package_root / "manifest" / "system-model-baseline.json"
    _write_json(baseline_path, baseline)
    _write_json(
        package_root / "manifest" / "release-manifest.json",
        {
            "system_model_baseline_sha256": _sha256(baseline_path),
            "system_model": {
                "baseline": "manifest/system-model-baseline.json",
                "capture_mode": "explicit-current-system",
                "model_library_id": report.model_library_id,
                "model_identity_sha256": report.model_identity_sha256,
                "node_count": node_count,
                "scheme_count": scheme_count,
            },
        },
    )

    verified = _verify_system_model_baseline(package_root)
    assert verified["model_identity_sha256"] == report.model_identity_sha256
    assert verified["node_count"] == node_count
    assert verified["scheme_count"] == scheme_count


def test_builder_refuses_system_source_inside_recreated_package_root(tmp_path: Path) -> None:
    from build_portable import ReleaseBuildError, _require_external_system_source

    package_root = tmp_path / "PilotAssessment-0.1.0-win-x64"
    source = package_root / "system"
    with pytest.raises(ReleaseBuildError, match="inside the package output"):
        _require_external_system_source(source, package_root)


def test_runtime_system_model_comparison_rejects_manifest_drift() -> None:
    from verify_portable import (
        PortableVerificationError,
        _verify_runtime_system_model,
    )

    baseline = {
        "model_library_id": "model-library.alpha",
        "model_identity_sha256": "a" * 64,
        "node_count": 54,
        "scheme_count": 2,
    }
    runtime = {
        **baseline,
        "format_version": "0.1.0",
        "database_schema_version": 5,
        "edit_session_dirty": False,
        "recovery_diagnostics": [],
    }
    _verify_runtime_system_model(runtime, baseline)

    with pytest.raises(PortableVerificationError, match="runtime system model"):
        _verify_runtime_system_model({**runtime, "node_count": 55}, baseline)


def test_inspection_rejects_active_writer(tmp_path: Path) -> None:
    SystemCaptureError, _, inspect_system_source = _capture_api()
    root = tmp_path / "system"
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    try:
        with pytest.raises(SystemCaptureError, match="close the application"):
            inspect_system_source(root)
    finally:
        app.close()


def test_inspection_rejects_closed_but_dirty_edit_session(tmp_path: Path) -> None:
    SystemCaptureError, _, inspect_system_source = _capture_api()
    root = tmp_path / "system"
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    current = app.editable_model.list_nodes()[0]
    proposal = current.model_copy(update={"name_en": f"{current.name_en} Draft"})
    with app.model_edits.database.transaction() as connection:
        app.editable_model.update_node(
            proposal,
            expected_semantic_revision=current.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.m8d.dirty",
            actor_id="expert.test",
        )
        app.model_edits.capture_checkpoint(
            connection,
            transaction_id="tx.m8d.dirty",
            method="model.node.update",
        )
    app.close()

    with pytest.raises(SystemCaptureError, match="save or discard"):
        inspect_system_source(root)


def test_inspection_rejects_user_owned_rows(tmp_path: Path) -> None:
    SystemCaptureError, _, inspect_system_source = _capture_api()
    root = _create_closed_system(tmp_path / "system")
    database = sqlite3.connect(root / "model-library.sqlite3")
    try:
        database.execute(
            """
            INSERT INTO project_metadata(
                singleton, project_id, format_version, name, created_at,
                clean_shutdown, last_opened_at, last_closed_at
            ) VALUES (1, 'project.forbidden', '0.1.0', 'Forbidden', ?, 1, ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
        )
        database.commit()
        database.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        database.close()

    with pytest.raises(SystemCaptureError, match="user-owned rows"):
        inspect_system_source(root)


def test_capture_omits_legacy_import_receipt_without_mutating_source(
    tmp_path: Path,
) -> None:
    _, capture_current_system, _ = _capture_api()
    source = _create_closed_system(tmp_path / "system")
    database = sqlite3.connect(source / "model-library.sqlite3")
    try:
        database.execute(
            """
            INSERT INTO legacy_system_model_import_receipts(
                import_fingerprint, source_project_id, canonical_fingerprint,
                legacy_edit_fingerprint, node_mapping_json, scheme_mapping_json,
                inserted_node_count, inserted_scheme_count, reused_node_count,
                reused_scheme_count, dirty_edit_recovered, imported_at
            ) VALUES (?, ?, ?, NULL, ?, ?, 1, 1, 0, 0, 0, ?)
            """,
            (
                "a" * 64,
                "project.source-local",
                "b" * 64,
                b"{}",
                b"{}",
                NOW.isoformat(),
            ),
        )
        database.commit()
        database.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        database.close()

    target = tmp_path / "captured-system"
    capture_current_system(source, target)

    source_database = sqlite3.connect(source / "model-library.sqlite3")
    target_database = sqlite3.connect(target / "model-library.sqlite3")
    try:
        assert source_database.execute(
            "SELECT COUNT(*) FROM legacy_system_model_import_receipts"
        ).fetchone() == (1,)
        assert target_database.execute(
            "SELECT COUNT(*) FROM legacy_system_model_import_receipts"
        ).fetchone() == (0,)
    finally:
        source_database.close()
        target_database.close()
    assert b"project.source-local" in (source / "model-library.sqlite3").read_bytes()
    assert b"project.source-local" not in (target / "model-library.sqlite3").read_bytes()


def test_inspection_rejects_future_schema(tmp_path: Path) -> None:
    SystemCaptureError, _, inspect_system_source = _capture_api()
    root = _create_closed_system(tmp_path / "future-system")
    database = sqlite3.connect(root / "model-library.sqlite3")
    try:
        database.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (6, ?, ?)",
            ("future_schema", NOW.isoformat()),
        )
        database.commit()
        database.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        database.close()

    with pytest.raises(SystemCaptureError, match="unsupported schema"):
        inspect_system_source(root)


def test_inspection_rejects_corrupt_database(tmp_path: Path) -> None:
    SystemCaptureError, _, inspect_system_source = _capture_api()
    root = _create_closed_system(tmp_path / "corrupt-system")
    (root / "model-library.sqlite3").write_bytes(b"not a SQLite database")

    with pytest.raises(SystemCaptureError, match="database|integrity"):
        inspect_system_source(root)
