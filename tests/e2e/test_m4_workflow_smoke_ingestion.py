from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "m4"
RECIPE_PATH = FIXTURE_ROOT / "m4-workflow-smoke-recipe-v0.1.json"
BUILDER_PATH = REPOSITORY_ROOT / "tests" / "m4_support" / "fixture_builder.py"
SOURCE_HASHES_PATH = FIXTURE_ROOT / "m4-workflow-smoke-source-hashes-v0.1.json"


def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"lightweight M4 module is not implemented: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_workflow_bundle_runs_public_m1_m2_m3_and_matches_frozen_source_hashes(
    m4_workflow_bundle: Path,
) -> None:
    from pilot_assessment.ingestion import (
        ManifestLoader,
        inspect_loaded_ingestion_readiness,
    )
    from pilot_assessment.synchronization import (
        SynchronizationInput,
        synchronize_session,
    )

    builder = _load_module(BUILDER_PATH, "m4_lightweight_fixture_builder_e2e")
    assert str(inspect.signature(builder.build_fixture)) == (
        "(recipe_path: 'Path', case_id: 'str', output_root: 'Path') -> 'Path'"
    )
    assert str(inspect.signature(builder.source_hash_manifest)) == (
        "(bundle_root: 'Path') -> 'dict[str, str]'"
    )
    assert str(inspect.signature(builder.validate_input_recipe)) == (
        "(recipe: 'Mapping[str, object]') -> 'None'"
    )
    recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    legitimate_config = copy.deepcopy(recipe)
    legitimate_config["configuration_probe"] = {
        "expected_phases": ["Translation", "Deceleration", "Hover"],
        "phase_state": "configured",
        "O1": {"threshold_profile_id": "probe-only-v0.1"},
    }
    builder.validate_input_recipe(legitimate_config)
    expected_hashes = json.loads(SOURCE_HASHES_PATH.read_text(encoding="utf-8"))
    assert builder.source_hash_manifest(m4_workflow_bundle) == expected_hashes
    assert expected_hashes == {
        path: _sha256(m4_workflow_bundle / path) for path in sorted(expected_hashes)
    }

    loaded = ManifestLoader().load(m4_workflow_bundle)
    assert loaded.declared_reference_count == 468
    assert loaded.unique_artifact_count == 467
    assert len(loaded.verified_paths) == 466
    assert set(expected_hashes) == set(loaded.verified_paths)
    m2 = inspect_loaded_ingestion_readiness(loaded)
    assert m2.prepared_session is not None
    assert m2.report.disposition.value == "ready"
    assert m2.report.formal_run_authorized is False
    assert m2.report.synthetic_provenance is not None
    assert m2.report.synthetic_provenance.scientific_validation_status == "not_supported"

    prepared = m2.prepared_session
    actual_rows = {
        "xu_shared": prepared.streams["X"].tables["samples"].height,
        "task_reference": prepared.task_reference.tables["commanded_path"].height,
        "vr_frame_index": prepared.streams["I"].tables["frame_index"].height,
        "vr_aoi_instances": prepared.streams["I"].tables["aoi_instances"].height,
        "gaze_samples": prepared.streams["G"].tables["gaze_samples"].height,
        "compatibility_fixation": prepared.streams["G"].tables["fixations"].height,
        "eeg_samples": prepared.streams["EEG"].tables["samples"].height,
        "ecg_samples": prepared.streams["ECG"].tables["samples"].height,
        "r_peaks": prepared.streams["ECG"].tables["r_peaks"].height,
        "pilot_camera_index": prepared.streams["pilot_camera"].tables["frame_index"].height,
    }
    assert prepared.streams["U"].tables["samples"].height == actual_rows["xu_shared"]
    assert actual_rows == {
        "xu_shared": 1001,
        "task_reference": 1001,
        "vr_frame_index": 301,
        "vr_aoi_instances": 602,
        "gaze_samples": 1201,
        "compatibility_fixation": 1,
        "eeg_samples": 2561,
        "ecg_samples": 2501,
        "r_peaks": 11,
        "pilot_camera_index": 151,
    }
    assert sum(actual_rows.values()) == 9331
    assert prepared.streams["X"].tables["samples"]["position.earth.x_m"].to_list() != (
        prepared.task_reference.tables["commanded_path"]["target_x_m"].to_list()
    )
    x_samples = prepared.streams["X"].tables["samples"]
    reference = prepared.task_reference.tables["commanded_path"]
    metres_per_foot = recipe["semantic_bindings"]["metres_per_foot"]
    peak_excursion_ft = max(
        math.dist(actual, commanded) / metres_per_foot
        for actual, commanded in zip(
            x_samples.select(
                "position.earth.x_m",
                "position.earth.y_m",
                "position.earth.z_m",
            ).iter_rows(),
            reference.select("target_x_m", "target_y_m", "target_z_m").iter_rows(),
            strict=True,
        )
    )
    assert math.isclose(peak_excursion_ft, 3.0, rel_tol=0.0, abs_tol=1e-9)

    vr_recipe = recipe["streams"]["vr_scene"]
    scene_recipe = recipe["gaze"]["scene"]
    frame_index = prepared.streams["I"].tables["frame_index"]
    assert frame_index["width"].unique().to_list() == [vr_recipe["image_width"]]
    assert frame_index["height"].unique().to_list() == [vr_recipe["image_height"]]
    assert frame_index["frame_valid"].unique().to_list() == [scene_recipe["frame_valid"]]
    aoi_instances = prepared.streams["I"].tables["aoi_instances"]
    expected_geometry = {item["role"]: item for item in recipe["gaze"]["aoi_geometry"]}
    assert set(aoi_instances["aoi_id"].unique()) == set(expected_geometry)
    for role, geometry in expected_geometry.items():
        rows = aoi_instances.filter(aoi_instances["aoi_id"] == role)
        assert rows.height == frame_index.height
        assert rows["taxonomy_version"].unique().to_list() == [recipe["gaze"]["aoi_taxonomy_id"]]
        actual_bbox = rows.select("bbox_x_norm", "bbox_y_norm", "bbox_w_norm", "bbox_h_norm").row(0)
        assert all(
            math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-7)
            for actual, expected in zip(actual_bbox, geometry["bbox_norm"], strict=True)
        )

    from PIL import Image

    modality_recipe = {
        "I": recipe["streams"]["vr_scene"],
        "pilot_camera": recipe["streams"]["pilot_camera"],
    }
    for modality, stream_recipe in modality_recipe.items():
        image_path = next(
            path for path in loaded.manifest.streams[modality].paths if path.endswith(".png")
        )
        with Image.open(m4_workflow_bundle / image_path) as image:
            image.load()
            assert image.mode == {"RGB8": "RGB"}[stream_recipe["image_mode"]]
            assert image.size == (
                stream_recipe["image_width"],
                stream_recipe["image_height"],
            )
    camera_recipe = recipe["streams"]["pilot_camera"]
    camera_descriptor = loaded.manifest.streams["pilot_camera"]
    assert camera_descriptor.metadata["privacy_class"] == camera_recipe["privacy_class"]
    assert camera_descriptor.metadata["generator_id"] == "m4-lightweight-workflow-builder-v1"
    camera_index = prepared.streams["pilot_camera"].tables["frame_index"]
    assert camera_index["width"].unique().to_list() == [camera_recipe["image_width"]]
    assert camera_index["height"].unique().to_list() == [camera_recipe["image_height"]]
    assert camera_index["frame_valid"].unique().to_list() == [camera_recipe["frame_valid"]]
    assert camera_index["privacy_class"].unique().to_list() == [camera_recipe["privacy_class"]]

    m3 = synchronize_session(
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=m2.report,
            prepared_session=m2.prepared_session,
        )
    )
    assert m3.aligned_session is not None
    assert m3.report.disposition.value == "ready"
    assert m3.report.can_continue_to_anchor_availability is True
    assert m3.report.formal_run_authorized is False
    assert m3.report.session_window.start_t_ns == 0
    assert m3.report.session_window.end_t_ns == 10_000_000_000
    assert m3.aligned_session.streams["pilot_camera"].tables["frame_index"][
        "privacy_class"
    ].unique().to_list() == [camera_recipe["privacy_class"]]
    assert builder.source_hash_manifest(m4_workflow_bundle) == expected_hashes


def test_dense_assets_are_temporary_and_untracked(m4_workflow_bundle: Path) -> None:
    resolved_bundle = m4_workflow_bundle.resolve()
    assert not resolved_bundle.is_relative_to((REPOSITORY_ROOT / "tests" / "fixtures").resolve())
    assert len(list(resolved_bundle.rglob("*.png"))) == 452
    tracked = subprocess.run(
        ["git", "ls-files", "tests/fixtures/m4"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    dense_suffixes = {".csv", ".parquet", ".png"}
    assert not [path for path in tracked if Path(path).suffix.lower() in dense_suffixes]
    repository_dense = [
        path
        for path in (REPOSITORY_ROOT / "tests" / "fixtures" / "m4").rglob("*")
        if path.is_file() and path.suffix.lower() in dense_suffixes
    ]
    assert not repository_dense
    cli = subprocess.run(
        [sys.executable, "-m", "tests.m4_support.fixture_builder", "--help"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0, cli.stderr
    assert all(option in cli.stdout for option in ("--recipe", "--case-id", "--output-root"))
