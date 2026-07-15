"""Deterministic compiler for technically executable evidence recipes."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    OperatorDefinition,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScoring,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import (
    RecipeValidationDisposition,
    RecipeValidationOutcome,
    validate_recipe,
)


class RecipeCompilationError(ValueError):
    """Raised when an incomplete draft cannot become an executable plan."""

    def __init__(self, outcome: RecipeValidationOutcome) -> None:
        super().__init__("evidence recipe is not technically executable")
        self.outcome = outcome


@dataclass(frozen=True, slots=True)
class CompiledIncomingEdge:
    edge_id: str
    source_node_id: str
    source_port_id: str
    target_port_id: str


@dataclass(frozen=True, slots=True)
class CompiledNode:
    node: RecipeNode
    definition: OperatorDefinition
    incoming_edges: tuple[CompiledIncomingEdge, ...]


@dataclass(frozen=True, slots=True)
class CompiledRecipe:
    recipe: EvidenceRecipe
    nodes: tuple[CompiledNode, ...]
    outputs: tuple[RecipeOutputBinding, ...]
    scoring: RecipeScoring


def _topological_node_ids(recipe: EvidenceRecipe) -> tuple[str, ...]:
    nodes = {node.node_id: node for node in recipe.graph.nodes}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    indegree = dict.fromkeys(nodes, 0)
    for edge in recipe.graph.edges:
        adjacency[edge.source.node_id].append(edge.target.node_id)
        indegree[edge.target.node_id] += 1
    for targets in adjacency.values():
        targets.sort()

    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(queue)
    ordered: list[str] = []
    while queue:
        source_id = heapq.heappop(queue)
        ordered.append(source_id)
        for target_id in adjacency[source_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                heapq.heappush(queue, target_id)
    return tuple(ordered)


def compile_recipe(
    recipe: EvidenceRecipe,
    registry: OperatorRegistry,
) -> CompiledRecipe:
    """Resolve a frozen recipe snapshot without executing any operator."""

    outcome = validate_recipe(recipe, registry)
    if outcome.disposition is not RecipeValidationDisposition.EXECUTABLE:
        raise RecipeCompilationError(outcome)
    assert recipe.scoring is not None

    nodes = {node.node_id: node for node in recipe.graph.nodes}
    incoming: dict[str, list[CompiledIncomingEdge]] = {
        node_id: [] for node_id in nodes
    }
    for edge in recipe.graph.edges:
        incoming[edge.target.node_id].append(
            CompiledIncomingEdge(
                edge_id=edge.edge_id,
                source_node_id=edge.source.node_id,
                source_port_id=edge.source.port_id,
                target_port_id=edge.target.port_id,
            )
        )
    for values in incoming.values():
        values.sort(key=lambda item: (item.target_port_id, item.edge_id))

    compiled_nodes = tuple(
        CompiledNode(
            node=nodes[node_id],
            definition=registry.definition(
                nodes[node_id].operator_id,
                nodes[node_id].operator_version,
            ),
            incoming_edges=tuple(incoming[node_id]),
        )
        for node_id in _topological_node_ids(recipe)
    )
    return CompiledRecipe(
        recipe=recipe,
        nodes=compiled_nodes,
        outputs=recipe.outputs,
        scoring=recipe.scoring,
    )


__all__ = [
    "CompiledIncomingEdge",
    "CompiledNode",
    "CompiledRecipe",
    "RecipeCompilationError",
    "compile_recipe",
]
