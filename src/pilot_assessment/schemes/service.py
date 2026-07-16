"""Use cases for scheme draft editing, copy-on-write publication, and exact replay."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from pydantic import BaseModel, JsonValue, ValidationError

from pilot_assessment.bayesian.inference import InferenceEngine
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    DraftComponentCandidate,
    DraftDiagnostic,
    DraftDiagnosticSeverity,
    DraftValidationState,
    LayoutVersion,
    SchemeDraft,
    TaskProfileVersion,
)
from pilot_assessment.contracts.bayesian import (
    BayesianDependencyEdge,
    ExtractionEdge,
    InferencePlan,
    InferenceTrace,
    Observation,
    ObservationSet,
    PosteriorResult,
)
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
    PinnedComponentRef,
    SourceDescriptor,
    VersionLineage,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    InMemoryComponentLibraryRepository,
    LibraryItem,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.service import Clock, IdFactory
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.schemes.operations import (
    OperationDiff,
    SchemeOperation,
    apply_scheme_operation,
)
from pilot_assessment.schemes.repository import (
    DraftRevisionConflictError,
    SchemeDraftRecord,
    SchemeDraftRepository,
    WorkspaceUnitOfWork,
)
from pilot_assessment.schemes.validation import (
    SchemeDiagnosticSeverity,
    SchemeValidationDisposition,
    SchemeValidationOutcome,
    validate_executable_scheme,
    validate_scheme_draft,
)

ZERO_HASH = "0" * 64


class SchemePublicationError(ValueError):
    """Raised when a persistable draft is not yet technically publishable."""

    def __init__(
        self,
        message: str,
        *,
        validation: SchemeValidationOutcome | None = None,
        diagnostics: tuple[DraftDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.validation = validation
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class SchemePublicationResult:
    scheme: AssessmentSchemeVersion
    scheme_ref: PinnedComponentRef
    new_component_refs: tuple[PinnedComponentRef, ...]
    retained_component_refs: tuple[PinnedComponentRef, ...]
    diff: OperationDiff
    rebased_draft: SchemeDraft


@dataclass(frozen=True, slots=True)
class SchemeReplaySnapshot:
    scheme: AssessmentSchemeVersion
    component_refs: tuple[PinnedComponentRef, ...]
    components: tuple[VersionLibraryItem, ...]


@dataclass(frozen=True, slots=True)
class SchemePreviewResult:
    draft_id: str
    graph_version: int
    layout_version: int
    draft_hash: str
    scheme: AssessmentSchemeVersion
    validation: SchemeValidationOutcome
    plan: InferencePlan
    observations: ObservationSet
    posterior: PosteriorResult
    trace: InferenceTrace


_VERSION_MODELS: dict[ComponentKind, type[BaseModel]] = {
    ComponentKind.EVIDENCE_VERSION: EvidenceVersion,
    ComponentKind.BN_NODE_VERSION: BnNodeVersion,
    ComponentKind.EVIDENCE_BINDING_VERSION: EvidenceBindingVersion,
    ComponentKind.CPT_VERSION: CptVersion,
    ComponentKind.TASK_PROFILE_VERSION: TaskProfileVersion,
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: CoverageReportingPolicyVersion,
    ComponentKind.LAYOUT_VERSION: LayoutVersion,
    ComponentKind.SOURCE_DESCRIPTOR: SourceDescriptor,
}

_VERSION_ID_FIELDS: dict[ComponentKind, str] = {
    ComponentKind.EVIDENCE_VERSION: "evidence_version_id",
    ComponentKind.BN_NODE_VERSION: "bn_node_version_id",
    ComponentKind.EVIDENCE_BINDING_VERSION: "evidence_binding_version_id",
    ComponentKind.CPT_VERSION: "cpt_version_id",
    ComponentKind.TASK_PROFILE_VERSION: "task_profile_version_id",
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: "policy_version_id",
    ComponentKind.LAYOUT_VERSION: "layout_version_id",
    ComponentKind.SOURCE_DESCRIPTOR: "source_id",
}

_LINEAGE_KINDS = frozenset(
    {
        ComponentKind.EVIDENCE_VERSION,
        ComponentKind.BN_NODE_VERSION,
        ComponentKind.EVIDENCE_BINDING_VERSION,
        ComponentKind.CPT_VERSION,
        ComponentKind.TASK_PROFILE_VERSION,
        ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
        ComponentKind.LAYOUT_VERSION,
    }
)


def _scheme_refs(scheme: AssessmentSchemeVersion) -> tuple[PinnedComponentRef, ...]:
    return (
        scheme.task_profile,
        *scheme.source_descriptors,
        *scheme.evidence_versions,
        *scheme.evidence_binding_versions,
        *scheme.bn_node_versions,
        *scheme.cpt_versions,
        scheme.reporting_policy,
        scheme.layout,
    )


def _edge_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]
    return f"{prefix}.{digest}"


def _draft_diagnostic(
    code: str,
    location: str,
    message: str,
    component_id: str | None,
    *,
    warning: bool = False,
) -> DraftDiagnostic:
    return DraftDiagnostic(
        code=code,
        severity=(DraftDiagnosticSeverity.WARNING if warning else DraftDiagnosticSeverity.ERROR),
        location=location,
        component_id=component_id,
        message=message[:256] or "Technical draft diagnostic.",
    )


def _candidate_diagnostics(
    candidates: tuple[DraftComponentCandidate, ...],
) -> tuple[DraftDiagnostic, ...]:
    diagnostics: list[DraftDiagnostic] = []
    for index, candidate in enumerate(candidates):
        model = _VERSION_MODELS.get(candidate.kind)
        if model is None:
            diagnostics.append(
                _draft_diagnostic(
                    "draft.candidate_kind_unsupported",
                    f"/candidate_components/{index}/kind",
                    f"{candidate.kind.value} cannot be published as a component candidate",
                    candidate.candidate_id,
                )
            )
            continue
        try:
            model.model_validate(candidate.payload)
        except ValidationError as error:
            diagnostics.append(
                _draft_diagnostic(
                    "draft.candidate_incomplete",
                    f"/candidate_components/{index}/payload",
                    str(error.errors()[0].get("msg", "candidate payload is incomplete")),
                    candidate.candidate_id,
                )
            )
    return tuple(diagnostics)


def _draft_closure_diagnostics(
    draft: SchemeDraft,
    repository: ComponentLibraryRepository,
) -> tuple[DraftDiagnostic, ...]:
    available = {
        (reference.kind, reference.version_id) for reference in draft.retained_component_refs
    }
    available.update(
        (candidate.kind, candidate.candidate_id) for candidate in draft.candidate_components
    )
    items: list[VersionLibraryItem] = []
    for reference in draft.retained_component_refs:
        try:
            item = repository.get_exact(reference.kind, reference.version_id)
        except KeyError:
            continue
        if hasattr(item, "content_hash"):
            items.append(cast(VersionLibraryItem, item))
    for candidate in draft.candidate_components:
        model = _VERSION_MODELS.get(candidate.kind)
        if model is None:
            continue
        try:
            items.append(cast(VersionLibraryItem, model.model_validate(candidate.payload)))
        except ValidationError:
            continue

    diagnostics: list[DraftDiagnostic] = []
    seen: set[tuple[ComponentKind, str, str]] = set()

    def require(
        kind: ComponentKind,
        version_id: str,
        *,
        owner_id: str,
        relationship: str,
    ) -> None:
        key = (kind, version_id, owner_id)
        if (kind, version_id) in available or key in seen:
            return
        seen.add(key)
        diagnostics.append(
            _draft_diagnostic(
                "draft.reference_closure_incomplete",
                f"/component_closure/{owner_id}/{relationship}",
                f"{owner_id!r} still requires unselected {kind.value}:{version_id}",
                owner_id,
            )
        )

    for item in items:
        owner_id = component_record_id(item)
        if isinstance(item, EvidenceVersion):
            for binding in item.recipe.inputs:
                require(
                    ComponentKind.SOURCE_DESCRIPTOR,
                    binding.source_id,
                    owner_id=owner_id,
                    relationship="source",
                )
        elif isinstance(item, EvidenceBindingVersion):
            require(
                ComponentKind.EVIDENCE_VERSION,
                item.evidence_version_id.version_id,
                owner_id=owner_id,
                relationship="evidence",
            )
            require(
                ComponentKind.CPT_VERSION,
                item.cpt_version_id.version_id,
                owner_id=owner_id,
                relationship="cpt",
            )
            for parent in item.ordered_probabilistic_parent_ids:
                require(
                    parent.kind,
                    parent.version_id,
                    owner_id=owner_id,
                    relationship="parent",
                )
        elif isinstance(item, BnNodeVersion):
            require(
                ComponentKind.CPT_VERSION,
                item.cpt_version_id.version_id,
                owner_id=owner_id,
                relationship="cpt",
            )
            for parent in item.ordered_probabilistic_parent_ids:
                require(
                    parent.kind,
                    parent.version_id,
                    owner_id=owner_id,
                    relationship="parent",
                )
        elif isinstance(item, CptVersion):
            require(
                item.child_variable_id.kind,
                item.child_variable_id.version_id,
                owner_id=owner_id,
                relationship="child",
            )
            for parent in item.ordered_parent_variable_ids:
                require(
                    parent.kind,
                    parent.version_id,
                    owner_id=owner_id,
                    relationship="parent",
                )
        elif isinstance(item, TaskProfileVersion):
            for source_id in item.required_source_descriptor_ids:
                require(
                    ComponentKind.SOURCE_DESCRIPTOR,
                    source_id,
                    owner_id=owner_id,
                    relationship="required_source",
                )
    return tuple(diagnostics)


def _annotate_draft(
    draft: SchemeDraft,
    repository: ComponentLibraryRepository,
) -> SchemeDraft:
    outcome = validate_scheme_draft(draft, repository)
    diagnostics = [
        _draft_diagnostic(
            item.code,
            item.location,
            item.message,
            item.component_id,
            warning=item.severity is SchemeDiagnosticSeverity.WARNING,
        )
        for item in outcome.diagnostics
    ]
    diagnostics.extend(_candidate_diagnostics(draft.candidate_components))
    diagnostics.extend(_draft_closure_diagnostics(draft, repository))
    state = (
        DraftValidationState.INCOMPLETE
        if any(item.severity is DraftDiagnosticSeverity.ERROR for item in diagnostics)
        else DraftValidationState.EXECUTABLE
    )
    return draft.model_copy(update={"validation_state": state, "diagnostics": tuple(diagnostics)})


def _require_scheme(item: LibraryItem) -> AssessmentSchemeVersion:
    if not isinstance(item, AssessmentSchemeVersion):
        raise SchemePublicationError("selected exact ID is not an assessment scheme")
    return item


def _require_version(item: LibraryItem) -> VersionLibraryItem:
    if not hasattr(item, "content_hash"):
        raise SchemePublicationError("scheme replay encountered a non-version component")
    return cast(VersionLibraryItem, item)


def _project_edges(
    scheme: AssessmentSchemeVersion,
    repository: ComponentLibraryRepository,
) -> tuple[tuple[ExtractionEdge, ...], tuple[BayesianDependencyEdge, ...]]:
    extraction: list[ExtractionEdge] = []
    for reference in scheme.evidence_versions:
        item = repository.get_exact(reference.kind, reference.version_id)
        if not isinstance(item, EvidenceVersion):
            continue
        for binding in item.recipe.inputs:
            extraction.append(
                ExtractionEdge(
                    edge_id=_edge_id(
                        "extraction",
                        item.evidence_version_id,
                        binding.binding_id,
                        binding.source_id,
                    ),
                    source_descriptor_id=binding.source_id,
                    target_evidence_version_id=item.evidence_version_id,
                    input_binding_id=binding.binding_id,
                )
            )
    bayesian: list[BayesianDependencyEdge] = []
    for reference in (*scheme.bn_node_versions, *scheme.evidence_binding_versions):
        item = repository.get_exact(reference.kind, reference.version_id)
        if not isinstance(item, (BnNodeVersion, EvidenceBindingVersion)):
            continue
        child = ComponentIdRef(kind=reference.kind, version_id=reference.version_id)
        for parent in item.ordered_probabilistic_parent_ids:
            bayesian.append(
                BayesianDependencyEdge(
                    edge_id=_edge_id(
                        "bayesian",
                        parent.kind.value,
                        parent.version_id,
                        child.kind.value,
                        child.version_id,
                    ),
                    parent_variable_id=parent,
                    child_variable_id=child,
                )
            )
    return tuple(extraction), tuple(bayesian)


def _replace_json_strings(value: JsonValue, replacements: Mapping[str, str]) -> JsonValue:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, dict):
        return {key: _replace_json_strings(nested, replacements) for key, nested in value.items()}
    if isinstance(value, list):
        return [_replace_json_strings(nested, replacements) for nested in value]
    return value


def _pin(item: VersionLibraryItem) -> PinnedComponentRef:
    return PinnedComponentRef(
        kind=component_kind(item),
        version_id=component_record_id(item),
        content_hash=item.content_hash,
    )


class SchemeWorkspaceService:
    """Backend canonical-state service intended for M6 transport and M7 forms."""

    def __init__(
        self,
        components: ComponentLibraryRepository,
        drafts: SchemeDraftRepository,
        unit_of_work: WorkspaceUnitOfWork,
        *,
        source_catalog: SourceCatalog,
        operator_registry: OperatorRegistry,
        clock: Clock,
        ids: IdFactory,
    ) -> None:
        self._components = components
        self._drafts = drafts
        self._uow = unit_of_work
        self._source_catalog = source_catalog
        self._operator_registry = operator_registry
        self._clock = clock
        self._ids = ids

    def create_draft_from_scheme(
        self,
        scheme_version_id: str,
        *,
        draft_id: str,
        author_id: str,
    ) -> SchemeDraftRecord:
        scheme = _require_scheme(
            self._components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                scheme_version_id,
            )
        )
        extraction, bayesian = _project_edges(scheme, self._components)
        provisional = SchemeDraft(
            draft_id=draft_id,
            base_scheme_version_id=scheme.scheme_version_id,
            graph_version=0,
            layout_version=0,
            history_cursor=0,
            retained_component_refs=_scheme_refs(scheme),
            candidate_components=(),
            extraction_edges=extraction,
            bayesian_edges=bayesian,
            output_node_ids=scheme.output_node_ids,
            validation_state=DraftValidationState.INCOMPLETE,
            diagnostics=(),
        )
        return self._drafts.create(
            _annotate_draft(provisional, self._components),
            author_id=author_id,
        )

    def apply_operation(
        self,
        draft_id: str,
        operation: SchemeOperation,
        *,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self.apply_operations(draft_id, (operation,), author_id=author_id)

    def apply_operations(
        self,
        draft_id: str,
        operations: Sequence[SchemeOperation],
        *,
        author_id: str,
    ) -> SchemeDraftRecord:
        if not operations:
            raise SchemePublicationError("operation batch must not be empty")
        current = self._drafts.get(draft_id).draft
        proposed = current
        applications = []
        for operation in operations:
            application = apply_scheme_operation(proposed, operation, self._components)
            applications.append(application)
            proposed = application.draft
        graph_changed = any(application.graph_changed for application in applications)
        layout_changed = any(application.layout_changed for application in applications)
        expected_graph_versions = {
            application.expected_graph_version
            for application in applications
            if application.graph_changed
        }
        expected_layout_versions = {
            application.expected_layout_version
            for application in applications
            if application.layout_changed
        }
        if graph_changed and expected_graph_versions != {current.graph_version}:
            raise DraftRevisionConflictError(
                "all graph operations in a batch must target the current graph version"
            )
        if layout_changed and expected_layout_versions != {current.layout_version}:
            raise DraftRevisionConflictError(
                "all layout operations in a batch must target the current layout version"
            )
        annotated = _annotate_draft(proposed, self._components)
        changed_paths = tuple(
            dict.fromkeys(
                path for application in applications for path in application.diff.changed_paths
            )
        )
        diff = OperationDiff(
            operation_type=(
                applications[0].diff.operation_type
                if len(applications) == 1
                else "AtomicOperationBatch"
            ),
            changed_paths=changed_paths,
            added_component_ids=tuple(
                item
                for application in applications
                for item in application.diff.added_component_ids
            ),
            removed_component_ids=tuple(
                item
                for application in applications
                for item in application.diff.removed_component_ids
            ),
        )
        return self._drafts.save(
            annotated,
            expected_graph_version=current.graph_version if graph_changed else None,
            expected_layout_version=current.layout_version if layout_changed else None,
            graph_changed=graph_changed,
            layout_changed=layout_changed,
            diff=diff,
            author_id=author_id,
        )

    def discard_draft(self, draft_id: str) -> SchemeDraftRecord:
        return self._drafts.discard(draft_id)

    def undo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._drafts.undo(
            draft_id,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def redo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._drafts.redo(
            draft_id,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def _materialize_candidates(
        self,
        draft: SchemeDraft,
        *,
        author_id: str,
        note: str | None,
        created_at: datetime,
    ) -> tuple[tuple[VersionLibraryItem, ...], dict[str, str]]:
        id_map = {
            candidate.candidate_id: self._ids.new_id(candidate.kind)
            for candidate in draft.candidate_components
        }
        materialized: list[VersionLibraryItem] = []
        for candidate in draft.candidate_components:
            model = _VERSION_MODELS.get(candidate.kind)
            id_field = _VERSION_ID_FIELDS.get(candidate.kind)
            if model is None or id_field is None:
                raise SchemePublicationError(
                    f"candidate kind {candidate.kind.value} cannot be published"
                )
            raw = cast(JsonValue, candidate.payload)
            rewritten = _replace_json_strings(raw, id_map)
            if not isinstance(rewritten, dict):
                raise SchemePublicationError("candidate payload must be a JSON object")
            payload = dict(rewritten)
            payload[id_field] = id_map[candidate.candidate_id]
            payload["content_hash"] = ZERO_HASH
            if candidate.kind in _LINEAGE_KINDS:
                payload["lineage"] = VersionLineage(
                    source_version_ids=(candidate.base_version_id,)
                    if candidate.base_version_id is not None
                    else (),
                    created_at=created_at,
                    created_by=author_id,
                    note=note,
                ).model_dump(mode="json")
            try:
                provisional = cast(VersionLibraryItem, model.model_validate(payload))
                item = cast(
                    VersionLibraryItem,
                    model.model_validate(
                        {
                            **provisional.model_dump(mode="json"),
                            "content_hash": component_content_hash(provisional),
                        }
                    ),
                )
            except ValidationError as error:
                raise SchemePublicationError(
                    f"candidate {candidate.candidate_id!r} is incomplete or invalid"
                ) from error
            materialized.append(item)
        return tuple(materialized), id_map

    def _materialize_preview_candidates(
        self,
        draft: SchemeDraft,
    ) -> tuple[VersionLibraryItem, ...]:
        """Materialize candidate IDs as-is without consuming publish IDs or writing state."""

        materialized: list[VersionLibraryItem] = []
        for candidate in draft.candidate_components:
            model = _VERSION_MODELS.get(candidate.kind)
            if model is None:
                raise SchemePublicationError(
                    f"candidate kind {candidate.kind.value} cannot be previewed"
                )
            payload = dict(candidate.payload)
            payload["content_hash"] = ZERO_HASH
            try:
                provisional = cast(VersionLibraryItem, model.model_validate(payload))
                item = cast(
                    VersionLibraryItem,
                    model.model_validate(
                        {
                            **provisional.model_dump(mode="json"),
                            "content_hash": component_content_hash(provisional),
                        }
                    ),
                )
            except ValidationError as error:
                raise SchemePublicationError(
                    f"candidate {candidate.candidate_id!r} is incomplete or invalid"
                ) from error
            materialized.append(item)
        return tuple(materialized)

    @staticmethod
    def _one(
        refs: Mapping[ComponentKind, list[PinnedComponentRef]],
        kind: ComponentKind,
        label: str,
    ) -> PinnedComponentRef:
        selected = refs.get(kind, [])
        if len(selected) != 1:
            raise SchemePublicationError(f"scheme requires exactly one {label}")
        return selected[0]

    def _prepare_scheme(
        self,
        draft: SchemeDraft,
        base: AssessmentSchemeVersion,
        candidates: tuple[VersionLibraryItem, ...],
        id_map: Mapping[str, str],
        *,
        scheme_version_id: str,
        author_id: str,
        note: str | None,
        created_at: datetime,
    ) -> AssessmentSchemeVersion:
        by_kind: dict[ComponentKind, list[PinnedComponentRef]] = {}
        for reference in draft.retained_component_refs:
            by_kind.setdefault(reference.kind, []).append(reference)
        for item in candidates:
            by_kind.setdefault(component_kind(item), []).append(_pin(item))
        outputs = tuple(
            output.model_copy(
                update={"version_id": id_map.get(output.version_id, output.version_id)}
            )
            for output in draft.output_node_ids
        )
        provisional = AssessmentSchemeVersion(
            scheme_version_id=scheme_version_id,
            scheme_concept_id=base.scheme_concept_id,
            name=base.name,
            description=base.description,
            task_profile=self._one(
                by_kind,
                ComponentKind.TASK_PROFILE_VERSION,
                "task profile",
            ),
            source_descriptors=tuple(by_kind.get(ComponentKind.SOURCE_DESCRIPTOR, ())),
            evidence_versions=tuple(by_kind.get(ComponentKind.EVIDENCE_VERSION, ())),
            evidence_binding_versions=tuple(
                by_kind.get(ComponentKind.EVIDENCE_BINDING_VERSION, ())
            ),
            bn_node_versions=tuple(by_kind.get(ComponentKind.BN_NODE_VERSION, ())),
            cpt_versions=tuple(by_kind.get(ComponentKind.CPT_VERSION, ())),
            reporting_policy=self._one(
                by_kind,
                ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
                "reporting policy",
            ),
            layout=self._one(by_kind, ComponentKind.LAYOUT_VERSION, "layout"),
            output_node_ids=outputs,
            lineage=VersionLineage(
                source_version_ids=(base.scheme_version_id,),
                created_at=created_at,
                created_by=author_id,
                note=note,
            ),
            content_hash=ZERO_HASH,
        )
        return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})

    def _staging_repository(
        self,
        candidates: tuple[VersionLibraryItem, ...],
        *,
        recorded_at: datetime,
    ) -> InMemoryComponentLibraryRepository:
        if isinstance(self._components, InMemoryComponentLibraryRepository):
            staging = self._components.clone()
        else:
            staging = InMemoryComponentLibraryRepository()
            for record in self._components.list_records():
                staging.add(record.item, recorded_at=record.metadata.created_at)
        for candidate in candidates:
            staging.add(candidate, recorded_at=recorded_at)
        return staging

    def _draft_from_published(
        self,
        current: SchemeDraft,
        scheme: AssessmentSchemeVersion,
        staging: ComponentLibraryRepository,
    ) -> SchemeDraft:
        extraction, bayesian = _project_edges(scheme, staging)
        provisional = SchemeDraft(
            draft_id=current.draft_id,
            base_scheme_version_id=scheme.scheme_version_id,
            graph_version=current.graph_version,
            layout_version=current.layout_version,
            history_cursor=0,
            retained_component_refs=_scheme_refs(scheme),
            candidate_components=(),
            extraction_edges=extraction,
            bayesian_edges=bayesian,
            output_node_ids=scheme.output_node_ids,
            validation_state=DraftValidationState.INCOMPLETE,
            diagnostics=(),
        )
        return _annotate_draft(provisional, staging)

    def publish(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
        note: str | None = None,
    ) -> SchemePublicationResult:
        current = self._drafts.get(draft_id).draft
        if (
            current.graph_version != expected_graph_version
            or current.layout_version != expected_layout_version
        ):
            raise SchemePublicationError("draft revision changed before publication")
        if current.validation_state is not DraftValidationState.EXECUTABLE:
            raise SchemePublicationError(
                "draft is persistable but not technically publishable",
                diagnostics=current.diagnostics,
            )
        if current.base_scheme_version_id is None:
            raise SchemePublicationError("new scheme publication requires a base in M5 v0")
        base = _require_scheme(
            self._components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                current.base_scheme_version_id,
            )
        )
        created_at = self._clock.now()
        candidates, id_map = self._materialize_candidates(
            current,
            author_id=author_id,
            note=note,
            created_at=created_at,
        )
        scheme_id = self._ids.new_id(ComponentKind.ASSESSMENT_SCHEME_VERSION)
        scheme = self._prepare_scheme(
            current,
            base,
            candidates,
            id_map,
            scheme_version_id=scheme_id,
            author_id=author_id,
            note=note,
            created_at=created_at,
        )
        staging = self._staging_repository(candidates, recorded_at=created_at)
        source_descriptors = list(self._source_catalog.descriptors())
        source_descriptors.extend(item for item in candidates if isinstance(item, SourceDescriptor))
        validation = validate_executable_scheme(
            scheme,
            staging,
            SourceCatalog(source_descriptors),
            self._operator_registry,
        )
        if validation.disposition is not SchemeValidationDisposition.EXECUTABLE:
            raise SchemePublicationError(
                "draft failed exact scheme publication validation",
                validation=validation,
            )
        staging.add(scheme, recorded_at=created_at)
        rebased = self._draft_from_published(current, scheme, staging)
        self._uow.publish_atomic(
            (*candidates, scheme),
            recorded_at=created_at,
            draft_id=draft_id,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            rebased_draft=rebased,
            author_id=author_id,
        )
        new_refs = tuple(_pin(item) for item in candidates)
        scheme_ref = _pin(scheme)
        return SchemePublicationResult(
            scheme=scheme,
            scheme_ref=scheme_ref,
            new_component_refs=new_refs,
            retained_component_refs=current.retained_component_refs,
            diff=OperationDiff(
                operation_type="PublishScheme",
                changed_paths=("/candidate_components", "/base_scheme_version_id"),
                added_component_ids=tuple(
                    reference.version_id for reference in (*new_refs, scheme_ref)
                ),
            ),
            rebased_draft=rebased,
        )

    def preview(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        observations: Sequence[Observation],
        query_node_ids: Sequence[ComponentIdRef] | None = None,
    ) -> SchemePreviewResult:
        """Compile and infer one exact draft snapshot without publishing or mutating state."""

        current = self._drafts.get(draft_id).draft
        if (
            current.graph_version != expected_graph_version
            or current.layout_version != expected_layout_version
        ):
            raise SchemePublicationError("draft revision changed before preview")
        if current.validation_state is not DraftValidationState.EXECUTABLE:
            raise SchemePublicationError(
                "draft is persistable but not technically previewable",
                diagnostics=current.diagnostics,
            )
        if current.base_scheme_version_id is None:
            raise SchemePublicationError("draft preview requires a base scheme in M5 v0")
        base = _require_scheme(
            self._components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                current.base_scheme_version_id,
            )
        )
        draft_hash = typed_content_sha256(
            current.contract_id,
            current.contract_version,
            current.model_dump(mode="json"),
        )
        candidates = self._materialize_preview_candidates(current)
        preview_scheme = self._prepare_scheme(
            current,
            base,
            candidates,
            {},
            scheme_version_id=f"preview-scheme.{draft_hash[:24]}",
            author_id="preview.engine",
            note="Read-only draft preview.",
            created_at=base.lineage.created_at,
        )
        staging = self._staging_repository(
            candidates,
            recorded_at=base.lineage.created_at,
        )
        source_descriptors = list(self._source_catalog.descriptors())
        source_descriptors.extend(item for item in candidates if isinstance(item, SourceDescriptor))
        validation = validate_executable_scheme(
            preview_scheme,
            staging,
            SourceCatalog(source_descriptors),
            self._operator_registry,
        )
        if validation.disposition is not SchemeValidationDisposition.EXECUTABLE:
            raise SchemePublicationError(
                "draft failed exact preview validation",
                validation=validation,
            )
        staging.add(preview_scheme, recorded_at=base.lineage.created_at)
        engine = InferenceEngine(staging)
        plan = engine.compile(preview_scheme)
        observation_set = engine.observe(plan, observations)
        queries = tuple(current.output_node_ids if query_node_ids is None else query_node_ids)
        posterior = engine.infer(plan, observation_set, queries)
        trace = engine.explain(plan, observation_set, queries)
        return SchemePreviewResult(
            draft_id=current.draft_id,
            graph_version=current.graph_version,
            layout_version=current.layout_version,
            draft_hash=draft_hash,
            scheme=preview_scheme,
            validation=validation,
            plan=plan,
            observations=observation_set,
            posterior=posterior,
            trace=trace,
        )

    def replay_exact(self, scheme_version_id: str) -> SchemeReplaySnapshot:
        scheme = _require_scheme(
            self._components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                scheme_version_id,
            )
        )
        refs = _scheme_refs(scheme)
        components: list[VersionLibraryItem] = []
        for reference in refs:
            item = _require_version(
                self._components.get_exact(reference.kind, reference.version_id)
            )
            if item.content_hash != reference.content_hash:
                raise SchemePublicationError(
                    f"replay pin mismatch for {reference.kind.value}:{reference.version_id}"
                )
            components.append(item)
        return SchemeReplaySnapshot(
            scheme=scheme,
            component_refs=refs,
            components=tuple(components),
        )


__all__ = [
    "SchemePublicationError",
    "SchemePublicationResult",
    "SchemePreviewResult",
    "SchemeReplaySnapshot",
    "SchemeWorkspaceService",
]
