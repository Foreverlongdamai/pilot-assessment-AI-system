"""Validation for checkpoint-owned raw values and signed tolerances (schema 2)."""

from __future__ import annotations

import math
from typing import Any

from pilot_assessment.scene_assessment.validation import (
    _interval,
    issue,
    object_issues,
)


def is_number(value: Any) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def document_issues(value: Any, section: str, catalog: dict[str, Any]) -> list[dict[str, str]]:
    keys = {"schema_version", "scene_id", section}
    if section == "parameters":
        keys.add("skill_models")
    issues = object_issues(value, keys, "")
    if not isinstance(value, dict):
        return issues
    for key in ("schema_version", "scene_id"):
        if value.get(key) != catalog[key]:
            issues.append(issue("/" + key, f"必须为 {catalog[key]}，请使用对应版本的新模板。"))
    if not isinstance(value.get(section), dict):
        issues.append(issue("/" + section, "此处必须是 JSON 对象。"))
    return issues


def parameter_issues(value: Any, metric: dict[str, Any]) -> list[dict[str, str]]:
    path = "/parameters/" + metric["metric_id"]
    issues = object_issues(value, {"expected", "desired", "acceptable"}, path)
    if not isinstance(value, dict):
        return issues
    if not is_number(value.get("expected")):
        issues.append(issue(path + "/expected", "请填写原始量的有限数值期望值。"))
    desired, d_issues = _interval(value.get("desired"), path + "/desired")
    acceptable, a_issues = _interval(value.get("acceptable"), path + "/acceptable")
    issues.extend(d_issues + a_issues)
    for name in ("desired", "acceptable"):
        interval = value.get(name)
        if not isinstance(interval, dict):
            continue
        for bound in ("lower", "upper"):
            number = interval.get(bound)
            if number is not None and not is_number(number):
                issues.append(issue(f"{path}/{name}/{bound}", "容差边界必须在有限数值范围内。"))
    if desired is not None and acceptable is not None:
        dl, du = desired
        al, au = acceptable
        if not al <= dl <= du <= au or desired == acceptable:
            issues.append(issue(path, "D 偏差范围必须是 A 的严格子区间。"))
        if not dl <= 0 <= du or not al <= 0 <= au:
            issues.append(issue(path, "D/A 是相对期望值的偏差范围，均须包含 0。"))
    return issues


def validate_configuration(configuration: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    from pilot_assessment.scene_assessment.series_models import configuration_model_issues

    issues = document_issues(configuration, "parameters", catalog)
    rows = configuration.get("parameters") if isinstance(configuration, dict) else None
    if isinstance(rows, dict):
        metrics = [metric for metric in catalog["metrics"] if metric["rule"] == "interval"]
        issues.extend(
            object_issues(rows, {metric["metric_id"] for metric in metrics}, "/parameters")
        )
        for metric in metrics:
            issues.extend(parameter_issues(rows.get(metric["metric_id"]), metric))
    issues.extend(configuration_model_issues(configuration, catalog))
    return {"valid": not issues, "issues": issues}


def value_error(value: Any, metric: dict[str, Any]) -> str | None:
    if metric["rule"] == "must_be_true":
        return None if type(value) is bool else "必须提供 true/false，不能使用数值或字符串代替。"
    if metric["rule"] == "zero_events":
        return None if type(value) is int and value >= 0 else "事件数量必须是非负整数。"
    return None if is_number(value) else "原始值必须为有限数值，不能使用布尔、字符串或无穷值。"


def sample_grid(samples: Any, metric_ids: set[str], path: str):
    """Inspect the supplied intervals without sorting, clipping or interpolation."""
    if not isinstance(samples, list):
        return [], [issue(path, "samples 必须是数组。")], False
    issues = []
    valid_grid = True
    previous_end = None
    first_start = None
    for index, sample in enumerate(samples):
        sample_path = f"{path}/{index}"
        entry_issues = object_issues(sample, {"start_s", "end_s", "values"}, sample_path)
        if not isinstance(sample, dict):
            issues.extend(entry_issues)
            valid_grid = False
            continue
        start, end = sample.get("start_s"), sample.get("end_s")
        if not is_number(start) or not is_number(end):
            entry_issues.append(issue(sample_path, "区间起止时间必须是有限数值。"))
            valid_grid = False
        else:
            try:
                duration = end - start
                span = end - (start if first_start is None else first_start)
            except OverflowError:
                duration = span = float("inf")
            if not is_number(duration) or not is_number(span) or duration <= 0:
                entry_issues.append(issue(sample_path, "时间区间长度必须为有限正数。"))
                valid_grid = False
            if previous_end is not None and start < previous_end:
                entry_issues.append(issue(sample_path, "区间重叠或顺序错误；系统不会重排数据。"))
                valid_grid = False
            elif previous_end is not None and start > previous_end:
                entry_issues.append(
                    issue(sample_path, f"{previous_end} 至 {start} 秒没有数据覆盖。")
                )
            if first_start is None:
                first_start = start
            previous_end = end
        values = sample.get("values")
        entry_issues.extend(object_issues(values, metric_ids, sample_path + "/values"))
        if not isinstance(values, dict):
            valid_grid = False
        issues.extend(entry_issues)
    return samples if valid_grid else [], issues, valid_grid
