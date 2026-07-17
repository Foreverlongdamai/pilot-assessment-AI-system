from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

import pilot_assessment.persistence as public_persistence
from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    ModelChangeKind,
    ModelNode,
    ModelObjectLifecycle,
    NodeLayout,
)
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.model_workspace_repository import (
    CurrentObjectConflictError,
    CurrentObjectIntegrityError,
    SqliteModelWorkspaceRepository,
    UndoRedoUnavailableError,
)
from tests.model_workspace.support import seven_node_graph

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _node(nodes: tuple[ModelNode, ...], node_id: str) -> ModelNode:
    return next(node for node in nodes if node.node_id == node_id)


def _diff(path: str, *, metadata: dict[str, str] | None = None) -> CanonicalModelDiff:
    return CanonicalModelDiff(
        changed_paths=(path,),
        added_node_ids=(),
        removed_node_ids=(),
        added_edge_ids=(),
        removed_edge_ids=(),
        metadata={} if metadata is None else metadata,
    )


def _create_node(
    repository: SqliteModelWorkspaceRepository,
    node: ModelNode,
    *,
    event_id: str = "event.node.create",
    join_existing: bool = False,
) -> ModelNode:
    return repository.create_node(
        node,
        event_id=event_id,
        actor_id="expert.one",
        transaction_id=f"tx.{event_id}",
        occurred_at=NOW,
        diff=_diff("/"),
        join_existing=join_existing,
    )


def test_current_model_repository_is_exported_from_public_persistence_package() -> None:
    assert public_persistence.SqliteModelWorkspaceRepository is SqliteModelWorkspaceRepository


