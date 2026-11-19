"""Reference profiles change targets, never the supplied flight observations."""

from __future__ import annotations

import copy

import pytest

from pilot_assessment.scene_assessment.frame_calculator import evaluate
from pilot_assessment.scene_assessment.frame_validation import parameter_issues


def parameter(expected):
    return {
        "expected": expected,
        "desired": {"lower": -1, "upper": 1, "unbounded_upper": False},
        "acceptable": {"lower": -3, "upper": 3, "unbounded_upper": False},
    }


@pytest.fixture
def case():
    metric = {
        "metric_id": "speed",
        "name": "speed",
        "input_kind": "frame",
        "comparison": "linear",
        "rule": "interval",
        "value_type": "number",
        "phase_ids": ["approach", "deceleration"],
        "target_mode": "phase_profile",
    }
    phases = [
        {
            "phase_id": key,
            "name": key,
            "single_frame": False,
            "required_duration_s": None,
            "minimum_frame_count": 2,
        }
        for key in metric["phase_ids"]
    ]
    catalog = {
        "schema_version": "3.0",
        "scene_id": "PROFILE-TEST",
        "metrics": [metric],
        "phase_sequence": metric["phase_ids"],
        "items": [
            {
                "item_id": "flight",
                "name": "flight",
                "assessment_kind": "flight",
                "phases": phases,
                "checkpoints": [
                    {
                        "checkpoint_id": "speed-control",
                        "name": "speed-control",
                        "metric_ids": ["speed"],
                    }
                ],
            }
        ],
    }
    identity = {"schema_version": "3.0", "scene_id": "PROFILE-TEST"}
    config = {
        **identity,
        "parameters": {
            "speed": parameter(None)
            | {
                "reference_profiles": {
                    "approach": [
                        {"elapsed_s": 0, "expected": 20},
                        {"elapsed_s": 2, "expected": 18},
                        {"elapsed_s": 6, "expected": 10},
                    ],
                    "deceleration": [
                        {"elapsed_s": 0, "expected": 10},
                        {"elapsed_s": 4, "expected": 0},
                    ],
                },
            }
        },
    }
    source = {
        **identity,
        "items": {
            "flight": {
                "frames": [
                    {"timestamp_s": stamp, "phase_id": phase, "values": {"speed": actual}}
                    for stamp, phase, actual in [
                        (100, "approach", 20),
                        (101, "approach", 21),
                        (102, "approach", 18),
                        (105, "approach", 12),
                        (106, "approach", 10),
                        (110, "deceleration", 10),
                        (112, "deceleration", 5),
                        (114, "deceleration", 0),
                    ]
                ]
            }
        },
    }
    return catalog, config, source


def run(case):
    return evaluate(case[1], case[2], case[0])


def result_metric(report):
    return report["items"][0]["checkpoints"][0]["metrics"][0]


def test_piecewise_targets_use_exact_observations_and_keep_config(case):
    original = copy.deepcopy(case)
    report = run(case)
    points = result_metric(report)["timeline"]
    assert report["calculation_status"] == "complete"
    assert report["grade"] == "A" and report["passed"] is True
    assert [p["expected"] for p in points] == [20, 19, 18, 12, 10, 10, 5, 0]
    assert [p["deviation"] for p in points] == [0, 2, 0, 0, 0, 0, 0, 0]
    assert [p["value"] for p in points] == [20, 21, 18, 12, 10, 10, 5, 0]
    assert [p["timestamp_s"] for p in points] == [100, 101, 102, 105, 106, 110, 112, 114]
    assert len(points) == 8
    assert case == original
    assert report["configuration"] == original[1] and report["input"] == original[2]


def test_phase_reference_clock_is_invariant_to_time_translation(case):
    baseline = result_metric(run(case))["timeline"]
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["timestamp_s"] += 43200.25
    shifted = result_metric(run(case))["timeline"]
    assert [(p["expected"], p["deviation"], p["grade"]) for p in shifted] == [
        (p["expected"], p["deviation"], p["grade"]) for p in baseline
    ]


@pytest.mark.parametrize("translation", [0, 100, 43200.25])
def test_decimal_profile_endpoint_survives_clock_translation_roundoff(case, translation):
    case[1]["parameters"]["speed"]["reference_profiles"]["approach"] = [
        {"elapsed_s": 0, "expected": 20},
        {"elapsed_s": 0.3, "expected": 10},
    ]
    frames = case[2]["items"]["flight"]["frames"]
    frames[:] = [
        {"timestamp_s": 10.1, "phase_id": "approach", "values": {"speed": 20}},
        {"timestamp_s": 10.4, "phase_id": "approach", "values": {"speed": 10}},
    ] + [frame for frame in frames if frame["phase_id"] == "deceleration"]
    for frame in frames:
        frame["timestamp_s"] += translation
    report = run(case)
    terminal = result_metric(report)["timeline"][1]
    assert terminal["timestamp_s"] == 10.4 + translation
    assert terminal["status"] == "calculated"
    assert terminal["expected"] == 10 and terminal["deviation"] == 0
    assert report["passed"] is True

    # This offset is far beyond floating representation error at these clock
    # scales; endpoint correction must not become a physical time tolerance.
    frames[1]["timestamp_s"] += 0.000001
    outside = result_metric(run(case))["timeline"][1]
    assert outside["status"] == "missing" and outside["expected"] is None
    assert outside["grade"] is None


