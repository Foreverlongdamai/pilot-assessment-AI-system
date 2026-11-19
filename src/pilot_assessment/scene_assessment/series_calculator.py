"""Signed raw-value grading and time evidence; no phase extraction or Bayesian guess."""

from __future__ import annotations

import copy
import math
from datetime import UTC, datetime
from typing import Any

from pilot_assessment.scene_assessment.series_validation import (
    document_issues,
    is_number,
    parameter_issues,
    sample_grid,
    validate_configuration,
    value_error,
)
from pilot_assessment.scene_assessment.validation import issue, object_issues


def _worst(grades):
    if "U" in grades:
        return "U"
    if not grades or None in grades:
        return None
    return "A" if "A" in grades else "D"


def _passed(grade):
    return None if grade is None else grade != "U"


def _inside(deviation, interval):
    return deviation >= interval["lower"] and (
        interval["unbounded_upper"] or deviation <= interval["upper"]
    )


def _metric(metric, value, parameter, *, not_required=False, blocked=False):
    result = {
        "metric_id": metric["metric_id"],
        "value": copy.deepcopy(value),
        "expected": None,
        "deviation": None,
        "grade": None,
        "status": "calculated",
        "reason": "",
        "parameter": copy.deepcopy(parameter),
        "timeline": [],
        "distribution": None,
        "episodes": [],
    }
    if isinstance(parameter, dict):
        result["expected"] = copy.deepcopy(parameter.get("expected"))
    if blocked:
        result.update(status="invalid", reason="文档或时间区间不合法，暂不计算此结果。")
    elif value is None:
        result.update(
            status="not_required" if not_required else "missing",
            reason="相关动作未发生，该缺值无需补齐。" if not_required else "缺少该检查点原始值。",
        )
    elif error := value_error(value, metric):
        result.update(status="invalid", reason=error)
    elif metric["rule"] == "must_be_true":
        result.update(grade="D" if value else "U", reason="已完成。" if value else "未完成。")
    elif metric["rule"] == "zero_events":
        result.update(
            grade="D" if value == 0 else "U",
            reason="未发生禁止事件。" if value == 0 else "发生禁止事件。",
        )
    elif parameter_issues(parameter, metric):
        result.update(status="invalid", reason="期望值或相对容差未配置完整或不合法。")
    else:
        expected = parameter["expected"]
        try:
            deviation = (
                (value % 360 - expected % 360 + 180) % 360 - 180
                if metric.get("comparison") == "angle_degrees"
                else value - expected
            )
        except OverflowError:
            deviation = float("inf")
        if not is_number(deviation):
            result.update(status="invalid", reason="偏差超出有限数值范围，无法计算。")
        else:
            grade = (
                "D"
                if _inside(deviation, parameter["desired"])
                else "A"
                if _inside(deviation, parameter["acceptable"])
                else "U"
            )
            result.update(deviation=deviation, grade=grade, reason=f"有符号偏差落在 {grade} 档。")
    return result


def _distribution(timeline):
    if not timeline:
        return None
    durations = {
        grade: math.fsum(
            point["end_s"] - point["start_s"] for point in timeline if point["grade"] == grade
        )
        for grade in ("D", "A", "U")
    }
    duration = math.fsum(durations.values())
    span = timeline[-1]["end_s"] - timeline[0]["start_s"]
    return {
        "duration_s": duration,
        "span_s": span,
        "gap_s": max(0, span - duration),
        "durations": durations,
        "proportions": {
            grade: elapsed / duration if duration else None for grade, elapsed in durations.items()
        },
    }


def _episodes(timeline):
    episodes = []
    for point in timeline:
        if point["grade"] not in {"A", "U"}:
            continue
        if (
            episodes
            and episodes[-1]["grade"] == point["grade"]
            and episodes[-1]["end_s"] == point["start_s"]
        ):
            previous = episodes[-1]
            previous["end_s"] = point["end_s"]
            previous["duration_s"] = previous["end_s"] - previous["start_s"]
            previous["max_abs_deviation"] = max(
                previous["max_abs_deviation"], abs(point["deviation"])
            )
        else:
            episodes.append(
                {
                    "start_s": point["start_s"],
                    "end_s": point["end_s"],
                    "grade": point["grade"],
                    "duration_s": point["end_s"] - point["start_s"],
                    "max_abs_deviation": abs(point["deviation"]),
                }
            )
    return episodes


