"""Canonical semantic and layout hashes for mutable M7 current objects."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from pilot_assessment.contracts.model_workspace import (
    ModelGraphEdge,
    ModelNode,
    TaskScheme,
)
from pilot_assessment.model_library.identity import typed_content_sha256

_NODE_SEMANTIC_EXCLUDES = {
    "content_hash",
    "layout_hash",
    "global_layout",
    "semantic_revision",
    "layout_revision",
    "technical_status",
    "diagnostics",
    "created_at",
    "updated_at",
}
_SCHEME_SEMANTIC_EXCLUDES = {
    "content_hash",
    "layout_hash",
    "layout_overrides",
    "semantic_revision",
    "layout_revision",
    "technical_status",
    "diagnostics",
    "created_at",
    "updated_at",
}


def model_node_semantic_hash(node: ModelNode) -> str:
    """Hash current node identity and function while excluding mutable bookkeeping/layout."""

    payload = node.model_dump(mode="json", exclude=_NODE_SEMANTIC_EXCLUDES)
    return typed_content_sha256("model-node-semantic", node.contract_version, payload)


def model_node_layout_hash(node: ModelNode) -> str:
    """Hash only the stable node identity and its project-global layout."""

    payload = {
        "node_id": node.node_id,
        "global_layout": node.global_layout.model_dump(mode="json"),
    }
    return typed_content_sha256("model-node-layout", node.contract_version, payload)


def rehash_model_node(node: ModelNode) -> ModelNode:
    """Return the same immutable node content with freshly derived canonical hashes."""

    return node.model_copy(
        update={
            "content_hash": model_node_semantic_hash(node),
            "layout_hash": model_node_layout_hash(node),
        }
    )


def task_scheme_semantic_hash(scheme: TaskScheme) -> str:
    """Hash task activation/meaning without layout or mutable bookkeeping fields."""

    payload = scheme.model_dump(mode="json", exclude=_SCHEME_SEMANTIC_EXCLUDES)
    return typed_content_sha256("task-scheme-semantic", scheme.contract_version, payload)


def task_scheme_layout_hash(scheme: TaskScheme) -> str:
    """Hash only the scheme identity and canonical task-specific layout overrides."""

    payload = {
        "scheme_id": scheme.scheme_id,
        "layout_overrides": [layout.model_dump(mode="json") for layout in scheme.layout_overrides],
    }
    return typed_content_sha256("task-scheme-layout", scheme.contract_version, payload)


def rehash_task_scheme(scheme: TaskScheme) -> TaskScheme:
    """Return the same immutable scheme content with freshly derived canonical hashes."""

    return scheme.model_copy(
        update={
            "content_hash": task_scheme_semantic_hash(scheme),
            "layout_hash": task_scheme_layout_hash(scheme),
        }
    )


def model_library_identity(
    nodes: Iterable[ModelNode],
    schemes: Iterable[TaskScheme],
) -> str:
    """Hash ordered current node/scheme semantic and layout identities."""

    digest = hashlib.sha256()
    collections = (
        ("node", sorted(nodes, key=lambda item: item.node_id), "node_id"),
        ("scheme", sorted(schemes, key=lambda item: item.scheme_id), "scheme_id"),
    )
    for kind, items, identity_field in collections:
        for item in items:
            identity = getattr(item, identity_field)
            digest.update(kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(identity.encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.content_hash.encode("ascii"))
            digest.update(b"\0")
            digest.update(item.layout_hash.encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def model_graph_semantic_hash(
    model_library_id: str,
    scheme: TaskScheme,
    nodes: Iterable[ModelNode],
    edges: Iterable[ModelGraphEdge],
) -> str:
    """Hash one graph projection independently of input order and visual layout."""

    ordered_nodes = tuple(sorted(nodes, key=lambda item: item.node_id))
    ordered_edges = tuple(sorted(edges, key=lambda item: item.edge_id))
    payload = {
        "model_library_id": model_library_id,
        "scheme_id": scheme.scheme_id,
        "scheme_content_hash": task_scheme_semantic_hash(scheme),
        "nodes": [
            {
                "node_id": node.node_id,
                "node_kind": node.node_kind.value,
                "content_hash": model_node_semantic_hash(node),
            }
            for node in ordered_nodes
        ],
        "edges": [edge.model_dump(mode="json") for edge in ordered_edges],
    }
    return typed_content_sha256("model-graph-semantic", "0.2.0", payload)


__all__ = [
    "model_graph_semantic_hash",
    "model_library_identity",
    "model_node_layout_hash",
    "model_node_semantic_hash",
    "rehash_model_node",
    "rehash_task_scheme",
    "task_scheme_layout_hash",
    "task_scheme_semantic_hash",
]