def test_current_nodes_and_schemes_round_trip_with_append_only_create_events(tmp_path) -> None:
    nodes, scheme = seven_node_graph()
    precision = _node(nodes, "evidence.precision")
    path = tmp_path / "project.sqlite3"
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        created_node = _create_node(repository, precision)
        created_scheme = repository.create_scheme(
            scheme,
            event_id="event.scheme.create",
            actor_id="expert.one",
            transaction_id="tx.scheme.create",
            occurred_at=NOW,
            diff=_diff("/"),
        )

        assert repository.get_node(precision.node_id) == created_node
        assert repository.get_scheme(scheme.scheme_id) == created_scheme
        assert repository.list_nodes() == (created_node,)
        assert repository.list_schemes() == (created_scheme,)
        assert tuple(event.event_kind for event in repository.node_history(precision.node_id)) == (
            ModelChangeKind.CREATE,
        )
        assert tuple(event.event_kind for event in repository.scheme_history(scheme.scheme_id)) == (
            ModelChangeKind.CREATE,
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute(
                "UPDATE model_change_events SET actor_id = 'tampered' WHERE event_id = ?",
                ("event.node.create",),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute(
                "DELETE FROM model_change_events WHERE event_id = ?",
                ("event.node.create",),
            )
        database.verify_integrity()
    finally:
        database.close()

    reopened = ProjectDatabase.connect(path, clock=lambda: NOW + timedelta(minutes=1))
    try:
        durable = SqliteModelWorkspaceRepository(reopened)
        assert durable.get_node(precision.node_id) == created_node
        assert durable.get_scheme(scheme.scheme_id) == created_scheme
    finally:
        reopened.close()


def test_semantic_and_layout_updates_merge_without_lost_updates_and_check_revisions(
    tmp_path,
) -> None:
    nodes, _ = seven_node_graph()
    original = _node(nodes, "evidence.precision")
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        created = _create_node(repository, original)
        renamed = created.model_copy(update={"name_en": "Renamed precision"})
        semantic = repository.update_node(
            renamed,
            expected_semantic_revision=0,
            expected_layout_revision=None,
            event_id="event.node.rename",
            actor_id="expert.one",
            transaction_id="tx.node.rename",
            occurred_at=NOW + timedelta(seconds=1),
            diff=_diff("/name_en"),
        )
        assert semantic.semantic_revision == 1
        assert semantic.layout_revision == 0
        assert semantic.global_layout == created.global_layout

        stale_layout_proposal = created.model_copy(
            update={
                "global_layout": NodeLayout(
                    node_id=created.node_id,
                    x=777.0,
                    y=888.0,
                )
            }
        )
        moved = repository.update_node(
            stale_layout_proposal,
            expected_semantic_revision=None,
            expected_layout_revision=0,
            event_id="event.node.move",
            actor_id="expert.one",
            transaction_id="tx.node.move",
            occurred_at=NOW + timedelta(seconds=2),
            diff=_diff("/global_layout"),
        )
        assert moved.name_en == "Renamed precision"
        assert moved.semantic_revision == 1
        assert moved.layout_revision == 1
        assert moved.global_layout.x == 777.0

        with pytest.raises(CurrentObjectConflictError, match="semantic revision"):
            repository.update_node(
                renamed,
                expected_semantic_revision=0,
                expected_layout_revision=None,
                event_id="event.node.stale",
                actor_id="expert.one",
                transaction_id="tx.node.stale",
                occurred_at=NOW + timedelta(seconds=3),
                diff=_diff("/name_en"),
            )

        archived = repository.archive_node(
            original.node_id,
            expected_semantic_revision=1,
            event_id="event.node.archive",
            actor_id="expert.one",
            transaction_id="tx.node.archive",
            occurred_at=NOW + timedelta(seconds=4),
            diff=_diff("/lifecycle"),
        )
        assert archived.lifecycle is ModelObjectLifecycle.ARCHIVED
        assert archived.semantic_revision == 2
        assert repository.list_nodes(lifecycle=ModelObjectLifecycle.ACTIVE) == ()
        assert repository.list_nodes(lifecycle=ModelObjectLifecycle.ARCHIVED) == (archived,)
        assert tuple(event.event_kind for event in repository.node_history(original.node_id)) == (
            ModelChangeKind.CREATE,
            ModelChangeKind.UPDATE,
            ModelChangeKind.UPDATE,
            ModelChangeKind.ARCHIVE,
        )
    finally:
        database.close()


def test_undo_redo_keep_monotonic_revisions_and_new_edit_preserves_old_branch(tmp_path) -> None:
    nodes, _ = seven_node_graph()
    original = _node(nodes, "evidence.precision")
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        current = _create_node(repository, original)
        for index, label in enumerate(("Name A", "Name B"), start=1):
            current = repository.update_node(
                current.model_copy(update={"name_en": label}),
                expected_semantic_revision=current.semantic_revision,
                expected_layout_revision=None,
                event_id=f"event.node.rename-{index}",
                actor_id="expert.one",
                transaction_id=f"tx.node.rename-{index}",
                occurred_at=NOW + timedelta(seconds=index),
                diff=_diff("/name_en"),
            )
        assert current.name_en == "Name B"
        assert current.semantic_revision == 2

        first_undo = repository.undo_node(
            original.node_id,
            expected_semantic_revision=2,
            expected_layout_revision=0,
            event_id="event.node.undo-1",
            actor_id="expert.one",
            transaction_id="tx.node.undo-1",
            occurred_at=NOW + timedelta(seconds=3),
        )
        assert first_undo.name_en == "Name A"
        assert first_undo.semantic_revision == 3

        second_undo = repository.undo_node(
            original.node_id,
            expected_semantic_revision=3,
            expected_layout_revision=0,
            event_id="event.node.undo-2",
            actor_id="expert.one",
            transaction_id="tx.node.undo-2",
            occurred_at=NOW + timedelta(seconds=4),
        )
        assert second_undo.name_en == original.name_en
        assert second_undo.semantic_revision == 4

        redone = repository.redo_node(
            original.node_id,
            expected_semantic_revision=4,
            expected_layout_revision=0,
            event_id="event.node.redo-1",
            actor_id="expert.one",
            transaction_id="tx.node.redo-1",
            occurred_at=NOW + timedelta(seconds=5),
        )
        assert redone.name_en == "Name A"
        assert redone.semantic_revision == 5

        branched = repository.update_node(
            redone.model_copy(update={"name_en": "Branch C"}),
            expected_semantic_revision=5,
            expected_layout_revision=None,
            event_id="event.node.branch-c",
            actor_id="expert.one",
            transaction_id="tx.node.branch-c",
            occurred_at=NOW + timedelta(seconds=6),
            diff=_diff("/name_en", metadata={"branch": "new"}),
        )
        assert branched.semantic_revision == 6
        with pytest.raises(UndoRedoUnavailableError, match="redo"):
            repository.redo_node(
                original.node_id,
                expected_semantic_revision=6,
                expected_layout_revision=0,
                event_id="event.node.redo-cleared",
                actor_id="expert.one",
                transaction_id="tx.node.redo-cleared",
                occurred_at=NOW + timedelta(seconds=7),
            )

        history = repository.node_history(original.node_id)
        assert tuple(event.event_kind for event in history) == (
            ModelChangeKind.CREATE,
            ModelChangeKind.UPDATE,
            ModelChangeKind.UPDATE,
            ModelChangeKind.UNDO,
            ModelChangeKind.UNDO,
            ModelChangeKind.REDO,
            ModelChangeKind.UPDATE,
        )
        assert any(event.event_id == "event.node.rename-2" for event in history)
    finally:
        database.close()


def test_scheme_update_archive_and_history_use_the_same_current_object_rules(tmp_path) -> None:
    _, scheme = seven_node_graph()
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        created = repository.create_scheme(
            scheme,
            event_id="event.scheme.create",
            actor_id="expert.one",
            transaction_id="tx.scheme.create",
            occurred_at=NOW,
            diff=_diff("/"),
        )
        proposal = created.model_copy(update={"name_en": "Renamed Scheme"})
        updated = repository.update_scheme(
            proposal,
            expected_semantic_revision=0,
            expected_layout_revision=None,
            event_id="event.scheme.rename",
            actor_id="expert.one",
            transaction_id="tx.scheme.rename",
            occurred_at=NOW + timedelta(seconds=1),
            diff=_diff("/name_en"),
        )
        archived = repository.archive_scheme(
            scheme.scheme_id,
            expected_semantic_revision=1,
            event_id="event.scheme.archive",
            actor_id="expert.one",
            transaction_id="tx.scheme.archive",
            occurred_at=NOW + timedelta(seconds=2),
            diff=_diff("/lifecycle"),
        )
        assert updated.semantic_revision == 1
        assert archived.lifecycle is ModelObjectLifecycle.ARCHIVED
        assert tuple(event.event_kind for event in repository.scheme_history(scheme.scheme_id)) == (
            ModelChangeKind.CREATE,
            ModelChangeKind.UPDATE,
            ModelChangeKind.ARCHIVE,
        )
    finally:
        database.close()


def test_join_existing_transaction_commits_or_rolls_back_model_event_and_audit_together(
    tmp_path,
) -> None:
    nodes, _ = seven_node_graph()
    precision = _node(nodes, "evidence.precision")
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        with pytest.raises(RuntimeError, match="rollback"), database.transaction() as connection:
            _create_node(
                repository,
                precision,
                event_id="event.node.rollback",
                join_existing=True,
            )
            connection.execute(
                """
                INSERT INTO audit_events(
                    audit_event_id, event_type, actor_id, occurred_at,
                    subject_kind, subject_id, transaction_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "audit.rollback",
                    "model.node.create",
                    "expert.one",
                    "2026-07-17T12:00:00Z",
                    "node",
                    precision.node_id,
                    "tx.event.node.rollback",
                    b"{}",
                ),
            )
            raise RuntimeError("rollback")
        assert database.fetchone("SELECT 1 FROM model_nodes") is None
        assert database.fetchone("SELECT 1 FROM model_change_events") is None
        assert database.fetchone("SELECT 1 FROM audit_events") is None

        with database.transaction() as connection:
            _create_node(
                repository,
                precision,
                event_id="event.node.atomic",
                join_existing=True,
            )
            connection.execute(
                """
                INSERT INTO idempotency_transactions(
                    transaction_id, method, request_hash, status,
                    response_json, audit_event_id, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tx.atomic",
                    "model.node.create",
                    "a" * 64,
                    "completed",
                    b"{}",
                    "audit.atomic",
                    "2026-07-17T12:00:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events(
                    audit_event_id, event_type, actor_id, occurred_at,
                    subject_kind, subject_id, transaction_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "audit.atomic",
                    "model.node.create",
                    "expert.one",
                    "2026-07-17T12:00:00Z",
                    "node",
                    precision.node_id,
                    "tx.atomic",
                    b"{}",
                ),
            )
        assert repository.get_node(precision.node_id).node_id == precision.node_id
        assert database.fetchone("SELECT 1 FROM idempotency_transactions") is not None
        assert database.fetchone("SELECT 1 FROM audit_events") is not None
    finally:
        database.close()


def test_stored_current_object_column_or_hash_corruption_is_rejected(tmp_path) -> None:
    nodes, _ = seven_node_graph()
    precision = _node(nodes, "evidence.precision")
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    try:
        _create_node(repository, precision)
        database.execute(
            "UPDATE model_nodes SET content_hash = ? WHERE node_id = ?",
            ("f" * 64, precision.node_id),
        )
        with pytest.raises(CurrentObjectIntegrityError, match="columns"):
            repository.get_node(precision.node_id)
    finally:
        database.close()
