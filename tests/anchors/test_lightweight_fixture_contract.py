from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "m4"
RECIPE_PATH = FIXTURE_ROOT / "m4-workflow-smoke-recipe-v0.1.json"
EXPECTED_PATH = FIXTURE_ROOT / "m4-workflow-smoke-expected-v0.1.json"
SOURCE_HASHES_PATH = FIXTURE_ROOT / "m4-workflow-smoke-source-hashes-v0.1.json"
BUILDER_PATH = REPOSITORY_ROOT / "tests" / "m4_support" / "fixture_builder.py"
ORACLE_PATH = REPOSITORY_ROOT / "tests" / "m4_support" / "oracle.py"
CANONICAL_ANCHOR_IDS = tuple(
    [f"O{index}" for index in range(1, 14)] + [f"H{index}" for index in range(1, 6)]
)


def _load_json(path: Path) -> object:
    assert path.is_file(), f"lightweight M4 resource is not implemented: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"lightweight M4 module is not implemented: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            targets.add(base)
            targets.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return targets


def test_lightweight_recipe_identity_rates_and_budget() -> None:
    recipe = _load_json(RECIPE_PATH)
    assert isinstance(recipe, dict)
    assert recipe["fixture_contract"] == "m4-workflow-smoke-fixture-v1"
    assert recipe["generator_id"] == "m4-lightweight-workflow-builder-v1"
    assert recipe["fixture_id"] == "m4-workflow-smoke-v0.1"
    assert recipe["seed"] == 20260713
    assert recipe["session"] == {
        "start_s": 0,
        "end_s": 10,
        "baseline": [0, 4],
        "phases": [
            {"name": "Translation", "span_s": [4, 6]},
            {"name": "Deceleration", "span_s": [6, 8]},
            {"name": "Hover", "span_s": [8, 10]},
        ],
    }
    expected_rates = {
        "xu": 100,
        "task_reference": 100,
        "vr_scene": 30,
        "gaze": 120,
        "eeg": 256,
        "ecg": 250,
        "pilot_camera": 15,
    }
    streams = recipe["streams"]
    assert isinstance(streams, dict)
    assert {name: streams[name]["rate_hz"] for name in expected_rates} == expected_rates
    assert streams["eeg"]["mains_frequency_hz"] == 50
    assert recipe["asset_budget"] == {
        "png_files": 452,
        "declared_path_references": 468,
        "unique_artifacts": 467,
        "verified_paths": 466,
        "physical_source_table_rows": 9331,
        "max_physical_source_table_rows": 9500,
    }


def test_recipe_rejects_answer_echo_shapes() -> None:
    import pytest

    builder = _load_module(BUILDER_PATH, "m4_lightweight_fixture_builder_contract")
    recipe = _load_json(RECIPE_PATH)
    assert isinstance(recipe, dict)
    builder.validate_input_recipe(recipe)

    prohibited_mutations = (
        {"production_output": {}},
        {"expected_anchor_results": {"O1": {"state": "Adequate"}}},
        {"q_control": 0.75},
        {"o8_composite": 0.4},
        {"o13_composite": 12.5},
        {"plugin_artifacts": {"O1": {"value": 75.0}}},
        {"anchor_result_map": {"O1": {"state": "Adequate"}}},
        {"anchor_value_map": {"O1": {"value": 75.0}, "H5": 35.0}},
        {
            "serialized_anchor_measurement": {
                "anchor_id": "H1",
                "measurement_status": "computed",
                "primary_value": 85.0,
                "unit": "percent",
            }
        },
        {
            "serialized_measurement": {
                "anchor_id": "O1",
                "primary_value": 75.0,
                "state": "Adequate",
                "likelihood": [0.1, 0.8, 0.1],
            }
        },
    )
    for mutation in prohibited_mutations:
        candidate = copy.deepcopy(recipe)
        candidate["answer_echo_probe"] = mutation
        with pytest.raises(ValueError, match="answer echo"):
            builder.validate_input_recipe(candidate)


