"""Deterministic real-X/U plus synthetic-multimodal Session Bundle generator."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import JsonValue

from pilot_assessment.contracts.session import (
    ClockSync,
    QualitySummary,
    SessionManifest,
    StreamDescriptor,
)
from pilot_assessment.ingestion.adapters.base import AdapterRequest, AdapterResult
from pilot_assessment.ingestion.adapters.profiled_csv import ProfiledCsvAdapter
from pilot_assessment.ingestion.manifest_loader import ManifestLoader, ManifestLoaderLimits
from pilot_assessment.ingestion.parquet_io import write_profiled_parquet
from pilot_assessment.ingestion.profiles import CompositeProfile, CsvProfile, load_builtin_profiles
from pilot_assessment.synthetic.modalities import (
    build_annotations,
    build_ecg,
    build_eeg,
    build_gaze,
    build_pilot_camera,
    build_scene,
    build_task_reference,
    write_rgb8_png,
)
from pilot_assessment.synthetic.timelines import source_grid

GENERATOR_ID: Final = "synthetic-multimodal-generator-v0.1"
DEFAULT_SEED: Final = 20260711
DEFAULT_CREATED_AT: Final = "2000-01-01T00:00:00Z"
_CSV_SCHEMA_ID: Final = "cranfield-simulator-combined-csv-raw-v0.1"
_CHECKSUM_PATH: Final = "integrity/checksums.sha256"
_GENERATOR_PARAMETERS: Final[dict[str, JsonValue]] = {
    "scene_rate_hz": 30.0,
    "scene_width": 64,
    "scene_height": 36,
    "gaze_rate_hz": 120.0,
    "eeg_rate_hz": 256.0,
    "ecg_rate_hz": 250.0,
    "pilot_camera_rate_hz": 15.0,
    "pilot_camera_width": 48,
    "pilot_camera_height": 48,
    "duration_mode": "source",
    "control_activity_definition": "min(1,abs(control.longitudinal_raw)/100)",
    "physiology_activity_resampling": "linear-clamped-v0.1",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as payload:
        for chunk in iter(lambda: payload.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_canonical_json(path: Path, payload: object) -> None:
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    if path.exists():
        raise FileExistsError(path)
    path.write_bytes(_canonical_json_bytes(payload))


def _validate_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**63 - 1:
        raise ValueError("seed must be an integer in 0..2^63-1")


def _validate_created_at(created_at: str) -> None:
    if not isinstance(created_at, str):
        raise ValueError("created_at must be an RFC 3339 string with timezone")
    normalized = created_at[:-1] + "+00:00" if created_at.endswith("Z") else created_at
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("created_at must be an RFC 3339 string with timezone") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created_at must be an RFC 3339 string with timezone")


def _clock_sync(*, offset_ns: int, drift_ppm: float) -> ClockSync:
    return ClockSync(
        method="synthetic-declared-truth-v0.1",
        scale=1.0 + drift_ppm * 1e-6,
        offset_ns=offset_ns,
        drift_ppm=drift_ppm,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
    )


def _quality_summary() -> QualitySummary:
    return QualitySummary(
        coverage_ratio=1.0,
        gap_count=0,
        validity_ratio=1.0,
        artifact_ratio=0.0,
    )


def _csv_descriptor(
    modality: Literal["X", "U"],
    *,
    relative_path: str,
    digest: str,
) -> StreamDescriptor:
    return StreamDescriptor(
        modality=modality,
        status="present",
        required_for_import=True,
        paths=[relative_path],
        format="csv",
        schema_id=_CSV_SCHEMA_ID,
        clock_id="sim_clock",
        clock_sync=_clock_sync(offset_ns=0, drift_ppm=0.0),
        sample_rate_hz=100.0,
        units="profile-defined-engineering-units",
        quality_summary=_quality_summary(),
        checksums={relative_path: digest},
        metadata={
            "adapter_profile_id": _CSV_SCHEMA_ID,
            "shared_source_id": "simulator-main",
            "view_id": modality,
        },
    )


def _inspect_source_csv(source: Path, payload: bytes, digest: str) -> AdapterResult:
    profiles = load_builtin_profiles()
    profile = profiles[_CSV_SCHEMA_ID]
    if not isinstance(profile, CsvProfile):
        raise RuntimeError("packaged simulator profile is not a CsvProfile")
    relative_path = source.name
    descriptors = {
        modality: _csv_descriptor(
            modality,
            relative_path=relative_path,
            digest=digest,
        )
        for modality in ("X", "U")
    }
    result = ProfiledCsvAdapter().inspect(
        AdapterRequest(
            bundle_root=source.parent,
            descriptors=descriptors,
            source_paths=(relative_path,),
            verified_digests={relative_path: digest},
            profile=profile,
        )
    )
    if source.read_bytes() != payload:
        raise RuntimeError("source CSV changed during synthetic generation preflight")
    return result


def _lock_fingerprint() -> str:
    repository_root = Path(__file__).resolve().parents[3]
    lockfile = repository_root / "uv.lock"
    if lockfile.is_file():
        return _sha256_file(lockfile)

    installed: list[str] = []
    for distribution in ("pilot-assessment-system", "Pillow", "polars", "pydantic"):
        try:
            installed.append(f"{distribution}=={version(distribution)}")
        except PackageNotFoundError:
            installed.append(f"{distribution}==not-installed")
    return _sha256_bytes(("\n".join(installed) + "\n").encode("utf-8"))


def _stable_session_id(source_digest: str, seed: int) -> str:
    identity = f"{source_digest}\0{GENERATOR_ID}\0{seed}".encode("ascii")
    return f"synthetic-{_sha256_bytes(identity)[:32]}"


def _declared_path_count(duration_s: float) -> int:
    scene_images = len(source_grid(duration_s=duration_s, sample_rate_hz=30.0))
    camera_images = len(source_grid(duration_s=duration_s, sample_rate_hz=15.0))
    # 16 non-image references: X/U (shared physical CSV counted twice), ten
    # other stream artifacts, three annotations, and the checksum manifest.
    return scene_images + camera_images + 16


def _prepare_output(output: Path, source: Path) -> Path:
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(f"output path already exists and is not a directory: {output}")
        if any(output.iterdir()):
            raise FileExistsError(f"output directory is not empty: {output}")
    else:
        output.mkdir(parents=True)
    resolved = output.resolve(strict=True)
    if source.is_relative_to(resolved):
        raise ValueError("source CSV must remain outside the generated bundle directory")
    return resolved


def _make_directories(root: Path) -> None:
    for relative in (
        "streams/vr_scene/frames",
        "streams/gaze",
        "streams/eeg",
        "streams/ecg",
        "streams/pilot_camera/frames",
        "references",
        "annotations",
        "integrity",
    ):
        root.joinpath(*relative.split("/")).mkdir(parents=True)


def _write_images(root: Path, paths: Sequence[str], *, seed: int, modality: str) -> None:
    dimensions = (64, 36) if modality == "I" else (48, 48)
    for index, relative_path in enumerate(paths):
        write_rgb8_png(
            root.joinpath(*relative_path.split("/")),
            width=dimensions[0],
            height=dimensions[1],
            seed=seed,
            modality=modality,
            index=index,
        )


def _composite_roles(schema_id: str) -> dict[str, JsonValue]:
    profile = load_builtin_profiles()[schema_id]
    if not isinstance(profile, CompositeProfile):
        raise RuntimeError(f"packaged profile {schema_id} is not composite")
    return {
        role: cast(JsonValue, definition.model_dump(mode="json"))
        for role, definition in profile.artifact_roles.items()
    }


def _descriptor(
    *,
    modality: str,
    paths: Sequence[str],
    format: str,
    schema_id: str,
    clock_id: str,
    offset_ns: int,
    drift_ppm: float,
    sample_rate_hz: float,
    units: str | dict[str, str],
    digests: Mapping[str, str],
    metadata: dict[str, JsonValue],
    required_for_import: bool = False,
) -> StreamDescriptor:
    ordered_paths = list(paths)
    return StreamDescriptor(
        modality=modality,
        status="present",
        required_for_import=required_for_import,
        paths=ordered_paths,
        format=format,
        schema_id=schema_id,
        clock_id=clock_id,
        clock_sync=_clock_sync(offset_ns=offset_ns, drift_ppm=drift_ppm),
        sample_rate_hz=sample_rate_hz,
        units=units,
        quality_summary=_quality_summary(),
        checksums={path: digests[path] for path in ordered_paths},
        metadata=metadata,
    )


def _write_checksum_manifest(root: Path, digests: Mapping[str, str]) -> None:
    destination = root / "integrity" / "checksums.sha256"
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(
        "".join(f"{digests[path]}  {path}\n" for path in sorted(digests)),
        encoding="utf-8",
        newline="\n",
    )


def _build_manifest(
    *,
    source_digest: str,
    seed: int,
    created_at: str,
    duration_s: float,
    digests: Mapping[str, str],
    scene_paths: Sequence[str],
    camera_paths: Sequence[str],
) -> SessionManifest:
    simulator_path = "streams/simulator.csv"
    streams: dict[str, StreamDescriptor] = {
        "X": _csv_descriptor("X", relative_path=simulator_path, digest=digests[simulator_path]),
        "U": _csv_descriptor("U", relative_path=simulator_path, digest=digests[simulator_path]),
        "I": _descriptor(
            modality="I",
            paths=scene_paths,
            format="image_sequence+parquet_index",
            schema_id="vr-scene-source-bundle-v0.1",
            clock_id="vr_scene_clock",
            offset_ns=4_000_000,
            drift_ppm=0.0,
            sample_rate_hz=30.0,
            units="pixels-metres-quaternion-degrees",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles("vr-scene-source-bundle-v0.1"),
                "generator_id": GENERATOR_ID,
                "seed": seed,
            },
        ),
        "G": _descriptor(
            modality="G",
            paths=(
                "streams/gaze/gaze_samples.parquet",
                "streams/gaze/fixations.parquet",
            ),
            format="parquet",
            schema_id="gaze-source-bundle-v0.1",
            clock_id="gaze_clock",
            offset_ns=7_000_000,
            drift_ppm=20.0,
            sample_rate_hz=120.0,
            units="normalized-viewport-metres-millimetres",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles("gaze-source-bundle-v0.1"),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "scene_binding": "I.frame_id",
            },
        ),
        "EEG": _descriptor(
            modality="EEG",
            paths=(
                "streams/eeg/eeg_samples.parquet",
                "streams/eeg/eeg_sidecar.json",
            ),
            format="parquet+json_sidecar",
            schema_id="eeg-source-bundle-v0.1",
            clock_id="eeg_clock",
            offset_ns=-12_000_000,
            drift_ppm=-15.0,
            sample_rate_hz=256.0,
            units="microvolt",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles("eeg-source-bundle-v0.1"),
                "generator_id": GENERATOR_ID,
                "seed": seed,
            },
        ),
        "ECG": _descriptor(
            modality="ECG",
            paths=(
                "streams/ecg/ecg_samples.parquet",
                "streams/ecg/r_peaks.parquet",
            ),
            format="parquet",
            schema_id="ecg-source-bundle-v0.1",
            clock_id="ecg_clock",
            offset_ns=9_000_000,
            drift_ppm=10.0,
            sample_rate_hz=250.0,
            units="millivolt",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles("ecg-source-bundle-v0.1"),
                "generator_id": GENERATOR_ID,
                "seed": seed,
            },
        ),
        "pilot_camera": _descriptor(
            modality="pilot_camera",
            paths=camera_paths,
            format="image_sequence+parquet_index",
            schema_id="pilot-camera-source-bundle-v0.1",
            clock_id="pilot_camera_clock",
            offset_ns=15_000_000,
            drift_ppm=0.0,
            sample_rate_hz=15.0,
            units="pixels-normalized-bbox",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles("pilot-camera-source-bundle-v0.1"),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "privacy_class": "synthetic-no-identity",
            },
        ),
        "task_reference": _descriptor(
            modality="task_reference",
            paths=("references/commanded_path.parquet",),
            format="parquet",
            schema_id="task-reference-path-raw-v0.1",
            clock_id="sim_clock",
            offset_ns=0,
            drift_ppm=0.0,
            sample_rate_hz=100.0,
            units="profile-defined-reference-units",
            digests=digests,
            metadata={
                "adapter_profile_id": "task-reference-path-raw-v0.1",
                "generator_id": GENERATOR_ID,
                "seed": seed,
            },
            required_for_import=True,
        ),
    }
    return SessionManifest.model_validate(
        {
            "bundle_schema_version": "0.1.0",
            "session_id": _stable_session_id(source_digest, seed),
            "created_at": created_at,
            "source_session": {
                "system": GENERATOR_ID,
                "source_id": f"source-{source_digest[:24]}",
                "campaign": "synthetic-multimodal-software-test",
                "extensions": {
                    "source_xu_sha256": source_digest,
                    "source_artifact_role": "real-simulator-xu",
                },
            },
            "participant": {
                "pseudonymous_id": "synthetic-pilot",
                "research_attributes": {"synthetic_identity": True},
            },
            "task": {
                "task_profile_id": "synthetic-hover-deceleration-v0.1",
                "scenario_id": "synthetic-longitudinal-01",
                "expected_phases": [
                    "translation",
                    "deceleration",
                    "hover_stabilization",
                ],
                "reference": {
                    "source": "bundle",
                    "reference_id": "commanded-path-v0.1",
                    "stream_id": "task_reference",
                },
            },
            "session_timebase": {
                "origin": "session_start",
                "unit": "ns",
                "master_clock_id": "sim_clock",
            },
            "streams": streams,
            "annotations": {
                "revision": "synthetic-unvalidated-v0.1",
                "phases": "annotations/phases.json",
                "events": "annotations/events.json",
                "baseline_intervals": "annotations/baseline_intervals.json",
            },
            "integrity": {
                "algorithm": "sha256",
                "manifest_canonicalization": "sorted-compact-json-lf-v0.1",
                "checksum_file": _CHECKSUM_PATH,
            },
            "privacy": {
                "classification": "synthetic-test-data",
                "direct_identifiers_removed": True,
                "contains_biometric_data": False,
                "biometric_modalities_export_pending": [],
                "permitted_use": "software-testing-only",
            },
            "extensions": {
                "synthetic": {
                    "generator_id": GENERATOR_ID,
                    "scientific_validation_status": "not_supported",
                    "seed": seed,
                    "source_xu_sha256": source_digest,
                    "lock_fingerprint": _lock_fingerprint(),
                    "duration_s": duration_s,
                    "parameters": _GENERATOR_PARAMETERS,
                    "provenance_scope": "real-xu-plus-synthetic-modalities",
                    "formal_assessment_supported": False,
                }
            },
        }
    )


def generate_synthetic_bundle(
    xu_csv: str | Path,
    output: str | Path,
    *,
    seed: int = DEFAULT_SEED,
    duration_mode: Literal["source"] = "source",
    created_at: str = DEFAULT_CREATED_AT,
) -> Path:
    """Generate and M1-validate one deterministic software-test Session Bundle."""

    _validate_seed(seed)
    _validate_created_at(created_at)
    if duration_mode != "source":
        raise ValueError("duration_mode must be 'source'")

    source = Path(xu_csv).resolve(strict=True)
    if not source.is_file():
        raise ValueError("xu_csv must identify a regular file")
    source_payload = source.read_bytes()
    source_digest = _sha256_bytes(source_payload)
    inspected = _inspect_source_csv(source, source_payload, source_digest)
    x_table = inspected.streams["X"].primary_table
    u_table = inspected.streams["U"].primary_table
    source_times = tuple(float(value) for value in x_table["source_time_s"].to_list())
    source_x = tuple(float(value) for value in x_table["position.earth.x_m"].to_list())
    controls = tuple(float(value) for value in u_table["control.longitudinal_raw"].to_list())
    duration_s = source_times[-1]
    if duration_s <= 0.0:
        raise ValueError("source CSV duration must be positive")
    control_activity = tuple(min(1.0, abs(value) / 100.0) for value in controls)

    path_count = _declared_path_count(duration_s)
    max_declared_paths = ManifestLoaderLimits().max_declared_paths
    if path_count > max_declared_paths:
        raise ValueError(
            "generated bundle would exceed the M1 declared path budget "
            f"({path_count} > {max_declared_paths})"
        )

    root = _prepare_output(Path(output), source)
    _make_directories(root)
    simulator_destination = root / "streams" / "simulator.csv"
    simulator_destination.write_bytes(source_payload)
    if simulator_destination.read_bytes() != source_payload:
        raise OSError("byte-for-byte simulator CSV copy verification failed")

    scene = build_scene(duration_s=duration_s, seed=seed)
    gaze = build_gaze(duration_s=duration_s, seed=seed, scene=scene)
    eeg = build_eeg(
        duration_s=duration_s,
        seed=seed,
        control_source_times_s=source_times,
        control_activity=control_activity,
    )
    ecg = build_ecg(
        duration_s=duration_s,
        seed=seed,
        control_source_times_s=source_times,
        control_activity=control_activity,
    )
    pilot_camera = build_pilot_camera(duration_s=duration_s, seed=seed)
    task_reference = build_task_reference(
        source_times_s=source_times,
        source_x_m=source_x,
    )
    annotations = build_annotations(duration_s=duration_s, seed=seed)

    write_profiled_parquet(
        scene.frame_index,
        root / "streams" / "vr_scene" / "frame_index.parquet",
        schema_id="vr-frame-index-raw-v0.1",
    )
    write_profiled_parquet(
        scene.aoi_instances,
        root / "streams" / "vr_scene" / "aoi_instances.parquet",
        schema_id="vr-aoi-instance-raw-v0.1",
    )
    scene_images = tuple(cast(list[str], scene.frame_index["image_path"].to_list()))
    _write_images(root, scene_images, seed=seed, modality="I")

    write_profiled_parquet(
        gaze.samples,
        root / "streams" / "gaze" / "gaze_samples.parquet",
        schema_id="gaze-sample-raw-v0.1",
    )
    write_profiled_parquet(
        gaze.fixations,
        root / "streams" / "gaze" / "fixations.parquet",
        schema_id="gaze-fixation-raw-v0.1",
    )
    write_profiled_parquet(
        eeg.samples,
        root / "streams" / "eeg" / "eeg_samples.parquet",
        schema_id="eeg-sample-raw-v0.1",
    )
    _write_canonical_json(root / "streams" / "eeg" / "eeg_sidecar.json", eeg.sidecar)
    write_profiled_parquet(
        ecg.samples,
        root / "streams" / "ecg" / "ecg_samples.parquet",
        schema_id="ecg-sample-raw-v0.1",
    )
    write_profiled_parquet(
        ecg.r_peaks,
        root / "streams" / "ecg" / "r_peaks.parquet",
        schema_id="ecg-r-peak-raw-v0.1",
    )
    write_profiled_parquet(
        pilot_camera,
        root / "streams" / "pilot_camera" / "frame_index.parquet",
        schema_id="pilot-camera-frame-index-raw-v0.1",
    )
    camera_images = tuple(cast(list[str], pilot_camera["image_path"].to_list()))
    _write_images(root, camera_images, seed=seed, modality="pilot_camera")
    write_profiled_parquet(
        task_reference,
        root / "references" / "commanded_path.parquet",
        schema_id="task-reference-path-raw-v0.1",
    )

    for annotation_name in ("phases", "events", "baseline_intervals"):
        _write_canonical_json(
            root / "annotations" / f"{annotation_name}.json",
            annotations[annotation_name],
        )

    relative_paths = (
        "streams/simulator.csv",
        "streams/vr_scene/frame_index.parquet",
        "streams/vr_scene/aoi_instances.parquet",
        *scene_images,
        "streams/gaze/gaze_samples.parquet",
        "streams/gaze/fixations.parquet",
        "streams/eeg/eeg_samples.parquet",
        "streams/eeg/eeg_sidecar.json",
        "streams/ecg/ecg_samples.parquet",
        "streams/ecg/r_peaks.parquet",
        "streams/pilot_camera/frame_index.parquet",
        *camera_images,
        "references/commanded_path.parquet",
        "annotations/phases.json",
        "annotations/events.json",
        "annotations/baseline_intervals.json",
    )
    digests = {
        relative_path: _sha256_file(root.joinpath(*relative_path.split("/")))
        for relative_path in relative_paths
    }
    _write_checksum_manifest(root, digests)

    scene_descriptor_paths = (
        "streams/vr_scene/frame_index.parquet",
        "streams/vr_scene/aoi_instances.parquet",
        *scene_images,
    )
    camera_descriptor_paths = (
        "streams/pilot_camera/frame_index.parquet",
        *camera_images,
    )
    manifest = _build_manifest(
        source_digest=source_digest,
        seed=seed,
        created_at=created_at,
        duration_s=duration_s,
        digests=digests,
        scene_paths=scene_descriptor_paths,
        camera_paths=camera_descriptor_paths,
    )
    _write_canonical_json(
        root / "manifest.json",
        manifest.model_dump(mode="json"),
    )

    loaded = ManifestLoader().load(root)
    if loaded.manifest != manifest:
        raise RuntimeError("M1 self-validation did not reproduce the generated manifest")
    from pilot_assessment.ingestion import readiness as readiness_module

    readiness = readiness_module.inspect_ingestion_readiness(root)
    if (
        readiness.report.disposition.value != "ready"
        or readiness.prepared_session is None
        or readiness.report.formal_run_authorized
    ):
        raise RuntimeError("M2 self-validation did not produce a ready software-test bundle")
    if source.read_bytes() != source_payload:
        raise RuntimeError("source CSV changed during synthetic bundle generation")
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pilot_assessment.synthetic",
        description="Generate a deterministic multimodal software-test Session Bundle.",
    )
    parser.add_argument("--xu-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--duration-mode", choices=("source",), default="source")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the module CLI and return a process exit status."""

    arguments = _parser().parse_args(argv)
    output = generate_synthetic_bundle(
        arguments.xu_csv,
        arguments.output,
        seed=arguments.seed,
        duration_mode=arguments.duration_mode,
        created_at=arguments.created_at,
    )
    print(output)
    return 0


__all__ = [
    "DEFAULT_CREATED_AT",
    "DEFAULT_SEED",
    "GENERATOR_ID",
    "generate_synthetic_bundle",
    "main",
]
