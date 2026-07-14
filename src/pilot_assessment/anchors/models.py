"""Immutable runtime containers used by M4 reference binding."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, NoReturn

import polars as pl
from pydantic import TypeAdapter

from pilot_assessment.contracts.anchor_execution import (
    AnchorExecutionPlan,
    ReferenceAlignmentContract,
    ReferenceSessionIdentity,
    ReferenceSourceKind,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.common import Sha256Digest, StableId
from pilot_assessment.contracts.synchronization import (
    SynchronizationDisposition,
    SynchronizationItemStatus,
    SynchronizationReport,
)
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedSession,
    AlignedStreamView,
)

_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_SHA256_ADAPTER = TypeAdapter(Sha256Digest)

_REQUEST_ERROR_CODES = frozenset(
    {
        "request_session_mismatch",
        "request_semantic_identity_mismatch",
        "request_reference_inventory_mismatch",
        "request_reference_provenance_mismatch",
        "request_fingerprint_mismatch",
    }
)

_POLARS_DTYPES: Mapping[str, type[pl.DataType]] = MappingProxyType(
    {
        "bool": pl.Boolean,
        "i8": pl.Int8,
        "i16": pl.Int16,
        "i32": pl.Int32,
        "i64": pl.Int64,
        "u8": pl.UInt8,
        "u16": pl.UInt16,
        "u32": pl.UInt32,
        "u64": pl.UInt64,
        "f32": pl.Float32,
        "f64": pl.Float64,
        "utf8": pl.String,
    }
)


def _strict_stable_id(value: object, *, field_name: str) -> str:
    try:
        return _STABLE_ID_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid stable ID") from error


def _strict_sha256(value: object, *, field_name: str) -> str:
    try:
        return _SHA256_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a SHA-256 digest") from error


@dataclass(frozen=True, slots=True)
class ReferenceViewCandidate:
    """One trusted, session-bound runtime reference candidate."""

    reference_id: StableId
    source_kind: ReferenceSourceKind
    session_identity: ReferenceSessionIdentity
    aligned_view: AlignedStreamView
    alignment_contract: ReferenceAlignmentContract
    table_contract: ReferenceTableContract
    resource_fingerprint: Sha256Digest
    aligned_content_fingerprint: Sha256Digest
    alignment_fingerprint: Sha256Digest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_id",
            _strict_stable_id(self.reference_id, field_name="reference_id"),
        )
        if not isinstance(self.source_kind, ReferenceSourceKind):
            raise TypeError("source_kind must be a ReferenceSourceKind")
        if not isinstance(self.session_identity, ReferenceSessionIdentity):
            raise TypeError("session_identity must be a ReferenceSessionIdentity")
        if not isinstance(self.aligned_view, AlignedStreamView):
            raise TypeError("aligned_view must be an AlignedStreamView")
        if not isinstance(self.alignment_contract, ReferenceAlignmentContract):
            raise TypeError("alignment_contract must be a ReferenceAlignmentContract")
        if not isinstance(self.table_contract, ReferenceTableContract):
            raise TypeError("table_contract must be a ReferenceTableContract")
        for field_name in (
            "resource_fingerprint",
            "aligned_content_fingerprint",
            "alignment_fingerprint",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_sha256(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """One descriptor paired with its exact runtime view, when present."""

    descriptor: ResolvedReferenceDescriptor
    aligned_view: AlignedStreamView | None

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, ResolvedReferenceDescriptor):
            raise TypeError("descriptor must be a ResolvedReferenceDescriptor")
        if self.aligned_view is not None and not isinstance(self.aligned_view, AlignedStreamView):
            raise TypeError("aligned_view must be an AlignedStreamView or None")

        status = self.descriptor.resolution_status.value
        if (status == "present") != (self.aligned_view is not None):
            raise ValueError("present descriptors require a view and absent descriptors forbid one")


@dataclass(frozen=True, slots=True)
class ResolvedReferenceSet:
    """Frozen runtime reference inventory for one aligned session."""

    session_identity: ReferenceSessionIdentity
    entries: Mapping[str, ResolvedReference]
    reference_set_fingerprint: Sha256Digest

    def __post_init__(self) -> None:
        if not isinstance(self.session_identity, ReferenceSessionIdentity):
            raise TypeError("session_identity must be a ReferenceSessionIdentity")
        if not isinstance(self.entries, Mapping):
            raise TypeError("entries must be a mapping")

        frozen_entries: dict[str, ResolvedReference] = {}
        for raw_key, entry in self.entries.items():
            key = _strict_stable_id(raw_key, field_name="entries key")
            if not isinstance(entry, ResolvedReference):
                raise TypeError("entries values must be ResolvedReference instances")
            if key != entry.descriptor.reference_id:
                raise ValueError("entry key must equal descriptor reference_id")
            frozen_entries[key] = entry

        object.__setattr__(self, "entries", MappingProxyType(frozen_entries))
        object.__setattr__(
            self,
            "reference_set_fingerprint",
            _strict_sha256(
                self.reference_set_fingerprint,
                field_name="reference_set_fingerprint",
            ),
        )


class AnchorRequestValidationError(ValueError):
    """Stable pre-request failure; no M4 report exists at this boundary."""

    code: str
    details: Mapping[str, str]

    def __init__(self, code: str, details: Mapping[str, str] | None = None) -> None:
        if code not in _REQUEST_ERROR_CODES:
            raise ValueError("unknown anchor request validation error code")
        stable_details = dict(details or {})
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in stable_details.items()
        ):
            raise TypeError("request validation details must be stable string fields")
        self.code = code
        self.details = MappingProxyType(stable_details)
        suffix = ", ".join(f"{key}={value}" for key, value in sorted(stable_details.items()))
        super().__init__(f"{code}: {suffix}" if suffix else code)


def _request_error(code: str, *, field: str, reason: str) -> NoReturn:
    raise AnchorRequestValidationError(code, {"field": field, "reason": reason})


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _modality_value(value: object) -> str:
    raw = _enum_value(value)
    if not isinstance(raw, str):
        _request_error(
            "request_semantic_identity_mismatch",
            field="input_table_contracts.modality",
            reason="invalid_modality",
        )
    return raw


def _required_modalities(plan: Any) -> set[str]:
    required: set[str] = set()
    for owner in (*tuple(plan.entries), *tuple(plan.preprocessing_recipes)):
        required.update(_modality_value(item) for item in owner.required_streams)
    return required


def _required_reference_ids(plan: Any) -> set[str]:
    required: set[str] = set()
    for owner in (*tuple(plan.entries), *tuple(plan.preprocessing_recipes)):
        required.update(owner.required_reference_ids)
    return required


@dataclass(frozen=True, slots=True)
class AnchorEvaluationRequest:
    """Fully closed immutable M4 input, validated before any service access."""

    aligned_session: AlignedSession
    synchronization_report: SynchronizationReport
    session_semantic_snapshot: SessionSemanticSnapshot
    execution_plan: AnchorExecutionPlan
    resolved_references: ResolvedReferenceSet

    def __post_init__(self) -> None:
        self._validate_session_identity()
        self._validate_semantic_relations()
        self._validate_reference_inventory_and_provenance()
        self._validate_fingerprint_closure()

    def _validate_session_identity(self) -> None:
        session = self.aligned_session
        report = self.synchronization_report
        semantic = self.session_semantic_snapshot
        references = self.resolved_references

        if (
            not isinstance(session, AlignedSession)
            or not isinstance(report, SynchronizationReport)
            or not isinstance(semantic, SessionSemanticSnapshot)
            or not isinstance(references, ResolvedReferenceSet)
        ):
            _request_error(
                "request_session_mismatch",
                field="request_inputs",
                reason="invalid_runtime_type",
            )
        if (
            report.disposition is SynchronizationDisposition.BLOCKED
            or not report.can_continue_to_anchor_availability
            or report.session_window is None
        ):
            _request_error(
                "request_session_mismatch",
                field="synchronization_report.disposition",
                reason="m3_blocked",
            )

        report_aligned = {
            modality
            for modality, result in report.stream_results.items()
            if result.synchronization_status is SynchronizationItemStatus.ALIGNED
        }
        if report_aligned != set(session.streams):
            _request_error(
                "request_session_mismatch",
                field="aligned_stream_inventory",
                reason="report_view_inventory_mismatch",
            )

        identity_values = {
            "aligned_session": session.session_id,
            "synchronization_report": report.session_id,
            "semantic_snapshot": semantic.session_id,
            "resolved_references": references.session_identity.session_id,
        }
        if len(set(identity_values.values())) != 1:
            _request_error(
                "request_session_mismatch",
                field="session_id",
                reason="identity_mismatch",
            )

        source_values = (
            session.source_snapshot_fingerprint,
            report.source_snapshot_fingerprint,
            semantic.source_snapshot_fingerprint,
            references.session_identity.source_snapshot_fingerprint,
        )
        synchronization_values = (
            session.synchronization_fingerprint,
            report.synchronization_fingerprint,
            semantic.synchronization_fingerprint,
            references.session_identity.synchronization_fingerprint,
        )
        if len(set(source_values)) != 1:
            _request_error(
                "request_session_mismatch",
                field="source_snapshot_fingerprint",
                reason="identity_mismatch",
            )
        if len(set(synchronization_values)) != 1:
            _request_error(
                "request_session_mismatch",
                field="synchronization_fingerprint",
                reason="identity_mismatch",
            )
        if session.window != report.session_window:
            _request_error(
                "request_session_mismatch",
                field="session_window",
                reason="window_mismatch",
            )
        if (
            semantic.session_start_t_ns != session.window.start_t_ns
            or semantic.session_end_t_ns != session.window.end_t_ns
            or references.session_identity.session_start_t_ns != session.window.start_t_ns
            or references.session_identity.session_end_t_ns != session.window.end_t_ns
        ):
            _request_error(
                "request_session_mismatch",
                field="session_window",
                reason="snapshot_window_mismatch",
            )

    def _validate_semantic_relations(self) -> None:
        session = self.aligned_session
        report = self.synchronization_report
        semantic = self.session_semantic_snapshot
        plan = self.execution_plan
        annotation = report.annotation_result

        if not isinstance(plan, AnchorExecutionPlan):
            _request_error(
                "request_semantic_identity_mismatch",
                field="execution_plan",
                reason="invalid_runtime_type",
            )
        if not isinstance(session.annotations, AlignedAnnotations):
            _request_error(
                "request_semantic_identity_mismatch",
                field="aligned_session.annotations",
                reason="invalid_runtime_type",
            )

        if (
            annotation is None
            or annotation.synchronization_status is not SynchronizationItemStatus.ALIGNED
        ):
            _request_error(
                "request_semantic_identity_mismatch",
                field="annotation_result",
                reason="annotations_not_aligned",
            )
        if (
            semantic.annotation_revision != session.annotations.revision
            or semantic.annotation_revision != annotation.revision
            or semantic.synthetic_semantics_unvalidated
            != session.annotations.synthetic_semantics_unvalidated
            or semantic.synthetic_semantics_unvalidated
            != annotation.synthetic_semantics_unvalidated
        ):
            _request_error(
                "request_semantic_identity_mismatch",
                field="annotations",
                reason="annotation_identity_mismatch",
            )

        semantic_phases = tuple(
            (item.phase_id, item.start_t_ns, item.end_t_ns) for item in semantic.phases
        )
        aligned_phases = tuple(
            (item.phase_id, item.start_t_ns, item.end_t_ns) for item in session.annotations.phases
        )
        semantic_events = tuple(
            (item.event_id, item.event_type, item.t_ns, item.duration_ns)
            for item in semantic.events
        )
        aligned_events = tuple(
            (item.event_id, item.event_type, item.t_ns, item.duration_ns)
            for item in session.annotations.events
        )
        semantic_baselines = tuple(
            (
                item.baseline_id,
                item.start_t_ns,
                item.end_t_ns,
                item.condition_id,
                item.annotation_valid,
                item.annotation_exclusion_reason,
            )
            for item in semantic.baselines
        )
        aligned_baselines = tuple(
            (
                item.interval_id,
                item.start_t_ns,
                item.end_t_ns,
                item.condition,
                item.valid,
                item.exclusion_reason,
            )
            for item in session.annotations.baseline_intervals
        )
        annotation_schema_ids = {
            "phases": annotation.phase_schema_id,
            "events": annotation.event_schema_id,
            "baselines": annotation.baseline_schema_id,
        }
        if (
            semantic_phases != aligned_phases
            or semantic_events != aligned_events
            or semantic_baselines != aligned_baselines
            or dict(session.annotations.source_schema_ids) != annotation_schema_ids
            or annotation.phase_count != len(aligned_phases)
            or annotation.event_count != len(aligned_events)
            or annotation.baseline_count != len(aligned_baselines)
        ):
            _request_error(
                "request_semantic_identity_mismatch",
                field="annotations",
                reason="annotation_content_mismatch",
            )
        plan_by_anchor = {entry.anchor_id: entry for entry in plan.entries}
        applicability_by_anchor = {item.anchor_id: item for item in semantic.applicability}
        if set(plan_by_anchor) != set(applicability_by_anchor):
            _request_error(
                "request_semantic_identity_mismatch",
                field="applicability",
                reason="anchor_inventory_mismatch",
            )
        for anchor_id, entry in plan_by_anchor.items():
            applicability = applicability_by_anchor[anchor_id]
            if (
                entry.applicability is not applicability.status
                or entry.phase_scope != applicability.phase_ids
                or entry.event_scope != applicability.event_ids
            ):
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"applicability.{anchor_id}",
                    reason="scope_or_status_mismatch",
                )

        contracts_by_key: dict[tuple[str, str], Any] = {}
        for contract in plan.input_table_contracts:
            key = (_modality_value(contract.modality), contract.table_role)
            contracts_by_key[key] = contract

        required_modalities = _required_modalities(plan)
        for modality in sorted(required_modalities):
            result = report.stream_results.get(modality)
            if result is None:
                _request_error(
                    "request_semantic_identity_mismatch",
                    field="stream_results",
                    reason="required_modality_missing",
                )
            if result.synchronization_status is not SynchronizationItemStatus.ALIGNED:
                continue
            view = session.streams.get(modality)
            if view is None:
                _request_error(
                    "request_semantic_identity_mismatch",
                    field="aligned_stream",
                    reason="required_view_missing",
                )
            modality_contracts = {
                role: contract
                for (contract_modality, role), contract in contracts_by_key.items()
                if contract_modality == modality
            }
            if set(modality_contracts) != set(view.tables) or set(modality_contracts) != set(
                result.artifacts
            ):
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"input_table_contracts.{modality}",
                    reason="table_inventory_mismatch",
                )
            if (
                view.source_schema_id != result.source_schema_id
                or view.aligned_schema_id != result.aligned_schema_id
                or result.clock is None
                or view.clock_id != result.clock.clock_id
            ):
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"aligned_stream.{modality}",
                    reason="stream_contract_mismatch",
                )
            for role, contract in modality_contracts.items():
                if (
                    contract.stream_aligned_schema_id != view.aligned_schema_id
                    or contract.table_aligned_schema_id != result.artifacts[role].aligned_schema_id
                ):
                    _request_error(
                        "request_semantic_identity_mismatch",
                        field=f"input_table_contracts.{modality}.{role}",
                        reason="schema_mismatch",
                    )
                self._validate_live_table(view.tables[role], contract, modality, role)

        for aoi in semantic.aois:
            source = aoi.dynamic_source
            if source is None:
                continue
            contract = contracts_by_key.get(("I", source.table_role))
            if contract is None:
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"dynamic_aoi.{aoi.aoi_id}",
                    reason="input_contract_missing",
                )
            fields = {field.field_name: field for field in contract.fields}
            geometry_ids = set(source.geometry_field_ids)
            ordered_geometry_ids = tuple(
                field.field_name for field in contract.fields if field.field_name in geometry_ids
            )
            if (
                source.aligned_schema_id != contract.table_aligned_schema_id
                or source.coordinate_frame_id != contract.coordinate_frame_id
                or source.frame_id_field not in fields
                or source.aoi_id_field not in fields
                or source.frame_id_field == source.aoi_id_field
                or source.frame_id_field in geometry_ids
                or source.aoi_id_field in geometry_ids
                or any(field_id not in fields for field_id in source.geometry_field_ids)
                or ordered_geometry_ids != source.geometry_field_ids
                or any(
                    fields[field_id].unit != source.unit for field_id in source.geometry_field_ids
                )
            ):
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"dynamic_aoi.{aoi.aoi_id}",
                    reason="input_contract_mismatch",
                )

    @staticmethod
    def _validate_live_table(table: pl.DataFrame, contract: Any, modality: str, role: str) -> None:
        if not isinstance(table, pl.DataFrame):
            _request_error(
                "request_semantic_identity_mismatch",
                field=f"aligned_table.{modality}.{role}",
                reason="invalid_runtime_type",
            )
        expected_names = tuple(field.field_name for field in contract.fields)
        if tuple(table.columns) != expected_names:
            _request_error(
                "request_semantic_identity_mismatch",
                field=f"aligned_table.{modality}.{role}",
                reason="column_order_mismatch",
            )
        for field in contract.fields:
            expected_dtype = _POLARS_DTYPES.get(field.dtype_id)
            if expected_dtype is None or table.schema[field.field_name] != expected_dtype:
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"aligned_table.{modality}.{role}.{field.field_name}",
                    reason="dtype_mismatch",
                )
            if not field.nullable and table[field.field_name].null_count() != 0:
                _request_error(
                    "request_semantic_identity_mismatch",
                    field=f"aligned_table.{modality}.{role}.{field.field_name}",
                    reason="non_nullable_column_contains_null",
                )

    def _validate_reference_inventory_and_provenance(self) -> None:
        required_ids = _required_reference_ids(self.execution_plan)
        actual_ids = set(self.resolved_references.entries)
        if required_ids != actual_ids:
            _request_error(
                "request_reference_inventory_mismatch",
                field="resolved_references",
                reason="required_inventory_mismatch",
            )

        report_reference = self.synchronization_report.task_reference_result
        for reference_id, resolved in self.resolved_references.entries.items():
            descriptor = resolved.descriptor
            source_kind = _enum_value(descriptor.source_kind)
            present = _enum_value(descriptor.resolution_status) == "present"

            if source_kind == "model_bundle":
                if (
                    report_reference is None
                    or report_reference.reference_id != reference_id
                    or report_reference.source != "model_bundle"
                    or report_reference.synchronization_status
                    is not SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
                ):
                    _request_error(
                        "request_reference_provenance_mismatch",
                        field=f"resolved_references.{reference_id}",
                        reason="model_bundle_not_deferred_by_m3",
                    )
                continue

            if not present:
                if report_reference is None:
                    continue
                if (
                    report_reference.reference_id != reference_id
                    or report_reference.source != "bundle"
                    or report_reference.synchronization_status is SynchronizationItemStatus.ALIGNED
                ):
                    _request_error(
                        "request_reference_provenance_mismatch",
                        field=f"resolved_references.{reference_id}",
                        reason="absent_bundle_hides_m3_reference",
                    )
                continue

            view = resolved.aligned_view
            expected_checksums = {
                item.path: item.checksum for item in descriptor.resource_checksums
            }
            clock = report_reference.clock if report_reference is not None else None
            alignment = descriptor.alignment_contract
            if (
                report_reference is None
                or view is None
                or report_reference.reference_id != reference_id
                or report_reference.source != "bundle"
                or report_reference.synchronization_status is not SynchronizationItemStatus.ALIGNED
                or self.aligned_session.task_reference is not view
                or clock is None
                or clock.clock_id != descriptor.clock_id
                or clock.method != alignment.mapping_method
                or clock.scale != alignment.scale
                or clock.offset_ns != alignment.offset_ns
                or clock.drift_ppm != alignment.declared_drift_ppm
                or alignment.mapping_policy_id != self.synchronization_report.policy.policy_id
                or report_reference.source_schema_id != descriptor.source_schema_id
                or report_reference.aligned_schema_id != descriptor.aligned_schema_id
                or dict(report_reference.source_checksums) != expected_checksums
            ):
                _request_error(
                    "request_reference_provenance_mismatch",
                    field=f"resolved_references.{reference_id}",
                    reason="bundle_m3_provenance_mismatch",
                )

    def _validate_fingerprint_closure(self) -> None:
        plan = self.execution_plan
        if (
            plan.source_snapshot_fingerprint != self.aligned_session.source_snapshot_fingerprint
            or plan.synchronization_fingerprint != self.aligned_session.synchronization_fingerprint
            or plan.semantic_snapshot_fingerprint
            != self.session_semantic_snapshot.semantic_snapshot_fingerprint
            or plan.reference_set_fingerprint != self.resolved_references.reference_set_fingerprint
        ):
            _request_error(
                "request_fingerprint_mismatch",
                field="execution_plan",
                reason="fingerprint_closure_mismatch",
            )


__all__ = [
    "AnchorEvaluationRequest",
    "AnchorRequestValidationError",
    "ReferenceViewCandidate",
    "ResolvedReference",
    "ResolvedReferenceSet",
]
