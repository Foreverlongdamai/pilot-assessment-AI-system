"""Exact-reference and only-technical validation for M5 assessment schemes."""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar, cast

from pilot_assessment.bayesian.validation import (
    CptDiagnosticSeverity,
    validate_cpt,
)
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    SchemeDraft,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
    ModelScientificStatus,
    PinnedComponentRef,
    RawModality,
    SourceDescriptor,
    SourceKind,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import validate_recipe
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    LibraryItem,
    LibraryItemNotFoundError,
    VersionLibraryItem,
    component_content_hash,
)
from pilot_assessment.model_library.sources import (
    SourceCatalog,
    SourceCatalogError,
    SourceCatalogLookupError,
    SourceDiagnosticCode,
)


class SchemeValidationDisposition(StrEnum):
    DRAFT_INCOMPLETE = "draft_incomplete"
    INVALID = "invalid"
    EXECUTABLE = "executable"


class SchemeDiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class SchemeDiagnostic:
    code: str
    severity: SchemeDiagnosticSeverity
    location: str
    component_id: str | None
    message: str

    @property
    def blocking(self) -> bool:
        return self.severity is SchemeDiagnosticSeverity.ERROR


@dataclass(frozen=True, slots=True)
class SchemeValidationOutcome:
    disposition: SchemeValidationDisposition
    diagnostics: tuple[SchemeDiagnostic, ...]


_TVersion = TypeVar("_TVersion", bound=VersionLibraryItem)


def _pointer(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _diagnostic(
    diagnostics: list[SchemeDiagnostic],
    code: str,
    location: str,
    message: str,
    *,
    component_id: str | None = None,
    severity: SchemeDiagnosticSeverity = SchemeDiagnosticSeverity.ERROR,
) -> None:
    diagnostics.append(
        SchemeDiagnostic(
            code=code,
            severity=severity,
            location=location,
            component_id=component_id,
            message=message,
        )
    )


def _ordered(diagnostics: Iterable[SchemeDiagnostic]) -> tuple[SchemeDiagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.location,
                item.code,
                item.component_id or "",
                item.message,
            ),
        )
    )


def _key(reference: ComponentIdRef | PinnedComponentRef) -> tuple[ComponentKind, str]:
    return (reference.kind, reference.version_id)


def _pin_entries(
    scheme: AssessmentSchemeVersion,
) -> tuple[tuple[PinnedComponentRef, str], ...]:
    entries: list[tuple[PinnedComponentRef, str]] = [
        (scheme.task_profile, "/task_profile"),
        (scheme.reporting_policy, "/reporting_policy"),
        (scheme.layout, "/layout"),
    ]
    for field in (
        "source_descriptors",
        "evidence_versions",
        "evidence_binding_versions",
        "bn_node_versions",
        "cpt_versions",
    ):
        references = cast(tuple[PinnedComponentRef, ...], getattr(scheme, field))
        entries.extend(
            (reference, f"/{field}/{index}") for index, reference in enumerate(references)
        )
    return tuple(entries)


