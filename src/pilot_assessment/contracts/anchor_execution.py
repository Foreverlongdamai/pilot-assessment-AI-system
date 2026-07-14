"""Serializable M4 semantic and resolved-reference contracts.

This module deliberately contains no Polars runtime objects and computes no
canonical fingerprints.  Runtime reference candidates and binding live under
``pilot_assessment.anchors``; canonical identity is introduced by M4 Task 8.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    FiniteFloat,
    Int64,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    NonNegativeInt64,
    PositiveFiniteFloat,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.session import CoreModality
from pilot_assessment.contracts.synchronization import MAX_SESSION_END_NS_V0_1

UNIT_NAME_PATTERN = r"^[A-Za-z0-9%*/^._-]+$"
REFERENCE_DTYPE_IDS = frozenset(
    {
        "bool",
        "i8",
        "i16",
        "i32",
        "i64",
        "u8",
        "u16",
        "u32",
        "u64",
        "f32",
        "f64",
        "utf8",
    }
)
REFERENCE_INTEGER_DTYPE_IDS = frozenset({"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"})

UnitName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=UNIT_NAME_PATTERN),
]
AuditText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ResourceRelativePath = BundleRelativePath

_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_UNIT_NAME_ADAPTER = TypeAdapter(UnitName)


class SemanticApplicabilityStatus(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


class AoiGeometryKind(StrEnum):
    DYNAMIC_2D = "dynamic_2d"
    DYNAMIC_3D = "dynamic_3d"
    POLYGON_2D = "polygon_2d"
    BOX_3D = "box_3d"
    CATCH_ALL = "catch_all"


class BaselineModality(StrEnum):
    ECG = "ECG"
    EEG = "EEG"


class ReferenceResolutionStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"


class ReferenceSourceKind(StrEnum):
    BUNDLE = "bundle"
    MODEL_BUNDLE = "model_bundle"


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must contain unique IDs")


def _require_sorted(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must use canonical lexical order")


def _strict_integer(value: object, label: str) -> object:
    if value.__class__ is not int:
        raise ValueError(f"{label} must be an integer")
    return value


class SemanticVector(StrictContractModel):
    coordinate_frame_id: StableId
    unit: UnitName
    values: tuple[FiniteFloat, ...]

    @field_validator("values")
    @classmethod
    def require_two_or_three_dimensions(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) not in {2, 3}:
            raise ValueError("semantic vector must have exactly two or three values")
        return value


class TaskTargetDefinition(StrictContractModel):
    target_id: StableId
    position: SemanticVector
    arrival_axis: SemanticVector | None = None

    @model_validator(mode="after")
    def validate_target_geometry(self) -> Self:
        if len(self.position.values) != 3:
            raise ValueError("target position must be three-dimensional")
        if self.arrival_axis is None:
            return self
        if len(self.arrival_axis.values) != 3:
            raise ValueError("arrival axis must be three-dimensional")
        if not any(component != 0.0 for component in self.arrival_axis.values):
            raise ValueError("arrival axis must be non-zero")
        if self.arrival_axis.coordinate_frame_id != self.position.coordinate_frame_id:
            raise ValueError("arrival axis must use the target position frame")
        if self.arrival_axis.unit != "dimensionless":
            raise ValueError("arrival axis unit must be dimensionless")
        return self


class EnvelopeAxisLimit(StrictContractModel):
    metric_id: StableId
    desired_abs_max: NonNegativeFiniteFloat
    adequate_abs_max: NonNegativeFiniteFloat
    unit: UnitName

    @model_validator(mode="after")
    def require_ordered_limits(self) -> Self:
        if self.adequate_abs_max < self.desired_abs_max:
            raise ValueError("adequate_abs_max must be at least desired_abs_max")
        return self


class EnvelopeDefinition(StrictContractModel):
    envelope_id: StableId
    target_id: StableId
    axis_limits: tuple[EnvelopeAxisLimit, ...]

    @model_validator(mode="after")
    def validate_axis_inventory(self) -> Self:
        if not self.axis_limits:
            raise ValueError("envelope must define at least one axis limit")
        ids = tuple(limit.metric_id for limit in self.axis_limits)
        _require_unique(ids, "envelope metric IDs")
        _require_sorted(ids, "envelope metric IDs")
        return self


class SemanticPhase(StrictContractModel):
    phase_id: StableId
    phase_type: StableId
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    include_session_terminal_point: StrictBool = False
    target_id: StableId | None = None
    envelope_id: StableId | None = None

    @model_validator(mode="after")
    def require_positive_half_open_span(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("phase end must be greater than phase start")
        return self


class SemanticEvent(StrictContractModel):
    event_id: StableId
    event_type: StableId
    t_ns: NonNegativeInt64
    duration_ns: NonNegativeInt64 | None = None
    opportunity_end_t_ns: NonNegativeInt64 | None = None
    phase_id: StableId | None = None
    target_id: StableId | None = None
    envelope_id: StableId | None = None
    relevant_aoi_ids: tuple[StableId, ...] = ()
    control_mapping_ids: tuple[StableId, ...] = ()

    @model_validator(mode="after")
    def validate_event_shape(self) -> Self:
        if self.duration_ns is not None and self.duration_ns <= 0:
            raise ValueError("event duration must be positive")
        if self.opportunity_end_t_ns is not None and self.opportunity_end_t_ns <= self.t_ns:
            raise ValueError("event opportunity end must be greater than event time")
        for values, label in (
            (self.relevant_aoi_ids, "event AOI IDs"),
            (self.control_mapping_ids, "event control mapping IDs"),
        ):
            _require_unique(values, label)
            _require_sorted(values, label)
        return self


class DynamicAoiSource(StrictContractModel):
    stream_role: Literal["I"] = "I"
    table_role: StableId
    aligned_schema_id: StableId
    coordinate_frame_id: StableId
    unit: UnitName
    frame_id_field: StableId
    aoi_id_field: StableId
    geometry_field_ids: tuple[StableId, ...]

    @field_validator("geometry_field_ids")
    @classmethod
    def require_geometry_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("dynamic AOI geometry fields must be non-empty")
        _require_unique(value, "dynamic AOI geometry fields")
        return value


class AoiDefinition(StrictContractModel):
    aoi_id: StableId
    taxonomy_id: StableId
    role: StableId
    geometry_kind: AoiGeometryKind
    priority: NonNegativeInt
    role_weight: UnitInterval
    off_task: StrictBool
    dynamic_source: DynamicAoiSource | None = None
    vertices: tuple[SemanticVector, ...] = ()

    @model_validator(mode="after")
    def validate_geometry_matrix(self) -> Self:
        if self.geometry_kind in {
            AoiGeometryKind.DYNAMIC_2D,
            AoiGeometryKind.DYNAMIC_3D,
        }:
            if self.dynamic_source is None or self.vertices:
                raise ValueError("dynamic AOI requires a source and forbids vertices")
            return self
        if self.dynamic_source is not None:
            raise ValueError("static and catch-all AOIs forbid a dynamic source")

        if self.geometry_kind is AoiGeometryKind.POLYGON_2D:
            if len(self.vertices) < 3 or any(len(v.values) != 2 for v in self.vertices):
                raise ValueError("polygon AOI requires at least three 2D vertices")
            self._require_common_vertex_frame_and_unit()
            twice_area = sum(
                a.values[0] * b.values[1] - b.values[0] * a.values[1]
                for a, b in zip(
                    self.vertices,
                    (*self.vertices[1:], self.vertices[0]),
                    strict=True,
                )
            )
            if twice_area == 0.0:
                raise ValueError("polygon AOI must have non-zero area")
            return self

        if self.geometry_kind is AoiGeometryKind.BOX_3D:
            if len(self.vertices) != 2 or any(len(v.values) != 3 for v in self.vertices):
                raise ValueError("box AOI requires exactly two 3D corners")
            self._require_common_vertex_frame_and_unit()
            if any(
                upper <= lower
                for lower, upper in zip(
                    self.vertices[0].values, self.vertices[1].values, strict=True
                )
            ):
                raise ValueError("box AOI extents must be strictly positive")
            return self

        if self.vertices:
            raise ValueError("catch-all AOI forbids vertices")
        if self.role != "other_scene" or not self.off_task or self.role_weight != 0.0:
            raise ValueError("catch-all AOI must be other_scene, off-task and have zero weight")
        return self

    def _require_common_vertex_frame_and_unit(self) -> None:
        first = self.vertices[0]
        if any(
            vertex.coordinate_frame_id != first.coordinate_frame_id or vertex.unit != first.unit
            for vertex in self.vertices[1:]
        ):
            raise ValueError("AOI vertices must share one frame and unit")


class ControlEffectMapping(StrictContractModel):
    control_mapping_id: StableId
    state_axis_id: StableId
    control_channel_id: StableId
    correct_sign: Literal[-1, 1]
    state_unit: UnitName
    control_unit: UnitName
    lower: FiniteFloat
    trim: FiniteFloat
    upper: FiniteFloat

    @field_validator("correct_sign", mode="before")
    @classmethod
    def require_strict_sign_integer(cls, value: object) -> object:
        return _strict_integer(value, "correct_sign")

    @model_validator(mode="after")
    def validate_calibration(self) -> Self:
        if not self.lower < self.trim < self.upper:
            raise ValueError("control calibration must satisfy lower < trim < upper")
        return self


class BaselineChannelBinding(StrictContractModel):
    modality: BaselineModality
    channel_ids: tuple[StableId, ...]

    @field_validator("channel_ids")
    @classmethod
    def validate_channel_map(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("baseline channel map must be non-empty")
        _require_unique(value, "baseline channel IDs")
        return value


class BaselineDefinition(StrictContractModel):
    baseline_id: StableId
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    channel_bindings: tuple[BaselineChannelBinding, ...]
    condition_id: StableId | None = None
    annotation_valid: StrictBool | None = None
    annotation_exclusion_reason: AuditText | None = None

    @model_validator(mode="after")
    def validate_baseline(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("baseline end must be greater than baseline start")
        if not self.channel_bindings:
            raise ValueError("baseline channel bindings must be non-empty")
        modalities = tuple(binding.modality.value for binding in self.channel_bindings)
        _require_unique(modalities, "baseline modalities")
        _require_sorted(modalities, "baseline modalities")
        if self.annotation_valid is False and self.annotation_exclusion_reason is None:
            raise ValueError("invalid baseline annotation requires an exclusion reason")
        return self


class AnchorApplicability(StrictContractModel):
    anchor_id: StableId
    status: SemanticApplicabilityStatus
    phase_ids: tuple[StableId, ...] = ()
    event_ids: tuple[StableId, ...] = ()
    aoi_ids: tuple[StableId, ...] = ()
    control_mapping_ids: tuple[StableId, ...] = ()
    baseline_ids: tuple[StableId, ...] = ()
    target_ids: tuple[StableId, ...] = ()
    envelope_ids: tuple[StableId, ...] = ()
    reason: StableId | None = None

    @model_validator(mode="after")
    def validate_status_matrix(self) -> Self:
        reference_sets = (
            self.phase_ids,
            self.event_ids,
            self.aoi_ids,
            self.control_mapping_ids,
            self.baseline_ids,
            self.target_ids,
            self.envelope_ids,
        )
        for values in reference_sets:
            _require_unique(values, "applicability references")
            _require_sorted(values, "applicability references")
        if self.status is SemanticApplicabilityStatus.APPLICABLE:
            if self.reason is not None:
                raise ValueError("applicable anchor must not provide a reason")
        elif self.reason is None or any(reference_sets):
            raise ValueError(
                "not_applicable anchor requires a reason and forbids semantic references"
            )
        return self


class SessionSemanticSnapshot(StrictContractModel):
    contract_id: Literal["session-semantic-snapshot"] = "session-semantic-snapshot"
    contract_version: Literal["0.1.0"] = "0.1.0"
    session_id: StableId
    task_profile_id: StableId
    scenario_id: StableId
    source_snapshot_fingerprint: Sha256Digest
    synchronization_fingerprint: Sha256Digest
    annotation_revision: StableId
    synthetic_semantics_unvalidated: StrictBool
    session_start_t_ns: Literal[0] = 0
    session_end_t_ns: Annotated[int, Field(strict=True, gt=0, le=MAX_SESSION_END_NS_V0_1)]
    phases: tuple[SemanticPhase, ...] = ()
    events: tuple[SemanticEvent, ...] = ()
    aois: tuple[AoiDefinition, ...] = ()
    control_mappings: tuple[ControlEffectMapping, ...] = ()
    baselines: tuple[BaselineDefinition, ...] = ()
    targets: tuple[TaskTargetDefinition, ...] = ()
    envelopes: tuple[EnvelopeDefinition, ...] = ()
    applicability: tuple[AnchorApplicability, ...] = ()
    semantic_snapshot_fingerprint: Sha256Digest

    @field_validator("session_start_t_ns", mode="before")
    @classmethod
    def require_strict_integer_zero(cls, value: object) -> object:
        if value.__class__ is not int:
            raise ValueError("session_start_t_ns must be an integer zero")
        return value

    @model_validator(mode="after")
    def validate_semantic_graph(self) -> Self:
        self._validate_canonical_root_inventories()
        phase_by_id = {phase.phase_id: phase for phase in self.phases}
        target_ids = {target.target_id for target in self.targets}
        envelope_by_id = {envelope.envelope_id: envelope for envelope in self.envelopes}
        aoi_ids = {aoi.aoi_id for aoi in self.aois}
        control_ids = {mapping.control_mapping_id for mapping in self.control_mappings}
        baseline_ids = {baseline.baseline_id for baseline in self.baselines}
        event_ids = {event.event_id for event in self.events}

        previous_end = 0
        terminal_owners: list[SemanticPhase] = []
        for index, phase in enumerate(self.phases):
            if phase.end_t_ns > self.session_end_t_ns:
                raise ValueError("phase lies outside the session")
            if index and phase.start_t_ns < previous_end:
                raise ValueError("phases must not overlap")
            previous_end = phase.end_t_ns
            if phase.include_session_terminal_point:
                terminal_owners.append(phase)
                if index != len(self.phases) - 1 or phase.end_t_ns != self.session_end_t_ns:
                    raise ValueError("only the canonical final phase may own the terminal point")
            self._require_optional_reference(phase.target_id, target_ids, "phase target")
            self._require_optional_reference(
                phase.envelope_id, set(envelope_by_id), "phase envelope"
            )
        if len(terminal_owners) > 1:
            raise ValueError("only one phase may own the session terminal point")

        for envelope in self.envelopes:
            if envelope.target_id not in target_ids:
                raise ValueError("envelope target reference does not exist")

        catch_all_counts: dict[str, int] = {}
        for aoi in self.aois:
            catch_all_counts.setdefault(aoi.taxonomy_id, 0)
            if aoi.geometry_kind is AoiGeometryKind.CATCH_ALL:
                catch_all_counts[aoi.taxonomy_id] += 1
        if any(count != 1 for count in catch_all_counts.values()):
            raise ValueError("each AOI taxonomy must contain exactly one catch_all")

        for baseline in self.baselines:
            if baseline.end_t_ns > self.session_end_t_ns:
                raise ValueError("baseline lies outside the session")

        for event in self.events:
            if event.t_ns > self.session_end_t_ns:
                raise ValueError("event lies outside the session")
            phase = phase_by_id.get(event.phase_id) if event.phase_id is not None else None
            if event.phase_id is not None and phase is None:
                raise ValueError("event phase reference does not exist")
            is_terminal = event.t_ns == self.session_end_t_ns
            if is_terminal:
                if event.duration_ns is not None or event.opportunity_end_t_ns is not None:
                    raise ValueError("terminal event forbids duration and opportunity")
                if phase is not None and not phase.include_session_terminal_point:
                    raise ValueError("terminal phase-scoped event requires the terminal owner")
            elif phase is not None and not phase.start_t_ns <= event.t_ns < phase.end_t_ns:
                raise ValueError("event is outside its phase")

            scope_end = phase.end_t_ns if phase is not None else self.session_end_t_ns
            if event.duration_ns is not None and event.t_ns + event.duration_ns > scope_end:
                raise ValueError("event duration exceeds its phase or session")
            if event.opportunity_end_t_ns is not None and event.opportunity_end_t_ns > scope_end:
                raise ValueError("event opportunity exceeds its phase or session")
            self._require_optional_reference(event.target_id, target_ids, "event target")
            self._require_optional_reference(
                event.envelope_id, set(envelope_by_id), "event envelope"
            )
            if not set(event.relevant_aoi_ids) <= aoi_ids:
                raise ValueError("event AOI reference does not exist")
            if not set(event.control_mapping_ids) <= control_ids:
                raise ValueError("event control mapping reference does not exist")

        namespaces = {
            "phase": set(phase_by_id),
            "event": event_ids,
            "AOI": aoi_ids,
            "control mapping": control_ids,
            "baseline": baseline_ids,
            "target": target_ids,
            "envelope": set(envelope_by_id),
        }
        for applicability in self.applicability:
            for values, label in (
                (applicability.phase_ids, "phase"),
                (applicability.event_ids, "event"),
                (applicability.aoi_ids, "AOI"),
                (applicability.control_mapping_ids, "control mapping"),
                (applicability.baseline_ids, "baseline"),
                (applicability.target_ids, "target"),
                (applicability.envelope_ids, "envelope"),
            ):
                if not set(values) <= namespaces[label]:
                    raise ValueError(f"applicability {label} reference does not exist")
        return self

    def _validate_canonical_root_inventories(self) -> None:
        inventories: tuple[tuple[tuple[object, ...], tuple[object, ...], str], ...] = (
            (
                self.phases,
                tuple(sorted(self.phases, key=lambda x: (x.start_t_ns, x.end_t_ns, x.phase_id))),
                "phases",
            ),
            (self.events, tuple(sorted(self.events, key=lambda x: (x.t_ns, x.event_id))), "events"),
            (self.aois, tuple(sorted(self.aois, key=lambda x: x.aoi_id)), "AOIs"),
            (
                self.control_mappings,
                tuple(sorted(self.control_mappings, key=lambda x: x.control_mapping_id)),
                "control mappings",
            ),
            (
                self.baselines,
                tuple(sorted(self.baselines, key=lambda x: x.baseline_id)),
                "baselines",
            ),
            (self.targets, tuple(sorted(self.targets, key=lambda x: x.target_id)), "targets"),
            (
                self.envelopes,
                tuple(sorted(self.envelopes, key=lambda x: x.envelope_id)),
                "envelopes",
            ),
            (
                self.applicability,
                tuple(sorted(self.applicability, key=lambda x: x.anchor_id)),
                "applicability",
            ),
        )
        for actual, expected, label in inventories:
            if actual != expected:
                raise ValueError(f"{label} must use canonical order")
            ids = tuple(self._root_item_id(item) for item in actual)
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} must contain unique IDs")

    @staticmethod
    def _root_item_id(item: object) -> str:
        for field_name in (
            "phase_id",
            "event_id",
            "aoi_id",
            "control_mapping_id",
            "baseline_id",
            "envelope_id",
            "target_id",
            "anchor_id",
        ):
            value = getattr(item, field_name, None)
            if isinstance(value, str):
                return value
        raise TypeError("unsupported semantic root item")

    @staticmethod
    def _require_optional_reference(value: str | None, inventory: set[str], label: str) -> None:
        if value is not None and value not in inventory:
            raise ValueError(f"{label} reference does not exist")


class ReferenceSessionIdentity(StrictContractModel):
    session_id: StableId
    source_snapshot_fingerprint: Sha256Digest
    synchronization_fingerprint: Sha256Digest
    session_start_t_ns: Literal[0] = 0
    session_end_t_ns: Annotated[int, Field(strict=True, gt=0, le=MAX_SESSION_END_NS_V0_1)]

    @field_validator("session_start_t_ns", mode="before")
    @classmethod
    def require_strict_integer_zero(cls, value: object) -> object:
        if value.__class__ is not int:
            raise ValueError("session_start_t_ns must be an integer zero")
        return value


class ReferenceAlignmentContract(StrictContractModel):
    mapping_method: StableId
    mapping_policy_id: StableId
    source_clock_id: StableId
    target_time_domain: Literal["session_time_ns"] = "session_time_ns"
    scale: PositiveFiniteFloat
    offset_ns: Int64
    declared_drift_ppm: FiniteFloat
    rounding_mode: Literal["decimal_round_half_even"] = "decimal_round_half_even"
    in_session_policy: Literal["m3_closed_source_row_mask_v0.1"] = "m3_closed_source_row_mask_v0.1"

    @model_validator(mode="after")
    def require_decimal_scale_drift_consistency(self) -> Self:
        try:
            scale = Decimal(str(self.scale))
            drift = Decimal(str(self.declared_drift_ppm))
        except InvalidOperation as error:
            raise ValueError("scale and drift must be finite decimals") from error
        expected = (scale - Decimal(1)) * Decimal(1_000_000)
        if abs(drift - expected) > Decimal("0.000001"):
            raise ValueError("declared drift is inconsistent with scale")
        return self


class ReferenceFieldContract(StrictContractModel):
    field_name: StableId
    dtype_id: StableId
    unit: UnitName
    nullable: StrictBool

    @field_validator("dtype_id")
    @classmethod
    def require_allowlisted_dtype(cls, value: str) -> str:
        if value not in REFERENCE_DTYPE_IDS:
            raise ValueError("reference dtype is not in the v0.1 primitive allowlist")
        return value


class ReferenceTableContract(StrictContractModel):
    table_role: StableId
    coordinate_frame_id: StableId
    session_time_field: Literal["t_ns"] = "t_ns"
    in_session_field: Literal["in_session"] = "in_session"
    stable_row_id_field: StableId
    fields: tuple[ReferenceFieldContract, ...]
    canonical_order_keys: tuple[StableId, ...]
    table_contract_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_physical_schema(self) -> Self:
        if not self.fields:
            raise ValueError("reference table fields must be non-empty")
        names = tuple(field.field_name for field in self.fields)
        _require_unique(names, "reference table fields")
        by_name = {field.field_name: field for field in self.fields}
        time_field = by_name.get(self.session_time_field)
        if (
            time_field is None
            or time_field.dtype_id != "i64"
            or time_field.unit != "ns"
            or time_field.nullable
        ):
            raise ValueError("t_ns must be a non-nullable i64/ns field")
        mask_field = by_name.get(self.in_session_field)
        if (
            mask_field is None
            or mask_field.dtype_id != "bool"
            or mask_field.unit != "bool"
            or mask_field.nullable
        ):
            raise ValueError("in_session must be a non-nullable bool/bool field")
        if self.stable_row_id_field in {self.session_time_field, self.in_session_field}:
            raise ValueError("stable row field must be separate from t_ns and in_session")
        stable_field = by_name.get(self.stable_row_id_field)
        if (
            stable_field is None
            or stable_field.dtype_id not in REFERENCE_INTEGER_DTYPE_IDS
            or stable_field.nullable
        ):
            raise ValueError("stable row field must be a non-nullable integer")
        if self.canonical_order_keys != (
            self.session_time_field,
            self.stable_row_id_field,
        ):
            raise ValueError("canonical order keys must be (t_ns, stable_row_id_field)")
        return self


class ReferenceResourceChecksum(StrictContractModel):
    path: ResourceRelativePath
    checksum: Sha256Digest


class ResolvedReferenceDescriptor(StrictContractModel):
    reference_id: StableId
    resolution_status: ReferenceResolutionStatus
    source_kind: ReferenceSourceKind
    runtime_view_role: Literal["task_reference"] = "task_reference"
    source_schema_id: StableId
    aligned_schema_id: StableId
    clock_id: StableId
    alignment_contract: ReferenceAlignmentContract
    table_contract: ReferenceTableContract
    resource_checksums: tuple[ReferenceResourceChecksum, ...]
    resource_fingerprint: Sha256Digest | None = None
    aligned_content_fingerprint: Sha256Digest | None = None
    alignment_fingerprint: Sha256Digest | None = None
    absence_reason: StableId | None = None

    @model_validator(mode="after")
    def validate_resolution_matrix(self) -> Self:
        if self.clock_id != self.alignment_contract.source_clock_id:
            raise ValueError("descriptor clock must equal alignment source clock")
        paths = tuple(item.path for item in self.resource_checksums)
        if paths != tuple(sorted(paths)):
            raise ValueError("reference resource checksums must use canonical path order")
        if len(paths) != len(set(paths)) or len(paths) != len({path.casefold() for path in paths}):
            raise ValueError("reference resource paths must be unique without aliases")
        fingerprints = (
            self.resource_fingerprint,
            self.aligned_content_fingerprint,
            self.alignment_fingerprint,
        )
        if self.resolution_status is ReferenceResolutionStatus.PRESENT:
            if not self.resource_checksums or any(value is None for value in fingerprints):
                raise ValueError("present reference requires resources and all fingerprints")
            if self.absence_reason is not None:
                raise ValueError("present reference forbids an absence reason")
        elif (
            self.resource_checksums
            or any(value is not None for value in fingerprints)
            or self.absence_reason is None
        ):
            raise ValueError(
                "absent reference forbids resources/fingerprints and requires a reason"
            )
        return self


class ResolvedReferenceSetSnapshot(StrictContractModel):
    contract_id: Literal["resolved-reference-set"] = "resolved-reference-set"
    contract_version: Literal["0.1.0"] = "0.1.0"
    session_identity: ReferenceSessionIdentity
    descriptors: tuple[ResolvedReferenceDescriptor, ...]
    reference_set_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_descriptor_inventory(self) -> Self:
        if len(self.descriptors) > 1:
            raise ValueError("v0.1 permits at most one resolved reference descriptor")
        ids = tuple(descriptor.reference_id for descriptor in self.descriptors)
        _require_unique(ids, "reference descriptor IDs")
        _require_sorted(ids, "reference descriptor IDs")
        return self


class DependencyKind(StrEnum):
    RESULT = "result_dependency"
    ARTIFACT = "artifact_dependency"
    ALGORITHM_PROFILE = "algorithm_profile_dependency"
    PREPROCESSING = "preprocessing_dependency"


class ScientificValidationStatus(StrEnum):
    ENGINEERING_DEFAULT = "engineering_default"
    EXPERT_REVIEWED = "expert_reviewed"
    CALIBRATED = "calibrated"
    INTERNALLY_VALIDATED = "internally_validated"
    EXTERNALLY_VALIDATED = "externally_validated"
    NOT_SUPPORTED = "not_supported"


class AnchorLifecycle(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


_INPUT_DTYPE_IDS = REFERENCE_DTYPE_IDS
_QUALITY_GATE_FIELD_NAMES = frozenset(
    {
        "quality",
        "quality_gate",
        "quality_gates",
        "quality_transform",
        "min_valid_coverage",
        "failed_quality",
        "invalid_quality",
        "binary_quality_v1",
    }
)


def _require_unique_by(values: tuple[Any, ...], key: Any, label: str) -> None:
    keys = tuple(key(value) for value in values)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} must be unique")


def _validate_projection_paths(
    context_paths: tuple[str, ...], semantic_paths: tuple[str, ...]
) -> None:
    for values, prefix, label in (
        (context_paths, "context.", "context paths"),
        (semantic_paths, "semantic.", "semantic paths"),
    ):
        _require_unique(values, label)
        _require_sorted(values, label)
        if any(not value.startswith(prefix) or value == prefix for value in values):
            raise ValueError(f"{label} must use the {prefix[:-1]} namespace")


def _validate_json_tree(value: object, *, reject_quality_fields: bool = False) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            if reject_quality_fields and str(key) in _QUALITY_GATE_FIELD_NAMES:
                raise ValueError("quality-gate fields are not part of the M4 contract")
            _validate_json_tree(child, reject_quality_fields=reject_quality_fields)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_json_tree(child, reject_quality_fields=reject_quality_fields)


def _validate_descriptor(descriptor: dict[str, JsonValue], payload_kind: str) -> None:
    _validate_json_tree(descriptor)
    if descriptor.get("type") != payload_kind:
        raise ValueError("schema descriptor type must equal payload kind")
    if payload_kind == "table":
        fields = descriptor.get("fields")
        order_keys = descriptor.get("canonical_order_keys")
        if not isinstance(fields, list) or not fields:
            raise ValueError("table descriptor requires non-empty ordered fields")
        if not isinstance(order_keys, list) or not order_keys:
            raise ValueError("table descriptor requires canonical order keys")
        names: list[str] = []
        for field in fields:
            if not isinstance(field, dict) or not {
                "name",
                "dtype",
                "unit",
                "nullable",
            } <= set(field):
                raise ValueError("table descriptor fields require name, dtype, unit and nullable")
            try:
                name = _STABLE_ID_ADAPTER.validate_python(field["name"], strict=True)
                _UNIT_NAME_ADAPTER.validate_python(field["unit"], strict=True)
            except ValueError as error:
                raise ValueError("table descriptor field name or unit is invalid") from error
            dtype = field["dtype"]
            if not isinstance(dtype, str) or dtype not in REFERENCE_DTYPE_IDS:
                raise ValueError("table descriptor field dtype is not a supported primitive")
            if type(field["nullable"]) is not bool:
                raise ValueError("table descriptor field nullable must be a strict boolean")
            names.append(name)
        if len(names) != len(set(names)):
            raise ValueError("table descriptor field names must be unique")
        if (
            any(not isinstance(key, str) for key in order_keys)
            or len(order_keys) != len(set(order_keys))
            or not set(order_keys) <= set(names)
        ):
            raise ValueError("table descriptor order keys must be unique field names")
    else:
        media_type = descriptor.get("media_type")
        content_encoding = descriptor.get("content_encoding")
        if (
            not isinstance(media_type, str)
            or not media_type
            or media_type.strip() != media_type
            or "/" not in media_type
            or not isinstance(content_encoding, str)
            or not content_encoding
            or content_encoding.strip() != content_encoding
        ):
            raise ValueError("blob descriptor requires canonical media_type and content_encoding")
        if "fields" in descriptor or "canonical_order_keys" in descriptor:
            raise ValueError("blob descriptor forbids table fields and canonical order keys")


def _validate_inline_schema_identities(
    schemas: tuple[tuple[str, dict[str, JsonValue], str], ...],
) -> None:
    identities: dict[str, tuple[str, dict[str, JsonValue]]] = {}
    for schema_id, descriptor, payload_kind in schemas:
        identity = (payload_kind, descriptor)
        existing = identities.setdefault(schema_id, identity)
        if existing != identity:
            raise ValueError("one inline schema ID cannot identify multiple descriptors")


def _validate_definition_collections(
    *,
    required_streams: tuple[CoreModality, ...],
    required_context_paths: tuple[str, ...],
    required_semantic_paths: tuple[str, ...],
    required_reference_ids: tuple[str, ...],
    dependencies: tuple[Any, ...],
    artifact_recipes: tuple[Any, ...] = (),
) -> None:
    _require_unique(tuple(item.value for item in required_streams), "required streams")
    _validate_projection_paths(required_context_paths, required_semantic_paths)
    _require_unique(required_reference_ids, "required reference IDs")
    _require_sorted(required_reference_ids, "required reference IDs")
    _require_unique_by(dependencies, lambda item: item.dependency_id, "dependency IDs")
    _require_unique_by(artifact_recipes, lambda item: item.artifact_id, "artifact recipe IDs")
    _validate_inline_schema_identities(
        tuple(
            (item.schema_id, item.schema_descriptor, item.payload_kind) for item in artifact_recipes
        )
    )


class AnchorDependency(StrictContractModel):
    dependency_id: StableId
    kind: DependencyKind
    target_anchor_id: StableId | None = None
    target_resource_id: StableId | None = None
    expected_schema_id: StableId | None = None
    expected_artifact_kind: StableId | None = None
    required: StrictBool

    @model_validator(mode="after")
    def validate_kind_matrix(self) -> Self:
        anchor = self.target_anchor_id is not None
        resource = self.target_resource_id is not None
        schema = self.expected_schema_id is not None
        artifact_kind = self.expected_artifact_kind is not None
        valid = {
            DependencyKind.RESULT: anchor and not resource and schema and not artifact_kind,
            DependencyKind.ARTIFACT: anchor and resource and schema and artifact_kind,
            DependencyKind.ALGORITHM_PROFILE: not anchor
            and resource
            and schema
            and not artifact_kind,
            DependencyKind.PREPROCESSING: not anchor and resource and schema and artifact_kind,
        }[self.kind]
        if not valid:
            raise ValueError("dependency fields do not match dependency kind")
        return self


class AnchorArtifactRecipe(StrictContractModel):
    artifact_id: StableId
    kind: StableId
    schema_id: StableId
    schema_descriptor: dict[StableId, JsonValue]
    payload_kind: Literal["table", "blob"]

    @model_validator(mode="after")
    def validate_inline_schema(self) -> Self:
        _validate_descriptor(self.schema_descriptor, self.payload_kind)
        return self


class PreprocessingDependencySpec(StrictContractModel):
    dependency_id: StableId
    expected_schema_id: StableId
    expected_artifact_kind: StableId


class ResolvedPreprocessingDependencyBinding(StrictContractModel):
    dependency_id: StableId
    target_recipe_id: StableId


class AnchorPluginDefinition(StrictContractModel):
    contract_id: Literal["anchor-plugin-definition"] = "anchor-plugin-definition"
    contract_version: Literal["0.1.0"] = "0.1.0"
    anchor_id: StableId
    definition_version: StableId
    plugin_id: StableId
    plugin_version: StableId
    api_version: Literal["0.1.0"]
    required_streams: tuple[CoreModality, ...]
    required_context_paths: tuple[StableId, ...]
    required_semantic_paths: tuple[StableId, ...]
    required_reference_ids: tuple[StableId, ...]
    dependencies: tuple[AnchorDependency, ...]
    parameter_schema_id: StableId
    measurement_schema_id: StableId
    artifact_recipes: tuple[AnchorArtifactRecipe, ...]

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        _validate_definition_collections(
            required_streams=self.required_streams,
            required_context_paths=self.required_context_paths,
            required_semantic_paths=self.required_semantic_paths,
            required_reference_ids=self.required_reference_ids,
            dependencies=self.dependencies,
            artifact_recipes=self.artifact_recipes,
        )
        return self


class PreprocessingProviderDefinition(StrictContractModel):
    contract_id: Literal["preprocessing-provider-definition"] = "preprocessing-provider-definition"
    contract_version: Literal["0.1.0"] = "0.1.0"
    provider_id: StableId
    provider_version: StableId
    api_version: Literal["0.1.0"]
    required_streams: tuple[CoreModality, ...]
    required_context_paths: tuple[StableId, ...]
    required_semantic_paths: tuple[StableId, ...]
    required_reference_ids: tuple[StableId, ...]
    dependencies: tuple[PreprocessingDependencySpec, ...]
    parameter_schema_id: StableId
    output_schema_id: StableId
    output_schema_descriptor: dict[StableId, JsonValue]
    artifact_kind: StableId
    output_payload_kind: Literal["table", "blob"]

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        _validate_definition_collections(
            required_streams=self.required_streams,
            required_context_paths=self.required_context_paths,
            required_semantic_paths=self.required_semantic_paths,
            required_reference_ids=self.required_reference_ids,
            dependencies=self.dependencies,
        )
        _validate_descriptor(self.output_schema_descriptor, self.output_payload_kind)
        return self


class ContentMemberIdentity(StrictContractModel):
    package_relative_path: BundleRelativePath
    content_sha256: Sha256Digest


class PythonRuntimeIdentity(StrictContractModel):
    implementation_name: str
    version: tuple[NonNegativeInt, NonNegativeInt, NonNegativeInt]
    cache_tag: str
    soabi: str


class NumericRuntimeIdentity(StrictContractModel):
    normalized_name: str
    version: str
    record_content_sha256: Sha256Digest


def _validate_registry_members(
    implementation_members: tuple[ContentMemberIdentity, ...],
    resource_members: tuple[ContentMemberIdentity, ...],
    numeric_runtimes: tuple[NumericRuntimeIdentity, ...],
) -> None:
    members = (*implementation_members, *resource_members)
    paths = tuple(item.package_relative_path for item in members)
    if len(paths) != len(set(paths)) or len(paths) != len({path.casefold() for path in paths}):
        raise ValueError("registry member paths must be unique without aliases")
    for group, label in (
        (implementation_members, "implementation members"),
        (resource_members, "resource members"),
    ):
        group_paths = tuple(item.package_relative_path for item in group)
        if group_paths != tuple(sorted(group_paths)):
            raise ValueError(f"registry {label} must use canonical path order")
    _require_unique_by(
        numeric_runtimes, lambda item: item.normalized_name.casefold(), "numeric runtimes"
    )
    runtime_names = tuple(item.normalized_name.casefold() for item in numeric_runtimes)
    if runtime_names != tuple(sorted(runtime_names)):
        raise ValueError("numeric runtimes must use canonical normalized-name order")


class PluginRegistryEntry(StrictContractModel):
    anchor_id: StableId
    definition_version: StableId
    plugin_id: StableId
    plugin_version: StableId
    api_version: Literal["0.1.0"]
    factory_module: str
    factory_symbol: str
    allowed_package_namespace: str
    definition_fingerprint: Sha256Digest
    parameter_schema_id: StableId
    parameter_schema_sha256: Sha256Digest
    measurement_schema_id: StableId
    measurement_schema_sha256: Sha256Digest
    artifact_schema_hashes: dict[StableId, Sha256Digest]
    implementation_members: tuple[ContentMemberIdentity, ...]
    resource_members: tuple[ContentMemberIdentity, ...]
    python_runtime: PythonRuntimeIdentity
    numeric_runtimes: tuple[NumericRuntimeIdentity, ...]
    implementation_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_registry_entry(self) -> Self:
        if not (
            self.factory_module == self.allowed_package_namespace
            or self.factory_module.startswith(f"{self.allowed_package_namespace}.")
        ):
            raise ValueError("factory module lies outside the allowed package namespace")
        if tuple(self.artifact_schema_hashes) != tuple(sorted(self.artifact_schema_hashes)):
            raise ValueError("artifact schema hashes must use canonical schema order")
        _validate_registry_members(
            self.implementation_members, self.resource_members, self.numeric_runtimes
        )
        return self


class PreprocessingRegistryEntry(StrictContractModel):
    provider_id: StableId
    provider_version: StableId
    api_version: Literal["0.1.0"]
    factory_module: str
    factory_symbol: str
    allowed_package_namespace: str
    definition_fingerprint: Sha256Digest
    parameter_schema_id: StableId
    parameter_schema_sha256: Sha256Digest
    output_schema_id: StableId
    output_schema_sha256: Sha256Digest
    artifact_kind: StableId
    output_payload_kind: Literal["table", "blob"]
    implementation_members: tuple[ContentMemberIdentity, ...]
    resource_members: tuple[ContentMemberIdentity, ...]
    python_runtime: PythonRuntimeIdentity
    numeric_runtimes: tuple[NumericRuntimeIdentity, ...]
    implementation_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_registry_entry(self) -> Self:
        if not (
            self.factory_module == self.allowed_package_namespace
            or self.factory_module.startswith(f"{self.allowed_package_namespace}.")
        ):
            raise ValueError("factory module lies outside the allowed package namespace")
        _validate_registry_members(
            self.implementation_members, self.resource_members, self.numeric_runtimes
        )
        return self


class AnchorRuntimeRegistry(StrictContractModel):
    contract_id: Literal["anchor-runtime-registry"] = "anchor-runtime-registry"
    contract_version: Literal["0.1.0"] = "0.1.0"
    entries: tuple[PluginRegistryEntry, ...]
    preprocessors: tuple[PreprocessingRegistryEntry, ...]

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        entry_keys = tuple((item.anchor_id, item.definition_version) for item in self.entries)
        if entry_keys != tuple(sorted(entry_keys)):
            raise ValueError("registry entries must use canonical anchor order")
        preprocessor_keys = tuple(
            (item.provider_id, item.provider_version) for item in self.preprocessors
        )
        if preprocessor_keys != tuple(sorted(preprocessor_keys)):
            raise ValueError("registry preprocessors must use canonical provider order")
        _require_unique_by(
            self.entries,
            lambda item: (item.anchor_id, item.definition_version),
            "registry anchor keys",
        )
        _require_unique_by(
            self.entries,
            lambda item: (item.plugin_id, item.plugin_version),
            "registry plugin keys",
        )
        _require_unique_by(
            self.preprocessors,
            lambda item: (item.provider_id, item.provider_version),
            "registry provider keys",
        )
        return self


class AnchorCatalogEntry(StrictContractModel):
    anchor_id: StableId
    definition_version: StableId
    lifecycle: AnchorLifecycle
    required: StrictBool
    canonical_order: NonNegativeInt
    plugin_id: StableId
    plugin_version: StableId
    parameter_schema_id: StableId
    scorer_id: StableId
    required_inputs: tuple[StableId, ...]
    dependencies: tuple[AnchorDependency, ...]
    artifact_recipes: tuple[AnchorArtifactRecipe, ...]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        _require_unique(self.required_inputs, "catalog required inputs")
        _require_unique_by(self.dependencies, lambda item: item.dependency_id, "dependency IDs")
        _require_unique_by(
            self.artifact_recipes, lambda item: item.artifact_id, "artifact recipe IDs"
        )
        return self


class AnchorCatalog(StrictContractModel):
    contract_id: Literal["anchor-catalog"] = "anchor-catalog"
    contract_version: Literal["0.1.0"] = "0.1.0"
    profile_id: StableId
    profile_version: StableId
    scientific_validation_status: ScientificValidationStatus
    entries: tuple[AnchorCatalogEntry, ...]
    catalog_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        _require_unique_by(
            self.entries,
            lambda item: (item.anchor_id, item.definition_version),
            "catalog anchor keys",
        )
        ordered = tuple(
            sorted(self.entries, key=lambda item: (item.canonical_order, item.anchor_id))
        )
        if self.entries != ordered:
            raise ValueError("catalog entries must use canonical order")
        _validate_inline_schema_identities(
            tuple(
                (recipe.schema_id, recipe.schema_descriptor, recipe.payload_kind)
                for entry in self.entries
                for recipe in entry.artifact_recipes
            )
        )
        return self


class ResolvedAlgorithmProfile(StrictContractModel):
    profile_id: StableId
    profile_version: StableId
    parameters: dict[StableId, JsonValue]
    parameter_hash: Sha256Digest
    implementation_digest: Sha256Digest
    output_schema_id: StableId

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _validate_json_tree(value, reject_quality_fields=True)
        return value


class ResolvedInputFieldContract(StrictContractModel):
    field_name: StableId
    dtype_id: StableId
    unit: UnitName
    nullable: StrictBool

    @field_validator("dtype_id")
    @classmethod
    def require_primitive_dtype(cls, value: str) -> str:
        if value not in _INPUT_DTYPE_IDS:
            raise ValueError("dtype_id is not an allowed primitive dtype")
        return value


class ResolvedInputTableContract(StrictContractModel):
    modality: CoreModality
    table_role: StableId
    stream_aligned_schema_id: StableId
    table_aligned_schema_id: StableId
    coordinate_frame_id: StableId
    fields: tuple[ResolvedInputFieldContract, ...]

    @field_validator("fields")
    @classmethod
    def validate_fields(
        cls, value: tuple[ResolvedInputFieldContract, ...]
    ) -> tuple[ResolvedInputFieldContract, ...]:
        if not value:
            raise ValueError("input table fields must be non-empty")
        _require_unique_by(value, lambda field: field.field_name, "input table field names")
        return value


class ResolvedPreprocessingRecipe(StrictContractModel):
    recipe_id: StableId
    recipe_version: StableId
    provider_id: StableId
    provider_version: StableId
    api_version: Literal["0.1.0"]
    definition_fingerprint: Sha256Digest
    implementation_digest: Sha256Digest
    parameter_schema_id: StableId
    parameter_schema_sha256: Sha256Digest
    parameters: dict[StableId, JsonValue]
    parameter_hash: Sha256Digest
    required_streams: tuple[CoreModality, ...]
    required_context_paths: tuple[StableId, ...]
    required_semantic_paths: tuple[StableId, ...]
    required_reference_ids: tuple[StableId, ...]
    dependency_specs: tuple[PreprocessingDependencySpec, ...]
    dependency_bindings: tuple[ResolvedPreprocessingDependencyBinding, ...]
    output_schema_id: StableId
    output_schema_descriptor: dict[StableId, JsonValue]
    output_schema_sha256: Sha256Digest
    artifact_kind: StableId
    output_payload_kind: Literal["table", "blob"]
    scope_policy: Literal["session", "phase", "event", "window"]

    @model_validator(mode="after")
    def validate_recipe(self) -> Self:
        _validate_definition_collections(
            required_streams=self.required_streams,
            required_context_paths=self.required_context_paths,
            required_semantic_paths=self.required_semantic_paths,
            required_reference_ids=self.required_reference_ids,
            dependencies=self.dependency_specs,
        )
        _require_unique_by(
            self.dependency_bindings, lambda item: item.dependency_id, "dependency bindings"
        )
        if {item.dependency_id for item in self.dependency_specs} != {
            item.dependency_id for item in self.dependency_bindings
        }:
            raise ValueError("provider dependency specs and bindings must match exactly")
        _validate_descriptor(self.output_schema_descriptor, self.output_payload_kind)
        _validate_json_tree(self.parameters, reject_quality_fields=True)
        return self


class ScorerPolicy(StrictContractModel):
    scorer_id: StableId
    scorer_version: StableId
    policy_schema_id: StableId
    parameters: dict[StableId, JsonValue]
    policy_hash: Sha256Digest

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _validate_json_tree(value, reject_quality_fields=True)
        return value


class AnchorExecutionEntry(StrictContractModel):
    anchor_id: StableId
    definition_version: StableId
    lifecycle: Literal["active"]
    canonical_order: NonNegativeInt
    plugin_id: StableId
    plugin_version: StableId
    api_version: Literal["0.1.0"]
    definition_fingerprint: Sha256Digest
    implementation_digest: Sha256Digest
    parameter_schema_id: StableId
    parameters: dict[StableId, JsonValue]
    parameter_hash: Sha256Digest
    required_streams: tuple[CoreModality, ...]
    required_context_paths: tuple[StableId, ...]
    required_semantic_paths: tuple[StableId, ...]
    required_reference_ids: tuple[StableId, ...]
    applicability: SemanticApplicabilityStatus
    phase_scope: tuple[StableId, ...]
    event_scope: tuple[StableId, ...]
    dependencies: tuple[AnchorDependency, ...]
    measurement_schema_id: StableId
    result_schema_id: StableId
    artifact_recipes: tuple[AnchorArtifactRecipe, ...]
    temporal_recipe: dict[StableId, JsonValue]
    scorer_policy: ScorerPolicy

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        _validate_definition_collections(
            required_streams=self.required_streams,
            required_context_paths=self.required_context_paths,
            required_semantic_paths=self.required_semantic_paths,
            required_reference_ids=self.required_reference_ids,
            dependencies=self.dependencies,
            artifact_recipes=self.artifact_recipes,
        )
        for values, label in (
            (self.phase_scope, "phase scope"),
            (self.event_scope, "event scope"),
        ):
            _require_unique(values, label)
            _require_sorted(values, label)
        _validate_json_tree(self.parameters, reject_quality_fields=True)
        _validate_json_tree(self.temporal_recipe, reject_quality_fields=True)
        return self


class AnchorExecutionPlan(StrictContractModel):
    contract_id: Literal["anchor-execution-plan"] = "anchor-execution-plan"
    contract_version: Literal["0.1.0"] = "0.1.0"
    plan_id: StableId
    model_profile_id: StableId
    scientific_validation_status: ScientificValidationStatus
    catalog_fingerprint: Sha256Digest
    registry_fingerprint: Sha256Digest
    source_snapshot_fingerprint: Sha256Digest
    synchronization_fingerprint: Sha256Digest
    semantic_snapshot_fingerprint: Sha256Digest
    reference_set_fingerprint: Sha256Digest
    entries: tuple[AnchorExecutionEntry, ...]
    input_table_contracts: tuple[ResolvedInputTableContract, ...]
    algorithm_profiles: tuple[ResolvedAlgorithmProfile, ...]
    preprocessing_recipes: tuple[ResolvedPreprocessingRecipe, ...]
    parameter_fingerprint: Sha256Digest
    plan_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        _validate_inline_schema_identities(
            (
                *tuple(
                    (recipe.schema_id, recipe.schema_descriptor, recipe.payload_kind)
                    for entry in self.entries
                    for recipe in entry.artifact_recipes
                ),
                *tuple(
                    (
                        recipe.output_schema_id,
                        recipe.output_schema_descriptor,
                        recipe.output_payload_kind,
                    )
                    for recipe in self.preprocessing_recipes
                ),
            )
        )
        self._validate_entry_inventory()
        self._validate_input_contracts()
        self._validate_anchor_dependencies()
        self._validate_provider_dependencies()
        return self

    def _validate_entry_inventory(self) -> None:
        _require_unique_by(self.entries, lambda item: item.anchor_id, "execution anchor IDs")
        ordered = tuple(
            sorted(self.entries, key=lambda item: (item.canonical_order, item.anchor_id))
        )
        if self.entries != ordered:
            raise ValueError("execution entries must use canonical order")
        _require_unique_by(
            self.algorithm_profiles, lambda item: item.profile_id, "algorithm profile IDs"
        )
        _require_unique_by(
            self.preprocessing_recipes, lambda item: item.recipe_id, "preprocessing recipe IDs"
        )

    def _validate_input_contracts(self) -> None:
        keys = tuple((item.modality.value, item.table_role) for item in self.input_table_contracts)
        if len(keys) != len(set(keys)):
            raise ValueError("input table contract keys must be unique")
        if keys != tuple(sorted(keys)):
            raise ValueError("input table contracts must use canonical order")
        stream_schema_by_modality: dict[CoreModality, str] = {}
        for contract in self.input_table_contracts:
            existing = stream_schema_by_modality.setdefault(
                contract.modality, contract.stream_aligned_schema_id
            )
            if existing != contract.stream_aligned_schema_id:
                raise ValueError("one modality cannot declare inconsistent stream schemas")
        required_modalities = {
            *(modality for entry in self.entries for modality in entry.required_streams),
            *(
                modality
                for recipe in self.preprocessing_recipes
                for modality in recipe.required_streams
            ),
        }
        if set(stream_schema_by_modality) != required_modalities:
            raise ValueError("input table contracts must exactly cover required modalities")

    def _validate_anchor_dependencies(self) -> None:
        entries = {item.anchor_id: item for item in self.entries}
        profiles = {item.profile_id: item for item in self.algorithm_profiles}
        recipes = {item.recipe_id: item for item in self.preprocessing_recipes}
        graph: dict[str, set[str]] = {anchor_id: set() for anchor_id in entries}
        for consumer in self.entries:
            for dependency in consumer.dependencies:
                if dependency.kind is DependencyKind.RESULT:
                    producer = entries.get(dependency.target_anchor_id or "")
                    if (
                        producer is None
                        or producer.result_schema_id != dependency.expected_schema_id
                    ):
                        raise ValueError("result dependency does not resolve exactly")
                    graph[consumer.anchor_id].add(producer.anchor_id)
                elif dependency.kind is DependencyKind.ARTIFACT:
                    producer = entries.get(dependency.target_anchor_id or "")
                    if producer is None:
                        raise ValueError("artifact dependency does not resolve exactly")
                    matches = [
                        recipe
                        for recipe in producer.artifact_recipes
                        if recipe.artifact_id == dependency.target_resource_id
                        and recipe.schema_id == dependency.expected_schema_id
                        and recipe.kind == dependency.expected_artifact_kind
                    ]
                    if len(matches) != 1:
                        raise ValueError("artifact dependency does not resolve exactly")
                    graph[consumer.anchor_id].add(producer.anchor_id)
                elif dependency.kind is DependencyKind.ALGORITHM_PROFILE:
                    profile = profiles.get(dependency.target_resource_id or "")
                    if profile is None or profile.output_schema_id != dependency.expected_schema_id:
                        raise ValueError("algorithm profile dependency does not resolve exactly")
                else:
                    recipe = recipes.get(dependency.target_resource_id or "")
                    if (
                        recipe is None
                        or recipe.output_schema_id != dependency.expected_schema_id
                        or recipe.artifact_kind != dependency.expected_artifact_kind
                    ):
                        raise ValueError("preprocessing dependency does not resolve exactly")
        self._require_acyclic(graph, "anchor dependency graph")

    def _validate_provider_dependencies(self) -> None:
        recipes = {item.recipe_id: item for item in self.preprocessing_recipes}
        graph: dict[str, set[str]] = {recipe_id: set() for recipe_id in recipes}
        provider_contracts: dict[tuple[str, str], tuple[str, str]] = {}
        for recipe in self.preprocessing_recipes:
            provider_key = (recipe.provider_id, recipe.provider_version)
            contract = (recipe.parameter_schema_id, recipe.parameter_schema_sha256)
            existing = provider_contracts.setdefault(provider_key, contract)
            if existing != contract:
                raise ValueError("one provider version cannot use different parameter schemas")
            specs = {item.dependency_id: item for item in recipe.dependency_specs}
            for binding in recipe.dependency_bindings:
                target = recipes.get(binding.target_recipe_id)
                spec = specs[binding.dependency_id]
                if (
                    target is None
                    or target.output_schema_id != spec.expected_schema_id
                    or target.artifact_kind != spec.expected_artifact_kind
                ):
                    raise ValueError("provider dependency does not resolve exactly")
                if target.scope_policy != recipe.scope_policy:
                    raise ValueError("provider dependency scope policies must match")
                graph[recipe.recipe_id].add(target.recipe_id)
        self._require_acyclic(graph, "preprocessing dependency graph")

    @staticmethod
    def _require_acyclic(graph: dict[str, set[str]], label: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError(f"{label} must be acyclic")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)


__all__ = [
    "AoiDefinition",
    "AoiGeometryKind",
    "AnchorApplicability",
    "AnchorArtifactRecipe",
    "AnchorCatalog",
    "AnchorCatalogEntry",
    "AnchorDependency",
    "AnchorExecutionEntry",
    "AnchorExecutionPlan",
    "AnchorLifecycle",
    "AnchorPluginDefinition",
    "AnchorRuntimeRegistry",
    "AuditText",
    "BaselineChannelBinding",
    "BaselineDefinition",
    "BaselineModality",
    "ContentMemberIdentity",
    "ControlEffectMapping",
    "DependencyKind",
    "DynamicAoiSource",
    "EnvelopeAxisLimit",
    "EnvelopeDefinition",
    "NumericRuntimeIdentity",
    "PluginRegistryEntry",
    "PreprocessingDependencySpec",
    "PreprocessingProviderDefinition",
    "PreprocessingRegistryEntry",
    "PythonRuntimeIdentity",
    "REFERENCE_DTYPE_IDS",
    "ReferenceAlignmentContract",
    "ReferenceFieldContract",
    "ReferenceResolutionStatus",
    "ReferenceResourceChecksum",
    "ReferenceSessionIdentity",
    "ReferenceSourceKind",
    "ReferenceTableContract",
    "ResolvedAlgorithmProfile",
    "ResolvedInputFieldContract",
    "ResolvedInputTableContract",
    "ResolvedPreprocessingDependencyBinding",
    "ResolvedPreprocessingRecipe",
    "ResolvedReferenceDescriptor",
    "ResolvedReferenceSetSnapshot",
    "ResourceRelativePath",
    "ScientificValidationStatus",
    "ScorerPolicy",
    "SemanticApplicabilityStatus",
    "SemanticEvent",
    "SemanticPhase",
    "SemanticVector",
    "SessionSemanticSnapshot",
    "TaskTargetDefinition",
    "UnitName",
]
