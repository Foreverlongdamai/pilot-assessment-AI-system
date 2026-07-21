"""Contracts for inspecting external session data before managed import."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StringConstraints, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    NonNegativeInt,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
)
from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.session import CORE_MODALITIES, StreamStatus

NonEmptyString = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class SessionDataSourceKind(StrEnum):
    """Shape of an external folder selected by the user."""

    CANONICAL_BUNDLE = "canonical_bundle"
    SIMULATOR_RAW = "simulator_raw"


class UnitProvenance(StrEnum):
    SOURCE = "source"
    PROFILE = "profile"
    UNDECLARED = "undeclared"


class RawSourceFile(StrictContractModel):
    relative_path: BundleRelativePath
    byte_size: NonNegativeInt
    sha256: Sha256Digest


class RawFieldMapping(StrictContractModel):
    source_path: BundleRelativePath
    source_field: NonEmptyString
    canonical_field: StableId
    modality: StableId
    physical_dtype: StableId
    declared_unit: NonEmptyString | None = None
    unit_provenance: UnitProvenance
    timestamp_role: Literal["source_timestamp", "measurement", "context", "quality_check"]
    resolution_status: Literal["resolved"] = "resolved"

    @model_validator(mode="after")
    def validate_unit_provenance(self) -> Self:
        if self.unit_provenance is UnitProvenance.UNDECLARED:
            if self.declared_unit is not None:
                raise ValueError("undeclared unit provenance requires declared_unit=null")
        elif self.declared_unit is None:
            raise ValueError("declared unit provenance requires a unit value")
        return self


class RawModalityProposal(StrictContractModel):
    modality: StableId
    status: StreamStatus
    paths: tuple[BundleRelativePath, ...]
    format: NonEmptyString
    schema_id: StableId
    clock_id: StableId
    sample_rate_hz: PositiveFiniteFloat | None = None
    declared_units: dict[StableId, NonEmptyString] = Field(default_factory=dict)
    unit_handling: StableId

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is StreamStatus.PRESENT and not self.paths:
            raise ValueError("present raw modality proposals require source paths")
        if self.status is not StreamStatus.PRESENT and self.paths:
            raise ValueError("non-present raw modality proposals cannot claim source paths")
        return self


class RawAnnotationMapping(StrictContractModel):
    record_field: Literal["phases", "events", "baseline_intervals"]
    source_path: BundleRelativePath | None = None
    canonical_path: BundleRelativePath
    source_schema_id: StableId | None = None
    record_count: NonNegativeInt
    disposition: Literal["copied", "normalized", "empty"]


class RawRequiredInput(StrictContractModel):
    input_id: StableId
    label: NonEmptyString
    reason: NonEmptyString


class RawSessionInspection(StrictContractModel):
    contract_version: Literal["0.1.0"] = "0.1.0"
    source_snapshot_fingerprint: Sha256Digest
    detected_profile_id: StableId
    profile_candidates: tuple[StableId, ...] = ()
    files: tuple[RawSourceFile, ...]
    field_mappings: tuple[RawFieldMapping, ...]
    modality_proposals: dict[StableId, RawModalityProposal]
    annotation_mappings: tuple[RawAnnotationMapping, ...]
    required_user_inputs: tuple[RawRequiredInput, ...] = ()
    warnings: tuple[DomainErrorData, ...] = ()
    can_materialize: StrictBool

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        if set(self.modality_proposals) != set(CORE_MODALITIES):
            raise ValueError("raw inspection requires exactly seven core modalities")
        if any(key != proposal.modality for key, proposal in self.modality_proposals.items()):
            raise ValueError("raw modality proposal keys must match modality")
        if self.can_materialize != (not self.required_user_inputs):
            raise ValueError("can_materialize must reflect unresolved required inputs")
        return self


class SessionSourceInspection(StrictContractModel):
    contract_version: Literal["0.1.0"] = "0.1.0"
    source_kind: SessionDataSourceKind
    report: IngestionReadinessReport | None = None
    raw: RawSessionInspection | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.source_kind is SessionDataSourceKind.CANONICAL_BUNDLE:
            if self.report is None or self.raw is not None:
                raise ValueError("canonical source inspection requires only report")
        elif self.raw is None or self.report is not None:
            raise ValueError("raw source inspection requires only raw payload")
        return self


__all__ = [
    "RawAnnotationMapping",
    "RawFieldMapping",
    "RawModalityProposal",
    "RawRequiredInput",
    "RawSessionInspection",
    "RawSourceFile",
    "SessionDataSourceKind",
    "SessionSourceInspection",
    "UnitProvenance",
]
