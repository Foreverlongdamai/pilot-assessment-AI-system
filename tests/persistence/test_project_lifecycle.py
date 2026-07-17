from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.persistence.project import (
    PROJECT_DIRECTORY_NAMES,
    PROJECT_LOCATOR_NAME,
    ProjectAlreadyExistsError,
    ProjectFormatError,
    ProjectStore,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_project_create_close_move_and_reopen_uses_only_relative_storage(tmp_path) -> None:
    original_root = tmp_path / "alpha-project"
    project = ProjectStore.create(
        original_root,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )

    assert project.descriptor.project_id == "project.alpha"
    assert [
        row["version"]
        for row in project.database.fetchall(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ] == [1, 2, 3]
    assert project.root == original_root.resolve()
    assert {path.name for path in original_root.iterdir() if path.is_dir()} == set(
        PROJECT_DIRECTORY_NAMES
    )
    locator = json.loads((original_root / PROJECT_LOCATOR_NAME).read_text(encoding="utf-8"))
    assert locator["database_path"] == "project.sqlite3"
    assert "absolute_root" not in locator
    project.close()

    moved_root = tmp_path / "moved" / "alpha-project"
    moved_root.parent.mkdir()
    shutil.move(original_root, moved_root)

    reopened = ProjectStore.open(moved_root, clock=lambda: NOW + timedelta(minutes=1))
    try:
        assert reopened.descriptor == project.descriptor
        assert reopened.root == moved_root.resolve()
        assert reopened.recovery_diagnostics == ()
    finally:
        reopened.close()

    database_bytes = (moved_root / "project.sqlite3").read_bytes()
    assert str(original_root.resolve()).encode() not in database_bytes
    assert str(moved_root.resolve()).encode() not in database_bytes


def test_project_create_refuses_to_adopt_a_nonempty_directory(tmp_path) -> None:
    project_root = tmp_path / "occupied"
    project_root.mkdir()
    (project_root / "unrelated.txt").write_text("preserve me", encoding="utf-8")

    with pytest.raises(ProjectAlreadyExistsError):
        ProjectStore.create(
            project_root,
            project_id="project.alpha",
            name="Alpha project",
            created_at=NOW,
            clock=lambda: NOW,
        )
    assert (project_root / "unrelated.txt").read_text(encoding="utf-8") == "preserve me"


def test_project_open_rejects_locator_path_escape_before_opening_database(tmp_path) -> None:
    project_root = tmp_path / "alpha"
    project = ProjectStore.create(
        project_root,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    project.close()

    locator_path = project_root / PROJECT_LOCATOR_NAME
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["database_path"] = "../outside.sqlite3"
    locator_path.write_text(json.dumps(locator), encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="database_path"):
        ProjectStore.open(project_root, clock=lambda: NOW)
    assert not (tmp_path / "outside.sqlite3").exists()


def test_project_open_reports_previous_unclean_shutdown_without_losing_state(tmp_path) -> None:
    project_root = tmp_path / "alpha"
    project = ProjectStore.create(
        project_root,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    project.close()

    raw = sqlite3.connect(project_root / "project.sqlite3")
    try:
        raw.execute("UPDATE project_metadata SET clean_shutdown = 0")
        raw.commit()
    finally:
        raw.close()

    reopened = ProjectStore.open(project_root, clock=lambda: NOW + timedelta(minutes=1))
    try:
        assert reopened.recovery_diagnostics == ("previous_shutdown_unclean",)
        row = reopened.database.fetchone("SELECT project_id, clean_shutdown FROM project_metadata")
        assert tuple(row) == ("project.alpha", 0)
    finally:
        reopened.close()
