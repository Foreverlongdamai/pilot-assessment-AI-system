"""Run-blocking technical validation without scientific truth gates."""

from __future__ import annotations

from collections.abc import Iterable, Set
from dataclasses import dataclass

from pydantic import ValidationError

from pilot_assessment.contracts.model_components import (
    CptMode,
    ModelScientificStatus,
)
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelDiagnostic,
    ModelDiagnosticSeverity,
    ModelGraphEdge,
    ModelNode,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeCpt,
    RawInputNodeDefinition,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import validate_recipe
from pilot_assessment.model_workspace.graph import (
    ModelGraphError,
    ensure_probabilistic_acyclic,
    project_model_edges,
)
from pilot_assessment.model_workspace.hashing import (
    model_node_layout_hash,
    model_node_semantic_hash,
)


@dataclass(frozen=True, slots=True)
class ModelValidationOutcome:
    technical_status: ModelTechnicalStatus
    diagnostics: tuple[ModelDiagnostic, ...]
    projected_edges: tuple[ModelGraphEdge, ...]


def _diagnostic(
    code: str,
    severity: ModelDiagnosticSeverity,
    location: str,
    message: str,
    **details: str,
) -> ModelDiagnostic:
    return ModelDiagnostic(
        code=code,
        severity=severity,
        location=location,
        message=message,
        details=details,
    )


def _state_ids(node: ModelNode) -> tuple[str, ...] | None:
    if isinstance(node.definition, EvidenceNodeDefinition):
        return tuple(state.state_id for state in node.definition.ordered_observation_states)
    if isinstance(node.definition, BnNodeDefinition):
        return tuple(state.state_id for state in node.definition.ordered_states)
    return None


def _validate_cpt_axes(
    node: ModelNode,
    index: dict[str, ModelNode],
    diagnostics: list[ModelDiagnostic],
) -> None:
    definition = node.definition
    if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
        return
    try:
        NodeCpt.model_validate(definition.cpt.model_dump(mode="python"))
    except ValidationError:
        diagnostics.append(
            _diagnostic(
                "model.cpt_invalid",
                ModelDiagnosticSeverity.ERROR,
                f"/nodes/{node.node_id}/definition/cpt",
                "active node CPT has an impossible shape, axis or probability row",
            )
        )
        return
    if definition.cpt.mode is CptMode.INCOMPLETE:
        diagnostics.append(
            _diagnostic(
                "model.cpt_incomplete",
                ModelDiagnosticSeverity.ERROR,
                f"/nodes/{node.node_id}/definition/cpt",
                "active node CPT is explicitly incomplete",
            )
        )
    for position, (parent_ref, declared_states) in enumerate(
        zip(
            definition.cpt.ordered_parent_nodes,
            definition.cpt.ordered_parent_state_ids,
            strict=True,
        )
    ):
        parent = index.get(parent_ref.node_id)
        if parent is None:
            continue
        actual_states = _state_ids(parent)
        if actual_states is not None and declared_states != actual_states:
            diagnostics.append(
                _diagnostic(
                    "model.cpt_parent_axis_mismatch",
                    ModelDiagnosticSeverity.ERROR,
                    f"/nodes/{node.node_id}/definition/cpt/ordered_parent_state_ids/{position}",
                    "CPT parent state axis does not match the referenced parent state order",
                    parent_node_id=parent.node_id,
                )
            )


def _validate_raw_source(
    node: ModelNode,
    available_source_ids: Set[str],
    diagnostics: list[ModelDiagnostic],
) -> None:
    definition = node.definition
    if not isinstance(definition, RawInputNodeDefinition):
        return
    descriptor = definition.source_descriptor
    required = (descriptor.source_id, *descriptor.source_dependencies)
    for source_id in required:
        if source_id not in available_source_ids:
            diagnostics.append(
                _diagnostic(
                    "model.source_unavailable",
                    ModelDiagnosticSeverity.ERROR,
                    f"/nodes/{node.node_id}/definition/source_descriptor/source_id",
                    f"required source provider {source_id!r} is unavailable",
                    source_id=source_id,
                )
            )


