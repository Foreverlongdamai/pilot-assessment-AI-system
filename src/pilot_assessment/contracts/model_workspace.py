"""Current complete-node and task-activation contracts for the M7 workspace."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import (
    AwareDatetime,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from pilot_assessment.contracts.common import (
    FiniteFloat,
    NonNegativeInt,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
    freeze_json_mapping,
)
from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe
from pilot_assessment.contracts.model_components import (
    BnNodeRole,
    ComponentSource,
    CptMode,
    ModelScientificStatus,
    ObservationPolicy,
    RawModality,
    SourceDescriptor,
    SourceKind,
    VariableState,
)

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
ShortLabel = Annotated[str, StringConstraints(min_length=1, max_length=96)]
HumanText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]
JsonPointer = Annotated[str, StringConstraints(min_length=1, max_length=2048, pattern=r"^/")]


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


def _require_canonical_set(values: tuple[str, ...], label: str) -> None:
    _require_unique(values, label)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must use canonical sorted order")


def _freeze_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return freeze_json_mapping(value)


def _ref_key(reference: ModelNodeRef) -> str:
    return f"{reference.node_kind.value}:{reference.node_id}"


def _require_localized_pair(
    first: str | None,
    second: str | None,
    label: str,
) -> None:
    if first is None and second is None:
        raise ValueError(f"{label} requires at least one localized value")


def _require_utc_datetime(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC offset +00:00")
    return value


class ModelNodeKind(StrEnum):
    RAW_INPUT = "raw_input"
    EVIDENCE = "evidence"
    BN = "bn"


class ModelObjectKind(StrEnum):
    NODE = "node"
    SCHEME = "scheme"


class ModelObjectLifecycle(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ModelTechnicalStatus(StrEnum):
    EXECUTABLE = "executable"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


class ModelDiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RawInputFamily(StrEnum):
    X = "X"
    U = "U"
    I = "I"  # noqa: E741 - canonical raw-input family identifier
    G = "G"
    P = "P"
    PILOT_CAMERA = "pilot_camera"


class RawResourceRole(StrEnum):
    STREAM = "stream"
    TASK_REFERENCE = "task_reference"
    ANNOTATION = "annotation"
    EVENT = "event"
    AOI_DEFINITION = "aoi_definition"
    DERIVED_RESOURCE = "derived_resource"


class ModelGraphEdgeKind(StrEnum):
    EXTRACTION = "extraction"
    PROBABILISTIC = "probabilistic"


class ModelChangeKind(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    ARCHIVE = "archive"
    UNDO = "undo"
    REDO = "redo"
    MIGRATE = "migrate"


class ModelDiagnostic(StrictContractModel):
    code: StableId
    severity: ModelDiagnosticSeverity
    location: JsonPointer
    message: HumanLabel
    details: dict[str, JsonValue]

    @field_validator("details")
    @classmethod
    def freeze_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class ModelNodeRef(StrictContractModel):
    node_id: StableId
    node_kind: ModelNodeKind


class NodeLayout(StrictContractModel):
    node_id: StableId
    x: FiniteFloat
    y: FiniteFloat


class EvidenceDataBinding(StrictContractModel):
    recipe_input_binding_id: StableId
    raw_input_node: ModelNodeRef

    @model_validator(mode="after")
    def validate_raw_input(self) -> Self:
        if self.raw_input_node.node_kind is not ModelNodeKind.RAW_INPUT:
            raise ValueError("Evidence data bindings must identify Raw Input nodes")
        return self


class NodeCpt(StrictContractModel):
    cpt_id: StableId
    child_node: ModelNodeRef
    ordered_parent_nodes: tuple[ModelNodeRef, ...]
    child_state_ids: tuple[StableId, ...] = Field(min_length=2)
    ordered_parent_state_ids: tuple[tuple[StableId, ...], ...]
    materialized_probabilities: tuple[tuple[UnitInterval, ...], ...]
    mode: CptMode
    generator_metadata: dict[str, JsonValue]
    source: ComponentSource

    @field_validator("generator_metadata")
    @classmethod
    def freeze_generator_metadata(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_cpt(self) -> Self:
        if self.child_node.node_kind is ModelNodeKind.RAW_INPUT:
            raise ValueError("CPT child must identify an Evidence or BN node")
        parent_keys = tuple(_ref_key(parent) for parent in self.ordered_parent_nodes)
        _require_unique(parent_keys, "CPT parent nodes")
        if any(parent.node_kind is ModelNodeKind.RAW_INPUT for parent in self.ordered_parent_nodes):
            raise ValueError("CPT probabilistic parents cannot identify Raw Input nodes")
        if any(parent == self.child_node for parent in self.ordered_parent_nodes):
            raise ValueError("a CPT child cannot be its own probabilistic parent")

        _require_unique(self.child_state_ids, "CPT child state IDs")
        if len(self.ordered_parent_state_ids) != len(self.ordered_parent_nodes):
            raise ValueError("CPT parent state axes must align with ordered parent nodes")
        for state_ids in self.ordered_parent_state_ids:
            if len(state_ids) < 2:
                raise ValueError("each CPT parent state axis must contain at least two states")
            _require_unique(state_ids, "CPT parent state IDs")

        if self.mode is CptMode.INCOMPLETE and not self.materialized_probabilities:
            return self
        expected_rows = math.prod(len(states) for states in self.ordered_parent_state_ids)
        if not self.ordered_parent_state_ids:
            expected_rows = 1
        if len(self.materialized_probabilities) != expected_rows:
            raise ValueError(
                f"CPT row count must be {expected_rows} for the declared parent state axes"
            )
        for row in self.materialized_probabilities:
            if len(row) != len(self.child_state_ids):
                raise ValueError("each CPT row must align with the child state axis")
            if abs(math.fsum(row) - 1.0) > 1e-12:
                raise ValueError("each CPT probability row must sum to 1")
        return self


class RawInputNodeDefinition(StrictContractModel):
    definition_kind: Literal["raw_input"] = "raw_input"
    family: RawInputFamily | None
    resource_role: RawResourceRole
    source_descriptor: SourceDescriptor
    metadata: dict[str, JsonValue]
    help_text_zh: HumanText | None
    help_text_en: HumanText | None

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_family_and_role(self) -> Self:
        descriptor = self.source_descriptor
        if descriptor.kind is not SourceKind.RAW_STREAM:
            if self.family is not None:
                raise ValueError("typed session/task resources must not claim a raw-input family")
            if self.resource_role is RawResourceRole.STREAM:
                raise ValueError("only raw-stream descriptors may use the stream resource role")
            return self

        modality = descriptor.raw_modality
        if modality is None:
            raise ValueError("raw-stream descriptors must declare a physical modality")
        expected_family = {
            RawModality.X: RawInputFamily.X,
            RawModality.U: RawInputFamily.U,
            RawModality.I: RawInputFamily.I,
            RawModality.G: RawInputFamily.G,
            RawModality.EEG: RawInputFamily.P,
            RawModality.ECG: RawInputFamily.P,
            RawModality.PILOT_CAMERA: RawInputFamily.PILOT_CAMERA,
        }[modality]
        if self.resource_role is not RawResourceRole.STREAM:
            raise ValueError("raw-stream descriptors must use the stream resource role")
        if self.family is not expected_family:
            raise ValueError("raw-input family must match the exact physical modality")
        return self


class EvidenceNodeDefinition(StrictContractModel):
    definition_kind: Literal["evidence"] = "evidence"
    recipe: EvidenceRecipe
    data_bindings: tuple[EvidenceDataBinding, ...]
    ordered_observation_states: tuple[VariableState, ...] = Field(min_length=2)
    observation_mapping: dict[str, JsonValue]
    ordered_probabilistic_parent_nodes: tuple[ModelNodeRef, ...]
    cpt: NodeCpt
    observation_policy: ObservationPolicy
    modality_attribution_weights: dict[StableId, UnitInterval]
    scientific_status: ModelScientificStatus
    provenance: dict[str, JsonValue]
    help_text_zh: HumanText | None
    help_text_en: HumanText | None

    @field_validator("observation_mapping", "provenance")
    @classmethod
    def freeze_json_fields(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @field_validator("modality_attribution_weights")
    @classmethod
    def freeze_modality_weights(
        cls,
        value: dict[str, float],
    ) -> dict[str, UnitInterval]:
        if not value:
            raise ValueError("modality attribution weights must not be empty")
        allowed = {modality.value for modality in RawModality}
        if not set(value).issubset(allowed):
            raise ValueError("modality attribution weights contain an unknown raw modality")
        if abs(math.fsum(value.values()) - 1.0) > 1e-12:
            raise ValueError("modality attribution weights must sum to 1")
        frozen = _freeze_json_object(cast(dict[str, JsonValue], value))
        return cast(dict[str, UnitInterval], frozen)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        input_ids = tuple(item.binding_id for item in self.recipe.inputs)
        binding_ids = tuple(item.recipe_input_binding_id for item in self.data_bindings)
        _require_unique(input_ids, "recipe input binding IDs")
        _require_unique(binding_ids, "Evidence data binding IDs")
        if set(input_ids) != set(binding_ids):
            raise ValueError("Evidence data bindings must cover recipe input bindings exactly")

        state_ids = tuple(state.state_id for state in self.ordered_observation_states)
        _require_unique(state_ids, "Evidence observation state IDs")
        parent_keys = tuple(_ref_key(parent) for parent in self.ordered_probabilistic_parent_nodes)
        _require_unique(parent_keys, "Evidence probabilistic parent nodes")
        if any(
            parent.node_kind is not ModelNodeKind.BN
            for parent in self.ordered_probabilistic_parent_nodes
        ):
            raise ValueError("Evidence probabilistic parents must identify BN nodes")
        if self.cpt.child_node.node_kind is not ModelNodeKind.EVIDENCE:
            raise ValueError("Evidence CPT child must identify an Evidence node")
        if self.cpt.ordered_parent_nodes != self.ordered_probabilistic_parent_nodes:
            raise ValueError("Evidence CPT parent order must match probabilistic parent order")
        if self.cpt.child_state_ids != state_ids:
            raise ValueError("Evidence CPT child states must match observation state order")
        return self


class BnNodeDefinition(StrictContractModel):
    definition_kind: Literal["bn"] = "bn"
    node_role: BnNodeRole
    ordered_states: tuple[VariableState, ...] = Field(min_length=2)
    ordered_probabilistic_parent_nodes: tuple[ModelNodeRef, ...]
    cpt: NodeCpt
    documentation: HumanText
    scientific_status: ModelScientificStatus
    reporting_metadata: dict[str, JsonValue]
    provenance: dict[str, JsonValue]
    help_text_zh: HumanText | None
    help_text_en: HumanText | None

    @field_validator("reporting_metadata", "provenance")
    @classmethod
    def freeze_json_fields(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_bn_node(self) -> Self:
        state_ids = tuple(state.state_id for state in self.ordered_states)
        _require_unique(state_ids, "BN state IDs")
        parent_keys = tuple(_ref_key(parent) for parent in self.ordered_probabilistic_parent_nodes)
        _require_unique(parent_keys, "BN probabilistic parent nodes")
        if any(
            parent.node_kind is ModelNodeKind.RAW_INPUT
            for parent in self.ordered_probabilistic_parent_nodes
        ):
            raise ValueError("BN probabilistic parents cannot identify Raw Input nodes")
        if self.cpt.child_node.node_kind is not ModelNodeKind.BN:
            raise ValueError("BN CPT child must identify a BN node")
        if self.cpt.ordered_parent_nodes != self.ordered_probabilistic_parent_nodes:
            raise ValueError("BN CPT parent order must match probabilistic parent order")
        if self.cpt.child_state_ids != state_ids:
            raise ValueError("BN CPT child states must match BN state order")
        return self


ModelNodeDefinition = Annotated[
    RawInputNodeDefinition | EvidenceNodeDefinition | BnNodeDefinition,
    Field(discriminator="definition_kind"),
]


class ModelNode(StrictContractModel):
    contract_id: Literal["model-node"] = "model-node"
    contract_version: Literal["0.1.0"] = "0.1.0"
    node_id: StableId
    node_kind: ModelNodeKind
    name_zh: HumanLabel | None
    name_en: HumanLabel | None
    short_name_zh: ShortLabel | None
    short_name_en: ShortLabel | None
    description_zh: HumanText | None
    description_en: HumanText | None
    tags: tuple[StableId, ...]
    group: StableId | None
    lifecycle: ModelObjectLifecycle
    copied_from_node_id: StableId | None
    definition: ModelNodeDefinition
    global_layout: NodeLayout
    semantic_revision: NonNegativeInt
    layout_revision: NonNegativeInt
    technical_status: ModelTechnicalStatus
    diagnostics: tuple[ModelDiagnostic, ...]
    content_hash: Sha256Digest
    layout_hash: Sha256Digest
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_canonical_set(value, "node tags")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc_datetime(value)

    @model_validator(mode="after")
    def validate_complete_node(self) -> Self:
        _require_localized_pair(self.name_zh, self.name_en, "node name")
        _require_localized_pair(self.short_name_zh, self.short_name_en, "node short name")
        _require_localized_pair(
            self.description_zh,
            self.description_en,
            "node description",
        )
        if self.node_kind.value != self.definition.definition_kind:
            raise ValueError("node kind must match its discriminated complete definition")
        if self.global_layout.node_id != self.node_id:
            raise ValueError("global layout node ID must match node identity")
        if self.copied_from_node_id == self.node_id:
            raise ValueError("a copied node cannot identify itself as its source")
        if self.updated_at < self.created_at:
            raise ValueError("node updated_at cannot precede created_at")

        if isinstance(self.definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            expected_child = ModelNodeRef(node_id=self.node_id, node_kind=self.node_kind)
            if self.definition.cpt.child_node != expected_child:
                raise ValueError("embedded CPT child must match the complete node identity")
            if any(
                parent.node_id == self.node_id
                for parent in self.definition.ordered_probabilistic_parent_nodes
            ):
                raise ValueError("a node cannot be its own probabilistic parent")
        return self


class TaskScheme(StrictContractModel):
    contract_id: Literal["task-scheme"] = "task-scheme"
    contract_version: Literal["0.1.0"] = "0.1.0"
    scheme_id: StableId
    name_zh: HumanLabel | None
    name_en: HumanLabel | None
    description_zh: HumanText | None
    description_en: HumanText | None
    tags: tuple[StableId, ...]
    group: StableId | None
    lifecycle: ModelObjectLifecycle
    copied_from_scheme_id: StableId | None
    explicit_active_node_ids: tuple[StableId, ...]
    computed_active_closure: tuple[StableId, ...]
    output_node_ids: tuple[StableId, ...]
    task_bindings: dict[str, JsonValue]
    layout_overrides: tuple[NodeLayout, ...]
    semantic_revision: NonNegativeInt
    layout_revision: NonNegativeInt
    technical_status: ModelTechnicalStatus
    diagnostics: tuple[ModelDiagnostic, ...]
    content_hash: Sha256Digest
    layout_hash: Sha256Digest
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("task_bindings")
    @classmethod
    def freeze_task_bindings(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_canonical_set(value, "scheme tags")
        return value

    @field_validator("explicit_active_node_ids", "computed_active_closure")
    @classmethod
    def validate_canonical_node_sets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_canonical_set(value, "scheme activation node IDs")
        return value

    @field_validator("output_node_ids")
    @classmethod
    def validate_canonical_outputs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_canonical_set(value, "scheme output node IDs")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc_datetime(value)

    @model_validator(mode="after")
    def validate_scheme(self) -> Self:
        _require_localized_pair(self.name_zh, self.name_en, "scheme name")
        _require_localized_pair(
            self.description_zh,
            self.description_en,
            "scheme description",
        )
        _require_unique(self.output_node_ids, "scheme output node IDs")
        closure = set(self.computed_active_closure)
        if not set(self.explicit_active_node_ids).issubset(closure):
            raise ValueError("explicit active nodes must be contained in computed closure")
        if not set(self.output_node_ids).issubset(closure):
            raise ValueError("scheme output nodes must be active in computed closure")
        layout_ids = tuple(layout.node_id for layout in self.layout_overrides)
        _require_unique(layout_ids, "scheme layout override node IDs")
        if layout_ids != tuple(sorted(layout_ids)):
            raise ValueError("scheme layout overrides must use canonical node order")
        if self.copied_from_scheme_id == self.scheme_id:
            raise ValueError("a copied scheme cannot identify itself as its source")
        if self.updated_at < self.created_at:
            raise ValueError("scheme updated_at cannot precede created_at")
        return self


class ModelGraphEdge(StrictContractModel):
    edge_id: StableId
    edge_kind: ModelGraphEdgeKind
    parent: ModelNodeRef
    child: ModelNodeRef
    recipe_input_binding_id: StableId | None

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        if self.parent == self.child:
            raise ValueError("a graph edge cannot be a self-edge")
        if self.edge_kind is ModelGraphEdgeKind.EXTRACTION:
            if self.parent.node_kind is not ModelNodeKind.RAW_INPUT:
                raise ValueError("extraction edge parent must identify a Raw Input node")
            if self.child.node_kind is not ModelNodeKind.EVIDENCE:
                raise ValueError("extraction edge child must identify an Evidence node")
            if self.recipe_input_binding_id is None:
                raise ValueError("extraction edges require a recipe input binding ID")
        else:
            if self.parent.node_kind is ModelNodeKind.RAW_INPUT:
                raise ValueError("probabilistic edge parent cannot identify Raw Input")
            if self.child.node_kind is ModelNodeKind.RAW_INPUT:
                raise ValueError("probabilistic edge child cannot identify Raw Input")
            if self.recipe_input_binding_id is not None:
                raise ValueError("probabilistic edges cannot identify recipe input bindings")
        return self


class ModelGraphSnapshot(StrictContractModel):
    contract_id: Literal["model-graph-snapshot"] = "model-graph-snapshot"
    contract_version: Literal["0.1.0"] = "0.1.0"
    project_id: StableId
    scheme: TaskScheme
    nodes: tuple[ModelNode, ...]
    edges: tuple[ModelGraphEdge, ...]
    generated_at: AwareDatetime
    graph_hash: Sha256Digest

    @field_validator("generated_at")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc_datetime(value)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        node_ids = tuple(node.node_id for node in self.nodes)
        _require_unique(node_ids, "graph node IDs")
        if node_ids != tuple(sorted(node_ids)):
            raise ValueError("graph nodes must use canonical node order")
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        _require_unique(edge_ids, "graph edge IDs")
        if edge_ids != tuple(sorted(edge_ids)):
            raise ValueError("graph edges must use canonical edge order")

        nodes = {node.node_id: node for node in self.nodes}
        if not set(self.scheme.computed_active_closure).issubset(nodes):
            raise ValueError("scheme active closure must resolve within graph nodes")
        for edge in self.edges:
            parent = nodes.get(edge.parent.node_id)
            child = nodes.get(edge.child.node_id)
            if parent is None or child is None:
                raise ValueError("graph edge endpoints must resolve within graph nodes")
            if parent.node_kind is not edge.parent.node_kind:
                raise ValueError("graph edge parent kind must match referenced node")
            if child.node_kind is not edge.child.node_kind:
                raise ValueError("graph edge child kind must match referenced node")
        return self


class CanonicalModelDiff(StrictContractModel):
    changed_paths: tuple[JsonPointer, ...]
    added_node_ids: tuple[StableId, ...]
    removed_node_ids: tuple[StableId, ...]
    added_edge_ids: tuple[StableId, ...]
    removed_edge_ids: tuple[StableId, ...]
    metadata: dict[str, JsonValue]

    @field_validator(
        "changed_paths",
        "added_node_ids",
        "removed_node_ids",
        "added_edge_ids",
        "removed_edge_ids",
    )
    @classmethod
    def validate_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "canonical diff values")
        return value

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class DeactivationImpact(StrictContractModel):
    contract_id: Literal["deactivation-impact"] = "deactivation-impact"
    contract_version: Literal["0.1.0"] = "0.1.0"
    scheme_id: StableId
    scheme_semantic_revision: NonNegativeInt
    requested_node_id: StableId
    impacted_node_ids: tuple[StableId, ...]
    impacted_edge_ids: tuple[StableId, ...]
    impact_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_impact(self) -> Self:
        _require_canonical_set(self.impacted_node_ids, "impacted node IDs")
        _require_canonical_set(self.impacted_edge_ids, "impacted edge IDs")
        if self.requested_node_id not in self.impacted_node_ids:
            raise ValueError("deactivation impact must contain the requested node")
        return self


class ModelChangeEvent(StrictContractModel):
    contract_id: Literal["model-change-event"] = "model-change-event"
    contract_version: Literal["0.1.0"] = "0.1.0"
    event_id: StableId
    object_kind: ModelObjectKind
    object_id: StableId
    event_kind: ModelChangeKind
    parent_event_id: StableId | None
    semantic_revision: NonNegativeInt
    layout_revision: NonNegativeInt
    before_hash: Sha256Digest | None
    after_hash: Sha256Digest | None
    diff: CanonicalModelDiff
    transaction_id: StableId
    actor_id: StableId
    occurred_at: AwareDatetime

    @field_validator("occurred_at")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc_datetime(value)

    @model_validator(mode="after")
    def validate_hash_transition(self) -> Self:
        if self.event_kind is ModelChangeKind.CREATE and self.before_hash is not None:
            raise ValueError("create events cannot have a before hash")
        if self.event_kind is not ModelChangeKind.CREATE and self.before_hash is None:
            raise ValueError("non-create events require a before hash")
        if self.after_hash is None and self.event_kind is not ModelChangeKind.ARCHIVE:
            raise ValueError("only archive events may omit an after hash")
        return self


__all__ = [
    "BnNodeDefinition",
    "CanonicalModelDiff",
    "DeactivationImpact",
    "EvidenceDataBinding",
    "EvidenceNodeDefinition",
    "ModelChangeEvent",
    "ModelChangeKind",
    "ModelDiagnostic",
    "ModelDiagnosticSeverity",
    "ModelGraphEdge",
    "ModelGraphEdgeKind",
    "ModelGraphSnapshot",
    "ModelNode",
    "ModelNodeDefinition",
    "ModelNodeKind",
    "ModelNodeRef",
    "ModelObjectKind",
    "ModelObjectLifecycle",
    "ModelTechnicalStatus",
    "NodeCpt",
    "NodeLayout",
    "RawInputFamily",
    "RawInputNodeDefinition",
    "RawResourceRole",
    "TaskScheme",
]