def _series(metric, samples, parameter, *, not_required, blocked, has_gaps, path):
    result = _metric(metric, None, parameter, not_required=not_required, blocked=blocked)
    if not samples or blocked:
        return result, (
            [] if result["status"] == "not_required" else [issue(path, result["reason"])]
        )
    statuses, grades, timeline, issues = [], [], [], []
    for index, sample in enumerate(samples):
        value = sample["values"].get(metric["metric_id"])
        point = _metric(metric, value, parameter, not_required=not_required)
        statuses.append(point["status"])
        grades.append(point["grade"])
        timeline.append(
            {
                "start_s": sample["start_s"],
                "end_s": sample["end_s"],
                "value": point["value"],
                "expected": point["expected"],
                "deviation": point["deviation"],
                "grade": point["grade"],
            }
        )
        if point["status"] in {"missing", "invalid"}:
            issues.append(issue(f"{path}/{index}/values/{metric['metric_id']}", point["reason"]))
    status = (
        "invalid"
        if "invalid" in statuses
        else "missing"
        if "missing" in statuses or has_gaps
        else "not_required"
        if all(s == "not_required" for s in statuses)
        else "calculated"
    )
    grade = _worst(grades + ([None] if has_gaps else []))
    result.update(
        status=status,
        grade=grade,
        timeline=timeline,
        distribution=_distribution(timeline),
        episodes=_episodes(timeline),
        reason="逐区间计算有符号偏差与档位；有缺口时保留已知结果。"
        if status != "calculated"
        else "按已提供区间计算，规则档位取最差表现。",
    )
    return result, issues


def _condition(checkpoint, key, scalar_values, metrics):
    for condition in checkpoint.get(key, []):
        metric_id, expected = condition["metric_id"], condition["equals"]
        value = scalar_values.get(metric_id)
        if value is None or value_error(value, metrics[metric_id]):
            continue
        if type(expected) is bool:
            matches = type(value) is bool and value is expected
        else:
            matches = type(value) in {int, float} and value == expected
        if matches:
            return True
    return False


def _quantification(item, issues):
    checklist = item.get("assessment_kind") == "checklist"
    path = "/skill_models/" + item["item_id"]
    model_issues = [
        entry
        for entry in issues
        if entry["path"] in {"/skill_models", path} or entry["path"].startswith(path + "/")
    ]
    return {
        "status": "not_applicable"
        if checklist
        else "invalid_model"
        if model_issues
        else "pending_method",
        "skill_name": item.get("skill_name", item["name"]),
        "method": "not_applicable" if checklist else "pending",
        "model_version": None,
        "calibration": None,
        "parameter_source": None,
        "posterior": None,
        "score": None,
        "evidence_count": 0,
        "expected_evidence_count": len(item["checkpoints"]),
        "evidence": [],
        "warnings": [] if checklist else [entry["message"] for entry in model_issues],
        "message": (
            "检查单仅评价完成性，不推断操纵熟练度。"
            if checklist
            else "时间占比到贝叶斯后验及 item 过程算法尚未确定；保留规则与时间统计。"
        ),
    }


