"""Frozen readers for bilingual M7 current-model payloads.

These contracts preserve the exact v0.1 node/scheme shape embedded in historical
v0.1/v0.2 run snapshots.  New mutable model content must use
``pilot_assessment.contracts.model_workspace`` instead.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
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
    ModelScientificStatus,
    ObservationPolicy,
    RawModality,
    SourceDescriptor,
    SourceKind,
    VariableState,
)
from pilot_assessment.contracts.model_workspace import (
    EvidenceDataBinding,
    ModelDiagnostic,
    ModelGraphEdge,
    ModelNodeKind,
    ModelNodeRef,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeCpt,
    NodeLayout,
    RawInputFamily,
    RawResourceRole,
)

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
ShortLabel = Annotated[str, StringConstraints(min_length=1, max_length=96)]
HumanText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]


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


def _require_localized_pair(first: str | None, second: str | None, label: str) -> None:
    if first is None and second is None:
        raise ValueError(f"{label} requires at least one localized value")


def _require_utc_datetime(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC offset +00:00")
    return value


class LegacyRawInputNodeDefinitionV010(StrictContractModel):
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


class LegacyEvidenceNodeDefinitionV010(StrictContractModel):
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
    def freeze_modality_weights(cls, value: dict[str, float]) -> dict[str, UnitInterval]:
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


class LegacyBnNodeDefinitionV010(StrictContractModel):
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


LegacyModelNodeDefinitionV010 = Annotated[
    LegacyRawInputNodeDefinitionV010
    | LegacyEvidenceNodeDefinitionV010
    | LegacyBnNodeDefinitionV010,
    Field(discriminator="definition_kind"),
]


class LegacyModelNodeV010(StrictContractModel):
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
    definition: LegacyModelNodeDefinitionV010
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
        _require_localized_pair(self.description_zh, self.description_en, "node description")
        if self.node_kind.value != self.definition.definition_kind:
            raise ValueError("node kind must match its discriminated complete definition")
        if self.global_layout.node_id != self.node_id:
            raise ValueError("global layout node ID must match node identity")
        if self.copied_from_node_id == self.node_id:
            raise ValueError("a copied node cannot identify itself as its source")
        if self.updated_at < self.created_at:
            raise ValueError("node updated_at cannot precede created_at")

        if isinstance(
            self.definition,
            (LegacyEvidenceNodeDefinitionV010, LegacyBnNodeDefinitionV010),
        ):
            expected_child = ModelNodeRef(node_id=self.node_id, node_kind=self.node_kind)
            if self.definition.cpt.child_node != expected_child:
                raise ValueError("embedded CPT child must match the complete node identity")
            if any(
                parent.node_id == self.node_id
                for parent in self.definition.ordered_probabilistic_parent_nodes
            ):
                raise ValueError("a node cannot be its own probabilistic parent")
        return self


class LegacyTaskSchemeV010(StrictContractModel):
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
        _require_localized_pair(self.description_zh, self.description_en, "scheme description")
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


class LegacyModelGraphSnapshotV020(StrictContractModel):
    contract_id: Literal["model-graph-snapshot"] = "model-graph-snapshot"
    contract_version: Literal["0.2.0"] = "0.2.0"
    model_library_id: StableId
    scheme: LegacyTaskSchemeV010
    nodes: tuple[LegacyModelNodeV010, ...]
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


__all__ = [
    "LegacyBnNodeDefinitionV010",
    "LegacyEvidenceNodeDefinitionV010",
    "LegacyModelGraphSnapshotV020",
    "LegacyModelNodeDefinitionV010",
    "LegacyModelNodeV010",
    "LegacyRawInputNodeDefinitionV010",
    "LegacyTaskSchemeV010",
]
