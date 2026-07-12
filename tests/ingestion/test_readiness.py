from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from pilot_assessment.contracts.ingestion import ReadinessDisposition, StreamReadiness
from pilot_assessment.contracts.session import SessionManifest
from pilot_assessment.ingestion.adapters.profiled_csv import ProfiledCsvAdapter
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.readiness import (
    inspect_ingestion_readiness,
    inspect_loaded_ingestion_readiness,
    source_snapshot_fingerprint,
)
from pilot_assessment.synthetic.generator import generate_synthetic_bundle

HEADERS = (
    "Simulation time",
    " Xe m",
    " Ye m",
    " Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "  V_ey m/s",
    " V_ez m/s",
    "V_ex kts",
    "  V_ey kts",
    " V_ez kts",
    "V_bx m/s",
    " V_by m/s",
    " V_bz m/s",
    "phi deg",
    " theta deg",
    " psi deg",
    "p deg/s",
    " q deg/s",
    " r deg/s",
    "ax m/s^2",
    " ay m/s^2",
    " az m/s^2",
    "alpha deg",
    " beta deg",
    "Control_Mode",
    "Pilot Yaw",
    " Pilot Lon",
    " Pilot Lat",
    " Pilot Heave",
    "Time Delay s",
    " Lon Frequency rad/s",
    " Long Damping ",
)
KNOTS_PER_METRE_PER_SECOND = 1.9438444924406048


def _write_micro_csv(path: Path, duration_s: float = 2.0) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADERS)
    count = round(duration_s * 100.0) + 1
    for index in range(count):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        writer.writerow(
            [
                str(time_s),
                str(0.75 * time_s),
                "0",
                "-31.668",
                "21.008",
                *(str(value) for value in velocities),
                *(str(value * KNOTS_PER_METRE_PER_SECOND) for value in velocities),
                *(str(value) for value in velocities),
                "0",
                "0",
                "270",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "1",
                "0",
                str(-100.0 * index / (count - 1)),
                "0",
                "0",
                "0.2",
                "8",
                "0.8",
            ]
        )
    path.write_bytes(output.getvalue().encode("utf-8"))


def _full_bundle(tmp_path: Path, name: str = "bundle") -> Path:
    source = tmp_path / f"{name}.csv"
    _write_micro_csv(source)
    return generate_synthetic_bundle(source, tmp_path / name, seed=20260711)


def _write_manifest(bundle: Path, manifest: dict[str, object]) -> None:
    SessionManifest.model_validate(manifest)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _rewrite_checksum_scope(bundle: Path, manifest: dict[str, object]) -> None:
    streams = manifest["streams"]
    assert isinstance(streams, dict)
    paths = {
        path
        for descriptor in streams.values()
        if isinstance(descriptor, dict) and descriptor["status"] in {"present", "invalid"}
        for path in descriptor["paths"]
    }
    annotations = manifest["annotations"]
    assert isinstance(annotations, dict)
    paths.update(
        {
            annotations["phases"],
            annotations["events"],
            annotations["baseline_intervals"],
        }
    )
    lines = []
    for relative_path in sorted(paths):
        assert isinstance(relative_path, str)
        payload = bundle.joinpath(*relative_path.split("/")).read_bytes()
        lines.append(f"{hashlib.sha256(payload).hexdigest()}  {relative_path}")
    (bundle / "integrity" / "checksums.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def _set_status(
    bundle: Path,
    modality: str,
    status: str,
    *,
    required: bool = False,
) -> None:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    descriptor = manifest["streams"][modality]
    descriptor["status"] = status
    descriptor["required_for_import"] = required
    if status in {"export_pending", "missing", "not_applicable"}:
        descriptor["paths"] = []
        descriptor["checksums"] = {}
        descriptor["quality_summary"] = None
    if status in {"missing", "not_applicable"}:
        descriptor["clock_sync"] = None
    if status == "invalid":
        descriptor["quality_summary"] = None
    _rewrite_checksum_scope(bundle, manifest)
    _write_manifest(bundle, manifest)