def _load_pins(
    scheme: AssessmentSchemeVersion,
    repository: ComponentLibraryRepository,
    diagnostics: list[SchemeDiagnostic],
) -> dict[tuple[ComponentKind, str], LibraryItem]:
    loaded: dict[tuple[ComponentKind, str], LibraryItem] = {}
    seen: set[tuple[ComponentKind, str]] = set()
    variable_seen: set[tuple[ComponentKind, str]] = set()
    variable_kinds = {ComponentKind.BN_NODE_VERSION, ComponentKind.EVIDENCE_BINDING_VERSION}
    for reference, location in _pin_entries(scheme):
        key = _key(reference)
        if key in seen:
            _diagnostic(
                diagnostics,
                "scheme.pin_duplicate",
                location,
                f"exact component pin {reference.kind.value}:{reference.version_id} is duplicated",
                component_id=reference.version_id,
            )
        seen.add(key)
        if reference.kind in variable_kinds:
            if key in variable_seen:
                _diagnostic(
                    diagnostics,
                    "scheme.variable_duplicate",
                    location,
                    f"BN variable {reference.kind.value}:{reference.version_id} is duplicated",
                    component_id=reference.version_id,
                )
            variable_seen.add(key)
        try:
            item = repository.get_exact(reference.kind, reference.version_id)
        except LibraryItemNotFoundError:
            _diagnostic(
                diagnostics,
                "scheme.reference_missing",
                location,
                f"exact component {reference.kind.value}:{reference.version_id} does not exist",
                component_id=reference.version_id,
            )
            continue
        if hasattr(item, "content_hash"):
            actual_hash = component_content_hash(cast(VersionLibraryItem, item))
            if reference.content_hash != actual_hash:
                _diagnostic(
                    diagnostics,
                    "scheme.pin_hash_mismatch",
                    f"{location}/content_hash",
                    "pinned hash does not match the exact stored component",
                    component_id=reference.version_id,
                )
        loaded.setdefault(key, item)
    return loaded


def _typed(
    loaded: dict[tuple[ComponentKind, str], LibraryItem],
    kind: ComponentKind,
    item_type: type[_TVersion],
) -> dict[str, _TVersion]:
    return {
        record_id: item
        for (record_kind, record_id), item in loaded.items()
        if record_kind is kind and isinstance(item, item_type)
    }


def _has_cycle(
    node_ids: set[tuple[ComponentKind, str]],
    edges: list[tuple[tuple[ComponentKind, str], tuple[ComponentKind, str]]],
) -> bool:
    adjacency: dict[tuple[ComponentKind, str], list[tuple[ComponentKind, str]]] = {
        node_id: [] for node_id in node_ids
    }
    indegree = dict.fromkeys(node_ids, 0)
    for parent, child in edges:
        if parent not in node_ids or child not in node_ids:
            continue
        adjacency[parent].append(child)
        indegree[child] += 1
    for targets in adjacency.values():
        targets.sort(key=lambda item: (item[0].value, item[1]))
    queue = [
        (kind.value, record_id, (kind, record_id))
        for (kind, record_id), degree in indegree.items()
        if degree == 0
    ]
    heapq.heapify(queue)
    visited = 0
    while queue:
        _, _, node = heapq.heappop(queue)
        visited += 1
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(queue, (target[0].value, target[1], target))
    return visited != len(node_ids)


def _reachable_undirected(
    node_ids: set[tuple[ComponentKind, str]],
    edges: list[tuple[tuple[ComponentKind, str], tuple[ComponentKind, str]]],
    starts: set[tuple[ComponentKind, str]],
) -> set[tuple[ComponentKind, str]]:
    adjacency = {node_id: set() for node_id in node_ids}
    for left, right in edges:
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    reached: set[tuple[ComponentKind, str]] = set()
    pending = list(starts)
    while pending:
        node = pending.pop()
        if node in reached or node not in adjacency:
            continue
        reached.add(node)
        pending.extend(adjacency[node] - reached)
    return reached


