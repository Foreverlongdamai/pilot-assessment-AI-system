"""Validate draft parameters and the sole v3 Bayesian compensation method."""

from __future__ import annotations

import math

from pilot_assessment.scene_assessment.configuration import SEQUENTIAL_INFERENCE_METHOD
from pilot_assessment.scene_assessment.series_validation import is_number
from pilot_assessment.scene_assessment.validation import issue, object_issues

MODEL_KEYS = {
    "model_version",
    "calibration",
    "parameter_source",
    "prior",
    "state_scores",
    "checkpoint_models",
}


def _required_object(value, keys, path, *, optional_keys=frozenset()):
    issues = object_issues(value, keys | optional_keys, path)
    if isinstance(value, dict):
        issues.extend(
            issue(f"{path}/{key}", "缺少模型结构字段；请使用完整的空单元格模板。")
            for key in sorted(keys - set(value))
        )
    return issues


def _number_row(value, columns, path, *, probability):
    if not isinstance(value, list) or len(value) != columns:
        return [issue(path, f"必须包含 {columns} 个单元格，未填写的单元格用 null。")]
    maximum = 1 if probability else 100
    issues = [
        issue(f"{path}/{index}", f"已填数值必须有限且在 0 至 {maximum} 范围内。")
        for index, number in enumerate(value)
        if number is not None and (not is_number(number) or not 0 <= number <= maximum)
    ]
    if issues:
        return issues
    known = [number for number in value if number is not None]
    if probability:
        total = math.fsum(known)
        if len(known) == columns and not math.isclose(total, 1, rel_tol=0, abs_tol=1e-9):
            issues.append(issue(path, "完整概率行之和必须为 1；系统不会自动归一化。"))
        elif total > 1 + 1e-9:
            issues.append(issue(path, "已填写的概率之和不能超过 1。"))
    elif any(lower >= upper for lower, upper in zip(known, known[1:], strict=False)):
        issues.append(issue(path, "已填写的低、中、高状态分值必须严格递增。"))
    return issues


def _model_issues(model, item, metrics, *, schema_version=None):
    path = "/skill_models/" + item["item_id"]
    issues = _required_object(
        model,
        MODEL_KEYS,
        path,
        optional_keys={"inference_method", "compensation"}
        if schema_version == "3.0" else set(),
    )
    if not isinstance(model, dict):
        return issues
    inference_method = model.get("inference_method")
    sequential = schema_version == "3.0" and inference_method == SEQUENTIAL_INFERENCE_METHOD
    if inference_method is not None and not sequential:
        issues.append(
            issue(path + "/inference_method", "未知推断方法；不自动选择替代算法。")
        )
    if sequential:
        compensation = model.get("compensation")
        compensation_path = path + "/compensation"
        issues.extend(_required_object(compensation, {"alpha"}, compensation_path))
        if isinstance(compensation, dict):
            alpha = compensation.get("alpha")
            if not is_number(alpha) or not 0 <= alpha <= 1:
                issues.append(
                    issue(compensation_path + "/alpha", "网络更新系数须为 0 至 1 的有限数值。")
                )
    elif "compensation" in model:
        issues.append(issue(path + "/compensation", "网络更新参数仅适用于当前贝叶斯网络方法。"))
    version = model.get("model_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(issue(path + "/model_version", "模型版本标识必须是非空文本。"))
    if model.get("calibration") != "uncalibrated":
        issues.append(issue(path + "/calibration", "本版仅支持未校准的研究模型标记 uncalibrated。"))
    if model.get("parameter_source") not in ("unconfigured", "user_defined", "demonstration"):
        issues.append(issue(path + "/parameter_source", "未知模型参数来源标记。"))
    issues.extend(_number_row(model.get("prior"), 3, path + "/prior", probability=True))
    issues.extend(
        _number_row(model.get("state_scores"), 3, path + "/state_scores", probability=False)
    )
    points = model.get("checkpoint_models")
    point_ids = {point["checkpoint_id"] for point in item["checkpoints"]}
    issues.extend(_required_object(points, point_ids, path + "/checkpoint_models"))
    if not isinstance(points, dict):
        return issues
    for point in item["checkpoints"]:
        key = point["checkpoint_id"]
        point_path = path + "/checkpoint_models/" + key
        row = points.get(key)
        issues.extend(_required_object(row, {"states", "probabilities"}, point_path))
        if not isinstance(row, dict):
            continue
        binary = all(metrics[metric_id]["rule"] != "interval" for metric_id in point["metric_ids"])
        states = ["D", "U"] if binary else ["D", "A", "U"]
        if row.get("states") != states:
            issues.append(issue(point_path + "/states", "观察状态及顺序必须为 " + "/".join(states)))
        matrix = row.get("probabilities")
        if not isinstance(matrix, list) or len(matrix) != 3:
            issues.append(issue(point_path + "/probabilities", "概率表必须有低、中、高三行。"))
            continue
        for index, probabilities in enumerate(matrix):
            issues.extend(
                _number_row(
                    probabilities,
                    len(states),
                    f"{point_path}/probabilities/{index}",
                    probability=True,
                )
            )
    if sequential:
        probability_rows = [(path + "/prior", model.get("prior"), False)]
        for key, point in points.items():
            matrix = point.get("probabilities") if isinstance(point, dict) else None
            if isinstance(matrix, list):
                probability_rows.extend(
                    (f"{path}/checkpoint_models/{key}/probabilities/{index}", row, True)
                    for index, row in enumerate(matrix)
                )
        for row_path, row, strictly_positive in probability_rows:
            if isinstance(row, list):
                issues.extend(
                    issue(
                        f"{row_path}/{index}",
                        "推断须填写完整概率，CPT 须严格大于 0；不补值或截断零值。",
                    )
                    for index, value in enumerate(row)
                    if not is_number(value) or (value <= 0 if strictly_positive else value < 0)
                )
        if isinstance(model.get("state_scores"), list) and any(
            value is None for value in model["state_scores"]
        ):
            issues.append(issue(path + "/state_scores", "推断须填写完整的状态分值。"))
    return issues


def configuration_model_issues(configuration, catalog):
    if not isinstance(configuration, dict) or configuration.get("skill_models") is None:
        return []
    models = configuration["skill_models"]
    items = {
        item["item_id"]: item
        for item in catalog["items"]
        if item.get("assessment_kind") == "flight"
    }
    issues = object_issues(models, set(items), "/skill_models")
    if not isinstance(models, dict):
        return issues
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for key, item in items.items():
        if key in models:
            issues.extend(
                _model_issues(
                    models[key], item, metrics, schema_version=catalog.get("schema_version")
                )
            )
    return issues
