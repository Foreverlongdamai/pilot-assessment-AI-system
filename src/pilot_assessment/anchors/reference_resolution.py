"""Exact binding of frozen reference descriptors to trusted runtime views."""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from pilot_assessment.anchors.models import (
    ReferenceViewCandidate,
    ResolvedReference,
    ResolvedReferenceSet,
)
from pilot_assessment.contracts.anchor_execution import (
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
)
from pilot_assessment.synchronization.models import AlignedSession, AlignedStreamView

_ERROR_CODES = frozenset(
    {
        "reference_session_mismatch",
        "reference_candidate_inventory_mismatch",
        "reference_source_ownership_mismatch",
        "reference_identity_mismatch",
        "reference_table_contract_mismatch",
    }
)

_POLARS_DTYPES = {
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


class ReferenceBindingError(ValueError):
    """Stable pre-request error raised when an exact reference bind fails."""

    def __init__(self, code: str, message: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError(f"unsupported reference binding error code: {code}")
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> None:
    raise ReferenceBindingError(code, message)


def _validate_session_identity(
    snapshot: ResolvedReferenceSetSnapshot,
    aligned_session: AlignedSession,
) -> None:
    identity = snapshot.session_identity
    if (
        identity.session_id != aligned_session.session_id
        or identity.session_start_t_ns != 0
        or identity.session_end_t_ns != aligned_session.window.end_t_ns
        or identity.source_snapshot_fingerprint != aligned_session.source_snapshot_fingerprint
        or identity.synchronization_fingerprint != aligned_session.synchronization_fingerprint
    ):
        _fail(
            "reference_session_mismatch",
            "reference snapshot and aligned session identities must match exactly",
        )


def _validate_candidate_inventory(
    snapshot: ResolvedReferenceSetSnapshot,
    candidates: Mapping[str, ReferenceViewCandidate],
) -> None:
    present_ids = {
        descriptor.reference_id
        for descriptor in snapshot.descriptors
        if descriptor.resolution_status.value == "present"
    }
    if set(candidates) != present_ids:
        _fail(
            "reference_candidate_inventory_mismatch",
            "candidate keys must equal the present descriptor inventory",
        )

    for key, candidate in candidates.items():
        if not isinstance(candidate, ReferenceViewCandidate) or key != candidate.reference_id:
            _fail(
                "reference_candidate_inventory_mismatch",
                "candidate mapping keys must equal candidate reference IDs",
            )
        if candidate.session_identity != snapshot.session_identity:
            _fail(
                "reference_session_mismatch",
                "candidate and reference snapshot session identities must match exactly",
            )


def _validate_absent_ownership(
    descriptor: ResolvedReferenceDescriptor,
    aligned_session: AlignedSession,
) -> None:
    if descriptor.source_kind.value == "bundle" and aligned_session.task_reference is not None:
        _fail(
            "reference_source_ownership_mismatch",
            "an absent bundle descriptor cannot hide a dedicated task reference view",
        )


def _validate_declared_identity(
    descriptor: ResolvedReferenceDescriptor,
    candidate: ReferenceViewCandidate,
) -> None:
    view = candidate.aligned_view
    identity_matches = (
        candidate.reference_id == descriptor.reference_id
        and candidate.source_kind == descriptor.source_kind
        and candidate.alignment_contract == descriptor.alignment_contract
        and candidate.resource_fingerprint == descriptor.resource_fingerprint
        and candidate.aligned_content_fingerprint == descriptor.aligned_content_fingerprint
        and candidate.alignment_fingerprint == descriptor.alignment_fingerprint
        and view.source_schema_id == descriptor.source_schema_id
        and view.aligned_schema_id == descriptor.aligned_schema_id
        and view.clock_id == descriptor.clock_id
        and view.clock_id == descriptor.alignment_contract.source_clock_id
    )
    if not identity_matches:
        _fail(
            "reference_identity_mismatch",
            "candidate and descriptor identities must match exactly",
        )

    if view.modality != descriptor.runtime_view_role or view.modality != "task_reference":
        _fail(
            "reference_source_ownership_mismatch",
            "reference views must use the dedicated task_reference role",
        )

    expected_checksums = {
        checksum.path: checksum.checksum for checksum in descriptor.resource_checksums
    }
    if any(
        type(path) is not str or type(digest) is not str
        for path, digest in view.source_checksums.items()
    ):
        _fail(
            "reference_identity_mismatch",
            "runtime source checksum keys and values must be strings",
        )
    actual_checksums = dict(view.source_checksums)
    actual_casefold_paths = {path.casefold() for path in actual_checksums}
    if (
        len(actual_casefold_paths) != len(actual_checksums)
        or actual_checksums != expected_checksums
    ):
        _fail(
            "reference_identity_mismatch",
            "runtime source checksums must match descriptor resources exactly",
        )

    if candidate.table_contract != descriptor.table_contract:
        _fail(
            "reference_table_contract_mismatch",
            "candidate and descriptor table contracts must match exactly",
        )


def _owned_session_views(aligned_session: AlignedSession) -> tuple[AlignedStreamView, ...]:
    views = list(aligned_session.streams.values())
    if aligned_session.task_reference is not None:
        views.append(aligned_session.task_reference)
    return tuple(views)


def _validate_source_ownership(
    descriptor: ResolvedReferenceDescriptor,
    candidate: ReferenceViewCandidate,
    aligned_session: AlignedSession,
) -> None:
    view = candidate.aligned_view
    if descriptor.source_kind.value == "bundle":
        if aligned_session.task_reference is None or view is not aligned_session.task_reference:
            _fail(
                "reference_source_ownership_mismatch",
                "bundle candidates must be the dedicated aligned-session reference view",
            )
        return

    session_views = _owned_session_views(aligned_session)
    if any(view is owned_view for owned_view in session_views):
        _fail(
            "reference_source_ownership_mismatch",
            "model-bundle candidates must not alias session-owned views",
        )
    if any(view.tables is owned_view.tables for owned_view in session_views):
        _fail(
            "reference_source_ownership_mismatch",
            "model-bundle candidates must not alias session-owned table containers",
        )

    owned_tables = tuple(
        table for owned_view in session_views for table in owned_view.tables.values()
    )
    if any(
        candidate_table is owned_table
        for candidate_table in view.tables.values()
        for owned_table in owned_tables
    ):
        _fail(
            "reference_source_ownership_mismatch",
            "model-bundle candidates must not alias session-owned dataframes",
        )


def _validate_runtime_table(
    table: pl.DataFrame,
    contract: ReferenceTableContract,
    *,
    session_end_t_ns: int,
) -> None:
    expected_columns = [field.field_name for field in contract.fields]
    if table.columns != expected_columns:
        _fail(
            "reference_table_contract_mismatch",
            "runtime columns must exactly match the declared physical order",
        )

    for field in contract.fields:
        expected_dtype = _POLARS_DTYPES.get(field.dtype_id)
        if expected_dtype is None or table.schema[field.field_name] != expected_dtype:
            _fail(
                "reference_table_contract_mismatch",
                "runtime column dtypes must exactly match the primitive contract",
            )
        series = table.get_column(field.field_name)
        if not field.nullable and series.null_count() != 0:
            _fail(
                "reference_table_contract_mismatch",
                "non-nullable runtime columns must not contain nulls",
            )
        if field.dtype_id in {"f32", "f64"} and not series.drop_nulls().is_finite().all():
            _fail(
                "reference_table_contract_mismatch",
                "floating reference values must be finite",
            )

    stable_rows = table.get_column(contract.stable_row_id_field)
    if stable_rows.n_unique() != table.height:
        _fail(
            "reference_table_contract_mismatch",
            "stable row identifiers must be unique",
        )

    order_keys = list(contract.canonical_order_keys)
    ordered_values = table.select(order_keys)
    if ordered_values.n_unique() != table.height or not ordered_values.equals(
        ordered_values.sort(order_keys, maintain_order=True)
    ):
        _fail(
            "reference_table_contract_mismatch",
            "runtime rows must have unique, ascending canonical order keys",
        )

    time_values = table.get_column(contract.session_time_field)
    actual_mask = table.get_column(contract.in_session_field)
    expected_mask = ((time_values >= 0) & (time_values <= session_end_t_ns)).to_list()
    if actual_mask.to_list() != expected_mask:
        _fail(
            "reference_table_contract_mismatch",
            "in_session must equal the closed mapped-source-row session mask",
        )


def _validate_table_inventory_and_content(
    descriptor: ResolvedReferenceDescriptor,
    candidate: ReferenceViewCandidate,
    *,
    session_end_t_ns: int,
) -> None:
    view = candidate.aligned_view
    table_role = descriptor.table_contract.table_role
    if set(view.tables) != {table_role}:
        _fail(
            "reference_table_contract_mismatch",
            "runtime table inventory must contain exactly the declared table role",
        )
    if view.json_artifacts or view.file_artifacts:
        _fail(
            "reference_table_contract_mismatch",
            "reference views must not expose undeclared artifact side channels",
        )

    table = view.tables[table_role]
    if not isinstance(table, pl.DataFrame):
        _fail(
            "reference_table_contract_mismatch",
            "runtime reference tables must be Polars DataFrame instances",
        )
    _validate_runtime_table(
        table,
        descriptor.table_contract,
        session_end_t_ns=session_end_t_ns,
    )


def bind_resolved_reference_snapshot(
    snapshot: ResolvedReferenceSetSnapshot,
    aligned_session: AlignedSession,
    candidates: Mapping[str, ReferenceViewCandidate],
) -> ResolvedReferenceSet:
    """Bind only exact, independently described reference candidates."""

    _validate_session_identity(snapshot, aligned_session)
    _validate_candidate_inventory(snapshot, candidates)

    entries: dict[str, ResolvedReference] = {}
    for descriptor in snapshot.descriptors:
        if descriptor.resolution_status.value == "absent":
            _validate_absent_ownership(descriptor, aligned_session)
            entries[descriptor.reference_id] = ResolvedReference(
                descriptor=descriptor,
                aligned_view=None,
            )
            continue

        candidate = candidates[descriptor.reference_id]
        _validate_declared_identity(descriptor, candidate)
        _validate_source_ownership(descriptor, candidate, aligned_session)
        _validate_table_inventory_and_content(
            descriptor,
            candidate,
            session_end_t_ns=snapshot.session_identity.session_end_t_ns,
        )
        entries[descriptor.reference_id] = ResolvedReference(
            descriptor=descriptor,
            aligned_view=candidate.aligned_view,
        )

    return ResolvedReferenceSet(
        session_identity=snapshot.session_identity,
        entries=entries,
        reference_set_fingerprint=snapshot.reference_set_fingerprint,
    )


__all__ = ["ReferenceBindingError", "bind_resolved_reference_snapshot"]
