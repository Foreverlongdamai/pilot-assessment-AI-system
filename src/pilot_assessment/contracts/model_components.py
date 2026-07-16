"""Public contracts for the shared immutable model-component library."""

from __future__ import annotations

import math
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
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
    freeze_json_mapping,
)
from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe, PortType

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
HumanText = Annotated[str, StringConstraints(max_length=8000)]


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_finite_json(value: JsonValue) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("JSON object keys must be strings")
            _require_finite_json(nested)
    elif isinstance(value, list):
        for nested in value:
            _require_finite_json(nested)


def _freeze_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    _require_finite_json(value)
    return freeze_json_mapping(value)


class ComponentKind(StrEnum):
    EVIDENCE_CONCEPT = "evidence_concept"
    EVIDENCE_VERSION = "evidence_version"
    BN_NODE_CONCEPT = "bn_node_concept"
    BN_NODE_VERSION = "bn_node_version"
    EVIDENCE_BINDING_VERSION = "evidence_binding_version"
    CPT_VERSION = "cpt_version"
    TASK_PROFILE_VERSION = "task_profile_version"
    COVERAGE_REPORTING_POLICY_VERSION = "coverage_reporting_policy_version"
    LAYOUT_VERSION = "layout_version"
    ASSESSMENT_SCHEME_VERSION = "assessment_scheme_version"
    SOURCE_DESCRIPTOR = "source_descriptor"


class ComponentLifecycle(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    RETIRED = "retired"


class ModelScientificStatus(StrEnum):
    STARTER_TEMPLATE = "starter_template"
    ENGINEERING_DEFAULT = "engineering_default"
    EXPERT_DEFINED = "expert_defined"
    CALIBRATED = "calibrated"


class ComponentSource(StrEnum):
    ENGINEERING_DEFAULT = "engineering_default"
    EXPERT_DEFINED = "expert_defined"
    CALIBRATED = "calibrated"
    IMPORTED = "imported"


class BnNodeRole(StrEnum):
    AGGREGATE_COMPETENCY = "aggregate_competency"
    SUB_SKILL = "sub_skill"
    LATENT = "latent"
    DERIVED = "derived"
    CUSTOM = "custom"


class ObservationPolicy(StrEnum):
    HARD = "hard"
    VIRTUAL = "virtual"
    HARD_OR_VIRTUAL = "hard_or_virtual"


class CptMode(StrEnum):
    MANUAL = "manual"
    GENERATED = "generated"
    INCOMPLETE = "incomplete"


class SourceKind(StrEnum):
    RAW_STREAM = "raw_stream"
    SESSION_SEMANTIC = "session_semantic"
    TASK_SEMANTIC = "task_semantic"
    DERIVED_ARTIFACT = "derived_artifact"
    EVIDENCE_OBSERVATION = "evidence_observation"


class RawModality(StrEnum):
    X = "X"
    U = "U"
    I = "I"  # noqa: E741 - canonical raw-stream identifier
    G = "G"
    EEG = "EEG"
    ECG = "ECG"
    PILOT_CAMERA = "pilot_camera"


VARIABLE_COMPONENT_KINDS = frozenset(
    {ComponentKind.BN_NODE_VERSION, ComponentKind.EVIDENCE_BINDING_VERSION}
)


class ComponentIdRef(StrictContractModel):
    """An internal exact ID reference without a recursive content hash."""

    kind: ComponentKind
    version_id: StableId


class PinnedComponentRef(StrictContractModel):
    """An external replay pin binding an exact ID to its canonical content."""

    kind: ComponentKind
    version_id: StableId
    content_hash: Sha256Digest


class VersionLineage(StrictContractModel):
    source_version_ids: tuple[StableId, ...]
    created_at: AwareDatetime
    created_by: StableId
    note: HumanText | None

    @field_validator("source_version_ids")
    @classmethod
    def validate_source_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "source version IDs")
        return value


class VariableState(StrictContractModel):
    state_id: StableId
    label: HumanLabel
    description: HumanText


class EvidenceConcept(StrictContractModel):
    contract_id: Literal["evidence-concept"] = "evidence-concept"
    contract_version: Literal["0.1.0"] = "0.1.0"
    concept_id: StableId
    name: HumanLabel
    description: HumanText
    tags: tuple[StableId, ...]
    lifecycle: ComponentLifecycle

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "tags")
        return value


class EvidenceVersion(StrictContractModel):
    contract_id: Literal["evidence-version"] = "evidence-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    evidence_version_id: StableId
    concept_id: StableId
    recipe: EvidenceRecipe
    scientific_status: ModelScientificStatus
    lineage: VersionLineage
    content_hash: Sha256Digest


class BnNodeConcept(StrictContractModel):
    contract_id: Literal["bn-node-concept"] = "bn-node-concept"
    contract_version: Literal["0.1.0"] = "0.1.0"
    concept_id: StableId
    name: HumanLabel
    description: HumanText
    node_role: BnNodeRole
    tags: tuple[StableId, ...]
    lifecycle: ComponentLifecycle

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "tags")
        return value


