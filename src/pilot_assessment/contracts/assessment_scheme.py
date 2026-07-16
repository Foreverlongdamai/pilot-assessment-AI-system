"""Public contracts for task schemes, graph layout, and editable drafts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import JsonValue, StringConstraints, field_validator, model_validator

from pilot_assessment.contracts.bayesian import BayesianDependencyEdge, ExtractionEdge
from pilot_assessment.contracts.common import (
    FiniteFloat,
    NonNegativeInt,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
    freeze_json_mapping,
)
from pilot_assessment.contracts.model_components import (
    VARIABLE_COMPONENT_KINDS,
    ComponentIdRef,
    ComponentKind,
    ComponentSource,
    PinnedComponentRef,
    VersionLineage,
)

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
HumanText = Annotated[str, StringConstraints(max_length=8000)]
JsonPointer = Annotated[str, StringConstraints(min_length=1, max_length=2048)]


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


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


def _pinned_key(reference: PinnedComponentRef) -> str:
    return f"{reference.kind.value}:{reference.version_id}"


def _require_kind(
    reference: PinnedComponentRef,
    expected: ComponentKind,
    label: str,
) -> None:
    if reference.kind is not expected:
        raise ValueError(f"{label} must identify {expected.value}")


class TaskProfileVersion(StrictContractModel):
    contract_id: Literal["task-profile-version"] = "task-profile-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    task_profile_version_id: StableId
    task_concept_id: StableId
    name: HumanLabel
    description: HumanText
    task_semantics: dict[str, JsonValue]
    required_source_descriptor_ids: tuple[StableId, ...]
    reference_parameters: dict[str, JsonValue]
    annotation_parameters: dict[str, JsonValue]
    aoi_parameters: dict[str, JsonValue]
    source: ComponentSource
    lineage: VersionLineage
    content_hash: Sha256Digest

    @field_validator(
        "task_semantics",
        "reference_parameters",
        "annotation_parameters",
        "aoi_parameters",
    )
    @classmethod
    def freeze_json_fields(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @field_validator("required_source_descriptor_ids")
    @classmethod
    def validate_source_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "required source descriptor IDs")
        return value


class CoverageReportingPolicyVersion(StrictContractModel):
    contract_id: Literal["coverage-reporting-policy-version"] = "coverage-reporting-policy-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    policy_version_id: StableId
    applicability_rules: dict[str, JsonValue]
    coverage_rules: dict[str, JsonValue]
    output_rules: dict[str, JsonValue]
    source: ComponentSource
    lineage: VersionLineage
    content_hash: Sha256Digest

    @field_validator("applicability_rules", "coverage_rules", "output_rules")
    @classmethod
    def freeze_json_fields(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class NodePosition(StrictContractModel):
    node_id: StableId
    x: FiniteFloat
    y: FiniteFloat


class LayoutGroup(StrictContractModel):
    group_id: StableId
    label: HumanLabel
    node_ids: tuple[StableId, ...]
    metadata: dict[str, JsonValue]

    @field_validator("node_ids")
    @classmethod
    def validate_node_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "layout group node IDs")
        return value

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class Viewport(StrictContractModel):
    x: FiniteFloat
    y: FiniteFloat
    zoom: PositiveFiniteFloat


class LayoutVersion(StrictContractModel):
    contract_id: Literal["layout-version"] = "layout-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    layout_version_id: StableId
    node_positions: tuple[NodePosition, ...]
    groups: tuple[LayoutGroup, ...]
    viewport: Viewport
    lineage: VersionLineage
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_layout(self) -> Self:
        _require_unique(
            tuple(position.node_id for position in self.node_positions),
            "layout position node IDs",
        )
        _require_unique(tuple(group.group_id for group in self.groups), "layout group IDs")
        return self


class AssessmentSchemeVersion(StrictContractModel):
    contract_id: Literal["assessment-scheme-version"] = "assessment-scheme-version"
    contract_version: Literal["0.1.0"] = "0.1.0"
    scheme_version_id: StableId
    scheme_concept_id: StableId
    name: HumanLabel
    description: HumanText
    task_profile: PinnedComponentRef
    source_descriptors: tuple[PinnedComponentRef, ...]
    evidence_versions: tuple[PinnedComponentRef, ...]
    evidence_binding_versions: tuple[PinnedComponentRef, ...]
    bn_node_versions: tuple[PinnedComponentRef, ...]
    cpt_versions: tuple[PinnedComponentRef, ...]
    reporting_policy: PinnedComponentRef
    layout: PinnedComponentRef
    output_node_ids: tuple[ComponentIdRef, ...]
    lineage: VersionLineage
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_scheme(self) -> Self:
        _require_kind(
            self.task_profile,
            ComponentKind.TASK_PROFILE_VERSION,
            "task profile",
        )
        _require_kind(
            self.reporting_policy,
            ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
            "reporting policy",
        )
        _require_kind(self.layout, ComponentKind.LAYOUT_VERSION, "layout")
        for label, references, expected in (
            ("source descriptors", self.source_descriptors, ComponentKind.SOURCE_DESCRIPTOR),
            ("Evidence versions", self.evidence_versions, ComponentKind.EVIDENCE_VERSION),
            (
                "Evidence binding versions",
                self.evidence_binding_versions,
                ComponentKind.EVIDENCE_BINDING_VERSION,
            ),
            ("BN node versions", self.bn_node_versions, ComponentKind.BN_NODE_VERSION),
            ("CPT versions", self.cpt_versions, ComponentKind.CPT_VERSION),
        ):
            _require_unique(tuple(_pinned_key(item) for item in references), label)
            for reference in references:
                _require_kind(reference, expected, label)
        output_keys = tuple(
            f"{reference.kind.value}:{reference.version_id}" for reference in self.output_node_ids
        )
        _require_unique(output_keys, "output node IDs")
        if any(
            reference.kind not in VARIABLE_COMPONENT_KINDS for reference in self.output_node_ids
        ):
            raise ValueError("output node IDs must identify BN variables")
        return self


class DraftDiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DraftValidationState(StrEnum):
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    EXECUTABLE = "executable"


class DraftDiagnostic(StrictContractModel):
    code: StableId
    severity: DraftDiagnosticSeverity
    location: JsonPointer
    component_id: StableId | None
    message: HumanLabel


class DraftComponentCandidate(StrictContractModel):
    kind: ComponentKind
    candidate_id: StableId
    base_version_id: StableId | None
    payload: dict[str, JsonValue]

    @field_validator("payload")
    @classmethod
    def freeze_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class SchemeDraft(StrictContractModel):
    contract_id: Literal["scheme-draft"] = "scheme-draft"
    contract_version: Literal["0.1.0"] = "0.1.0"
    draft_id: StableId
    base_scheme_version_id: StableId | None
    graph_version: NonNegativeInt
    layout_version: NonNegativeInt
    history_cursor: NonNegativeInt
    retained_component_refs: tuple[PinnedComponentRef, ...]
    candidate_components: tuple[DraftComponentCandidate, ...]
    extraction_edges: tuple[ExtractionEdge, ...]
    bayesian_edges: tuple[BayesianDependencyEdge, ...]
    output_node_ids: tuple[ComponentIdRef, ...]
    validation_state: DraftValidationState
    diagnostics: tuple[DraftDiagnostic, ...]

    @model_validator(mode="after")
    def validate_draft_identity(self) -> Self:
        _require_unique(
            tuple(_pinned_key(item) for item in self.retained_component_refs),
            "retained component refs",
        )
        _require_unique(
            tuple(item.candidate_id for item in self.candidate_components),
            "candidate component IDs",
        )
        edge_ids = tuple(edge.edge_id for edge in self.extraction_edges) + tuple(
            edge.edge_id for edge in self.bayesian_edges
        )
        _require_unique(edge_ids, "draft edge IDs")
        output_keys = tuple(
            f"{reference.kind.value}:{reference.version_id}" for reference in self.output_node_ids
        )
        _require_unique(output_keys, "draft output node IDs")
        if any(
            reference.kind not in VARIABLE_COMPONENT_KINDS for reference in self.output_node_ids
        ):
            raise ValueError("draft output node IDs must identify BN variables")
        return self


__all__ = [
    "AssessmentSchemeVersion",
    "CoverageReportingPolicyVersion",
    "DraftComponentCandidate",
    "DraftDiagnostic",
    "DraftDiagnosticSeverity",
    "DraftValidationState",
    "LayoutGroup",
    "LayoutVersion",
    "NodePosition",
    "SchemeDraft",
    "TaskProfileVersion",
    "Viewport",
]
