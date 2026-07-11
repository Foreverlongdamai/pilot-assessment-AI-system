"""Unified result contract returned by every anchor extractor."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StrictBool, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    FiniteFloat,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    NonNegativeInt64,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.session import StreamStatus

PROBABILITY_TOLERANCE = 1e-9
NonEmptyString = Annotated[str, Field(min_length=1, max_length=2048)]


class CalculationStatus(StrEnum):
    COMPUTED = "computed"
    INVALID_QUALITY = "invalid_quality"
    MISSING_INPUT = "missing_input"
    NOT_APPLICABLE = "not_applicable"
    NOT_COMPUTABLE = "not_computable"
    DEPENDENCY_MISSING = "dependency_missing"
    EXTRACTOR_ERROR = "extractor_error"


class EvidenceState(StrEnum):
    UNACCEPTABLE = "unacceptable"
    ADEQUATE = "adequate"
    DESIRED = "desired"


CANONICAL_EVIDENCE_STATE_ORDER = (
    EvidenceState.UNACCEPTABLE,
    EvidenceState.ADEQUATE,
    EvidenceState.DESIRED,
)
SUPPORTED_SOFT_TIE_POLICIES = {
    "prefer_unacceptable": EvidenceState.UNACCEPTABLE,
    "prefer_adequate": EvidenceState.ADEQUATE,
    "prefer_desired": EvidenceState.DESIRED,
}


class EvidenceLikelihood(StrictContractModel):
    state_order: tuple[
        Literal["unacceptable"],
        Literal["adequate"],
        Literal["desired"],
    ]
    values: tuple[UnitInterval, UnitInterval, UnitInterval]

    @model_validator(mode="after")
    def validate_probability_sum(self) -> Self:
        if not math.isclose(
            sum(self.values),
            1.0,
            rel_tol=0.0,
            abs_tol=PROBABILITY_TOLERANCE,
        ):
            raise ValueError("evidence likelihood values must sum to one")
        return self


class PrimaryValue(StrictContractModel):
    value: FiniteFloat
    unit: NonEmptyString
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class SourceWindow(StrictContractModel):
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    phase: StableId | None = None
    event_id: StableId | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("end_t_ns must be greater than start_t_ns")
        return self


class DerivedArtifact(StrictContractModel):
    artifact_id: StableId
    kind: StableId
    path: BundleRelativePath
    schema_id: StableId
    window_grid_id: StableId | None = None
    window_length_s: PositiveFiniteFloat | None = None
    step_s: PositiveFiniteFloat | None = None
    alignment: StableId | None = None
    min_valid_fraction: UnitInterval | None = None
    partial_window_policy: StableId | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_window_definition_for_window_traces(self) -> Self:
        if self.kind == "window_metric_trace":
            window_fields = (
                self.window_grid_id,
                self.window_length_s,
                self.step_s,
                self.alignment,
                self.min_valid_fraction,
                self.partial_window_policy,
            )
            if any(value is None for value in window_fields):
                raise ValueError("window_metric_trace requires a complete window definition")
        return self


class AnchorQuality(StrictContractModel):
    passed: StrictBool
    score: UnitInterval
    valid_coverage: UnitInterval
    sync_error_ms: NonNegativeFiniteFloat | None
    flags: list[StableId]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Dependencies(StrictContractModel):
    available: list[StableId]
    missing: list[StableId]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sets(self) -> Self:
        if len(self.available) != len(set(self.available)):
            raise ValueError("available dependencies must be unique")
        if len(self.missing) != len(set(self.missing)):
            raise ValueError("missing dependencies must be unique")
        overlap = set(self.available) & set(self.missing)
        if overlap:
            raise ValueError(
                f"dependencies cannot be both available and missing: {sorted(overlap)}"
            )
        return self


class SampleRange(StrictContractModel):
    source_file: BundleRelativePath
    start_index: NonNegativeInt
    end_index: NonNegativeInt
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_index <= self.start_index:
            raise ValueError("end_index must be greater than start_index")
        return self


class Provenance(StrictContractModel):
    source_files: list[BundleRelativePath]
    sample_ranges: list[SampleRange]
    extractor_version: StableId
    evidence_grade: StableId
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class Diagnostic(StrictContractModel):
    code: StableId
    severity: DiagnosticSeverity
    message: NonEmptyString
    field_or_path: NonEmptyString | None = None
    remediation: NonEmptyString | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class EventResult(StrictContractModel):
    event_id: StableId
    evidence_state: EvidenceState | None
    raw_metrics: dict[StableId, FiniteFloat]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class AnchorResult(StrictContractModel):
    anchor_id: StableId
    model_version: StableId
    calculation_status: CalculationStatus
    evidence_state: EvidenceState | None
    continuous_score: UnitInterval | None
    evidence_likelihood: EvidenceLikelihood | None
    raw_metrics: dict[StableId, FiniteFloat]
    primary_value: PrimaryValue | None
    phase_results: dict[StableId, EvidenceState]
    event_results: list[EventResult]
    source_windows: list[SourceWindow]
    derived_artifacts: list[DerivedArtifact]
    quality: AnchorQuality
    thresholds_used: dict[StableId, FiniteFloat]
    parameters_used: dict[str, JsonValue]
    parameter_hash: Sha256Digest
    dependencies: Dependencies
    input_status_snapshot: dict[StableId, StreamStatus]
    provenance: Provenance
    diagnostics: list[Diagnostic]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_dependent_observation(self) -> Self:
        observation_fields = (
            self.evidence_state,
            self.continuous_score,
            self.evidence_likelihood,
        )
        if self.calculation_status is CalculationStatus.COMPUTED:
            if any(value is None for value in observation_fields):
                raise ValueError("computed results require all evidence observation fields")
            if not self.quality.passed:
                raise ValueError("computed results require a passed quality gate")
            self._validate_computed_observation()
        else:
            if any(value is not None for value in observation_fields):
                raise ValueError("non-computed results must omit all evidence observation fields")
            if self.quality.passed:
                raise ValueError("non-computed results cannot claim a passed quality gate")
        return self

    def _validate_computed_observation(self) -> None:
        likelihood = self.evidence_likelihood
        continuous_score = self.continuous_score
        evidence_state = self.evidence_state
        assert likelihood is not None
        assert continuous_score is not None
        assert evidence_state is not None

        expected_score = (likelihood.values[1] + 2.0 * likelihood.values[2]) / 2.0
        if not math.isclose(
            continuous_score,
            expected_score,
            rel_tol=0.0,
            abs_tol=PROBABILITY_TOLERANCE,
        ):
            raise ValueError("continuous_score must equal ordinal_expectation_v1")

        required_parameters = {
            "scoring_transform",
            "continuous_score_transform",
            "quality_transform",
            "config_version",
        }
        missing_parameters = required_parameters - self.parameters_used.keys()
        if missing_parameters:
            raise ValueError(f"parameters_used is missing: {sorted(missing_parameters)}")
        non_string_parameters = sorted(
            parameter
            for parameter in required_parameters
            if not isinstance(self.parameters_used[parameter], str)
        )
        if non_string_parameters:
            raise ValueError(f"standard parameters must be string IDs: {non_string_parameters}")

        scoring_transform = self.parameters_used["scoring_transform"]
        quality_transform = self.parameters_used["quality_transform"]
        if scoring_transform == "hard_threshold_v1":
            one_indices = [
                index
                for index, value in enumerate(likelihood.values)
                if math.isclose(value, 1.0, rel_tol=0.0, abs_tol=PROBABILITY_TOLERANCE)
            ]
            zero_count = sum(
                math.isclose(value, 0.0, rel_tol=0.0, abs_tol=PROBABILITY_TOLERANCE)
                for value in likelihood.values
            )
            if len(one_indices) != 1 or zero_count != 2:
                raise ValueError("hard_threshold_v1 requires a one-hot likelihood")
            if CANONICAL_EVIDENCE_STATE_ORDER[one_indices[0]] is not evidence_state:
                raise ValueError("evidence_state must match the hard one-hot likelihood")
        else:
            maximum = max(likelihood.values)
            maximum_indices = [
                index
                for index, value in enumerate(likelihood.values)
                if math.isclose(
                    value,
                    maximum,
                    rel_tol=0.0,
                    abs_tol=PROBABILITY_TOLERANCE,
                )
            ]
            if len(maximum_indices) == 1:
                expected_state = CANONICAL_EVIDENCE_STATE_ORDER[maximum_indices[0]]
                if evidence_state is not expected_state:
                    raise ValueError(
                        "soft evidence_state must match the unique maximum likelihood state"
                    )
            else:
                tie_policy = self.parameters_used.get("tie_policy")
                if not isinstance(tie_policy, str):
                    raise ValueError("soft likelihood ties require an explicit tie_policy")
                preferred_state = SUPPORTED_SOFT_TIE_POLICIES.get(tie_policy)
                if preferred_state is None:
                    raise ValueError(f"unsupported soft likelihood tie_policy: {tie_policy}")
                tied_states = {CANONICAL_EVIDENCE_STATE_ORDER[index] for index in maximum_indices}
                if preferred_state not in tied_states:
                    raise ValueError("tie_policy must select one of the tied maximum states")
                if evidence_state is not preferred_state:
                    raise ValueError("evidence_state must match the declared tie_policy")

        if quality_transform == "binary_quality_v1" and not math.isclose(
            self.quality.score,
            1.0,
            rel_tol=0.0,
            abs_tol=PROBABILITY_TOLERANCE,
        ):
            raise ValueError("binary_quality_v1 computed results require quality score 1")


__all__ = [
    "CANONICAL_EVIDENCE_STATE_ORDER",
    "PROBABILITY_TOLERANCE",
    "SUPPORTED_SOFT_TIE_POLICIES",
    "AnchorQuality",
    "AnchorResult",
    "CalculationStatus",
    "Dependencies",
    "DerivedArtifact",
    "Diagnostic",
    "DiagnosticSeverity",
    "EvidenceLikelihood",
    "EvidenceState",
    "EventResult",
    "PrimaryValue",
    "Provenance",
    "SampleRange",
    "SourceWindow",
]
