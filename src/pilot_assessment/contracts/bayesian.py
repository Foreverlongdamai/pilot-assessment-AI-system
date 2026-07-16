"""Transport-neutral contracts for editable Bayesian models and inference."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pilot_assessment.contracts.common import (
    NonNegativeFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.model_components import (
    VARIABLE_COMPONENT_KINDS,
    ComponentIdRef,
    ComponentKind,
    PinnedComponentRef,
    VariableState,
)

InfluenceDelta = Annotated[
    float,
    Field(strict=True, ge=0.0, le=2.0, allow_inf_nan=False),
]


def _ref_key(reference: ComponentIdRef | PinnedComponentRef) -> str:
    return f"{reference.kind.value}:{reference.version_id}"


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


def _require_variable(reference: ComponentIdRef, label: str) -> None:
    if reference.kind not in VARIABLE_COMPONENT_KINDS:
        raise ValueError(f"{label} must identify a BN variable")


class ExtractionEdge(StrictContractModel):
    edge_kind: Literal["extraction"] = "extraction"
    edge_id: StableId
    source_descriptor_id: StableId
    target_evidence_version_id: StableId
    input_binding_id: StableId


class BayesianDependencyEdge(StrictContractModel):
    edge_kind: Literal["bayesian_dependency"] = "bayesian_dependency"
    edge_id: StableId
    parent_variable_id: ComponentIdRef
    child_variable_id: ComponentIdRef

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        _require_variable(self.parent_variable_id, "parent variable")
        _require_variable(self.child_variable_id, "child variable")
        if self.parent_variable_id == self.child_variable_id:
            raise ValueError("a Bayesian dependency cannot be a self edge")
        return self


class InferenceInfluenceEdge(StrictContractModel):
    edge_kind: Literal["inference_influence"] = "inference_influence"
    edge_id: StableId
    observed_variable_id: ComponentIdRef
    queried_variable_id: ComponentIdRef
    method_id: Literal["leave-one-observation-out-v1"]
    l1_delta: InfluenceDelta
    canonical_path: tuple[StableId, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        _require_variable(self.observed_variable_id, "observed variable")
        _require_variable(self.queried_variable_id, "queried variable")
        if self.canonical_path[0] != self.observed_variable_id.version_id:
            raise ValueError("canonical influence path must start at the observed variable")
        if self.canonical_path[-1] != self.queried_variable_id.version_id:
            raise ValueError("canonical influence path must end at the queried variable")
        return self


class InferenceVariable(StrictContractModel):
    variable_id: ComponentIdRef
    ordered_states: tuple[VariableState, ...] = Field(min_length=2)
    ordered_parent_ids: tuple[ComponentIdRef, ...]
    cpt_ref: PinnedComponentRef

    @model_validator(mode="after")
    def validate_variable(self) -> Self:
        _require_variable(self.variable_id, "variable_id")
        _require_unique(tuple(state.state_id for state in self.ordered_states), "state IDs")
        _require_unique(tuple(_ref_key(parent) for parent in self.ordered_parent_ids), "parent IDs")
        for parent in self.ordered_parent_ids:
            _require_variable(parent, "parent variable")
        if self.variable_id in self.ordered_parent_ids:
            raise ValueError("a variable cannot be its own parent")
        if self.cpt_ref.kind is not ComponentKind.CPT_VERSION:
            raise ValueError("cpt_ref must identify a CPT version")
        return self


class InferencePlan(StrictContractModel):
    contract_id: Literal["inference-plan"] = "inference-plan"
    contract_version: Literal["0.1.0"] = "0.1.0"
    plan_id: StableId
    scheme_ref: PinnedComponentRef
    variables: tuple[InferenceVariable, ...] = Field(min_length=1)
    queryable_variable_ids: tuple[ComponentIdRef, ...]
    component_refs: tuple[PinnedComponentRef, ...]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        variable_keys = tuple(_ref_key(variable.variable_id) for variable in self.variables)
        _require_unique(variable_keys, "variable IDs")
        query_keys = tuple(_ref_key(reference) for reference in self.queryable_variable_ids)
        _require_unique(query_keys, "queryable variable IDs")
        for reference in self.queryable_variable_ids:
            _require_variable(reference, "queryable variable")
        if not set(query_keys).issubset(variable_keys):
            raise ValueError("queryable variables must exist in the inference plan")
        _require_unique(
            tuple(_ref_key(reference) for reference in self.component_refs),
            "component refs",
        )
        return self


class ObservationKind(StrEnum):
    HARD = "hard"
    VIRTUAL = "virtual"
    OMITTED = "omitted"


class Observation(StrictContractModel):
    variable_id: ComponentIdRef
    kind: ObservationKind
    hard_state_id: StableId | None
    likelihood: tuple[NonNegativeFiniteFloat, ...] | None

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        _require_variable(self.variable_id, "observation variable")
        if self.kind is ObservationKind.HARD:
            if self.hard_state_id is None or self.likelihood is not None:
                raise ValueError("hard observation requires hard_state_id and forbids likelihood")
        elif self.kind is ObservationKind.VIRTUAL:
            if (
                self.hard_state_id is not None
                or self.likelihood is None
                or not self.likelihood
                or not any(value > 0.0 for value in self.likelihood)
            ):
                raise ValueError(
                    "virtual observation requires a nonzero likelihood and no hard state"
                )
        elif self.hard_state_id is not None or self.likelihood is not None:
            raise ValueError("omitted observation cannot carry a hard state or likelihood")
        return self


class ObservationSet(StrictContractModel):
    contract_id: Literal["observation-set"] = "observation-set"
    contract_version: Literal["0.1.0"] = "0.1.0"
    plan_hash: Sha256Digest
    observations: tuple[Observation, ...]
    observation_set_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_set(self) -> Self:
        _require_unique(
            tuple(_ref_key(observation.variable_id) for observation in self.observations),
            "observation variable IDs",
        )
        return self


class PosteriorDistribution(StrictContractModel):
    variable_id: ComponentIdRef
    ordered_state_ids: tuple[StableId, ...] = Field(min_length=1)
    probabilities: tuple[UnitInterval, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_distribution(self) -> Self:
        _require_variable(self.variable_id, "distribution variable")
        _require_unique(self.ordered_state_ids, "distribution state IDs")
        if len(self.ordered_state_ids) != len(self.probabilities):
            raise ValueError("state IDs and probabilities must have equal length")
        if abs(math.fsum(self.probabilities) - 1.0) > 1e-9:
            raise ValueError("posterior probabilities must sum to 1")
        return self


class PosteriorResult(StrictContractModel):
    contract_id: Literal["posterior-result"] = "posterior-result"
    contract_version: Literal["0.1.0"] = "0.1.0"
    scheme_ref: PinnedComponentRef
    plan_hash: Sha256Digest
    observation_set_hash: Sha256Digest
    priors: tuple[PosteriorDistribution, ...]
    posteriors: tuple[PosteriorDistribution, ...]
    result_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        prior_keys = tuple(_ref_key(item.variable_id) for item in self.priors)
        posterior_keys = tuple(_ref_key(item.variable_id) for item in self.posteriors)
        _require_unique(prior_keys, "prior variable IDs")
        _require_unique(posterior_keys, "posterior variable IDs")
        if prior_keys != posterior_keys:
            raise ValueError("prior and posterior variables must use the same stable order")
        return self


class FactorScope(StrictContractModel):
    variable_ids: tuple[ComponentIdRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        for reference in self.variable_ids:
            _require_variable(reference, "factor-scope variable")
        _require_unique(tuple(_ref_key(item) for item in self.variable_ids), "factor scope")
        return self


class InferenceTrace(StrictContractModel):
    contract_id: Literal["inference-trace"] = "inference-trace"
    contract_version: Literal["0.1.0"] = "0.1.0"
    scheme_ref: PinnedComponentRef
    plan_hash: Sha256Digest
    observation_set_hash: Sha256Digest
    query_variable_ids: tuple[ComponentIdRef, ...]
    observed_variable_ids: tuple[ComponentIdRef, ...]
    elimination_order: tuple[ComponentIdRef, ...]
    factor_scopes: tuple[FactorScope, ...]
    influence_edges: tuple[InferenceInfluenceEdge, ...]
    trace_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        for label, references in (
            ("query variables", self.query_variable_ids),
            ("observed variables", self.observed_variable_ids),
            ("elimination order", self.elimination_order),
        ):
            for reference in references:
                _require_variable(reference, label)
            _require_unique(tuple(_ref_key(item) for item in references), label)
        _require_unique(tuple(edge.edge_id for edge in self.influence_edges), "influence edges")
        return self


__all__ = [
    "BayesianDependencyEdge",
    "ExtractionEdge",
    "FactorScope",
    "InferenceInfluenceEdge",
    "InferencePlan",
    "InferenceTrace",
    "InferenceVariable",
    "Observation",
    "ObservationKind",
    "ObservationSet",
    "PosteriorDistribution",
    "PosteriorResult",
]
