"""A spatial route is checked against raw positions, without a time schedule."""

from __future__ import annotations

import copy
import json
import math

import pytest

from pilot_assessment.scene_assessment.frame_calculator import evaluate
from pilot_assessment.scene_assessment.frame_validation import parameter_issues


def position(x=0, y=0, h=0):
    return {"x_m": x, "y_m": y, "height_m": h}


@pytest.fixture
def case():
    metric = {
        "metric_id": "approach_position_m",
        "name": "进近三维位置",
        "input_kind": "frame",
        "comparison": "route_3d",
        "rule": "interval",
        "value_type": "position_3d",
        "phase_ids": ["approach"],
    }
    catalog = {
        "schema_version": "3.0",
        "scene_id": "ROUTE-TEST",
        "metrics": [metric],
        "phase_sequence": ["approach"],
        "items": [
            {
                "item_id": "flight",
                "name": "flight",
                "assessment_kind": "flight",
                "phases": [
                    {
                        "phase_id": "approach",
                        "name": "approach",
                        "single_frame": False,
                        "required_duration_s": None,
                        "minimum_frame_count": 2,
                    }
                ],
                "checkpoints": [
                    {
                        "checkpoint_id": "route-control",
                        "name": "进近航迹控制",
                        "metric_ids": ["approach_position_m"],
                    }
                ],
            }
        ],
    }
    identity = {"schema_version": "3.0", "scene_id": "ROUTE-TEST"}
    config = {
        **identity,
        "parameters": {
            "approach_position_m": {
                "expected": 0,
                "desired": {"lower": 0, "upper": 1, "unbounded_upper": False},
                "acceptable": {"lower": 0, "upper": 3, "unbounded_upper": False},
                "route_points": [position(), position(10)],
            }
        },
    }
    source = {
        **identity,
        "items": {
            "flight": {
                "frames": [
                    {
                        "timestamp_s": stamp,
                        "phase_id": "approach",
                        "values": {"approach_position_m": point},
                    }
                    for stamp, point in [(10, position(2)), (25, position(8))]
                ]
            }
        },
    }
    return catalog, config, source


def run(case):
    return evaluate(case[1], case[2], case[0])


def metric_result(report):
    return report["items"][0]["checkpoints"][0]["metrics"][0]


@pytest.mark.parametrize(
    "route,actual,nearest,distance,segment",
    [
        ([position(), position(10)], position(5, 2), position(5), 2, 0),
        ([position(), position(10)], position(5, 0, 2), position(5), 2, 0),
        ([position(), position(10)], position(5, 3, 4), position(5), 5, 0),
        ([position(), position(10)], position(-2, 0), position(), 2, 0),
        ([position(), position(10)], position(13, 0, 4), position(10), 5, 0),
        ([position(), position(0, 0, 10)], position(3, 4, 7), position(0, 0, 7), 5, 0),
        ([position(), position(10, 0, 10)], position(8, 0, 2), position(5, 0, 5), math.sqrt(18), 0),
        (
            [position(), position(10), position(10, 10)],
            position(12, 8),
            position(10, 8),
            2,
            1,
        ),
    ],
)
def test_distance_to_finite_three_dimensional_route(
    case, route, actual, nearest, distance, segment
):
    case[1]["parameters"]["approach_position_m"]["route_points"] = route
    case[2]["items"]["flight"]["frames"][0]["values"]["approach_position_m"] = actual
    point = metric_result(run(case))["timeline"][0]
    assert point["status"] == "calculated"
    assert point["value"] == actual and point["expected"] == 0
    assert point["deviation"] == pytest.approx(distance)
    assert point["nearest_route_point"] == pytest.approx(nearest)
    assert point["route_segment_index"] == segment


@pytest.mark.parametrize(
    "distance,grade", [(0, "D"), (1, "D"), (1.001, "A"), (3, "A"), (3.001, "U")]
)
def test_distance_bands_include_their_outer_boundary(case, distance, grade):
    case[2]["items"]["flight"]["frames"][0]["values"]["approach_position_m"] = position(5, distance)
    report = run(case)
    assert metric_result(report)["timeline"][0]["grade"] == grade
    assert report["calculation_status"] == "complete"
    assert report["passed"] == (grade != "U")


