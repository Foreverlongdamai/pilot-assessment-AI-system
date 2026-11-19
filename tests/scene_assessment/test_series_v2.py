from __future__ import annotations

import copy

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration


@pytest.fixture
def case():
    metrics = [
        {
            "metric_id": key,
            "name": key,
            "input_kind": kind,
            "comparison": comparison,
            "value_type": value_type,
            "rule": rule,
            "parameter_kind": "signed",
        }
        for key, kind, comparison, value_type, rule in [
            ("height", "series", "linear", "number", "interval"),
            ("heading", "series", "angle_degrees", "number", "interval"),
            ("duration", "scalar", "linear", "number", "interval"),
            ("done", "scalar", "linear", "boolean", "must_be_true"),
        ]
    ]
    catalog = {
        "schema_version": "2.0",
        "scene_id": "TEST-SERIES",
        "metrics": metrics,
        "items": [
            {
                "item_id": "flight",
                "name": "飞行",
                "assessment_kind": "flight",
                "checkpoints": [
                    {
                        "checkpoint_id": "control",
                        "name": "控制",
                        "metric_ids": ["height", "heading"],
                    },
                    {
                        "checkpoint_id": "hold",
                        "name": "保持",
                        "metric_ids": ["duration"],
                        "fail_when": [{"metric_id": "duration", "equals": 0}],
                    },
                ],
            },
            {
                "item_id": "checklist",
                "name": "检查单",
                "assessment_kind": "checklist",
                "checkpoints": [
                    {"checkpoint_id": "prepared", "name": "准备", "metric_ids": ["done"]}
                ],
            },
        ],
    }

    def row(expected):
        return {
            "expected": expected,
            "desired": {"lower": -2, "upper": 2, "unbounded_upper": False},
            "acceptable": {"lower": -5, "upper": 5, "unbounded_upper": False},
        }

    configuration = {
        "schema_version": "2.0",
        "scene_id": "TEST-SERIES",
        "parameters": {"height": row(100), "heading": row(359), "duration": row(5)},
    }
    input_data = {
        "schema_version": "2.0",
        "scene_id": "TEST-SERIES",
        "items": {
            "flight": {
                "checkpoints": {
                    "control": {
                        "values": {},
                        "samples": [
                            {"start_s": 0, "end_s": 1, "values": {"height": 98, "heading": 1}},
                            {"start_s": 1, "end_s": 4, "values": {"height": 101, "heading": 358}},
                        ],
                    },
                    "hold": {"values": {"duration": 5}, "samples": []},
                }
            },
            "checklist": {"checkpoints": {"prepared": {"values": {"done": True}, "samples": []}}},
        },
    }
    return catalog, configuration, input_data


def run(case):
    return evaluate(case[1], case[2], catalog=case[0])


def control(case):
    return case[2]["items"]["flight"]["checkpoints"]["control"]


def result_metric(report, key):
    return next(
        metric
        for item in report["items"]
        for checkpoint in item["checkpoints"]
        for metric in checkpoint["metrics"]
        if metric["metric_id"] == key
    )


def draft_model():
    return {
        "model_version": "draft-v2",
        "calibration": "uncalibrated",
        "parameter_source": "unconfigured",
        "prior": [None, None, None],
        "state_scores": [None, None, None],
        "checkpoint_models": {
            key: {"states": ["D", "A", "U"], "probabilities": [[None] * 3 for _ in range(3)]}
            for key in ("control", "hold")
        },
    }


def test_raw_values_use_expected_and_keep_signed_offsets(case):
    assert validate_configuration(case[1], catalog=case[0])["valid"]
    report = run(case)
    assert report["grade"] == "D"
    height = result_metric(report, "height")
    assert [point["deviation"] for point in height["timeline"]] == [-2, 1]
    assert height["timeline"][0]["value"] == 98
    assert height["timeline"][0]["expected"] == 100
    case[1]["parameters"]["height"]["expected"] = 90
    assert run(case)["grade"] == "U"


@pytest.mark.parametrize(
    ("expected", "actual", "deviation"),
    [
        (359, 1, 2),
        (1, 359, -2),
        (0, 180, -180),
        (180, 0, -180),
        (720, 721, 1),
    ],
)
def test_heading_wrap_uses_fixed_half_open_convention(case, expected, actual, deviation):
    case[1]["parameters"]["heading"]["expected"] = expected
    control(case)["samples"][0]["values"]["heading"] = actual
    result = result_metric(run(case), "heading")
    assert result["timeline"][0]["deviation"] == deviation


def test_signed_asymmetric_closed_tolerances(case):
    row = case[1]["parameters"]["height"]
    row["desired"].update(lower=-1, upper=2)
    row["acceptable"].update(lower=-3, upper=5)
    control(case)["samples"] = [
        {"start_s": index, "end_s": index + 1, "values": {"height": value, "heading": 359}}
        for index, value in enumerate([99, 102, 97, 105, 96.9, 105.1])
    ]
    result = result_metric(run(case), "height")
    assert [point["grade"] for point in result["timeline"]] == ["D", "D", "A", "A", "U", "U"]


