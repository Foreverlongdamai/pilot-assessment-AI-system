"""Validate exact item frames and editable v3 parameters without deriving phases."""

from __future__ import annotations

import math
from collections import Counter

from pilot_assessment.scene_assessment.route_geometry import COORDINATES
from pilot_assessment.scene_assessment.series_models import configuration_model_issues
from pilot_assessment.scene_assessment.series_validation import (
    document_issues,
    is_number,
)
from pilot_assessment.scene_assessment.series_validation import (
    parameter_issues as signed_parameter_issues,
)
from pilot_assessment.scene_assessment.validation import issue, object_issues

CONTROLS = {"Pilot Lon", "Pilot Lat", "Pilot Yaw", "Pilot Heave"}


def _profile_parameter_issues(value, metric):
    path = "/parameters/" + metric["metric_id"]
    shared = metric.get("target_mode") == "item_profile"
    field = "reference_profile" if shared else "reference_profiles"
    issues = object_issues(value, {"expected", "desired", "acceptable", field}, path)
    if not isinstance(value, dict):
        return issues
    if metric.get("comparison", "linear") != "linear":
        issues.append(issue(path, "参考剖面仅适用于线性原始量，不能用于航向角或径向比较。"))
    if "expected" not in value or value["expected"] is not None:
        issues.append(
            issue(path + "/expected", "参考剖面必须使用 expected: null，不能同时设置固定目标。")
        )
    # Reuse signed tolerance validation with a neutral finite target; the actual
    # target is supplied explicitly by the profile, never filled into the config.
    basic = {key: value.get(key) for key in ("desired", "acceptable")} | {"expected": 0}
    issues.extend(signed_parameter_issues(basic, metric))
    profiles_path = path + "/" + field
    if shared:
        origin = metric.get("reference_origin_phase")
        if not isinstance(origin, str) or origin not in metric["phase_ids"]:
            issues.append(issue(path, "跨环节参考曲线必须指定一个适用环节作为共同计时起点。"))
        profiles = [(profiles_path, value.get(field))]
    else:
        by_phase = value.get(field)
        issues.extend(object_issues(by_phase, set(metric["phase_ids"]), profiles_path))
        if not isinstance(by_phase, dict):
            return issues
        profiles = [
            (profiles_path + "/" + phase_id, by_phase.get(phase_id))
            for phase_id in metric["phase_ids"]
        ]
    for nodes_path, nodes in profiles:
        if not isinstance(nodes, list) or len(nodes) < 2:
            issues.append(issue(nodes_path, "参考曲线至少需要两个节点。"))
            continue
        previous = None
        for index, node in enumerate(nodes):
            node_path = f"{nodes_path}/{index}"
            issues.extend(object_issues(node, {"elapsed_s", "expected"}, node_path))
            if not isinstance(node, dict):
                continue
            elapsed = node.get("elapsed_s")
            if not is_number(elapsed) or elapsed < 0:
                issues.append(issue(node_path + "/elapsed_s", "相对时刻必须为非负有限数值。"))
            else:
                if index == 0 and elapsed != 0:
                    issues.append(
                        issue(node_path + "/elapsed_s", "参考曲线首节点必须从相对时刻 0 秒开始。")
                    )
                if previous is not None and elapsed <= previous:
                    issues.append(
                        issue(
                            node_path + "/elapsed_s", "参考节点时刻必须严格递增；系统不重排节点。"
                        )
                    )
                previous = elapsed
            if not is_number(node.get("expected")):
                issues.append(issue(node_path + "/expected", "参考节点的目标必须为有限数值。"))
    return issues


