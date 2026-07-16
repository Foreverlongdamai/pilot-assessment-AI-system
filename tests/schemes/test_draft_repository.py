from __future__ import annotations

import pytest

from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind
from pilot_assessment.schemes.operations import (
    CloneComponentVersion,
    MoveLayoutNode,
    SetOutputNodes,
)
from pilot_assessment.schemes.repository import (
    DraftHistoryBoundaryError,
    DraftRevisionConflictError,
)
from tests.schemes.support import build_fixture
from tests.schemes.workspace_support import build_workspace


def test_incomplete_autosave_optimistic_revision_undo_redo_and_branch_truncation() -> None:
    fixture = build_fixture()
    workspace = build_workspace(fixture)
    created = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.history",
        author_id="expert.one",
    )
    emptied = workspace.service.apply_operation(
        created.draft.draft_id,
        SetOutputNodes(expected_graph_version=0, output_node_ids=()),
        author_id="expert.one",
    )

    assert emptied.draft.graph_version == 1
    assert emptied.draft.validation_state.value == "incomplete"
    assert emptied.draft.history_cursor == 1
    with pytest.raises(DraftRevisionConflictError):
        workspace.service.apply_operation(
            created.draft.draft_id,
            SetOutputNodes(expected_graph_version=0, output_node_ids=()),
            author_id="stale.client",
        )

    undone = workspace.service.undo(
        created.draft.draft_id,
        expected_graph_version=1,
        expected_layout_version=0,
        author_id="expert.one",
    )
    assert undone.draft.output_node_ids == fixture.scheme.output_node_ids
    assert undone.draft.graph_version == 2
    assert undone.draft.history_cursor == 0
    redone = workspace.service.redo(
        created.draft.draft_id,
        expected_graph_version=2,
        expected_layout_version=0,
        author_id="expert.one",
    )
    assert redone.draft.output_node_ids == ()
    assert redone.draft.graph_version == 3
    assert redone.draft.history_cursor == 1

    branched_from = workspace.service.undo(
        created.draft.draft_id,
        expected_graph_version=3,
        expected_layout_version=0,
        author_id="expert.one",
    )
    branched = workspace.service.apply_operation(
        created.draft.draft_id,
        SetOutputNodes(
            expected_graph_version=branched_from.draft.graph_version,
            output_node_ids=(
                ComponentIdRef(
                    kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                    version_id=fixture.scheme.evidence_binding_versions[0].version_id,
                ),
            ),
        ),
        author_id="expert.one",
    )
    assert branched.draft.history_cursor == 1
    with pytest.raises(DraftHistoryBoundaryError):
        workspace.service.redo(
            created.draft.draft_id,
            expected_graph_version=branched.draft.graph_version,
            expected_layout_version=0,
            author_id="expert.one",
        )


def test_layout_operation_uses_independent_layout_revision() -> None:
    fixture = build_fixture()
    workspace = build_workspace(fixture)
    draft = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.layout",
        author_id="expert.one",
    ).draft
    layout = fixture.scheme.layout
    draft = workspace.service.apply_operation(
        draft.draft_id,
        CloneComponentVersion(
            expected_graph_version=0,
            source=ComponentIdRef(kind=layout.kind, version_id=layout.version_id),
            candidate_id="candidate.layout",
            replace_source=True,
        ),
        author_id="expert.one",
    ).draft
    moved = workspace.service.apply_operation(
        draft.draft_id,
        MoveLayoutNode(
            expected_layout_version=0,
            candidate_id="candidate.layout",
            node_id="bn-version.alpha-v2",
            x=42.0,
            y=24.0,
        ),
        author_id="expert.one",
    )

    assert moved.draft.graph_version == 1
    assert moved.draft.layout_version == 1
    layout_candidate = next(
        item for item in moved.draft.candidate_components if item.candidate_id == "candidate.layout"
    )
    positions = layout_candidate.payload["node_positions"]
    assert isinstance(positions, list)
    assert positions[0] == {
        "node_id": "bn-version.alpha-v2",
        "x": 42.0,
        "y": 24.0,
    }
    with pytest.raises(DraftRevisionConflictError):
        workspace.service.apply_operation(
            draft.draft_id,
            MoveLayoutNode(
                expected_layout_version=0,
                candidate_id="candidate.layout",
                node_id="bn-version.alpha-v2",
                x=0.0,
                y=0.0,
            ),
            author_id="stale.client",
        )
