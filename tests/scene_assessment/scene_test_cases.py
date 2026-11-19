"""Small, deterministic scene inputs shared by inference contract tests."""

import copy

METHOD = "sequential_bayes_compensation_v1"
CPT = [[0.10, 0.25, 0.65], [0.35, 0.63, 0.02], [0.90, 0.099, 0.001]]


def make_case(grades="DDDDDDD AAU", *, second_grades=None):
    grades = grades.replace(" ", "")
    rows = [grades] if second_grades is None else [grades, second_grades]
    assert all(len(row) == len(grades) for row in rows)
    points = [
        {"checkpoint_id": f"cp{index}", "name": f"cp{index}", "metric_ids": [f"m{index}"]}
        for index in range(len(rows))
    ]
    metrics = [
        {
            "metric_id": f"m{index}",
            "name": f"m{index}",
            "input_kind": "frame",
            "comparison": "linear",
            "rule": "interval",
            "value_type": "number",
            "phase_ids": ["move"],
            "parameter_kind": "relative",
        }
        for index in range(len(rows))
    ]
    item = {
        "item_id": "flight",
        "name": "飞行",
        "assessment_kind": "flight",
        "phases": [
            {
                "phase_id": "move",
                "name": "move",
                "single_frame": False,
                "required_duration_s": None,
                "minimum_frame_count": 2,
            }
        ],
        "checkpoints": points,
    }
    identity = {"schema_version": "3.0", "scene_id": "DEMO-TEST"}
    catalog = {**identity, "items": [item], "metrics": metrics}
    configuration = {
        **identity,
        "parameters": {
            metric["metric_id"]: {
                "expected": 0,
                "desired": {"lower": -1, "upper": 1, "unbounded_upper": False},
                "acceptable": {"lower": -3, "upper": 3, "unbounded_upper": False},
            }
            for metric in metrics
        },
        "skill_models": {
            "flight": {
                "model_version": "supervisor-demo-2026-09-15-v1",
                "inference_method": METHOD,
                "calibration": "uncalibrated",
                "parameter_source": "demonstration",
                "prior": [1 / 3] * 3,
                "state_scores": [0, 50, 100],
                "checkpoint_models": {
                    point["checkpoint_id"]: {
                        "states": ["D", "A", "U"],
                        "probabilities": copy.deepcopy(CPT),
                    }
                    for point in points
                },
            }
        },
    }
    data = {
        **identity,
        "items": {
            "flight": {
                "frames": [
                    {
                        "timestamp_s": index,
                        "phase_id": "move",
                        "values": {
                            f"m{number}": {"D": 0, "A": 2, "U": 5}[row[index]]
                            for number, row in enumerate(rows)
                        },
                    }
                    for index in range(len(grades))
                ]
            }
        },
    }
    return catalog, configuration, data
