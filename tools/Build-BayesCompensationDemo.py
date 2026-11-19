"""Re-evaluate existing synthetic flights with the approved CPT + compensation model.

Input bytes, rule parameters, priors and CPTs are retained from the historical
demo. New artifacts are written to a separate directory. No fitting is done.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from pilot_assessment.scene_assessment.calculator import evaluate
from pilot_assessment.scene_assessment.catalog import load_catalog
from pilot_assessment.scene_assessment.configuration import normalize_configuration

ROOT = Path(__file__).resolve().parents[1]
METHOD = "sequential_bayes_compensation_v1"
DEFAULT_SOURCE = ROOT / "examples" / "supervisor-demo-2026-09-15"
DEFAULT_OUTPUT = ROOT / "examples" / "bayes-compensation-2026-09-23"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def build(source, destination, alpha=None):
    if source.resolve() == destination.resolve():
        raise ValueError("A separate output folder is required; preserve historical evidence.")
    if alpha is not None and not 0 <= alpha <= 1:
        raise ValueError("alpha must be between 0 and 1")
    source_manifest = read(source / "manifest.json")
    manifest = {
        "title": "贝叶斯网络 · 双场景",
        "synthetic": True,
        "calibration": "uncalibrated",
        "method": METHOD,
        "compensation_alpha_override": alpha,
        "evidence_unit": "one valid frame; full CPT per frame",
        "probability_order": ["low", "middle", "high"],
        "source_directory": str(source.resolve()),
        "scenes": [],
    }
    summary = [
        "# 贝叶斯网络：实算结果",
        "",
        f"方法 `{METHOD}`；alpha 读取各 item 配置。模型及数值未经真实飞行员标定。",
        "末帧概率换算为最终分数，和过程图末点一致；不是顺序无关的整段平均分。",
        "原始 U/Fail 保留。恢复后的末帧分数可能高，不表示之前没有失误。",
        "",
    ]
    for scene in source_manifest["scenes"]:
        config = normalize_configuration(
            read(source / scene["configuration_file"]), load_catalog(scene["scene_id"])
        )
        for model in config["skill_models"].values():
            if model.get("inference_method") != METHOD:
                raise ValueError("Unknown inference method cannot be converted automatically.")
            model["model_version"] = "cpt-compensation-2026-09-23-v1"
            if alpha is not None:
                model["compensation"] = {"alpha": alpha}
        write(destination / scene["configuration_file"], config)
        entry = {
            "scene_id": scene["scene_id"],
            "name": scene["name"],
            "configuration_file": scene["configuration_file"],
            "cases": [],
        }
        summary.extend(
            [
                f"## {scene['scene_id']} {scene['name']}",
                "",
                "| 数据 | item | P(低/中/高) | 末帧分数 | 规则 |",
                "|---|---|---|---:|---|",
            ]
        )
        for case in scene["cases"]:
            raw = (source / case["input_file"]).read_bytes()
            data = json.loads(raw.decode("utf-8-sig"))
            report = evaluate(config, data)
            if report["calculation_status"] != "complete" or report["issues"]:
                raise ValueError(f"{scene['scene_id']} {case['case_id']}: {report['issues']}")
            original = read(source / case["report_file"])
            if (report["grade"], report["passed"]) != (original["grade"], original["passed"]):
                raise AssertionError("The algorithm change must not alter rule grades.")
            target = destination / case["input_file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            write(destination / case["report_file"], report)
            entry["cases"].append(
                {key: case[key] for key in ("case_id", "name", "input_file", "report_file")}
                | {"source_input_sha256": hashlib.sha256(raw).hexdigest()}
            )
            for item in report["items"]:
                result = item["skill_quantification"]
                if result["status"] == "not_applicable":
                    probabilities, score = "检查单", "—"
                else:
                    if result["status"] != "complete" or result["method"] != METHOD:
                        raise AssertionError((item["item_id"], result))
                    last = result["temporal_analysis"]["item_trace"]["timeline"][-1]
                    assert result["posterior"] == last["posterior"]
                    assert result["score"] == last["score"]
                    probabilities = " / ".join(f"{p:.4f}" for p in result["posterior"])
                    score = f"{result['score']:.3f}"
                verdict = "Pass" if item["passed"] else "Fail"
                summary.append(
                    f"| {case['name']} | {item['name']} | {probabilities} | {score} "
                    f"| {item['grade']} / {verdict} |"
                )
        manifest["scenes"].append(entry)
        summary.append("")
    write(destination / "manifest.json", manifest)
    (destination / "SUMMARY_CN.md").write_text("\n".join(summary), encoding="utf-8")
    instructions = [
        "# 手动加载新版双场景演示",
        "",
        "在软件左侧选择场景，点击加载配置，使用该场景 configuration.json；",
        "再导入同目录的 01-proficient / 02-marginal / 03-unqualified.input.json，点击开始评估。",
        "点击 item 查看贝叶斯网络全程曲线、D/A/U 色带和逐帧概率更新明细。",
        "",
        "概率内部顺序为低／中／高，对应观测目标 U／A／D。",
        "更新系数 alpha 读取各 item 配置（旧配置缺省为0.2），用于调整网络对每帧观测的响应。",
        "末帧模型分数反映最后的更新状态；失误后恢复也可能接近100，历史U和Fail仍保留。",
        "本文件夹复用原有六组人工合成飞行数据与原CPT，没有为了新分数修改输入。",
        "",
        "## 文件路径",
        "",
    ]
    for scene in manifest["scenes"]:
        instructions.append(f"- {scene['name']}配置：`{destination / scene['configuration_file']}`")
        for case in scene["cases"]:
            instructions.append(f"- {case['name']}输入：`{destination / case['input_file']}`")
    instructions.extend(["", "计算结果见 SUMMARY_CN.md；完整输入和计算过程在各 report.json。"])
    (destination / "README_CN.md").write_text("\n".join(instructions), encoding="utf-8")
    render_reports(destination, manifest)
    return manifest


def render_reports(destination, manifest):
    """Render only reports computed by the single supported inference engine."""
    display = copy.deepcopy(manifest)
    for scene in display["scenes"]:
        for case in scene["cases"]:
            full = read(destination / case["report_file"])
            case["report"] = {"items": []}
            for item in full["items"]:
                result = item["skill_quantification"]
                if result.get("status") != "not_applicable" and result.get("method") != METHOD:
                    raise ValueError("旧算法报告仅为历史记录，请先用新版重新评估后再生成展示。")
                case["report"]["items"].append(
                    {
                        "name": item["name"],
                        "grade": item["grade"],
                        "passed": item["passed"],
                        "checkpoints": [{"name": c["name"]} for c in item["checkpoints"]],
                        "skill_quantification": {
                            key: result.get(key)
                            for key in ("score", "posterior", "temporal_analysis")
                        },
                    }
                )
    payload = json.dumps(display, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload = (
        payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )
    template = (ROOT / "tools" / "templates" / "bayes-compensation.html").read_text(
        encoding="utf-8"
    )
    (destination / "index.html").write_text(template.replace("__DATA__", payload), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--alpha", type=float, help="Explicitly override every item's alpha")
    args = parser.parse_args()
    result = build(args.source, args.output, args.alpha)
    print(
        json.dumps(
            {
                "directory": str(args.output),
                "scenes": len(result["scenes"]),
                "cases": sum(len(s["cases"]) for s in result["scenes"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
