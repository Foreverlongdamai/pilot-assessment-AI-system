from __future__ import annotations

import hashlib
import struct
from importlib import import_module
from types import ModuleType
from typing import Any, cast

import polars as pl
import pytest
import rfc8785
from pydantic import JsonValue

from pilot_assessment.anchors.protocols import (
    ReadOnlyBlobPayload,
    ReadOnlyTabularPayload,
    ResolvedArtifactDependency,
)
from pilot_assessment.contracts.anchor_execution import (
    ReferenceAlignmentContract,
    ReferenceFieldContract,
    ReferenceSessionIdentity,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
END_NS = 10


@pytest.fixture
def fingerprint_module() -> ModuleType:
    return import_module("pilot_assessment.anchors.fingerprint")


def _call(module: ModuleType, name: str, *args: object) -> Any:
    return getattr(module, name)(*args)


def _typed_hash(type_id: str, version: str, payload: object) -> str:
    canonical = rfc8785.dumps(cast(JsonValue, payload))
    framed = (
        type_id.encode("ascii")
        + b"\0"
        + version.encode("ascii")
        + b"\0"
        + struct.pack(">Q", len(canonical))
        + canonical
    )
    return hashlib.sha256(framed).hexdigest()


def _semantic_snapshot() -> SessionSemanticSnapshot:
    return SessionSemanticSnapshot(
        session_id="session-1",
        task_profile_id="task-profile-1",
        scenario_id="scenario-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        annotation_revision="annotations-1",
        synthetic_semantics_unvalidated=False,
        session_end_t_ns=END_NS,
        semantic_snapshot_fingerprint=SHA_C,
    )


def _table_contract() -> ReferenceTableContract:
    return ReferenceTableContract(
        table_role="commanded-path",
        coordinate_frame_id="world",
        stable_row_id_field="row-id",
        fields=(
            ReferenceFieldContract(field_name="t_ns", dtype_id="i64", unit="ns", nullable=False),
            ReferenceFieldContract(
                field_name="in_session", dtype_id="bool", unit="bool", nullable=False
            ),
            ReferenceFieldContract(
                field_name="row-id", dtype_id="i64", unit="index", nullable=False
            ),
            ReferenceFieldContract(field_name="x", dtype_id="f64", unit="m", nullable=False),
        ),
        canonical_order_keys=("t_ns", "row-id"),
        table_contract_fingerprint=SHA_A,
    )


def _alignment_contract() -> ReferenceAlignmentContract:
    return ReferenceAlignmentContract(
        mapping_method="affine-v1",
        mapping_policy_id="native-alignment-engineering-v0.1",
        source_clock_id="reference-clock",
        scale=1.0,
        offset_ns=0,
        declared_drift_ppm=0.0,
    )


def _descriptor(*, present: bool) -> ResolvedReferenceDescriptor:
    return ResolvedReferenceDescriptor.model_validate(
        {
            "reference_id": "reference-1",
            "resolution_status": "present" if present else "absent",
            "source_kind": "bundle",
            "source_schema_id": "reference-raw-v0.1",
            "aligned_schema_id": "reference-aligned-v0.1",
            "clock_id": "reference-clock",
            "alignment_contract": _alignment_contract(),
            "table_contract": _table_contract(),
            "resource_checksums": (
                [{"path": "references/commanded.parquet", "checksum": SHA_E}] if present else []
            ),
            "resource_fingerprint": SHA_A if present else None,
            "aligned_content_fingerprint": SHA_B if present else None,
            "alignment_fingerprint": SHA_C if present else None,
            "absence_reason": None if present else "not-provided",
        }
    )


def _session_identity() -> ReferenceSessionIdentity:
    return ReferenceSessionIdentity(
        session_id="session-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        session_end_t_ns=END_NS,
    )


def _reference_frame(*, second_x: float = 2.5) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "t_ns": pl.Series("t_ns", [0, 5], dtype=pl.Int64),
            "in_session": pl.Series("in_session", [True, True], dtype=pl.Boolean),
            "row-id": pl.Series("row-id", [0, 1], dtype=pl.Int64),
            "x": pl.Series("x", [1.25, second_x], dtype=pl.Float64),
        }
    )


def _reference_inline_descriptor(contract: ReferenceTableContract) -> dict[str, object]:
    return {
        "type": "table",
        "fields": [
            {
                "name": field.field_name,
                "dtype": field.dtype_id,
                "unit": field.unit,
                "nullable": field.nullable,
            }
            for field in contract.fields
        ],
        "canonical_order_keys": list(contract.canonical_order_keys),
    }


