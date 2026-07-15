from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AoiDefinition,
    AoiGeometryKind,
    BaselineChannelBinding,
    BaselineDefinition,
    BaselineModality,
    ControlEffectMapping,
    DynamicAoiSource,
    EnvelopeAxisLimit,
    EnvelopeDefinition,
    ReferenceAlignmentContract,
    ReferenceFieldContract,
    ReferenceResolutionStatus,
    ReferenceResourceChecksum,
    ReferenceSessionIdentity,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
    SemanticApplicabilityStatus,
    SemanticEvent,
    SemanticPhase,
    SemanticVector,
    SessionSemanticSnapshot,
    TaskTargetDefinition,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
END_NS = 10_000_000_000


def _semantic_payload() -> dict[str, object]:
    return {
        "session_id": "session-1",
        "task_profile_id": "profile-1",
        "scenario_id": "scenario-1",
        "source_snapshot_fingerprint": SHA_A,
        "synchronization_fingerprint": SHA_B,
        "annotation_revision": "annotations-1",
        "synthetic_semantics_unvalidated": False,
        "session_end_t_ns": END_NS,
        "phases": [
            {
                "phase_id": "phase-1",
                "phase_type": "departure",
                "start_t_ns": 0,
                "end_t_ns": 5_000_000_000,
                "target_id": "target-1",
                "envelope_id": "envelope-1",
            },
            {
                "phase_id": "phase-2",
                "phase_type": "arrival",
                "start_t_ns": 5_000_000_000,
                "end_t_ns": END_NS,
                "include_session_terminal_point": True,
                "target_id": "target-1",
                "envelope_id": "envelope-1",
            },
        ],
        "events": [
            {
                "event_id": "event-1",
                "event_type": "disturbance",
                "t_ns": 6_000_000_000,
                "duration_ns": 1_000_000_000,
                "opportunity_end_t_ns": 8_000_000_000,
                "phase_id": "phase-2",
                "target_id": "target-1",
                "envelope_id": "envelope-1",
                "relevant_aoi_ids": ["aoi-other"],
                "control_mapping_ids": ["control-1"],
            }
        ],
        "aois": [
            {
                "aoi_id": "aoi-other",
                "taxonomy_id": "taxonomy-1",
                "role": "other_scene",
                "geometry_kind": "catch_all",
                "priority": 0,
                "role_weight": 0.0,
                "off_task": True,
            }
        ],
        "control_mappings": [
            {
                "control_mapping_id": "control-1",
                "state_axis_id": "x",
                "control_channel_id": "stick-x",
                "correct_sign": 1,
                "state_unit": "m",
                "control_unit": "normalized",
                "lower": -1.0,
                "trim": 0.0,
                "upper": 1.0,
            }
        ],
        "baselines": [
            {
                "baseline_id": "baseline-1",
                "start_t_ns": 0,
                "end_t_ns": 2_000_000_000,
                "channel_bindings": [{"modality": "ECG", "channel_ids": ["ecg-1"]}],
                "condition_id": "rest",
                "annotation_valid": True,
            }
        ],
        "targets": [
            {
                "target_id": "target-1",
                "position": {
                    "coordinate_frame_id": "world",
                    "unit": "m",
                    "values": [0.0, 0.0, 0.0],
                },
                "arrival_axis": {
                    "coordinate_frame_id": "world",
                    "unit": "dimensionless",
                    "values": [1.0, 0.0, 0.0],
                },
            }
        ],
        "envelopes": [
            {
                "envelope_id": "envelope-1",
                "target_id": "target-1",
                "axis_limits": [
                    {
                        "metric_id": "position-error",
                        "desired_abs_max": 1.0,
                        "adequate_abs_max": 2.0,
                        "unit": "m",
                    }
                ],
            }
        ],
        "applicability": [
            {
                "anchor_id": "O1",
                "status": "applicable",
                "phase_ids": ["phase-2"],
                "event_ids": ["event-1"],
                "aoi_ids": ["aoi-other"],
                "control_mapping_ids": ["control-1"],
                "baseline_ids": ["baseline-1"],
                "target_ids": ["target-1"],
                "envelope_ids": ["envelope-1"],
            }
        ],
        "semantic_snapshot_fingerprint": SHA_C,
    }


