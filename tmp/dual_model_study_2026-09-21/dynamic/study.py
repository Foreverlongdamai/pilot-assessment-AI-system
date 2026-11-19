"""Deterministic offline dynamic-state study; no application mutations."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / "src"))
from pilot_assessment.scene_assessment.temporal_analysis import _transition_log  # noqa: E402

THETA = ((.10, .25, .65), (.35, .63, .02), (.90, .099, .001))
PI = (1/3, 1/3, 1/3)
SCORES = (0., 50., 100.)
GRADES = ("D", "A", "U")
LOG_PI = tuple(map(math.log, PI))
TAU_OBS = 5.
TRAJECTORIES = {
    "D30_U5_D20": {"duration": 55, "history": 30},
    "D300_U5_D20": {"duration": 325, "history": 300},
    "all_A_60": {"duration": 60, "history": None},
    "flicker_DU_halfsec_30_then_D20": {"duration": 50, "history": None},
}
CONFIGS = [("fixed_skill_markov", None)] + [
    (model, tskill)
    for model in ("dynamic_raw_cpt", "dynamic_correlated")
    for tskill in (5, 20, 60)
]


def normalize(logs):
    maximum = max(logs)
    z = maximum + math.log(math.fsum(math.exp(x - maximum) for x in logs))
    return tuple(x - z for x in logs)


def logadd(a, b):
    maximum = max(a, b)
    return maximum + math.log(math.exp(a - maximum) + math.exp(b - maximum))


def predict(logp, dt, tskill):
    if tskill is None or dt == 0:
        return logp
    log_retain = -dt / tskill
    log_refresh = math.log(-math.expm1(-dt / tskill))
    return tuple(logadd(log_retain + x, log_refresh + prior) for x, prior in zip(logp, LOG_PI))


def observation(model, grade, previous, dt):
    column = GRADES.index(grade)
    if previous is None or model == "dynamic_raw_cpt":
        return tuple(math.log(row[column]) for row in THETA)
    return tuple(_transition_log(row[column], grade == previous, dt, TAU_OBS) for row in THETA)


def advance(logp, model, tskill, dt, grades, previous):
    """One predicted prior followed by conditionally independent CP likelihoods."""
    predicted = predict(logp, dt, tskill)
    likelihoods = [observation(model, grade, last, dt) for grade, last in zip(grades, previous)]
    updated = normalize(tuple(predicted[s] + math.fsum(row[s] for row in likelihoods) for s in range(3)))
    old_odds = logp[2] - logp[0]
    predicted_odds = predicted[2] - predicted[0]
    cp_llrs = [row[2] - row[0] for row in likelihoods]
    new_odds = updated[2] - updated[0]
    residual = new_odds - (old_odds + (predicted_odds - old_odds) + math.fsum(cp_llrs))
    return updated, {
        "previous_log_odds_H_L": old_odds,
        "predicted_log_odds_H_L": predicted_odds,
        "prediction_drift_log_odds": predicted_odds - old_odds,
        "checkpoint_log_likelihood_ratios_H_L": cp_llrs,
        "posterior_log_odds_H_L": new_odds,
        "identity_residual": residual,
    }


def grade_at(name, tick, hz):
    specification = TRAJECTORIES[name]
    history = specification["history"]
    if history is not None:
        return "U" if history * hz <= tick < (history + 5) * hz else "D"
    if name == "all_A_60":
        return "A"
    if tick < 30 * hz:
        return "D" if (tick * 2 // hz) % 2 == 0 else "U"
    return "D"


def snapshot(logp):
    probs = tuple(math.exp(x) for x in logp)
    assert all(math.isfinite(p) and 0 <= p <= 1 for p in probs)
    assert abs(math.fsum(probs) - 1) < 2e-12
    return {"posterior": probs, "score": math.fsum(p * v for p, v in zip(probs, SCORES))}


def run(name, hz, model, tskill):
    specification = TRAJECTORIES[name]
    history = specification["history"]
    logp = LOG_PI
    previous = None
    common = {}
    points = {}
    latency = {"U_score_le25_s": None, "U_Plow_ge_half_s": None,
               "D_return_score_ge75_s": None, "D_return_Phigh_ge_half_s": None}
    max_residual = 0.
    targets = {"final": specification["duration"] * hz}
    if history is not None:
        targets["pre_U_last_sample"] = history * hz - 1
        for elapsed in (0, .1, 1, 4.9):
            targets[f"U_elapsed_{elapsed:g}s"] = round((history + elapsed) * hz)
        for elapsed in (0, .1, 1, 5, 20):
            targets[f"D_return_elapsed_{elapsed:g}s"] = round((history + 5 + elapsed) * hz)
    for tick in range(specification["duration"] * hz + 1):
        grade = grade_at(name, tick, hz)
        logp, decomposition = advance(logp, model, tskill, 0 if tick == 0 else 1/hz, [grade], [previous])
        previous = grade
        value = snapshot(logp)
        max_residual = max(max_residual, abs(decomposition["identity_residual"]))
        if tick % (hz // 10) == 0:
            common[tick * 10 // hz] = {"timestamp_s": tick/hz, "grade": grade, **value}
        for key, target in targets.items():
            if tick == target:
                points[key] = {"timestamp_s": tick/hz, "grade": grade, **value, **decomposition}
        if history is not None and history * hz <= tick < (history + 5) * hz:
            for key, met in (("U_score_le25_s", value["score"] <= 25),
                             ("U_Plow_ge_half_s", value["posterior"][0] >= .5)):
                if met and latency[key] is None:
                    latency[key] = (tick - history * hz) / hz
        if history is not None and tick >= (history + 5) * hz:
            for key, met in (("D_return_score_ge75_s", value["score"] >= 75),
                             ("D_return_Phigh_ge_half_s", value["posterior"][2] >= .5)):
                if met and latency[key] is None:
                    latency[key] = (tick - (history + 5) * hz) / hz
    assert max_residual < 1e-10
    identifier = f"{name}__{model}__T{tskill}__{hz}Hz"
    return {"run_id": identifier, "trajectory": name, "hz": hz, "model": model,
            "Tskill_s": tskill, "samples": specification["duration"] * hz + 1,
            "snapshots": points, "diagnostic_latencies": latency,
            "max_log_odds_identity_error": max_residual}, common


def verify_math():
    transition_error = 0.
    for dt in (.001, .01, .1, 1., 100.):
        r = -math.expm1(-dt / TAU_OBS)
        for row in THETA:
            for theta in row:
                for same in (False, True):
                    actual = math.exp(_transition_log(theta, same, dt, TAU_OBS))
                    expected = (math.exp(-dt / TAU_OBS) if same else 0) + r * theta
                    transition_error = max(transition_error, abs(actual - expected))
    assert transition_error < 1e-14
    semigroup_error = 0.
    for tskill in (5, 20, 60):
        def matrix(dt):
            h = -math.expm1(-dt/tskill)
            return [[(1-h if i == j else 0) + h*PI[j] for j in range(3)] for i in range(3)]
        left, right, direct = matrix(.07), matrix(.13), matrix(.2)
        for row in direct:
            assert abs(sum(row)-1) < 1e-14 and min(row) >= 0
        for i in range(3):
            for j in range(3):
                semigroup_error = max(semigroup_error, abs(sum(left[i][k]*right[k][j] for k in range(3))-direct[i][j]))
    assert semigroup_error < 1e-14
    # Independent direct linear update check for a nonsaturated short sequence.
    linear = list(PI)
    logs = LOG_PI
    previous = None
    posterior_error = 0.
    for grade in ("D", "D", "A", "A", "U", "U", "D"):
        index = GRADES.index(grade)
        for state in range(3):
            likelihood = THETA[state][index] if previous is None else (
                math.exp(-.1/TAU_OBS)*(grade == previous)
                + (-math.expm1(-.1/TAU_OBS))*THETA[state][index])
            linear[state] *= likelihood
        total = sum(linear)
        linear = [p/total for p in linear]
        logs, _ = advance(logs, "fixed_skill_markov", None, 0 if previous is None else .1, [grade], [previous])
        posterior_error = max(posterior_error, *(abs(math.exp(logs[s])-linear[s]) for s in range(3)))
        previous = grade
    assert posterior_error < 1e-14
    # Independently enumerate all latent-state paths (no filtering recursion).
    # This checks transition orientation, the predicted prior, and the new DBN
    # observation assumption against their finite joint probability model.
    joint_reference_error = 0.
    grades = tuple("DDUAD")
    dt = .1
    for model in ("dynamic_raw_cpt", "dynamic_correlated"):
        for tskill in (5, 20, 60):
            h = -math.expm1(-dt/tskill)
            joint_totals = [0., 0., 0.]
            for path in itertools.product(range(3), repeat=len(grades)):
                joint = PI[path[0]] * THETA[path[0]][GRADES.index(grades[0])]
                for t in range(1, len(grades)):
                    joint *= ((1-h) if path[t-1] == path[t] else 0) + h*PI[path[t]]
                    theta = THETA[path[t]][GRADES.index(grades[t])]
                    likelihood = theta if model == "dynamic_raw_cpt" else (
                        math.exp(-dt/TAU_OBS)*(grades[t] == grades[t-1])
                        + (-math.expm1(-dt/TAU_OBS))*theta)
                    joint *= likelihood
                joint_totals[path[-1]] += joint
            joint_sum = sum(joint_totals)
            joint_posterior = [value/joint_sum for value in joint_totals]
            filtered = LOG_PI
            previous = None
            for grade in grades:
                filtered, _ = advance(filtered, model, tskill, 0 if previous is None else dt, [grade], [previous])
                previous = grade
            joint_reference_error = max(joint_reference_error, *(abs(math.exp(filtered[s])-joint_posterior[s]) for s in range(3)))
    assert joint_reference_error < 1e-14
    return {"transition_formula_max_error": transition_error,
            "A_semigroup_max_error": semigroup_error,
            "fixed_short_sequence_linear_reference_max_error": posterior_error,
            "dynamic_enumerated_joint_reference_max_error": joint_reference_error}


def decomposition_example():
    logs, previous = LOG_PI, [None, None]
    rows = []
    for tick, grades in enumerate(zip("DDUUD", "AAADD")):
        logs, decomposition = advance(logs, "dynamic_correlated", 20, .1 if tick else 0, grades, previous)
        rows.append({"time_s": tick/10, "checkpoint_grades": grades,
                     **snapshot(logs), **decomposition})
        previous = grades
    return rows


def render_summary(result):
    lines = ["# Offline dynamic-state comparison", "", "Synthetic grades only. No application changes, fitted parameters, real-pilot accuracy or training-effectiveness claim.", "",
             "56 deterministic runs; theta/pi/tau as PLAN.md. EAP=0*P(L)+50*P(M)+100*P(H). Raw-frame CPT is a negative control, not a recommended observation model.", "",
             "## 主要发现（中文）", "",
             "1. 固定能力模型有历史锁定：300 秒 D 后，5 秒 U 全段仍约 100 分；30 秒 D 后则在首次 U 降至 60.75，U+4.9 秒降至 47.42。这里比较的是相同后续轨迹，仅改变前段历史时长。",
             "2. 动态状态改善历史锁定，但观测模型仍需调整。相关观测 DBN 的 Tskill=20 秒时，300 秒 D 后首次 U 降至 3.25；持续 U 到 4.9 秒却回升至 9.87。原因是状态预测向均匀先验漂移，而同档 U 的新证据较弱，不能把这个行为解释成飞行员已经恢复。",
             "3. 仅逐帧使用 CPT 的真正 HMM 是负对照：100 Hz 下约 0.01 秒达到 EAP<=25，回 D 约 0.04 秒达到 EAP>=75（Tskill=20）。10/100 Hz 同时刻曲线最大差 86.07 分，暴露原始帧独立似然的采样率依赖。",
             "4. 相关观测 DBN 在本实验所有采样对比中的最大 EAP 差为 0.1492 分；这是这些规则合成轨迹上的近似一致，不能据此宣称任意数据严格采样率不变。",
             "5. Tskill 会实质改变含义：Tskill=5 时长期 D 稳态仅约 63.62 分，恢复后的 20 秒也未越过诊断阈值 75；Tskill=20/60 回 D 后约 14 秒越过 75。故不能把该时间常数直接命名为真实能力恢复时间。",
             "6. 每 0.5 秒 D/U 切换 30 秒后再维持 D 20 秒，固定模型仍约 0 分；相关 DBN 的 Tskill=5/20/60 末点分别约 63.19/71.19/57.38。切换次数也是关键证据来源，必须检查噪声抖动的影响。", "",
             "## Adverse interval and return to D (100 Hz)", "",
             "Numbers are EAP; U+4.9s is a common timestamp before the grade returns to D. 'None' means no threshold crossing in the observed segment.", "",
             "| Earlier D | Model | Tskill | pre-U | first U | U+4.9s | first return D | D+5s | D+20s | U <=25 latency | return >=75 latency |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for run_result in result["runs"]:
        if run_result["hz"] != 100 or not run_result["trajectory"].startswith("D"):
            continue
        p = run_result["snapshots"]
        values = [p[key]["score"] for key in ("pre_U_last_sample", "U_elapsed_0s", "U_elapsed_4.9s", "D_return_elapsed_0s", "D_return_elapsed_5s", "D_return_elapsed_20s")]
        l = run_result["diagnostic_latencies"]
        lines.append(f"| {TRAJECTORIES[run_result['trajectory']]['history']} | {run_result['model']} | {run_result['Tskill_s']} | " + " | ".join(f"{x:.3f}" for x in values) + f" | {l['U_score_le25_s']} | {l['D_return_score_ge75_s']} |")
    lines += ["", "## Sampling dependence: 10 versus 100 Hz", "", "All metrics compare identical physical timestamps and grades. The sample paths between those timestamps differ only by the number of samples.", "",
              "| Trajectory | Model | Tskill | Max EAP difference | EAP RMSE | Max state-probability difference | Final EAP difference |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for pair in result["sampling_comparisons"]:
        lines.append(f"| {pair['trajectory']} | {pair['model']} | {pair['Tskill_s']} | {pair['max_absolute_score_difference']:.6f} | {pair['score_rmse']:.6f} | {pair['max_absolute_state_probability_difference']:.6f} | {pair['final_absolute_score_difference']:.6f} |")
    lines += ["", "## All-A and repeated D/U switching (100 Hz endpoints)", "",
              "| Trajectory | Model | Tskill | Final P(L), P(M), P(H) | Final EAP |", "|---|---|---:|---|---:|"]
    for run_result in result["runs"]:
        if run_result["hz"] == 100 and not run_result["trajectory"].startswith("D"):
            p = run_result["snapshots"]["final"]
            lines.append(f"| {run_result['trajectory']} | {run_result['model']} | {run_result['Tskill_s']} | " + ", ".join(f"{x:.6f}" for x in p["posterior"]) + f" | {p['score']:.6f} |")
    lines += ["", "## Log-odds explanation", "",
              "For H versus L: new posterior log odds = previous posterior log odds + prediction drift + sum of checkpoint conditional log-likelihood ratios. The score is a nonlinear posterior summary, so those terms are not additive EAP points. They are model evidence terms, not causal contributions. Combining checkpoints assumes their conditional independence under the specified state/observation history.", "",
              "Two-checkpoint correlated DBN example, Tskill=20s, dt=0.1s:", "",
              "| Time | CP grades | Previous log odds | Prediction drift | CP1 log LR | CP2 log LR | New log odds |", "|---:|---|---:|---:|---:|---:|---:|"]
    for row in result["two_checkpoint_decomposition"]:
        a, b = row["checkpoint_log_likelihood_ratios_H_L"]
        lines.append(f"| {row['time_s']:.1f} | {'/'.join(row['checkpoint_grades'])} | {row['previous_log_odds_H_L']:.6f} | {row['prediction_drift_log_odds']:.6f} | {a:.6f} | {b:.6f} | {row['posterior_log_odds_H_L']:.6f} |")
    lines += ["", "## Limits and parameter meaning", "",
              "- The dynamic state is an explicit added modelling assumption. A(dt) refreshes toward the uniform pi; it describes neither monotonic skill improvement nor a learned flight-skill transition law.",
              "- A true DBN alone does not repair an observation model. With the correlated likelihood, a D->U switch is much more informative than another U frame; persistent U can coexist with prediction drift toward pi. Inspect both first-U and end-U posteriors.",
              "- Sampling-rate agreement on these four noiseless piecewise-constant trajectories is not proof of invariance for arbitrary noisy trajectories. Flicker is a deliberately adverse observation-history test.",
              "- 30s versus 300s is a history-length comparison within one synthetic session, not cross-session inheritance.",
              "- No parameter is selected as calibrated or validated. The static whole-attempt BN is a separate study.", "",
              "## Verification", "", "All 56 runs completed with finite normalized posteriors. The run script asserted source-transition agreement, a direct linear reference, independently enumerated joint latent-state paths for both dynamic models, A row sums and semigroup, and log-odds identity. Grade alignment was asserted at every common timestamp.", "", "```json", json.dumps(result["verification"], indent=2), "```", "",
              "Run: the existing project `.venv/Scripts/python.exe` with the absolute path to `dynamic/study.py`. Outputs: results.json (parameters, snapshots, latencies, comparisons, provenance), traces_common_10hz.csv (all models at shared timestamps), SUMMARY.md (this file)."]
    return "\n".join(lines) + "\n"


def main():
    assert (HERE / "PLAN.md").exists(), "Write PLAN.md before execution."
    verification = verify_math()
    source = PROJECT / "src/pilot_assessment/scene_assessment/temporal_analysis.py"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "synthetic deterministic offline dynamics; application unchanged",
              "theta": THETA, "pi": PI, "state_scores": SCORES, "tau_observation_s": TAU_OBS,
              "trajectories": TRAJECTORIES, "runs": [], "sampling_comparisons": [],
              "two_checkpoint_decomposition": decomposition_example(),
              "verification": verification,
              "provenance": {"python": sys.executable, "version": sys.version,
                             "transition_source": str(source), "transition_source_sha256": source_hash,
                             "study_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    with (HERE / "traces_common_10hz.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "trajectory", "model", "Tskill_s", "hz", "time_s", "grade", "P_L", "P_M", "P_H", "EAP"])
        for name in TRAJECTORIES:
            for model, tskill in CONFIGS:
                curves = {}
                for hz in (10, 100):
                    run_result, common = run(name, hz, model, tskill)
                    result["runs"].append(run_result)
                    curves[hz] = common
                    for row in common.values():
                        writer.writerow([run_result["run_id"], name, model, tskill, hz,
                                         row["timestamp_s"], row["grade"], *row["posterior"], row["score"]])
                differences, probability_differences = [], []
                assert curves[10].keys() == curves[100].keys()
                for time_tick, left in curves[10].items():
                    right = curves[100][time_tick]
                    assert left["grade"] == right["grade"]
                    differences.append(abs(left["score"]-right["score"]))
                    probability_differences.extend(abs(a-b) for a,b in zip(left["posterior"], right["posterior"]))
                result["sampling_comparisons"].append({"trajectory": name, "model": model, "Tskill_s": tskill,
                    "common_timestamps": len(differences), "max_absolute_score_difference": max(differences),
                    "score_rmse": math.sqrt(math.fsum(x*x for x in differences)/len(differences)),
                    "max_absolute_state_probability_difference": max(probability_differences),
                    "final_absolute_score_difference": differences[-1]})
    assert len(result["runs"]) == 56
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    verification.update({"completed_runs": len(result["runs"]), "sampling_pairs": len(result["sampling_comparisons"]),
        "max_log_odds_identity_error": max(row["max_log_odds_identity_error"] for row in result["runs"]),
        "application_transition_source_unchanged": True})
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (HERE / "SUMMARY.md").write_text(render_summary(result), encoding="utf-8")
    print(json.dumps({"runs": len(result["runs"]), "verification": verification, "output": str(HERE)}, indent=2))


if __name__ == "__main__":
    main()