def test_semantic_snapshot_uses_exact_projection_and_excludes_only_self_claim(
    fingerprint_module: ModuleType,
) -> None:
    snapshot = _semantic_snapshot()
    payload = snapshot.model_dump(mode="json", exclude={"semantic_snapshot_fingerprint"})
    expected = _typed_hash("session-semantic-snapshot", "0.1.0", payload)

    assert _call(fingerprint_module, "session_semantic_snapshot_fingerprint", snapshot) == expected
    assert (
        _call(
            fingerprint_module,
            "session_semantic_snapshot_fingerprint",
            snapshot.model_copy(update={"semantic_snapshot_fingerprint": SHA_D}),
        )
        == expected
    )
    assert (
        _call(
            fingerprint_module,
            "session_semantic_snapshot_fingerprint",
            snapshot.model_copy(update={"scenario_id": "scenario-2"}),
        )
        != expected
    )

    for field_name, value in (
        ("session_id", "session-2"),
        ("task_profile_id", "task-profile-2"),
        ("source_snapshot_fingerprint", SHA_D),
        ("synchronization_fingerprint", SHA_E),
        ("annotation_revision", "annotations-2"),
        ("synthetic_semantics_unvalidated", True),
        ("session_end_t_ns", END_NS - 1),
    ):
        changed = snapshot.model_copy(update={field_name: value})
        assert (
            _call(fingerprint_module, "session_semantic_snapshot_fingerprint", changed) != expected
        ), field_name


def test_reference_table_contract_uses_complete_contract_without_self_claim(
    fingerprint_module: ModuleType,
) -> None:
    contract = _table_contract()
    payload = contract.model_dump(mode="json", exclude={"table_contract_fingerprint"})
    expected = _typed_hash("reference-table-contract", "0.1.0", payload)

    assert _call(fingerprint_module, "reference_table_contract_fingerprint", contract) == expected
    assert (
        _call(
            fingerprint_module,
            "reference_table_contract_fingerprint",
            contract.model_copy(update={"table_contract_fingerprint": SHA_D}),
        )
        == expected
    )
    changed_fields = (*contract.fields[:-1], contract.fields[-1].model_copy(update={"unit": "ft"}))
    assert (
        _call(
            fingerprint_module,
            "reference_table_contract_fingerprint",
            contract.model_copy(update={"fields": changed_fields}),
        )
        != expected
    )

    x_field = contract.fields[-1]
    contract_mutations = {
        "table-role": contract.model_copy(update={"table_role": "alternate-path"}),
        "coordinate-frame": contract.model_copy(update={"coordinate_frame_id": "body"}),
        "field-name": contract.model_copy(
            update={
                "fields": (*contract.fields[:-1], x_field.model_copy(update={"field_name": "y"}))
            }
        ),
        "field-dtype": contract.model_copy(
            update={
                "fields": (*contract.fields[:-1], x_field.model_copy(update={"dtype_id": "f32"}))
            }
        ),
        "field-nullable": contract.model_copy(
            update={
                "fields": (*contract.fields[:-1], x_field.model_copy(update={"nullable": True}))
            }
        ),
        "physical-field-order": contract.model_copy(
            update={"fields": (*contract.fields[:2], contract.fields[3], contract.fields[2])}
        ),
    }
    for label, changed in contract_mutations.items():
        assert (
            _call(fingerprint_module, "reference_table_contract_fingerprint", changed) != expected
        ), label


def test_reference_resource_identity_binds_ordered_checksums_not_digest_claims(
    fingerprint_module: ModuleType,
) -> None:
    descriptor = _descriptor(present=True)
    payload = [
        descriptor.reference_id,
        descriptor.source_kind.value,
        descriptor.runtime_view_role,
        descriptor.source_schema_id,
        descriptor.table_contract.table_contract_fingerprint,
        [[checksum.path, checksum.checksum] for checksum in descriptor.resource_checksums],
    ]
    expected = _typed_hash("reference-resource", "0.1.0", payload)

    assert _call(fingerprint_module, "reference_resource_fingerprint", descriptor) == expected
    assert (
        _call(
            fingerprint_module,
            "reference_resource_fingerprint",
            descriptor.model_copy(update={"resource_fingerprint": SHA_D}),
        )
        == expected
    )
    changed_checksum = descriptor.resource_checksums[0].model_copy(update={"checksum": SHA_D})
    assert (
        _call(
            fingerprint_module,
            "reference_resource_fingerprint",
            descriptor.model_copy(update={"resource_checksums": (changed_checksum,)}),
        )
        != expected
    )

    original_checksum = descriptor.resource_checksums[0]
    for label, changed in {
        "reference-id": descriptor.model_copy(update={"reference_id": "reference-2"}),
        "source-schema": descriptor.model_copy(update={"source_schema_id": "reference-raw-v0.2"}),
        "table-contract": descriptor.model_copy(
            update={
                "table_contract": descriptor.table_contract.model_copy(
                    update={"table_contract_fingerprint": SHA_D}
                )
            }
        ),
        "resource-path": descriptor.model_copy(
            update={
                "resource_checksums": (
                    original_checksum.model_copy(update={"path": "references/alternate.parquet"}),
                )
            }
        ),
    }.items():
        assert _call(fingerprint_module, "reference_resource_fingerprint", changed) != expected, (
            label
        )


