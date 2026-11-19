from __future__ import annotations

import copy

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration


def phase(key, *, single=False, duration=None):
    return {"phase_id": key, "name": key, "single_frame": single, "required_duration_s": duration}


def parameter(expected):
    return {
        "expected": expected,
        "desired": {"lower": -1, "upper": 1, "unbounded_upper": False},
        "acceptable": {"lower": -3, "upper": 3, "unbounded_upper": False},
    }


@pytest.fixture
def case():
    def metric(key, phases, comparison="linear", rule="interval"):
        return {
            "metric_id": key,
            "name": key,
            "input_kind": "frame",
            "comparison": comparison,
            "rule": rule,
            "value_type": "boolean" if rule == "must_be_true" else "number",
            "phase_ids": phases,
            "parameter_kind": "relative",
        }

    def point(key, keys):
        return {"checkpoint_id": key, "name": key, "metric_ids": keys}

    def frame(time, phase_id, **values):
        return {"timestamp_s": time, "phase_id": phase_id, "values": values}

    metrics = [
        metric("heading", ["move", "stop"], "angle_degrees"),
        metric("endpoint", ["stop"]),
        metric("low", ["lower_1", "lower_2"]),
        metric("high", ["upper_1", "upper_2"]),
        metric("laser", ["lower_1", "upper_1", "lower_2", "upper_2"], "radial"),
        metric("ready", ["check"], rule="must_be_true"),
    ]
    hover_phases = [phase(key, duration=5) for key in ["lower_1", "upper_1", "lower_2", "upper_2"]]
    catalog = {
        "schema_version": "3.0",
        "scene_id": "TEST-FRAMES",
        "metrics": metrics,
        "items": [
            {
                "item_id": "flight",
                "name": "飞行",
                "assessment_kind": "flight",
                "phases": [phase("move"), phase("stop", single=True)],
                "checkpoints": [point("direction", ["heading"]), point("arrival", ["endpoint"])],
            },
            {
                "item_id": "hover",
                "name": "悬停",
                "assessment_kind": "flight",
                "phases": hover_phases,
                "checkpoints": [point("height", ["low", "high"]), point("aim", ["laser"])],
            },
            {
                "item_id": "checklist",
                "name": "检查单",
                "assessment_kind": "checklist",
                "phases": [phase("check", single=True)],
                "checkpoints": [point("prepared", ["ready"])],
            },
        ],
    }
    parameters = {
        "heading": parameter(359),
        "endpoint": parameter(100),
        "low": parameter(10),
        "high": parameter(20),
        "laser": {
            "expected": 0,
            "center_u": 0,
            "center_v": 0,
            "target_radius": 5,
            "desired": {"lower": 0, "upper": 1, "unbounded_upper": False},
            "acceptable": {"lower": 0, "upper": 3, "unbounded_upper": False},
        },
    }
    identity = {"schema_version": "3.0", "scene_id": "TEST-FRAMES"}
    inputs = {
        **identity,
        "items": {
            "flight": {
                "frames": [
                    frame(0, "move", heading=359),
                    frame(3, "move", heading=0),
                    frame(10, "stop", heading=359, endpoint=100),
                ]
            },
            "hover": {
                "frames": [
                    frame(
                        index * 10 + delta,
                        key,
                        **{
                            "low" if key.startswith("lower") else "high": 10
                            if key.startswith("lower")
                            else 20,
                            "laser": {"status": "hit", "u_m": 0, "v_m": 0},
                        },
                    )
                    for index, key in enumerate([p["phase_id"] for p in hover_phases])
                    for delta in (0, 5)
                ]
            },
            "checklist": {"frames": [frame(0, "check", ready=True)]},
        },
    }
    return catalog, {**identity, "parameters": parameters}, inputs


def run(case):
    return evaluate(case[1], case[2], catalog=case[0])


def item(report, key="flight"):
    return next(value for value in report["items"] if value["item_id"] == key)


def result_metric(report, key):
    return next(
        metric
        for value in report["items"]
        for point in value["checkpoints"]
        for metric in point["metrics"]
        if metric["metric_id"] == key
    )


def frames(case, key="flight"):
    return case[2]["items"][key]["frames"]


def test_v3_exact_frames_use_signed_expected_and_heading(case):
    assert validate_configuration(case[1], catalog=case[0])["valid"]
    report = run(case)
    assert report["schema_version"] == "3.0"
    assert report["grade"] == "D" and report["passed"] is True
    heading = result_metric(report, "heading")
    assert [p["deviation"] for p in heading["timeline"]] == [0, 1, 0]
    assert [p["timestamp_s"] for p in heading["timeline"]] == [0, 3, 10]
    assert [p["frame_index"] for p in heading["timeline"]] == [0, 1, 2]
    assert "distribution" not in heading and "episodes" not in heading
    assert all("start_s" not in p and "end_s" not in p for p in heading["timeline"])


