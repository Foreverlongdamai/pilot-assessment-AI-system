"""One-time materialization of immutable starter records into M7 current objects."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict, cast

from pydantic import JsonValue

from pilot_assessment.contracts.assessment_scheme import (
    CoverageReportingPolicyVersion,
    LayoutVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    RawModality,
    SourceDescriptor,
    SourceKind,
)
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    CanonicalModelDiff,
    EvidenceDataBinding,
    EvidenceNodeDefinition,
    ModelDiagnostic,
    ModelDiagnosticSeverity,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    ModelObjectKind,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeCpt,
    NodeLayout,
    RawInputFamily,
    RawInputNodeDefinition,
    RawResourceRole,
    TaskScheme,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.profile import LoadedModelProfile
from pilot_assessment.model_library.repository import (
    LibraryItem,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_workspace.graph import (
    ModelGraphError,
    activation_closure,
    project_model_edges,
)
from pilot_assessment.model_workspace.hashing import rehash_model_node, rehash_task_scheme
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.model_workspace.validation import validate_model_graph

CURRENT_STARTER_MIGRATION_VERSION = "0.1.0"
CURRENT_HOVER_STARTER_SEED_ID = "starter.hover.current-model.0.1.0"
_ZERO_HASH = "0" * 64
_SYSTEM_ACTOR = "system.m7-starter-migration"

LegacyKey = tuple[ComponentKind, str]
CurrentTarget = tuple[ModelObjectKind, str]


class CurrentStarterMigrationError(RuntimeError):
    """Raised when a frozen legacy package cannot map coherently to current objects."""


@dataclass(frozen=True, slots=True)
class CurrentStarterSeedResult:
    seed_id: str
    seed_hash: str
    scheme_id: str
    applied: bool
    inserted_nodes: int
    inserted_schemes: int
    total_nodes: int
    total_schemes: int
    mapping_count: int


@dataclass(frozen=True, slots=True)
class _StarterMapping:
    mapping_id: str
    legacy_kind: ComponentKind
    legacy_record_id: str
    current_object_kind: ModelObjectKind
    current_object_id: str
    seed_id: str
    seed_hash: str


@dataclass(frozen=True, slots=True)
class _MaterializedStarter:
    seed_id: str
    seed_hash: str
    nodes: tuple[ModelNode, ...]
    scheme: TaskScheme
    mappings: tuple[_StarterMapping, ...]


class _NodeFields(TypedDict):
    node_id: str
    node_kind: ModelNodeKind
    name: str
    short_name: str
    description: str
    tags: tuple[str, ...]
    group: str | None
    lifecycle: ModelObjectLifecycle
    copied_from_node_id: None
    global_layout: NodeLayout
    semantic_revision: int
    layout_revision: int
    technical_status: ModelTechnicalStatus
    diagnostics: tuple[ModelDiagnostic, ...]
    content_hash: str
    layout_hash: str
    created_at: datetime
    updated_at: datetime


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentStarterMigrationError("starter migration timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _key(item: LibraryItem) -> LegacyKey:
    return component_kind(item), component_record_id(item)


def _legacy_projection(items: Iterable[LibraryItem]) -> list[dict[str, JsonValue]]:
    return [
        {
            "kind": component_kind(item).value,
            "record_id": component_record_id(item),
            "record": cast(JsonValue, item.model_dump(mode="json")),
        }
        for item in sorted(
            items, key=lambda value: (component_kind(value), component_record_id(value))
        )
    ]


def _current_id(prefix: str, items: Iterable[LibraryItem]) -> str:
    digest = typed_content_sha256(
        "m7-current-starter-object",
        CURRENT_STARTER_MIGRATION_VERSION,
        {"legacy_records": _legacy_projection(items)},
    )
    return f"{prefix}.{digest[:32]}"


def _mapping_id(
    legacy_key: LegacyKey,
    target: CurrentTarget,
    *,
    seed_id: str,
) -> str:
    digest = typed_content_sha256(
        "m7-current-starter-mapping",
        CURRENT_STARTER_MIGRATION_VERSION,
        {
            "legacy_kind": legacy_key[0].value,
            "legacy_record_id": legacy_key[1],
            "current_object_kind": target[0].value,
            "current_object_id": target[1],
            "seed_id": seed_id,
        },
    )
    return f"model-starter-mapping.{digest[:32]}"


def _event_id(seed_hash: str, object_kind: ModelObjectKind, object_id: str) -> str:
    digest = typed_content_sha256(
        "m7-current-starter-event",
        CURRENT_STARTER_MIGRATION_VERSION,
        {
            "seed_hash": seed_hash,
            "object_kind": object_kind.value,
            "object_id": object_id,
        },
    )
    return f"model-event.migrate.{digest[:32]}"


def _require(
    index: dict[LegacyKey, LibraryItem],
    kind: ComponentKind,
    record_id: str,
    expected_type: type[LibraryItem],
) -> LibraryItem:
    item = index.get((kind, record_id))
    if item is None or not isinstance(item, expected_type):
        raise CurrentStarterMigrationError(
            f"starter dependency {kind.value}:{record_id} is missing or has the wrong type"
        )
    return item


def _raw_family(descriptor: SourceDescriptor) -> RawInputFamily | None:
    if descriptor.kind is not SourceKind.RAW_STREAM:
        return None
    if descriptor.raw_modality is None:
        raise CurrentStarterMigrationError("raw starter source has no physical modality")
    return {
        RawModality.X: RawInputFamily.X,
        RawModality.U: RawInputFamily.U,
        RawModality.I: RawInputFamily.I,
        RawModality.G: RawInputFamily.G,
        RawModality.EEG: RawInputFamily.P,
        RawModality.ECG: RawInputFamily.P,
        RawModality.PILOT_CAMERA: RawInputFamily.PILOT_CAMERA,
    }[descriptor.raw_modality]


def _resource_role(descriptor: SourceDescriptor) -> RawResourceRole:
    declared = descriptor.metadata.get("resource_role")
    if isinstance(declared, str):
        try:
            return RawResourceRole(declared)
        except ValueError as error:
            raise CurrentStarterMigrationError(
                f"source {descriptor.source_id!r} declares an unknown resource role"
            ) from error
    if descriptor.kind is SourceKind.RAW_STREAM:
        return RawResourceRole.STREAM
    if descriptor.kind is SourceKind.DERIVED_ARTIFACT:
        return RawResourceRole.DERIVED_RESOURCE
    if descriptor.kind is SourceKind.TASK_SEMANTIC:
        value_type = descriptor.declared_type.value_type
        if value_type == "event_collection":
            return RawResourceRole.EVENT
        if value_type in {"aoi_collection", "aoi_definition"}:
            return RawResourceRole.AOI_DEFINITION
        return RawResourceRole.TASK_REFERENCE
    if descriptor.kind is SourceKind.SESSION_SEMANTIC:
        return RawResourceRole.DERIVED_RESOURCE
    return RawResourceRole.DERIVED_RESOURCE


def _short_label(name: str, fallback: str) -> str:
    return name if len(name) <= 96 else fallback[-96:]


def _legacy_refs(items: Iterable[LibraryItem]) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for item in sorted(
        items, key=lambda value: (component_kind(value), component_record_id(value))
    ):
        record: dict[str, JsonValue] = {
            "kind": component_kind(item).value,
            "record_id": component_record_id(item),
        }
        content_hash = getattr(item, "content_hash", None)
        if isinstance(content_hash, str):
            record["content_hash"] = content_hash
        result.append(record)
    return result


def _node_fields(
    *,
    node_id: str,
    node_kind: ModelNodeKind,
    name: str,
    short_name: str,
    description: str,
    tags: Iterable[str],
    group: str | None,
    layout: NodeLayout,
    recorded_at: datetime,
) -> _NodeFields:
    return {
        "node_id": node_id,
        "node_kind": node_kind,
        "name": name,
        "short_name": _short_label(short_name, node_id),
        "description": description,
        "tags": tuple(sorted(set(tags))),
        "group": group,
        "lifecycle": ModelObjectLifecycle.ACTIVE,
        "copied_from_node_id": None,
        "global_layout": layout,
        "semantic_revision": 0,
        "layout_revision": 0,
        "technical_status": ModelTechnicalStatus.EXECUTABLE,
        "diagnostics": (),
        "content_hash": _ZERO_HASH,
        "layout_hash": _ZERO_HASH,
        "created_at": recorded_at,
        "updated_at": recorded_at,
    }


def _node_ref_for_component(
    reference: ComponentIdRef,
    *,
    bn_node_ids: dict[str, str],
    evidence_node_ids: dict[str, str],
) -> ModelNodeRef:
    if reference.kind is ComponentKind.BN_NODE_VERSION:
        try:
            return ModelNodeRef(
                node_id=bn_node_ids[reference.version_id],
                node_kind=ModelNodeKind.BN,
            )
        except KeyError as error:
            raise CurrentStarterMigrationError(
                f"BN parent {reference.version_id!r} is outside the starter migration set"
            ) from error
    if reference.kind is ComponentKind.EVIDENCE_BINDING_VERSION:
        try:
            return ModelNodeRef(
                node_id=evidence_node_ids[reference.version_id],
                node_kind=ModelNodeKind.EVIDENCE,
            )
        except KeyError as error:
            raise CurrentStarterMigrationError(
                f"Evidence variable {reference.version_id!r} is outside the migration set"
            ) from error
    raise CurrentStarterMigrationError(
        f"legacy variable reference kind {reference.kind.value!r} cannot become a current node"
    )


def _node_cpt(
    legacy: CptVersion,
    *,
    node_id: str,
    node_kind: ModelNodeKind,
    bn_node_ids: dict[str, str],
    evidence_node_ids: dict[str, str],
) -> NodeCpt:
    parents = tuple(
        _node_ref_for_component(
            parent,
            bn_node_ids=bn_node_ids,
            evidence_node_ids=evidence_node_ids,
        )
        for parent in legacy.ordered_parent_variable_ids
    )
    cpt_id = _current_id("node-cpt", (legacy,))
    return NodeCpt(
        cpt_id=cpt_id,
        child_node=ModelNodeRef(node_id=node_id, node_kind=node_kind),
        ordered_parent_nodes=parents,
        child_state_ids=legacy.child_state_ids,
        ordered_parent_state_ids=legacy.ordered_parent_state_ids,
        materialized_probabilities=legacy.materialized_probabilities,
        mode=legacy.mode,
        generator_metadata=dict(legacy.generator_metadata),
        source=legacy.source,
    )


def _graph_diagnostic(error: ModelGraphError, node_id: str) -> ModelDiagnostic:
    return ModelDiagnostic(
        code=error.code,
        severity=ModelDiagnosticSeverity.ERROR,
        location=error.location or f"/nodes/{node_id}",
        message=str(error),
        details={},
    )


def _normalize_nodes(
    nodes: tuple[ModelNode, ...],
    service: CurrentModelWorkspaceService,
) -> tuple[ModelNode, ...]:
    hashed = tuple(rehash_model_node(node) for node in nodes)
    normalized: list[ModelNode] = []
    for node in hashed:
        try:
            closure = activation_closure(hashed, (node.node_id,))
        except ModelGraphError as error:
            status = ModelTechnicalStatus.INCOMPLETE
            diagnostics = (_graph_diagnostic(error, node.node_id),)
        else:
            outcome = validate_model_graph(
                hashed,
                active_node_ids=closure,
                operator_registry=service.operator_registry,
                available_source_ids=service.available_source_ids,
            )
            status = (
                ModelTechnicalStatus.INCOMPLETE
                if outcome.technical_status is ModelTechnicalStatus.BLOCKED
                else ModelTechnicalStatus.EXECUTABLE
            )
            diagnostics = outcome.diagnostics
        normalized.append(
            rehash_model_node(
                node.model_copy(
                    update={
                        "technical_status": status,
                        "diagnostics": diagnostics,
                    }
                )
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.node_id))


def _materialize(
    profile: LoadedModelProfile,
    service: CurrentModelWorkspaceService,
    *,
    seed_id: str,
    recorded_at: datetime,
) -> _MaterializedStarter:
    _utc_text(recorded_at)
    seed_hash = typed_content_sha256(
        "m7-current-starter-seed",
        CURRENT_STARTER_MIGRATION_VERSION,
        {
            "profile_id": profile.profile_id,
            "profile_manifest_hash": profile.manifest_hash,
            "seed_id": seed_id,
        },
    )
    index = {_key(item): item for item in profile.library_items}
    if len(index) != len(profile.library_items):
        raise CurrentStarterMigrationError("starter package contains duplicate exact records")

    scheme = profile.scheme
    layout = cast(
        LayoutVersion,
        _require(
            index,
            ComponentKind.LAYOUT_VERSION,
            scheme.layout.version_id,
            LayoutVersion,
        ),
    )
    task_profile = cast(
        TaskProfileVersion,
        _require(
            index,
            ComponentKind.TASK_PROFILE_VERSION,
            scheme.task_profile.version_id,
            TaskProfileVersion,
        ),
    )
    reporting = cast(
        CoverageReportingPolicyVersion,
        _require(
            index,
            ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
            scheme.reporting_policy.version_id,
            CoverageReportingPolicyVersion,
        ),
    )
    positions = {position.node_id: position for position in layout.node_positions}
    groups = {node_id: group.group_id for group in layout.groups for node_id in group.node_ids}
    max_source_y = max(
        (position.y for position in layout.node_positions if position.x == 0.0),
        default=0.0,
    )

    target_by_legacy: dict[LegacyKey, set[CurrentTarget]] = defaultdict(set)
    raw_node_id_by_source: dict[str, str] = {}
    raw_nodes: list[ModelNode] = []
    source_descriptors = tuple(
        sorted(
            (item for item in profile.library_items if isinstance(item, SourceDescriptor)),
            key=lambda item: item.source_id,
        )
    )
    missing_position_index = 0
    for descriptor in source_descriptors:
        node_id = _current_id("model-node.raw_input", (descriptor,))
        raw_node_id_by_source[descriptor.source_id] = node_id
        position = positions.get(descriptor.source_id)
        if position is None:
            missing_position_index += 1
            x = 0.0
            y = max_source_y + 100.0 * missing_position_index
        else:
            x, y = position.x, position.y
        family = _raw_family(descriptor)
        metadata: dict[str, JsonValue] = dict(descriptor.metadata)
        metadata.update(
            {
                "legacy_source_kind": descriptor.kind.value,
                "physical_modality": (
                    descriptor.raw_modality.value if descriptor.raw_modality is not None else None
                ),
                "starter_seed_id": seed_id,
            }
        )
        node = ModelNode(
            **_node_fields(
                node_id=node_id,
                node_kind=ModelNodeKind.RAW_INPUT,
                name=descriptor.name,
                short_name=descriptor.source_id,
                description=descriptor.description,
                tags=("starter",),
                group=groups.get(descriptor.source_id, "layout-group.sources"),
                layout=NodeLayout(node_id=node_id, x=x, y=y),
                recorded_at=recorded_at,
            ),
            definition=RawInputNodeDefinition(
                family=family,
                resource_role=_resource_role(descriptor),
                source_descriptor=descriptor,
                metadata=metadata,
                help_text=descriptor.description,
            ),
        )
        raw_nodes.append(node)
        target_by_legacy[_key(descriptor)].add((ModelObjectKind.NODE, node_id))

    bn_versions = tuple(
        cast(
            BnNodeVersion,
            _require(
                index,
                ComponentKind.BN_NODE_VERSION,
                reference.version_id,
                BnNodeVersion,
            ),
        )
        for reference in scheme.bn_node_versions
    )
    bn_records: dict[str, tuple[BnNodeConcept, BnNodeVersion, CptVersion]] = {}
    bn_node_ids: dict[str, str] = {}
    for version in bn_versions:
        concept = cast(
            BnNodeConcept,
            _require(
                index,
                ComponentKind.BN_NODE_CONCEPT,
                version.concept_id,
                BnNodeConcept,
            ),
        )
        cpt = cast(
            CptVersion,
            _require(
                index,
                ComponentKind.CPT_VERSION,
                version.cpt_version_id.version_id,
                CptVersion,
            ),
        )
        records = (concept, version, cpt)
        bn_records[version.bn_node_version_id] = records
        bn_node_ids[version.bn_node_version_id] = _current_id("model-node.bn", records)

    evidence_bindings = tuple(
        cast(
            EvidenceBindingVersion,
            _require(
                index,
                ComponentKind.EVIDENCE_BINDING_VERSION,
                reference.version_id,
                EvidenceBindingVersion,
            ),
        )
        for reference in scheme.evidence_binding_versions
    )
    selected_evidence_ids = {reference.version_id for reference in scheme.evidence_versions}
    evidence_records: dict[
        str,
        tuple[EvidenceConcept, EvidenceVersion, EvidenceBindingVersion, CptVersion],
    ] = {}
    evidence_node_ids: dict[str, str] = {}
    for binding in evidence_bindings:
        evidence = cast(
            EvidenceVersion,
            _require(
                index,
                ComponentKind.EVIDENCE_VERSION,
                binding.evidence_version_id.version_id,
                EvidenceVersion,
            ),
        )
        if evidence.evidence_version_id not in selected_evidence_ids:
            raise CurrentStarterMigrationError(
                f"binding {binding.evidence_binding_version_id!r} selects an unpinned Evidence"
            )
        concept = cast(
            EvidenceConcept,
            _require(
                index,
                ComponentKind.EVIDENCE_CONCEPT,
                evidence.concept_id,
                EvidenceConcept,
            ),
        )
        cpt = cast(
            CptVersion,
            _require(
                index,
                ComponentKind.CPT_VERSION,
                binding.cpt_version_id.version_id,
                CptVersion,
            ),
        )
        records = (concept, evidence, binding, cpt)
        evidence_records[binding.evidence_binding_version_id] = records
        evidence_node_ids[binding.evidence_binding_version_id] = _current_id(
            "model-node.evidence",
            records,
        )

    bn_nodes: list[ModelNode] = []
    for version_id in sorted(bn_records):
        concept, version, cpt = bn_records[version_id]
        node_id = bn_node_ids[version_id]
        parents = tuple(
            _node_ref_for_component(
                parent,
                bn_node_ids=bn_node_ids,
                evidence_node_ids=evidence_node_ids,
            )
            for parent in version.ordered_probabilistic_parent_ids
        )
        node_cpt = _node_cpt(
            cpt,
            node_id=node_id,
            node_kind=ModelNodeKind.BN,
            bn_node_ids=bn_node_ids,
            evidence_node_ids=evidence_node_ids,
        )
        if node_cpt.ordered_parent_nodes != parents:
            raise CurrentStarterMigrationError(
                f"BN {version_id!r} parent order disagrees with its exact CPT"
            )
        position = positions.get(version_id)
        x, y = (360.0, 0.0) if position is None else (position.x, position.y)
        provenance: dict[str, JsonValue] = {
            "migration": "m5-legacy-to-m7-current-v1",
            "seed_id": seed_id,
            "seed_hash": seed_hash,
            "legacy_records": _legacy_refs((concept, version, cpt)),
        }
        node = ModelNode(
            **_node_fields(
                node_id=node_id,
                node_kind=ModelNodeKind.BN,
                name=concept.name,
                short_name=concept.name,
                description=concept.description,
                tags=(*concept.tags, "starter"),
                group=groups.get(version_id),
                layout=NodeLayout(node_id=node_id, x=x, y=y),
                recorded_at=recorded_at,
            ),
            definition=BnNodeDefinition(
                node_role=concept.node_role,
                ordered_states=version.ordered_states,
                ordered_probabilistic_parent_nodes=parents,
                cpt=node_cpt,
                documentation=version.documentation,
                scientific_status=version.scientific_status,
                reporting_metadata={"legacy_concept_id": concept.concept_id},
                provenance=provenance,
                help_text=version.documentation,
            ),
        )
        bn_nodes.append(node)
        target = (ModelObjectKind.NODE, node_id)
        for item in (concept, version, cpt):
            target_by_legacy[_key(item)].add(target)

    evidence_nodes: list[ModelNode] = []
    for binding_id in sorted(evidence_records):
        concept, evidence, binding, cpt = evidence_records[binding_id]
        node_id = evidence_node_ids[binding_id]
        parents = tuple(
            _node_ref_for_component(
                parent,
                bn_node_ids=bn_node_ids,
                evidence_node_ids=evidence_node_ids,
            )
            for parent in binding.ordered_probabilistic_parent_ids
        )
        node_cpt = _node_cpt(
            cpt,
            node_id=node_id,
            node_kind=ModelNodeKind.EVIDENCE,
            bn_node_ids=bn_node_ids,
            evidence_node_ids=evidence_node_ids,
        )
        if node_cpt.ordered_parent_nodes != parents:
            raise CurrentStarterMigrationError(
                f"Evidence {binding_id!r} parent order disagrees with its exact CPT"
            )
        data_bindings: list[EvidenceDataBinding] = []
        for recipe_input in evidence.recipe.inputs:
            raw_node_id = raw_node_id_by_source.get(recipe_input.source_id)
            if raw_node_id is None:
                raise CurrentStarterMigrationError(
                    f"Evidence {binding_id!r} source {recipe_input.source_id!r} has no Raw Input"
                )
            data_bindings.append(
                EvidenceDataBinding(
                    recipe_input_binding_id=recipe_input.binding_id,
                    raw_input_node=ModelNodeRef(
                        node_id=raw_node_id,
                        node_kind=ModelNodeKind.RAW_INPUT,
                    ),
                )
            )
        position = positions.get(binding_id)
        x, y = (1080.0, 0.0) if position is None else (position.x, position.y)
        provenance = {
            "migration": "m5-legacy-to-m7-current-v1",
            "seed_id": seed_id,
            "seed_hash": seed_hash,
            "legacy_records": _legacy_refs((concept, evidence, binding, cpt)),
        }
        node = ModelNode(
            **_node_fields(
                node_id=node_id,
                node_kind=ModelNodeKind.EVIDENCE,
                name=concept.name,
                short_name=evidence.recipe.anchor.anchor_id,
                description=concept.description,
                tags=(*concept.tags, "starter"),
                group=groups.get(binding_id),
                layout=NodeLayout(node_id=node_id, x=x, y=y),
                recorded_at=recorded_at,
            ),
            definition=EvidenceNodeDefinition(
                recipe=evidence.recipe,
                data_bindings=tuple(data_bindings),
                ordered_observation_states=binding.ordered_observation_states,
                observation_mapping=dict(binding.observation_mapping),
                ordered_probabilistic_parent_nodes=parents,
                cpt=node_cpt,
                observation_policy=binding.observation_policy,
                modality_attribution_weights=dict(binding.modality_attribution_weights),
                scientific_status=evidence.scientific_status,
                provenance=provenance,
                help_text=evidence.recipe.documentation.summary,
            ),
        )
        evidence_nodes.append(node)
        target = (ModelObjectKind.NODE, node_id)
        for item in (concept, evidence, binding, cpt):
            target_by_legacy[_key(item)].add(target)

    nodes = _normalize_nodes(tuple((*raw_nodes, *bn_nodes, *evidence_nodes)), service)
    source_node_ids = {
        raw_node_id_by_source[reference.version_id] for reference in scheme.source_descriptors
    }
    explicit = tuple(sorted(source_node_ids | set(evidence_node_ids.values())))
    closure = activation_closure(nodes, explicit)
    output_ids = tuple(
        sorted(
            _node_ref_for_component(
                reference,
                bn_node_ids=bn_node_ids,
                evidence_node_ids=evidence_node_ids,
            ).node_id
            for reference in scheme.output_node_ids
        )
    )
    if not set(output_ids).issubset(closure):
        raise CurrentStarterMigrationError("starter outputs do not resolve inside active closure")

    scheme_records: tuple[LibraryItem, ...] = (scheme, task_profile, reporting, layout)
    scheme_id = _current_id("task-scheme", scheme_records)
    task_bindings: dict[str, JsonValue] = {
        "starter_profile_id": profile.profile_id,
        "starter_manifest_hash": profile.manifest_hash,
        "legacy_scheme": {
            "record_id": scheme.scheme_version_id,
            "content_hash": scheme.content_hash,
            "name": scheme.name,
        },
        "task_profile": cast(JsonValue, task_profile.model_dump(mode="json")),
        "reporting_policy": cast(JsonValue, reporting.model_dump(mode="json")),
        "layout_context": {
            "legacy_layout_id": layout.layout_version_id,
            "viewport": layout.viewport.model_dump(mode="json"),
            "groups": [group.model_dump(mode="json") for group in layout.groups],
        },
    }
    outcome = validate_model_graph(
        nodes,
        active_node_ids=closure,
        operator_registry=service.operator_registry,
        available_source_ids=service.available_source_ids,
    )
    current_scheme = rehash_task_scheme(
        TaskScheme(
            scheme_id=scheme_id,
            name="Base Scheme",
            description=scheme.description,
            tags=("starter",),
            group="starter",
            lifecycle=ModelObjectLifecycle.ACTIVE,
            copied_from_scheme_id=None,
            explicit_active_node_ids=explicit,
            computed_active_closure=closure,
            output_node_ids=output_ids,
            task_bindings=task_bindings,
            layout_overrides=(),
            semantic_revision=0,
            layout_revision=0,
            technical_status=outcome.technical_status,
            diagnostics=outcome.diagnostics,
            content_hash=_ZERO_HASH,
            layout_hash=_ZERO_HASH,
            created_at=recorded_at,
            updated_at=recorded_at,
        )
    )
    scheme_target = (ModelObjectKind.SCHEME, scheme_id)
    for item in scheme_records:
        target_by_legacy[_key(item)].add(scheme_target)

    unmapped = set(index) - set(target_by_legacy)
    if unmapped:
        labels = ", ".join(f"{kind.value}:{record_id}" for kind, record_id in sorted(unmapped))
        raise CurrentStarterMigrationError(f"starter contains unmapped legacy records: {labels}")

    mappings = tuple(
        sorted(
            (
                _StarterMapping(
                    mapping_id=_mapping_id(legacy_key, target, seed_id=seed_id),
                    legacy_kind=legacy_key[0],
                    legacy_record_id=legacy_key[1],
                    current_object_kind=target[0],
                    current_object_id=target[1],
                    seed_id=seed_id,
                    seed_hash=seed_hash,
                )
                for legacy_key, targets in target_by_legacy.items()
                for target in targets
            ),
            key=lambda item: item.mapping_id,
        )
    )
    return _MaterializedStarter(
        seed_id=seed_id,
        seed_hash=seed_hash,
        nodes=nodes,
        scheme=current_scheme,
        mappings=mappings,
    )


def _verify_existing(
    materialized: _MaterializedStarter,
    connection,
) -> None:
    rows = connection.execute(
        """
        SELECT mapping_id, legacy_kind, legacy_record_id,
               current_object_kind, current_object_id, seed_id, seed_hash
        FROM model_starter_mappings WHERE seed_id = ? ORDER BY mapping_id
        """,
        (materialized.seed_id,),
    ).fetchall()
    actual = tuple(
        (
            row["mapping_id"],
            row["legacy_kind"],
            row["legacy_record_id"],
            row["current_object_kind"],
            row["current_object_id"],
            row["seed_id"],
            row["seed_hash"],
        )
        for row in rows
    )
    expected = tuple(
        (
            item.mapping_id,
            item.legacy_kind.value,
            item.legacy_record_id,
            item.current_object_kind.value,
            item.current_object_id,
            item.seed_id,
            item.seed_hash,
        )
        for item in materialized.mappings
    )
    if actual != expected:
        raise CurrentStarterMigrationError("current starter mapping set is incomplete or changed")
    for mapping in materialized.mappings:
        table, id_column = (
            ("model_nodes", "node_id")
            if mapping.current_object_kind is ModelObjectKind.NODE
            else ("task_schemes", "scheme_id")
        )
        row = connection.execute(
            f"SELECT 1 FROM {table} WHERE {id_column} = ?",  # noqa: S608
            (mapping.current_object_id,),
        ).fetchone()
        if row is None:
            raise CurrentStarterMigrationError(
                f"mapped current object {mapping.current_object_id!r} is missing"
            )


def seed_current_starter(
    profile: LoadedModelProfile,
    service: CurrentModelWorkspaceService,
    *,
    recorded_at: datetime,
    seed_id: str = CURRENT_HOVER_STARTER_SEED_ID,
) -> CurrentStarterSeedResult:
    """Create one editable current starter atomically, or verify its durable mapping."""

    materialized = _materialize(
        profile,
        service,
        seed_id=seed_id,
        recorded_at=recorded_at,
    )
    database = service.repository.database
    applied = False
    transaction_id = f"system-seed.{materialized.seed_hash[:32]}"
    with database.transaction() as connection:
        marker = connection.execute(
            "SELECT seed_hash FROM project_seed_markers WHERE seed_id = ?",
            (seed_id,),
        ).fetchone()
        if marker is not None:
            if marker["seed_hash"] != materialized.seed_hash:
                raise CurrentStarterMigrationError(
                    "current starter seed marker does not match the migration input"
                )
            _verify_existing(materialized, connection)
        else:
            stray = connection.execute(
                "SELECT 1 FROM model_starter_mappings WHERE seed_id = ? LIMIT 1",
                (seed_id,),
            ).fetchone()
            if stray is not None:
                raise CurrentStarterMigrationError(
                    "current starter mappings exist without their seed marker"
                )
            edges = project_model_edges(materialized.nodes)
            for node in materialized.nodes:
                service.repository.create_node(
                    node,
                    event_id=_event_id(materialized.seed_hash, ModelObjectKind.NODE, node.node_id),
                    actor_id=_SYSTEM_ACTOR,
                    transaction_id=transaction_id,
                    occurred_at=recorded_at,
                    diff=CanonicalModelDiff(
                        changed_paths=(f"/nodes/{node.node_id}",),
                        added_node_ids=(node.node_id,),
                        removed_node_ids=(),
                        added_edge_ids=tuple(
                            edge.edge_id for edge in edges if edge.child.node_id == node.node_id
                        ),
                        removed_edge_ids=(),
                        metadata={"mutation": "migrate_starter_to_current_model"},
                    ),
                    join_existing=True,
                )
            service.repository.create_scheme(
                materialized.scheme,
                event_id=_event_id(
                    materialized.seed_hash,
                    ModelObjectKind.SCHEME,
                    materialized.scheme.scheme_id,
                ),
                actor_id=_SYSTEM_ACTOR,
                transaction_id=transaction_id,
                occurred_at=recorded_at,
                diff=CanonicalModelDiff(
                    changed_paths=(f"/schemes/{materialized.scheme.scheme_id}",),
                    added_node_ids=(),
                    removed_node_ids=(),
                    added_edge_ids=(),
                    removed_edge_ids=(),
                    metadata={"mutation": "migrate_starter_to_current_model"},
                ),
                join_existing=True,
            )
            for mapping in materialized.mappings:
                connection.execute(
                    """
                    INSERT INTO model_starter_mappings(
                        mapping_id, legacy_kind, legacy_record_id,
                        current_object_kind, current_object_id,
                        seed_id, seed_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mapping.mapping_id,
                        mapping.legacy_kind.value,
                        mapping.legacy_record_id,
                        mapping.current_object_kind.value,
                        mapping.current_object_id,
                        mapping.seed_id,
                        mapping.seed_hash,
                        _utc_text(recorded_at),
                    ),
                )
            connection.execute(
                """
                INSERT INTO project_seed_markers(seed_id, seed_hash, applied_at)
                VALUES (?, ?, ?)
                """,
                (seed_id, materialized.seed_hash, _utc_text(recorded_at)),
            )
            applied = True

    return CurrentStarterSeedResult(
        seed_id=materialized.seed_id,
        seed_hash=materialized.seed_hash,
        scheme_id=materialized.scheme.scheme_id,
        applied=applied,
        inserted_nodes=len(materialized.nodes) if applied else 0,
        inserted_schemes=1 if applied else 0,
        total_nodes=len(materialized.nodes),
        total_schemes=1,
        mapping_count=len(materialized.mappings),
    )


__all__ = [
    "CURRENT_HOVER_STARTER_SEED_ID",
    "CURRENT_STARTER_MIGRATION_VERSION",
    "CurrentStarterMigrationError",
    "CurrentStarterSeedResult",
    "seed_current_starter",
]
