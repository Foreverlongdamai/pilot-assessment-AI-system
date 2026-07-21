from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.ingestion import ReadinessDisposition, StreamReadiness
from pilot_assessment.contracts.session import CORE_MODALITIES, StreamStatus
from pilot_assessment.contracts.session_source import SessionDataSourceKind, UnitProvenance
from pilot_assessment.ingestion.profiles import CsvProfile, load_builtin_profiles
from pilot_assessment.ingestion.raw_session import (
    RawSessionError,
    inspect_session_source,
    materialize_raw_session,
)


def _raw_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "raw"
    streams = root / "streams"
    annotations = root / "annotations"
    streams.mkdir(parents=True)
    annotations.mkdir()
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    assert isinstance(profile, CsvProfile)
    headers = [column.source_header for column in profile.columns]
    rows = []
    for index in range(6):
        values = ["0" for _ in headers]
        values[headers.index("Simulation time")] = f"{index / 100:.2f}"
        values[headers.index("Control_Mode")] = "1"
        values[headers.index("Time Delay s")] = "0.2"
        values[headers.index("Lon Frequency rad/s")] = "8"
        values[headers.index("Long Damping")] = "0.8"
        rows.append(",".join(values))
    (streams / "simulator.csv").write_text(
        ",".join(headers) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="",
    )
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_raw_inspection_is_read_only_and_undeclared_units_are_not_inputs(tmp_path: Path) -> None:
    raw_root = _raw_fixture(tmp_path)
    before = _snapshot(raw_root)

    inspected = inspect_session_source(raw_root)

    assert inspected.source_kind is SessionDataSourceKind.SIMULATOR_RAW
    assert inspected.raw is not None
    assert inspected.raw.detected_profile_id == "cranfield-simulator-combined-csv-raw-v0.1"
    assert inspected.raw.required_user_inputs == ()
    assert inspected.raw.can_materialize is True
    assert set(inspected.raw.modality_proposals) == set(CORE_MODALITIES)
    assert inspected.raw.modality_proposals["X"].status is StreamStatus.PRESENT
    assert inspected.raw.modality_proposals["U"].status is StreamStatus.PRESENT
    assert inspected.raw.modality_proposals["G"].status is StreamStatus.MISSING
    yaw = next(
        mapping
        for mapping in inspected.raw.field_mappings
        if mapping.canonical_field == "control.yaw_raw"
    )
    assert yaw.declared_unit is None
    assert yaw.unit_provenance is UnitProvenance.UNDECLARED
    assert _snapshot(raw_root) == before


def test_materialization_preserves_raw_bytes_and_builds_partial_bundle(tmp_path: Path) -> None:
    raw_root = _raw_fixture(tmp_path)
    before = _snapshot(raw_root)
    inspected = inspect_session_source(raw_root)
    assert inspected.raw is not None

    result = materialize_raw_session(
        raw_root,
        tmp_path / "managed-bundle",
        inspection=inspected.raw,
        transaction_id="tx-raw-test-001",
        created_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
    )

    assert _snapshot(raw_root) == before
    assert (result.loaded.bundle_root / "streams" / "simulator.csv").read_bytes() == (
        raw_root / "streams" / "simulator.csv"
    ).read_bytes()
    assert result.readiness.disposition is ReadinessDisposition.READY_PARTIAL
    assert result.readiness.stream_results["X"].readiness is StreamReadiness.READY
    assert result.readiness.stream_results["U"].readiness is StreamReadiness.READY
    assert result.readiness.stream_results["G"].readiness is StreamReadiness.UNAVAILABLE
    assert result.manifest.streams["U"].units == {}
    assert result.manifest.streams["G"].paths == []
    assert not (result.loaded.bundle_root / "streams" / "gaze").exists()
    assert not (result.loaded.bundle_root / "streams" / "eeg").exists()
    assert result.manifest.extensions["raw_import"]["unit_handling"] == (
        "undeclared-pass-through-v1"
    )


def test_materialization_rejects_source_changed_after_inspection(tmp_path: Path) -> None:
    raw_root = _raw_fixture(tmp_path)
    inspected = inspect_session_source(raw_root)
    assert inspected.raw is not None
    source = raw_root / "streams" / "simulator.csv"
    source.write_bytes(source.read_bytes() + b"\n")

    with pytest.raises(RawSessionError) as caught:
        materialize_raw_session(
            raw_root,
            tmp_path / "managed-bundle",
            inspection=inspected.raw,
            transaction_id="tx-raw-test-002",
            created_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        )

    assert caught.value.error.error_code == "RAW_SOURCE_CHANGED"


def test_existing_invalid_manifest_never_falls_back_to_raw(tmp_path: Path) -> None:
    raw_root = _raw_fixture(tmp_path)
    (raw_root / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(Exception) as caught:
        inspect_session_source(raw_root)

    assert type(caught.value).__name__ == "ManifestLoadError"