def test_positions_are_not_retimed_interpolated_or_replaced(case):
    original = copy.deepcopy(case)
    report = run(case)
    points = metric_result(report)["timeline"]
    assert [point["timestamp_s"] for point in points] == [10, 25]
    assert [point["frame_index"] for point in points] == [0, 1]
    assert [point["value"] for point in points] == [position(2), position(8)]
    assert [point["deviation"] for point in points] == [0, 0]
    assert report["passed"] is True
    assert case == original
    assert report["configuration"] == original[1] and report["input"] == original[2]
    json.dumps(report, allow_nan=False)


def test_route_check_is_spatial_and_does_not_invent_progress_or_speed(case):
    frames = case[2]["items"]["flight"]["frames"]
    frames[0]["values"]["approach_position_m"] = position(8)
    frames[1]["values"]["approach_position_m"] = position(2)
    frames[1]["timestamp_s"] = 10000
    report = run(case)
    assert report["passed"] is True
    assert [point["timestamp_s"] for point in metric_result(report)["timeline"]] == [10, 10000]


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.pop("route_points"),
        lambda p: p.update(route_points=[]),
        lambda p: p.update(route_points=[position()]),
        lambda p: p.update(route_points=[position(), position()]),
        lambda p: p["route_points"][0].update(x_m=None),
        lambda p: p["route_points"][0].pop("height_m"),
        lambda p: p["route_points"][0].update(y_m=True),
        lambda p: p["route_points"][0].update(height_m=math.inf),
        lambda p: p["route_points"][0].update(z_m=1),
        lambda p: p.update(route_points="0,0,0;10,0,0"),
        lambda p: p.update(expected=1),
        lambda p: p.update(expected=False),
        lambda p: p["desired"].update(lower=-1),
        lambda p: p["desired"].update(upper=-1),
        lambda p: p["acceptable"].update(upper=1),
        lambda p: p["acceptable"].update(upper=None, unbounded_upper=True),
        lambda p: p.update(reference_profiles={}),
        lambda p: p.update(center_u=0),
    ],
)
def test_invalid_or_incomplete_route_config_is_never_pilot_failure_or_pass(case, change):
    parameter = case[1]["parameters"]["approach_position_m"]
    change(parameter)
    assert parameter_issues(parameter, case[0]["metrics"][0])
    report = run(case)
    assert report["calculation_status"] == "needs_input"
    assert report["grade"] is None and report["passed"] is None
    assert all(point["grade"] is None for point in metric_result(report)["timeline"])


@pytest.mark.parametrize(
    "raw,status",
    [
        (None, "missing"),
        ({}, "missing"),
        (position(None, None, None), "missing"),
        (position(1, None, 0), "missing"),
        (position(True), "invalid"),
        (position(math.nan), "invalid"),
        (position(math.inf), "invalid"),
        (position() | {"z_m": 0}, "invalid"),
        ([0, 0, 0], "invalid"),
        (0, "invalid"),
    ],
)
def test_unavailable_or_invalid_position_cannot_pass(case, raw, status):
    case[2]["items"]["flight"]["frames"][0]["values"]["approach_position_m"] = raw
    report = run(case)
    point = metric_result(report)["timeline"][0]
    assert point["status"] == status
    assert point["grade"] is None and point["deviation"] is None
    assert "nearest_route_point" not in point and "route_segment_index" not in point
    assert report["passed"] is None and report["calculation_status"] == "needs_input"


def test_known_failure_survives_recovery_and_a_missing_position(case):
    frames = case[2]["items"]["flight"]["frames"]
    frames[0]["values"]["approach_position_m"] = position(2, 4)
    report = run(case)
    assert [p["grade"] for p in metric_result(report)["timeline"]] == ["U", "D"]
    assert report["grade"] == "U" and report["passed"] is False
    frames[1]["values"]["approach_position_m"] = None
    report = run(case)
    assert report["grade"] == "U" and report["passed"] is False
    assert report["calculation_status"] == "needs_input"


