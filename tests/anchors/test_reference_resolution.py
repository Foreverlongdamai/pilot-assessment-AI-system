from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import polars as pl
import pytest

from pilot_assessment.anchors.models import ReferenceViewCandidate
from pilot_assessment.anchors.reference_resolution import (
    ReferenceBindingError,
    bind_resolved_reference_snapshot,
)
from pilot_assessment.contracts.anchor_execution import (
    ReferenceAlignmentContract,
    ReferenceFieldContract,
    ReferenceSessionIdentity,
    ReferenceSourceKind,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
)
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedSession,
    AlignedStreamView,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
END_NS = 10_000_000_000


def _parts() -> tuple[
    ReferenceSessionIdentity,
    ReferenceAlignmentContract,
    ReferenceTableContract,
]:
    return (
        ReferenceSessionIdentity(
            session_id="session-1",
            source_snapshot_fingerprint=SHA_A,
            synchronization_fingerprint=SHA_B,
            session_end_t_ns=END_NS,
        ),
        ReferenceAlignmentContract(
            mapping_method="affine-v1",
            mapping_policy_id="policy-v1",
            source_clock_id="reference-clock",
            scale=1.0,
            offset_ns=0,
            declared_drift_ppm=0.0,
        ),
        ReferenceTableContract(
            table_role="commanded-path",
            coordinate_frame_id="world",
            stable_row_id_field="row-id",
            fields=(
                ReferenceFieldContract(
                    field_name="t_ns", dtype_id="i64", unit="ns", nullable=False
                ),
                ReferenceFieldContract(
                    field_name="in_session", dtype_id="bool", unit="bool", nullable=False
                ),
                ReferenceFieldContract(
                    field_name="row-id", dtype_id="i64", unit="index", nullable=False
                ),
                ReferenceFieldContract(field_name="x", dtype_id="f64", unit="m", nullable=False),
            ),
            canonical_order_keys=("t_ns", "row-id"),
            table_contract_fingerprint=SHA_C,
        ),
    )


def _table(**updates: pl.Series) -> pl.DataFrame:
    columns: dict[str, pl.Series] = {
        "t_ns": pl.Series("t_ns", [0, END_NS], dtype=pl.Int64),
        "in_session": pl.Series("in_session", [True, True], dtype=pl.Boolean),
        "row-id": pl.Series("row-id", [0, 1], dtype=pl.Int64),
        "x": pl.Series("x", [0.0, 1.0], dtype=pl.Float64),
    }
    columns.update(updates)
    return pl.DataFrame(list(columns.values()))


def _view(
    table: pl.DataFrame | None = None,
    *,
    source_schema_id: str = "reference-raw-v0.1",
    aligned_schema_id: str = "reference-aligned-v0.1",
    clock_id: str = "reference-clock",
    json_artifacts: dict[str, object] | None = None,
) -> AlignedStreamView:
    return AlignedStreamView(
        modality="task_reference",
        source_schema_id=source_schema_id,
        aligned_schema_id=aligned_schema_id,
        clock_id=clock_id,
        tables={"commanded-path": table if table is not None else _table()},
        json_artifacts=json_artifacts or {},
        file_artifacts={},
        source_checksums={"references/commanded.parquet": SHA_D},
    )


def _session(reference: AlignedStreamView | None) -> AlignedSession:
    return AlignedSession(
        session_id="session-1",
        window=SessionWindow(end_t_ns=END_NS, source="master-clock-x-mapped-coverage-v1"),
        streams={},
        context={},
        annotations=AlignedAnnotations(
            revision="annotations-1",
            phases=(),
            events=(),
            baseline_intervals=(),
            source_schema_ids={},
            synthetic_semantics_unvalidated=False,
        ),
        task_reference=reference,
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
    )


