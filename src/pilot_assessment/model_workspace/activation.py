"""Pure activation and deactivation planning for one current TaskScheme."""

from __future__ import annotations

from dataclasses import dataclass

from pilot_assessment.contracts.model_workspace import (
    DeactivationImpact,
    ModelGraphEdge,
    ModelNode,
    TaskScheme,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_workspace.graph import (
    activation_closure,
    descendants,
    edge_activation,
)


class ActivationPlanningError(ValueError):
    """Raised when the requested activation intent has no coherent graph meaning."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ActivationPlan:
    explicit_node_ids: tuple[str, ...]
    computed_closure: tuple[str, ...]
    added_node_ids: tuple[str, ...]
    auto_enabled_parent_ids: tuple[str, ...]
    added_edge_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeactivationPlan:
    impact: DeactivationImpact
    remaining_explicit_node_ids: tuple[str, ...]
    computed_closure: tuple[str, ...]
    remaining_output_node_ids: tuple[str, ...]


def plan_activation(
    scheme: TaskScheme,
    nodes: tuple[ModelNode, ...],
    edges: tuple[ModelGraphEdge, ...],
    node_id: str,
) -> ActivationPlan:
    index = {node.node_id: node for node in nodes}
    if node_id not in index:
        raise ActivationPlanningError(
            "model.activation_node_missing",
            f"activation target {node_id!r} does not resolve",
        )
    if node_id in scheme.explicit_active_node_ids:
        raise ActivationPlanningError(
            "model.node_already_explicitly_active",
            f"node {node_id!r} is already explicitly active",
        )
    explicit = tuple(sorted((*scheme.explicit_active_node_ids, node_id)))
    closure = activation_closure(nodes, explicit)
    old_closure = set(scheme.computed_active_closure)
    added = tuple(sorted(set(closure) - old_closure))
    auto_enabled = tuple(sorted(set(added) - {node_id}))
    before_edges = edge_activation(edges, scheme.computed_active_closure).active_edges
    after_edges = edge_activation(edges, closure).active_edges
    before_edge_ids = {edge.edge_id for edge in before_edges}
    added_edge_ids = tuple(
        edge.edge_id for edge in after_edges if edge.edge_id not in before_edge_ids
    )
    return ActivationPlan(
        explicit_node_ids=explicit,
        computed_closure=closure,
        added_node_ids=added,
        auto_enabled_parent_ids=auto_enabled,
        added_edge_ids=added_edge_ids,
    )


def plan_deactivation(
    scheme: TaskScheme,
    nodes: tuple[ModelNode, ...],
    edges: tuple[ModelGraphEdge, ...],
    node_id: str,
) -> DeactivationPlan:
    active = set(scheme.computed_active_closure)
    if node_id not in active:
        raise ActivationPlanningError(
            "model.node_not_active",
            f"node {node_id!r} is not active in scheme {scheme.scheme_id!r}",
        )
    active_edges = edge_activation(edges, active).active_edges
    downstream = set(descendants(active_edges, (node_id,)))
    cascade = downstream | {node_id}
    remaining_explicit = tuple(sorted(set(scheme.explicit_active_node_ids) - cascade))
    new_closure = activation_closure(nodes, remaining_explicit)
    impacted_nodes = tuple(sorted(active - set(new_closure)))
    remaining_outputs = tuple(node for node in scheme.output_node_ids if node in set(new_closure))
    new_active_edge_ids = {
        edge.edge_id for edge in edge_activation(edges, new_closure).active_edges
    }
    impacted_edge_ids = tuple(
        edge.edge_id for edge in active_edges if edge.edge_id not in new_active_edge_ids
    )
    node_index = {node.node_id: node for node in nodes}
    impact_hash = typed_content_sha256(
        "deactivation-impact",
        "0.1.0",
        {
            "scheme_id": scheme.scheme_id,
            "scheme_semantic_revision": scheme.semantic_revision,
            "scheme_content_hash": scheme.content_hash,
            "requested_node_id": node_id,
            "active_nodes": [
                {
                    "node_id": active_node_id,
                    "content_hash": node_index[active_node_id].content_hash,
                }
                for active_node_id in sorted(active)
            ],
            "active_edge_ids": [edge.edge_id for edge in active_edges],
            "remaining_explicit_node_ids": list(remaining_explicit),
            "computed_closure_after": list(new_closure),
            "impacted_node_ids": list(impacted_nodes),
            "impacted_edge_ids": list(impacted_edge_ids),
        },
    )
    impact = DeactivationImpact(
        scheme_id=scheme.scheme_id,
        scheme_semantic_revision=scheme.semantic_revision,
        requested_node_id=node_id,
        impacted_node_ids=impacted_nodes,
        impacted_edge_ids=impacted_edge_ids,
        impact_hash=impact_hash,
    )
    return DeactivationPlan(
        impact=impact,
        remaining_explicit_node_ids=remaining_explicit,
        computed_closure=new_closure,
        remaining_output_node_ids=remaining_outputs,
    )


__all__ = [
    "ActivationPlan",
    "ActivationPlanningError",
    "DeactivationPlan",
    "plan_activation",
    "plan_deactivation",
]