def test_builder_and_oracle_are_independent_of_production_anchors() -> None:
    assert BUILDER_PATH.is_file(), f"lightweight M4 builder is not implemented: {BUILDER_PATH}"
    assert ORACLE_PATH.is_file(), f"lightweight M4 oracle is not implemented: {ORACLE_PATH}"
    builder_targets = _import_targets(BUILDER_PATH)
    oracle_targets = _import_targets(ORACLE_PATH)
    assert not any(target.startswith("pilot_assessment.anchors") for target in builder_targets)
    assert not any(target.startswith("pilot_assessment.anchors") for target in oracle_targets)
    assert "tests.m4_support.oracle" not in builder_targets
    assert "tests.m4_support.fixture_builder" not in oracle_targets
    builder_source = BUILDER_PATH.read_text(encoding="utf-8")
    oracle_source = ORACLE_PATH.read_text(encoding="utf-8")
    assert EXPECTED_PATH.name not in builder_source
    assert EXPECTED_PATH.name not in oracle_source
    assert "fixture_builder" not in oracle_source
    assert "build_fixture" not in oracle_source
    assert "source_hash_manifest" not in oracle_source
    assert "bundle_root" not in oracle_source
    for source in (builder_source, oracle_source):
        assert "__import__(" not in source
        assert "import_module(" not in source

    production_root = REPOSITORY_ROOT / "src" / "pilot_assessment"
    for source_path in production_root.rglob("*.py"):
        assert not any(
            target == "tests" or target.startswith("tests.")
            for target in _import_targets(source_path)
        ), f"production imports test-only code: {source_path}"


