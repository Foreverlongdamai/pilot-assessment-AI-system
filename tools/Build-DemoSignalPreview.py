"""Draw every real demo observation in a standalone, unsmoothed SVG comparison."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "examples" / "supervisor-demo-2026-09-15"
BEFORE = ROOT / "tmp" / "demo_jitter_qa" / "before" / DEFAULT.name
CASES = (
    ("01-proficient", "熟练表现型", "整体稳定，包含连续的小幅修正"),
    ("02-marginal", "勉强合格表现型", "较大的持续波动，仍在可接受范围内"),
    ("03-unqualified", "不合格表现型", "保留局部失误与后续恢复"),
)
SCENES = (
    ("SCN-001", "加速减速场景 · 保速空速", "speed_hold_airspeed_mps", "空速 / (m/s)"),
    ("SCN-002", "悬停场景 · X 方向位置", "hover_x_m", "X 位置 / m"),
)
PHASES = {
    "hold": "保速",
    "hold_end": "末端",
    "lower_1": "下方 ①",
    "upper_1": "上方 ①",
    "lower_2": "下方 ②",
    "upper_2": "上方 ②",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def observations(data: dict, metric: str) -> list[dict]:
    """Keep input order, exact timestamps and raw values; never resample."""
    matching_items = [
        item
        for item in data["items"].values()
        if any(metric in frame["values"] for frame in item["frames"])
    ]
    if len(matching_items) != 1:
        raise ValueError(f"Expected one item providing {metric}, got {len(matching_items)}")
    result = [
        {"time": frame["timestamp_s"], "phase": frame["phase_id"], "value": frame["values"][metric]}
        for frame in matching_items[0]["frames"]
        if metric in frame["values"]
    ]
    if any(not math.isfinite(point["value"]) for point in result):
        raise ValueError(f"Non-finite observation for {metric}")
    if any(a["time"] >= b["time"] for a, b in zip(result, result[1:], strict=False)):
        raise ValueError(f"Observations are not strictly ordered for {metric}")
    return result


def segments(points: list[dict]) -> list[list[dict]]:
    result: list[list[dict]] = []
    for point in points:
        if not result or point["phase"] != result[-1][-1]["phase"]:
            result.append([])
        result[-1].append(point)
    return result


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def text(x: float, y: float, value: str, size: int = 17, fill: str = "#334155", **attrs) -> str:
    extra = " ".join(f'{key.replace("_", "-")}="{esc(value)}"' for key, value in attrs.items())
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'fill="{fill}" {extra}>{esc(value)}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1, **attrs) -> str:
    extra = " ".join(f'{key.replace("_", "-")}="{esc(value)}"' for key, value in attrs.items())
    return (
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        f'stroke="{color}" stroke-width="{width}" {extra}/>'
    )


def build(directory: Path, baseline: Path) -> tuple[str, dict]:
    rows = []
    for case_id, case_name, explanation in CASES:
        for scene_id, title, metric, unit in SCENES:
            file = f"{scene_id}/{case_id}.input.json"
            current = observations(read(directory / file), metric)
            previous = observations(read(baseline / file), metric)
            parameter = read(directory / scene_id / "configuration.json")["parameters"][metric]
            old_parameter = read(baseline / scene_id / "configuration.json")["parameters"][metric]
            if parameter != old_parameter:
                raise ValueError(f"Before/after tolerance changed: {metric}")
            if [(p["time"], p["phase"]) for p in current] != [
                (p["time"], p["phase"]) for p in previous
            ]:
                raise ValueError(f"Before/after sampling changed: {file}")
            rows.append(
                dict(
                    case=case_id,
                    case_name=case_name,
                    explanation=explanation,
                    scene=scene_id,
                    title=title,
                    metric=metric,
                    unit=unit,
                    current=current,
                    previous=previous,
                    parameter=parameter,
                )
            )

    # A shared axis per scene makes the three pilot categories directly comparable.
    limits = {}
    for scene_id, *_ in SCENES:
        members = [row for row in rows if row["scene"] == scene_id]
        values = [
            point["value"]
            for row in members
            for key in ("current", "previous")
            for point in row[key]
        ]
        parameter = members[0]["parameter"]
        expected = parameter["expected"]
        values.extend(
            expected + parameter[band][side]
            for band in ("desired", "acceptable")
            for side in ("lower", "upper")
        )
        low, high = min(values), max(values)
        span = high - low
        raw_step = span / 5
        scale = 10 ** math.floor(math.log10(raw_step))
        step = next(factor * scale for factor in (1, 2, 2.5, 5, 10) if factor * scale >= raw_step)
        low = math.floor((low - span * 0.08) / step) * step
        high = math.ceil((high + span * 0.08) / step) * step
        limits[scene_id] = (low, high, step)

    output = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1440" '
        'viewBox="0 0 1600 1440" role="img" aria-labelledby="title desc">',
        '<title id="title">演示飞行数据：连续修正与局部失误</title>',
        '<desc id="desc">两个场景三类合成演示飞行数据。新数据为黑线，旧数据为灰线。'
        "逐一绘制全部原始观测点，按阶段断线，没有平滑或抽样。</desc>",
        '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif} '
        ".curve{fill:none;stroke-linejoin:round;stroke-linecap:round}</style>",
        '<rect width="1600" height="1440" fill="#f5f7fa"/>',
        text(48, 55, "演示飞行数据 · 连续修正与局部失误", 31, "#142338", font_weight="700"),
        text(
            48,
            89,
            "两场景 × 三类表现｜完整原始观测，不平滑、不抽样；灰线为修改前，黑线为修改后。",
            18,
        ),
        line(50, 124, 90, 124, "#111827", 2.2),
        text(100, 130, "新数据", 16),
        line(212, 124, 252, 124, "#9ca3af", 1.6),
        text(262, 130, "旧数据", 16),
        '<rect x="374" y="114" width="34" height="20" fill="#cfe5b5"/>',
        text(417, 130, "Desired", 16),
        '<rect x="532" y="114" width="34" height="20" fill="#fbefba"/>',
        text(575, 130, "Acceptable（含 Desired）", 16),
        line(836, 124, 876, 124, "#55765b", 1.4, stroke_dasharray="6 5"),
        text(886, 130, "期望值", 16),
        text(1080, 130, "色带以外为 Unacceptable", 16),
    ]
    summaries = []
    for index, row in enumerate(rows):
        col, row_index = index % 2, index // 2
        left, top = 40 + col * 780, 160 + row_index * 397
        x, y, width, height = left + 80, top + 97, 641, 232
        low, high, step = limits[row["scene"]]
        start, end = row["current"][0]["time"], row["current"][-1]["time"]

        def xp(t, x=x, start=start, end=end, width=width):
            return x + (t - start) / (end - start) * width

        def yp(v, y=y, high=high, low=low, height=height):
            return y + (high - v) / (high - low) * height

        output.extend(
            [
                f'<rect x="{left}" y="{top}" width="760" height="378" '
                'rx="13" fill="white" stroke="#dce2ea"/>',
                text(left + 22, top + 33, row["case_name"], 23, "#142338", font_weight="700"),
                text(left + 225, top + 33, row["title"], 20, "#34455f"),
                text(left + 22, top + 62, row["explanation"], 16, "#526174"),
                text(x, y - 12, row["unit"], 15),
                f'<defs><clipPath id="plot-{index}"><rect x="{x}" y="{y}" '
                f'width="{width}" height="{height}"/></clipPath></defs>',
            ]
        )
        parameter, expected = row["parameter"], row["parameter"]["expected"]
        for band, fill, stroke in (
            ("acceptable", "#fbefba", "#e2d077"),
            ("desired", "#cfe5b5", "#a4c481"),
        ):
            upper = yp(expected + parameter[band]["upper"])
            bottom = yp(expected + parameter[band]["lower"])
            output.append(
                f'<rect x="{x}" y="{upper:.3f}" width="{width}" '
                f'height="{bottom - upper:.3f}" fill="{fill}" stroke="{stroke}"/>'
            )
        parts = segments(row["current"])
        if row["scene"] == "SCN-002":
            for first, second in zip(parts, parts[1:], strict=False):
                gap_start, gap_end = xp(first[-1]["time"]), xp(second[0]["time"])
                output.append(
                    f'<rect x="{gap_start:.3f}" y="{y}" width="{gap_end - gap_start:.3f}" '
                    f'height="{height}" fill="#f1f3f6"/>'
                )
                output.append(
                    text(
                        (gap_start + gap_end) / 2,
                        y + 18,
                        "转换",
                        13,
                        "#8794a5",
                        text_anchor="middle",
                    )
                )
            for part in parts:
                output.append(
                    text(
                        (xp(part[0]["time"]) + xp(part[-1]["time"])) / 2,
                        y + 18,
                        PHASES.get(part[0]["phase"], part[0]["phase"]),
                        13,
                        "#637588",
                        text_anchor="middle",
                    )
                )
        count = round((high - low) / step)
        for tick_index in range(count + 1):
            value = low + tick_index * step
            output.append(line(x, yp(value), x + width, yp(value), "#dde2e8", 0.75))
            output.append(text(x - 12, yp(value) + 5, number(value), 14, text_anchor="end"))
        ticks = [
            start,
            *[
                float(t)
                for t in range(math.ceil(start / 5) * 5, math.floor(end / 5) * 5 + 1, 5)
                if start + 1 < t < end - 1
            ],
            end,
        ]
        for tick in ticks:
            output.append(line(xp(tick), y + height, xp(tick), y + height + 5, "#64748b"))
            output.append(text(xp(tick), y + height + 24, number(tick), 14, text_anchor="middle"))
        output.extend(
            [
                line(x, y, x, y + height, "#64748b", 1.2),
                line(x, y + height, x + width, y + height, "#64748b", 1.2),
                line(
                    x, yp(expected), x + width, yp(expected), "#55765b", 1.4, stroke_dasharray="6 5"
                ),
            ]
        )
        for kind, color, stroke_width in (
            ("previous", "#9ca3af", 1.6),
            ("current", "#111827", 2.2),
        ):
            output.append(
                f'<g clip-path="url(#plot-{index})" data-series="{kind}" '
                f'data-observation-count="{len(row[kind])}">'
            )
            for part in segments(row[kind]):
                vertices = " ".join(f"{xp(p['time']):.6f},{yp(p['value']):.6f}" for p in part)
                if len(part) == 1:
                    output.append(
                        f'<circle cx="{xp(part[0]["time"]):.6f}" '
                        f'cy="{yp(part[0]["value"]):.6f}" r="2.2" fill="{color}"/>'
                    )
                else:
                    output.append(
                        f'<polyline class="curve" points="{vertices}" stroke="{color}" '
                        f'stroke-width="{stroke_width}" data-phase="{esc(part[0]["phase"])}"/>'
                    )
            output.append("</g>")
        output.extend(
            [
                text(x + width / 2, y + height + 46, "任务时间 / s", 15, text_anchor="middle"),
                text(
                    left + 738,
                    top + 62,
                    f"{len(row['current'])} 帧 · {len(parts)} 段",
                    14,
                    "#637588",
                    text_anchor="end",
                ),
            ]
        )
        summaries.append(
            dict(
                scene_id=row["scene"],
                case_id=row["case"],
                metric_id=row["metric"],
                new_frame_count=len(row["current"]),
                old_frame_count=len(row["previous"]),
                phase_frame_counts={part[0]["phase"]: len(part) for part in parts},
                first_timestamp_s=start,
                last_timestamp_s=end,
            )
        )
    output.extend(
        [
            text(
                48,
                1380,
                "灰色空档表示高度转换阶段：这些帧属于另一个 item，悬停曲线不跨阶段连线。",
                16,
                "#526174",
            ),
            text(
                48,
                1410,
                "说明：这是合成数据的工程演示；波动幅值尚未通过真实飞行数据或飞行员样本验证。",
                16,
                "#526174",
            ),
            f"<metadata>{esc(json.dumps(summaries, ensure_ascii=False))}</metadata>",
            "</svg>",
        ]
    )
    return "\n".join(output) + "\n", {
        "panels": summaries,
        "method": "all raw observations; phase-separated polylines; no smoothing or resampling",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    parser.add_argument("--baseline", type=Path, default=BEFORE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    svg, metadata = build(args.directory.resolve(), args.baseline.resolve())
    output = args.output or args.directory / "SIGNAL_PREVIEW.svg"
    output.write_text(svg, encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), **metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