def _descriptor(
    *, present: bool = True, source_kind: str = "bundle"
) -> ResolvedReferenceDescriptor:
    _, alignment, contract = _parts()
    return ResolvedReferenceDescriptor.model_validate(
        {
            "reference_id": "reference-1",
            "resolution_status": "present" if present else "absent",
            "source_kind": source_kind,
            "source_schema_id": "reference-raw-v0.1",
            "aligned_schema_id": "reference-aligned-v0.1",
            "clock_id": "reference-clock",
            "alignment_contract": alignment,
            "table_contract": contract,
            "resource_checksums": (
                [{"path": "references/commanded.parquet", "checksum": SHA_D}] if present else []
            ),
            "resource_fingerprint": SHA_D if present else None,
            "aligned_content_fingerprint": SHA_E if present else None,
            "alignment_fingerprint": SHA_F if present else None,
            "absence_reason": None if present else "not-provided",
        }
    )


def _snapshot(descriptor: ResolvedReferenceDescriptor | None) -> ResolvedReferenceSetSnapshot:
    identity, _, _ = _parts()
    return ResolvedReferenceSetSnapshot(
        session_identity=identity,
        descriptors=() if descriptor is None else (descriptor,),
        reference_set_fingerprint=SHA_A,
    )


def _candidate(
    view: AlignedStreamView,
    *,
    descriptor: ResolvedReferenceDescriptor | None = None,
) -> ReferenceViewCandidate:
    descriptor = descriptor or _descriptor()
    identity, _, _ = _parts()
    return ReferenceViewCandidate(
        reference_id=descriptor.reference_id,
        source_kind=descriptor.source_kind,
        session_identity=identity,
        aligned_view=view,
        alignment_contract=descriptor.alignment_contract,
        table_contract=descriptor.table_contract,
        resource_fingerprint=descriptor.resource_fingerprint,
        aligned_content_fingerprint=descriptor.aligned_content_fingerprint,
        alignment_fingerprint=descriptor.alignment_fingerprint,
    )


def _assert_code(code: str, call: Callable[[], object]) -> None:
    with pytest.raises(ReferenceBindingError) as caught:
        call()  # type: ignore[operator]
    assert caught.value.code == code


def test_present_binding_preserves_descriptor_view_and_dataframe_identity() -> None:
    descriptor = _descriptor()
    view = _view()
    session = _session(view)
    candidate = _candidate(view, descriptor=descriptor)

    snapshot = _snapshot(descriptor)
    resolved = bind_resolved_reference_snapshot(
        snapshot, session, {descriptor.reference_id: candidate}
    )

    entry = resolved.entries[descriptor.reference_id]
    assert entry.descriptor is descriptor
    assert entry.aligned_view is view
    assert entry.aligned_view.tables["commanded-path"] is view.tables["commanded-path"]
    assert resolved.session_identity is snapshot.session_identity
    assert resolved.reference_set_fingerprint == snapshot.reference_set_fingerprint
    with pytest.raises(TypeError):
        resolved.entries["other"] = entry  # type: ignore[index]


def test_absent_binding_and_unused_reference_inventory_are_explicit() -> None:
    descriptor = _descriptor(present=False)
    resolved = bind_resolved_reference_snapshot(_snapshot(descriptor), _session(None), {})
    assert resolved.entries[descriptor.reference_id].aligned_view is None

    live_unused = _view()
    empty = bind_resolved_reference_snapshot(_snapshot(None), _session(live_unused), {})
    assert dict(empty.entries) == {}

    _assert_code(
        "reference_source_ownership_mismatch",
        lambda: bind_resolved_reference_snapshot(_snapshot(descriptor), _session(live_unused), {}),
    )