def _reference_parts() -> tuple[
    ReferenceSessionIdentity,
    ReferenceAlignmentContract,
    ReferenceTableContract,
]:
    identity = ReferenceSessionIdentity(
        session_id="session-1",
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        session_end_t_ns=END_NS,
    )
    alignment = ReferenceAlignmentContract(
        mapping_method="affine-v1",
        mapping_policy_id="policy-v1",
        source_clock_id="reference-clock",
        scale=1.0,
        offset_ns=0,
        declared_drift_ppm=0.0,
    )
    table = ReferenceTableContract(
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
        table_contract_fingerprint=SHA_C,
    )
    return identity, alignment, table


def _descriptor_payload(*, present: bool = True) -> dict[str, object]:
    _, alignment, table = _reference_parts()
    payload: dict[str, object] = {
        "reference_id": "reference-1",
        "resolution_status": "present" if present else "absent",
        "source_kind": "bundle",
        "source_schema_id": "reference-raw-v0.1",
        "aligned_schema_id": "reference-aligned-v0.1",
        "clock_id": "reference-clock",
        "alignment_contract": alignment.model_dump(mode="python"),
        "table_contract": table.model_dump(mode="python"),
        "resource_checksums": (
            [{"path": "references/commanded.parquet", "checksum": SHA_D}] if present else []
        ),
        "resource_fingerprint": SHA_D if present else None,
        "aligned_content_fingerprint": SHA_E if present else None,
        "alignment_fingerprint": SHA_F if present else None,
        "absence_reason": None if present else "not-provided",
    }
    return payload


def test_semantic_snapshot_round_trip_is_strict_and_frozen() -> None:
    snapshot = SessionSemanticSnapshot.model_validate(_semantic_payload())

    assert SessionSemanticSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert snapshot.contract_id == "session-semantic-snapshot"
    assert snapshot.contract_version == "0.1.0"
    with pytest.raises(ValidationError):
        SessionSemanticSnapshot.model_validate({**_semantic_payload(), "extra": True})
    with pytest.raises(ValidationError):
        snapshot.session_id = "changed"  # type: ignore[misc]


def test_semantic_snapshot_allows_distinct_events_in_the_same_phase() -> None:
    payload = _semantic_payload()
    second_event = deepcopy(payload["events"][0])  # type: ignore[index]
    second_event.update(
        {
            "event_id": "event-2",
            "t_ns": 7_000_000_000,
            "duration_ns": 1_000_000_000,
            "opportunity_end_t_ns": 9_000_000_000,
        }
    )
    payload["events"].append(second_event)  # type: ignore[union-attr]
    payload["applicability"][0]["event_ids"] = ["event-1", "event-2"]  # type: ignore[index]

    snapshot = SessionSemanticSnapshot.model_validate(payload)

    assert tuple(event.event_id for event in snapshot.events) == ("event-1", "event-2")


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [
        (lambda p: p["phases"].append(deepcopy(p["phases"][0])), "phase"),
        (lambda p: p["phases"].reverse(), "canonical"),
        (lambda p: p["events"][0].update({"t_ns": 4_000_000_000}), "phase"),
        (lambda p: p["events"][0].update({"duration_ns": 0}), "duration"),
        (lambda p: p["events"][0].update({"target_id": "missing"}), "target"),
        (lambda p: p.update({"session_start_t_ns": False}), "integer zero"),
    ],
)
def test_semantic_snapshot_rejects_temporal_and_reference_violations(
    mutate: object, expected_fragment: str
) -> None:
    payload = _semantic_payload()
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(ValidationError, match=expected_fragment):
        SessionSemanticSnapshot.model_validate(payload)