def test_reversed_frames_are_rejected_and_not_reordered(case):
    case[2]["items"]["flight"]["frames"].reverse()
    report = run(case)
    assert report["passed"] is None and report["calculation_status"] == "needs_input"
    assert metric_result(report)["timeline"] == []


def test_old_lateral_position_input_is_not_silently_migrated(case):
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"] = {"approach_lateral_position_m": 0}
    report = run(case)
    assert report["passed"] is None and report["calculation_status"] == "needs_input"
    assert any("approach_lateral_position_m" in entry["path"] for entry in report["issues"])


def test_equal_distance_uses_first_configured_segment(case):
    case[1]["parameters"]["approach_position_m"]["route_points"] = [
        position(),
        position(10),
        position(10, 10),
    ]
    case[2]["items"]["flight"]["frames"][0]["values"]["approach_position_m"] = position(9, 1)
    point = metric_result(run(case))["timeline"][0]
    assert point["deviation"] == 1
    assert point["route_segment_index"] == 0
    assert point["nearest_route_point"] == position(9)


@pytest.mark.parametrize("endpoint", [1e-200, 1e200, 10**308])
def test_finite_extreme_segment_scales_do_not_create_nan(case, endpoint):
    case[1]["parameters"]["approach_position_m"]["route_points"] = [
        position(-endpoint),
        position(endpoint),
    ]
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["approach_position_m"] = position(0, 2)
    report = run(case)
    point = metric_result(report)["timeline"][0]
    assert point["status"] == "calculated"
    assert point["deviation"] == 2
    assert point["nearest_route_point"] == position()
    assert report["grade"] == "A"
    json.dumps(report, allow_nan=False)


def test_unrepresentable_distance_is_invalid_and_json_safe(case):
    case[1]["parameters"]["approach_position_m"]["route_points"] = [
        position(-1e308, 0),
        position(-1e308, 1),
    ]
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["approach_position_m"] = position(1e308)
    report = run(case)
    point = metric_result(report)["timeline"][0]
    assert point["status"] == "invalid" and point["deviation"] is None
    assert point["grade"] is None and report["passed"] is None
    assert "nearest_route_point" not in point
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    "endpoint,actual",
    [
        (position(10, 0, 10), position(5, 0, 5)),
        (position(10, 10, 10), position(2, 2, 2)),
        (position(1, 1, 1), position(0.2, 0.2, 0.2)),
    ],
)
def test_exact_point_on_segment_passes_a_zero_radius_desired_corridor(case, endpoint, actual):
    parameter = case[1]["parameters"]["approach_position_m"]
    parameter["route_points"] = [position(), endpoint]
    parameter["desired"]["upper"] = 0
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["approach_position_m"] = actual
    report = run(case)
    point = metric_result(report)["timeline"][0]
    assert point["deviation"] == 0 and point["nearest_route_point"] == actual
    assert report["grade"] == "D"


def test_distinct_mixed_int_float_nodes_do_not_collapse_into_a_zero_length_segment(case):
    case[1]["parameters"]["approach_position_m"]["route_points"] = [
        position(9007199254740993),
        position(9007199254740992.0),
    ]
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["approach_position_m"] = position(9007199254740992)
    report = run(case)
    assert report["passed"] is True
    assert metric_result(report)["timeline"][0]["deviation"] == 0


def test_floating_collinearity_recheck_does_not_add_a_physical_tolerance(case):
    parameter = case[1]["parameters"]["approach_position_m"]
    parameter["route_points"] = [position(), position(10, 10, 10)]
    parameter["desired"]["upper"] = 0
    for frame in case[2]["items"]["flight"]["frames"]:
        frame["values"]["approach_position_m"] = position(2, 2, math.nextafter(2.0, math.inf))
    report = run(case)
    assert metric_result(report)["timeline"][0]["deviation"] > 0
    assert report["grade"] == "A"
