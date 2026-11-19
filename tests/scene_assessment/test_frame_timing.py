"""Scene chronology validates explicit phase labels without detecting new events."""

import copy
import runpy
from pathlib import Path

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate
from pilot_assessment.scene_assessment.catalog import load_catalog


def all_desired_case(scene_id):
    catalog = load_catalog(scene_id, "3.0")
    root = Path(__file__).resolve().parents[2]
    factory = runpy.run_path(str(root / "tools/Generate-SceneFrameExamples.py"))["engineering_case"]
    config, data = factory(catalog)
    for item in data["items"].values():
        for frame in item["frames"]:
            for key in frame["values"]:
                parameter = config["parameters"].get(key)
                if parameter is not None and (
                    "reference_profiles" in parameter
                    or "reference_profile" in parameter
                    or "route_points" in parameter
                ):
                    # The example already follows its explicitly configured route/profile.
                    continue
                if parameter is not None:
                    frame["values"][key] = (
                        {"status": "hit", "u_m": 0, "v_m": 0}
                        if "center_u" in parameter
                        else parameter["expected"]
                    )
    assert evaluate(config, data)["passed"] is True
    return config, data


@pytest.fixture
def aligned_case():
    return all_desired_case("SCN-002")


def test_same_phase_cannot_refer_to_different_times_across_items(aligned_case):
    config, data = aligned_case
    # The current hover scene shares one item for height and position. Keep
    # testing the generic cross-item timing invariant with an explicit second
    # observer, rather than retaining the retired height-only scene item.
    catalog = load_catalog("SCN-002")
    observer = copy.deepcopy(catalog["items"][0])
    observer["item_id"] = "TEST-SECOND-OBSERVER"
    catalog["items"].append(observer)
    config["skill_models"][observer["item_id"]] = copy.deepcopy(config["skill_models"]["A-S2-02"])
    data["items"][observer["item_id"]] = copy.deepcopy(data["items"]["A-S2-02"])
    assert evaluate(config, data, catalog=catalog)["passed"] is True
    for frame in data["items"][observer["item_id"]]["frames"]:
        frame["timestamp_s"] += 100
    report = evaluate(config, data, catalog=catalog)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None
    assert any("同名环节" in issue["message"] for issue in report["issues"])


def test_out_of_order_transfer_is_incomplete_but_preserves_local_u(aligned_case):
    config, data = aligned_case
    for frame in data["items"]["SCENE-VERTICAL"]["frames"]:
        frame["timestamp_s"] -= 15
    data["items"]["A-S2-02"]["frames"][0]["values"]["hover_x_m"] += 100
    report = evaluate(config, data)
    assert report["calculation_status"] == "needs_input"
    assert report["grade"] == "U" and report["passed"] is False
    assert any(issue["path"] == "/input/phase_sequence" for issue in report["issues"])


def test_equal_phase_boundary_is_allowed_but_overlap_is_rejected(aligned_case):
    config, data = aligned_case
    transfer = data["items"]["SCENE-VERTICAL"]["frames"]
    first = next(frame for frame in transfer if frame["phase_id"] == "rise_1")
    first["timestamp_s"] = 15
    assert evaluate(config, data)["passed"] is True
    first["timestamp_s"] = 14.99
    report = evaluate(config, data)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None
    assert any(issue["path"] == "/input/phase_sequence" for issue in report["issues"])


def test_same_frame_actual_height_cannot_have_two_conflicting_values():
    config, data = all_desired_case("SCN-001")
    stop = data["items"]["A-S2-30"]["frames"][-1]
    stop["values"]["stop_height_m"] += 0.1  # Still individually D, but not the same actual height.
    report = evaluate(config, data)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None
    assert any("同一原始量" in issue["message"] for issue in report["issues"])