def _route_parameter_issues(value, metric):
    path = "/parameters/" + metric["metric_id"]
    issues = object_issues(value, {"expected", "desired", "acceptable", "route_points"}, path)
    if not isinstance(value, dict):
        return issues
    basic = {key: value.get(key) for key in ("expected", "desired", "acceptable")}
    issues.extend(signed_parameter_issues(basic, metric))
    if value.get("expected") != 0:
        issues.append(issue(path + "/expected", "到三维路线的距离期望值必须为 0。"))
    for name in ("desired", "acceptable"):
        interval = value.get(name)
        if isinstance(interval, dict) and (
            interval.get("lower") != 0 or interval.get("unbounded_upper") is not False
        ):
            issues.append(issue(path + "/" + name, "通道距离从 0 起算，必须使用有限的外半径。"))
    nodes_path = path + "/route_points"
    nodes = value.get("route_points")
    if not isinstance(nodes, list) or len(nodes) < 2:
        issues.append(issue(nodes_path, "三维路线至少需要两个完整的有序位置点。"))
        return issues
    previous = None
    for index, node in enumerate(nodes):
        node_path = f"{nodes_path}/{index}"
        issues.extend(object_issues(node, set(COORDINATES), node_path))
        if not isinstance(node, dict):
            previous = None
            continue
        for key in COORDINATES:
            if not is_number(node.get(key)):
                issues.append(issue(node_path + "/" + key, "路线点坐标必须填写有限数值。"))
        current = (
            tuple(node[key] for key in COORDINATES)
            if all(is_number(node.get(key)) for key in COORDINATES)
            else None
        )
        if current is not None and current == previous:
            issues.append(issue(node_path, "相邻路线点不能完全相同；系统不删除或重排路线点。"))
        previous = current
    return issues


def parameter_issues(value, metric):
    if metric.get("target_mode") in ("phase_profile", "item_profile"):
        return _profile_parameter_issues(value, metric)
    if metric.get("comparison") == "route_3d":
        return _route_parameter_issues(value, metric)
    if metric.get("comparison") != "radial":
        return signed_parameter_issues(value, metric)
    path = "/parameters/" + metric["metric_id"]
    keys = {"expected", "desired", "acceptable", "center_u", "center_v", "target_radius"}
    issues = object_issues(value, keys, path)
    if not isinstance(value, dict):
        return issues
    basic = {key: value.get(key) for key in ("expected", "desired", "acceptable")}
    issues.extend(signed_parameter_issues(basic, metric))
    for key in ("center_u", "center_v", "target_radius"):
        if not is_number(value.get(key)):
            issues.append(issue(path + "/" + key, "请填写有限数值的靶面几何参数。"))
    if value.get("expected") != 0:
        issues.append(issue(path + "/expected", "径向偏差的期望值必须为 0。"))
    for name in ("desired", "acceptable"):
        interval = value.get(name)
        if isinstance(interval, dict) and (
            interval.get("lower") != 0 or interval.get("unbounded_upper") is not False
        ):
            issues.append(issue(path + "/" + name, "圆环下界必须为 0，并使用有限外半径。"))
    if not issues:
        rd, ra = value["desired"]["upper"], value["acceptable"]["upper"]
        if not 0 <= rd < ra < value["target_radius"]:
            issues.append(issue(path, "圆环必须满足 0 ≤ D 半径 < A 半径 < 实体靶半径。"))
    return issues


def validate_configuration(configuration, catalog):
    from pilot_assessment.scene_assessment.configuration import normalize_configuration

    configuration = normalize_configuration(configuration, catalog)
    issues = document_issues(configuration, "parameters", catalog)
    rows = configuration.get("parameters") if isinstance(configuration, dict) else None
    if isinstance(rows, dict):
        metrics = [metric for metric in catalog["metrics"] if metric["rule"] == "interval"]
        issues.extend(object_issues(rows, {m["metric_id"] for m in metrics}, "/parameters"))
        for metric in metrics:
            issues.extend(parameter_issues(rows.get(metric["metric_id"]), metric))
    issues.extend(configuration_model_issues(configuration, catalog))
    return {"valid": not issues, "issues": issues}