def test_frame_distribution_counts_unequal_timestamps_without_duration_weighting(case):
    frames(case)[1]["values"]["heading"] = 1
    frames(case)[2]["values"]["heading"] = 10
    report = run(case)
    result = result_metric(report, "heading")
    assert result["frame_distribution"] == {
        "counts": {"D": 1, "A": 1, "U": 1},
        "proportions": {"D": 1 / 3, "A": 1 / 3, "U": 1 / 3},
        "valid_frame_count": 3,
        "missing_frame_count": 0,
        "total_frame_count": 3,
    }
    assert item(report)["grade"] == "U" and item(report)["passed"] is False


def test_phase_specific_targets_and_terminal_only_metrics(case):
    report = run(case)
    assert len(result_metric(report, "endpoint")["timeline"]) == 1
    assert result_metric(report, "endpoint")["timeline"][0]["frame_index"] == 2
    assert [p["phase_id"] for p in result_metric(report, "low")["timeline"]] == ["lower_1"] * 2 + [
        "lower_2"
    ] * 2
    assert len(item(report, "hover")["phase_results"]) == 4
    assert all(
        p["observed_span_s"] == 5 and p["required_duration_s"] == 5
        for p in item(report, "hover")["phase_results"]
    )


@pytest.mark.parametrize(("value", "grade"), [(0, "D"), (1, "D"), (2, "A"), (3, "A"), (4, "U")])
def test_radial_closed_boundaries(case, value, grade):
    frames(case, "hover")[0]["values"]["laser"]["u_m"] = value
    point = result_metric(run(case), "laser")["timeline"][0]
    assert point["grade"] == grade and point["deviation"] == value
    assert point["value"]["u_m"] == value


@pytest.mark.parametrize(
    ("value", "grade", "status"),
    [
        ({"status": "miss", "u_m": None, "v_m": None}, "U", "calculated"),
        (None, None, "missing"),
        ({"status": "unavailable", "u_m": None, "v_m": None}, None, "missing"),
        ({"status": "hit", "u_m": True, "v_m": 0}, None, "invalid"),
    ],
)
def test_radial_miss_is_distinct_from_missing(case, value, grade, status):
    frames(case, "hover")[0]["values"]["laser"] = value
    point = result_metric(run(case), "laser")["timeline"][0]
    assert point["grade"] == grade and point["status"] == status


def test_known_u_survives_missing_data_and_missing_configuration(case):
    frames(case)[0]["values"]["heading"] = 20
    frames(case)[1]["values"]["heading"] = None
    case[1]["parameters"]["endpoint"]["expected"] = None
    report = run(case)
    assert item(report)["grade"] == "U" and item(report)["passed"] is False
    assert report["calculation_status"] == "needs_input"
    assert result_metric(report, "heading")["frame_distribution"]["missing_frame_count"] == 1


def test_all_missing_frames_have_null_grade_and_proportions(case):
    for frame in frames(case):
        frame["values"]["heading"] = None
    result = result_metric(run(case), "heading")
    assert result["grade"] is None
    assert result["frame_distribution"]["proportions"] == {"D": None, "A": None, "U": None}
    assert run(case)["passed"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda c: frames(c).pop(),
        lambda c: frames(c).append(copy.deepcopy(frames(c)[-1]) | {"timestamp_s": 11}),
        lambda c: frames(c)[1].update(timestamp_s=0),
        lambda c: frames(c)[1].update(timestamp_s=-1),
        lambda c: frames(c)[1].update(timestamp_s=True),
        lambda c: frames(c)[1].update(timestamp_s=float("nan")),
        lambda c: frames(c)[1].update(timestamp_s=10**400),
        lambda c: frames(c)[1].update(phase_id="unknown"),
        lambda c: frames(c)[-1].update(phase_id="move"),
        lambda c: frames(c)[0]["values"].update(endpoint=100),
        lambda c: frames(c, "hover")[3].update(phase_id="lower_1"),
        lambda c: frames(c, "hover")[1].update(timestamp_s=3),
    ],
)
def test_invalid_or_incomplete_frames_cannot_pass(case, change):
    change(case)
    report = run(case)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is not True
    assert report["issues"]


def test_controls_are_explanatory_and_snapshots_are_detached(case):
    controls = {"Pilot Lon": -100, "Pilot Lat": 87, "Pilot Yaw": 40, "Pilot Heave": -34}
    frames(case)[0]["controls"] = controls
    report = run(case)
    assert report["passed"] is True
    assert report["input"]["items"]["flight"]["frames"][0]["controls"] == controls
    controls["Pilot Lat"] = 999
    case[1]["parameters"]["heading"]["expected"] = 123
    assert report["input"]["items"]["flight"]["frames"][0]["controls"]["Pilot Lat"] == 87
    assert result_metric(report, "heading")["parameter"]["expected"] == 359


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_checklist_requires_boolean(case, value):
    frames(case, "checklist")[0]["values"]["ready"] = value
    assert run(case)["passed"] is None