def test_duration_distribution_is_weighted_and_a_excludes_d(case):
    control(case)["samples"][0]["values"]["height"] = 100
    control(case)["samples"][1]["values"]["height"] = 104
    result = result_metric(run(case), "height")
    assert result["distribution"] == {
        "duration_s": 4,
        "span_s": 4,
        "gap_s": 0,
        "durations": {"D": 1, "A": 3, "U": 0},
        "proportions": {"D": 0.25, "A": 0.75, "U": 0},
    }
    assert result["episodes"] == [
        {"start_s": 1, "end_s": 4, "grade": "A", "duration_s": 3, "max_abs_deviation": 4}
    ]


def test_subdivision_preserves_distribution_and_merges_episodes(case):
    control(case)["samples"] = [
        {"start_s": 0, "end_s": 4, "values": {"height": 104, "heading": 359}}
    ]
    before = result_metric(run(case), "height")
    control(case)["samples"] = [
        {"start_s": index, "end_s": index + 1, "values": {"height": 104, "heading": 359}}
        for index in range(4)
    ]
    after = result_metric(run(case), "height")
    assert after["distribution"] == before["distribution"]
    assert after["episodes"] == before["episodes"]


def test_gap_is_missing_coverage_not_interpolated(case):
    control(case)["samples"][1].update(start_s=2, end_s=4)
    report = run(case)
    result = result_metric(report, "height")
    assert result["distribution"]["gap_s"] == 1
    assert result["distribution"]["duration_s"] == 3
    assert len(result["timeline"]) == 2
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None
    assert report["issues"]


@pytest.mark.parametrize(
    ("start", "end"),
    [(0.5, 4), (-1, 0), (1, 1), (4, 3), (float("nan"), 4), (1, float("inf")), (True, 4)],
)
def test_invalid_sample_grid_is_rejected_without_sorting(case, start, end):
    control(case)["samples"][1].update(start_s=start, end_s=end)
    report = run(case)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None
    assert report["issues"]


def test_partial_u_retained_while_missing_value_time_is_not_counted(case):
    control(case)["samples"][0]["values"]["height"] = 110
    control(case)["samples"][1]["values"]["height"] = None
    report = run(case)
    result = result_metric(report, "height")
    assert report["grade"] == "U" and report["passed"] is False
    assert report["calculation_status"] == "needs_input"
    assert result["distribution"]["durations"]["U"] == 1
    assert result["distribution"]["gap_s"] == 3


def test_composite_checkpoint_uses_common_grid_without_repeating_scalar_facts(case):
    control(case)["samples"][0]["values"].update(height=100, heading=3)
    control(case)["samples"][1]["values"].update(height=110, heading=359)
    report = run(case)
    point = report["items"][0]["checkpoints"][0]
    assert point["timeline"] == [
        {"start_s": 0, "end_s": 1, "grade": "A"},
        {"start_s": 1, "end_s": 4, "grade": "U"},
    ]
    assert report["items"][1]["checkpoints"][0]["timeline"] == []
    assert result_metric(report, "done")["timeline"] == []


@pytest.mark.parametrize(
    ("value", "grade", "status"),
    [
        (True, "D", "calculated"),
        (False, "U", "calculated"),
        (None, None, "missing"),
        (1, None, "invalid"),
        ("true", None, "invalid"),
    ],
)
def test_checklist_boolean_is_not_numeric_or_probabilistic(case, value, grade, status):
    case[2]["items"]["checklist"]["checkpoints"]["prepared"]["values"]["done"] = value
    report = run(case)
    result = result_metric(report, "done")
    assert result["grade"] == grade and result["status"] == status
    assert result["expected"] is None and result["deviation"] is None
    assert report["items"][1]["skill_quantification"]["status"] == "not_applicable"


def test_checklist_missing_key_is_required(case):
    del case[2]["items"]["checklist"]["checkpoints"]["prepared"]["values"]["done"]
    assert result_metric(run(case), "done")["status"] == "missing"


def test_draft_models_do_not_block_rules_or_invent_quantification(case):
    case[1]["skill_models"] = {"flight": draft_model()}
    report = run(case)
    assert report["grade"] == "D"
    assert report["calculation_status"] == "complete"
    skill = report["items"][0]["skill_quantification"]
    assert skill["status"] == "pending_method"
    assert skill["posterior"] is None and skill["score"] is None


@pytest.mark.parametrize("where", ["items", "checkpoint", "series", "scalar"])
def test_unknown_nested_values_are_not_silently_ignored(case, where):
    if where == "items":
        case[2]["items"]["typo"] = {"checkpoints": {}}
    elif where == "checkpoint":
        case[2]["items"]["flight"]["checkpoints"]["typo"] = {"values": {}, "samples": []}
    elif where == "series":
        control(case)["samples"][0]["values"]["typo"] = 4
    else:
        control(case)["values"]["height"] = 100
    report = run(case)
    assert report["calculation_status"] == "needs_input" and report["passed"] is None
    assert report["issues"]