def test_geometry_control_baseline_and_applicability_matrices() -> None:
    with pytest.raises(ValidationError):
        SemanticVector(coordinate_frame_id="world", unit="m", values=(0.0,))
    with pytest.raises(ValidationError, match="arrival"):
        TaskTargetDefinition(
            target_id="t",
            position=SemanticVector(coordinate_frame_id="world", unit="m", values=(0.0, 0.0, 0.0)),
            arrival_axis=SemanticVector(
                coordinate_frame_id="world",
                unit="dimensionless",
                values=(0.0, 0.0, 0.0),
            ),
        )
    with pytest.raises(ValidationError):
        AoiDefinition(
            aoi_id="poly",
            taxonomy_id="tax",
            role="instrument",
            geometry_kind=AoiGeometryKind.POLYGON_2D,
            priority=1,
            role_weight=1.0,
            off_task=False,
            vertices=(
                SemanticVector(coordinate_frame_id="screen", unit="px", values=(0.0, 0.0)),
                SemanticVector(coordinate_frame_id="screen", unit="px", values=(1.0, 1.0)),
                SemanticVector(coordinate_frame_id="screen", unit="px", values=(2.0, 2.0)),
            ),
        )
    with pytest.raises(ValidationError):
        ControlEffectMapping(
            control_mapping_id="c",
            state_axis_id="x",
            control_channel_id="u",
            correct_sign=False,
            state_unit="m",
            control_unit="normalized",
            lower=-1.0,
            trim=0.0,
            upper=1.0,
        )
    with pytest.raises(ValidationError):
        BaselineDefinition(
            baseline_id="b",
            start_t_ns=0,
            end_t_ns=1,
            channel_bindings=(
                BaselineChannelBinding(modality=BaselineModality.ECG, channel_ids=("c",)),
            ),
            annotation_valid=False,
        )
    with pytest.raises(ValidationError):
        AnchorApplicability(
            anchor_id="O1",
            status=SemanticApplicabilityStatus.NOT_APPLICABLE,
            phase_ids=("phase-1",),
            reason="scenario-excludes-anchor",
        )


def test_dynamic_and_catch_all_aoi_contracts_are_explicit() -> None:
    source = DynamicAoiSource(
        table_role="aoi-geometry",
        aligned_schema_id="aoi-aligned-v0.1",
        coordinate_frame_id="screen",
        unit="px",
        frame_id_field="frame-id",
        aoi_id_field="aoi-id",
        geometry_field_ids=("x-min", "y-min", "x-max", "y-max"),
    )
    dynamic = AoiDefinition(
        aoi_id="dynamic",
        taxonomy_id="tax",
        role="display",
        geometry_kind=AoiGeometryKind.DYNAMIC_2D,
        priority=1,
        role_weight=1.0,
        off_task=False,
        dynamic_source=source,
    )
    assert dynamic.dynamic_source is source

    with pytest.raises(ValidationError):
        AoiDefinition(
            aoi_id="other",
            taxonomy_id="tax",
            role="other_scene",
            geometry_kind=AoiGeometryKind.CATCH_ALL,
            priority=0,
            role_weight=0.5,
            off_task=True,
        )


def test_reference_contract_present_absent_and_decimal_consistency() -> None:
    present = ResolvedReferenceDescriptor.model_validate(_descriptor_payload())
    absent = ResolvedReferenceDescriptor.model_validate(_descriptor_payload(present=False))
    assert present.resolution_status is ReferenceResolutionStatus.PRESENT
    assert absent.resolution_status is ReferenceResolutionStatus.ABSENT

    invalid = _descriptor_payload()
    invalid["absence_reason"] = "cannot-be-present"
    with pytest.raises(ValidationError):
        ResolvedReferenceDescriptor.model_validate(invalid)

    invalid = _descriptor_payload(present=False)
    invalid["resource_fingerprint"] = SHA_D
    with pytest.raises(ValidationError):
        ResolvedReferenceDescriptor.model_validate(invalid)

    with pytest.raises(ValidationError, match="drift"):
        ReferenceAlignmentContract(
            mapping_method="affine-v1",
            mapping_policy_id="policy-v1",
            source_clock_id="clock",
            scale=1.000001,
            offset_ns=0,
            declared_drift_ppm=2.0,
        )


