"""A single declared start clock covers acceleration and speed hold."""

import copy

import pytest

from pilot_assessment.scene_assessment.catalog import load_catalog
from pilot_assessment.scene_assessment.frame_calculator import evaluate
from pilot_assessment.scene_assessment.frame_validation import parameter_issues


@pytest.fixture
def case():
    identity = {"schema_version": "3.0", "scene_id": "ITEM-PROFILE-TEST"}
    metric = {
        "metric_id": "speed",
        "name": "speed",
        "input_kind": "frame",
        "comparison": "linear",
        "rule": "interval",
        "value_type": "number",
        "phase_ids": ["acceleration", "hold"],
        "target_mode": "item_profile",
        "reference_origin_phase": "acceleration",
    }
    item = {
        "item_id": "flight",
        "name": "flight",
        "assessment_kind": "flight",
        "phases": [
            {
                "phase_id": phase,
                "name": phase,
                "single_frame": False,
                "required_duration_s": None,
                "minimum_frame_count": 2,
            }
            for phase in metric["phase_ids"]
        ],
        "checkpoints": [
            {"checkpoint_id": "speed-control", "name": "speed-control", "metric_ids": ["speed"]}
        ],
    }
    catalog = {
        **identity,
        "metrics": [metric],
        "items": [item],
        "phase_sequence": metric["phase_ids"],
    }
    config = {
        **identity,
        "parameters": {
            "speed": {
                "expected": None,
                "desired": {"lower": -1, "upper": 1, "unbounded_upper": False},
                "acceptable": {"lower": -3, "upper": 3, "unbounded_upper": False},
                "reference_profile": [
                    {"elapsed_s": 0, "expected": 0},
                    {"elapsed_s": 2, "expected": 4},
                    {"elapsed_s": 6, "expected": 10},
                    {"elapsed_s": 16, "expected": 10},
                ],
            }
        },
        "skill_models": {
            "flight": {
                "model_version": "supervisor-demo-2026-09-15-v1",
                "inference_method": "demo_normalized_grade_likelihood_v1",
                "calibration": "uncalibrated",
                "parameter_source": "demonstration",
                "prior": [1 / 3] * 3,
                "state_scores": [0, 50, 100],
                "checkpoint_models": {
                    "speed-control": {
                        "states": ["D", "A", "U"],
                        "probabilities": [
                            [0.1, 0.25, 0.65],
                            [0.35, 0.63, 0.02],
                            [0.9, 0.099, 0.001],
                        ],
                    }
                },
            }
        },
    }
    data = {
        **identity,
        "items": {
            "flight": {
                "frames": [
                    {"timestamp_s": timestamp, "phase_id": phase, "values": {"speed": actual}}
                    for timestamp, phase, actual in [
                        (100, "acceleration", 0),
                        (102.4, "acceleration", 4.6),
                        (106.1, "hold", 10),
                        (116, "hold", 10),
                    ]
                ]
            }
        },
    }
    return catalog, config, data


def run(case):
    return evaluate(case[1], case[2], case[0])


def metric_result(report):
    return report["items"][0]["checkpoints"][0]["metrics"][0]


def test_single_origin_interpolates_non_nodes_without_reset_or_resampling(case):
    original = copy.deepcopy(case)
    report = run(case)
    timeline = metric_result(report)["timeline"]
    assert report["calculation_status"] == "complete", report["issues"]
    assert report["grade"] == "D"
    assert [p["reference_elapsed_s"] for p in timeline] == pytest.approx([0, 2.4, 6.1, 16])
    assert [p["expected"] for p in timeline] == pytest.approx([0, 4.6, 10, 10])
    assert [p["value"] for p in timeline] == [0, 4.6, 10, 10]
    assert case == original
    quantification = report["items"][0]["skill_quantification"]
    assert quantification["cumulative_trace"]["timeline"][-1]["score"] == quantification["score"]
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["timestamp_s"] += 43200.25
    shifted = metric_result(run(case))["timeline"]
    assert [p["expected"] for p in shifted] == pytest.approx([0, 4.6, 10, 10])
    assert [p["grade"] for p in shifted] == [p["grade"] for p in timeline]


@pytest.mark.parametrize("deviation,grade", [(-3, "A"), (-1, "D"), (1, "D"), (3, "A"), (3.01, "U")])
def test_signed_d_a_boundaries_apply_to_dynamic_expected(case, deviation, grade):
    case[2]["items"]["flight"]["frames"][2]["values"]["speed"] = 10 + deviation
    assert metric_result(run(case))["timeline"][2]["grade"] == grade


@pytest.mark.parametrize("actual,grade", [(10, None), (100, "U")])
def test_early_end_blocks_final_score_without_erasing_observed_failure(case, actual, grade):
    case[2]["items"]["flight"]["frames"][-1].update(timestamp_s=115.9, values={"speed": actual})
    report = run(case)
    result = metric_result(report)
    assert report["calculation_status"] == "needs_input"
    assert report["grade"] == grade
    assert result["status"] == "missing" and result["grade"] == grade
    assert len(result["timeline"]) == 4  # No fabricated end sample.
    assert all(p["status"] == "calculated" for p in result["timeline"])
    assert report["items"][0]["phase_results"][-1]["status"] == "missing"
    quantification = report["items"][0]["skill_quantification"]
    assert quantification["score"] is None
    assert quantification["cumulative_trace"]["timeline"][-1]["score"] is None
    assert quantification["cumulative_trace"]["timeline"][0]["score"] is not None


