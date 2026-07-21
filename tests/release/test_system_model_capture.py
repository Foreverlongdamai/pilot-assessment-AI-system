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


def test_capture_preserves_saved_dynamic_model_and_rebuilds_clean_workspace(
    tmp_path: Path,
) -> None:
    _, capture_current_system, inspect_system_source = _capture_api()

    source = tmp_path / "source-system"
    target = tmp_path / "captured-system"
    app = SystemApplication.open_or_create(source, clock=lambda: NOW)
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
    expected_nodes = len(app.current_model.list_nodes())
    expected_schemes = len(app.current_model.list_schemes())
    app.close()

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