def read_frames(raw_item, item, metrics, path):
    """Keep original indices; invalid ordering is rejected, never repaired."""
    issues = object_issues(raw_item, {"frames"}, path)
    source = raw_item.get("frames") if isinstance(raw_item, dict) else None
    if not isinstance(source, list):
        issues.append(issue(path + "/frames", "请提供按时间排列的 frames 数组。"))
        return [], issues, False
    phases = {phase["phase_id"]: index for index, phase in enumerate(item["phases"])}
    owner_ids = {key for point in item["checkpoints"] for key in point["metric_ids"]}
    allowed = {
        phase: {key for key in owner_ids if phase in metrics[key]["phase_ids"]} for phase in phases
    }
    records, counts = [], Counter()
    previous_time, previous_phase = None, -1
    ordered = True
    for index, frame in enumerate(source):
        frame_path = f"{path}/frames/{index}"
        issues.extend(
            object_issues(frame, {"timestamp_s", "phase_id", "values", "controls"}, frame_path)
        )
        if not isinstance(frame, dict):
            ordered = False
            continue
        time, phase = frame.get("timestamp_s"), frame.get("phase_id")
        if not is_number(time) or time < 0 or (previous_time is not None and time <= previous_time):
            issues.append(
                issue(
                    frame_path + "/timestamp_s", "时刻必须为非负有限数值并严格递增；系统不重排帧。"
                )
            )
            ordered = False
        else:
            previous_time = time
        if not isinstance(phase, str) or phase not in phases:
            issues.append(
                issue(frame_path + "/phase_id", "未知环节；必须使用目录给出的 phase_id。")
            )
            ordered = False
            continue
        if phases[phase] < previous_phase:
            issues.append(issue(frame_path + "/phase_id", "环节顺序错误，不能返回较早的同名环节。"))
            ordered = False
        previous_phase = phases[phase]
        counts[phase] += 1
        values = frame.get("values")
        issues.extend(object_issues(values, allowed[phase], frame_path + "/values"))
        if isinstance(values, dict):
            for equivalent in item.get("equivalent_values", []):
                supplied = [values.get(key) for key in equivalent]
                if all(is_number(value) for value in supplied) and any(
                    not math.isclose(value, supplied[0], rel_tol=0, abs_tol=1e-9)
                    for value in supplied[1:]
                ):
                    issues.append(
                        issue(
                            frame_path + "/values",
                            f"同一原始量的重复字段 {', '.join(equivalent)} 在本帧数值不一致。",
                        )
                    )
        if "controls" in frame:
            controls = frame["controls"]
            issues.extend(object_issues(controls, CONTROLS, frame_path + "/controls"))
            if isinstance(controls, dict):
                issues.extend(
                    issue(
                        frame_path + "/controls/" + key,
                        "操纵输入须为有限数值；只作解释，不参与分档。",
                    )
                    for key, value in controls.items()
                    if key in CONTROLS and not is_number(value)
                )
        records.append(
            {
                "frame_index": index,
                "timestamp_s": time,
                "phase_id": phase,
                "values": values if isinstance(values, dict) else {},
            }
        )
    for phase in item["phases"]:
        key = phase["phase_id"]
        if phase["single_frame"] and counts[key] > 1:
            issues.append(
                issue(path + "/frames", f"{key} 必须只提供一个约定状态帧，不能挑选最佳帧。")
            )
            ordered = False
    return records if ordered else [], issues, ordered


def scene_timing_issues(catalog, item_results):
    """Validate supplied common-clock phase ranges, without filling gaps or detecting events."""
    if not catalog.get("phase_sequence"):
        return []
    issues, ranges = [], {}
    for item in item_results:
        for phase in item["phase_results"]:
            key = phase["phase_id"]
            times = [point["timestamp_s"] for point in item["timeline"] if point["phase_id"] == key]
            if not times:
                continue
            current = (times[0], times[-1])
            existing = ranges.setdefault(key, [])
            if existing and any(
                not math.isclose(value, expected, rel_tol=0, abs_tol=1e-9)
                for value, expected in zip(current, existing[0], strict=True)
            ):
                issues.append(
                    issue(
                        f"/input/items/{item['item_id']}/frames",
                        f"同名环节 {key} 在不同 item 中的首末时刻不一致。",
                    )
                )
            existing.append(current)
    previous_end = None
    for key in catalog["phase_sequence"]:
        if key not in ranges:
            continue  # Missing phases already have their item-specific issue.
        start = min(pair[0] for pair in ranges[key])
        end = max(pair[1] for pair in ranges[key])
        if previous_end is not None and start + 1e-9 < previous_end:
            issues.append(
                issue(
                    "/input/phase_sequence",
                    f"环节 {key} 的时间范围与前序环节倒置或重叠；允许相邻边界同刻。",
                )
            )
        previous_end = max(previous_end, end) if previous_end is not None else end
    return issues
