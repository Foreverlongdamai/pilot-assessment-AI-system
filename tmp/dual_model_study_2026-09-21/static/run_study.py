"""Deterministic CPU-only synthetic model study; writes only beside this file."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
PROCESS_START = time.perf_counter()
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.special import logsumexp
from scipy.stats import beta

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from pilot_assessment.scene_assessment.demo_quantification import (  # noqa: E402
    EVIDENCE_STRENGTH,
    distribution_posterior,
)

START = time.perf_counter()
PRIOR = np.full(3, 1 / 3)
SCORES = np.array([0., 50., 100.])
BASE = np.array([[.10, .25, .65], [.35, .63, .02], [.90, .099, .001]])
STRICT = np.array([[.005, .045, .95], [.05, .9, .05], [.95, .045, .005]])
FLAT = .5 * BASE + .5 * np.full((3, 3), 1 / 3)
STRICT_MLR = np.array([[.001, .049, .95], [.05, .9, .05], [.95, .049, .001]])
FLAT_MLR = np.sqrt(BASE) / np.sqrt(BASE).sum(axis=1, keepdims=True)
CPTS = {"baseline": BASE, "stricter": STRICT, "flatter": FLAT,
        "stricter_MLR": STRICT_MLR, "flatter_MLR": FLAT_MLR}
CASES = {
    "pureD": [1., 0., 0.],
    "pureA": [0., 1., 0.],
    "pureU": [0., 0., 1.],
    "90D_10A": [.9, .1, 0.],
    "70D_30A": [.7, .3, 0.],
    "70D_20A_10U": [.7, .2, .1],
    "50D_50U": [.5, 0., .5],
    "20D_70A_10U": [.2, .7, .1],
    "45D_45A_10U": [.45, .45, .1],
    "60D_38A_02U": [.6, .38, .02],
}
GRID_COUNTS = np.array([(d, a, 50-d-a) for d in range(51) for a in range(51-d)])
GRID = GRID_COUNTS / 50
MIXED = (GRID > 0).sum(axis=1) > 1
DIRECTIONS = {"U_to_A": (2, 1), "A_to_D": (1, 0), "U_to_D": (2, 0)}


def latent(r, cpt, strength):
    r = np.asarray(r, dtype=float)
    logs = np.log(PRIOR) + strength * (r @ np.log(cpt).T)
    posterior = np.exp(logs - logsumexp(logs, axis=-1, keepdims=True))
    return posterior, posterior @ SCORES


def predictive(r, alpha0, exposure):
    r = np.asarray(r, dtype=float)[..., ::-1]  # observed D/A/U -> predictive U/A/D
    parameters = alpha0 / 3 + exposure * r
    posterior_mean = parameters / (alpha0 + exposure)
    return posterior_mean, posterior_mean @ SCORES


def dirichlet_details(r, alpha0, exposure):
    q, mean = predictive(r, alpha0, exposure)
    parameters = alpha0 / 3 + exposure * np.asarray(r)[::-1]
    total = float(parameters.sum())
    ci = [beta.ppf([.025, .975], a, total - a).tolist() for a in parameters]
    variance = float((q @ (SCORES**2) - mean**2) / (total + 1))
    # Independent algebraic identity using the exact Dirichlet covariance.
    covariance = (np.diag(q) - np.outer(q, q)) / (total + 1)
    assert np.isclose(variance, SCORES @ covariance @ SCORES, rtol=1e-10, atol=1e-10)
    return {
        "posterior_predictive_grade_UAD": q.tolist(),
        "posterior_dirichlet_parameters_UAD": parameters.tolist(),
        "expected_grade_score": float(mean),
        "grade_frequency_marginal_95pct_CI_UAD": ci,
        "expected_grade_score_posterior_SD": variance**.5,
        "raw_empirical_grade_score": float(np.asarray(r)[::-1] @ SCORES),
    }


def mlr_audit(cpt):
    violations = []
    for low in range(2):
        for good in range(3):
            for bad in range(good + 1, 3):
                left = cpt[low+1, good] * cpt[low, bad]
                right = cpt[low+1, bad] * cpt[low, good]
                if left + 1e-12 < right:
                    violations.append({"lower_row": "LMH"[low], "higher_row": "LMH"[low+1],
                                       "good_grade": "DAU"[good], "bad_grade": "DAU"[bad],
                                       "left_product": float(left), "right_product": float(right)})
    return {"satisfies_monotone_likelihood_ratio": not violations, "violations": violations}


def grid_audit(evaluator, component_labels):
    probabilities, scores = evaluator(GRID)
    assert np.isfinite(probabilities).all() and np.isfinite(scores).all()
    assert np.max(np.abs(probabilities.sum(axis=1) - 1)) < 1e-11
    saturated = (probabilities > .99) & MIXED[:, None]
    directed = {}
    for name, (bad, good) in DIRECTIONS.items():
        valid = GRID_COUNTS[:, bad] >= 1
        before = GRID[valid].copy()
        after = before.copy()
        after[:, bad] -= .02
        after[:, good] += .02
        after[np.abs(after) < 1e-15] = 0.
        pb, sb = evaluator(before)
        pa, sa = evaluator(after)
        delta = sa - sb
        violations = np.flatnonzero(delta < -1e-9)
        ordered = violations[np.argsort(delta[violations])][:2]
        directed[name] = {
            "comparisons": int(valid.sum()),
            "violation_count": len(violations),
            "minimum_score_delta": float(delta.min()),
            "worst_examples": [
                {"before_DAU": before[i].tolist(), "after_DAU": after[i].tolist(),
                 "before_probabilities": pb[i].tolist(), "after_probabilities": pa[i].tolist(),
                 "before_score": float(sb[i]), "after_score": float(sa[i]), "delta_score": float(delta[i])}
                for i in ordered
            ],
        }
    saturation_examples = {}
    for component, label in enumerate(component_labels):
        candidates = np.flatnonzero(saturated[:, component])
        chosen = candidates[np.argmax(probabilities[candidates, component])] if len(candidates) else None
        saturation_examples[label] = None if chosen is None else {
            "r_DAU": GRID[chosen].tolist(), "probabilities": probabilities[chosen].tolist(),
            "score": float(scores[chosen]),
        }
    return {
        "grid_points": len(GRID), "mixed_points": int(MIXED.sum()),
        "mixed_saturation_count_any_component_gt_0_99": int(np.any(saturated, axis=1).sum()),
        "mixed_saturation_counts_by_component": dict(zip(component_labels, saturated.sum(axis=0).tolist())),
        "mixed_max_component_probability": float(probabilities[MIXED].max()),
        "mixed_saturation_examples": saturation_examples,
        "directed_grade_improvements": directed,
        "total_monotonicity_violation_count": sum(v["violation_count"] for v in directed.values()),
    }


def runtime_check():
    evidence = {"states": list("DAU"), "probabilities": BASE.tolist()}
    max_probability_error = max_score_error = repeat_error = 0.
    for r in CASES.values():
        expected_p, expected_s = latent(r, BASE, 3)
        for copies in [1, 10, 1000]:
            counts = np.asarray(r) * 100 * copies
            proportions = dict(zip("DAU", (counts / counts.sum()).tolist()))
            got_p, got_s = distribution_posterior(PRIOR.tolist(), SCORES.tolist(), [(evidence, proportions, 1.)])
            max_probability_error = max(max_probability_error, float(np.max(np.abs(expected_p - got_p))))
            max_score_error = max(max_score_error, abs(float(expected_s - got_s)))
            repeat_error = max(repeat_error, float(np.max(np.abs(expected_p - got_p))))
    assert EVIDENCE_STRENGTH == 3
    assert max_probability_error < 1e-12 and max_score_error < 1e-10
    source = PROJECT / "src/pilot_assessment/scene_assessment/demo_quantification.py"
    return {"runtime_source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "runtime_function": "distribution_posterior", "runtime_evidence_strength": EVIDENCE_STRENGTH,
            "max_probability_difference": max_probability_error, "max_score_difference": max_score_error,
            "raw_count_repetition_factors": [1, 10, 1000], "repeat_max_probability_difference": repeat_error}


def markdown(results):
    lines = ["# 静态整段模型离线比较", "", "本实验只检查数学行为；CPT、先验和分值均为未校准示例，未测准确率。",
             "", "观察列始终为 D/A/U；离散潜在状态输出为 L/M/H，分值为 0/50/100。Dirichlet 输出为下一次可比观察的 U/A/D 预测概率，不能解释成飞行员属于低/中/高能力的概率。",
             "", "## 当前实现和公式", "",
             "已直接调用当前 `demo_quantification.distribution_posterior` 复核：",
             "", "`p_s = softmax(log(pi_s) + k * sum_g r_g * log(CPT[s,g]))`；单检查点 k=3，多检查点使用固定 1/K 权重。`EAP = 0*p_L + 50*p_M + 100*p_H`。",
             "", "固定 k 的一般化贝叶斯模型只随比例变化。独立证据模型把 k 换成有效独立观察数 N；这里 N*r 为理想化有效计数，非整数时不是实际采集的整数样本。",
             "", "`q | r,N ~ Dirichlet(alpha0/3 + N*r_UAD)`；`E[q] = (alpha0/3 + N*r_UAD)/(alpha0+N)`；预测分数 `50*E[q_A]+100*E[q_D]`。下表中的 Dirichlet 分数和分类模型 EAP 含义不同。",
             "", "## 固定案例", "",
             "| 方案 | pureD | pureA | pureU | 90D10A | 70D30A | 70D20A10U | 50D50U | 20D70A10U | 45D45A10U | 60D38A02U |",
             "|---|" + "---:|" * 10]
    for scheme, entry in results["schemes"].items():
        scores = [value.get("latent_EAP", value.get("expected_grade_score")) for value in entry["cases"].values()]
        lines.append("| " + scheme + " | " + " | ".join(f"{s:.3f}" for s in scores) + " |")
    lines += ["", "## 混合比例网格与单调性", "",
              "网格步长 .02，共 1326 个比例点，其中 1323 个混合点。每种模型检查 3825 次 .02 改善；混合饱和定义为任一分量严格大于 .99。仅改变一个观察比例，其他参数固定。",
              "", "| 方案 | 混合饱和数 | L/M/H 或 U/A/D 分量饱和数 | 改善却降分次数 | pureA 的 M 或 A 概率 |", "|---|---:|---|---:|---:|"]
    for scheme, entry in results["schemes"].items():
        audit = entry["grid_audit"]
        pure = entry["cases"]["pureA"]
        p = pure.get("latent_posterior_LMH", pure.get("posterior_predictive_grade_UAD"))
        counts = "/".join(str(v) for v in audit["mixed_saturation_counts_by_component"].values())
        lines.append(f"| {scheme} | {audit['mixed_saturation_count_any_component_gt_0_99']} | {counts} | {audit['total_monotonicity_violation_count']} | {p[1]:.8f} |")
    lines += ["", "## 已观察到的关键结果", ""]
    base3 = results["schemes"]["fixed_k3_baseline"]
    for key in ["pureD", "pureA", "pureU", "70D_20A_10U", "50D_50U"]:
        row = base3["cases"][key]
        lines.append(f"- 当前 k=3，{key}：p(L/M/H)={np.round(row['latent_posterior_LMH'], 6).tolist()}，EAP={row['latent_EAP']:.6f}。")
    for name in ["independent_N10000_baseline", "independent_N100_stricter", "fixed_k3_stricter", "fixed_k3_flatter", "fixed_k3_stricter_MLR", "independent_N100_stricter_MLR", "fixed_k3_flatter_MLR", "independent_N100_flatter_MLR"]:
        audit = results["schemes"][name]["grid_audit"]
        lines.append(f"- {name}：1323 个混合点中 {audit['mixed_saturation_count_any_component_gt_0_99']} 个出现 >.99；分量计数 {audit['mixed_saturation_counts_by_component']}；单调性违反 {audit['total_monotonicity_violation_count']} 次。")
    for name in ["fixed_k3_stricter", "fixed_k3_flatter", "independent_N100_flatter"]:
        examples = []
        for direction, audit in results["schemes"][name]["grid_audit"]["directed_grade_improvements"].items():
            for example in audit["worst_examples"]:
                examples.append((example["delta_score"], direction, example))
        _, direction, example = sorted(examples)[0]
        lines.append(f"- 具体逆序：{name} 的 {direction}，D/A/U 从 {np.round(example['before_DAU'], 3).tolist()} 改善至 {np.round(example['after_DAU'], 3).tolist()}，分数 {example['before_score']:.6f} → {example['after_score']:.6f}。")
    lines += ["", "## 更多真实独立证据与重复原始帧", "",
              "当前运行函数在计数整体重复 1/10/1000 倍时，结果不变（数值误差见 results.json）。Dirichlet 必须以有效独立暴露 N 为输入，重复同一批帧时 N 也应保持不变；否则人为缩窄区间。",
              "", "例如比例 70D/20A/10U，Dirichlet alpha0=1：", "",
              "| 有效 N | 预测 U/A/D | 预测分数 | D 比例 95% 可信区间 | 分数后验标准差 |", "|---:|---|---:|---|---:|"]
    for n in [10, 100, 10000]:
        row = results["schemes"][f"dirichlet_alpha1_N{n}"]["cases"]["70D_20A_10U"]
        lines.append(f"| {n} | {np.round(row['posterior_predictive_grade_UAD'], 6).tolist()} | {row['expected_grade_score']:.6f} | {np.round(row['grade_frequency_marginal_95pct_CI_UAD'][2], 6).tolist()} | {row['expected_grade_score_posterior_SD']:.6f} |")
    lines += ["", "## 解释边界", "",
              "- 大 N 下离散分类后验集中，表示在有限的几种预设 CPT 行中越来越确定哪一行最吻合；不表示所有帧都属于同一等级。严格 CPT 仍会把一整片混合比例判为某个状态，甚至把饱和移到 M。",
              "- 减小 k 或把 CPT 拉平可以缓解给定参数下的集中，也会减弱纯 D/U 的确定性。这是参数敏感性结果，不能单凭视觉温和程度选最终参数。",
              "- 只增加对角概率不保证改善观察后分数单调。需单独检查单调似然比；本次提供的严格示例仅作对照，不是推荐配置。",
              "- 两个补充 MLR 对照分别保持严格 CPT 的单调性、通过逐行平方根归一化降低 CPT 区分度。它们将单调性问题与离散状态集中问题分开；即使完全满足单调性，大 N 仍会集中到某个离散状态。所有 CPT 明确保存在 results.json，计划文件记录补充对照加入的理由。",
              "- Dirichlet 预测均值随混合比例变化，其不确定性随有效独立信息增加而缩小；它估计可比条件下的等级发生倾向。把它命名为能力仍需要任务覆盖、条件可比性与外部标签验证。",
              "- 连续模型不可能让纯 D 的概率 >.99，却保证所有无限接近纯 D 的混合输入都 ≤.99。若要求字面意义上的“只有全 D 才接近 1”，先定义接近的阈值和最小非 D 占比；本研究不添加硬截断。近纯案例保存在 results.json。",
              "", "## 复现与验证", "",
              f"实际数值计算及结果汇总耗时：{results['metadata']['measured_wall_seconds']:.6f} 秒，CPU only。",
              f"含 Python 依赖导入、截至写出前的进程耗时：{results['metadata']['process_seconds_including_imports_before_write']:.6f} 秒。",
              "运行：`pilot_assessment_system\\.venv\\Scripts\\python.exe pilot_assessment_system\\tmp\\dual_model_study_2026-09-21\\static\\run_study.py`。",
              "`results.json` 保存全部固定案例、区间、网格计数、违反单调性的具体输入与后验、CPT、版本、源文件哈希及运行基线差异。"]
    return "\n".join(lines) + "\n"


def main():
    assert len(GRID) == 1326 and MIXED.sum() == 1323 and len(CASES) == 10
    assert all(np.allclose(cpt.sum(axis=1), 1) and (cpt > 0).all() for cpt in CPTS.values())
    results = {
        "metadata": {"generated_utc": datetime.now(timezone.utc).isoformat(), "python_executable": sys.executable,
                     "python_version": platform.python_version(), "numpy_version": np.__version__,
                     "scipy_version": scipy.__version__, "cpu_only": True,
                     "interpretation": "Synthetic mathematical behavior only; no accuracy/calibration claim.",
                     "observed_order": list("DAU"), "latent_order": list("LMH"),
                     "predictive_grade_order": list("UAD"), "latent_and_predictive_scores": SCORES.tolist(),
                     "fractional_effective_counts_allowed_for_sensitivity": True,
                     "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "prior": PRIOR.tolist(), "CPTs_rows_LMH_columns_DAU": {k: v.tolist() for k, v in CPTS.items()},
        "CPT_monotone_likelihood_ratio_audits": {k: mlr_audit(v) for k, v in CPTS.items()},
        "fixed_cases_DAU": CASES, "runtime_baseline_verification": runtime_check(), "schemes": {},
    }
    specs = [(f"independent_N{n}_baseline", BASE, n, "independent_effective_exposure") for n in [10, 100, 10000]]
    specs += [(f"fixed_k{k:g}_baseline", BASE, k, "normalized_fixed_strength") for k in [.5, 1, 3, 8, 30]]
    specs += [(f"fixed_k3_{name}", CPTS[name], 3, "CPT_one_factor_at_fixed_k3") for name in ["stricter", "flatter", "stricter_MLR", "flatter_MLR"]]
    specs += [(f"independent_N100_{name}", CPTS[name], 100, "CPT_one_factor_at_independent_N100") for name in ["stricter", "flatter", "stricter_MLR", "flatter_MLR"]]
    for name, cpt, strength, family in specs:
        entry = {"family": family, "strength_or_N": strength, "cases": {}}
        for case_name, r in CASES.items():
            p, score = latent(r, cpt, strength)
            entry["cases"][case_name] = {"latent_posterior_LMH": p.tolist(), "latent_EAP": float(score)}
        entry["grid_audit"] = grid_audit(lambda r, cpt=cpt, strength=strength: latent(r, cpt, strength), list("LMH"))
        entry["near_pure_D_cases"] = [{"nonD_fraction": e, "posterior_LMH": latent([1-e, e, 0.], cpt, strength)[0].tolist()} for e in [.1, .02, .01, .001, .0001, 0.]]
        results["schemes"][name] = entry
    for alpha0 in [1, 3]:
        for exposure in [10, 100, 10000]:
            name = f"dirichlet_alpha{alpha0}_N{exposure}"
            entry = {"family": "Dirichlet_grade_predictive", "alpha_total": alpha0, "effective_exposure_N": exposure,
                     "cases": {key: dirichlet_details(r, alpha0, exposure) for key, r in CASES.items()}}
            entry["grid_audit"] = grid_audit(lambda r, a=alpha0, n=exposure: predictive(r, a, n), list("UAD"))
            assert entry["grid_audit"]["total_monotonicity_violation_count"] == 0
            entry["near_pure_D_cases"] = [{"nonD_fraction": e, "predictive_UAD": predictive([1-e, e, 0.], alpha0, exposure)[0].tolist()} for e in [.1, .02, .01, .001, .0001, 0.]]
            results["schemes"][name] = entry
    # Same exact proportions + fixed effective exposure are invariant to raw-frame duplication.
    duplicate_errors = []
    for r in CASES.values():
        raw = np.asarray(r) * 100
        a = predictive(raw / raw.sum(), 1, 100)[0]
        b = predictive(1000*raw / (1000*raw).sum(), 1, 100)[0]
        duplicate_errors.append(float(np.max(np.abs(a-b))))
    assert max(duplicate_errors) < 1e-12
    results["dirichlet_fixed_exposure_repeat_max_probability_difference"] = max(duplicate_errors)
    results["verification"] = {"probability_normalization": "PASS", "runtime_formula_agreement": "PASS",
                               "raw_frame_duplication_at_fixed_information": "PASS", "grid_and_case_counts": "PASS",
                               "Dirichlet_score_variance_identity": "PASS", "Dirichlet_monotonicity": "PASS"}
    results["metadata"]["measured_wall_seconds"] = time.perf_counter() - START
    results["metadata"]["process_seconds_including_imports_before_write"] = time.perf_counter() - PROCESS_START
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (OUT / "SUMMARY.md").write_text(markdown(results), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "schemes": len(results["schemes"]),
                      "wall_seconds": results["metadata"]["measured_wall_seconds"],
                      "verification": results["verification"],
                      "grid_results": {name: {"mixed_saturated": row["grid_audit"]["mixed_saturation_count_any_component_gt_0_99"],
                                             "monotonicity_violations": row["grid_audit"]["total_monotonicity_violation_count"]}
                                       for name, row in results["schemes"].items()}}, indent=2))


if __name__ == "__main__":
    main()