def _validate_evidence_recipe(
    node: ModelNode,
    index: dict[str, ModelNode],
    registry: OperatorRegistry,
    diagnostics: list[ModelDiagnostic],
) -> None:
    definition = node.definition
    if not isinstance(definition, EvidenceNodeDefinition):
        return
    recipe_inputs = {item.binding_id: item for item in definition.recipe.inputs}
    for position, binding in enumerate(definition.data_bindings):
        raw_node = index.get(binding.raw_input_node.node_id)
        if raw_node is None or not isinstance(raw_node.definition, RawInputNodeDefinition):
            continue
        recipe_input = recipe_inputs[binding.recipe_input_binding_id]
        actual_source = raw_node.definition.source_descriptor.source_id
        if recipe_input.source_id != actual_source:
            diagnostics.append(
                _diagnostic(
                    "model.recipe_source_binding_mismatch",
                    ModelDiagnosticSeverity.ERROR,
                    f"/nodes/{node.node_id}/definition/data_bindings/{position}",
                    "recipe source ID does not match the bound Raw Input source descriptor",
                    recipe_source_id=recipe_input.source_id,
                    raw_source_id=actual_source,
                )
            )
    outcome = validate_recipe(definition.recipe, registry)
    for recipe_diagnostic in outcome.diagnostics:
        suffix = recipe_diagnostic.code.removeprefix("recipe.")
        diagnostics.append(
            _diagnostic(
                f"model.recipe.{suffix}",
                ModelDiagnosticSeverity.ERROR,
                f"/nodes/{node.node_id}/definition/recipe{recipe_diagnostic.location}",
                recipe_diagnostic.message,
            )
        )


def validate_model_graph(
    nodes: Iterable[ModelNode],
    *,
    active_node_ids: Iterable[str],
    operator_registry: OperatorRegistry,
    available_source_ids: Set[str],
) -> ModelValidationOutcome:
    """Validate only the active closure so inactive experiments remain freely editable."""

    node_tuple = tuple(nodes)
    index = {node.node_id: node for node in node_tuple}
    active = tuple(sorted(set(active_node_ids)))
    diagnostics: list[ModelDiagnostic] = []
    projected_edges: tuple[ModelGraphEdge, ...] = ()
    try:
        projected_edges = project_model_edges(node_tuple, node_ids=active)
        ensure_probabilistic_acyclic(projected_edges, node_ids=active)
    except ModelGraphError as error:
        diagnostics.append(
            _diagnostic(
                error.code,
                ModelDiagnosticSeverity.ERROR,
                error.location,
                str(error),
            )
        )

    for node_id in active:
        node = index.get(node_id)
        if node is None:
            continue
        if node.lifecycle is not ModelObjectLifecycle.ACTIVE:
            diagnostics.append(
                _diagnostic(
                    "model.active_node_archived",
                    ModelDiagnosticSeverity.ERROR,
                    f"/nodes/{node_id}/lifecycle",
                    "active closure cannot contain an archived node",
                )
            )
        if node.content_hash != model_node_semantic_hash(node):
            diagnostics.append(
                _diagnostic(
                    "model.content_hash_mismatch",
                    ModelDiagnosticSeverity.ERROR,
                    f"/nodes/{node_id}/content_hash",
                    "stored node semantic hash does not match current content",
                )
            )
        if node.layout_hash != model_node_layout_hash(node):
            diagnostics.append(
                _diagnostic(
                    "model.layout_hash_mismatch",
                    ModelDiagnosticSeverity.WARNING,
                    f"/nodes/{node_id}/layout_hash",
                    "stored layout hash does not match current visual layout",
                )
            )
        _validate_raw_source(node, available_source_ids, diagnostics)
        _validate_evidence_recipe(node, index, operator_registry, diagnostics)
        _validate_cpt_axes(node, index, diagnostics)
        if isinstance(node.definition, (EvidenceNodeDefinition, BnNodeDefinition)) and (
            node.definition.scientific_status
            in {
                ModelScientificStatus.STARTER_TEMPLATE,
                ModelScientificStatus.ENGINEERING_DEFAULT,
            }
        ):
            diagnostics.append(
                _diagnostic(
                    "model.scientific_status_provisional",
                    ModelDiagnosticSeverity.WARNING,
                    f"/nodes/{node_id}/definition/scientific_status",
                    "starter or engineering scientific content remains open to expert replacement",
                )
            )

    ordered = tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.location, item.code, item.message),
        )
    )
    status = (
        ModelTechnicalStatus.BLOCKED
        if any(item.severity is ModelDiagnosticSeverity.ERROR for item in ordered)
        else ModelTechnicalStatus.EXECUTABLE
    )
    return ModelValidationOutcome(
        technical_status=status,
        diagnostics=ordered,
        projected_edges=projected_edges,
    )


__all__ = ["ModelValidationOutcome", "validate_model_graph"]
