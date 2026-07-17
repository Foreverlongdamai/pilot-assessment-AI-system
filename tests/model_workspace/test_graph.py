from __future__ import annotations

from datetime import timedelta

import pytest

from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    ModelGraphEdgeKind,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    NodeLayout,
)
from pilot_assessment.model_workspace.graph import (
    ModelGraphError,
    activation_closure,
    ancestors,
    descendants,
    edge_activation,
    ensure_probabilistic_acyclic,
    project_model_edges,
)
from pilot_assessment.model_workspace.hashing import (
    model_graph_semantic_hash,
    model_node_layout_hash,
    model_node_semantic_hash,
    task_scheme_layout_hash,
    task_scheme_semantic_hash,
)
from tests.model_workspace.support import NOW, seven_node_graph


def _node(nodes: tuple[ModelNode, ...], node_id: str) -> ModelNode:
    return next(node for node in nodes if node.node_id == node_id)


def test_seven_node_graph_projects_typed_edges_and_canonical_navigation() -> None:
    nodes, scheme = seven_node_graph()
    edges = project_model_edges(nodes)

    assert len(edges) == 6
    assert tuple(edge.edge_id for edge in edges) == tuple(sorted(edge.edge_id for edge in edges))
    assert sum(edge.edge_kind is ModelGraphEdgeKind.EXTRACTION for edge in edges) == 3
    assert sum(edge.edge_kind is ModelGraphEdgeKind.PROBABILISTIC for edge in edges) == 3

    assert activation_closure(nodes, ("evidence.precision",)) == (
        "bn.competency",
        "bn.skill",
        "evidence.precision",
        "raw.u",
        "raw.x",
    )
    assert ancestors(edges, ("evidence.precision",)) == (
        "bn.competency",
        "bn.skill",
        "raw.u",
        "raw.x",
    )
    assert ancestors(
        edges,
        ("evidence.precision",),
        edge_kinds=frozenset({ModelGraphEdgeKind.PROBABILISTIC}),
    ) == ("bn.competency", "bn.skill")
    assert descendants(edges, ("bn.competency",)) == (
        "bn.skill",
        "evidence.gaze",
        "evidence.precision",
    )

    projected = edge_activation(edges, scheme.computed_active_closure)
    assert len(projected.active_edges) == 4
    assert len(projected.inactive_edges) == 2
    assert all(edge.child.node_id != "evidence.gaze" for edge in projected.active_edges)


def test_projection_rejects_dangling_kind_mismatch_and_probabilistic_cycle() -> None:
    nodes, _ = seven_node_graph()
    precision = _node(nodes, "evidence.precision")
    definition = precision.definition
    bad_parent = ModelNodeRef(node_id="raw.x", node_kind=ModelNodeKind.BN)
    bad_cpt = definition.cpt.model_copy(
        update={
            "ordered_parent_nodes": (bad_parent,),
            "ordered_parent_state_ids": (("low", "medium", "high"),),
        }
    )
    bad_definition = definition.model_copy(
        update={
            "ordered_probabilistic_parent_nodes": (bad_parent,),
            "cpt": bad_cpt,
        }
    )
    wrong_kind = precision.model_copy(update={"definition": bad_definition})
    wrong_kind_nodes = tuple(
        wrong_kind if node.node_id == precision.node_id else node for node in nodes
    )
    with pytest.raises(ModelGraphError, match="kind"):
        project_model_edges(wrong_kind_nodes)

    dangling_parent = ModelNodeRef(node_id="bn.missing", node_kind=ModelNodeKind.BN)
    dangling_cpt = definition.cpt.model_copy(
        update={
            "ordered_parent_nodes": (dangling_parent,),
            "ordered_parent_state_ids": (("low", "medium", "high"),),
        }
    )
    dangling_definition = definition.model_copy(
        update={
            "ordered_probabilistic_parent_nodes": (dangling_parent,),
            "cpt": dangling_cpt,
        }
    )
    dangling = precision.model_copy(update={"definition": dangling_definition})
    dangling_nodes = tuple(
        dangling if node.node_id == precision.node_id else node for node in nodes
    )
    with pytest.raises(ModelGraphError, match="does not resolve"):
        project_model_edges(dangling_nodes)

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
    cycle_node = competency.model_copy(update={"definition": cycle_definition})
    cycle_nodes = tuple(
        cycle_node if node.node_id == competency.node_id else node for node in nodes
    )
    cycle_edges = project_model_edges(cycle_nodes)
    with pytest.raises(ModelGraphError, match="cycle"):
        ensure_probabilistic_acyclic(cycle_edges)


def test_semantic_and_layout_hashes_are_deterministic_and_separate() -> None:
    nodes, scheme = seven_node_graph()
    precision = _node(nodes, "evidence.precision")

    metadata_only = precision.model_copy(
        update={
            "semantic_revision": 99,
            "layout_revision": 77,
            "technical_status": "blocked",
            "diagnostics": (),
            "created_at": NOW + timedelta(days=1),
            "updated_at": NOW + timedelta(days=1),
        }
    )
    assert model_node_semantic_hash(metadata_only) == model_node_semantic_hash(precision)

    moved = precision.model_copy(
        update={
            "global_layout": NodeLayout(node_id=precision.node_id, x=999.0, y=888.0),
            "layout_revision": precision.layout_revision + 1,
        }
    )
    assert model_node_semantic_hash(moved) == model_node_semantic_hash(precision)
    assert model_node_layout_hash(moved) != model_node_layout_hash(precision)

    renamed = precision.model_copy(update={"name_en": "Renamed Evidence"})
    assert model_node_semantic_hash(renamed) != model_node_semantic_hash(precision)

    moved_scheme = scheme.model_copy(
        update={
            "layout_overrides": (NodeLayout(node_id="evidence.precision", x=333.0, y=444.0),),
            "layout_revision": scheme.layout_revision + 1,
        }
    )
    assert task_scheme_semantic_hash(moved_scheme) == task_scheme_semantic_hash(scheme)
    assert task_scheme_layout_hash(moved_scheme) != task_scheme_layout_hash(scheme)

    edges = project_model_edges(nodes)
    first = model_graph_semantic_hash("project.alpha", scheme, nodes, edges)
    second = model_graph_semantic_hash(
        "project.alpha",
        scheme,
        tuple(reversed(nodes)),
        tuple(reversed(edges)),
    )
    assert first == second
