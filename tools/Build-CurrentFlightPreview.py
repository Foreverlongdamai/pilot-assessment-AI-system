"""Render complete metric timelines from the evaluated supervisor-demo reports.

No raw observations are interpolated, smoothed, selected, or resampled.  The
speed target comes from each evaluated frame; tolerance offsets come from the
same report's frozen metric parameter.  The companion JSON records all points.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "examples" / "bayes-compensation-2026-09-23"
CASES = (
    ("01-proficient", "熟练表现型"),
    ("02-marginal", "勉强合格表现型"),
    ("03-unqualified", "不合格表现型"),
)
ROWS = (
    ("SCN-001", "A-S2-05", "air_taxi_airspeed_mps", "加速与保速 · 空速", "m/s"),
    ("SCN-001", "A-S2-30", "stop_x_m", "停止阶段 · X 位置", "m"),
    ("SCN-002", "A-S2-02", "hover_x_m", "定点悬停 · X 位置", "m"),
)
PHASES = {
    "acceleration": "加速",
    "hold": "保速",
    "stop": "停止阶段",
    "lower_1": "下①",
    "upper_1": "上①",
    "lower_2": "下②",
    "upper_2": "上②",
}
WIDTH, HEIGHT = 1800, 1280
COLORS = {"D": "#318057", "A": "#aa7800", "U": "#c84841"}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def finite(value: object) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def text(x: float, y: float, value: str, size: int = 16, fill: str = "#3c4a5e", **attrs) -> str:
    extra = " ".join(f'{key.replace("_", "-")}="{esc(val)}"' for key, val in attrs.items())
    return (
        f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" '
        f'fill="{fill}" {extra}>{esc(value)}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1, **attrs) -> str:
    extra = " ".join(f'{key.replace("_", "-")}="{esc(val)}"' for key, val in attrs.items())
    return (
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        f'stroke="{color}" stroke-width="{width}" {extra}/>'
    )


def segment(points: list[dict]) -> list[list[dict]]:
    """Respect provided phases; never join hover periods across transfers."""
    groups: list[list[dict]] = []
    for point in points:
        if not groups or groups[-1][-1]["phase_id"] != point["phase_id"]:
            groups.append([])
        groups[-1].append(point)
    return groups


def load_panel(directory: Path, row: tuple, case: tuple) -> dict:
    scene_id, item_id, metric_id, title, unit = row
    case_id, case_name = case
    relative = f"{scene_id}/{case_id}.report.json"
    path = directory / relative
    report = read(path)
    if report["calculation_status"] != "complete" or report["issues"]:
        raise ValueError(f"Report is incomplete or has issues: {relative}")
    items = [item for item in report["items"] if item["item_id"] == item_id]
    if len(items) != 1:
        raise ValueError(f"Expected exactly one {item_id}: {relative}")
    item = items[0]
    matches = [
        metric
        for checkpoint in item["checkpoints"]
        for metric in checkpoint["metrics"]
        if metric["metric_id"] == metric_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one metric {metric_id}: {relative}")
    metric = matches[0]
    parameter = metric["parameter"]
    if parameter != report["configuration"]["parameters"][metric_id]:
        raise ValueError(f"Metric parameter differs from configuration snapshot: {metric_id}")
    for name in ("desired", "acceptable"):
        bounds = parameter[name]
        if bounds.get("unbounded_upper") or not all(finite(bounds[k]) for k in ("lower", "upper")):
            raise ValueError(f"Preview requires finite {name} bounds: {metric_id}")
    timeline = metric["timeline"]
    if len(timeline) < 2:
        raise ValueError(f"Need at least two evaluated observations: {metric_id}")
    raw_frames = report["input"]["items"][item_id]["frames"]
    raw_applicable = [frame for frame in raw_frames if metric_id in frame["values"]]
    if len(raw_applicable) != len(timeline):
        raise ValueError(f"Timeline omits supplied metric frames: {metric_id}")
    relative_clock = metric_id == "air_taxi_airspeed_mps"
    origin = timeline[0]["timestamp_s"] if relative_clock else 0.0
    points, counts = [], Counter()
    for observed, raw in zip(timeline, raw_applicable, strict=True):
        time, value, expected = (observed[k] for k in ("timestamp_s", "value", "expected"))
        if observed["status"] != "calculated" or not all(
            finite(v) for v in (time, value, expected)
        ):
            raise ValueError(f"Preview encountered unavailable/non-finite observation: {metric_id}")
        if time != raw["timestamp_s"] or observed["phase_id"] != raw["phase_id"]:
            raise ValueError(f"Timeline changed input clock or phase: {metric_id}")
        if value != raw["values"][metric_id]:
            raise ValueError(f"Timeline observation differs from raw input snapshot: {metric_id}")
        clock = time - origin
        if relative_clock:
            if not math.isclose(clock, observed["reference_elapsed_s"], abs_tol=1e-9):
                raise ValueError("Evaluated speed clock does not use the acceleration origin")
            clock = observed["reference_elapsed_s"]
        deviation = value - expected
        grade = "U"
        for name, label in (("desired", "D"), ("acceptable", "A")):
            bounds = parameter[name]
            if bounds["lower"] <= deviation <= bounds["upper"]:
                grade = label
                break
        if grade != observed["grade"]:
            raise ValueError(f"Independent band check disagrees with evaluated grade: {metric_id}")
        if not math.isclose(deviation, observed["deviation"], abs_tol=1e-9):
            raise ValueError(f"Independent deviation check disagrees with report: {metric_id}")
        points.append({
            "frame_index": observed["frame_index"],
            "timestamp_s": time,
            "plot_time_s": clock,
            "phase_id": observed["phase_id"],
            "observed": value,
            "expected": expected,
            "desired_lower": expected + parameter["desired"]["lower"],
            "desired_upper": expected + parameter["desired"]["upper"],
            "acceptable_lower": expected + parameter["acceptable"]["lower"],
            "acceptable_upper": expected + parameter["acceptable"]["upper"],
            "grade": grade,
        })
        counts[grade] += 1
    if any(a["plot_time_s"] >= b["plot_time_s"] for a, b in zip(points, points[1:], strict=False)):
        raise ValueError(f"Metric timestamps are not strictly increasing: {metric_id}")
    count_summary = {grade: counts[grade] for grade in ("D", "A", "U")}
    if count_summary != metric["frame_distribution"]["counts"]:
        raise ValueError(f"Independent counts disagree with report: {metric_id}")
    if metric_id == "stop_x_m" and (
        len(points) != 51 or {p["phase_id"] for p in points} != {"stop"}
    ):
        raise ValueError("Current stop demonstration must contain all 51 stop frames")
    return {
        "case_id": case_id, "case_name": case_name,
        "scene_id": scene_id, "item_id": item_id, "metric_id": metric_id,
        "title": title, "unit": unit,
        "report_file": relative,
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "item_grade": item["grade"], "metric_grade": metric["grade"],
        "item_score": item["skill_quantification"].get("score"),
        "source_frame_count": len(timeline), "rendered_frame_count": len(points),
        "grade_counts": count_summary,
        "clock": "relative_to_acceleration_first_frame" if relative_clock else "original_timestamp",
        "clock_origin_s": origin,
        "parameter": parameter,
        "all_observations_equal_expected": all(p["observed"] == p["expected"] for p in points),
        "points": points,
    }


def axis_limits(panels: list[dict]) -> tuple[float, float, float]:
    values = [
        point[key] for panel in panels for point in panel["points"]
        for key in ("observed", "acceptable_lower", "acceptable_upper")
    ]
    low, high = min(values), max(values)
    span = high - low
    scale = 10 ** math.floor(math.log10(span / 5))
    step = next(f * scale for f in (1, 2, 2.5, 5, 10) if f * scale >= span / 5)
    return (
        math.floor((low - span * 0.06) / step) * step,
        math.ceil((high + span * 0.06) / step) * step,
        step,
    )


def render(panels: list[dict]) -> str:
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        '<title id="title">当前演示：完整加速保速、停止过程与定点悬停</title>',
        '<desc id="desc">九幅图使用真实评估报告的全部逐帧观测、期望值及容差。'
        '不平滑、不下采样、不重新计算参考曲线；停止阶段展示全部五十一帧。</desc>',
        '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif}'
        '.curve{fill:none;stroke-linejoin:round;stroke-linecap:round}</style>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#f3f6fa"/>',
        text(40, 49, "当前演示 · 每帧原始表现与 D / A 容差", 30, "#132b45", font_weight="700"),
        text(40, 81, "直接读取评估报告｜每行共用坐标尺度｜合成训练演示，不代表实飞标定", 17),
        line(42, 108, 79, 108, "#17212f", 2), text(90, 114, "观测值", 15),
        line(194, 108, 231, 108, "#496b69", 1.4, stroke_dasharray="6 4"),
        text(242, 114, "逐帧期望值", 15),
        '<rect x="384" y="98" width="28" height="18" fill="#cee7c3"/>',
        text(423, 114, "Desired", 15),
        '<rect x="544" y="98" width="28" height="18" fill="#fcf0bc"/>',
        text(583, 114, "Acceptable（含 Desired）", 15),
        text(846, 114, "色带之外为 Unacceptable；灰色空档为该指标不适用阶段", 15),
    ]
    limits = [axis_limits(panels[row * 3: row * 3 + 3]) for row in range(3)]
    for index, panel in enumerate(panels):
        row, col = divmod(index, 3)
        left, top = 30 + col * 590, 137 + row * 364
        x, y, plot_width, plot_height = left + 68, top + 89, 464, 193
        low, high, step = limits[row]
        points = panel["points"]
        first, last = points[0]["plot_time_s"], points[-1]["plot_time_s"]
        def xp(value, x=x, first=first, last=last, plot_width=plot_width):
            return x + (value - first) / (last - first) * plot_width

        def yp(value, y=y, high=high, low=low, plot_height=plot_height):
            return y + (high - value) / (high - low) * plot_height

        groups = segment(points)
        output.extend([
            f'<rect x="{left}" y="{top}" width="570" height="348" rx="11" '
            'fill="#ffffff" stroke="#dce3ec"/>',
            text(left + 18, top + 30, panel["case_name"], 21, "#142c46", font_weight="700"),
            text(left + 215, top + 30, panel["title"], 19, "#34475f"),
            text(left + 18, top + 56,
                 f'{len(points)} 帧 · D {panel["grade_counts"]["D"]} / '
                 f'A {panel["grade_counts"]["A"]} / U {panel["grade_counts"]["U"]} · '
                 f'检查点指标 {panel["metric_grade"]}', 14),
            text(x, y - 10, f'观测值 / {panel["unit"]}', 13),
            f'<defs><clipPath id="clip-{index}"><rect x="{x}" y="{y}" '
            f'width="{plot_width}" height="{plot_height}"/></clipPath></defs>',
            f'<rect x="{x}" y="{y}" width="{plot_width}" height="{plot_height}" fill="#eef1f5"/>',
        ])
        # Draw the two bands from each frame's evaluated expected value.  Gaps
        # between supplied phases remain gaps; no fictional states are drawn.
        for group in groups:
            gx1, gx2 = xp(group[0]["plot_time_s"]), xp(group[-1]["plot_time_s"])
            output.append(f'<rect x="{gx1:.6f}" y="{y}" width="{gx2 - gx1:.6f}" '
                          f'height="{plot_height}" fill="white"/>')
            for band, fill in (("acceptable", "#fcf0bc"), ("desired", "#cee7c3")):
                pairs = [(xp(p["plot_time_s"]), yp(p[f"{band}_upper"])) for p in group]
                pairs += [(xp(p["plot_time_s"]), yp(p[f"{band}_lower"])) for p in reversed(group)]
                coordinates = " ".join(f"{px:.6f},{py:.6f}" for px, py in pairs)
                output.append(f'<polygon points="{coordinates}" fill="{fill}"/>')
        for tick_index in range(round((high - low) / step) + 1):
            value = low + tick_index * step
            output.extend([
                line(x, yp(value), x + plot_width, yp(value), "#dce4e8", 0.65),
                text(x - 9, yp(value) + 4, number(value), 12, text_anchor="end"),
            ])
        for tick_index in range(5):
            tick = first + (last - first) * tick_index / 4
            output.extend([
                line(xp(tick), y + plot_height, xp(tick), y + plot_height + 5, "#768399"),
                text(xp(tick), y + plot_height + 21, number(tick), 12, text_anchor="middle"),
            ])
        output.extend([
            line(x, y, x, y + plot_height, "#6d7d8f", 1.1),
            line(x, y + plot_height, x + plot_width, y + plot_height, "#6d7d8f", 1.1),
            f'<g clip-path="url(#clip-{index})">',
        ])
        for group in groups:
            phase = group[0]["phase_id"]
            output.append(text((xp(group[0]["plot_time_s"]) + xp(group[-1]["plot_time_s"])) / 2,
                               y + 16, PHASES[phase], 12, "#58697c", text_anchor="middle"))
            for key, color, stroke_width, dash in (
                ("expected", "#496b69", 1.4, ' stroke-dasharray="6 4"'),
                ("observed", "#17212f", 1.7, ""),
            ):
                coordinates = " ".join(
                    f'{xp(p["plot_time_s"]):.6f},{yp(p[key]):.6f}' for p in group
                )
                data_attributes = (
                    f' data-panel="{index}" data-phase="{phase}" '
                    f'data-series="{key}" data-frame-count="{len(group)}"'
                )
                output.append(f'<polyline class="curve" points="{coordinates}" stroke="{color}" '
                              f'stroke-width="{stroke_width}"{dash}{data_attributes}/>')
        # Small dots expose every supplied observation, including coincident
        # expected/observed lines, without changing the plotted raw value.
        for point in points:
            output.append(
                f'<circle cx="{xp(point["plot_time_s"]):.6f}" cy="{yp(point["observed"]):.6f}" '
                f'r="0.85" fill="{COLORS[point["grade"]]}"><title>'
                f't={point["timestamp_s"]}; value={point["observed"]}; '
                f'expected={point["expected"]}; grade={point["grade"]}</title></circle>'
            )
        output.append("</g>")
        axis_label = "相对加速首帧 / s" if row == 0 else "原始时间 / s"
        raw_span = f'原始 {number(points[0]["timestamp_s"])}–{number(points[-1]["timestamp_s"])} s'
        note = raw_span if row == 0 else (
            "本输入该位置值始终等于目标" if panel["all_observations_equal_expected"]
            else "全部输入帧；按实际阶段断线"
        )
        output.extend([
            text(x + plot_width, top + 327, axis_label, 13, text_anchor="end"),
            text(left + 18, top + 327, note, 13, "#637086"),
        ])
    output.extend([
        text(
            40, 1261,
            "来源：同目录两场景三类 report.json；数值核验见 CURRENT_FLIGHT_PREVIEW.audit.json。",
            14,
        ),
        "</svg>",
    ])
    return "\n".join(output)


def build(directory: Path) -> tuple[str, dict]:
    panels = [load_panel(directory, row, case) for row in ROWS for case in CASES]
    svg = render(panels)
    tree = ElementTree.fromstring(svg)
    rendered = Counter()
    for polyline in tree.findall(".//{http://www.w3.org/2000/svg}polyline"):
        if polyline.attrib.get("data-series") == "observed":
            point_count = len(polyline.attrib["points"].split())
            if point_count != int(polyline.attrib["data-frame-count"]):
                raise ValueError("Serialized SVG lost observation points")
            rendered[int(polyline.attrib["data-panel"])] += point_count
    for index, panel in enumerate(panels):
        if rendered[index] != panel["source_frame_count"]:
            raise ValueError(f"Serialized SVG frame count mismatch in panel {index}")
    return svg, {
        "schema": "current-flight-preview-audit-v1",
        "source": "evaluated report metric.timeline and frozen metric.parameter",
        "observation_transform": "none",
        "smoothing": False, "downsampling": False, "baseline_comparison": False,
        "independent_input_value_check": "pass",
        "independent_deviation_and_grade_check": "pass",
        "svg_xml_parse_and_point_count_check": "pass",
        "total_rendered_observations": sum(rendered.values()),
        "panel_count": len(panels), "panels": panels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    args = parser.parse_args()
    directory = args.directory.resolve()
    svg, audit = build(directory)
    svg_path = directory / "CURRENT_FLIGHT_PREVIEW.svg"
    audit_path = directory / "CURRENT_FLIGHT_PREVIEW.audit.json"
    svg_path.write_text(svg, encoding="utf-8")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "svg": str(svg_path), "audit": str(audit_path),
        "panels": audit["panel_count"], "observations": audit["total_rendered_observations"],
        "verified": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