def test_missing_origin_never_uses_first_hold_frame_as_zero(case):
    frames = case[2]["items"]["flight"]["frames"]
    frames[:] = [f for f in frames if f["phase_id"] == "hold"]
    report = run(case)
    assert report["passed"] is None
    assert all(
        p["status"] == "missing" and p["expected"] is None and p["reference_elapsed_s"] is None
        for p in metric_result(report)["timeline"]
    )


def test_frame_beyond_reference_end_is_missing_not_extrapolated(case):
    case[2]["items"]["flight"]["frames"][-1]["timestamp_s"] += 0.000001
    report = run(case)
    point = metric_result(report)["timeline"][-1]
    assert point["status"] == "missing" and point["expected"] is None
    assert report["passed"] is None


def test_integer_clock_does_not_gain_floating_time_slack(case):
    frames = case[2]["items"]["flight"]["frames"]
    for frame, stamp in zip(frames, [100, 102, 107, 116], strict=True):
        frame["timestamp_s"] = stamp + 2**60
    frames[-1]["timestamp_s"] -= 1
    report = run(case)
    assert metric_result(report)["status"] == "missing"
    assert report["items"][0]["skill_quantification"]["score"] is None


@pytest.mark.parametrize("origin", [None, "unknown", 1])
def test_missing_or_invalid_catalog_origin_cannot_select_a_different_clock(case, origin):
    case[0]["metrics"][0]["reference_origin_phase"] = origin
    assert parameter_issues(case[1]["parameters"]["speed"], case[0]["metrics"][0])
    assert run(case)["passed"] is None


@pytest.mark.parametrize("translation", [0, 100, 43200.25])
def test_only_float_representation_error_is_allowed_at_terminal_time(case, translation):
    config = case[1]["parameters"]["speed"]
    config["reference_profile"] = [
        {"elapsed_s": 0, "expected": 0},
        {"elapsed_s": 0.3, "expected": 10},
    ]
    frames = case[2]["items"]["flight"]["frames"]
    for frame, timestamp in zip(frames, [10.1, 10.2, 10.3, 10.4], strict=True):
        frame["timestamp_s"] = timestamp + translation
        frame["values"]["speed"] = (timestamp - 10.1) / 0.3 * 10
    assert run(case)["calculation_status"] == "complete"
    frames[-1]["timestamp_s"] -= 0.000001
    assert run(case)["calculation_status"] == "needs_input"


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(expected=10),
        lambda p: p.pop("expected"),
        lambda p: p.update(reference_profile=[]),
        lambda p: p.update(reference_profile=None),
        lambda p: p.update(reference_profile=[{"elapsed_s": 0, "expected": 0}]),
        lambda p: p["reference_profile"][0].update(elapsed_s=1),
        lambda p: p["reference_profile"][1].update(elapsed_s=0),
        lambda p: p["reference_profile"][1].update(elapsed_s=-1),
        lambda p: p["reference_profile"][1].update(elapsed_s=True),
        lambda p: p["reference_profile"][1].update(elapsed_s=float("inf")),
        lambda p: p["reference_profile"][1].update(expected=float("nan")),
        lambda p: p["reference_profile"][1].update(expected=True),
        lambda p: p["reference_profile"][1].update(other=1),
        lambda p: p["reference_profile"].append("bad node"),
        lambda p: p.update(reference_profiles={}),
    ],
)
def test_bad_shared_reference_never_produces_a_pass(case, change):
    change(case[1]["parameters"]["speed"])
    assert parameter_issues(case[1]["parameters"]["speed"], case[0]["metrics"][0])
    report = run(case)
    assert report["passed"] is None
    assert all(p["status"] == "invalid" for p in metric_result(report)["timeline"])


def test_new_scene_contract_removes_legacy_hold_end_and_duration_field():
    catalog = load_catalog("SCN-001")
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    assert "speed_hold_duration_s" not in metrics and "speed_hold_airspeed_mps" not in metrics
    assert "hold_end" not in catalog["phase_sequence"]
    metric = metrics["air_taxi_airspeed_mps"]
    assert metric["target_mode"] == "item_profile"
    assert metric["reference_origin_phase"] == "acceleration"
    assert metric["phase_ids"] == ["acceleration", "hold"]
    item = next(item for item in catalog["items"] if item["item_id"] == "A-S2-05")
    assert [p["phase_id"] for p in item["phases"]] == ["acceleration", "hold"]
    assert all(p["minimum_frame_count"] == 2 for p in item["phases"])
    assert item["checkpoints"][0]["metric_ids"] == ["air_taxi_airspeed_mps"]
    parameter = catalog["configuration_template"]["parameters"][metric["metric_id"]]
    assert parameter["expected"] is None and parameter["reference_profile"] == []
    assert parameter["desired"]["upper"] is None


def test_legacy_field_names_and_phase_are_rejected(case):
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["speed_hold_airspeed_mps"] = 10
    report = run(case)
    assert report["calculation_status"] == "needs_input" and report["passed"] is None
    case[2]["items"]["flight"]["frames"][-1]["phase_id"] = "hold_end"
    assert run(case)["calculation_status"] == "needs_input"