def validate_executable_scheme(
    scheme: AssessmentSchemeVersion,
    repository: ComponentLibraryRepository,
    source_catalog: SourceCatalog,
    operator_registry: OperatorRegistry,
) -> SchemeValidationOutcome:
    """Validate exact closure and executability without imposing scientific approval."""

    diagnostics: list[SchemeDiagnostic] = []
    if scheme.content_hash != component_content_hash(scheme):
        _diagnostic(
            diagnostics,
            "scheme.content_hash_mismatch",
            "/content_hash",
            "scheme content hash does not match its canonical payload",
            component_id=scheme.scheme_version_id,
        )
    loaded = _load_pins(scheme, repository, diagnostics)

    source_items = _typed(loaded, ComponentKind.SOURCE_DESCRIPTOR, SourceDescriptor)
    evidence_items = _typed(loaded, ComponentKind.EVIDENCE_VERSION, EvidenceVersion)
    binding_items = _typed(
        loaded,
        ComponentKind.EVIDENCE_BINDING_VERSION,
        EvidenceBindingVersion,
    )
    bn_items = _typed(loaded, ComponentKind.BN_NODE_VERSION, BnNodeVersion)
    cpt_items = _typed(loaded, ComponentKind.CPT_VERSION, CptVersion)
    task_item = loaded.get(_key(scheme.task_profile))
    task_profile = task_item if isinstance(task_item, TaskProfileVersion) else None

    for source_id, descriptor in source_items.items():
        try:
            registered = source_catalog.get(source_id)
        except SourceCatalogLookupError:
            _diagnostic(
                diagnostics,
                "scheme.source_catalog_mismatch",
                f"/source_descriptors/{_pointer(source_id)}",
                "pinned source is not present in the selected source catalog",
                component_id=source_id,
            )
            continue
        if registered.content_hash != descriptor.content_hash:
            _diagnostic(
                diagnostics,
                "scheme.source_catalog_mismatch",
                f"/source_descriptors/{_pointer(source_id)}/content_hash",
                "pinned source differs from the selected source catalog descriptor",
                component_id=source_id,
            )

    try:
        scheme_sources = SourceCatalog(source_items.values())
    except SourceCatalogError as error:
        _diagnostic(
            diagnostics,
            "scheme.source_catalog_invalid",
            "/source_descriptors",
            str(error),
        )
        scheme_sources = SourceCatalog()

    used_source_ids: set[str] = set()
    evidence_modalities: dict[str, set[RawModality]] = {}
    task_required = (
        set(task_profile.required_source_descriptor_ids) if task_profile is not None else set()
    )
    used_source_ids.update(task_required)
    for source_id in sorted(task_required):
        if source_id not in source_items:
            _diagnostic(
                diagnostics,
                "scheme.task_source_missing",
                "/task_profile/required_source_descriptor_ids",
                f"task profile requires unpinned source {source_id!r}",
                component_id=source_id,
            )

    for evidence_id, evidence in evidence_items.items():
        recipe_outcome = validate_recipe(evidence.recipe, operator_registry)
        for recipe_diagnostic in recipe_outcome.diagnostics:
            _diagnostic(
                diagnostics,
                recipe_diagnostic.code,
                f"/evidence_versions/{_pointer(evidence_id)}/recipe{recipe_diagnostic.location}",
                recipe_diagnostic.message,
                component_id=evidence_id,
            )
        source_ids = tuple(binding.source_id for binding in evidence.recipe.inputs)
        closure = scheme_sources.validate_extraction_sources(source_ids)
        used_source_ids.update(closure.resolved_source_ids)
        evidence_modalities[evidence_id] = set(closure.raw_modalities)
        for source_diagnostic in closure.diagnostics:
            code = (
                "scheme.source_missing"
                if source_diagnostic.code is SourceDiagnosticCode.UNKNOWN_SOURCE
                else "scheme.source_provenance_invalid"
            )
            _diagnostic(
                diagnostics,
                code,
                f"/evidence_versions/{_pointer(evidence_id)}/recipe/inputs",
                source_diagnostic.message,
                component_id=source_diagnostic.source_id,
            )
        for index, binding in enumerate(evidence.recipe.inputs):
            try:
                descriptor = scheme_sources.resolve(binding.source_id)
            except SourceCatalogLookupError:
                continue
            if descriptor.declared_type != binding.declared_type:
                _diagnostic(
                    diagnostics,
                    "scheme.source_type_mismatch",
                    f"/evidence_versions/{_pointer(evidence_id)}/recipe/inputs/{index}",
                    "recipe binding type does not match its exact source descriptor",
                    component_id=binding.source_id,
                )
            if (
                descriptor.kind is SourceKind.TASK_SEMANTIC
                and binding.source_id not in task_required
            ):
                _diagnostic(
                    diagnostics,
                    "scheme.task_semantic_missing",
                    "/task_profile/required_source_descriptor_ids",
                    f"task profile does not declare required task semantic {binding.source_id!r}",
                    component_id=binding.source_id,
                )
        if evidence.scientific_status is not ModelScientificStatus.CALIBRATED:
            _diagnostic(
                diagnostics,
                "scheme.scientific_status_unvalidated",
                f"/evidence_versions/{_pointer(evidence_id)}/scientific_status",
                "scientific calibration remains expert work and does not block execution",
                component_id=evidence_id,
                severity=SchemeDiagnosticSeverity.WARNING,
            )

    variables: dict[tuple[ComponentKind, str], BnNodeVersion | EvidenceBindingVersion] = {}
    for record_id, node in bn_items.items():
        variables[(ComponentKind.BN_NODE_VERSION, record_id)] = node
        if node.scientific_status is not ModelScientificStatus.CALIBRATED:
            _diagnostic(
                diagnostics,
                "scheme.scientific_status_unvalidated",
                f"/bn_node_versions/{_pointer(record_id)}/scientific_status",
                "scientific calibration remains expert work and does not block execution",
                component_id=record_id,
                severity=SchemeDiagnosticSeverity.WARNING,
            )
    for record_id, binding in binding_items.items():
        variables[(ComponentKind.EVIDENCE_BINDING_VERSION, record_id)] = binding

    for cpt_id, cpt in cpt_items.items():
        cpt_outcome = validate_cpt(cpt, variables)
        for cpt_diagnostic in cpt_outcome.diagnostics:
            _diagnostic(
                diagnostics,
                cpt_diagnostic.code,
                f"/cpt_versions/{_pointer(cpt_id)}{cpt_diagnostic.location}",
                cpt_diagnostic.message,
                component_id=cpt_id,
                severity=(
                    SchemeDiagnosticSeverity.WARNING
                    if cpt_diagnostic.severity is CptDiagnosticSeverity.WARNING
                    else SchemeDiagnosticSeverity.ERROR
                ),
            )

    used_evidence_ids: set[str] = set()
    used_cpt_ids: set[str] = set()
    graph_edges: list[tuple[tuple[ComponentKind, str], tuple[ComponentKind, str]]] = []
    for child_key, variable in variables.items():
        parents = variable.ordered_probabilistic_parent_ids
        for parent in parents:
            parent_key = _key(parent)
            if parent_key not in variables:
                _diagnostic(
                    diagnostics,
                    "scheme.parent_missing",
                    f"/variables/{_pointer(child_key[1])}/ordered_probabilistic_parent_ids",
                    f"probabilistic parent {parent.kind.value}:{parent.version_id} is not pinned",
                    component_id=parent.version_id,
                )
            else:
                graph_edges.append((parent_key, child_key))
        cpt_id = variable.cpt_version_id.version_id
        cpt = cpt_items.get(cpt_id)
        if cpt is None:
            _diagnostic(
                diagnostics,
                "scheme.cpt_missing",
                f"/variables/{_pointer(child_key[1])}/cpt_version_id",
                f"CPT {cpt_id!r} is not pinned",
                component_id=cpt_id,
            )
        else:
            used_cpt_ids.add(cpt_id)
            if _key(cpt.child_variable_id) != child_key:
                _diagnostic(
                    diagnostics,
                    "scheme.cpt_child_mismatch",
                    f"/cpt_versions/{_pointer(cpt_id)}/child_variable_id",
                    "CPT child does not match the variable that references it",
                    component_id=cpt_id,
                )
            if tuple(_key(parent) for parent in cpt.ordered_parent_variable_ids) != tuple(
                _key(parent) for parent in parents
            ):
                _diagnostic(
                    diagnostics,
                    "scheme.cpt_parent_mismatch",
                    f"/cpt_versions/{_pointer(cpt_id)}/ordered_parent_variable_ids",
                    "CPT ordered parents do not match the child variable",
                    component_id=cpt_id,
                )
            state_ids = (
                tuple(state.state_id for state in variable.ordered_states)
                if isinstance(variable, BnNodeVersion)
                else tuple(state.state_id for state in variable.ordered_observation_states)
            )
            if cpt.child_state_ids != state_ids:
                _diagnostic(
                    diagnostics,
                    "scheme.cpt_state_mismatch",
                    f"/cpt_versions/{_pointer(cpt_id)}/child_state_ids",
                    "CPT child state order does not match the variable",
                    component_id=cpt_id,
                )
        if isinstance(variable, EvidenceBindingVersion):
            evidence_id = variable.evidence_version_id.version_id
            if evidence_id not in evidence_items:
                _diagnostic(
                    diagnostics,
                    "scheme.evidence_missing",
                    f"/evidence_binding_versions/{_pointer(child_key[1])}/evidence_version_id",
                    f"Evidence version {evidence_id!r} is not pinned",
                    component_id=evidence_id,
                )
            else:
                used_evidence_ids.add(evidence_id)
                allowed = {
                    modality.value for modality in evidence_modalities.get(evidence_id, set())
                }
                actual = set(variable.modality_attribution_weights)
                if not actual.issubset(allowed):
                    _diagnostic(
                        diagnostics,
                        "scheme.modality_attribution_outside_provenance",
                        (
                            f"/evidence_binding_versions/{_pointer(child_key[1])}"
                            "/modality_attribution_weights"
                        ),
                        (
                            "modality attribution must come from the Evidence "
                            "source-provenance closure"
                        ),
                        component_id=child_key[1],
                    )

    for evidence_id in evidence_items:
        if evidence_id not in used_evidence_ids:
            _diagnostic(
                diagnostics,
                "scheme.binding_missing",
                "/evidence_binding_versions",
                f"pinned Evidence {evidence_id!r} has no pinned observation binding",
                component_id=evidence_id,
            )

    if _has_cycle(set(variables), graph_edges):
        _diagnostic(
            diagnostics,
            "scheme.bayesian_cycle",
            "/bn_node_versions",
            "probabilistic dependency graph contains a cycle",
        )

    valid_outputs: set[tuple[ComponentKind, str]] = set()
    if not scheme.output_node_ids:
        _diagnostic(
            diagnostics,
            "scheme.output_missing",
            "/output_node_ids",
            "an executable scheme requires at least one output variable",
        )
    for index, output in enumerate(scheme.output_node_ids):
        output_key = _key(output)
        if output_key not in variables:
            _diagnostic(
                diagnostics,
                "scheme.output_missing",
                f"/output_node_ids/{index}",
                f"output variable {output.kind.value}:{output.version_id} is not pinned",
                component_id=output.version_id,
            )
        else:
            valid_outputs.add(output_key)

    reachable = _reachable_undirected(set(variables), graph_edges, valid_outputs)
    orphan_variables = sorted(
        set(variables) - reachable,
        key=lambda item: (item[0].value, item[1]),
    )
    for variable_key in orphan_variables:
        _diagnostic(
            diagnostics,
            "scheme.orphan_pin",
            "/bn_node_versions",
            "pinned BN variable is disconnected from every output",
            component_id=variable_key[1],
        )
    for cpt_id in sorted(set(cpt_items) - used_cpt_ids):
        _diagnostic(
            diagnostics,
            "scheme.orphan_pin",
            "/cpt_versions",
            "pinned CPT is not referenced by a pinned variable",
            component_id=cpt_id,
        )
    for source_id in sorted(set(source_items) - used_source_ids):
        _diagnostic(
            diagnostics,
            "scheme.orphan_pin",
            "/source_descriptors",
            "pinned source is not required by the task or any Evidence recipe",
            component_id=source_id,
        )

    ordered = _ordered(diagnostics)
    disposition = (
        SchemeValidationDisposition.INVALID
        if any(item.blocking for item in ordered)
        else SchemeValidationDisposition.EXECUTABLE
    )
    return SchemeValidationOutcome(disposition=disposition, diagnostics=ordered)