def test_checklist_false_is_definite_failure_without_bayesian_score(case):
    frames(case, "checklist")[0]["values"]["ready"] = False
    report = run(case)
    assert report["passed"] is False
    assert item(report, "checklist")["skill_quantification"]["status"] == "not_applicable"
    assert item(report)["skill_quantification"]["status"] == "not_configured"
    assert item(report)["skill_quantification"]["score"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(expected=1),
        lambda p: p.update(center_u=None),
        lambda p: p.update(target_radius=3),
        lambda p: p["desired"].update(lower=-1),
        lambda p: p["acceptable"].update(unbounded_upper=True),
        lambda p: p["desired"].update(upper=3),
    ],
)
def test_radial_parameters_require_real_geometry(case, change):
    change(case[1]["parameters"]["laser"])
    assert not validate_configuration(case[1], catalog=case[0])["valid"]
    assert run(case)["passed"] is not True


def test_empty_radial_template_is_missing_not_definite_failure(case):
    frames(case, "hover")[0]["values"]["laser"] = {"status": None, "u_m": None, "v_m": None}
    result = result_metric(run(case), "laser")
    assert result["timeline"][0]["status"] == "missing"
    assert result["grade"] is None


def test_first_timestamp_cannot_precede_simulation_clock_origin(case):
    frames(case)[0]["timestamp_s"] = -0.01
    report = run(case)
    assert report["calculation_status"] == "needs_input"
    assert item(report)["passed"] is None
    assert any(i["path"].endswith("/frames/0/timestamp_s") for i in report["issues"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 10**400, "100", None])
def test_invalid_parameter_cannot_remove_independent_definite_u(case, value):
    case[1]["parameters"]["endpoint"]["expected"] = value
    frames(case)[0]["values"]["heading"] = 20
    report = run(case)
    assert not validate_configuration(case[1], catalog=case[0])["valid"]
    assert report["calculation_status"] == "needs_input"
    assert item(report)["grade"] == "U" and report["passed"] is False


def test_radial_miss_remains_known_u_when_geometry_is_unconfigured(case):
    case[1]["parameters"]["laser"]["center_u"] = None
    frames(case, "hover")[0]["values"]["laser"] = {"status": "miss", "u_m": None, "v_m": None}
    report = run(case)
    assert result_metric(report, "laser")["timeline"][0]["grade"] == "U"
    assert report["grade"] == "U" and report["calculation_status"] == "needs_input"


def test_missing_required_phase_does_not_erase_u_from_present_phase(case):
    frames(case, "hover")[0]["values"]["low"] = 100
    frames(case, "hover")[:] = [p for p in frames(case, "hover") if p["phase_id"] != "upper_2"]
    report = run(case)
    assert item(report, "hover")["grade"] == "U"
    assert item(report, "hover")["phase_results"][-1]["grade"] is None
    assert report["calculation_status"] == "needs_input"


def test_empty_frames_have_no_invented_count_or_grade(case):
    frames(case)[:] = []
    result = item(run(case))
    assert result["grade"] is None and result["passed"] is None
    assert result["frame_distribution"]["total_frame_count"] == 0
    assert result["frame_distribution"]["proportions"] == {"D": None, "A": None, "U": None}


def test_unobserved_interior_does_not_become_weighted_time_evidence(case):
    result = item(run(case), "hover")["phase_results"][0]
    assert result["observed_span_s"] == 5
    assert result["frame_distribution"]["total_frame_count"] == 2
    assert result["coverage_note"]
    assert "duration_s" not in result["frame_distribution"]


def test_invalid_model_is_reported_independently_from_frame_rules(case):
    case[1]["skill_models"] = {"flight": {"prior": [-1, 2, 0]}}
    assert not validate_configuration(case[1], catalog=case[0])["valid"]
    report = run(case)
    assert report["passed"] is True and report["calculation_status"] == "complete"
    quantification = item(report)["skill_quantification"]
    assert quantification["status"] == "invalid_model"
    assert quantification["warnings"] and quantification["score"] is None


def test_runtime_default_is_v3_while_legacy_capabilities_remain():
    import io
    import json

    from pilot_assessment.scene_assessment.server import serve

    requests = [
        ("runtime.hello", {"supported_protocols": ["1.0"]}),
        ("scene.catalog", {}),
        ("scene.catalog", {"schema_version": "2.0"}),
        ("scene.catalog", {"schema_version": "1.0"}),
    ]
    data = "".join(
        json.dumps({"jsonrpc": "2.0", "id": index, "method": method, "params": params}) + "\n"
        for index, (method, params) in enumerate(requests)
    )
    output = io.BytesIO()
    assert serve(io.BytesIO(data.encode()), output) == 0
    responses = [json.loads(line)["result"] for line in output.getvalue().splitlines()]
    assert {"scene.assessment.v1", "scene.assessment.v2", "scene.assessment.v3"} <= set(
        responses[0]["capabilities"]
    )
    assert [r["schema_version"] for r in responses[1:]] == ["3.0", "2.0", "1.0"]