def test_aligned_reference_content_is_exact_tiny_logical_table(
    fingerprint_module: ModuleType,
) -> None:
    contract = _table_contract()
    frame = _reference_frame()
    descriptor = _reference_inline_descriptor(contract)
    rows = [[0, True, 0, 1.25], [5, True, 1, 2.5]]
    payload = [
        ["reference-aligned-v0.1", descriptor, ["t_ns", "row-id"]],
        rows,
    ]
    expected = _typed_hash("logical-table", "0.1.0", payload)

    assert (
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            frame,
            "reference-aligned-v0.1",
            contract,
        )
        == expected
    )
    assert (
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            _reference_frame(second_x=2.75),
            "reference-aligned-v0.1",
            contract,
        )
        != expected
    )
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            frame.reverse(),
            "reference-aligned-v0.1",
            contract,
        )

    mask_changed = frame.with_columns(pl.Series("in_session", [True, False], dtype=pl.Boolean))
    assert (
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            mask_changed,
            "reference-aligned-v0.1",
            contract,
        )
        != expected
    )
    assert (
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            frame,
            "reference-aligned-v0.2",
            contract,
        )
        != expected
    )


def test_reference_alignment_binds_complete_session_and_mapping_contract(
    fingerprint_module: ModuleType,
) -> None:
    descriptor = _descriptor(present=True)
    session_identity = _session_identity()
    payload = {
        "session_identity": session_identity.model_dump(mode="json"),
        "reference_id": descriptor.reference_id,
        "source_kind": descriptor.source_kind.value,
        "runtime_view_role": descriptor.runtime_view_role,
        "alignment_contract": descriptor.alignment_contract.model_dump(mode="json"),
        "clock_id": descriptor.clock_id,
        "source_schema_id": descriptor.source_schema_id,
        "aligned_schema_id": descriptor.aligned_schema_id,
        "table_contract_fingerprint": descriptor.table_contract.table_contract_fingerprint,
        "resource_fingerprint": descriptor.resource_fingerprint,
        "aligned_content_fingerprint": descriptor.aligned_content_fingerprint,
    }
    expected = _typed_hash("reference-alignment", "0.1.0", payload)

    assert (
        _call(
            fingerprint_module,
            "reference_alignment_fingerprint",
            descriptor,
            session_identity,
        )
        == expected
    )
    assert (
        _call(
            fingerprint_module,
            "reference_alignment_fingerprint",
            descriptor.model_copy(update={"alignment_fingerprint": SHA_D}),
            session_identity,
        )
        == expected
    )
    changed_alignment = descriptor.alignment_contract.model_copy(update={"offset_ns": 1})
    assert (
        _call(
            fingerprint_module,
            "reference_alignment_fingerprint",
            descriptor.model_copy(update={"alignment_contract": changed_alignment}),
            session_identity,
        )
        != expected
    )

    session_mutations = {
        "session": session_identity.model_copy(update={"session_id": "session-2"}),
        "source-snapshot": session_identity.model_copy(
            update={"source_snapshot_fingerprint": SHA_D}
        ),
        "synchronization": session_identity.model_copy(
            update={"synchronization_fingerprint": SHA_E}
        ),
        "window": session_identity.model_copy(update={"session_end_t_ns": END_NS - 1}),
    }
    for label, changed_session in session_mutations.items():
        assert (
            _call(
                fingerprint_module,
                "reference_alignment_fingerprint",
                descriptor,
                changed_session,
            )
            != expected
        ), label

    alignment_mutations = {
        "mapping-method": {"mapping_method": "affine-v2"},
        "mapping-policy": {"mapping_policy_id": "native-alignment-v0.2"},
        "scale": {"scale": 1.000001},
        "offset": {"offset_ns": 1},
        "drift": {"declared_drift_ppm": 1.0},
        "rounding": {"rounding_mode": "different-rounding"},
        "mask-policy": {"in_session_policy": "different-mask"},
    }
    for label, update in alignment_mutations.items():
        changed_contract = descriptor.alignment_contract.model_copy(update=update)
        changed_descriptor = descriptor.model_copy(update={"alignment_contract": changed_contract})
        assert (
            _call(
                fingerprint_module,
                "reference_alignment_fingerprint",
                changed_descriptor,
                session_identity,
            )
            != expected
        ), label

    changed_clock_contract = descriptor.alignment_contract.model_copy(
        update={"source_clock_id": "reference-clock-2"}
    )
    descriptor_mutations = {
        "clock": descriptor.model_copy(
            update={
                "clock_id": "reference-clock-2",
                "alignment_contract": changed_clock_contract,
            }
        ),
        "source-schema": descriptor.model_copy(update={"source_schema_id": "reference-raw-v0.2"}),
        "aligned-schema": descriptor.model_copy(
            update={"aligned_schema_id": "reference-aligned-v0.2"}
        ),
        "table-contract": descriptor.model_copy(
            update={
                "table_contract": descriptor.table_contract.model_copy(
                    update={"table_contract_fingerprint": SHA_D}
                )
            }
        ),
        "resource": descriptor.model_copy(update={"resource_fingerprint": SHA_D}),
        "content": descriptor.model_copy(update={"aligned_content_fingerprint": SHA_E}),
    }
    for label, changed_descriptor in descriptor_mutations.items():
        assert (
            _call(
                fingerprint_module,
                "reference_alignment_fingerprint",
                changed_descriptor,
                session_identity,
            )
            != expected
        ), label


