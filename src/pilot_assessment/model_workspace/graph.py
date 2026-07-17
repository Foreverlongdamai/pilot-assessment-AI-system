"""Deterministic graph projection and navigation for complete current nodes."""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelGraphEdge,
    ModelGraphEdgeKind,
    ModelNode,
    ModelNodeRef,
)
from pilot_assessment.model_library.identity import typed_content_sha256


class ModelGraphError(ValueError):
    """Stable technical graph failure used by services and validators."""

    def __init__(self, code: str, location: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.location = location


@dataclass(frozen=True, slots=True)
class EdgeActivation:
    active_edges: tuple[ModelGraphEdge, ...]
    inactive_edges: tuple[ModelGraphEdge, ...]


def _node_index(nodes: Iterable[ModelNode]) -> dict[str, ModelNode]:
    result: dict[str, ModelNode] = {}
    for node in nodes:
        if node.node_id in result:
            raise ModelGraphError(
                "model.node_id_duplicate",
                f"/nodes/{node.node_id}",
                f"node ID {node.node_id!r} occurs more than once",
            )
        result[node.node_id] = node
    return result


def _probabilistic_parent_refs(node: ModelNode) -> tuple[ModelNodeRef, ...]:
    if isinstance(node.definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        return node.definition.ordered_probabilistic_parent_nodes
    return ()


def _data_parent_refs(node: ModelNode) -> tuple[tuple[ModelNodeRef, str], ...]:
    if not isinstance(node.definition, EvidenceNodeDefinition):
        return ()
    return tuple(
        (binding.raw_input_node, binding.recipe_input_binding_id)
        for binding in node.definition.data_bindings
    )


def _resolve_ref(
    index: dict[str, ModelNode],
    reference: ModelNodeRef,
    *,
    location: str,
) -> ModelNode:
    resolved = index.get(reference.node_id)
    if resolved is None:
        raise ModelGraphError(
            "model.node_reference_missing",
            location,
            f"node reference {reference.node_id!r} does not resolve",
        )
    if resolved.node_kind is not reference.node_kind:
        raise ModelGraphError(
            "model.node_kind_mismatch",
            location,
            "node reference kind does not match resolved node kind: "
            f"{reference.node_kind.value} != {resolved.node_kind.value}",
        )
    return resolved


def _edge_id(
    edge_kind: ModelGraphEdgeKind,
    parent: ModelNodeRef,
    child: ModelNodeRef,
    recipe_input_binding_id: str | None,
) -> str:
    digest = typed_content_sha256(
        "model-graph-edge",
        "0.1.0",
        {
            "edge_kind": edge_kind.value,
            "parent": parent.model_dump(mode="json"),
            "child": child.model_dump(mode="json"),
            "recipe_input_binding_id": recipe_input_binding_id,
        },
    )
    return f"edge.{edge_kind.value}.{digest}"


def project_model_edges(
    nodes: Iterable[ModelNode],
    *,
    node_ids: Iterable[str] | None = None,
) -> tuple[ModelGraphEdge, ...]:
    """Derive both edge families; no independently persisted ghost edges exist."""

    index = _node_index(nodes)
    selected = set(index) if node_ids is None else set(node_ids)
    missing_selected = sorted(selected - set(index))
    if missing_selected:
        missing = missing_selected[0]
        raise ModelGraphError(
            "model.node_reference_missing",
            f"/nodes/{missing}",
            f"selected node {missing!r} does not resolve",
        )

    edges: list[ModelGraphEdge] = []
    for child_id in sorted(selected):
        child_node = index[child_id]
        child_ref = ModelNodeRef(node_id=child_id, node_kind=child_node.node_kind)
        for position, (parent_ref, binding_id) in enumerate(_data_parent_refs(child_node)):
            location = f"/nodes/{child_id}/definition/data_bindings/{position}/raw_input_node"
            _resolve_ref(index, parent_ref, location=location)
            if parent_ref.node_id not in selected:
                raise ModelGraphError(
                    "model.activation_closure_incomplete",
                    location,
                    f"data parent {parent_ref.node_id!r} is outside the selected closure",
                )
            edges.append(
                ModelGraphEdge(
                    edge_id=_edge_id(
                        ModelGraphEdgeKind.EXTRACTION,
                        parent_ref,
                        child_ref,
                        binding_id,
                    ),
                    edge_kind=ModelGraphEdgeKind.EXTRACTION,
                    parent=parent_ref,
                    child=child_ref,
                    recipe_input_binding_id=binding_id,
                )
            )
        for position, parent_ref in enumerate(_probabilistic_parent_refs(child_node)):
            location = f"/nodes/{child_id}/definition/ordered_probabilistic_parent_nodes/{position}"
            _resolve_ref(index, parent_ref, location=location)
            if parent_ref.node_id not in selected:
                raise ModelGraphError(
                    "model.activation_closure_incomplete",
                    location,
                    f"probabilistic parent {parent_ref.node_id!r} is outside the selected closure",
                )
            edges.append(
                ModelGraphEdge(
                    edge_id=_edge_id(
                        ModelGraphEdgeKind.PROBABILISTIC,
                        parent_ref,
                        child_ref,
                        None,
                    ),
                    edge_kind=ModelGraphEdgeKind.PROBABILISTIC,
                    parent=parent_ref,
                    child=child_ref,
                    recipe_input_binding_id=None,
                )
            )
    ordered = tuple(sorted(edges, key=lambda item: item.edge_id))
    if len({edge.edge_id for edge in ordered}) != len(ordered):
        raise ModelGraphError(
            "model.edge_id_duplicate",
            "/edges",
            "projected graph contains duplicate edge identities",
        )
    return ordered


def ensure_probabilistic_acyclic(
    edges: Iterable[ModelGraphEdge],
    *,
    node_ids: Iterable[str] | None = None,
) -> None:
    """Raise when the selected probabilistic dependency graph contains a cycle."""

    selected = None if node_ids is None else set(node_ids)
    probabilistic = tuple(
        edge
        for edge in edges
        if edge.edge_kind is ModelGraphEdgeKind.PROBABILISTIC
        and (
            selected is None or (edge.parent.node_id in selected and edge.child.node_id in selected)
        )
    )
    graph_nodes = (
        {
            endpoint
            for edge in probabilistic
            for endpoint in (edge.parent.node_id, edge.child.node_id)
        }
        if selected is None
        else selected
    )
    adjacency = {node_id: [] for node_id in graph_nodes}
    indegree = dict.fromkeys(graph_nodes, 0)
    for edge in probabilistic:
        adjacency[edge.parent.node_id].append(edge.child.node_id)
        indegree[edge.child.node_id] += 1
    for targets in adjacency.values():
        targets.sort()
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(queue)
    visited = 0
    while queue:
        node_id = heapq.heappop(queue)
        visited += 1
        for child_id in adjacency[node_id]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                heapq.heappush(queue, child_id)
    if visited != len(graph_nodes):
        raise ModelGraphError(
            "model.probabilistic_cycle",
            "/edges/probabilistic",
            "probabilistic dependency graph contains a cycle",
        )


def _reachable(
    edges: Iterable[ModelGraphEdge],
    starts: Iterable[str],
    *,
    reverse: bool,
    edge_kinds: frozenset[ModelGraphEdgeKind] | None,
) -> tuple[str, ...]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if edge_kinds is not None and edge.edge_kind not in edge_kinds:
            continue
        source = edge.child.node_id if reverse else edge.parent.node_id
        target = edge.parent.node_id if reverse else edge.child.node_id
        adjacency.setdefault(source, set()).add(target)
    start_set = set(starts)
    visited = set(start_set)
    queue = deque(sorted(start_set))
    while queue:
        current = queue.popleft()
        for target in sorted(adjacency.get(current, ())):
            if target not in visited:
                visited.add(target)
                queue.append(target)
    return tuple(sorted(visited - start_set))


def ancestors(
    edges: Iterable[ModelGraphEdge],
    starts: Iterable[str],
    *,
    edge_kinds: frozenset[ModelGraphEdgeKind] | None = None,
) -> tuple[str, ...]:
    return _reachable(edges, starts, reverse=True, edge_kinds=edge_kinds)


def descendants(
    edges: Iterable[ModelGraphEdge],
    starts: Iterable[str],
    *,
    edge_kinds: frozenset[ModelGraphEdgeKind] | None = None,
) -> tuple[str, ...]:
    return _reachable(edges, starts, reverse=False, edge_kinds=edge_kinds)


def activation_closure(
    nodes: Iterable[ModelNode],
    explicit_node_ids: Iterable[str],
) -> tuple[str, ...]:
    """Recursively activate fixed data and probabilistic parents in canonical order."""

    index = _node_index(nodes)
    explicit = tuple(explicit_node_ids)
    if len(explicit) != len(set(explicit)):
        raise ModelGraphError(
            "model.explicit_activation_duplicate",
            "/explicit_active_node_ids",
            "explicit activation contains duplicate node IDs",
        )
    closure: set[str] = set()
    queue = deque(sorted(explicit))
    while queue:
        node_id = queue.popleft()
        if node_id in closure:
            continue
        node = index.get(node_id)
        if node is None:
            raise ModelGraphError(
                "model.node_reference_missing",
                "/explicit_active_node_ids",
                f"explicit node {node_id!r} does not resolve",
            )
        closure.add(node_id)
        refs = tuple(ref for ref, _ in _data_parent_refs(node)) + _probabilistic_parent_refs(node)
        for position, reference in enumerate(refs):
            _resolve_ref(
                index,
                reference,
                location=f"/nodes/{node_id}/dependencies/{position}",
            )
            if reference.node_id not in closure:
                queue.append(reference.node_id)
    return tuple(sorted(closure))


def edge_activation(
    edges: Iterable[ModelGraphEdge],
    active_node_ids: Iterable[str],
) -> EdgeActivation:
    active_nodes = set(active_node_ids)
    ordered = tuple(sorted(edges, key=lambda item: item.edge_id))
    active = tuple(
        edge
        for edge in ordered
        if edge.parent.node_id in active_nodes and edge.child.node_id in active_nodes
    )
    inactive = tuple(edge for edge in ordered if edge not in active)
    return EdgeActivation(active_edges=active, inactive_edges=inactive)


__all__ = [
    "EdgeActivation",
    "ModelGraphError",
    "activation_closure",
    "ancestors",
    "descendants",
    "edge_activation",
    "ensure_probabilistic_acyclic",
    "project_model_edges",
]
