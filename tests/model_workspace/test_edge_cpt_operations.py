from __future__ import annotations

from pathlib import Path

import pytest

from pilot_assessment.contracts.model_components import CptMode, VariableState
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelTechnicalStatus,
)
from pilot_assessment.model_workspace.service import CurrentModelOperationError
from tests.model_workspace.support import seven_node_graph
from tests.model_workspace.test_scheme_service import _workspace


def test_probabilistic_parent_add_reorder_and_remove_migrate_one_child_cpt(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        original = service.get_node("evidence.precision")
        original_definition = original.definition
        assert isinstance(original_definition, EvidenceNodeDefinition)
        original_rows = original_definition.cpt.materialized_probabilities

        added = service.add_probabilistic_edge(
            original.node_id,
            "bn.competency",
            strategy="preserve_independence",
            expected_semantic_revision=original.semantic_revision,
            transaction_id="tx.edge.add-competency",
            actor_id="expert.one",
        )
        added_definition = added.node.definition
        assert isinstance(added_definition, EvidenceNodeDefinition)
        assert tuple(
            parent.node_id for parent in added_definition.ordered_probabilistic_parent_nodes
        ) == ("bn.skill", "bn.competency")
        assert added_definition.cpt.ordered_parent_nodes == (
            added_definition.ordered_probabilistic_parent_nodes
        )
        assert len(added_definition.cpt.materialized_probabilities) == 9
        assert added.editor.required_row_count == 9

        reordered = service.reorder_probabilistic_parents(
            original.node_id,
            ("bn.competency", "bn.skill"),
            expected_semantic_revision=added.semantic_revision,
            transaction_id="tx.edge.reorder-parents",
            actor_id="expert.one",
        )
        reordered_definition = reordered.node.definition
        assert isinstance(reordered_definition, EvidenceNodeDefinition)
        assert tuple(
            parent.node_id for parent in reordered_definition.ordered_probabilistic_parent_nodes
        ) == ("bn.competency", "bn.skill")
        assert reordered_definition.cpt.ordered_parent_nodes == (
            reordered_definition.ordered_probabilistic_parent_nodes
        )

        removed = service.remove_probabilistic_edge(
            original.node_id,
            "bn.competency",
            strategy="marginalize",
            marginal_weights=(1 / 3, 1 / 3, 1 / 3),
            expected_semantic_revision=reordered.semantic_revision,
            transaction_id="tx.edge.remove-competency",
            actor_id="expert.one",
        )
        removed_definition = removed.node.definition
        assert isinstance(removed_definition, EvidenceNodeDefinition)
        assert tuple(
            parent.node_id for parent in removed_definition.ordered_probabilistic_parent_nodes
        ) == ("bn.skill",)
        for actual, expected in zip(
            removed_definition.cpt.materialized_probabilities,
            original_rows,
            strict=True,
        ):
            assert actual == pytest.approx(expected)
        assert service.validate_current_cpt(original.node_id).executable is True
    finally:
        database.close()


def test_extraction_edge_is_derived_from_recipe_and_data_binding_without_ghost_row(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        precision = service.get_node("evidence.precision")
        gaze = service.get_node("evidence.gaze")
        precision_definition = precision.definition
        gaze_definition = gaze.definition
        assert isinstance(precision_definition, EvidenceNodeDefinition)
        assert isinstance(gaze_definition, EvidenceNodeDefinition)
        extra_input = gaze_definition.recipe.inputs[0].model_copy(
            update={"binding_id": "extra-gaze"}
        )
        extra_node = gaze_definition.recipe.graph.nodes[0].model_copy(
            update={
                "node_id": "input-extra-gaze",
                "input_binding_id": "extra-gaze",
            }
        )
        added_recipe = precision_definition.recipe.model_copy(
            update={
                "inputs": (*precision_definition.recipe.inputs, extra_input),
                "graph": precision_definition.recipe.graph.model_copy(
                    update={"nodes": (*precision_definition.recipe.graph.nodes, extra_node)}
                ),
            }
        )
        added = service.add_extraction_edge(
            precision.node_id,
            "raw.g",
            "extra-gaze",
            added_recipe,
            expected_semantic_revision=precision.semantic_revision,
            transaction_id="tx.extraction.add-gaze",
            actor_id="expert.one",
        )
        added_definition = added.node.definition
        assert isinstance(added_definition, EvidenceNodeDefinition)
        assert {item.recipe_input_binding_id for item in added_definition.data_bindings} == {
            "flight-x",
            "control-u",
            "extra-gaze",
        }
        assert len(added.diff.added_edge_ids) == 1

        removed_recipe = added_definition.recipe.model_copy(
            update={
                "inputs": tuple(
                    item
                    for item in added_definition.recipe.inputs
                    if item.binding_id != "extra-gaze"
                ),
                "graph": added_definition.recipe.graph.model_copy(
                    update={
                        "nodes": tuple(
                            item
                            for item in added_definition.recipe.graph.nodes
                            if item.node_id != "input-extra-gaze"
                        )
                    }
                ),
            }
        )
        removed = service.remove_extraction_edge(
            precision.node_id,
            "extra-gaze",
            removed_recipe,
            expected_semantic_revision=added.semantic_revision,
            transaction_id="tx.extraction.remove-gaze",
            actor_id="expert.one",
        )
        removed_definition = removed.node.definition
        assert isinstance(removed_definition, EvidenceNodeDefinition)
        assert removed_definition.data_bindings == precision_definition.data_bindings
        assert len(removed.diff.removed_edge_ids) == 1
    finally:
        database.close()


def test_cpt_batch_update_rejects_invalid_rows_without_write_and_materializes_uniform(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        root = service.get_node("bn.competency")
        with pytest.raises(CurrentModelOperationError) as captured:
            service.update_cpt_rows(
                root.node_id,
                ((0.2, 0.2, 0.2),),
                expected_semantic_revision=root.semantic_revision,
                transaction_id="tx.cpt.invalid-row",
                actor_id="expert.one",
            )
        assert captured.value.code == "model.cpt_update_invalid"
        assert service.get_node(root.node_id) == root

        updated = service.update_cpt_rows(
            root.node_id,
            ((0.1, 0.2, 0.7),),
            expected_semantic_revision=root.semantic_revision,
            transaction_id="tx.cpt.manual-row",
            actor_id="expert.one",
        )
        assert updated.editor.materialized_probabilities == ((0.1, 0.2, 0.7),)
        materialized = service.materialize_current_cpt(
            root.node_id,
            strategy="uniform",
            expected_semantic_revision=updated.semantic_revision,
            transaction_id="tx.cpt.uniform",
            actor_id="expert.one",
        )
        assert materialized.editor.mode is CptMode.GENERATED
        assert materialized.editor.materialized_probabilities[0] == pytest.approx(
            (1 / 3, 1 / 3, 1 / 3)
        )
        assert service.validate_current_cpt(root.node_id).executable is True
    finally:
        database.close()


def test_state_replacement_invalidates_child_and_dependents_atomically(tmp_path: Path) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    _, base = seven_node_graph()
    service.create_scheme(
        base,
        transaction_id="tx.scheme.base.create",
        actor_id="expert.one",
    )
    try:
        changed_ids = ("bn.skill", "evidence.gaze", "evidence.precision")
        originals = {node_id: service.get_node(node_id) for node_id in changed_ids}
        original_history_counts = {
            node_id: len(service.node_history(node_id)) for node_id in changed_ids
        }
        original_scheme_history_count = len(service.scheme_history(base.scheme_id))
        new_states = tuple(
            VariableState(
                state_id=state_id,
                label=state_id.title(),
                description=f"Editable {state_id} state.",
            )
            for state_id in ("very-low", "low", "high", "very-high")
        )
        stale_revisions = {node_id: node.semantic_revision for node_id, node in originals.items()}
        stale_revisions["evidence.gaze"] = 99
        with pytest.raises(CurrentModelOperationError) as captured:
            service.replace_node_states(
                "bn.skill",
                new_states,
                outcome="mark_incomplete",
                expected_semantic_revisions=stale_revisions,
                transaction_id="tx.states.stale",
                actor_id="expert.one",
            )
        assert captured.value.code == "model.state_revision_conflict"
        assert {node_id: service.get_node(node_id) for node_id in changed_ids} == originals
        assert {
            node_id: len(service.node_history(node_id)) for node_id in changed_ids
        } == original_history_counts
        assert len(service.scheme_history(base.scheme_id)) == original_scheme_history_count

        result = service.replace_node_states(
            "bn.skill",
            new_states,
            outcome="mark_incomplete",
            expected_semantic_revisions={
                node_id: node.semantic_revision for node_id, node in originals.items()
            },
            transaction_id="tx.states.replace",
            actor_id="expert.one",
        )
        assert tuple(node.node_id for node in result.nodes) == changed_ids
        skill = service.get_node("bn.skill")
        skill_definition = skill.definition
        assert isinstance(skill_definition, BnNodeDefinition)
        assert tuple(state.state_id for state in skill_definition.ordered_states) == tuple(
            state.state_id for state in new_states
        )
        assert skill_definition.cpt.mode is CptMode.INCOMPLETE
        assert skill_definition.cpt.materialized_probabilities == ()
        for evidence_id in ("evidence.gaze", "evidence.precision"):
            evidence = service.get_node(evidence_id)
            evidence_definition = evidence.definition
            assert isinstance(evidence_definition, EvidenceNodeDefinition)
            assert evidence_definition.cpt.mode is CptMode.INCOMPLETE
            assert evidence_definition.cpt.ordered_parent_state_ids == (
                tuple(state.state_id for state in new_states),
            )
            assert evidence.technical_status is ModelTechnicalStatus.INCOMPLETE
        assert service.get_scheme(base.scheme_id).technical_status is ModelTechnicalStatus.BLOCKED
        assert result.affected_scheme_ids == (base.scheme_id,)

        # Experts repair an incomplete graph incrementally.  A valid edit to one
        # node must not be rejected merely because a different node is still
        # awaiting its own CPT edit.
        precision_before = service.get_node("evidence.precision")
        repaired = service.materialize_current_cpt(
            precision_before.node_id,
            strategy="ranked",
            expected_semantic_revision=precision_before.semantic_revision,
            transaction_id="tx.states.repair.precision",
            actor_id="expert.one",
        )
        assert repaired.editor.mode is CptMode.GENERATED
        assert service.validate_current_cpt(precision_before.node_id).executable is True
        gaze_definition = service.get_node("evidence.gaze").definition
        assert isinstance(gaze_definition, EvidenceNodeDefinition)
        assert gaze_definition.cpt.mode is CptMode.INCOMPLETE
        assert service.get_scheme(base.scheme_id).technical_status is ModelTechnicalStatus.BLOCKED
    finally:
        database.close()