def test_resolved_reference_set_binds_absence_and_excludes_only_self_claim(
    fingerprint_module: ModuleType,
) -> None:
    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=_session_identity(),
        descriptors=(_descriptor(present=False),),
        reference_set_fingerprint=SHA_D,
    )
    payload = snapshot.model_dump(mode="json", exclude={"reference_set_fingerprint"})
    expected = _typed_hash("resolved-reference-set", "0.1.0", payload)

    assert _call(fingerprint_module, "resolved_reference_set_fingerprint", snapshot) == expected
    assert (
        _call(
            fingerprint_module,
            "resolved_reference_set_fingerprint",
            snapshot.model_copy(update={"reference_set_fingerprint": SHA_E}),
        )
        == expected
    )
    changed_identity = snapshot.session_identity.model_copy(update={"session_end_t_ns": END_NS - 1})
    assert (
        _call(
            fingerprint_module,
            "resolved_reference_set_fingerprint",
            snapshot.model_copy(update={"session_identity": changed_identity}),
        )
        != expected
    )


def test_absent_reference_never_invents_resource_content_or_alignment_hashes(
    fingerprint_module: ModuleType,
) -> None:
    absent = _descriptor(present=False)
    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=_session_identity(),
        descriptors=(absent,),
        reference_set_fingerprint=SHA_D,
    )

    assert len(_call(fingerprint_module, "resolved_reference_set_fingerprint", snapshot)) == 64
    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "reference_resource_fingerprint", absent)
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "reference_alignment_fingerprint",
            absent,
            snapshot.session_identity,
        )
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "aligned_reference_content_fingerprint",
            None,
            absent.aligned_schema_id,
            absent.table_contract,
        )


def _artifact_table_descriptor() -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        {
            "type": "table",
            "fields": [
                {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
                {"name": "value", "dtype": "f64", "unit": "ratio", "nullable": False},
            ],
            "canonical_order_keys": ["t_ns"],
        },
    )


def _artifact_ref(
    *,
    kind: str,
    schema_id: str,
    logical_sha256: str,
    storage_sha256: str | None,
    row_count: int,
    start_t_ns: int | None,
    end_t_ns: int | None,
    grid_hash: str | None,
) -> AnchorArtifactRef:
    return AnchorArtifactRef(
        artifact_id="artifact-1",
        kind=kind,
        schema_id=schema_id,
        logical_content_sha256=logical_sha256,
        storage_file_sha256=storage_sha256,
        row_count=row_count,
        start_t_ns=start_t_ns,
        end_t_ns=end_t_ns,
        grid_hash=grid_hash,
        producer_anchor_id="O1",
        producer_plugin_id="o1-plugin",
        producer_plugin_version="0.1.0",
        parameter_hash=SHA_C,
        dependency_fingerprints=(),
    )