def test_session_and_candidate_inventory_fail_before_table_access() -> None:
    descriptor = _descriptor()
    view = _view()
    session = _session(view)
    candidate = _candidate(view, descriptor=descriptor)

    wrong_session = replace(session, session_id="other-session")
    _assert_code(
        "reference_session_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor), wrong_session, {descriptor.reference_id: candidate}
        ),
    )
    _assert_code(
        "reference_candidate_inventory_mismatch",
        lambda: bind_resolved_reference_snapshot(_snapshot(descriptor), session, {}),
    )
    _assert_code(
        "reference_candidate_inventory_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor), session, {"wrong-key": candidate}
        ),
    )

    poisoned_view = replace(
        view,
        tables={"commanded-path": cast(pl.DataFrame, object())},
    )
    poisoned_candidate = _candidate(poisoned_view, descriptor=descriptor)
    _assert_code(
        "reference_session_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            wrong_session,
            {descriptor.reference_id: poisoned_candidate},
        ),
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda candidate: replace(candidate, resource_fingerprint=SHA_A),
        lambda candidate: replace(candidate, aligned_content_fingerprint=SHA_A),
        lambda candidate: replace(candidate, alignment_fingerprint=SHA_A),
        lambda candidate: replace(candidate, aligned_view=_view(source_schema_id="other-schema")),
        lambda candidate: replace(candidate, aligned_view=_view(aligned_schema_id="other-schema")),
        lambda candidate: replace(candidate, aligned_view=_view(clock_id="other-clock")),
    ],
)
def test_declared_identity_mutations_never_degrade_to_absent(
    mutate: Callable[[ReferenceViewCandidate], ReferenceViewCandidate],
) -> None:
    descriptor = _descriptor()
    view = _view()
    session = _session(view)
    candidate = mutate(_candidate(view, descriptor=descriptor))  # type: ignore[operator]

    _assert_code(
        "reference_identity_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor), session, {descriptor.reference_id: candidate}
        ),
    )


@pytest.mark.parametrize(
    "bad_table",
    [
        _table(**{"x": pl.Series("x", [0, 1], dtype=pl.Int64)}),
        _table(**{"x": pl.Series("x", [0.0, None], dtype=pl.Float64)}),
        _table(**{"x": pl.Series("x", [0.0, float("nan")], dtype=pl.Float64)}),
        _table(**{"row-id": pl.Series("row-id", [0, 0], dtype=pl.Int64)}),
        _table(
            **{
                "t_ns": pl.Series("t_ns", [END_NS, 0], dtype=pl.Int64),
                "row-id": pl.Series("row-id", [1, 0], dtype=pl.Int64),
            }
        ),
        _table(**{"in_session": pl.Series("in_session", [True, False], dtype=pl.Boolean)}),
    ],
)
def test_runtime_table_contract_violations_are_rejected(bad_table: pl.DataFrame) -> None:
    descriptor = _descriptor()
    view = _view(bad_table)
    candidate = _candidate(view, descriptor=descriptor)
    _assert_code(
        "reference_table_contract_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor), _session(view), {descriptor.reference_id: candidate}
        ),
    )


def test_side_channels_and_table_inventory_are_rejected() -> None:
    descriptor = _descriptor()
    side_channel = _view(json_artifacts={"metadata": {"value": "hidden"}})
    _assert_code(
        "reference_table_contract_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            _session(side_channel),
            {descriptor.reference_id: _candidate(side_channel, descriptor=descriptor)},
        ),
    )

    view = _view()
    extra_view = replace(
        view,
        tables={**dict(view.tables), "shape-compatible-extra": view.tables["commanded-path"]},
    )
    _assert_code(
        "reference_table_contract_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            _session(extra_view),
            {descriptor.reference_id: _candidate(extra_view, descriptor=descriptor)},
        ),
    )


def test_model_bundle_candidate_cannot_alias_session_or_core_views() -> None:
    descriptor = _descriptor(source_kind="model_bundle")
    bundle_view = _view()
    session = _session(bundle_view)
    candidate = _candidate(bundle_view, descriptor=descriptor)
    _assert_code(
        "reference_source_ownership_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor), session, {descriptor.reference_id: candidate}
        ),
    )

    shared_table = _table()
    core_view = AlignedStreamView(
        modality="X",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        clock_id="master-clock",
        tables={"state": shared_table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/x.parquet": SHA_A},
    )
    core_session = replace(_session(None), streams={"X": core_view})
    aliased_reference_view = _view(shared_table)
    _assert_code(
        "reference_source_ownership_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            core_session,
            {descriptor.reference_id: _candidate(aliased_reference_view, descriptor=descriptor)},
        ),
    )


