"""Hidden immutable execution assets for autosaved current M7 model graphs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import ValidationError, model_validator

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    NodePosition,
    TaskProfileVersion,
    Viewport,
)
from pilot_assessment.contracts.common import Sha256Digest, StableId, StrictContractModel
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    ComponentLifecycle,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    PinnedComponentRef,
    SourceDescriptor,
    VersionLineage,
)
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeKind,
    ModelObjectLifecycle,
    RawInputNodeDefinition,
    TaskScheme,
)
from pilot_assessment.contracts.run import ModelNodeSnapshotRef
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import (
    DuplicateLibraryItemError,
    LibraryItem,
    LibraryItemNotFoundError,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_workspace.graph import project_model_edges
from pilot_assessment.model_workspace.hashing import model_graph_semantic_hash
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository

ZERO_HASH = "0" * 64
MATERIALIZATION_VERSION = "0.1.0"
_CREATED_BY = "system.current-execution-materializer"


class CurrentExecutionMaterializationError(RuntimeError):
    """A current graph cannot be represented by the existing execution engine."""


class CurrentExecutionMaterialization(StrictContractModel):
    """Durable bridge identity; it is internal and never a user version picker."""

    contract_id: Literal["current-execution-materialization"] = "current-execution-materialization"
    contract_version: Literal["0.1.0"] = "0.1.0"
    graph_hash: Sha256Digest
    semantic_graph_hash: Sha256Digest
    scheme_id: StableId
    scheme_semantic_revision: int
    scheme_content_hash: Sha256Digest
    active_node_refs: tuple[ModelNodeSnapshotRef, ...]
    legacy_scheme_ref: PinnedComponentRef

    @model_validator(mode="after")
    def validate_identity(self) -> CurrentExecutionMaterialization:
        if self.scheme_semantic_revision < 0:
            raise ValueError("scheme semantic revision must be non-negative")
        node_ids = tuple(item.node_id for item in self.active_node_refs)
        if node_ids != tuple(sorted(node_ids)) or len(node_ids) != len(set(node_ids)):
            raise ValueError("active node refs must use unique canonical order")
        if self.legacy_scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("legacy scheme ref must identify an assessment scheme")
        return self


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentExecutionMaterializationError(
            "execution materialization clock must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _compat_id(label: str, digest: str) -> str:
    return f"compat.current.{label}.{digest[:32]}"


def _node_digest(node: ModelNode) -> str:
    return typed_content_sha256(
        "current-execution-node",
        MATERIALIZATION_VERSION,
        {
            "node_id": node.node_id,
            "node_kind": node.node_kind.value,
            "content_hash": node.content_hash,
        },
    )


def _name(node: ModelNode) -> str:
    return node.name_en or cast(str, node.name_zh)


def _description(node: ModelNode) -> str:
    return node.description_en or cast(str, node.description_zh)


def _lineage(
    source_ids: tuple[str, ...],
    *,
    created_at: datetime,
    note: str,
) -> VersionLineage:
    return VersionLineage(
        source_version_ids=source_ids,
        created_at=created_at,
        created_by=_CREATED_BY,
        note=note,
    )


def _rehash(item: VersionLibraryItem) -> VersionLibraryItem:
    return item.model_copy(update={"content_hash": component_content_hash(item)})


def _pin(item: VersionLibraryItem) -> PinnedComponentRef:
    return PinnedComponentRef(
        kind=component_kind(item),
        version_id=component_record_id(item),
        content_hash=item.content_hash,
    )


def _variable_ref(
    node_id: str,
    nodes: dict[str, ModelNode],
    variable_ids: dict[str, str],
) -> ComponentIdRef:
    node = nodes.get(node_id)
    if node is None:
        raise CurrentExecutionMaterializationError(
            f"probabilistic node {node_id!r} is outside the active closure"
        )
    kind = {
        ModelNodeKind.EVIDENCE: ComponentKind.EVIDENCE_BINDING_VERSION,
        ModelNodeKind.BN: ComponentKind.BN_NODE_VERSION,
    }.get(node.node_kind)
    if kind is None:
        raise CurrentExecutionMaterializationError(
            f"raw input {node_id!r} cannot be a probabilistic variable"
        )
    return ComponentIdRef(kind=kind, version_id=variable_ids[node_id])


def _template_task_profile(scheme: TaskScheme) -> TaskProfileVersion:
    payload = scheme.task_bindings.get("task_profile")
    try:
        return TaskProfileVersion.model_validate(payload)
    except (TypeError, ValidationError) as error:
        raise CurrentExecutionMaterializationError(
            "task_bindings.task_profile must contain a complete task-profile contract"
        ) from error


def _template_reporting_policy(scheme: TaskScheme) -> CoverageReportingPolicyVersion:
    payload = scheme.task_bindings.get("reporting_policy")
    try:
        return CoverageReportingPolicyVersion.model_validate(payload)
    except (TypeError, ValidationError) as error:
        raise CurrentExecutionMaterializationError(
            "task_bindings.reporting_policy must contain a complete reporting-policy contract"
        ) from error


def _materialized_records(
    scheme: TaskScheme,
    active_nodes: tuple[ModelNode, ...],
    *,
    graph_hash: str,
) -> tuple[tuple[LibraryItem, ...], AssessmentSchemeVersion]:
    nodes = {node.node_id: node for node in active_nodes}
    variable_ids: dict[str, str] = {}
    evidence_version_ids: dict[str, str] = {}
    cpt_ids: dict[str, str] = {}
    concept_ids: dict[str, str] = {}
    for node in active_nodes:
        digest = _node_digest(node)
        if node.node_kind is ModelNodeKind.EVIDENCE:
            concept_ids[node.node_id] = _compat_id("evidence.concept", digest)
            evidence_version_ids[node.node_id] = _compat_id("evidence.version", digest)
            variable_ids[node.node_id] = _compat_id("evidence.binding", digest)
            cpt_ids[node.node_id] = _compat_id("evidence.cpt", digest)
        elif node.node_kind is ModelNodeKind.BN:
            concept_ids[node.node_id] = _compat_id("bn.concept", digest)
            variable_ids[node.node_id] = _compat_id("bn.version", digest)
            cpt_ids[node.node_id] = _compat_id("bn.cpt", digest)

    raw_records: dict[str, SourceDescriptor] = {}
    concepts: list[LibraryItem] = []
    versions: list[LibraryItem] = []
    cpts: list[LibraryItem] = []
    for node in active_nodes:
        definition = node.definition
        if isinstance(definition, RawInputNodeDefinition):
            descriptor = definition.source_descriptor
            previous = raw_records.get(descriptor.source_id)
            if previous is not None and previous != descriptor:
                raise CurrentExecutionMaterializationError(
                    f"active Raw Input nodes disagree on source {descriptor.source_id!r}"
                )
            raw_records[descriptor.source_id] = descriptor
            continue

        parent_refs = tuple(
            _variable_ref(parent.node_id, nodes, variable_ids)
            for parent in definition.ordered_probabilistic_parent_nodes
        )
        child_ref = _variable_ref(node.node_id, nodes, variable_ids)
        cpt_lineage = _lineage(
            (node.node_id,),
            created_at=node.created_at,
            note="Internal immutable CPT compiled from one current complete node.",
        )
        provisional_cpt = CptVersion(
            cpt_version_id=cpt_ids[node.node_id],
            child_variable_id=child_ref,
            ordered_parent_variable_ids=parent_refs,
            child_state_ids=definition.cpt.child_state_ids,
            ordered_parent_state_ids=definition.cpt.ordered_parent_state_ids,
            materialized_probabilities=definition.cpt.materialized_probabilities,
            mode=definition.cpt.mode,
            generator_metadata=dict(definition.cpt.generator_metadata),
            source=definition.cpt.source,
            lineage=cpt_lineage,
            content_hash=ZERO_HASH,
        )
        cpt = cast(CptVersion, _rehash(provisional_cpt))
        cpts.append(cpt)

        if isinstance(definition, EvidenceNodeDefinition):
            concept = EvidenceConcept(
                concept_id=concept_ids[node.node_id],
                name=_name(node),
                description=_description(node),
                tags=node.tags,
                lifecycle=ComponentLifecycle.ACTIVE,
            )
            concepts.append(concept)
            lineage = _lineage(
                (node.node_id,),
                created_at=node.created_at,
                note="Internal immutable Evidence compiled from one current complete node.",
            )
            provisional_evidence = EvidenceVersion(
                evidence_version_id=evidence_version_ids[node.node_id],
                concept_id=concept.concept_id,
                recipe=definition.recipe,
                scientific_status=definition.scientific_status,
                lineage=lineage,
                content_hash=ZERO_HASH,
            )
            evidence = cast(EvidenceVersion, _rehash(provisional_evidence))
            versions.append(evidence)
            provisional_binding = EvidenceBindingVersion(
                evidence_binding_version_id=variable_ids[node.node_id],
                evidence_version_id=ComponentIdRef(
                    kind=ComponentKind.EVIDENCE_VERSION,
                    version_id=evidence.evidence_version_id,
                ),
                ordered_observation_states=definition.ordered_observation_states,
                observation_mapping=dict(definition.observation_mapping),
                ordered_probabilistic_parent_ids=parent_refs,
                cpt_version_id=ComponentIdRef(
                    kind=ComponentKind.CPT_VERSION,
                    version_id=cpt.cpt_version_id,
                ),
                observation_policy=definition.observation_policy,
                modality_attribution_weights=dict(definition.modality_attribution_weights),
                lineage=lineage,
                content_hash=ZERO_HASH,
            )
            versions.append(_rehash(provisional_binding))
            continue

        if not isinstance(definition, BnNodeDefinition):
            raise CurrentExecutionMaterializationError(
                f"unsupported current node definition {type(definition).__name__}"
            )
        concept = BnNodeConcept(
            concept_id=concept_ids[node.node_id],
            name=_name(node),
            description=_description(node),
            node_role=definition.node_role,
            tags=node.tags,
            lifecycle=ComponentLifecycle.ACTIVE,
        )
        concepts.append(concept)
        lineage = _lineage(
            (node.node_id,),
            created_at=node.created_at,
            note="Internal immutable BN variable compiled from one current complete node.",
        )
        provisional_bn = BnNodeVersion(
            bn_node_version_id=variable_ids[node.node_id],
            concept_id=concept.concept_id,
            ordered_states=definition.ordered_states,
            ordered_probabilistic_parent_ids=parent_refs,
            cpt_version_id=ComponentIdRef(
                kind=ComponentKind.CPT_VERSION,
                version_id=cpt.cpt_version_id,
            ),
            documentation=definition.documentation,
            scientific_status=definition.scientific_status,
            lineage=lineage,
            content_hash=ZERO_HASH,
        )
        versions.append(_rehash(provisional_bn))

    source_ids = tuple(sorted(raw_records))
    task_template = _template_task_profile(scheme)
    task_id = _compat_id("task", graph_hash)
    task_lineage = _lineage(
        (task_template.task_profile_version_id, scheme.scheme_id),
        created_at=scheme.created_at,
        note="Internal task projection for a frozen current graph.",
    )
    provisional_task = task_template.model_copy(
        update={
            "task_profile_version_id": task_id,
            "task_concept_id": _compat_id("task.concept", graph_hash),
            "name": scheme.name_en or cast(str, scheme.name_zh),
            "description": scheme.description_en or cast(str, scheme.description_zh),
            "required_source_descriptor_ids": source_ids,
            "lineage": task_lineage,
            "content_hash": ZERO_HASH,
        }
    )
    task = cast(TaskProfileVersion, _rehash(provisional_task))

    reporting_template = _template_reporting_policy(scheme)
    reporting_id = _compat_id("reporting", graph_hash)
    provisional_reporting = reporting_template.model_copy(
        update={
            "policy_version_id": reporting_id,
            "lineage": _lineage(
                (reporting_template.policy_version_id, scheme.scheme_id),
                created_at=scheme.created_at,
                note="Internal reporting projection for a frozen current graph.",
            ),
            "content_hash": ZERO_HASH,
        }
    )
    reporting = cast(CoverageReportingPolicyVersion, _rehash(provisional_reporting))

    legacy_id_by_current: dict[str, str] = {
        **{
            node.node_id: node.definition.source_descriptor.source_id
            for node in active_nodes
            if isinstance(node.definition, RawInputNodeDefinition)
        },
        **variable_ids,
    }
    layout_id = _compat_id("layout", graph_hash)
    positions = tuple(
        NodePosition(
            node_id=legacy_id_by_current[node.node_id],
            x=float(
                {ModelNodeKind.RAW_INPUT: 0, ModelNodeKind.BN: 1, ModelNodeKind.EVIDENCE: 2}[
                    node.node_kind
                ]
                * 360
            ),
            y=float(index * 90),
        )
        for index, node in enumerate(active_nodes)
    )
    provisional_layout = LayoutVersion(
        layout_version_id=layout_id,
        node_positions=positions,
        groups=(),
        viewport=Viewport(x=0.0, y=0.0, zoom=1.0),
        lineage=_lineage(
            (scheme.scheme_id,),
            created_at=scheme.created_at,
            note="Internal deterministic execution layout; the current UI layout stays in M7.",
        ),
        content_hash=ZERO_HASH,
    )
    layout = cast(LayoutVersion, _rehash(provisional_layout))

    evidence_versions = tuple(item for item in versions if isinstance(item, EvidenceVersion))
    evidence_bindings = tuple(item for item in versions if isinstance(item, EvidenceBindingVersion))
    bn_versions = tuple(item for item in versions if isinstance(item, BnNodeVersion))
    output_refs = tuple(
        _variable_ref(node_id, nodes, variable_ids) for node_id in scheme.output_node_ids
    )
    provisional_scheme = AssessmentSchemeVersion(
        scheme_version_id=_compat_id("scheme", graph_hash),
        scheme_concept_id=_compat_id("scheme.concept", graph_hash),
        name=scheme.name_en or cast(str, scheme.name_zh),
        description=scheme.description_en or cast(str, scheme.description_zh),
        task_profile=_pin(task),
        source_descriptors=tuple(_pin(raw_records[key]) for key in source_ids),
        evidence_versions=tuple(_pin(item) for item in evidence_versions),
        evidence_binding_versions=tuple(_pin(item) for item in evidence_bindings),
        bn_node_versions=tuple(_pin(item) for item in bn_versions),
        cpt_versions=tuple(_pin(cast(CptVersion, item)) for item in cpts),
        reporting_policy=_pin(reporting),
        layout=_pin(layout),
        output_node_ids=output_refs,
        lineage=_lineage(
            (scheme.scheme_id,),
            created_at=scheme.created_at,
            note="Internal immutable execution scheme for an autosaved current TaskScheme.",
        ),
        content_hash=ZERO_HASH,
    )
    legacy_scheme = cast(AssessmentSchemeVersion, _rehash(provisional_scheme))
    records: tuple[LibraryItem, ...] = tuple(
        (
            *sorted(raw_records.values(), key=lambda item: item.source_id),
            *sorted(
                concepts, key=lambda item: (component_kind(item).value, component_record_id(item))
            ),
            *sorted(
                versions, key=lambda item: (component_kind(item).value, component_record_id(item))
            ),
            *sorted(cpts, key=lambda item: component_record_id(item)),
            task,
            reporting,
            layout,
            legacy_scheme,
        )
    )
    return records, legacy_scheme


class CurrentModelExecutionMaterializer:
    """Compile current declarations to immutable M5/M6 execution records."""

    def __init__(
        self,
        database: ProjectDatabase,
        components: SqliteComponentLibraryRepository,
        workspace: CurrentModelWorkspaceService,
        *,
        clock: Clock,
    ) -> None:
        self.database = database
        self.components = components
        self.workspace = workspace
        self.clock = clock

    def materialize(self, scheme_id: str) -> CurrentExecutionMaterialization:
        scheme = self.workspace.get_scheme(scheme_id)
        if scheme.lifecycle is not ModelObjectLifecycle.ACTIVE:
            raise CurrentExecutionMaterializationError("archived schemes cannot be executed")
        all_nodes = {node.node_id: node for node in self.workspace.list_nodes()}
        try:
            active_nodes = tuple(all_nodes[node_id] for node_id in scheme.computed_active_closure)
        except KeyError as error:
            raise CurrentExecutionMaterializationError(
                f"active node {error.args[0]!r} does not exist"
            ) from error
        if any(node.lifecycle is not ModelObjectLifecycle.ACTIVE for node in active_nodes):
            raise CurrentExecutionMaterializationError("active closure contains an archived node")
        edges = project_model_edges(active_nodes, node_ids=scheme.computed_active_closure)
        semantic_graph_hash = model_graph_semantic_hash(
            self.workspace.project_id,
            scheme,
            active_nodes,
            edges,
        )
        active_refs = tuple(
            ModelNodeSnapshotRef(
                node_id=node.node_id,
                node_kind=node.node_kind,
                semantic_revision=node.semantic_revision,
                content_hash=node.content_hash,
            )
            for node in active_nodes
        )
        graph_hash = typed_content_sha256(
            "current-execution-graph-lock",
            MATERIALIZATION_VERSION,
            {
                "semantic_graph_hash": semantic_graph_hash,
                "scheme_semantic_revision": scheme.semantic_revision,
                "active_node_refs": [item.model_dump(mode="json") for item in active_refs],
            },
        )
        existing = self.database.fetchone(
            "SELECT * FROM model_execution_materializations WHERE graph_hash = ?",
            (graph_hash,),
        )
        if existing is not None:
            return self._from_row(existing, expected_refs=active_refs)

        records, legacy_scheme = _materialized_records(
            scheme,
            active_nodes,
            graph_hash=graph_hash,
        )
        materialization = CurrentExecutionMaterialization(
            graph_hash=graph_hash,
            semantic_graph_hash=semantic_graph_hash,
            scheme_id=scheme.scheme_id,
            scheme_semantic_revision=scheme.semantic_revision,
            scheme_content_hash=scheme.content_hash,
            active_node_refs=active_refs,
            legacy_scheme_ref=_pin(legacy_scheme),
        )
        timestamp = _utc_text(self.clock())
        try:
            with self.database.transaction() as connection:
                for item in records:
                    kind = component_kind(item)
                    record_id = component_record_id(item)
                    row = connection.execute(
                        "SELECT 1 FROM library_records WHERE kind = ? AND record_id = ?",
                        (kind.value, record_id),
                    ).fetchone()
                    if row is None:
                        self.components.add_in_transaction(
                            connection,
                            item,
                            recorded_at_text=timestamp,
                        )
                    elif self.components.get_exact(kind, record_id) != item:
                        raise CurrentExecutionMaterializationError(
                            f"immutable execution identity collides with {kind.value}:{record_id}"
                        )
                connection.execute(
                    """
                    INSERT INTO model_execution_materializations(
                        graph_hash, scheme_id, scheme_semantic_revision,
                        scheme_content_hash, legacy_scheme_version_id,
                        legacy_scheme_content_hash, materialization_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        graph_hash,
                        scheme.scheme_id,
                        scheme.semantic_revision,
                        scheme.content_hash,
                        legacy_scheme.scheme_version_id,
                        legacy_scheme.content_hash,
                        encode_canonical_json(materialization.model_dump(mode="json")),
                        timestamp,
                    ),
                )
        except (sqlite3.IntegrityError, DuplicateLibraryItemError) as error:
            raise CurrentExecutionMaterializationError(
                "current execution materialization could not be persisted atomically"
            ) from error
        return materialization

    def get(self, graph_hash: str) -> CurrentExecutionMaterialization:
        row = self.database.fetchone(
            "SELECT * FROM model_execution_materializations WHERE graph_hash = ?",
            (graph_hash,),
        )
        if row is None:
            raise CurrentExecutionMaterializationError(graph_hash)
        return self._from_row(row, expected_refs=None)

    def _from_row(
        self,
        row,
        *,
        expected_refs: tuple[ModelNodeSnapshotRef, ...] | None,
    ) -> CurrentExecutionMaterialization:
        try:
            materialization = CurrentExecutionMaterialization.model_validate(
                decode_canonical_json(row["materialization_json"])
            )
        except (ValueError, ValidationError) as error:
            raise CurrentExecutionMaterializationError(
                "stored current execution materialization is invalid"
            ) from error
        if (
            materialization.graph_hash != row["graph_hash"]
            or materialization.scheme_id != row["scheme_id"]
            or materialization.scheme_semantic_revision != int(row["scheme_semantic_revision"])
            or materialization.scheme_content_hash != row["scheme_content_hash"]
            or materialization.legacy_scheme_ref.version_id != row["legacy_scheme_version_id"]
            or materialization.legacy_scheme_ref.content_hash != row["legacy_scheme_content_hash"]
            or (expected_refs is not None and materialization.active_node_refs != expected_refs)
        ):
            raise CurrentExecutionMaterializationError(
                "stored materialization identity columns disagree with canonical JSON"
            )
        try:
            legacy = self.components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                materialization.legacy_scheme_ref.version_id,
            )
        except LibraryItemNotFoundError as error:
            raise CurrentExecutionMaterializationError(
                "materialized legacy execution scheme is missing"
            ) from error
        if not isinstance(legacy, AssessmentSchemeVersion) or (
            legacy.content_hash != materialization.legacy_scheme_ref.content_hash
        ):
            raise CurrentExecutionMaterializationError(
                "materialized legacy execution scheme changed"
            )
        return materialization


__all__ = [
    "CurrentExecutionMaterialization",
    "CurrentExecutionMaterializationError",
    "CurrentModelExecutionMaterializer",
]