def test_reference_table_and_snapshot_reject_noncanonical_or_ambiguous_inventory() -> None:
    identity, _, table = _reference_parts()
    assert table.canonical_order_keys == ("t_ns", "row-id")

    with pytest.raises(ValidationError):
        ReferenceTableContract(
            **{
                **table.model_dump(mode="python"),
                "stable_row_id_field": "t_ns",
                "canonical_order_keys": ("t_ns", "t_ns"),
            }
        )

    descriptor = ResolvedReferenceDescriptor.model_validate(_descriptor_payload())
    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=identity,
        descriptors=(descriptor,),
        reference_set_fingerprint=SHA_A,
    )
    assert snapshot.contract_id == "resolved-reference-set"
    assert "aligned_view" not in snapshot.model_dump()

    duplicate = descriptor.model_copy(update={"reference_id": "reference-2"})
    with pytest.raises(ValidationError):
        ResolvedReferenceSetSnapshot(
            session_identity=identity,
            descriptors=(descriptor, duplicate),
            reference_set_fingerprint=SHA_A,
        )

    invalid = _descriptor_payload()
    invalid["resource_checksums"] = [
        {"path": "references/A.parquet", "checksum": SHA_D},
        {"path": "references/a.parquet", "checksum": SHA_E},
    ]
    with pytest.raises(ValidationError):
        ResolvedReferenceDescriptor.model_validate(invalid)


def test_public_leaf_models_enforce_envelope_phase_and_event_bounds() -> None:
    with pytest.raises(ValidationError):
        EnvelopeAxisLimit(metric_id="error", desired_abs_max=2.0, adequate_abs_max=1.0, unit="m")
    with pytest.raises(ValidationError):
        EnvelopeDefinition(envelope_id="e", target_id="t", axis_limits=())
    with pytest.raises(ValidationError):
        SemanticPhase(phase_id="p", phase_type="x", start_t_ns=1, end_t_ns=1)
    with pytest.raises(ValidationError):
        SemanticEvent(event_id="e", event_type="x", t_ns=1, duration_ns=0)
    with pytest.raises(ValidationError):
        ReferenceResourceChecksum(path="../escape", checksum=SHA_A)


def test_semantics_preserve_m3_audit_fields_and_allow_shared_target_envelopes() -> None:
    baseline = BaselineDefinition(
        baseline_id="b",
        start_t_ns=0,
        end_t_ns=1,
        channel_bindings=(
            BaselineChannelBinding(modality=BaselineModality.ECG, channel_ids=("ecg",)),
        ),
        annotation_valid=True,
        annotation_exclusion_reason="source-note-preserved-verbatim",
    )
    assert baseline.annotation_exclusion_reason == "source-note-preserved-verbatim"

    payload = _semantic_payload()
    second_envelope = deepcopy(payload["envelopes"][0])
    second_envelope["envelope_id"] = "envelope-2"
    payload["envelopes"].append(second_envelope)
    snapshot = SessionSemanticSnapshot.model_validate(payload)
    assert tuple(item.envelope_id for item in snapshot.envelopes) == (
        "envelope-1",
        "envelope-2",
    )


def test_unscoped_terminal_event_is_valid_without_duration_or_opportunity() -> None:
    payload = _semantic_payload()
    payload["events"][0].update(
        {
            "t_ns": END_NS,
            "duration_ns": None,
            "opportunity_end_t_ns": None,
            "phase_id": None,
        }
    )
    snapshot = SessionSemanticSnapshot.model_validate(payload)
    assert snapshot.events[0].t_ns == END_NS
