"""Typed, transport-neutral domain operations for editable M5 scheme drafts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias, cast

from pydantic import JsonValue

from pilot_assessment.contracts.assessment_scheme import (
    DraftComponentCandidate,
    NodePosition,
    SchemeDraft,
)
from pilot_assessment.contracts.bayesian import BayesianDependencyEdge, ExtractionEdge
from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    RecipeInputBinding,
    RecipeScoring,
)
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    EvidenceBindingVersion,
    PinnedComponentRef,
    VariableState,
)
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    component_kind,
)


class SchemeOperationError(ValueError):
    """Raised when a typed operation cannot be applied to the selected draft."""


@dataclass(frozen=True, slots=True)
class CloneComponentVersion:
    expected_graph_version: int
    source: ComponentIdRef
    candidate_id: str
    replace_source: bool = True


@dataclass(frozen=True, slots=True)
class StageNewComponentVersion:
    expected_graph_version: int
    kind: ComponentKind
    candidate_id: str
    payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AddExistingComponent:
    expected_graph_version: int
    reference: PinnedComponentRef


@dataclass(frozen=True, slots=True)
class RemoveComponent:
    expected_graph_version: int
    target: ComponentIdRef


@dataclass(frozen=True, slots=True)
class ReplaceEvidenceRecipe:
    expected_graph_version: int
    candidate_id: str
    recipe: EvidenceRecipe


@dataclass(frozen=True, slots=True)
class ReplaceEvidenceScoring:
    expected_graph_version: int
    candidate_id: str
    scoring: RecipeScoring | None


@dataclass(frozen=True, slots=True)
class ReplaceBnStates:
    expected_graph_version: int
    candidate_id: str
    ordered_states: tuple[VariableState, ...]


@dataclass(frozen=True, slots=True)
class ReplaceCptProbabilities:
    expected_graph_version: int
    candidate_id: str
    probabilities: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class ReplaceReportingPolicyRules:
    expected_graph_version: int
    candidate_id: str
    applicability_rules: Mapping[str, JsonValue]
    coverage_rules: Mapping[str, JsonValue]
    output_rules: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AddExtractionDependency:
    expected_graph_version: int
    edge: ExtractionEdge
    binding: RecipeInputBinding


@dataclass(frozen=True, slots=True)
class RemoveExtractionDependency:
    expected_graph_version: int
    edge_id: str


@dataclass(frozen=True, slots=True)
class AddBayesianDependency:
    expected_graph_version: int
    edge: BayesianDependencyEdge


@dataclass(frozen=True, slots=True)
class RemoveBayesianDependency:
    expected_graph_version: int
    edge_id: str


@dataclass(frozen=True, slots=True)
class SetOutputNodes:
    expected_graph_version: int
    output_node_ids: tuple[ComponentIdRef, ...]


@dataclass(frozen=True, slots=True)
class MoveLayoutNode:
    expected_layout_version: int
    candidate_id: str
    node_id: str
    x: float
    y: float


SchemeOperation: TypeAlias = (
    CloneComponentVersion
    | StageNewComponentVersion
    | AddExistingComponent
    | RemoveComponent
    | ReplaceEvidenceRecipe
    | ReplaceEvidenceScoring
    | ReplaceBnStates
    | ReplaceCptProbabilities
    | ReplaceReportingPolicyRules
    | AddExtractionDependency
    | RemoveExtractionDependency
    | AddBayesianDependency
    | RemoveBayesianDependency
    | SetOutputNodes
    | MoveLayoutNode
)


@dataclass(frozen=True, slots=True)
class OperationDiff:
    operation_type: str
    changed_paths: tuple[str, ...]
    added_component_ids: tuple[str, ...] = ()
    removed_component_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationApplication:
    draft: SchemeDraft
    diff: OperationDiff
    graph_changed: bool
    layout_changed: bool
    expected_graph_version: int | None
    expected_layout_version: int | None


_ID_FIELD_BY_KIND: dict[ComponentKind, str] = {
    ComponentKind.EVIDENCE_VERSION: "evidence_version_id",
    ComponentKind.BN_NODE_VERSION: "bn_node_version_id",
    ComponentKind.EVIDENCE_BINDING_VERSION: "evidence_binding_version_id",
    ComponentKind.CPT_VERSION: "cpt_version_id",
    ComponentKind.TASK_PROFILE_VERSION: "task_profile_version_id",
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: "policy_version_id",
    ComponentKind.LAYOUT_VERSION: "layout_version_id",
    ComponentKind.ASSESSMENT_SCHEME_VERSION: "scheme_version_id",
    ComponentKind.SOURCE_DESCRIPTOR: "source_id",
}


def _thaw(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _thaw(nested) for key, nested in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_thaw(nested) for nested in value]
    return cast(JsonValue, value)


def _replace_strings(value: JsonValue, replacements: Mapping[str, str]) -> JsonValue:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, dict):
        return {key: _replace_strings(nested, replacements) for key, nested in value.items()}
    if isinstance(value, list):
        return [_replace_strings(nested, replacements) for nested in value]
    return value


def _candidate(
    draft: SchemeDraft,
    candidate_id: str,
    *,
    expected_kind: ComponentKind | None = None,
) -> DraftComponentCandidate:
    try:
        candidate = next(
            item for item in draft.candidate_components if item.candidate_id == candidate_id
        )
    except StopIteration as error:
        raise SchemeOperationError(f"candidate {candidate_id!r} does not exist") from error
    if expected_kind is not None and candidate.kind is not expected_kind:
        raise SchemeOperationError(
            f"candidate {candidate_id!r} is {candidate.kind.value}, not {expected_kind.value}"
        )
    return candidate


def _replace_candidate(
    draft: SchemeDraft,
    candidate: DraftComponentCandidate,
) -> SchemeDraft:
    candidates = tuple(
        candidate if item.candidate_id == candidate.candidate_id else item
        for item in draft.candidate_components
    )
    return draft.model_copy(update={"candidate_components": candidates})


def _updated_candidate(
    candidate: DraftComponentCandidate,
    **payload_updates: JsonValue,
) -> DraftComponentCandidate:
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    payload.update(payload_updates)
    return candidate.model_copy(update={"payload": payload})


def _ref_replace(reference: ComponentIdRef, old_id: str, new_id: str) -> ComponentIdRef:
    if reference.version_id != old_id:
        return reference
    return reference.model_copy(update={"version_id": new_id})


def _clone_component(
    draft: SchemeDraft,
    operation: CloneComponentVersion,
    repository: ComponentLibraryRepository,
) -> SchemeDraft:
    selected_ids = {reference.version_id for reference in draft.retained_component_refs} | {
        candidate.candidate_id for candidate in draft.candidate_components
    }
    if operation.candidate_id in selected_ids:
        raise SchemeOperationError(f"candidate {operation.candidate_id!r} already exists")
    item = repository.get_exact(operation.source.kind, operation.source.version_id)
    if not hasattr(item, "content_hash"):
        raise SchemeOperationError("only immutable component versions can be cloned into a draft")
    if component_kind(item) is not operation.source.kind:
        raise SchemeOperationError("component kind mismatch")
    id_field = _ID_FIELD_BY_KIND.get(operation.source.kind)
    if id_field is None:
        raise SchemeOperationError(f"{operation.source.kind.value} cannot become a draft candidate")
    replacements = {
        candidate.base_version_id: candidate.candidate_id
        for candidate in draft.candidate_components
        if candidate.base_version_id is not None
    }
    replacements[operation.source.version_id] = operation.candidate_id
    payload = cast(JsonValue, item.model_dump(mode="json"))
    rewritten = _replace_strings(payload, replacements)
    if not isinstance(rewritten, dict):
        raise SchemeOperationError("component payload must be an object")
    rewritten[id_field] = operation.candidate_id
    candidate = DraftComponentCandidate(
        kind=operation.source.kind,
        candidate_id=operation.candidate_id,
        base_version_id=operation.source.version_id,
        payload=rewritten,
    )
    retained = draft.retained_component_refs
    if operation.replace_source:
        retained = tuple(
            reference
            for reference in retained
            if not (
                reference.kind is operation.source.kind
                and reference.version_id == operation.source.version_id
            )
        )
    existing_candidates = tuple(
        existing.model_copy(
            update={
                "payload": _replace_strings(
                    cast(JsonValue, _thaw(existing.payload)),
                    {operation.source.version_id: operation.candidate_id},
                )
            }
        )
        for existing in draft.candidate_components
    )
    extraction_edges = tuple(
        edge.model_copy(
            update={
                "source_descriptor_id": (
                    operation.candidate_id
                    if edge.source_descriptor_id == operation.source.version_id
                    else edge.source_descriptor_id
                ),
                "target_evidence_version_id": (
                    operation.candidate_id
                    if edge.target_evidence_version_id == operation.source.version_id
                    else edge.target_evidence_version_id
                ),
            }
        )
        for edge in draft.extraction_edges
    )
    bayesian_edges = tuple(
        edge.model_copy(
            update={
                "parent_variable_id": _ref_replace(
                    edge.parent_variable_id,
                    operation.source.version_id,
                    operation.candidate_id,
                ),
                "child_variable_id": _ref_replace(
                    edge.child_variable_id,
                    operation.source.version_id,
                    operation.candidate_id,
                ),
            }
        )
        for edge in draft.bayesian_edges
    )
    outputs = tuple(
        _ref_replace(output, operation.source.version_id, operation.candidate_id)
        for output in draft.output_node_ids
    )
    return draft.model_copy(
        update={
            "retained_component_refs": retained,
            "candidate_components": (*existing_candidates, candidate),
            "extraction_edges": extraction_edges,
            "bayesian_edges": bayesian_edges,
            "output_node_ids": outputs,
        }
    )


def _stage_new_component(
    draft: SchemeDraft,
    operation: StageNewComponentVersion,
) -> SchemeDraft:
    selected_ids = {reference.version_id for reference in draft.retained_component_refs} | {
        candidate.candidate_id for candidate in draft.candidate_components
    }
    if operation.candidate_id in selected_ids:
        raise SchemeOperationError(f"candidate {operation.candidate_id!r} already exists")
    id_field = _ID_FIELD_BY_KIND.get(operation.kind)
    if id_field is None or operation.kind is ComponentKind.ASSESSMENT_SCHEME_VERSION:
        raise SchemeOperationError(
            f"{operation.kind.value} cannot be staged as a component candidate"
        )
    payload = cast(dict[str, JsonValue], _thaw(operation.payload))
    payload[id_field] = operation.candidate_id
    payload.setdefault("content_hash", "0" * 64)
    candidate = DraftComponentCandidate(
        kind=operation.kind,
        candidate_id=operation.candidate_id,
        base_version_id=None,
        payload=payload,
    )
    return draft.model_copy(
        update={"candidate_components": (*draft.candidate_components, candidate)}
    )


def _remove_component(draft: SchemeDraft, operation: RemoveComponent) -> SchemeDraft:
    retained = tuple(
        reference
        for reference in draft.retained_component_refs
        if not (
            reference.kind is operation.target.kind
            and reference.version_id == operation.target.version_id
        )
    )
    candidates = tuple(
        candidate
        for candidate in draft.candidate_components
        if not (
            candidate.kind is operation.target.kind
            and candidate.candidate_id == operation.target.version_id
        )
    )
    if retained == draft.retained_component_refs and candidates == draft.candidate_components:
        raise SchemeOperationError(
            f"component {operation.target.kind.value}:{operation.target.version_id} is not selected"
        )
    return draft.model_copy(
        update={"retained_component_refs": retained, "candidate_components": candidates}
    )


def _replace_evidence_recipe(
    draft: SchemeDraft,
    operation: ReplaceEvidenceRecipe,
) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.EVIDENCE_VERSION,
    )
    updated = _updated_candidate(
        candidate,
        recipe=cast(JsonValue, operation.recipe.model_dump(mode="json")),
    )
    return _replace_candidate(draft, updated)


def _replace_evidence_scoring(
    draft: SchemeDraft,
    operation: ReplaceEvidenceScoring,
) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.EVIDENCE_VERSION,
    )
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    recipe = payload.get("recipe")
    if not isinstance(recipe, dict):
        raise SchemeOperationError("Evidence candidate has no editable recipe object")
    recipe["scoring"] = (
        None if operation.scoring is None else operation.scoring.model_dump(mode="json")
    )
    updated = candidate.model_copy(update={"payload": payload})
    return _replace_candidate(draft, updated)


def _replace_bn_states(draft: SchemeDraft, operation: ReplaceBnStates) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.BN_NODE_VERSION,
    )
    updated = _updated_candidate(
        candidate,
        ordered_states=cast(
            JsonValue,
            [state.model_dump(mode="json") for state in operation.ordered_states],
        ),
    )
    return _replace_candidate(draft, updated)


def _replace_cpt_probabilities(
    draft: SchemeDraft,
    operation: ReplaceCptProbabilities,
) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.CPT_VERSION,
    )
    probabilities = [list(row) for row in operation.probabilities]
    updated = _updated_candidate(
        candidate,
        materialized_probabilities=cast(JsonValue, probabilities),
    )
    return _replace_candidate(draft, updated)


def _replace_reporting_rules(
    draft: SchemeDraft,
    operation: ReplaceReportingPolicyRules,
) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
    )
    updated = _updated_candidate(
        candidate,
        applicability_rules=cast(JsonValue, dict(operation.applicability_rules)),
        coverage_rules=cast(JsonValue, dict(operation.coverage_rules)),
        output_rules=cast(JsonValue, dict(operation.output_rules)),
    )
    return _replace_candidate(draft, updated)


def _add_extraction(
    draft: SchemeDraft,
    operation: AddExtractionDependency,
) -> SchemeDraft:
    edge = operation.edge
    if operation.binding.binding_id != edge.input_binding_id:
        raise SchemeOperationError("extraction binding ID must match the typed edge")
    if operation.binding.source_id != edge.source_descriptor_id:
        raise SchemeOperationError("extraction binding source must match the typed edge")
    if any(existing.edge_id == edge.edge_id for existing in draft.extraction_edges):
        raise SchemeOperationError(f"edge {edge.edge_id!r} already exists")
    candidate = _candidate(
        draft,
        edge.target_evidence_version_id,
        expected_kind=ComponentKind.EVIDENCE_VERSION,
    )
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    recipe = payload.get("recipe")
    if not isinstance(recipe, dict):
        raise SchemeOperationError("Evidence candidate has no editable recipe object")
    inputs = recipe.get("inputs")
    if not isinstance(inputs, list):
        raise SchemeOperationError("Evidence candidate recipe inputs are not an array")
    if any(
        isinstance(item, dict) and item.get("binding_id") == edge.input_binding_id
        for item in inputs
    ):
        raise SchemeOperationError(f"input binding {edge.input_binding_id!r} already exists")
    inputs.append(operation.binding.model_dump(mode="json"))
    updated = candidate.model_copy(update={"payload": payload})
    draft = _replace_candidate(draft, updated)
    return draft.model_copy(update={"extraction_edges": (*draft.extraction_edges, edge)})


def _remove_extraction(
    draft: SchemeDraft,
    operation: RemoveExtractionDependency,
) -> SchemeDraft:
    try:
        edge = next(item for item in draft.extraction_edges if item.edge_id == operation.edge_id)
    except StopIteration as error:
        raise SchemeOperationError(
            f"extraction edge {operation.edge_id!r} does not exist"
        ) from error
    candidate = _candidate(
        draft,
        edge.target_evidence_version_id,
        expected_kind=ComponentKind.EVIDENCE_VERSION,
    )
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    recipe = payload.get("recipe")
    if not isinstance(recipe, dict) or not isinstance(recipe.get("inputs"), list):
        raise SchemeOperationError("Evidence candidate recipe inputs are not editable")
    recipe["inputs"] = [
        item
        for item in cast(list[JsonValue], recipe["inputs"])
        if not (isinstance(item, dict) and item.get("binding_id") == edge.input_binding_id)
    ]
    updated = candidate.model_copy(update={"payload": payload})
    draft = _replace_candidate(draft, updated)
    return draft.model_copy(
        update={
            "extraction_edges": tuple(
                item for item in draft.extraction_edges if item.edge_id != operation.edge_id
            )
        }
    )


def _variable_candidate(
    draft: SchemeDraft,
    reference: ComponentIdRef,
) -> DraftComponentCandidate:
    expected = {
        ComponentKind.BN_NODE_VERSION: BnNodeVersion,
        ComponentKind.EVIDENCE_BINDING_VERSION: EvidenceBindingVersion,
    }
    if reference.kind not in expected:
        raise SchemeOperationError("Bayesian edge child must be a variable candidate")
    return _candidate(draft, reference.version_id, expected_kind=reference.kind)


def _add_bayesian(
    draft: SchemeDraft,
    operation: AddBayesianDependency,
) -> SchemeDraft:
    edge = operation.edge
    if any(existing.edge_id == edge.edge_id for existing in draft.bayesian_edges):
        raise SchemeOperationError(f"edge {edge.edge_id!r} already exists")
    candidate = _variable_candidate(draft, edge.child_variable_id)
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    parents = payload.get("ordered_probabilistic_parent_ids")
    if not isinstance(parents, list):
        raise SchemeOperationError("variable candidate parents are not an array")
    parent = edge.parent_variable_id.model_dump(mode="json")
    if parent in parents:
        raise SchemeOperationError("Bayesian parent already exists")
    parents.append(parent)
    updated = candidate.model_copy(update={"payload": payload})
    draft = _replace_candidate(draft, updated)
    return draft.model_copy(update={"bayesian_edges": (*draft.bayesian_edges, edge)})


def _remove_bayesian(
    draft: SchemeDraft,
    operation: RemoveBayesianDependency,
) -> SchemeDraft:
    try:
        edge = next(item for item in draft.bayesian_edges if item.edge_id == operation.edge_id)
    except StopIteration as error:
        raise SchemeOperationError(f"Bayesian edge {operation.edge_id!r} does not exist") from error
    candidate = _variable_candidate(draft, edge.child_variable_id)
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    parents = payload.get("ordered_probabilistic_parent_ids")
    if not isinstance(parents, list):
        raise SchemeOperationError("variable candidate parents are not an array")
    payload["ordered_probabilistic_parent_ids"] = [
        item for item in parents if item != edge.parent_variable_id.model_dump(mode="json")
    ]
    updated = candidate.model_copy(update={"payload": payload})
    draft = _replace_candidate(draft, updated)
    return draft.model_copy(
        update={
            "bayesian_edges": tuple(
                item for item in draft.bayesian_edges if item.edge_id != operation.edge_id
            )
        }
    )


def _move_layout(draft: SchemeDraft, operation: MoveLayoutNode) -> SchemeDraft:
    candidate = _candidate(
        draft,
        operation.candidate_id,
        expected_kind=ComponentKind.LAYOUT_VERSION,
    )
    payload = cast(dict[str, JsonValue], _thaw(candidate.payload))
    positions = payload.get("node_positions")
    if not isinstance(positions, list):
        raise SchemeOperationError("layout candidate node_positions are not an array")
    replacement = NodePosition(
        node_id=operation.node_id,
        x=operation.x,
        y=operation.y,
    ).model_dump(mode="json")
    found = False
    for index, position in enumerate(positions):
        if isinstance(position, dict) and position.get("node_id") == operation.node_id:
            positions[index] = replacement
            found = True
            break
    if not found:
        positions.append(replacement)
    updated = candidate.model_copy(update={"payload": payload})
    return _replace_candidate(draft, updated)


def apply_scheme_operation(
    draft: SchemeDraft,
    operation: SchemeOperation,
    repository: ComponentLibraryRepository,
) -> OperationApplication:
    """Apply one typed user intent without requiring the draft to be executable."""

    expected_graph = getattr(operation, "expected_graph_version", None)
    expected_layout = getattr(operation, "expected_layout_version", None)
    graph_changed = not isinstance(operation, MoveLayoutNode)
    layout_changed = isinstance(operation, MoveLayoutNode)
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    if isinstance(operation, CloneComponentVersion):
        proposed = _clone_component(draft, operation, repository)
        added = (operation.candidate_id,)
        if operation.replace_source:
            removed = (operation.source.version_id,)
        paths = ("/candidate_components", "/retained_component_refs")
    elif isinstance(operation, StageNewComponentVersion):
        proposed = _stage_new_component(draft, operation)
        added = (operation.candidate_id,)
        paths = ("/candidate_components",)
    elif isinstance(operation, AddExistingComponent):
        item = repository.get_exact(
            operation.reference.kind,
            operation.reference.version_id,
        )
        if getattr(item, "content_hash", None) != operation.reference.content_hash:
            raise SchemeOperationError("exact component pin hash does not match the library")
        if operation.reference in draft.retained_component_refs:
            raise SchemeOperationError("component is already selected")
        proposed = draft.model_copy(
            update={
                "retained_component_refs": (
                    *draft.retained_component_refs,
                    operation.reference,
                )
            }
        )
        added = (operation.reference.version_id,)
        paths = ("/retained_component_refs",)
    elif isinstance(operation, RemoveComponent):
        proposed = _remove_component(draft, operation)
        removed = (operation.target.version_id,)
        paths = ("/retained_component_refs", "/candidate_components")
    elif isinstance(operation, ReplaceEvidenceRecipe):
        proposed = _replace_evidence_recipe(draft, operation)
        paths = (f"/candidate_components/{operation.candidate_id}/payload/recipe",)
    elif isinstance(operation, ReplaceEvidenceScoring):
        proposed = _replace_evidence_scoring(draft, operation)
        paths = (f"/candidate_components/{operation.candidate_id}/payload/recipe/scoring",)
    elif isinstance(operation, ReplaceBnStates):
        proposed = _replace_bn_states(draft, operation)
        paths = (f"/candidate_components/{operation.candidate_id}/payload/ordered_states",)
    elif isinstance(operation, ReplaceCptProbabilities):
        proposed = _replace_cpt_probabilities(draft, operation)
        paths = (
            f"/candidate_components/{operation.candidate_id}/payload/materialized_probabilities",
        )
    elif isinstance(operation, ReplaceReportingPolicyRules):
        proposed = _replace_reporting_rules(draft, operation)
        paths = (f"/candidate_components/{operation.candidate_id}/payload",)
    elif isinstance(operation, AddExtractionDependency):
        proposed = _add_extraction(draft, operation)
        paths = ("/extraction_edges", "/candidate_components")
    elif isinstance(operation, RemoveExtractionDependency):
        proposed = _remove_extraction(draft, operation)
        paths = ("/extraction_edges", "/candidate_components")
    elif isinstance(operation, AddBayesianDependency):
        proposed = _add_bayesian(draft, operation)
        paths = ("/bayesian_edges", "/candidate_components")
    elif isinstance(operation, RemoveBayesianDependency):
        proposed = _remove_bayesian(draft, operation)
        paths = ("/bayesian_edges", "/candidate_components")
    elif isinstance(operation, SetOutputNodes):
        proposed = draft.model_copy(update={"output_node_ids": operation.output_node_ids})
        paths = ("/output_node_ids",)
    elif isinstance(operation, MoveLayoutNode):
        proposed = _move_layout(draft, operation)
        paths = (f"/candidate_components/{operation.candidate_id}/payload/node_positions",)
    else:  # pragma: no cover - exhaustive union guard
        raise SchemeOperationError(f"unsupported operation {type(operation).__name__}")

    return OperationApplication(
        draft=proposed,
        diff=OperationDiff(
            operation_type=type(operation).__name__,
            changed_paths=paths,
            added_component_ids=added,
            removed_component_ids=removed,
        ),
        graph_changed=graph_changed,
        layout_changed=layout_changed,
        expected_graph_version=expected_graph,
        expected_layout_version=expected_layout,
    )


__all__ = [
    "AddBayesianDependency",
    "AddExistingComponent",
    "AddExtractionDependency",
    "CloneComponentVersion",
    "MoveLayoutNode",
    "OperationApplication",
    "OperationDiff",
    "RemoveBayesianDependency",
    "RemoveComponent",
    "RemoveExtractionDependency",
    "ReplaceBnStates",
    "ReplaceCptProbabilities",
    "ReplaceEvidenceRecipe",
    "ReplaceEvidenceScoring",
    "ReplaceReportingPolicyRules",
    "SchemeOperation",
    "SchemeOperationError",
    "SetOutputNodes",
    "StageNewComponentVersion",
    "apply_scheme_operation",
]
