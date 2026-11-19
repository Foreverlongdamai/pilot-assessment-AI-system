from __future__ import annotations

import copy
import importlib
import importlib.util

import pytest


def api():
    name = "pilot_assessment.scene_assessment.calculator"
    try:
        available = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        available = None
    assert available is not None, "The independent scene calculator must be implemented"
    return importlib.import_module(name)


@pytest.fixture
def case():
    metrics = [
        ("gaze", "gaze", "number", "interval"),
        ("error", "error", "number", "interval"),
        ("hold", "hold", "number", "interval"),
        ("signed", "signed", "number", "interval"),
        ("duration", "duration", "number", "interval"),
        ("started", "fact", "boolean", "must_be_true"),
        ("events", "fact", "integer", "zero_events"),
    ]
    catalog = {
        "schema_version": "1.0",
        "scene_id": "SCN-001",
        "metrics": [
            {
                "metric_id": key,
                "name": key,
                "parameter_kind": kind,
                "value_type": value_type,
                "rule": rule,
                "shared": key == "hold",
            }
            for key, kind, value_type, rule in metrics
        ],
        "items": [
            {
                "item_id": "one",
                "name": "第一项",
                "checkpoints": [
                    {
                        "checkpoint_id": "one.hold",
                        "name": "保持",
                        "metric_ids": ["hold", "error"],
                        "fail_when": [{"metric_id": "hold", "equals": 0}],
                    },
                    {"checkpoint_id": "one.gaze", "name": "注视", "metric_ids": ["gaze"]},
                ],
            },
            {
                "item_id": "two",
                "name": "第二项",
                "checkpoints": [
                    {
                        "checkpoint_id": "two.action",
                        "name": "动作",
                        "metric_ids": ["started", "signed", "duration"],
                        "fail_when": [{"metric_id": "started", "equals": False}],
                    },
                    {
                        "checkpoint_id": "two.shared",
                        "name": "共享保持",
                        "metric_ids": ["hold", "events"],
                        "fail_when": [{"metric_id": "hold", "equals": 0}],
                    },
                ],
            },
        ],
    }

    def row(expected, dl, du, al, au):
        return {
            "expected": expected,
            "desired": {"lower": dl, "upper": du, "unbounded_upper": du is None},
            "acceptable": {"lower": al, "upper": au, "unbounded_upper": au is None},
        }

    configuration = {
        "schema_version": "1.0",
        "scene_id": "SCN-001",
        "parameters": {
            "gaze": row(3, 2, 4, 1, 5),
            "error": row(0, 0, 1, 0, 2),
            "hold": row(5, 4, None, 2, None),
            "signed": row(0, -1, 1, -2, 2),
            "duration": row(3, 2, 4, 1, 5),
        },
    }
    input_data = {
        "schema_version": "1.0",
        "scene_id": "SCN-001",
        "results": {
            "gaze": 3,
            "error": 0.5,
            "hold": 5,
            "signed": 0,
            "duration": 3,
            "started": True,
            "events": 0,
        },
    }
    return catalog, configuration, input_data


def run(case):
    catalog, configuration, input_data = case
    return api().evaluate(configuration, input_data, catalog=catalog)


def metric(report, metric_id):
    return next(
        m
        for item in report["items"]
        for point in item["checkpoints"]
        for m in point["metrics"]
        if m["metric_id"] == metric_id
    )


@pytest.mark.parametrize(
    ("value", "grade"), [(0, "D"), (1, "D"), (1.5, "A"), (2, "A"), (2.00001, "U")]
)
def test_closed_boundaries_and_worst_grade(case, value, grade):
    case[2]["results"]["error"] = value
    report = run(case)
    assert report["grade"] == grade
    assert report["passed"] is (grade != "U")
    assert report["calculation_status"] == "complete"


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf"), -0.1])
def test_invalid_numeric_result_is_not_pilot_failure(case, value):
    case[2]["results"]["error"] = value
    report = run(case)
    assert report["grade"] is None
    assert metric(report, "error")["status"] == "invalid"
    assert report["calculation_status"] == "needs_input"
    assert report["issues"]