def test_table_artifact_validation_recomputes_immutable_logical_content(
    fingerprint_module: ModuleType,
) -> None:
    descriptor = _artifact_table_descriptor()
    frame = pl.DataFrame(
        {
            "t_ns": pl.Series("t_ns", [0, 1], dtype=pl.Int64),
            "value": pl.Series("value", [0.25, 0.5], dtype=pl.Float64),
        }
    )
    logical_hash = _call(
        fingerprint_module,
        "logical_table_sha256",
        "artifact-table-v0.1",
        descriptor,
        frame.to_dicts(),
        ("t_ns",),
    )
    ref = _artifact_ref(
        kind="derived-table",
        schema_id="artifact-table-v0.1",
        logical_sha256=logical_hash,
        storage_sha256=SHA_B,
        row_count=2,
        start_t_ns=0,
        end_t_ns=1,
        grid_hash=SHA_D,
    )
    payload = ReadOnlyTabularPayload(
        schema_id=ref.schema_id,
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=("t_ns",),
        artifact_kind=ref.kind,
        grid_hash=ref.grid_hash,
        start_t_ns=ref.start_t_ns,
        end_t_ns=ref.end_t_ns,
        logical_content_sha256=logical_hash,
    )
    resolved = ResolvedArtifactDependency(ref=ref, payload=payload)

    assert _call(fingerprint_module, "validate_logical_artifact_ref", ref, resolved) is None
    assert _call(fingerprint_module, "logical_artifact_identity_payload", ref) == _call(
        fingerprint_module,
        "logical_artifact_identity_payload",
        ref.model_copy(update={"storage_file_sha256": SHA_E}),
    )
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "validate_logical_artifact_ref",
            ref.model_copy(update={"storage_file_sha256": SHA_E}),
            resolved,
        )

    corrupted_payload = ReadOnlyTabularPayload(
        schema_id=ref.schema_id,
        schema_descriptor=descriptor,
        frame=frame.with_columns(pl.lit(0.75).alias("value")),
        order_keys=("t_ns",),
        artifact_kind=ref.kind,
        grid_hash=ref.grid_hash,
        start_t_ns=ref.start_t_ns,
        end_t_ns=ref.end_t_ns,
        logical_content_sha256=logical_hash,
    )
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "validate_logical_artifact_ref",
            ref,
            ResolvedArtifactDependency(ref=ref, payload=corrupted_payload),
        )


def test_blob_artifact_validation_requires_raw_hash_and_equal_storage_digest(
    fingerprint_module: ModuleType,
) -> None:
    blob = b"tiny deterministic blob\n"
    logical_hash = hashlib.sha256(blob).hexdigest()
    ref = _artifact_ref(
        kind="derived-blob",
        schema_id="artifact-blob-v0.1",
        logical_sha256=logical_hash,
        storage_sha256=logical_hash,
        row_count=0,
        start_t_ns=None,
        end_t_ns=None,
        grid_hash=None,
    )
    payload = ReadOnlyBlobPayload(
        schema_id=ref.schema_id,
        payload_bytes=blob,
        artifact_kind=ref.kind,
        start_t_ns=None,
        end_t_ns=None,
        logical_content_sha256=logical_hash,
    )
    resolved = ResolvedArtifactDependency(ref=ref, payload=payload)

    assert _call(fingerprint_module, "validate_logical_artifact_ref", ref, resolved) is None
    for bad_storage_digest in (None, SHA_D):
        bad_ref = ref.model_copy(update={"storage_file_sha256": bad_storage_digest})
        equal_bad_resolved = ResolvedArtifactDependency(ref=bad_ref, payload=payload)
        with pytest.raises((TypeError, ValueError)):
            _call(
                fingerprint_module,
                "validate_logical_artifact_ref",
                bad_ref,
                equal_bad_resolved,
            )

    corrupted_payload = ReadOnlyBlobPayload(
        schema_id=ref.schema_id,
        payload_bytes=b"changed",
        artifact_kind=ref.kind,
        start_t_ns=None,
        end_t_ns=None,
        logical_content_sha256=logical_hash,
    )
    with pytest.raises((TypeError, ValueError)):
        _call(
            fingerprint_module,
            "validate_logical_artifact_ref",
            ref,
            ResolvedArtifactDependency(ref=ref, payload=corrupted_payload),
        )