def test_model_bundle_independent_view_and_structural_rows_are_accepted() -> None:
    descriptor = _descriptor(source_kind="model_bundle")
    view = _view()
    snapshot = _snapshot(descriptor)
    resolved = bind_resolved_reference_snapshot(
        snapshot,
        _session(None),
        {descriptor.reference_id: _candidate(view, descriptor=descriptor)},
    )
    assert resolved.entries[descriptor.reference_id].aligned_view is view

    empty = pl.DataFrame(
        schema={
            "t_ns": pl.Int64,
            "in_session": pl.Boolean,
            "row-id": pl.Int64,
            "x": pl.Float64,
        }
    )
    empty_view = _view(empty)
    resolved_empty = bind_resolved_reference_snapshot(
        _snapshot(_descriptor()),
        _session(empty_view),
        {"reference-1": _candidate(empty_view)},
    )
    assert resolved_empty.entries["reference-1"].aligned_view.tables["commanded-path"].is_empty()

    out_of_session = pl.DataFrame(
        {
            "t_ns": pl.Series("t_ns", [-1, END_NS + 1], dtype=pl.Int64),
            "in_session": pl.Series("in_session", [False, False], dtype=pl.Boolean),
            "row-id": pl.Series("row-id", [0, 1], dtype=pl.Int64),
            "x": pl.Series("x", [0.0, 1.0], dtype=pl.Float64),
        }
    )
    outside_view = _view(out_of_session)
    outside = bind_resolved_reference_snapshot(
        _snapshot(_descriptor()),
        _session(outside_view),
        {"reference-1": _candidate(outside_view)},
    )
    assert outside.entries["reference-1"].aligned_view is outside_view


def test_nullable_fields_remain_structural_not_quality_filters() -> None:
    descriptor = _descriptor()
    fields = tuple(
        field.model_copy(update={"nullable": True}) if field.field_name == "x" else field
        for field in descriptor.table_contract.fields
    )
    nullable_contract = ReferenceTableContract.model_validate(
        {**descriptor.table_contract.model_dump(mode="python"), "fields": fields}
    )
    nullable_descriptor = ResolvedReferenceDescriptor.model_validate(
        {
            **descriptor.model_dump(mode="python"),
            "table_contract": nullable_contract,
        }
    )
    view = _view(_table(**{"x": pl.Series("x", [None, 1.0], dtype=pl.Float64)}))
    candidate = replace(
        _candidate(view, descriptor=nullable_descriptor),
        table_contract=nullable_contract,
    )
    resolved = bind_resolved_reference_snapshot(
        _snapshot(nullable_descriptor),
        _session(view),
        {nullable_descriptor.reference_id: candidate},
    )
    assert resolved.entries[nullable_descriptor.reference_id].aligned_view is view


def test_malformed_runtime_containers_raise_stable_binding_errors() -> None:
    descriptor = _descriptor()
    malformed_table_view = replace(
        _view(),
        tables={"commanded-path": cast(pl.DataFrame, object())},
    )
    _assert_code(
        "reference_table_contract_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            _session(malformed_table_view),
            {descriptor.reference_id: _candidate(malformed_table_view, descriptor=descriptor)},
        ),
    )

    malformed_checksum_view = replace(
        _view(),
        source_checksums=cast(dict[str, str], {1: SHA_D}),
    )
    _assert_code(
        "reference_identity_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            _session(malformed_checksum_view),
            {descriptor.reference_id: _candidate(malformed_checksum_view, descriptor=descriptor)},
        ),
    )


def test_identity_ownership_and_table_contract_codes_are_stable() -> None:
    descriptor = _descriptor()
    view = _view()
    session = _session(view)
    candidate = _candidate(view, descriptor=descriptor)

    _assert_code(
        "reference_identity_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            session,
            {
                descriptor.reference_id: replace(
                    candidate, source_kind=ReferenceSourceKind.MODEL_BUNDLE
                )
            },
        ),
    )
    changed_contract = candidate.table_contract.model_copy(update={"coordinate_frame_id": "body"})
    _assert_code(
        "reference_table_contract_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(descriptor),
            session,
            {descriptor.reference_id: replace(candidate, table_contract=changed_contract)},
        ),
    )
    model_descriptor = _descriptor(source_kind="model_bundle")
    wrong_role_view = replace(view, modality="X")
    _assert_code(
        "reference_source_ownership_mismatch",
        lambda: bind_resolved_reference_snapshot(
            _snapshot(model_descriptor),
            _session(None),
            {
                model_descriptor.reference_id: _candidate(
                    wrong_role_view, descriptor=model_descriptor
                )
            },
        ),
    )
