"""Validate calculator documents without treating invalid input as pilot failure."""

from __future__ import annotations

import math
from typing import Any

Issue = dict[str, str]


def issue(path: str, message: str) -> Issue:
    return {"path": path, "message": message}


def is_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def object_issues(value: Any, keys: set[str], path: str) -> list[Issue]:
    if not isinstance(value, dict):
        return [issue(path, "此处必须是 JSON 对象。")]
    return [issue(f"{path}/{key}", "未知字段，请检查拼写。") for key in value if key not in keys]


def document_issues(value: Any, section: str, catalog: dict[str, Any]) -> list[Issue]:
    keys = {"schema_version", "scene_id", section}
    if section == "parameters":
        keys.add("skill_models")
    issues = object_issues(value, keys, "")
    if not isinstance(value, dict):
        return issues
    for key in ("schema_version", "scene_id"):
        if value.get(key) != catalog[key]:
            issues.append(issue(f"/{key}", f"必须为 {catalog[key]}。"))
    if not isinstance(value.get(section), dict):
        issues.append(issue(f"/{section}", "此处必须是 JSON 对象。"))
    return issues


def _interval(value: Any, path: str) -> tuple[tuple[Any, Any] | None, list[Issue]]:
    issues = object_issues(value, {"lower", "upper", "unbounded_upper"}, path)
    if not isinstance(value, dict):
        return None, issues
    lower, upper, unbounded = value.get("lower"), value.get("upper"), value.get("unbounded_upper")
    if not is_number(lower):
        issues.append(issue(path + "/lower", "请填写有限数值下界，布尔值不能作为数值。"))
    if type(unbounded) is not bool:
        issues.append(issue(path + "/unbounded_upper", "请明确选择是否无上限。"))
    if unbounded is True:
        if upper is not None:
            issues.append(issue(path + "/upper", "无上限时，上界必须留空。"))
        upper = math.inf
    elif not is_number(upper):
        issues.append(issue(path + "/upper", "请填写有限数值上界，或明确选择无上限。"))
    if not issues and lower > upper:
        issues.append(issue(path, "下界不能大于上界。"))
    return (None if issues else (lower, upper)), issues


def parameter_issues(value: Any, metric: dict[str, Any]) -> list[Issue]:
    path = "/parameters/" + metric["metric_id"]
    issues = object_issues(value, {"expected", "desired", "acceptable"}, path)
    if not isinstance(value, dict):
        return issues
    expected = value.get("expected")
    if not is_number(expected):
        issues.append(issue(path + "/expected", "请填写有限数值期望值。"))
    desired, desired_issues = _interval(value.get("desired"), path + "/desired")
    acceptable, acceptable_issues = _interval(value.get("acceptable"), path + "/acceptable")
    issues.extend(desired_issues + acceptable_issues)
    if issues:
        return issues
    assert desired is not None and acceptable is not None
    dl, du = desired
    al, au = acceptable
    if not (al <= dl <= du <= au) or desired == acceptable:
        issues.append(issue(path, "D 必须是 A 的严格子区间，不能相等或交叉。"))
    if not dl <= expected <= du:
        issues.append(issue(path + "/expected", "期望值必须落在 D 区间内。"))
    kind = metric["parameter_kind"]
    if kind == "error" and (expected != 0 or dl != 0 or al != 0):
        issues.append(issue(path, "绝对偏差的期望值与 D/A 下界必须为 0。"))
    if kind == "gaze" and al <= 0:
        issues.append(issue(path, "注视检查 A 下界必须大于 0，未观察不能通过。"))
    if kind == "hold" and not 0 < al < dl:
        issues.append(issue(path, "保持时长必须满足 0 < A 下界 < D 下界。"))
    if kind == "signed" and not (dl <= 0 <= du and al <= 0 <= au):
        issues.append(issue(path, "有符号位置偏差的 D/A 区间都必须包含 0。"))
    if kind == "duration" and al < 0:
        issues.append(issue(path, "减速耗时区间下界不能小于 0。"))
    return issues


def value_error(value: Any, metric: dict[str, Any]) -> str | None:
    value_type = metric["value_type"]
    if value_type == "boolean":
        return None if type(value) is bool else "必须提供 true 或 false，不能使用 0/1 代替。"
    if value_type == "integer":
        return None if type(value) is int and value >= 0 else "事件数量必须为非负整数。"
    if not is_number(value):
        return "必须提供有限数值，布尔、字符串、NaN 和无穷值均无效。"
    kind = metric["parameter_kind"]
    if kind != "signed" and value < 0:
        return "该结果不能小于 0。"
    if kind == "duration" and value <= 0:
        return "已完成减速的实际耗时必须大于 0。"
    return None
