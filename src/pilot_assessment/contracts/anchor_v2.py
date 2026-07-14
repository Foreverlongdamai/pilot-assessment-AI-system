"""Typed result contracts produced by M4 anchor extractors.

The v0.2 family intentionally lives beside the frozen v0.1 reader.  M4 writers
must use :class:`AnchorResultV2`; the legacy contract remains read-only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, Self, cast

from pydantic import Field, JsonValue, StrictBool, field_validator, model_validator

from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
from pilot_assessment.contracts.common import (
    FiniteFloat,
    Int64,
    NonNegativeInt,
    NonNegativeInt64,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
    freeze_json_mapping,
)
from pilot_assessment.contracts.errors import DomainErrorData


class AnchorCalculationStatusV2(StrEnum):
    """Active calculation outcomes for the v0.2 writer."""

    COMPUTED = "computed"
    MISSING_INPUT = "missing_input"
    NOT_APPLICABLE = "not_applicable"
    NOT_COMPUTABLE = "not_computable"
    DEPENDENCY_MISSING = "dependency_missing"
    EXTRACTOR_ERROR = "extractor_error"


class MetricValue(StrictContractModel):
    """A scalar metric whose JSON number kind and unit are explicit."""

    scalar_kind: Literal["integer", "float"]
    value: Int64 | FiniteFloat
    unit: StableId

    @model_validator(mode="after")
    def validate_declared_scalar_kind(self) -> Self:
        if self.scalar_kind == "integer" and type(self.value) is not int:
            raise ValueError("scalar_kind=integer requires a strict JSON integer")
        if self.scalar_kind == "float" and type(self.value) is not float:
            raise ValueError("scalar_kind=float requires a strict JSON float")
        return self


class _FrozenDict(dict[str, Any]):
    """A JSON-serializable dict whose validated snapshot cannot be mutated."""

    def __setitem__(self, _key: str, _value: Any) -> None:
        raise TypeError("validated contract mappings are immutable")

    def __delitem__(self, _key: str) -> None:
        raise TypeError("validated contract mappings are immutable")

    def __ior__(self, _value: Any, /) -> Self:
        raise TypeError("validated contract mappings are immutable")

    def clear(self) -> None:
        raise TypeError("validated contract mappings are immutable")

    def pop(self, _key: object, _default: Any = None, /) -> Any:
        raise TypeError("validated contract mappings are immutable")

    def popitem(self) -> tuple[str, Any]:
        raise TypeError("validated contract mappings are immutable")

    def setdefault(self, _key: str, _default: Any = None, /) -> Any:
        raise TypeError("validated contract mappings are immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("validated contract mappings are immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenDict:
        return self


def _freeze_metric_snapshot(
    value: dict[str, MetricValue],
) -> dict[str, MetricValue]:
    return cast(dict[str, MetricValue], _FrozenDict(value))


class ClassificationOverride(StrictContractModel):
    """A versioned failure mode that can only support Unacceptable evidence."""

    code: StableId
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def freeze_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return freeze_json_mapping(value)


class SourceWindowV2(StrictContractModel):
    """A named half-open semantic or analysis window."""

    window_id: StableId
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    phase_id: StableId | None
    event_id: StableId | None
    include_session_terminal_point: StrictBool = False

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("end_t_ns must be greater than start_t_ns")
        return self


class AnchorArtifactRef(StrictContractModel):
    """Immutable identity and provenance for a derived anchor artifact."""

    artifact_id: StableId
    kind: StableId
    schema_id: StableId
    logical_content_sha256: Sha256Digest
    storage_file_sha256: Sha256Digest | None
    row_count: NonNegativeInt
    start_t_ns: NonNegativeInt64 | None
    end_t_ns: NonNegativeInt64 | None
    grid_hash: Sha256Digest | None
    producer_anchor_id: StableId
    producer_plugin_id: StableId
    producer_plugin_version: StableId
    parameter_hash: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        _validate_optional_range(self.start_t_ns, self.end_t_ns, "artifact")
        return self


class ComputationTrace(StrictContractModel):
    """Typed audit trace; it is never a quality gate or scoring input."""

    sample_count: NonNegativeInt
    source_start_t_ns: NonNegativeInt64 | None
    source_end_t_ns: NonNegativeInt64 | None
    analysis_start_t_ns: NonNegativeInt64 | None
    analysis_end_t_ns: NonNegativeInt64 | None
    grid_id: StableId | None
    window_ids: tuple[StableId, ...]
    interpolation_method: StableId | None
    matching_method: StableId | None
    diagnostics: tuple[DomainErrorData, ...]

    @model_validator(mode="after")
    def validate_time_ranges(self) -> Self:
        _validate_optional_range(
            self.source_start_t_ns,
            self.source_end_t_ns,
            "source",
        )
        _validate_optional_range(
            self.analysis_start_t_ns,
            self.analysis_end_t_ns,
            "analysis",
        )
        return self


class AnchorBreakdownMeasurement(StrictContractModel):
    """Unscored per-phase or per-event measurement emitted by a plugin."""

    breakdown_id: StableId
    calculation_status: AnchorCalculationStatusV2
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    raw_metrics: dict[StableId, MetricValue]
    classification_override_candidate: ClassificationOverride | None
    trace: ComputationTrace
    diagnostics: tuple[DomainErrorData, ...]

    @field_validator("raw_metrics")
    @classmethod
    def freeze_raw_metrics(cls, value: dict[str, MetricValue]) -> dict[str, MetricValue]:
        return _freeze_metric_snapshot(value)

    @model_validator(mode="after")
    def validate_status_dependent_fields(self) -> Self:
        _validate_measurement_fields(
            status=self.calculation_status,
            primary_value=self.primary_value,
            primary_value_reason=self.primary_value_reason,
            raw_metrics=self.raw_metrics,
            classification_override_candidate=self.classification_override_candidate,
        )
        _validate_finite_json(self.model_dump(mode="python"))
        return self


class AnchorMeasurement(StrictContractModel):
    """Unscored, typed output from one M4 anchor plugin invocation."""

    contract_id: Literal["anchor-measurement"] = "anchor-measurement"
    contract_version: Literal["0.1.0"] = "0.1.0"
    anchor_id: StableId
    calculation_status: AnchorCalculationStatusV2
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    raw_metrics: dict[StableId, MetricValue]
    phase_results: tuple[AnchorBreakdownMeasurement, ...]
    event_results: tuple[AnchorBreakdownMeasurement, ...]
    classification_override_candidate: ClassificationOverride | None
    source_windows: tuple[SourceWindowV2, ...]
    derived_artifacts: tuple[AnchorArtifactRef, ...]
    trace: ComputationTrace
    diagnostics: tuple[DomainErrorData, ...]

    @field_validator("raw_metrics")
    @classmethod
    def freeze_raw_metrics(cls, value: dict[str, MetricValue]) -> dict[str, MetricValue]:
        return _freeze_metric_snapshot(value)

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        _validate_measurement_fields(
            status=self.calculation_status,
            primary_value=self.primary_value,
            primary_value_reason=self.primary_value_reason,
            raw_metrics=self.raw_metrics,
            classification_override_candidate=self.classification_override_candidate,
        )
        _validate_finite_json(self.model_dump(mode="python"))
        return self


class AnchorBreakdownResult(StrictContractModel):
    """Per-phase or per-event result with an independent observation."""

    breakdown_id: StableId
    calculation_status: AnchorCalculationStatusV2
    evidence_state: EvidenceState | None
    evidence_likelihood: EvidenceLikelihood | None
    continuous_score: UnitInterval | None
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    raw_metrics: dict[StableId, MetricValue]
    classification_override: ClassificationOverride | None
    trace: ComputationTrace
    diagnostics: tuple[DomainErrorData, ...]

    @field_validator("raw_metrics")
    @classmethod
    def freeze_raw_metrics(cls, value: dict[str, MetricValue]) -> dict[str, MetricValue]:
        return _freeze_metric_snapshot(value)

    @model_validator(mode="after")
    def validate_status_dependent_fields(self) -> Self:
        _validate_result_fields(
            status=self.calculation_status,
            evidence_state=self.evidence_state,
            evidence_likelihood=self.evidence_likelihood,
            continuous_score=self.continuous_score,
            primary_value=self.primary_value,
            primary_value_reason=self.primary_value_reason,
            raw_metrics=self.raw_metrics,
            classification_override=self.classification_override,
        )
        _validate_finite_json(self.model_dump(mode="python"))
        return self


class AnchorResultProvenance(StrictContractModel):
    """Reproducibility identity for the producing plugin invocation."""

    plugin_id: StableId
    plugin_version: StableId
    implementation_digest: Sha256Digest
    parameter_hash: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]
    computation_trace: ComputationTrace


class AnchorResultV2(StrictContractModel):
    """The breaking M4 anchor-result contract, versioned independently of v0.1."""

    contract_id: Literal["anchor-result"] = "anchor-result"
    contract_version: Literal["0.2.0"] = "0.2.0"
    anchor_id: StableId
    calculation_status: AnchorCalculationStatusV2
    evidence_state: EvidenceState | None
    evidence_likelihood: EvidenceLikelihood | None
    continuous_score: UnitInterval | None
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    classification_override: ClassificationOverride | None
    raw_metrics: dict[StableId, MetricValue]
    phase_results: tuple[AnchorBreakdownResult, ...]
    event_results: tuple[AnchorBreakdownResult, ...]
    derived_artifacts: tuple[AnchorArtifactRef, ...]
    diagnostics: tuple[DomainErrorData, ...]
    provenance: AnchorResultProvenance
    result_fingerprint: Sha256Digest

    @field_validator("raw_metrics")
    @classmethod
    def freeze_raw_metrics(cls, value: dict[str, MetricValue]) -> dict[str, MetricValue]:
        return _freeze_metric_snapshot(value)

    @model_validator(mode="after")
    def validate_status_dependent_fields(self) -> Self:
        _validate_result_fields(
            status=self.calculation_status,
            evidence_state=self.evidence_state,
            evidence_likelihood=self.evidence_likelihood,
            continuous_score=self.continuous_score,
            primary_value=self.primary_value,
            primary_value_reason=self.primary_value_reason,
            raw_metrics=self.raw_metrics,
            classification_override=self.classification_override,
        )
        _validate_finite_json(self.model_dump(mode="python"))
        return self


def _validate_optional_range(start: int | None, end: int | None, label: str) -> None:
    if (start is None) != (end is None):
        raise ValueError(f"{label} time range requires both start and end")
    if start is not None and end is not None and end < start:
        raise ValueError(f"{label} end_t_ns must not precede start_t_ns")


def _validate_result_fields(
    *,
    status: AnchorCalculationStatusV2,
    evidence_state: EvidenceState | None,
    evidence_likelihood: EvidenceLikelihood | None,
    continuous_score: float | None,
    primary_value: MetricValue | None,
    primary_value_reason: str | None,
    raw_metrics: Mapping[str, MetricValue],
    classification_override: ClassificationOverride | None,
) -> None:
    observation = (evidence_state, evidence_likelihood, continuous_score)
    if status is AnchorCalculationStatusV2.COMPUTED:
        if any(value is None for value in observation):
            raise ValueError("computed results require a complete evidence observation")
        _validate_hard_observation(
            evidence_state=evidence_state,
            evidence_likelihood=evidence_likelihood,
            continuous_score=continuous_score,
        )
        if primary_value is None:
            if primary_value_reason is None:
                raise ValueError("a null computed primary_value requires primary_value_reason")
            if not raw_metrics:
                raise ValueError("a null computed primary_value requires typed raw_metrics")
        elif primary_value_reason is not None:
            raise ValueError("primary_value_reason is only valid when primary_value is null")
        if classification_override is not None and evidence_state is not EvidenceState.UNACCEPTABLE:
            raise ValueError("classification_override may only select Unacceptable")
        return

    if any(value is not None for value in observation):
        raise ValueError("non-computed results must omit the evidence observation")
    if primary_value is not None or primary_value_reason is not None:
        raise ValueError("non-computed results must omit primary measurement fields")
    if classification_override is not None:
        raise ValueError("classification_override requires a computed Unacceptable result")


def _validate_measurement_fields(
    *,
    status: AnchorCalculationStatusV2,
    primary_value: MetricValue | None,
    primary_value_reason: str | None,
    raw_metrics: Mapping[str, MetricValue],
    classification_override_candidate: ClassificationOverride | None,
) -> None:
    if status is AnchorCalculationStatusV2.COMPUTED:
        if primary_value is None:
            if primary_value_reason is None:
                raise ValueError("a null computed primary_value requires primary_value_reason")
            if not raw_metrics:
                raise ValueError("a null computed primary_value requires typed raw_metrics")
        elif primary_value_reason is not None:
            raise ValueError("primary_value_reason is only valid when primary_value is null")
        return

    if primary_value is not None or primary_value_reason is not None:
        raise ValueError("non-computed measurements must omit primary measurement fields")
    if classification_override_candidate is not None:
        raise ValueError("classification_override_candidate requires a computed measurement")


def _validate_hard_observation(
    *,
    evidence_state: EvidenceState | None,
    evidence_likelihood: EvidenceLikelihood | None,
    continuous_score: float | None,
) -> None:
    assert evidence_state is not None
    assert evidence_likelihood is not None
    assert continuous_score is not None

    expected = {
        EvidenceState.UNACCEPTABLE: ((1.0, 0.0, 0.0), 0.0),
        EvidenceState.ADEQUATE: ((0.0, 1.0, 0.0), 0.5),
        EvidenceState.DESIRED: ((0.0, 0.0, 1.0), 1.0),
    }
    expected_values, expected_score = expected[evidence_state]
    if evidence_likelihood.values != expected_values:
        raise ValueError("evidence_likelihood must be canonical one-hot for evidence_state")
    if continuous_score != expected_score:
        raise ValueError("continuous_score must be 0, 0.5 or 1 for hard U/A/D evidence")


def _validate_finite_json(value: object) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("all JSON numbers must be finite")
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _validate_finite_json(nested)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _validate_finite_json(nested)


__all__ = [
    "AnchorArtifactRef",
    "AnchorBreakdownMeasurement",
    "AnchorBreakdownResult",
    "AnchorCalculationStatusV2",
    "AnchorMeasurement",
    "AnchorResultProvenance",
    "AnchorResultV2",
    "ClassificationOverride",
    "ComputationTrace",
    "MetricValue",
    "SourceWindowV2",
]