def test_generated_full_bundle_is_ready_but_never_formally_authorized(
    tmp_path: Path,
) -> None:
    bundle = _full_bundle(tmp_path)

    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.report.disposition is ReadinessDisposition.READY
    assert outcome.report.can_continue_to_synchronization is True
    assert outcome.report.formal_run_authorized is False
    assert all(
        result.readiness is StreamReadiness.READY
        for result in outcome.report.stream_results.values()
    )
    assert outcome.report.task_reference_result is not None
    assert outcome.report.task_reference_result.readiness is StreamReadiness.READY
    assert outcome.report.task_reference_result.required_for_import is True
    assert outcome.prepared_session is not None
    assert set(outcome.prepared_session.streams) == {
        "X",
        "U",
        "I",
        "G",
        "EEG",
        "ECG",
        "pilot_camera",
    }
    assert outcome.prepared_session.task_reference is not None


@pytest.mark.parametrize(
    ("status", "expected_readiness", "expected_disposition"),
    [
        ("export_pending", StreamReadiness.UNAVAILABLE, ReadinessDisposition.READY_PARTIAL),
        ("missing", StreamReadiness.UNAVAILABLE, ReadinessDisposition.READY_PARTIAL),
        ("invalid", StreamReadiness.INVALID, ReadinessDisposition.READY_PARTIAL),
        ("not_applicable", StreamReadiness.NOT_APPLICABLE, ReadinessDisposition.READY),
    ],
)
def test_optional_status_matrix_is_explicit(
    tmp_path: Path,
    status: str,
    expected_readiness: StreamReadiness,
    expected_disposition: ReadinessDisposition,
) -> None:
    bundle = _full_bundle(tmp_path)
    _set_status(bundle, "I", status)

    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.report.stream_results["I"].readiness is expected_readiness
    assert outcome.report.disposition is expected_disposition
    assert outcome.report.can_continue_to_synchronization is True


@pytest.mark.parametrize("status", ["export_pending", "missing", "invalid"])
def test_required_non_ready_stream_blocks_synchronization(
    tmp_path: Path,
    status: str,
) -> None:
    bundle = _full_bundle(tmp_path)
    _set_status(bundle, "I", status, required=True)

    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.report.disposition is ReadinessDisposition.BLOCKED
    assert outcome.report.can_continue_to_synchronization is False
    assert outcome.prepared_session is None


def test_shared_xu_source_is_dispatched_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _full_bundle(tmp_path)
    calls = 0
    original = ProfiledCsvAdapter.inspect

    def counted(self: ProfiledCsvAdapter, request: object) -> object:
        nonlocal calls
        calls += 1
        return original(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(ProfiledCsvAdapter, "inspect", counted)

    inspect_ingestion_readiness(bundle)

    assert calls == 1


def test_loaded_readiness_reuses_the_exact_m1_snapshot(tmp_path: Path) -> None:
    ready_bundle = _full_bundle(tmp_path)
    loaded = ManifestLoader().load(ready_bundle)

    outcome = inspect_loaded_ingestion_readiness(loaded)

    assert outcome.report.source_snapshot_fingerprint == source_snapshot_fingerprint(loaded)
    assert outcome.prepared_session is not None


def test_path_readiness_loads_manifest_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_bundle = _full_bundle(tmp_path)
    calls = 0
    original = ManifestLoader.load

    def counted(self: ManifestLoader, bundle_root: str | Path) -> LoadedManifest:
        nonlocal calls
        calls += 1
        return original(self, bundle_root)

    monkeypatch.setattr(ManifestLoader, "load", counted)

    outcome = inspect_ingestion_readiness(ready_bundle)

    assert calls == 1
    assert outcome.prepared_session is not None


def test_fingerprint_and_report_are_independent_of_bundle_root(tmp_path: Path) -> None:
    first = _full_bundle(tmp_path, "first")
    second_source = tmp_path / "second.csv"
    second_source.write_bytes((tmp_path / "first.csv").read_bytes())
    second = generate_synthetic_bundle(second_source, tmp_path / "second", seed=20260711)

    first_report = inspect_ingestion_readiness(first).report
    second_report = inspect_ingestion_readiness(second).report

    assert first_report.source_snapshot_fingerprint == second_report.source_snapshot_fingerprint
    assert first_report.model_dump(mode="json") == second_report.model_dump(mode="json")


def test_unregistered_present_schema_is_reported_as_unsupported(tmp_path: Path) -> None:
    bundle = _full_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["streams"]["I"]["schema_id"] = "unregistered-scene-v0.1"
    _write_manifest(bundle, manifest)

    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.report.stream_results["I"].readiness is StreamReadiness.UNSUPPORTED
    assert outcome.report.disposition is ReadinessDisposition.READY_PARTIAL
    assert outcome.report.stream_results["I"].issues[0].error_code == "ADAPTER_NOT_FOUND"
