"""Grade exact frames; interpolate only explicit reference targets, never observations."""

from __future__ import annotations

import copy
import math
from datetime import UTC, datetime

from pilot_assessment.scene_assessment.configuration import (
    SEQUENTIAL_INFERENCE_METHOD,
    normalize_configuration,
)
from pilot_assessment.scene_assessment.frame_validation import (
    parameter_issues,
    read_frames,
    scene_timing_issues,
    validate_configuration,
)
from pilot_assessment.scene_assessment.route_geometry import (
    nearest_route_position,
    position_status,
)
from pilot_assessment.scene_assessment.sequential_compensation import quantify_sequential
from pilot_assessment.scene_assessment.series_calculator import _quantification
from pilot_assessment.scene_assessment.series_validation import (
    document_issues,
    is_number,
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


def _status(points):
    if any(point["status"] == "invalid" for point in points):
        return "invalid"
    if not points or any(point["status"] == "missing" for point in points):
        return "missing"
    return "calculated"


def _distribution(points):
    counts = {grade: sum(point["grade"] == grade for point in points) for grade in ("D", "A", "U")}
    valid = sum(counts.values())
    return {
        "counts": counts,
        "proportions": {grade: count / valid if valid else None for grade, count in counts.items()},
        "valid_frame_count": valid,
        "missing_frame_count": len(points) - valid,
        "total_frame_count": len(points),
    }


def _inside(deviation, interval):
    return interval["lower"] <= deviation and (
        interval["unbounded_upper"] or deviation <= interval["upper"]
    )


def _radial(value, parameter):
    errors = object_issues(value, {"status", "u_m", "v_m"}, "")
    if not isinstance(value, dict):
        return None, "invalid", "激光输入须包含 status 与靶面落点坐标。"
    status = value.get("status")
    if not errors and status is None and value.get("u_m") is None and value.get("v_m") is None:
        return None, "missing", "尚未填写当前帧的激光状态与落点。"
    if errors or status not in ("hit", "miss", "unavailable"):
        return None, "invalid", "激光状态未知或包含未定义字段。"
    if status in ("miss", "unavailable"):
        if value.get("u_m") is not None or value.get("v_m") is not None:
            return None, "invalid", "脱靶或不可用状态不应同时提供有效命中坐标。"
        return (
            None,
            "missing" if status == "unavailable" else "miss",
            "激光数据不可用。" if status == "unavailable" else "明确未命中应评靶。",
        )
    if not is_number(value.get("u_m")) or not is_number(value.get("v_m")):
        return None, "invalid", "有效命中的 u_m/v_m 必须为有限数值。"
    if not isinstance(parameter, dict) or not all(
        is_number(parameter.get(key)) for key in ("center_u", "center_v")
    ):
        return None, "invalid", "靶心尚未配置完整。"
    try:
        distance = math.hypot(
            value["u_m"] - parameter["center_u"], value["v_m"] - parameter["center_v"]
        )
    except OverflowError:
        distance = math.inf
    return distance, "calculated", ""


def _profile_roundoff(timestamp_s, origin_s, elapsed_s, endpoint_s):
    """Only binary floating-point representation uncertainty, never time slack."""
    return sum(
        math.ulp(value) / 2
        for value in (timestamp_s, origin_s, elapsed_s, endpoint_s)
        if type(value) is float
    )


def _profile_expected(nodes, elapsed, *, timestamp_s=None, phase_origin_s=None):
    """Piecewise linear reference, inclusive endpoints, with no extrapolation."""
    if not is_number(elapsed):
        return None
    if elapsed == nodes[0]["elapsed_s"]:
        return nodes[0]["expected"]
    endpoint = nodes[-1]["elapsed_s"]
    if timestamp_s is not None and phase_origin_s is not None:
        # Input floats and the subtraction each contribute at most half an
        # ULP of rounding uncertainty. Correct only endpoint representation
        # error (e.g. 10.4 - 10.1 > 0.3), never add a physical time tolerance.
        # Integer timestamps/differences are exact and contribute no allowance.
        roundoff = _profile_roundoff(timestamp_s, phase_origin_s, elapsed, endpoint)
        if abs(elapsed - endpoint) <= roundoff:
            return nodes[-1]["expected"]
    if elapsed < nodes[0]["elapsed_s"] or elapsed > nodes[-1]["elapsed_s"]:
        return None
    for left, right in zip(nodes, nodes[1:], strict=False):
        if elapsed == left["elapsed_s"]:
            return left["expected"]
        if elapsed == right["elapsed_s"]:
            return right["expected"]
        if left["elapsed_s"] < elapsed < right["elapsed_s"]:
            fraction = (elapsed - left["elapsed_s"]) / (right["elapsed_s"] - left["elapsed_s"])
            # A convex combination avoids overflow from subtracting opposite
            # large finite targets. Observed values are not interpolated.
            return (1 - fraction) * left["expected"] + fraction * right["expected"]
    return None


def _value(
    metric,
    value,
    parameter,
    *,
    phase_id=None,
    elapsed_s=None,
    timestamp_s=None,
    phase_origin_s=None,
):
    result = {
        "value": copy.deepcopy(value),
        "expected": copy.deepcopy(parameter.get("expected"))
        if isinstance(parameter, dict)
        else None,
        "deviation": None,
        "grade": None,
        "status": "calculated",
        "reason": "",
    }
    shared_profile = metric.get("target_mode") == "item_profile"
    profile = shared_profile or metric.get("target_mode") == "phase_profile"
    if shared_profile:
        result["reference_elapsed_s"] = elapsed_s
    profile_errors = parameter_issues(parameter, metric) if profile else None
    if profile and not profile_errors:
        result["expected"] = _profile_expected(
            parameter["reference_profile"]
            if shared_profile
            else parameter["reference_profiles"][phase_id],
            elapsed_s,
            timestamp_s=timestamp_s,
            phase_origin_s=phase_origin_s,
        )
    if value is None:
        return result | {"status": "missing", "reason": "缺少当前帧必需的原始值。"}
    radial = metric.get("comparison") == "radial"
    route = metric.get("comparison") == "route_3d"
    if route:
        status, reason = position_status(value)
        if status != "calculated":
            return result | {"status": status, "reason": reason}
    elif radial:
        deviation, status, reason = _radial(value, parameter)
        if status != "calculated":
            return result | {
                "status": "calculated" if status == "miss" else status,
                "grade": "U" if status == "miss" else None,
                "reason": reason,
            }
    elif error := value_error(value, metric):
        return result | {"status": "invalid", "reason": error}
    elif metric["rule"] in ("must_be_true", "zero_events"):
        passed = value is True if metric["rule"] == "must_be_true" else value == 0
        return result | {
            "grade": "D" if passed else "U",
            "reason": "已满足完成性或禁止事件规则。"
            if passed
            else "明确未完成或存在已定义禁止事件。",
        }
    errors = profile_errors if profile else parameter_issues(parameter, metric)
    if errors:
        return result | {
            "status": "invalid",
            "reason": "期望值、容差、路线或靶面参数未配置完整或不合法。",
        }
    expected = result["expected"]
    if profile and expected is None:
        return result | {
            "status": "missing",
            "reason": (
                "缺少共同计时起点环节的首帧，无法确定参考曲线相对时间。"
                if shared_profile and phase_origin_s is None
                else "当前帧超出已配置参考剖面的时间覆盖范围；系统不外推目标。"
            ),
        }
    if route:
        deviation, nearest, segment_index = nearest_route_position(value, parameter["route_points"])
        if is_number(deviation):
            result["nearest_route_point"] = nearest
            result["route_segment_index"] = segment_index
    elif not radial:
        try:
            deviation = (
                (value % 360 - expected % 360 + 180) % 360 - 180
                if metric.get("comparison") in ("heading", "angle_degrees")
                else value - expected
            )
        except OverflowError:
            deviation = math.inf
    if not is_number(deviation):
        return result | {"status": "invalid", "reason": "偏差超出有限数值范围。"}
    grade = (
        "D"
        if _inside(deviation, parameter["desired"])
        else "A"
        if _inside(deviation, parameter["acceptable"])
        else "U"
    )
    return result | {
        "deviation": deviation,
        "grade": grade,
        "reason": f"当前帧偏差落在 {grade} 档。",
    }


def _metric(metric, records, parameter, missing_phases, path):
    applicable = [frame for frame in records if frame["phase_id"] in metric["phase_ids"]]
    timeline, issues = [], []
    phase_origins = {}
    for frame in records:
        phase_origins.setdefault(frame["phase_id"], frame["timestamp_s"])
    shared = metric.get("target_mode") == "item_profile"
    shared_origin = phase_origins.get(metric.get("reference_origin_phase")) if shared else None
    for frame in applicable:
        origin = shared_origin if shared else phase_origins[frame["phase_id"]]
        result = _value(
            metric,
            frame["values"].get(metric["metric_id"]),
            parameter,
            phase_id=frame["phase_id"],
            elapsed_s=frame["timestamp_s"] - origin if origin is not None else None,
            timestamp_s=frame["timestamp_s"],
            phase_origin_s=origin,
        )
        timeline.append(
            {key: frame[key] for key in ("frame_index", "timestamp_s", "phase_id")} | result
        )
        if result["status"] in ("missing", "invalid"):
            issues.append(
                issue(
                    f"{path}/frames/{frame['frame_index']}/values/{metric['metric_id']}",
                    result["reason"],
                )
            )
    uncovered_phases = set()
    if (
        shared
        and shared_origin is not None
        and applicable
        and not parameter_issues(parameter, metric)
    ):
        terminal = applicable[-1]["timestamp_s"]
        elapsed = terminal - shared_origin
        endpoint = parameter["reference_profile"][-1]["elapsed_s"]
        roundoff = _profile_roundoff(terminal, shared_origin, elapsed, endpoint)
        if elapsed < endpoint and endpoint - elapsed > roundoff:
            uncovered_phases.add(metric["phase_ids"][-1])
            issues.append(
                issue(
                    path + "/frames",
                    f"{metric['metric_id']} 首末帧仅覆盖共同起点后的 {elapsed:g} 秒，"
                    f"未覆盖参考曲线末端 {endpoint:g} 秒；不补帧、不拉伸时间。",
                )
            )
    missing = bool(uncovered_phases) or any(key in missing_phases for key in metric["phase_ids"])
    grade = _worst([point["grade"] for point in timeline] + ([None] if missing else []))
    status = _status(timeline)
    if missing and status != "invalid":
        status = "missing"
    only = timeline[0] if len(timeline) == 1 else {}
    return (
        {
            "metric_id": metric["metric_id"],
            "value": copy.deepcopy(only.get("value")),
            "expected": copy.deepcopy(parameter.get("expected"))
            if isinstance(parameter, dict)
            else None,
            "deviation": only.get("deviation"),
            "parameter": copy.deepcopy(parameter),
            "grade": grade,
            "status": status,
            "reason": "只计算已提供且适用的帧；不推断帧间持续状态。",
            "timeline": timeline,
            "frame_distribution": _distribution(timeline),
        },
        issues,
        uncovered_phases,
    )


def _combined_timeline(records, timelines):
    indexed = [{point["frame_index"]: point for point in timeline} for timeline in timelines]
    result = []
    for frame in records:
        points = [
            lookup[frame["frame_index"]] for lookup in indexed if frame["frame_index"] in lookup
        ]
        if not points:
            continue
        result.append(
            {key: frame[key] for key in ("frame_index", "timestamp_s", "phase_id")}
            | {
                "grade": _worst([point["grade"] for point in points]),
                "status": _status(points),
                "reason": "当前帧的必需量取最差档；已知 U 不被其他量抵消。",
            }
        )
    return result


def _phase_results(item, records, timeline, path, *, uncovered_phases=()):
    results, issues, incomplete = [], [], set(uncovered_phases)
    for phase in item["phases"]:
        key = phase["phase_id"]
        frames = [frame for frame in records if frame["phase_id"] == key]
        points = [point for point in timeline if point["phase_id"] == key]
        span = frames[-1]["timestamp_s"] - frames[0]["timestamp_s"] if frames else None
        required = phase["required_duration_s"]
        minimum_count = phase.get("minimum_frame_count")
        if not frames:
            issues.append(issue(path + "/frames", f"缺少必需环节 {key} 的帧。"))
            incomplete.add(key)
        elif not is_number(span):
            issues.append(issue(path + "/frames", f"{key} 的首末时刻跨度超出有限数值范围。"))
            span = None
            incomplete.add(key)
        elif required is not None and span + 1e-9 < required:
            issues.append(
                issue(
                    path + "/frames",
                    f"{key} 首末帧仅覆盖 {span:g} 秒，未达到规定的 {required:g} 秒。",
                )
            )
            incomplete.add(key)
        if minimum_count is not None and len(frames) < minimum_count:
            issues.append(
                issue(
                    path + "/frames",
                    f"{key} 仅提供 {len(frames)} 帧，"
                    f"未达到数据充分性要求的至少 {minimum_count} 帧。",
                )
            )
            incomplete.add(key)
        grade = _worst([point["grade"] for point in points] + ([None] if key in incomplete else []))
        status = _status(points)
        if key in incomplete and status != "invalid":
            status = "missing"
        results.append(
            {
                "phase_id": key,
                "name": phase["name"],
                "grade": grade,
                "passed": _passed(grade),
                "status": status,
                "frame_distribution": _distribution(points),
                "observed_span_s": span,
                "required_duration_s": required,
                "minimum_frame_count": minimum_count,
                "coverage_note": (
                    "首末帧跨度仅表示已提供的时间范围，不证明连续采样或帧间状态；"
                    "未对观测值积分、插值或补帧；最少帧数只是数据充分性检查。"
                ),
            }
        )
    return results, issues, incomplete


def _evaluate_item(item, raw_item, rows, metrics, blocked, path):
    records, issues, _valid = read_frames(raw_item, item, metrics, path)
    structure_blocked = bool(blocked or issues)
    if blocked:
        records = []
    phases, phase_issues, incomplete = _phase_results(item, records, [], path)
    issues.extend(phase_issues)
    checkpoints = []
    uncovered_phases = set()
    for point in item["checkpoints"]:
        results = []
        for key in point["metric_ids"]:
            result, metric_issues, uncovered = _metric(
                metrics[key], records, rows.get(key), incomplete, path
            )
            uncovered_phases.update(uncovered)
            results.append(result)
            issues.extend(metric_issues)
        timeline = _combined_timeline(records, [result["timeline"] for result in results])
        checkpoints.append(
            {
                "checkpoint_id": point["checkpoint_id"],
                "name": point["name"],
                "grade": _worst([result["grade"] for result in results]),
                "metrics": results,
                "timeline": timeline,
                "frame_distribution": _distribution(timeline),
            }
        )
    timeline = _combined_timeline(records, [point["timeline"] for point in checkpoints])
    phases, _phase_issues, _incomplete = _phase_results(
        item, records, timeline, path, uncovered_phases=uncovered_phases
    )
    grade = _worst([point["grade"] for point in checkpoints] + [phase["grade"] for phase in phases])
    if issues and grade != "U":
        grade = None
    return (
        {
            "item_id": item["item_id"],
            "name": item["name"],
            "grade": grade,
            "passed": _passed(grade),
            "checkpoints": checkpoints,
            "timeline": timeline,
            "phase_results": phases,
            "frame_distribution": _distribution(timeline),
        },
        issues,
        structure_blocked,
        records,
    )


def evaluate(configuration, input_data, catalog):
    configuration = normalize_configuration(configuration, catalog)
    issues = validate_configuration(configuration, catalog)["issues"]
    config_header = document_issues(configuration, "parameters", catalog)
    input_header = document_issues(input_data, "items", catalog)
    issues.extend({**entry, "path": "/input" + entry["path"]} for entry in input_header)
    supplied = input_data.get("items") if isinstance(input_data, dict) else None
    supplied = supplied if isinstance(supplied, dict) else {}
    rows = configuration.get("parameters") if isinstance(configuration, dict) else None
    rows = rows if isinstance(rows, dict) else {}
    issues.extend(
        object_issues(supplied, {item["item_id"] for item in catalog["items"]}, "/input/items")
    )
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    items = []
    process_blocks = {}
    process_records = {}
    for item in catalog["items"]:
        result, item_issues, structure_blocked, records = _evaluate_item(
            item,
            supplied.get(item["item_id"]),
            rows,
            metrics,
            bool(config_header or input_header),
            "/input/items/" + item["item_id"],
        )
        process_blocks[item["item_id"]] = structure_blocked
        process_records[item["item_id"]] = records
        issues.extend(item_issues)
        items.append(result)
    timing_issues = scene_timing_issues(catalog, items)
    issues.extend(timing_issues)
    issues = list({(entry["path"], entry["message"]): entry for entry in issues}.values())
    rule_issues = [
        entry
        for entry in issues
        if entry["path"] != "/skill_models" and not entry["path"].startswith("/skill_models/")
    ]
    known_owner_paths = {"/input/items/" + item["item_id"] for item in catalog["items"]} | {
        "/parameters/" + metric["metric_id"] for metric in catalog["metrics"]
    }
    global_rule_issues = any(
        not any(
            entry["path"] == key or entry["path"].startswith(key + "/") for key in known_owner_paths
        )
        for entry in rule_issues
    )
    for item, result in zip(catalog["items"], items, strict=True):
        quantification = _quantification(item, issues)
        if item.get("assessment_kind") != "checklist":
            if quantification["status"] == "pending_method":
                quantification["status"] = "not_configured"
            quantification["method"] = SEQUENTIAL_INFERENCE_METHOD
            quantification["message"] = "尚未填写完整的贝叶斯网络参数；保留规则结果与帧数分布。"
        path = "/input/items/" + item["item_id"]
        parameter_paths = {
            "/parameters/" + key for point in item["checkpoints"] for key in point["metric_ids"]
        }
        item_rule_issues = any(
            entry["path"] == path
            or entry["path"].startswith(path + "/")
            or any(
                entry["path"] == key or entry["path"].startswith(key + "/")
                for key in parameter_paths
            )
            for entry in rule_issues
        )
        parameter_blocked = any(
            entry["path"] == key or entry["path"].startswith(key + "/")
            for entry in rule_issues
            for key in parameter_paths
        )
        models = configuration.get("skill_models") if isinstance(configuration, dict) else None
        model = models.get(item["item_id"]) if isinstance(models, dict) else None
        if (
            item.get("assessment_kind") == "flight"
            and isinstance(model, dict)
            and model.get("inference_method") == SEQUENTIAL_INFERENCE_METHOD
        ):
            result["skill_quantification"] = quantify_sequential(
                configuration,
                item,
                result,
                quantification,
                issues,
                blocked=bool(
                    config_header
                    or input_header
                    or timing_issues
                    or global_rule_issues
                    or item_rule_issues
                ),
                process_blocked=bool(
                    process_blocks[item["item_id"]]
                    or timing_issues
                    or global_rule_issues
                    or parameter_blocked
                ),
                records=process_records[item["item_id"]],
            )
            continue
        result["skill_quantification"] = quantification
        quantification["temporal_analysis"] = {
            "status": "not_applicable"
            if item.get("assessment_kind") == "checklist"
            else "invalid_model"
            if quantification["status"] == "invalid_model"
            else "not_configured",
            "method": SEQUENTIAL_INFERENCE_METHOD,
            "model_version": None,
            "message": quantification["message"],
            "warnings": list(quantification["warnings"]),
            "checkpoint_traces": [],
            "item_trace": None,
        }
    grade = _worst([item["grade"] for item in items])
    if rule_issues and grade != "U":
        grade = None
    return {
        "schema_version": "3.0",
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
