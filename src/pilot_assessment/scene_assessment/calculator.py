"""Pure interval evaluation of precomputed scene results, without old pipelines."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from pilot_assessment.scene_assessment.catalog import (
    UnsupportedSceneError,
    catalog_for_configuration,
)
from pilot_assessment.scene_assessment.configuration import normalize_configuration
from pilot_assessment.scene_assessment.validation import (
    document_issues,
    issue,
    object_issues,
    parameter_issues,
    value_error,
)


def validate_configuration(
    configuration: Any,
    *,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        definition = catalog if catalog is not None else catalog_for_configuration(configuration)
    except UnsupportedSceneError as error:
        return {"valid": False, "issues": [issue(getattr(error, "path", "/scene_id"), str(error))]}
    configuration = normalize_configuration(configuration, definition)
    if definition.get("schema_version") == "3.0":
        from pilot_assessment.scene_assessment.frame_validation import (
            validate_configuration as validate_v3,
        )

        return validate_v3(configuration, definition)
    if definition.get("schema_version") == "2.0":
        from pilot_assessment.scene_assessment.series_validation import (
            validate_configuration as validate_v2,
        )

        return validate_v2(configuration, definition)
    issues = document_issues(configuration, "parameters", definition)
    rows = configuration.get("parameters") if isinstance(configuration, dict) else None
    if isinstance(rows, dict):
        metrics = [m for m in definition["metrics"] if m["rule"] == "interval"]
        issues.extend(object_issues(rows, {m["metric_id"] for m in metrics}, "/parameters"))
        for metric in metrics:
            issues.extend(parameter_issues(rows.get(metric["metric_id"]), metric))
    return {"valid": not issues, "issues": issues}


def _worst(grades: list[str | None]) -> str | None:
    if "U" in grades:
        return "U"
    if not grades or None in grades:
        return None
    return "A" if "A" in grades else "D"


def _passed(grade: str | None) -> bool | None:
    return None if grade is None else grade != "U"


def _inside(value: Any, interval: dict[str, Any]) -> bool:
    return interval["lower"] <= value and (
        interval["unbounded_upper"] or value <= interval["upper"]
    )


def _metric_result(metric, value, parameter, *, short_circuit, blocked):
    result = {
        "metric_id": metric["metric_id"],
        "value": copy.deepcopy(value),
        "grade": None,
        "status": "calculated",
        "reason": "",
        "parameter": copy.deepcopy(parameter),
    }
    if blocked:
        result.update(status="invalid", reason="场景或文档结构不合法，暂不计算此结果。")
    elif value is None:
        result.update(
            status="not_required" if short_circuit else "missing",
            reason=(
                "已知相关动作未发生，该缺失结果无需提供或补零。"
                if short_circuit
                else "结果缺失，请提供已计算的结果值。"
            ),
        )
    elif error := value_error(value, metric):
        result.update(status="invalid", reason=error)
    elif metric["rule"] == "interval" and parameter_issues(parameter, metric):
        result.update(status="invalid", reason="参数未填写完整或不合法，暂不计算等级。")
    elif metric["rule"] == "must_be_true":
        result.update(grade="D" if value else "U", reason="已完成。" if value else "未完成。")
    elif metric["rule"] == "zero_events":
        result.update(
            grade="D" if value == 0 else "U",
            reason="未发生禁止事件。" if value == 0 else "发生禁止事件。",
        )
    else:
        grade = (
            "D"
            if _inside(value, parameter["desired"])
            else "A"
            if _inside(value, parameter["acceptable"])
            else "U"
        )
        result.update(
            grade=grade, reason=f"位于 {grade} 区间。" if grade != "U" else "未落入 D/A 区间。"
        )
    return result


def _triggered(checkpoint, values, metrics, condition_key="fail_when"):
    for condition in checkpoint.get(condition_key, []):
        key, expected = condition["metric_id"], condition["equals"]
        value = values.get(key)
        if value is None or value_error(value, metrics[key]):
            continue
        if type(expected) is bool:
            matched = type(value) is bool and value is expected
        else:
            matched = type(value) in {int, float} and value == expected
        if matched:
            return True
    return False


def evaluate(
    configuration: Any,
    input_data: Any,
    *,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate detached JSON documents; unknown evidence never becomes Pass."""
    definition = catalog if catalog is not None else catalog_for_configuration(configuration)
    configuration = normalize_configuration(configuration, definition)
    if definition.get("schema_version") == "3.0":
        from pilot_assessment.scene_assessment.frame_calculator import evaluate as evaluate_v3

        return evaluate_v3(configuration, input_data, definition)
    if definition.get("schema_version") == "2.0":
        from pilot_assessment.scene_assessment.series_calculator import evaluate as evaluate_v2

        return evaluate_v2(configuration, input_data, definition)
    config_header = document_issues(configuration, "parameters", definition)
    input_header = document_issues(input_data, "results", definition)
    issues = validate_configuration(configuration, catalog=definition)["issues"]
    issues.extend({**entry, "path": "/input" + entry["path"]} for entry in input_header)
    metrics = {m["metric_id"]: m for m in definition["metrics"]}
    values = input_data.get("results", {}) if isinstance(input_data, dict) else {}
    rows = configuration.get("parameters", {}) if isinstance(configuration, dict) else {}
    values = values if isinstance(values, dict) else {}
    rows = rows if isinstance(rows, dict) else {}
    issues.extend(object_issues(values, set(metrics), "/input/results"))
    blocked = bool(config_header or input_header)
    items = []
    for item in definition["items"]:
        checkpoints = []
        for checkpoint in item["checkpoints"]:
            forced_fail = not blocked and _triggered(checkpoint, values, metrics)
            missing_not_required = forced_fail or (
                not blocked and _triggered(checkpoint, values, metrics, "not_required_when")
            )
            result_metrics = []
            for key in checkpoint["metric_ids"]:
                result = _metric_result(
                    metrics[key],
                    values.get(key),
                    rows.get(key),
                    short_circuit=missing_not_required,
                    blocked=blocked,
                )
                result_metrics.append(result)
                if result["status"] in {"missing", "invalid"}:
                    issues.append(issue("/input/results/" + key, result["reason"]))
            grade = "U" if forced_fail else _worst([r["grade"] for r in result_metrics])
            checkpoints.append(
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "name": checkpoint["name"],
                    "grade": grade,
                    "metrics": result_metrics,
                }
            )
        grade = _worst([point["grade"] for point in checkpoints])
        items.append(
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "grade": grade,
                "passed": _passed(grade),
                "checkpoints": checkpoints,
                "skill_quantification": {
                    "status": "requires_frames",
                    "skill_name": item.get("skill_name", item["name"]),
                    "method": "not_applicable",
                    "model_version": None,
                    "calibration": None,
                    "parameter_source": None,
                    "posterior": None,
                    "score": None,
                    "evidence_count": 0,
                    "expected_evidence_count": len(checkpoints),
                    "evidence": [],
                    "warnings": [],
                    "message": "旧版汇总结果仅保留规则评估；能力量化请使用 v3 逐帧输入。",
                },
            }
        )
    unique_issues = list({(entry["path"], entry["message"]): entry for entry in issues}.values())
    grade = _worst([item["grade"] for item in items])
    rule_issues = [
        entry
        for entry in unique_issues
        if entry["path"] != "/skill_models" and not entry["path"].startswith("/skill_models/")
    ]
    if rule_issues and grade != "U":
        grade = None
    return {
        "schema_version": definition["schema_version"],
        "scene_id": definition["scene_id"],
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "calculation_status": "needs_input" if unique_issues else "complete",
        "grade": grade,
        "passed": _passed(grade),
        "configuration": copy.deepcopy(configuration),
        "input": copy.deepcopy(input_data),
        "issues": unique_issues,
        "items": items,
    }