def validate_scheme_draft(
    draft: SchemeDraft,
    repository: ComponentLibraryRepository,
) -> SchemeValidationOutcome:
    """Validate persistable draft references without requiring a complete publication."""

    diagnostics: list[SchemeDiagnostic] = []
    retained_keys: set[tuple[ComponentKind, str]] = set()
    for index, reference in enumerate(draft.retained_component_refs):
        location = f"/retained_component_refs/{index}"
        retained_keys.add(_key(reference))
        try:
            item = repository.get_exact(reference.kind, reference.version_id)
        except LibraryItemNotFoundError:
            _diagnostic(
                diagnostics,
                "draft.reference_missing",
                location,
                "retained exact component does not exist",
                component_id=reference.version_id,
            )
            continue
        if hasattr(item, "content_hash") and reference.content_hash != component_content_hash(
            cast(VersionLibraryItem, item)
        ):
            _diagnostic(
                diagnostics,
                "draft.pin_hash_mismatch",
                f"{location}/content_hash",
                "retained component hash does not match",
                component_id=reference.version_id,
            )

    candidate_keys = {
        (candidate.kind, candidate.candidate_id) for candidate in draft.candidate_components
    }
    available = retained_keys | candidate_keys
    available_source_ids = {
        record_id for kind, record_id in available if kind is ComponentKind.SOURCE_DESCRIPTOR
    }
    available_evidence_ids = {
        record_id for kind, record_id in available if kind is ComponentKind.EVIDENCE_VERSION
    }
    for index, edge in enumerate(draft.extraction_edges):
        if edge.source_descriptor_id not in available_source_ids:
            _diagnostic(
                diagnostics,
                "draft.extraction_source_missing",
                f"/extraction_edges/{index}/source_descriptor_id",
                "extraction edge source is not retained or staged",
                component_id=edge.source_descriptor_id,
            )
        if edge.target_evidence_version_id not in available_evidence_ids:
            _diagnostic(
                diagnostics,
                "draft.extraction_target_missing",
                f"/extraction_edges/{index}/target_evidence_version_id",
                "extraction edge target is not retained or staged",
                component_id=edge.target_evidence_version_id,
            )
    for index, edge in enumerate(draft.bayesian_edges):
        for label, reference in (
            ("parent_variable_id", edge.parent_variable_id),
            ("child_variable_id", edge.child_variable_id),
        ):
            if _key(reference) not in available:
                _diagnostic(
                    diagnostics,
                    "draft.variable_missing",
                    f"/bayesian_edges/{index}/{label}",
                    "Bayesian edge endpoint is not retained or staged",
                    component_id=reference.version_id,
                )
    if not draft.output_node_ids:
        _diagnostic(
            diagnostics,
            "draft.output_missing",
            "/output_node_ids",
            "draft may be saved but needs at least one output before publication",
        )
    for index, output in enumerate(draft.output_node_ids):
        if _key(output) not in available:
            _diagnostic(
                diagnostics,
                "draft.output_missing",
                f"/output_node_ids/{index}",
                "draft output is not retained or staged",
                component_id=output.version_id,
            )
    ordered = _ordered(diagnostics)
    disposition = (
        SchemeValidationDisposition.DRAFT_INCOMPLETE
        if any(item.blocking for item in ordered)
        else SchemeValidationDisposition.EXECUTABLE
    )
    return SchemeValidationOutcome(disposition=disposition, diagnostics=ordered)


__all__ = [
    "SchemeDiagnostic",
    "SchemeDiagnosticSeverity",
    "SchemeValidationDisposition",
    "SchemeValidationOutcome",
    "validate_executable_scheme",
    "validate_scheme_draft",
]
