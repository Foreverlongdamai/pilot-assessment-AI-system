"""Pure complete-node copy helpers used by M7 graph mutation services."""

from __future__ import annotations

from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeRef,
    ModelObjectLifecycle,
    NodeLayout,
    TaskScheme,
)

_ZERO_HASH = "0" * 64


def copy_complete_node(
    source: ModelNode,
    *,
    new_node_id: str,
    offset_x: float = 40.0,
    offset_y: float = 40.0,
) -> ModelNode:
    """Deep-copy only one complete node while retaining all fixed parent references."""

    deep_source = ModelNode.model_validate(source.model_dump(mode="json"))
    definition = deep_source.definition
    if isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        child = ModelNodeRef(
            node_id=new_node_id,
            node_kind=deep_source.node_kind,
        )
        definition = definition.model_copy(
            update={
                "cpt": definition.cpt.model_copy(
                    update={
                        "cpt_id": f"cpt.{new_node_id}",
                        "child_node": child,
                    }
                )
            }
        )
    copied = deep_source.model_copy(
        update={
            "node_id": new_node_id,
            "lifecycle": ModelObjectLifecycle.ACTIVE,
            "copied_from_node_id": deep_source.node_id,
            "definition": definition,
            "global_layout": NodeLayout(
                node_id=new_node_id,
                x=deep_source.global_layout.x + offset_x,
                y=deep_source.global_layout.y + offset_y,
            ),
            "semantic_revision": 0,
            "layout_revision": 0,
            "content_hash": _ZERO_HASH,
            "layout_hash": _ZERO_HASH,
        }
    )
    return ModelNode.model_validate(copied.model_dump(mode="json"))


def effective_scheme_layout(scheme: TaskScheme, node: ModelNode) -> NodeLayout:
    for layout in scheme.layout_overrides:
        if layout.node_id == node.node_id:
            return layout
    return node.global_layout


def merge_scheme_layouts(
    scheme: TaskScheme,
    updates: tuple[NodeLayout, ...],
) -> tuple[NodeLayout, ...]:
    merged = {layout.node_id: layout for layout in scheme.layout_overrides}
    for layout in updates:
        merged[layout.node_id] = layout
    return tuple(merged[node_id] for node_id in sorted(merged))


__all__ = [
    "copy_complete_node",
    "effective_scheme_layout",
    "merge_scheme_layouts",
]
