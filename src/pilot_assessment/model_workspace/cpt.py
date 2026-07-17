"""Adapters from mutable M7 NodeCpt values to the existing M5 CPT engine."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from pilot_assessment.bayesian.validation import (
    CptMaterializationError,
    CptMigrationError,
    CptValidationOutcome,
    add_parent_preserving_independence,
    invalidate_cpts_for_state_change,
    materialize_ranked_cpt,
    materialize_uniform_prior,
    remove_parent_with_marginal_weights,
    validate_cpt,
)
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
    VariableState,
    VersionLineage,
)
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    NodeCpt,
)

_ZERO_HASH = "0" * 64
_ADAPTER_TIME = datetime(1970, 1, 1, tzinfo=UTC)


class CurrentCptError(ValueError):
    """Stable adapter failure for typed M7 CPT operations."""


@dataclass(frozen=True, slots=True)
class CptEditorState:
    child_node: ModelNodeRef
    ordered_parent_nodes: tuple[ModelNodeRef, ...]
    child_state_ids: tuple[str, ...]
    ordered_parent_state_ids: tuple[tuple[str, ...], ...]
    materialized_probabilities: tuple[tuple[float, ...], ...]
    mode: CptMode
    required_row_count: int
    required_cell_count: int


def node_state_ids(node: ModelNode) -> tuple[str, ...]:
    definition = node.definition
    if isinstance(definition, EvidenceNodeDefinition):
        return tuple(state.state_id for state in definition.ordered_observation_states)
    if isinstance(definition, BnNodeDefinition):
        return tuple(state.state_id for state in definition.ordered_states)
    raise CurrentCptError("Raw Input nodes do not have Bayesian states")


def _legacy_kind(kind: ModelNodeKind) -> ComponentKind:
    if kind is ModelNodeKind.BN:
        return ComponentKind.BN_NODE_VERSION
    if kind is ModelNodeKind.EVIDENCE:
        return ComponentKind.EVIDENCE_BINDING_VERSION
    raise CurrentCptError("Raw Input nodes cannot participate in a CPT")


def _current_kind(kind: ComponentKind) -> ModelNodeKind:
    if kind is ComponentKind.BN_NODE_VERSION:
        return ModelNodeKind.BN
    if kind is ComponentKind.EVIDENCE_BINDING_VERSION:
        return ModelNodeKind.EVIDENCE
    raise CurrentCptError(f"legacy CPT reference kind {kind.value!r} is unsupported")


def _legacy_ref(reference: ModelNodeRef) -> ComponentIdRef:
    return ComponentIdRef(
        kind=_legacy_kind(reference.node_kind),
        version_id=reference.node_id,
    )


def _current_ref(reference: ComponentIdRef) -> ModelNodeRef:
    return ModelNodeRef(
        node_id=reference.version_id,
        node_kind=_current_kind(reference.kind),
    )


def _lineage() -> VersionLineage:
    return VersionLineage(
        source_version_ids=(),
        created_at=_ADAPTER_TIME,
        created_by="system.current-cpt-adapter",
        note="Transient adapter value; not persisted as a legacy component.",
    )


def to_legacy_cpt(cpt: NodeCpt) -> CptVersion:
    return CptVersion(
        cpt_version_id=cpt.cpt_id,
        child_variable_id=_legacy_ref(cpt.child_node),
        ordered_parent_variable_ids=tuple(
            _legacy_ref(parent) for parent in cpt.ordered_parent_nodes
        ),
        child_state_ids=cpt.child_state_ids,
        ordered_parent_state_ids=cpt.ordered_parent_state_ids,
        materialized_probabilities=cpt.materialized_probabilities,
        mode=cpt.mode,
        generator_metadata=cpt.generator_metadata,
        source=cpt.source,
        lineage=_lineage(),
        content_hash=_ZERO_HASH,
    )


def from_legacy_cpt(cpt: CptVersion) -> NodeCpt:
    return NodeCpt(
        cpt_id=cpt.cpt_version_id,
        child_node=_current_ref(cpt.child_variable_id),
        ordered_parent_nodes=tuple(
            _current_ref(parent) for parent in cpt.ordered_parent_variable_ids
        ),
        child_state_ids=cpt.child_state_ids,
        ordered_parent_state_ids=cpt.ordered_parent_state_ids,
        materialized_probabilities=cpt.materialized_probabilities,
        mode=cpt.mode,
        generator_metadata=cpt.generator_metadata,
        source=cpt.source,
    )


def _legacy_variable(node: ModelNode) -> BnNodeVersion | EvidenceBindingVersion:
    definition = node.definition
    if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        raise CurrentCptError("Raw Input nodes do not have a Bayesian variable adapter")
    cpt_ref = ComponentIdRef(
        kind=ComponentKind.CPT_VERSION,
        version_id=definition.cpt.cpt_id,
    )
    parent_ids = tuple(
        _legacy_ref(parent) for parent in definition.ordered_probabilistic_parent_nodes
    )
    if isinstance(definition, BnNodeDefinition):
        return BnNodeVersion(
            bn_node_version_id=node.node_id,
            concept_id=f"concept.{node.node_id}",
            ordered_states=definition.ordered_states,
            ordered_probabilistic_parent_ids=parent_ids,
            cpt_version_id=cpt_ref,
            documentation=definition.documentation,
            scientific_status=definition.scientific_status,
            lineage=_lineage(),
            content_hash=_ZERO_HASH,
        )
    if isinstance(definition, EvidenceNodeDefinition):
        return EvidenceBindingVersion(
            evidence_binding_version_id=node.node_id,
            evidence_version_id=ComponentIdRef(
                kind=ComponentKind.EVIDENCE_VERSION,
                version_id=f"evidence-definition.{node.node_id}",
            ),
            ordered_observation_states=definition.ordered_observation_states,
            observation_mapping=definition.observation_mapping,
            ordered_probabilistic_parent_ids=parent_ids,
            cpt_version_id=cpt_ref,
            observation_policy=definition.observation_policy,
            modality_attribution_weights=definition.modality_attribution_weights,
            lineage=_lineage(),
            content_hash=_ZERO_HASH,
        )
    raise CurrentCptError("unsupported Bayesian node definition")


def validate_node_cpt(
    node: ModelNode,
    nodes: tuple[ModelNode, ...],
) -> CptValidationOutcome:
    if not isinstance(node.definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        raise CurrentCptError("Raw Input nodes do not have a CPT")
    variables = {
        (_legacy_kind(item.node_kind), item.node_id): _legacy_variable(item)
        for item in nodes
        if isinstance(item.definition, (EvidenceNodeDefinition, BnNodeDefinition))
    }
    return validate_cpt(to_legacy_cpt(node.definition.cpt), variables)


def editor_state(node: ModelNode, nodes: tuple[ModelNode, ...]) -> CptEditorState:
    if not isinstance(node.definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        raise CurrentCptError("Raw Input nodes do not have a CPT editor")
    cpt = node.definition.cpt
    validation = validate_node_cpt(node, nodes)
    return CptEditorState(
        child_node=cpt.child_node,
        ordered_parent_nodes=cpt.ordered_parent_nodes,
        child_state_ids=cpt.child_state_ids,
        ordered_parent_state_ids=cpt.ordered_parent_state_ids,
        materialized_probabilities=cpt.materialized_probabilities,
        mode=cpt.mode,
        required_row_count=validation.required_row_count,
        required_cell_count=validation.required_cell_count,
    )


def mark_cpt_incomplete(
    cpt: NodeCpt,
    *,
    parent_nodes: tuple[ModelNodeRef, ...] | None = None,
    parent_state_ids: tuple[tuple[str, ...], ...] | None = None,
    child_state_ids: tuple[str, ...] | None = None,
    reason: str,
) -> NodeCpt:
    metadata = dict(cpt.generator_metadata)
    metadata["incomplete_reason"] = reason
    return NodeCpt.model_validate(
        cpt.model_copy(
            update={
                "ordered_parent_nodes": (
                    cpt.ordered_parent_nodes if parent_nodes is None else parent_nodes
                ),
                "ordered_parent_state_ids": (
                    cpt.ordered_parent_state_ids if parent_state_ids is None else parent_state_ids
                ),
                "child_state_ids": (
                    cpt.child_state_ids if child_state_ids is None else child_state_ids
                ),
                "materialized_probabilities": (),
                "mode": CptMode.INCOMPLETE,
                "generator_metadata": metadata,
            }
        ).model_dump(mode="json")
    )


def add_parent_to_cpt(
    cpt: NodeCpt,
    parent: ModelNodeRef,
    parent_state_ids: tuple[str, ...],
    *,
    strategy: str,
) -> NodeCpt:
    if strategy == "preserve_independence":
        try:
            migrated = add_parent_preserving_independence(
                to_legacy_cpt(cpt),
                _legacy_ref(parent),
                parent_state_ids,
            )
        except CptMigrationError as error:
            raise CurrentCptError(str(error)) from error
        return from_legacy_cpt(migrated)
    parents = (*cpt.ordered_parent_nodes, parent)
    state_axes = (*cpt.ordered_parent_state_ids, parent_state_ids)
    if strategy == "incomplete":
        return mark_cpt_incomplete(
            cpt,
            parent_nodes=parents,
            parent_state_ids=state_axes,
            reason="probabilistic_parent_added_v1",
        )
    if strategy == "uniform":
        prior = materialize_uniform_prior(cpt.child_state_ids)
        row_count = math.prod(len(states) for states in state_axes)
        metadata = dict(cpt.generator_metadata)
        metadata["last_materialization"] = "uniform_after_parent_add_v1"
        return NodeCpt.model_validate(
            cpt.model_copy(
                update={
                    "ordered_parent_nodes": parents,
                    "ordered_parent_state_ids": state_axes,
                    "materialized_probabilities": prior.probabilities * row_count,
                    "mode": CptMode.GENERATED,
                    "generator_metadata": metadata,
                }
            ).model_dump(mode="json")
        )
    raise CurrentCptError(f"unsupported add-parent strategy {strategy!r}")


def remove_parent_from_cpt(
    cpt: NodeCpt,
    parent: ModelNodeRef,
    *,
    strategy: str,
    marginal_weights: tuple[float, ...] | None,
) -> NodeCpt:
    if parent not in cpt.ordered_parent_nodes:
        raise CurrentCptError(f"parent {parent.node_id!r} is not present")
    removed_index = cpt.ordered_parent_nodes.index(parent)
    remaining_parents = tuple(
        item for index, item in enumerate(cpt.ordered_parent_nodes) if index != removed_index
    )
    remaining_axes = tuple(
        item for index, item in enumerate(cpt.ordered_parent_state_ids) if index != removed_index
    )
    if strategy == "marginalize":
        try:
            migrated = remove_parent_with_marginal_weights(
                to_legacy_cpt(cpt),
                _legacy_ref(parent),
                weights=marginal_weights,
            )
        except CptMigrationError as error:
            raise CurrentCptError(str(error)) from error
        return from_legacy_cpt(migrated)
    if strategy == "incomplete":
        return mark_cpt_incomplete(
            cpt,
            parent_nodes=remaining_parents,
            parent_state_ids=remaining_axes,
            reason="probabilistic_parent_removed_v1",
        )
    raise CurrentCptError(f"unsupported remove-parent strategy {strategy!r}")


def reorder_cpt_parents(
    cpt: NodeCpt,
    ordered_parents: tuple[ModelNodeRef, ...],
) -> NodeCpt:
    if set(ordered_parents) != set(cpt.ordered_parent_nodes) or len(ordered_parents) != len(
        cpt.ordered_parent_nodes
    ):
        raise CurrentCptError("reordered parents must be an exact permutation")
    old_axis_by_parent = dict(
        zip(cpt.ordered_parent_nodes, cpt.ordered_parent_state_ids, strict=True)
    )
    new_axes = tuple(old_axis_by_parent[parent] for parent in ordered_parents)
    if cpt.mode is CptMode.INCOMPLETE:
        return mark_cpt_incomplete(
            cpt,
            parent_nodes=ordered_parents,
            parent_state_ids=new_axes,
            reason="probabilistic_parent_order_changed_v1",
        )
    old_assignments = tuple(itertools.product(*cpt.ordered_parent_state_ids))
    row_by_assignment = dict(zip(old_assignments, cpt.materialized_probabilities, strict=True))
    new_rows = tuple(
        row_by_assignment[
            tuple(assignment[ordered_parents.index(parent)] for parent in cpt.ordered_parent_nodes)
        ]
        for assignment in itertools.product(*new_axes)
    )
    metadata = dict(cpt.generator_metadata)
    metadata["last_migration"] = "reorder_parent_axes_v1"
    return NodeCpt.model_validate(
        cpt.model_copy(
            update={
                "ordered_parent_nodes": ordered_parents,
                "ordered_parent_state_ids": new_axes,
                "materialized_probabilities": new_rows,
                "generator_metadata": metadata,
            }
        ).model_dump(mode="json")
    )


def materialize_cpt(
    cpt: NodeCpt,
    *,
    strategy: str,
    weights: tuple[float, ...] | None = None,
    weakest_link_strength: float = 0.0,
    sigma: float = 0.8,
) -> NodeCpt:
    try:
        if strategy == "uniform":
            prior = materialize_uniform_prior(cpt.child_state_ids)
            row_count = math.prod(len(states) for states in cpt.ordered_parent_state_ids)
            rows = prior.probabilities * row_count
        elif strategy == "ranked":
            if not cpt.ordered_parent_state_ids:
                raise CurrentCptError("ranked materialization requires at least one parent")
            effective_weights = (
                tuple(1.0 / len(cpt.ordered_parent_state_ids) for _ in cpt.ordered_parent_state_ids)
                if weights is None
                else weights
            )
            rows = materialize_ranked_cpt(
                cpt.ordered_parent_state_ids,
                cpt.child_state_ids,
                weights=effective_weights,
                weakest_link_strength=weakest_link_strength,
                sigma=sigma,
            ).probabilities
        else:
            raise CurrentCptError(f"unsupported materialization strategy {strategy!r}")
    except CptMaterializationError as error:
        raise CurrentCptError(str(error)) from error
    metadata = dict(cpt.generator_metadata)
    metadata["last_materialization"] = f"{strategy}_v1"
    return NodeCpt.model_validate(
        cpt.model_copy(
            update={
                "materialized_probabilities": rows,
                "mode": CptMode.GENERATED,
                "generator_metadata": metadata,
            }
        ).model_dump(mode="json")
    )


def update_cpt_probabilities(
    cpt: NodeCpt,
    rows: tuple[tuple[float, ...], ...],
) -> NodeCpt:
    metadata = dict(cpt.generator_metadata)
    metadata["last_edit"] = "manual_probability_batch_v1"
    try:
        return NodeCpt.model_validate(
            cpt.model_copy(
                update={
                    "materialized_probabilities": rows,
                    "mode": CptMode.MANUAL,
                    "generator_metadata": metadata,
                }
            ).model_dump(mode="json")
        )
    except ValueError as error:
        raise CurrentCptError(str(error)) from error


def invalidate_state_change_cpts(
    nodes: tuple[ModelNode, ...],
    changed_node: ModelNodeRef,
    new_state_ids: tuple[str, ...],
) -> dict[str, NodeCpt]:
    cpt_nodes = tuple(
        node
        for node in nodes
        if isinstance(node.definition, (EvidenceNodeDefinition, BnNodeDefinition))
    )
    legacy_cpts: list[CptVersion] = []
    for node in cpt_nodes:
        definition = node.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentCptError("Raw Input node leaked into CPT migration")
        legacy_cpts.append(to_legacy_cpt(definition.cpt))
    try:
        migrated = invalidate_cpts_for_state_change(
            tuple(legacy_cpts),
            _legacy_ref(changed_node),
            new_state_ids,
        )
    except CptMigrationError as error:
        raise CurrentCptError(str(error)) from error
    return {
        node.node_id: from_legacy_cpt(cpt) for node, cpt in zip(cpt_nodes, migrated, strict=True)
    }


def replace_definition_cpt(node: ModelNode, cpt: NodeCpt) -> ModelNode:
    definition = node.definition
    if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        raise CurrentCptError("Raw Input nodes do not have a CPT")
    return node.model_copy(update={"definition": definition.model_copy(update={"cpt": cpt})})


def replace_definition_states(
    node: ModelNode,
    states: tuple[VariableState, ...],
    cpt: NodeCpt,
) -> ModelNode:
    definition = node.definition
    if isinstance(definition, EvidenceNodeDefinition):
        updated = definition.model_copy(
            update={
                "ordered_observation_states": states,
                "cpt": cpt,
            }
        )
    elif isinstance(definition, BnNodeDefinition):
        updated = definition.model_copy(update={"ordered_states": states, "cpt": cpt})
    else:
        raise CurrentCptError("Raw Input nodes do not have Bayesian states")
    return node.model_copy(update={"definition": updated})


__all__ = [
    "CptEditorState",
    "CurrentCptError",
    "add_parent_to_cpt",
    "editor_state",
    "from_legacy_cpt",
    "invalidate_state_change_cpts",
    "mark_cpt_incomplete",
    "materialize_cpt",
    "node_state_ids",
    "remove_parent_from_cpt",
    "reorder_cpt_parents",
    "replace_definition_cpt",
    "replace_definition_states",
    "to_legacy_cpt",
    "update_cpt_probabilities",
    "validate_node_cpt",
]