class BnNodeVersion(StrictContractModel):
    contract_id: Literal["bn-node-version"] = "bn-node-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    bn_node_version_id: StableId
    concept_id: StableId
    ordered_states: tuple[VariableState, ...] = Field(min_length=2)
    ordered_probabilistic_parent_ids: tuple[ComponentIdRef, ...]
    cpt_version_id: ComponentIdRef
    documentation: HumanText
    scientific_status: ModelScientificStatus
    lineage: VersionLineage
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_node(self) -> Self:
        _require_unique(tuple(state.state_id for state in self.ordered_states), "state IDs")
        parent_keys = tuple(
            f"{parent.kind.value}:{parent.version_id}"
            for parent in self.ordered_probabilistic_parent_ids
        )
        _require_unique(parent_keys, "probabilistic parent IDs")
        if any(
            parent.kind not in VARIABLE_COMPONENT_KINDS
            for parent in self.ordered_probabilistic_parent_ids
        ):
            raise ValueError("probabilistic parent references must identify BN variables")
        if any(
            parent.kind is ComponentKind.BN_NODE_VERSION
            and parent.version_id == self.bn_node_version_id
            for parent in self.ordered_probabilistic_parent_ids
        ):
            raise ValueError("a BN node cannot be its own probabilistic parent")
        if self.cpt_version_id.kind is not ComponentKind.CPT_VERSION:
            raise ValueError("cpt_version_id must identify a CPT version")
        return self


class EvidenceBindingVersion(StrictContractModel):
    contract_id: Literal["evidence-binding-version"] = "evidence-binding-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    evidence_binding_version_id: StableId
    evidence_version_id: ComponentIdRef
    ordered_observation_states: tuple[VariableState, ...] = Field(min_length=2)
    observation_mapping: dict[str, JsonValue]
    ordered_probabilistic_parent_ids: tuple[ComponentIdRef, ...]
    cpt_version_id: ComponentIdRef
    observation_policy: ObservationPolicy
    modality_attribution_weights: dict[StableId, UnitInterval]
    lineage: VersionLineage
    content_hash: Sha256Digest

    @field_validator("observation_mapping")
    @classmethod
    def freeze_observation_mapping(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
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
    def validate_binding(self) -> Self:
        if self.evidence_version_id.kind is not ComponentKind.EVIDENCE_VERSION:
            raise ValueError("evidence_version_id must identify an Evidence version")
        _require_unique(
            tuple(state.state_id for state in self.ordered_observation_states),
            "observation state IDs",
        )
        parent_keys = tuple(
            f"{parent.kind.value}:{parent.version_id}"
            for parent in self.ordered_probabilistic_parent_ids
        )
        _require_unique(parent_keys, "probabilistic parent IDs")
        if any(
            parent.kind is not ComponentKind.BN_NODE_VERSION
            for parent in self.ordered_probabilistic_parent_ids
        ):
            raise ValueError("Evidence probabilistic parents must identify BN node versions")
        if self.cpt_version_id.kind is not ComponentKind.CPT_VERSION:
            raise ValueError("cpt_version_id must identify a CPT version")
        return self


class CptVersion(StrictContractModel):
    contract_id: Literal["cpt-version"] = "cpt-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    cpt_version_id: StableId
    child_variable_id: ComponentIdRef
    ordered_parent_variable_ids: tuple[ComponentIdRef, ...]
    child_state_ids: tuple[StableId, ...] = Field(min_length=2)
    ordered_parent_state_ids: tuple[tuple[StableId, ...], ...]
    materialized_probabilities: tuple[tuple[UnitInterval, ...], ...]
    mode: CptMode
    generator_metadata: dict[str, JsonValue]
    source: ComponentSource
    lineage: VersionLineage
    content_hash: Sha256Digest

    @field_validator("generator_metadata")
    @classmethod
    def freeze_generator_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_identity_shape(self) -> Self:
        if self.child_variable_id.kind not in VARIABLE_COMPONENT_KINDS:
            raise ValueError("child variable must identify a BN variable")
        _require_unique(self.child_state_ids, "child state IDs")
        parent_keys = tuple(
            f"{parent.kind.value}:{parent.version_id}"
            for parent in self.ordered_parent_variable_ids
        )
        _require_unique(parent_keys, "parent variable IDs")
        if any(
            parent.kind not in VARIABLE_COMPONENT_KINDS
            for parent in self.ordered_parent_variable_ids
        ):
            raise ValueError("parent variable references must identify BN variables")
        if len(self.ordered_parent_state_ids) != len(self.ordered_parent_variable_ids):
            raise ValueError("parent state spaces must align with ordered parent variables")
        for state_ids in self.ordered_parent_state_ids:
            if len(state_ids) < 2:
                raise ValueError("each parent state space must contain at least two states")
            _require_unique(state_ids, "parent state IDs")
        return self


class SourceDescriptor(StrictContractModel):
    contract_id: Literal["source-descriptor"] = "source-descriptor"
    contract_version: Literal["0.1.0"] = "0.1.0"
    source_id: StableId
    kind: SourceKind
    name: HumanLabel
    description: HumanText
    declared_type: PortType
    raw_modality: RawModality | None
    source_dependencies: tuple[StableId, ...]
    metadata: dict[str, JsonValue]
    content_hash: Sha256Digest

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_descriptor_shape(self) -> Self:
        _require_unique(self.source_dependencies, "source dependencies")
        if self.source_id in self.source_dependencies:
            raise ValueError("a source descriptor cannot depend on itself")
        if self.kind is SourceKind.RAW_STREAM and self.raw_modality is None:
            raise ValueError("raw_stream descriptors require raw_modality")
        if self.kind is not SourceKind.RAW_STREAM and self.raw_modality is not None:
            raise ValueError("only raw_stream descriptors may declare raw_modality")
        return self


__all__ = [
    "BnNodeConcept",
    "BnNodeRole",
    "BnNodeVersion",
    "ComponentIdRef",
    "ComponentKind",
    "ComponentLifecycle",
    "ComponentSource",
    "CptMode",
    "CptVersion",
    "EvidenceBindingVersion",
    "EvidenceConcept",
    "EvidenceVersion",
    "ModelScientificStatus",
    "ObservationPolicy",
    "PinnedComponentRef",
    "RawModality",
    "SourceDescriptor",
    "SourceKind",
    "VARIABLE_COMPONENT_KINDS",
    "VariableState",
    "VersionLineage",
]
