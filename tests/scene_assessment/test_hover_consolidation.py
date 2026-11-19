"""Hover height is required evidence in the same item as position and heading."""

import copy
import runpy
from pathlib import Path

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration
from pilot_assessment.scene_assessment.catalog import load_catalog


@pytest.fixture
def hover_case():
    catalog = load_catalog("SCN-002")
    factory = runpy.run_path(str(Path(__file__).resolve().parents[2]
                                / "tools/Generate-SceneFrameExamples.py"))["engineering_case"]
    config, data = factory(catalog)
    for item in data["items"].values():
        for frame in item["frames"]:
            for key in frame["values"]:
                parameter = config["parameters"][key]
                frame["values"][key] = (
                    {"status": "hit", "u_m": 0, "v_m": 0}
                    if "center_u" in parameter else parameter["expected"]
                )
    for model in config["skill_models"].values():
        model.update(
            inference_method="sequential_bayes_compensation_v1", compensation={"alpha": 0.2},
            parameter_source="demonstration", prior=[1 / 3] * 3, state_scores=[0, 50, 100],
        )
        for point in model["checkpoint_models"].values():
            point["probabilities"] = [[.1, .25, .65], [.35, .63, .02], [.9, .099, .001]]
    return config, data


def hold(report):
    return next(item for item in report["items"] if item["item_id"] == "A-S2-02")


def test_hover_template_owns_height_once_in_the_same_frame_and_model():
    catalog = load_catalog("SCN-002")
    assert [item["item_id"] for item in catalog["items"]] == ["A-S2-02", "SCENE-VERTICAL"]
    item = catalog["items"][0]
    assert item["name"] == "定点悬停保持"
    points = {point["checkpoint_id"]: point for point in item["checkpoints"]}
    assert list(points) == ["A-S2-02-01", "A-S2-02-04", "A-S2-02-02", "A-S2-02-03"]
    assert points["A-S2-02-04"]["metric_ids"] == [
        "hover_lower_height_m", "hover_upper_height_m", "hover_vz_mps"
    ]
    assert points["A-S2-02-02"]["metric_ids"] == ["hover_heading_deg"]
    all_keys = [key for point in points.values() for key in point["metric_ids"]]
    assert len(all_keys) == len(set(all_keys))
    assert set(catalog["configuration_template"]["skill_models"]) == {"A-S2-02", "SCENE-VERTICAL"}
    model = catalog["configuration_template"]["skill_models"]["A-S2-02"]
    assert set(model["checkpoint_models"]) == set(points)
    for frame in catalog["input_template"]["items"]["A-S2-02"]["frames"]:
        expected_height = "hover_" + frame["phase_id"].split("_")[0] + "_height_m"
        assert expected_height in frame["values"]
        assert len([key for key in frame["values"] if "height_m" in key]) == 1
        assert {"hover_x_m", "hover_y_m", "hover_heading_deg", "hover_vz_mps"} <= set(
            frame["values"]
        )


@pytest.mark.parametrize("height_key, phase", [
    ("hover_lower_height_m", "lower_1"), ("hover_upper_height_m", "upper_1")
])
def test_height_error_changes_hover_fail_and_process_even_if_other_checks_are_desired(
    hover_case, height_key, phase
):
    config, data = hover_case
    baseline = evaluate(config, data)
    assert baseline["passed"] is True
    frames = data["items"]["A-S2-02"]["frames"]
    for frame in frames:
        if frame["phase_id"] == phase:
            parameter = config["parameters"][height_key]
            frame["values"][height_key] = (
                parameter["expected"] + parameter["acceptable"]["upper"] + 1
            )
    report = evaluate(config, data)
    assert report["calculation_status"] == "complete", report["issues"]
    result = hold(report)
    assert result["grade"] == "U" and result["passed"] is False
    points = {point["checkpoint_id"]: point for point in result["checkpoints"]}
    assert points["A-S2-02-04"]["grade"] == "U"
    assert all(point["grade"] == "D" for key, point in points.items() if key != "A-S2-02-04")
    score = result["skill_quantification"]
    affected = score["temporal_analysis"]["item_trace"]["timeline"]
    baseline_analysis = hold(baseline)["skill_quantification"]["temporal_analysis"]
    reference = baseline_analysis["item_trace"]["timeline"]
    changed_pairs = [
        (a, b) for a, b in zip(affected, reference, strict=True) if a["phase_id"] == phase
    ]
    assert changed_pairs
    assert all(a["score"] < b["score"] for a, b in changed_pairs)
    # The current-state estimate can recover later; the observed U stays Fail.
    assert score["score"] == affected[-1]["score"]
    assert score["evidence_count"] == score["expected_evidence_count"] == 4
    assert all(point["weight"] is None for point in score["evidence"])
    assert sum(score["posterior"]) == pytest.approx(1)


def test_missing_height_cannot_be_replaced_by_zero_vertical_speed_or_laser(hover_case):
    config, data = hover_case
    del data["items"]["A-S2-02"]["frames"][0]["values"]["hover_lower_height_m"]
    report = evaluate(config, data)
    assert report["calculation_status"] == "needs_input"
    assert hold(report)["passed"] is None
    assert hold(report)["skill_quantification"]["score"] is None
    assert any("hover_lower_height_m" in issue["path"] for issue in report["issues"])


@pytest.mark.parametrize("metric, checkpoint", [
    ("hover_vx_mps", "A-S2-02-01"), ("hover_vy_mps", "A-S2-02-01"),
    ("hover_vz_mps", "A-S2-02-04"), ("hover_heading_deg", "A-S2-02-02")
])
def test_each_motion_indicator_affects_only_its_assigned_checkpoint(hover_case, metric, checkpoint):
    config, data = hover_case
    parameter = config["parameters"][metric]
    data["items"]["A-S2-02"]["frames"][0]["values"][metric] = (
        parameter["expected"] + parameter["acceptable"]["upper"] + 1
    )
    result = hold(evaluate(config, data))
    unacceptable = [
        point["checkpoint_id"] for point in result["checkpoints"] if point["grade"] == "U"
    ]
    assert unacceptable == [checkpoint]


def test_legacy_split_input_is_rejected_without_silently_ignoring_height(hover_case):
    config, data = hover_case
    data["items"]["A-S2-01"] = {"frames": []}
    for frame in data["items"]["A-S2-02"]["frames"]:
        height = {key: value for key, value in frame["values"].items() if "height_m" in key}
        data["items"]["A-S2-01"]["frames"].append({**copy.deepcopy(frame), "values": height})
        for key in height:
            del frame["values"][key]
    report = evaluate(config, data)
    assert report["calculation_status"] == "needs_input"
    assert hold(report)["skill_quantification"]["score"] is None
    assert any(issue["path"] == "/input/items/A-S2-01" for issue in report["issues"])


def test_old_three_checkpoint_cpt_is_not_silently_used_as_the_merged_model(hover_case):
    config, data = hover_case
    del config["skill_models"]["A-S2-02"]["checkpoint_models"]["A-S2-02-04"]
    assert validate_configuration(config)["valid"] is False
    result = hold(evaluate(config, data))
    assert result["passed"] is True  # Model validity does not override the flight rules.
    assert result["skill_quantification"]["status"] == "invalid_model"
    assert result["skill_quantification"]["score"] is None