def test_snapshots_and_all_timeline_samples_are_detached(case):
    before = copy.deepcopy(case)
    report = run(case)
    control(case)["samples"][0]["values"]["height"] = 999
    case[1]["parameters"]["height"]["expected"] = 0
    assert report["input"] == before[2] and report["configuration"] == before[1]
    assert result_metric(report, "height")["timeline"][0]["value"] == 98


def test_relative_tolerance_validation_contains_zero_but_not_raw_expected(case):
    assert validate_configuration(case[1], catalog=case[0])["valid"]
    case[1]["parameters"]["height"]["desired"]["lower"] = 1
    assert not validate_configuration(case[1], catalog=case[0])["valid"]


def test_wrong_version_is_not_silently_reinterpreted(case):
    case[2]["schema_version"] = "1.0"
    report = run(case)
    assert report["passed"] is None and report["issues"]


def test_all_missing_samples_have_unknown_proportions(case):
    for sample in control(case)["samples"]:
        sample["values"]["height"] = None
    result = result_metric(run(case), "height")
    assert result["distribution"]["duration_s"] == 0
    assert result["distribution"]["gap_s"] == 4
    assert result["distribution"]["proportions"] == {"D": None, "A": None, "U": None}


def test_episode_does_not_cross_missing_time_or_unclassified_values(case):
    control(case)["samples"] = [
        {"start_s": 0, "end_s": 1, "values": {"height": 104, "heading": 359}},
        {"start_s": 1, "end_s": 2, "values": {"height": None, "heading": 359}},
        {"start_s": 2, "end_s": 3, "values": {"height": 104, "heading": 359}},
        {"start_s": 4, "end_s": 5, "values": {"height": 104, "heading": 359}},
    ]
    episodes = result_metric(run(case), "height")["episodes"]
    assert [(episode["start_s"], episode["end_s"]) for episode in episodes] == [
        (0, 1),
        (2, 3),
        (4, 5),
    ]


def test_unrepresentable_integer_timestamps_report_invalid_instead_of_crashing(case):
    control(case)["samples"] = [
        {"start_s": 0, "end_s": 10**400, "values": {"height": 100, "heading": 359}}
    ]
    report = run(case)
    assert report["calculation_status"] == "needs_input"
    assert report["passed"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda models: models.update(UNKNOWN={"garbage": True}),
        lambda models: models.update(checklist=draft_model()),
        lambda models: models["flight"].update(prior=[-1, 2, 0]),
        lambda models: models["flight"].update(prior=[0.6, None, 0.5]),
        lambda models: models["flight"].update(prior=[0.2, 0.3, 0.4]),
        lambda models: models["flight"].update(prior=[True, None, None]),
        lambda models: models["flight"].update(prior=[float("inf"), None, None]),
        lambda models: models["flight"].update(state_scores=[90, None, 20]),
        lambda models: models["flight"].update(state_scores=[0, None, 101]),
        lambda models: models["flight"].update(state_scores=[50, None, 50]),
        lambda models: models["flight"].update(garbage=True),
        lambda models: models["flight"]["checkpoint_models"].update(UNKNOWN={}),
        lambda models: models["flight"]["checkpoint_models"]["control"].update(
            states=["A", "D", "U"]
        ),
        lambda models: models["flight"]["checkpoint_models"]["control"][
            "probabilities"
        ].__setitem__(0, [1.1, None, None]),
        lambda models: models["flight"]["checkpoint_models"]["control"][
            "probabilities"
        ].__setitem__(0, [0.5, 0.5, 0.5]),
        lambda models: models.update(flight={}),
    ],
)
def test_invalid_filled_models_report_issues_without_changing_rules(case, change):
    case[1]["skill_models"] = {"flight": draft_model()}
    change(case[1]["skill_models"])
    validation = validate_configuration(case[1], catalog=case[0])
    assert not validation["valid"]
    assert all(entry["path"].startswith("/skill_models") for entry in validation["issues"])
    report = run(case)
    assert report["grade"] == "D" and report["passed"] is True
    assert report["calculation_status"] == "complete"
    assert report["issues"]
    assert report["items"][0]["skill_quantification"]["score"] is None
    assert report["items"][1]["skill_quantification"]["status"] == "not_applicable"


def test_partly_filled_valid_model_cells_are_drafts(case):
    model = draft_model()
    model["prior"] = [0.3, None, 0.2]
    model["state_scores"] = [0, None, 100]
    model["checkpoint_models"]["control"]["probabilities"][0] = [0.2, None, 0.5]
    case[1]["skill_models"] = {"flight": model}
    assert validate_configuration(case[1], catalog=case[0])["valid"]
    report = run(case)
    assert report["items"][0]["skill_quantification"]["status"] == "pending_method"
    assert report["grade"] == "D"


@pytest.mark.parametrize("value", [[], {}, True])
def test_bad_model_source_type_returns_issues_instead_of_crashing(case, value):
    model = draft_model()
    model["parameter_source"] = value
    case[1]["skill_models"] = {"flight": model}
    validation = validate_configuration(case[1], catalog=case[0])
    assert not validation["valid"]
    assert run(case)["grade"] == "D"
