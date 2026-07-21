from __future__ import annotations

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.session import CORE_MODALITIES, StreamStatus
from pilot_assessment.contracts.session_source import (
    RawAnnotationMapping,
    RawFieldMapping,
    RawModalityProposal,
    RawSessionInspection,
    RawSourceFile,
    SessionDataSourceKind,
    SessionSourceInspection,
    UnitProvenance,
)

_DIGEST = "1" * 64


def _proposals() -> dict[str, RawModalityProposal]:
    return {
        modality: RawModalityProposal(
            modality=modality,
            status=StreamStatus.PRESENT if modality in {"X", "U"} else StreamStatus.MISSING,
            paths=("streams/simulator.csv",) if modality in {"X", "U"} else (),
            format="csv" if modality in {"X", "U"} else "unavailable",
            schema_id=(
                "cranfield-simulator-combined-csv-raw-v0.1"
                if modality in {"X", "U"}
                else f"{modality.lower()}-missing-v0.1"
            ),
            clock_id="simulator-clock",
            sample_rate_hz=100.0 if modality in {"X", "U"} else None,
            declared_units={},
            unit_handling="undeclared-pass-through-v1",
        )
        for modality in CORE_MODALITIES
    }


def _raw_inspection(**overrides: object) -> RawSessionInspection:
    payload: dict[str, object] = {
        "source_snapshot_fingerprint": _DIGEST,
        "detected_profile_id": "cranfield-simulator-combined-csv-raw-v0.1",
        "files": (
            RawSourceFile(
                relative_path="streams/simulator.csv",
                byte_size=12,
                sha256=_DIGEST,
            ),
        ),
        "field_mappings": (
            RawFieldMapping(
                source_path="streams/simulator.csv",
                source_field="Pilot Yaw",
                canonical_field="control.yaw_raw",
                modality="U",
                physical_dtype="f64",
                declared_unit=None,
                unit_provenance=UnitProvenance.UNDECLARED,
                timestamp_role="measurement",
            ),
        ),
        "modality_proposals": _proposals(),
        "annotation_mappings": (
            RawAnnotationMapping(
                record_field="events",
                canonical_path="_pilot_assessment/annotations/events.json",
                record_count=0,
                disposition="empty",
            ),
        ),
        "can_materialize": True,
    }
    payload.update(overrides)
    return RawSessionInspection.model_validate(payload)


def test_undeclared_units_do_not_create_required_input() -> None:
    raw = _raw_inspection()

    assert raw.required_user_inputs == ()
    assert raw.can_materialize is True
    assert raw.field_mappings[0].declared_unit is None
    assert raw.field_mappings[0].unit_provenance is UnitProvenance.UNDECLARED


def test_raw_inspection_requires_all_core_modalities() -> None:
    proposals = _proposals()
    proposals.pop("G")

    with pytest.raises(ValidationError, match="exactly seven core modalities"):
        _raw_inspection(modality_proposals=proposals)


def test_source_kind_requires_matching_payload() -> None:
    raw = _raw_inspection()
    inspection = SessionSourceInspection(
        source_kind=SessionDataSourceKind.SIMULATOR_RAW,
        raw=raw,
    )

    assert inspection.raw == raw

    with pytest.raises(ValidationError, match="raw source inspection requires only raw payload"):
        SessionSourceInspection(source_kind=SessionDataSourceKind.SIMULATOR_RAW)


def test_declared_unit_and_provenance_must_agree() -> None:
    with pytest.raises(ValidationError, match="requires declared_unit=null"):
        RawFieldMapping(
            source_path="streams/simulator.csv",
            source_field="Pilot Yaw",
            canonical_field="control.yaw_raw",
            modality="U",
            physical_dtype="f64",
            declared_unit="ratio",
            unit_provenance=UnitProvenance.UNDECLARED,
            timestamp_role="measurement",
        )