def test_expected_vector_is_separate_and_has_exactly_18_ids(monkeypatch) -> None:
    import builtins

    import rfc8785

    recipe = _load_json(RECIPE_PATH)
    expected = _load_json(EXPECTED_PATH)
    assert RECIPE_PATH != EXPECTED_PATH
    assert isinstance(recipe, dict)
    assert isinstance(expected, dict)
    anchors = expected["anchors"]
    assert isinstance(anchors, list)
    assert tuple(item["anchor_id"] for item in anchors) == CANONICAL_ANCHOR_IDS
    assert len({item["anchor_id"] for item in anchors}) == 18
    assert expected["formal_run_authorized"] is False
    assert expected["scientific_validation_status"] == "not_supported"
    assert EXPECTED_PATH.read_bytes() == rfc8785.dumps(expected) + b"\n"

    expected_resolved = EXPECTED_PATH.resolve()
    real_open = builtins.open
    real_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        try:
            candidate = Path(file).resolve()
        except TypeError:
            candidate = None
        if candidate == expected_resolved:
            raise AssertionError("oracle attempted to read the frozen expected vector")
        return real_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args, **kwargs):
        if path.resolve() == expected_resolved:
            raise AssertionError("oracle attempted to read the frozen expected vector")
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)

    oracle = _load_module(ORACLE_PATH, "m4_lightweight_oracle_contract")
    assert str(inspect.signature(oracle.evaluate_recipe)) == (
        "(recipe: 'Mapping[str, object]') -> 'dict[str, object]'"
    )
    first = oracle.evaluate_recipe(copy.deepcopy(recipe))
    second = oracle.evaluate_recipe(copy.deepcopy(recipe))
    assert first == second == expected
    completed = subprocess.run(
        [sys.executable, str(ORACLE_PATH), "--recipe", str(RECIPE_PATH)],
        check=True,
        capture_output=True,
    )
    assert completed.stderr == b""
    assert completed.stdout == rfc8785.dumps(expected) + b"\n"

    baseline_by_id = {item["anchor_id"]: item for item in first["anchors"]}
    deceleration_o1 = next(
        item
        for item in baseline_by_id["O1"]["trace"]["phase_results"]
        if item["phase_id"] == "Deceleration"
    )
    assert deceleration_o1["precision_percent"] == 90.0
    assert deceleration_o1["state"] == "desired"
    deceleration_o13 = next(
        item
        for item in baseline_by_id["O13"]["trace"]["windows"]
        if item["phase_id"] == "Deceleration"
    )
    assert deceleration_o13["control_score"] == 1.0
    assert deceleration_o13["coupling_loss_percent"] == 0.0

    def evaluated(candidate: dict[str, object]) -> dict[str, dict[str, object]]:
        result = oracle.evaluate_recipe(candidate)
        return {item["anchor_id"]: item for item in result["anchors"]}

    trajectory_recipe = copy.deepcopy(recipe)
    trajectory_recipe["trajectory"]["tracking_offset_m"] = 0.1
    trajectory_recipe["trajectory"]["kinematics"]["velocity_earth_m_s"] = [
        10.0,
        0.0,
        0.0,
    ]
    trajectory = evaluated(trajectory_recipe)
    for anchor_id in ("O1", "O2", "O3", "O4", "O10"):
        assert trajectory[anchor_id] != baseline_by_id[anchor_id]
    assert trajectory["O3"]["classification_override"] is None
    assert trajectory["O10"]["calculation_status"] == "not_applicable"
    assert trajectory["H5"] == baseline_by_id["H5"]

    movement_recipe = copy.deepcopy(recipe)
    movement_recipe["controls"]["workload_reversal"]["frequency_hz"] = 1.5
    movement = evaluated(movement_recipe)
    for anchor_id in ("O5", "O7", "O8", "O13"):
        assert movement[anchor_id] != baseline_by_id[anchor_id]
    assert movement["H4"] == baseline_by_id["H4"]

    magnitude_recipe = copy.deepcopy(recipe)
    magnitude_recipe["controls"]["full_travel"]["upper"] = 2.0
    magnitude = evaluated(magnitude_recipe)
    assert magnitude["O6"] != baseline_by_id["O6"]
    assert magnitude["H4"] == baseline_by_id["H4"]

    response_recipe = copy.deepcopy(recipe)
    response_recipe["controls"]["event_response"]["amplitude_full_travel_fraction"] = 0.04
    response = evaluated(response_recipe)
    assert response["O11"] != baseline_by_id["O11"]
    assert response["O12"] != baseline_by_id["O12"]
    assert response["H5"] == baseline_by_id["H5"]

    gaze_recipe = copy.deepcopy(recipe)
    gaze_recipe["gaze"]["off_task_tail_s_per_phase"] = 0.5
    gaze_recipe["gaze"]["aoi_geometry"][0]["bbox_norm"] = [0.1, 0.1, 0.1, 0.1]
    gaze = evaluated(gaze_recipe)
    for anchor_id in ("H1", "H2", "H3"):
        assert gaze[anchor_id] != baseline_by_id[anchor_id]
    assert gaze["O6"] == baseline_by_id["O6"]

    rr_recipe = copy.deepcopy(recipe)
    rr_recipe["ecg"]["provided_r_peaks"]["task_rr_step_s"] = 0.8
    rr = evaluated(rr_recipe)
    assert rr["H4"] != baseline_by_id["H4"]
    assert rr["O13"] != baseline_by_id["O13"]
    assert rr["H5"] == baseline_by_id["H5"]

    eeg_recipe = copy.deepcopy(recipe)
    eeg_recipe["eeg"]["components"]["beta"]["task_power_ratio"] = 1.6
    eeg = evaluated(eeg_recipe)
    assert eeg["H5"] != baseline_by_id["H5"]
    assert eeg["H4"] == baseline_by_id["H4"]

    pipeline_recipe = copy.deepcopy(recipe)
    pipeline_recipe["eeg"]["pipeline"]["bandpass_order"] = 2
    pipeline = evaluated(pipeline_recipe)
    assert pipeline["H5"] != baseline_by_id["H5"]
    assert pipeline["O6"] == baseline_by_id["O6"]
    assert SOURCE_HASHES_PATH.is_file(), (
        f"lightweight source-hash resource is not implemented: {SOURCE_HASHES_PATH}"
    )
    source_hashes = _load_json(SOURCE_HASHES_PATH)
    assert isinstance(source_hashes, dict)
    assert len(source_hashes) == 466
    assert list(source_hashes) == sorted(source_hashes)
    for relative_path, digest in source_hashes.items():
        path = Path(relative_path)
        assert relative_path == path.as_posix()
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
