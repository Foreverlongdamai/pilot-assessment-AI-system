from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pilot_assessment.contracts.errors import ErrorSeverity
from pilot_assessment.ingestion.manifest_loader import (
    ManifestLoader,
    ManifestLoaderLimits,
    ManifestLoadError,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "session_manifest_valid.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_declared_checksums(root: Path, manifest: dict[str, Any]) -> None:
    paths = {
        path
        for descriptor in manifest["streams"].values()
        if descriptor["status"] in {"present", "invalid"}
        for path in descriptor["paths"]
    }
    paths.update(
        {
            manifest["annotations"]["phases"],
            manifest["annotations"]["events"],
            manifest["annotations"]["baseline_intervals"],
        }
    )
    checksum_lines = []
    for relative_path in sorted(paths):
        artifact = root / Path(*relative_path.split("/"))
        checksum_lines.append(f"{_sha256(artifact.read_bytes())}  {relative_path}")
    _write(
        root / "integrity" / "checksums.sha256",
        ("\n".join(checksum_lines) + "\n").encode(),
    )


def _build_valid_bundle(root: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    files = {
        "streams/flight_state.parquet": b"synthetic flight state\n",
        "streams/control_input.parquet": b"synthetic control input\n",
        "annotations/phases.json": b'{"phases":[]}\n',
        "annotations/events.json": b'{"events":[]}\n',
        "annotations/baseline_intervals.json": b'{"baseline_intervals":[]}\n',
    }
    for relative_path, payload in files.items():
        _write(root / Path(*relative_path.split("/")), payload)

    manifest["streams"]["X"]["checksums"] = {
        "streams/flight_state.parquet": _sha256(files["streams/flight_state.parquet"])
    }
    manifest["streams"]["U"]["checksums"] = {
        "streams/control_input.parquet": _sha256(files["streams/control_input.parquet"])
    }

    checksum_lines = [
        f"{_sha256(payload)}  {relative_path}" for relative_path, payload in sorted(files.items())
    ]
    _write(
        root / "integrity" / "checksums.sha256",
        ("\n".join(checksum_lines) + "\n").encode(),
    )
    _write_manifest(root, manifest)
    return manifest


def _configure_shared_xu(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = "streams/simulator.csv"
    payload = b"time,state,control\n0.0,1.0,0.0\n"
    _write(root / "streams" / "simulator.csv", payload)
    digest = _sha256(payload)
    for modality in ("X", "U"):
        manifest["streams"][modality].update(
            paths=[path],
            format="csv",
            schema_id="cranfield-simulator-combined-csv-raw-v0.1",
            checksums={path: digest},
            metadata={
                "adapter_profile_id": "cranfield-simulator-combined-csv-raw-v0.1",
                "shared_source_id": "simulator-main",
                "view_id": modality,
            },
        )
    _write_declared_checksums(root, manifest)
    _write_manifest(root, manifest)
    return manifest


def _add_bundle_task_reference(root: Path, manifest: dict[str, Any]) -> None:
    path = "references/commanded_path.parquet"
    payload = b"synthetic commanded path\n"
    _write(root / "references" / "commanded_path.parquet", payload)
    descriptor = copy.deepcopy(manifest["streams"]["X"])
    descriptor.update(
        modality="task_reference",
        required_for_import=False,
        paths=[path],
        format="parquet",
        schema_id="task-reference-path-raw-v0.1",
        units="task-reference-units-v0.1",
        quality_summary=None,
        checksums={path: _sha256(payload)},
        metadata={"artifact_role": "task_reference"},
    )
    manifest["streams"]["task_reference"] = descriptor
    manifest["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }
    _write_declared_checksums(root, manifest)
    _write_manifest(root, manifest)


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_valid_directory_bundle_loads_without_mutating_sources(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    before = _snapshot_files(tmp_path)

    loaded = ManifestLoader().load(tmp_path)

    assert loaded.manifest.session_id == "session-p001-20260710-001"
    assert loaded.bundle_root == tmp_path.resolve()
    assert loaded.validation_scope == "inspect_only_structure_and_declared_file_integrity"
    assert "streams/flight_state.parquet" in loaded.verified_paths
    assert "streams/scene.mp4" not in loaded.verified_paths
    assert not (tmp_path / "streams" / "scene.mp4").exists()
    assert loaded.declared_reference_count == 6
    assert loaded.unique_artifact_count == 6
    assert _snapshot_files(tmp_path) == before


def test_bundle_root_must_be_a_directory(tmp_path: Path) -> None:
    bundle_file = tmp_path / "bundle.zip"
    bundle_file.write_bytes(b"not-supported-in-m1")

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(bundle_file)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


@pytest.mark.parametrize(
    "payload",
    [b"{invalid", b"[]", b"\xff\xfe"],
)
def test_manifest_must_be_utf8_json_object(tmp_path: Path, payload: bytes) -> None:
    (tmp_path / "manifest.json").write_bytes(payload)
    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)
    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.severity is ErrorSeverity.ERROR
    assert caught.value.error.message
    assert caught.value.error.remediation


def test_missing_manifest_returns_typed_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)
    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.field_or_path == "manifest.json"


def test_unsupported_schema_major_has_specific_error(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    manifest["bundle_schema_version"] = "1.0.0"
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "SCHEMA_INCOMPATIBLE"


def test_missing_present_stream_file_is_rejected(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    (tmp_path / "streams" / "flight_state.parquet").unlink()

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "STREAM_MISSING"


def test_missing_annotation_file_is_rejected(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    (tmp_path / "annotations" / "events.json").unlink()

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_missing_integrity_file_is_rejected(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    (tmp_path / "integrity" / "checksums.sha256").unlink()

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    (tmp_path / "streams" / "control_input.parquet").write_bytes(b"tampered")

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "CHECKSUM_MISMATCH"
    assert caught.value.error.recoverable is True


def test_checksum_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    checksum_file = tmp_path / "integrity" / "checksums.sha256"
    checksum_file.write_text(
        checksum_file.read_text(encoding="utf-8") + f"{'f' * 64}  ../outside.bin\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_checksum_manifest_cannot_expand_scope_to_undeclared_files(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    undeclared = tmp_path / "private" / "undeclared.bin"
    _write(undeclared, b"not part of the SessionManifest")
    checksum_file = tmp_path / "integrity" / "checksums.sha256"
    checksum_file.write_text(
        checksum_file.read_text(encoding="utf-8")
        + f"{_sha256(undeclared.read_bytes())}  private/undeclared.bin\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["undeclared_checksum_paths"] == ["private/undeclared.bin"]


@pytest.mark.parametrize(
    ("payload", "expected_error_type"),
    [
        (b'{"key":1,"key":2}', "duplicate_key"),
        (b'{"value":NaN}', "nonstandard_constant"),
        (b'{"value":' + b"9" * 5000 + b"}", "ValueError"),
        (b"[" * 2000 + b"0" + b"]" * 2000, "RecursionError"),
    ],
)
def test_problematic_json_always_returns_typed_manifest_error(
    tmp_path: Path, payload: bytes, expected_error_type: str
) -> None:
    (tmp_path / "manifest.json").write_bytes(payload)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["json_error_type"] == expected_error_type


def test_manifest_and_checksum_reads_have_configurable_byte_limits(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    small_manifest_limit = ManifestLoaderLimits(max_manifest_bytes=32)
    with pytest.raises(ManifestLoadError) as manifest_error:
        ManifestLoader(small_manifest_limit).load(tmp_path)
    assert manifest_error.value.error.diagnostics["limit_name"] == "max_manifest_bytes"

    checksum_size = (tmp_path / "integrity" / "checksums.sha256").stat().st_size
    small_checksum_limit = ManifestLoaderLimits(max_checksum_bytes=checksum_size - 1)
    with pytest.raises(ManifestLoadError) as checksum_error:
        ManifestLoader(small_checksum_limit).load(tmp_path)
    assert checksum_error.value.error.diagnostics["limit_name"] == "max_checksum_bytes"


def test_hash_budget_is_enforced_before_unbounded_io(tmp_path: Path) -> None:
    _build_valid_bundle(tmp_path)
    limits = ManifestLoaderLimits(max_single_file_bytes=8, max_total_hash_bytes=16)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader(limits).load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["limit_name"] == "max_single_file_bytes"


def test_shared_xu_artifact_is_verified_once_and_counts_logical_views(
    tmp_path: Path,
) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)

    loaded = ManifestLoader().load(tmp_path)

    assert loaded.declared_reference_count == 6
    assert loaded.unique_artifact_count == 5
    assert loaded.verified_paths.count("streams/simulator.csv") == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format", "parquet"),
        ("schema_id", "other-combined-schema-v0.1"),
        ("shared_source_id", "other-source"),
        ("view_id", "X"),
    ],
)
def test_shared_xu_requires_identical_physical_identity_and_distinct_views(
    tmp_path: Path, field: str, value: str
) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    if field in {"shared_source_id", "view_id"}:
        manifest["streams"]["U"]["metadata"][field] = value
    else:
        manifest["streams"]["U"][field] = value
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["duplicate_paths"]


def test_shared_xu_requires_identical_descriptor_digest(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    manifest["streams"]["U"]["checksums"]["streams/simulator.csv"] = "f" * 64
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_shared_xu_requires_both_logical_views_to_be_present(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    manifest["streams"]["X"].update(
        status="invalid",
        clock_sync=None,
        quality_summary=None,
    )
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["duplicate_paths"]


def test_shared_xu_rejects_case_only_path_alias(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    digest = manifest["streams"]["U"]["checksums"].pop("streams/simulator.csv")
    manifest["streams"]["U"]["paths"] = ["STREAMS/simulator.csv"]
    manifest["streams"]["U"]["checksums"] = {"STREAMS/simulator.csv": digest}
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_only_x_and_u_may_share_a_stream_artifact(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    manifest["streams"]["THERMAL"] = copy.deepcopy(manifest["streams"]["X"])
    manifest["streams"]["THERMAL"].update(
        modality="THERMAL",
        metadata={
            **manifest["streams"]["X"]["metadata"],
            "view_id": "THERMAL",
        },
    )
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_stream_artifact_cannot_share_an_annotation_role(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _configure_shared_xu(tmp_path, manifest)
    manifest["annotations"]["phases"] = "streams/simulator.csv"
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"


def test_invalid_stream_artifacts_still_cross_integrity_gate(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    manifest["streams"]["X"].update(
        status="invalid",
        clock_sync=None,
        quality_summary=None,
    )
    _write_manifest(tmp_path, manifest)

    loaded = ManifestLoader().load(tmp_path)
    assert "streams/flight_state.parquet" in loaded.verified_paths

    (tmp_path / "streams" / "flight_state.parquet").write_bytes(b"tampered")
    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)
    assert caught.value.error.error_code == "CHECKSUM_MISMATCH"


def test_bundle_task_reference_is_verified_as_reference_artifact(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    _add_bundle_task_reference(tmp_path, manifest)

    loaded = ManifestLoader().load(tmp_path)

    assert "references/commanded_path.parquet" in loaded.verified_paths
    assert loaded.declared_reference_count == 7
    assert loaded.unique_artifact_count == 7


def test_case_insensitive_duplicate_declared_paths_are_rejected(tmp_path: Path) -> None:
    manifest = _build_valid_bundle(tmp_path)
    manifest["streams"]["THERMAL"] = copy.deepcopy(manifest["streams"]["X"])
    manifest["streams"]["THERMAL"]["modality"] = "THERMAL"
    manifest["streams"]["THERMAL"]["paths"] = ["STREAMS/flight_state.parquet"]
    manifest["streams"]["THERMAL"]["checksums"] = {
        "STREAMS/flight_state.parquet": manifest["streams"]["X"]["checksums"][
            "streams/flight_state.parquet"
        ]
    }
    _write_manifest(tmp_path, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(tmp_path)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert caught.value.error.diagnostics["duplicate_paths"]


def test_symlink_escape_is_rejected_when_platform_allows_symlinks(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    manifest = _build_valid_bundle(bundle_root)
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    outside = outside_directory / "thermal.bin"
    outside.write_bytes(b"sensitive outside content")
    link = bundle_root / "streams" / "external"
    try:
        link.symlink_to(outside_directory, target_is_directory=True)
    except OSError as error:
        if os.name != "nt":
            pytest.skip(f"symlink creation unavailable: {error}")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside_directory)],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip(f"symlink and junction creation unavailable: {junction.stderr}")

    digest = _sha256(outside.read_bytes())
    manifest["streams"]["THERMAL"] = copy.deepcopy(manifest["streams"]["X"])
    manifest["streams"]["THERMAL"].update(
        {
            "modality": "THERMAL",
            "paths": ["streams/external/thermal.bin"],
            "checksums": {"streams/external/thermal.bin": digest},
        }
    )
    checksum_file = bundle_root / "integrity" / "checksums.sha256"
    checksum_file.write_text(
        checksum_file.read_text(encoding="utf-8") + f"{digest}  streams/external/thermal.bin\n",
        encoding="utf-8",
    )
    _write_manifest(bundle_root, manifest)

    with pytest.raises(ManifestLoadError) as caught:
        ManifestLoader().load(bundle_root)

    assert caught.value.error.error_code == "INVALID_MANIFEST"
    assert "bundle root" in caught.value.error.message
