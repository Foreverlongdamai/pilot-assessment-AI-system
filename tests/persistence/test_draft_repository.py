from __future__ import annotations

from datetime import timedelta

import pytest

from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.draft_repository import SqliteSchemeDraftRepository
from pilot_assessment.schemes.operations import OperationDiff
from pilot_assessment.schemes.repository import (
    DraftHistoryBoundaryError,
    DraftRevisionConflictError,
)
from tests.schemes.support import NOW, build_fixture
from tests.schemes.workspace_support import FrozenClock, build_workspace


def _draft(draft_id: str):
    fixture = build_fixture()
    workspace = build_workspace(fixture)
    return fixture, workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id=draft_id,
        author_id="expert.one",
    ).draft


def test_draft_history_survives_reopen_and_branch_truncates_redo(tmp_path) -> None:
    fixture, draft = _draft("draft.history")
    path = tmp_path / "project.sqlite3"
    clock = FrozenClock(NOW)
    database = ProjectDatabase.connect(path, clock=clock.now)
    repository = SqliteSchemeDraftRepository(database, clock=clock.now)
    repository.create(draft, author_id="expert.one")
    emptied = repository.save(
        draft.model_copy(update={"output_node_ids": ()}),
        expected_graph_version=0,
        expected_layout_version=None,
        graph_changed=True,
        layout_changed=False,
        diff=OperationDiff(operation_type="SetOutputNodes", changed_paths=("/output_node_ids",)),
        author_id="expert.one",
    )
    assert emptied.draft.graph_version == 1
    assert emptied.draft.history_cursor == 1
    with pytest.raises(DraftRevisionConflictError):
        repository.save(
            draft,
            expected_graph_version=0,
            expected_layout_version=None,
            graph_changed=True,
            layout_changed=False,
            diff=OperationDiff(operation_type="Stale", changed_paths=("/",)),
            author_id="stale.client",
        )

    clock.value += timedelta(minutes=1)
    undone = repository.undo(
        draft.draft_id,
        expected_graph_version=1,
        expected_layout_version=0,
        author_id="expert.one",
    )
    assert undone.draft.output_node_ids == fixture.scheme.output_node_ids
    assert undone.draft.graph_version == 2
    assert undone.draft.history_cursor == 0
    database.close()

    reopened_database = ProjectDatabase.connect(path, clock=clock.now)
    reopened = SqliteSchemeDraftRepository(reopened_database, clock=clock.now)
    try:
        persisted = reopened.get(draft.draft_id)
        assert persisted.draft == undone.draft
        redone = reopened.redo(
            draft.draft_id,
            expected_graph_version=2,
            expected_layout_version=0,
            author_id="expert.one",
        )
        assert redone.draft.output_node_ids == ()
        assert redone.draft.graph_version == 3
        assert redone.draft.history_cursor == 1

        branched_from = reopened.undo(
            draft.draft_id,
            expected_graph_version=3,
            expected_layout_version=0,
            author_id="expert.one",
        )
        alternative = (
            ComponentIdRef(
                kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                version_id=fixture.scheme.evidence_binding_versions[0].version_id,
            ),
        )
        branched = reopened.save(
            branched_from.draft.model_copy(update={"output_node_ids": alternative}),
            expected_graph_version=branched_from.draft.graph_version,
            expected_layout_version=None,
            graph_changed=True,
            layout_changed=False,
            diff=OperationDiff(
                operation_type="SetOutputNodes", changed_paths=("/output_node_ids",)
            ),
            author_id="expert.one",
        )
        with pytest.raises(DraftHistoryBoundaryError):
            reopened.redo(
                draft.draft_id,
                expected_graph_version=branched.draft.graph_version,
                expected_layout_version=branched.draft.layout_version,
                author_id="expert.one",
            )
        assert (
            reopened_database.fetchone(
                "SELECT COUNT(*) FROM draft_snapshots WHERE draft_id = ?", (draft.draft_id,)
            )[0]
            == 2
        )
        assert (
            reopened_database.fetchone(
                "SELECT COUNT(*) FROM draft_transitions WHERE draft_id = ?", (draft.draft_id,)
            )[0]
            == 1
        )
    finally:
        reopened_database.close()


def test_layout_revision_is_independent_and_optimistic(tmp_path) -> None:
    _, draft = _draft("draft.layout")
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteSchemeDraftRepository(database, clock=lambda: NOW)
    try:
        repository.create(draft, author_id="expert.one")
        moved = repository.save(
            draft,
            expected_graph_version=None,
            expected_layout_version=0,
            graph_changed=False,
            layout_changed=True,
            diff=OperationDiff(operation_type="MoveLayoutNode", changed_paths=("/layout",)),
            author_id="expert.one",
        )
        assert moved.draft.graph_version == 0
        assert moved.draft.layout_version == 1
        with pytest.raises(DraftRevisionConflictError):
            repository.save(
                draft,
                expected_graph_version=None,
                expected_layout_version=0,
                graph_changed=False,
                layout_changed=True,
                diff=OperationDiff(operation_type="MoveLayoutNode", changed_paths=("/layout",)),
                author_id="stale.client",
            )
    finally:
        database.close()
