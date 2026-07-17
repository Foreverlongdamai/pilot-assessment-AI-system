from __future__ import annotations

from pilot_assessment.contracts.model_components import CptMode
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelDiagnosticSeverity,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    ModelTechnicalStatus,
)
from pilot_assessment.model_workspace.hashing import rehash_model_node
from pilot_assessment.model_workspace.validation import validate_model_graph
from tests.model_workspace.support import (
    available_source_ids,
    operator_registry,
    seven_node_graph,
)


def _node(nodes: tuple[ModelNode, ...], node_id: str) -> ModelNode:
    return next(node for node in nodes if node.node_id == node_id)


def _replace(nodes: tuple[ModelNode, ...], replacement: ModelNode) -> tuple[ModelNode, ...]:
    return tuple(replacement if node.node_id == replacement.node_id else node for node in nodes)


def test_valid_active_graph_is_executable_with_nonblocking_starter_warnings() -> None:
    nodes, scheme = seven_node_graph()
    outcome = validate_model_graph(
        nodes,
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )

    assert outcome.technical_status is ModelTechnicalStatus.EXECUTABLE
    assert outcome.diagnostics
    assert all(
        diagnostic.severity is ModelDiagnosticSeverity.WARNING for diagnostic in outcome.diagnostics
    )
    assert {diagnostic.code for diagnostic in outcome.diagnostics} == {
        "model.scientific_status_provisional"
    }


def test_missing_operator_source_and_cpt_axis_block_only_when_active() -> None:
    nodes, scheme = seven_node_graph()
    precision = _node(nodes, "evidence.precision")
    definition = precision.definition
    assert isinstance(definition, EvidenceNodeDefinition)
    recipe_node = definition.recipe.graph.nodes[0]
    changed_recipe_node = recipe_node.model_copy(update={"operator_id": "operator.missing"})
    changed_graph = definition.recipe.graph.model_copy(
        update={
            "nodes": (changed_recipe_node, *definition.recipe.graph.nodes[1:]),
        }
    )
    changed_recipe = definition.recipe.model_copy(update={"graph": changed_graph})
    missing_operator = rehash_model_node(
        precision.model_copy(
            update={"definition": definition.model_copy(update={"recipe": changed_recipe})}
        )
    )
    operator_outcome = validate_model_graph(
        _replace(nodes, missing_operator),
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )
    assert operator_outcome.technical_status is ModelTechnicalStatus.BLOCKED
    assert "model.recipe.operator_unknown" in {
        diagnostic.code for diagnostic in operator_outcome.diagnostics
    }

    source_outcome = validate_model_graph(
        nodes,
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=frozenset({"source.U", "source.G"}),
    )
    assert source_outcome.technical_status is ModelTechnicalStatus.BLOCKED
    assert "model.source_unavailable" in {
        diagnostic.code for diagnostic in source_outcome.diagnostics
    }

    bad_cpt = definition.cpt.model_copy(
        update={"ordered_parent_state_ids": (("bad", "medium", "high"),)}
    )
    axis_mismatch = rehash_model_node(
        precision.model_copy(update={"definition": definition.model_copy(update={"cpt": bad_cpt})})
    )
    axis_outcome = validate_model_graph(
        _replace(nodes, axis_mismatch),
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )
    assert axis_outcome.technical_status is ModelTechnicalStatus.BLOCKED
    assert "model.cpt_parent_axis_mismatch" in {
        diagnostic.code for diagnostic in axis_outcome.diagnostics
    }

    impossible_shape = definition.cpt.model_copy(
        update={"materialized_probabilities": ((0.5, 0.5),)}
    )
    shape_mismatch = rehash_model_node(
        precision.model_copy(
            update={"definition": definition.model_copy(update={"cpt": impossible_shape})}
        )
    )
    shape_outcome = validate_model_graph(
        _replace(nodes, shape_mismatch),
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )
    assert shape_outcome.technical_status is ModelTechnicalStatus.BLOCKED
    assert "model.cpt_invalid" in {diagnostic.code for diagnostic in shape_outcome.diagnostics}


def test_incomplete_inactive_node_is_editable_but_cycle_in_active_graph_blocks_run() -> None:
    nodes, scheme = seven_node_graph()
    gaze = _node(nodes, "evidence.gaze")
    gaze_definition = gaze.definition
    assert isinstance(gaze_definition, EvidenceNodeDefinition)
    incomplete_cpt = gaze_definition.cpt.model_copy(
        update={"mode": CptMode.INCOMPLETE, "materialized_probabilities": ()}
    )
    incomplete_gaze = rehash_model_node(
        gaze.model_copy(
            update={"definition": gaze_definition.model_copy(update={"cpt": incomplete_cpt})}
        )
    )
    inactive_outcome = validate_model_graph(
        _replace(nodes, incomplete_gaze),
        active_node_ids=scheme.computed_active_closure,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )
    assert inactive_outcome.technical_status is ModelTechnicalStatus.EXECUTABLE

    competency = _node(nodes, "bn.competency")
    competency_definition = competency.definition
    assert isinstance(competency_definition, BnNodeDefinition)
    cycle_parent = ModelNodeRef(node_id="bn.skill", node_kind=ModelNodeKind.BN)
    cycle_cpt = competency_definition.cpt.model_copy(
        update={
            "ordered_parent_nodes": (cycle_parent,),
            "ordered_parent_state_ids": (("low", "medium", "high"),),
            "materialized_probabilities": (
                (0.7, 0.2, 0.1),
                (0.2, 0.6, 0.2),
                (0.1, 0.2, 0.7),
            ),
        }
    )
    cycle_definition = competency_definition.model_copy(
        update={
            "ordered_probabilistic_parent_nodes": (cycle_parent,),
            "cpt": cycle_cpt,
        }
    )
    cycle_competency = rehash_model_node(
        competency.model_copy(update={"definition": cycle_definition})
    )
    all_active = tuple(sorted(node.node_id for node in nodes))
    cycle_outcome = validate_model_graph(
        _replace(nodes, cycle_competency),
        active_node_ids=all_active,
        operator_registry=operator_registry(),
        available_source_ids=available_source_ids(),
    )
    assert cycle_outcome.technical_status is ModelTechnicalStatus.BLOCKED
    assert "model.probabilistic_cycle" in {
        diagnostic.code for diagnostic in cycle_outcome.diagnostics
    }