@pytest.mark.parametrize("value", [True, 1.0, 0.5, -1, "0"])
def test_event_count_is_strict_nonnegative_integer(case, value):
    case[2]["results"]["events"] = value
    assert metric(run(case), "events")["status"] == "invalid"


def test_missing_result_is_not_zero_or_pass(case):
    del case[2]["results"]["error"]
    report = run(case)
    assert report["grade"] is None
    assert report["passed"] is None
    assert metric(report, "error")["status"] == "missing"


def test_known_zero_short_circuits_nonexistent_results_and_is_shared(case):
    case[2]["results"].update(hold=0, error=None)
    report = run(case)
    assert report["grade"] == "U"
    assert report["passed"] is False
    assert report["calculation_status"] == "complete"
    assert metric(report, "error")["status"] == "not_required"
    assert [item["grade"] for item in report["items"]] == ["U", "U"]


def test_false_short_circuits_but_missing_does_not(case):
    case[2]["results"].update(started=False, signed=None, duration=None)
    report = run(case)
    assert report["grade"] == "U"
    assert metric(report, "signed")["status"] == "not_required"
    case[2]["results"]["started"] = None
    assert run(case)["grade"] is None


def test_known_failure_survives_other_missing_data(case):
    case[2]["results"].update(events=1, gaze=None)
    report = run(case)
    assert report["grade"] == "U"
    assert report["passed"] is False
    assert report["calculation_status"] == "needs_input"


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p["error"]["acceptable"].update(upper=1),
        lambda p: p["error"]["desired"].update(upper=3),
        lambda p: p["error"].update(expected=0.5),
        lambda p: p["error"]["desired"].update(lower=-1),
        lambda p: p["gaze"]["acceptable"].update(lower=0),
        lambda p: p["hold"]["desired"].update(lower=2),
        lambda p: p["signed"]["desired"].update(lower=0.1),
        lambda p: p["duration"]["acceptable"].update(lower=-1),
        lambda p: p["gaze"].update(expected=6),
        lambda p: p["error"]["desired"].update(upper=None),
        lambda p: p["error"]["desired"].update(upper=float("inf")),
        lambda p: p["error"]["desired"].update(upper=True),
        lambda p: p["hold"]["desired"].update(upper=10),
        lambda p: p["error"].update(typo=1),
        lambda p: p.update(unknown={}),
    ],
)
def test_configuration_rejects_invalid_or_ambiguous_ranges(case, change):
    catalog, configuration, _ = case
    change(configuration["parameters"])
    validation = api().validate_configuration(configuration, catalog=catalog)
    assert not validation["valid"]
    assert validation["issues"]
    assert run(case)["grade"] is None


def test_missing_configuration_can_be_saved_but_cannot_pass(case):
    case[1]["parameters"]["gaze"]["expected"] = None
    assert not api().validate_configuration(case[1], catalog=case[0])["valid"]
    assert run(case)["grade"] is None


@pytest.mark.parametrize("target", [1, 2])
def test_wrong_scene_or_unknown_top_level_fields_are_reported(case, target):
    case[target]["scene_id"] = "OTHER"
    case[target]["unexpected"] = 1
    report = run(case)
    assert report["grade"] is None
    assert len(report["issues"]) >= 2


def test_unknown_result_not_silently_ignored(case):
    case[2]["results"]["typo"] = 1
    report = run(case)
    assert report["grade"] is None
    assert any("typo" in issue["path"] for issue in report["issues"])


def test_result_snapshots_and_metric_parameters_are_detached(case):
    before = copy.deepcopy(case)
    report = run(case)
    case[1]["parameters"]["error"]["desired"]["upper"] = 100
    case[2]["results"]["error"] = 100
    assert report["configuration"] == before[1]
    assert report["input"] == before[2]
    assert metric(report, "error")["parameter"] == before[1]["parameters"]["error"]


def test_actual_duration_must_be_positive(case):
    case[2]["results"]["duration"] = 0
    assert metric(run(case), "duration")["status"] == "invalid"