def test_outside_profile_is_missing_not_extrapolated_or_failed(case):
    case[2]["items"]["flight"]["frames"][-1]["timestamp_s"] = 114.1
    report = run(case)
    point = result_metric(report)["timeline"][-1]
    assert point["value"] == 0
    assert point["status"] == "missing"
    assert point["expected"] is None and point["deviation"] is None
    assert point["grade"] is None
    assert report["passed"] is None
    assert report["items"][0]["phase_results"][-1]["status"] == "missing"


def test_exact_integer_clock_does_not_gain_a_floating_endpoint_allowance(case):
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["timestamp_s"] += 2**60
    case[2]["items"]["flight"]["frames"][-1]["timestamp_s"] += 1
    terminal = result_metric(run(case))["timeline"][-1]
    assert terminal["status"] == "missing" and terminal["expected"] is None


def test_known_profile_target_remains_visible_when_raw_value_is_missing(case):
    case[2]["items"]["flight"]["frames"][1]["values"]["speed"] = None
    point = result_metric(run(case))["timeline"][1]
    assert point["expected"] == 19
    assert point["value"] is None and point["deviation"] is None
    assert point["status"] == "missing" and point["grade"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(expected=20),
        lambda p: p.pop("expected"),
        lambda p: p.update(reference_profiles={}),
        lambda p: p["reference_profiles"].pop("deceleration"),
        lambda p: p["reference_profiles"].update(unknown=[]),
        lambda p: p["reference_profiles"].update(approach=None),
        lambda p: p["reference_profiles"].update(approach=[{"elapsed_s": 0, "expected": 20}]),
        lambda p: p["reference_profiles"]["approach"][0].update(elapsed_s=1),
        lambda p: p["reference_profiles"]["approach"][1].update(elapsed_s=0),
        lambda p: p["reference_profiles"]["approach"][1].update(elapsed_s=-1),
        lambda p: p["reference_profiles"]["approach"][1].update(elapsed_s=True),
        lambda p: p["reference_profiles"]["approach"][1].update(elapsed_s=float("inf")),
        lambda p: p["reference_profiles"]["approach"][1].update(expected=float("nan")),
        lambda p: p["reference_profiles"]["approach"][1].update(expected=True),
        lambda p: p["reference_profiles"]["approach"][1].update(other=1),
        lambda p: p["reference_profiles"]["approach"].append("bad node"),
    ],
)
def test_malformed_profile_cannot_produce_pass(case, change):
    change(case[1]["parameters"]["speed"])
    assert parameter_issues(case[1]["parameters"]["speed"], case[0]["metrics"][0])
    report = run(case)
    assert report["passed"] is None and report["calculation_status"] == "needs_input"
    assert all(p["status"] == "invalid" for p in result_metric(report)["timeline"])


def test_profiles_are_linear_only_and_fixed_targets_reject_profile_fields(case):
    metric = case[0]["metrics"][0]
    config = case[1]["parameters"]["speed"]
    metric["comparison"] = "angle_degrees"
    assert parameter_issues(config, metric)
    metric.pop("target_mode")
    config["expected"] = 20
    assert parameter_issues(config, metric)
    config.pop("reference_profiles")
    assert not parameter_issues(config, metric)
    points = result_metric(run(case))["timeline"]
    assert all(p["expected"] == 20 for p in points)
    assert points[-1]["grade"] == "U"


@pytest.mark.parametrize("actual,grade,passed", [(20, None, None), (100, "U", False)])
def test_insufficient_frames_prevent_pass_but_preserve_observed_u(case, actual, grade, passed):
    frames = case[2]["items"]["flight"]["frames"]
    frames[:] = [frames[0]] + [f for f in frames if f["phase_id"] == "deceleration"]
    frames[0]["values"]["speed"] = actual
    report = run(case)
    phase = report["items"][0]["phase_results"][0]
    assert phase["status"] == "missing" and phase["minimum_frame_count"] == 2
    assert phase["grade"] == grade and phase["passed"] is passed
    assert report["grade"] == grade and report["passed"] is passed
    assert report["calculation_status"] == "needs_input"


def test_minimum_count_is_optional_for_existing_phase_contract(case):
    frames = case[2]["items"]["flight"]["frames"]
    frames[:] = [frames[0]] + [f for f in frames if f["phase_id"] == "deceleration"]
    case[0]["items"][0]["phases"][0].pop("minimum_frame_count")
    report = run(case)
    assert report["grade"] == "D" and report["passed"] is True