def evaluate(configuration: Any, input_data: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    issues = validate_configuration(configuration, catalog)["issues"]
    config_header = document_issues(configuration, "parameters", catalog)
    input_header = document_issues(input_data, "items", catalog)
    issues.extend({**entry, "path": "/input" + entry["path"]} for entry in input_header)
    blocked = bool(config_header or input_header)
    supplied_items = input_data.get("items", {}) if isinstance(input_data, dict) else {}
    supplied_items = supplied_items if isinstance(supplied_items, dict) else {}
    rows = configuration.get("parameters", {}) if isinstance(configuration, dict) else {}
    rows = rows if isinstance(rows, dict) else {}
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    issues.extend(
        object_issues(
            supplied_items, {item["item_id"] for item in catalog["items"]}, "/input/items"
        )
    )
    # Resolve scalar facts only at their declared owner. This supports an explicit
    # cross-checkpoint condition without searching or deriving any flight event.
    scalar_values = {}
    for item in catalog["items"]:
        raw_item = supplied_items.get(item["item_id"], {})
        points = raw_item.get("checkpoints", {}) if isinstance(raw_item, dict) else {}
        for point in item["checkpoints"]:
            raw_point = points.get(point["checkpoint_id"], {}) if isinstance(points, dict) else {}
            values = raw_point.get("values", {}) if isinstance(raw_point, dict) else {}
            if isinstance(values, dict):
                scalar_values.update(
                    {
                        key: values[key]
                        for key in point["metric_ids"]
                        if metrics[key]["input_kind"] == "scalar" and key in values
                    }
                )
    items = []
    for item in catalog["items"]:
        item_path = "/input/items/" + item["item_id"]
        raw_item = supplied_items.get(item["item_id"])
        issues.extend(object_issues(raw_item, {"checkpoints"}, item_path))
        points = raw_item.get("checkpoints") if isinstance(raw_item, dict) else None
        issues.extend(
            object_issues(
                points,
                {point["checkpoint_id"] for point in item["checkpoints"]},
                item_path + "/checkpoints",
            )
        )
        points = points if isinstance(points, dict) else {}
        checkpoints = []
        for checkpoint in item["checkpoints"]:
            point_path = item_path + "/checkpoints/" + checkpoint["checkpoint_id"]
            raw_point = points.get(checkpoint["checkpoint_id"])
            point_issues = object_issues(raw_point, {"values", "samples"}, point_path)
            raw_point = raw_point if isinstance(raw_point, dict) else {}
            scalar_ids = {
                key for key in checkpoint["metric_ids"] if metrics[key]["input_kind"] == "scalar"
            }
            series_ids = set(checkpoint["metric_ids"]) - scalar_ids
            values = raw_point.get("values")
            point_issues.extend(object_issues(values, scalar_ids, point_path + "/values"))
            values = values if isinstance(values, dict) else {}
            samples, grid_issues, valid_grid = sample_grid(
                raw_point.get("samples"), series_ids, point_path + "/samples"
            )
            if samples and not series_ids:
                grid_issues.append(
                    issue(
                        point_path + "/samples",
                        "此检查点只接收一次标量或检查单事实，不接收逐帧重复记录。",
                    )
                )
                valid_grid = False
            point_issues.extend(grid_issues)
            has_gaps = any(
                next_sample["start_s"] > sample["end_s"]
                for sample, next_sample in zip(samples, samples[1:], strict=False)
            )
            forced_fail = not blocked and _condition(
                checkpoint, "fail_when", scalar_values, metrics
            )
            not_required = forced_fail or (
                not blocked and _condition(checkpoint, "not_required_when", scalar_values, metrics)
            )
            result_metrics = []
            for key in checkpoint["metric_ids"]:
                if key in scalar_ids:
                    result = _metric(
                        metrics[key],
                        values.get(key),
                        rows.get(key),
                        not_required=not_required,
                        blocked=blocked,
                    )
                    if result["status"] in {"missing", "invalid"}:
                        point_issues.append(issue(point_path + "/values/" + key, result["reason"]))
                else:
                    result, metric_issues = _series(
                        metrics[key],
                        samples,
                        rows.get(key),
                        not_required=not_required,
                        blocked=blocked or not valid_grid,
                        has_gaps=has_gaps,
                        path=point_path + "/samples",
                    )
                    point_issues.extend(metric_issues)
                result_metrics.append(result)
            series_results = [
                result for result in result_metrics if result["metric_id"] in series_ids
            ]
            timeline = []
            if valid_grid and not blocked and series_results:
                timeline = [
                    {
                        "start_s": sample["start_s"],
                        "end_s": sample["end_s"],
                        "grade": _worst(
                            [result["timeline"][index]["grade"] for result in series_results]
                        ),
                    }
                    for index, sample in enumerate(samples)
                ]
            grade = "U" if forced_fail else _worst([result["grade"] for result in result_metrics])
            if point_issues and grade != "U":
                grade = None
            checkpoints.append(
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "name": checkpoint["name"],
                    "grade": grade,
                    "metrics": result_metrics,
                    "timeline": timeline,
                    "distribution": _distribution(timeline),
                }
            )
            issues.extend(point_issues)
        grade = _worst([point["grade"] for point in checkpoints])
        items.append(
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "grade": grade,
                "passed": _passed(grade),
                "checkpoints": checkpoints,
                "skill_quantification": _quantification(item, issues),
            }
        )
    issues = list({(entry["path"], entry["message"]): entry for entry in issues}.values())
    rule_issues = [
        entry
        for entry in issues
        if entry["path"] != "/skill_models" and not entry["path"].startswith("/skill_models/")
    ]
    grade = _worst([item["grade"] for item in items])
    if rule_issues and grade != "U":
        grade = None
    return {
        "schema_version": "2.0",
        "scene_id": catalog["scene_id"],
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "calculation_status": "needs_input" if rule_issues else "complete",
        "grade": grade,
        "passed": _passed(grade),
        "configuration": copy.deepcopy(configuration),
        "input": copy.deepcopy(input_data),
        "issues": issues,
        "items": items,
    }
