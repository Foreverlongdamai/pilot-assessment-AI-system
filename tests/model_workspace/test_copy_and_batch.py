from __future__ import annotations

from pathlib import Path

import pytest

from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelNodeKind,
    NodeLayout,
)
from pilot_assessment.model_workspace.service import CurrentSchemeRevisionConflict
from tests.model_workspace.support import seven_node_graph
from tests.model_workspace.test_scheme_service import _workspace


def _create_base(service):
    _, base = seven_node_graph()
    return service.create_scheme(
        base,
        transaction_id="tx.scheme.base.create",
        actor_id="expert.one",
    ).scheme


def test_copy_node_deep_copies_complete_definition_and_keeps_fixed_parents(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        source = service.get_node("evidence.precision")
        source_definition = source.definition
        assert isinstance(source_definition, EvidenceNodeDefinition)
        result = service.copy_node(
            source.node_id,
            transaction_id="tx.node.precision.copy",
            actor_id="expert.one",
        )
        copied = result.node
        copied_definition = copied.definition
        assert isinstance(copied_definition, EvidenceNodeDefinition)

        assert copied.node_id != source.node_id
        assert copied.copied_from_node_id == source.node_id
        assert copied.node_kind is source.node_kind
        assert copied.name == source.name
        assert copied_definition.recipe == source_definition.recipe
        assert copied_definition.recipe is not source_definition.recipe
        assert (
            copied_definition.ordered_probabilistic_parent_nodes
            == source_definition.ordered_probabilistic_parent_nodes
        )
        assert copied_definition.data_bindings == source_definition.data_bindings
        assert (
            copied_definition.cpt.materialized_probabilities
            == source_definition.cpt.materialized_probabilities
        )
        assert copied_definition.cpt.child_node.node_id == copied.node_id
        assert copied_definition.cpt.child_node.node_kind is ModelNodeKind.EVIDENCE
        assert copied_definition.cpt.cpt_id != source_definition.cpt.cpt_id
        assert len(service.list_nodes()) == 8
        assert result.affected_scheme_ids == ()
    finally:
        database.close()


def test_paste_node_and_scheme_activation_are_atomic_and_do_not_retarget_children(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base = _create_base(service)
        with pytest.raises(CurrentSchemeRevisionConflict):
            service.copy_node_to_scheme(
                "bn.skill",
                base.scheme_id,
                expected_semantic_revision=base.semantic_revision,
                expected_layout_revision=99,
                transaction_id="tx.paste.skill.stale",
                actor_id="expert.one",
            )
        assert len(service.list_nodes()) == 7

        result = service.copy_node_to_scheme(
            "bn.skill",
            base.scheme_id,
            expected_semantic_revision=base.semantic_revision,
            expected_layout_revision=base.layout_revision,
            transaction_id="tx.paste.skill",
            actor_id="expert.one",
        )
        assert len(result.copied_nodes) == 1
        copied = result.copied_nodes[0]
        definition = copied.definition
        assert isinstance(definition, BnNodeDefinition)
        assert copied.copied_from_node_id == "bn.skill"
        assert tuple(
            parent.node_id for parent in definition.ordered_probabilistic_parent_nodes
        ) == ("bn.competency",)
        assert copied.node_id in result.scheme.explicit_active_node_ids
        assert "bn.skill" in result.scheme.computed_active_closure
        assert "evidence.precision" in result.scheme.explicit_active_node_ids
        assert any(layout.node_id == copied.node_id for layout in result.scheme.layout_overrides)

        precision = service.get_node("evidence.precision")
        precision_definition = precision.definition
        assert isinstance(precision_definition, EvidenceNodeDefinition)
        assert tuple(
            parent.node_id for parent in precision_definition.ordered_probabilistic_parent_nodes
        ) == ("bn.skill",)
        assert len(service.list_nodes()) == 8
    finally:
        database.close()


def test_graph_batch_applies_copy_activation_and_layout_with_one_canonical_diff(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base = _create_base(service)
        result = service.apply_graph_batch(
            base.scheme_id,
            copy_node_ids=("evidence.precision",),
            activate_node_ids=("evidence.gaze",),
            layout_updates=(NodeLayout(node_id="evidence.precision", x=900.0, y=700.0),),
            expected_semantic_revision=base.semantic_revision,
            expected_layout_revision=base.layout_revision,
            transaction_id="tx.graph.batch-one",
            actor_id="expert.one",
        )

        assert len(result.copied_nodes) == 1
        copied = result.copied_nodes[0]
        assert copied.node_id in result.scheme.explicit_active_node_ids
        assert "evidence.precision" in result.scheme.explicit_active_node_ids
        assert "evidence.gaze" in result.scheme.explicit_active_node_ids
        assert "raw.g" in result.scheme.computed_active_closure
        assert result.scheme.semantic_revision == 1
        assert result.scheme.layout_revision == 1
        assert next(
            layout
            for layout in result.scheme.layout_overrides
            if layout.node_id == "evidence.precision"
        ) == NodeLayout(node_id="evidence.precision", x=900.0, y=700.0)
        assert any(layout.node_id == copied.node_id for layout in result.scheme.layout_overrides)
        assert copied.node_id in result.diff.added_node_ids
        assert "evidence.gaze" in result.diff.added_node_ids
        assert result.diff.metadata["mutation"] == "graph_batch_apply"
        assert result.diff.metadata["copied_nodes"] == [
            {
                "source_node_id": "evidence.precision",
                "new_node_id": copied.node_id,
            }
        ]
        assert len(service.scheme_history(base.scheme_id)) == 2
        assert len(service.node_history(copied.node_id)) == 1
        assert result.graph.scheme == result.scheme
    finally:
        database.close()


def test_graph_batch_persists_raw_family_display_layout_without_a_model_node(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base = _create_base(service)

        result = service.apply_graph_batch(
            base.scheme_id,
            layout_updates=(NodeLayout(node_id="raw-family.X", x=310.0, y=270.0),),
            expected_semantic_revision=base.semantic_revision,
            expected_layout_revision=base.layout_revision,
            transaction_id="tx.graph.raw-family-layout",
            actor_id="expert.one",
        )

        assert result.scheme.semantic_revision == base.semantic_revision
        assert result.scheme.layout_revision == base.layout_revision + 1
        assert NodeLayout(node_id="raw-family.X", x=310.0, y=270.0) in (
            result.scheme.layout_overrides
        )
    finally:
        database.close()
