"""Offline continuous-model and demo comparisons; no production mutations.

All grade orderings here are D,A,U. N denotes a stipulated effective evidence
budget, not raw simulator frame count. A fractional likelihood power is an
engineering experiment, not proof of conditionally independent observations.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import ndtr, softmax
from scipy.stats import beta

from pilot_assessment.scene_assessment.demo_quantification import distribution_posterior


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
X = (np.arange(10001) + .5) / 10001
CASES = {
    "all_D": [1., 0., 0.], "all_A": [0., 1., 0.], "all_U": [0., 0., 1.],
    "90D10A": [.9, .1, 0.], "70D30A": [.7, .3, 0.],
    "70D20A10U": [.7, .2, .1], "50D50U": [.5, 0., .5],
    "20D70A10U": [.2, .7, .1], "45D45A10U": [.45, .45, .1],
    "60D38A2U": [.6, .38, .02],
}


def beta_model(q, n):
    a = 1 + n * (2 * q[0] + q[1])
    b = 1 + n * (2 * q[2] + q[1])
    total = a + b
    predictive = [a * (a + 1), 2 * a * b, b * (b + 1)]
    predictive = [v / (total * (total + 1)) for v in predictive]
    # These are interval-class posterior masses, distinct from predictions.
    class_prob = [float(beta.sf(.75, a, b)),
                  float(beta.cdf(.75, a, b) - beta.cdf(.25, a, b)),
                  float(beta.cdf(.25, a, b))]
    return {"mean_score": 100 * a / total,
            "score_interval95": (100 * beta.ppf([.025, .975], a, b)).tolist(),
            "predictive_D_A_U": predictive,
            "interval_class_D_A_U": class_prob,
            "alpha": a, "beta": b,
            "predictive_l1_misfit": float(np.abs(np.array(predictive) - q).sum())}


def emission(sigma, binary=False):
    if binary:
        return np.array([ndtr((X - .5) / sigma), ndtr((.5 - X) / sigma)])
    return np.array([ndtr((X - .65) / sigma),
                     ndtr((.65 - X) / sigma) - ndtr((.35 - X) / sigma),
                     ndtr((.35 - X) / sigma)])


EMISSIONS = {s: emission(s) for s in (.08, .15, .25)}


def grid_summary(logs, matrix=None, q=None):
    p = softmax(logs)
    # Each p is probability mass in a midpoint quadrature cell: its cumulative
    # mass belongs at the right cell edge, not at the midpoint.
    cdf = np.concatenate(([0.], np.cumsum(p)))
    ci = np.interp([.025, .975], cdf, np.linspace(0., 1., len(X) + 1))
    result = {"mean_score": float(100 * (p @ X)),
              "score_interval95": (100 * ci).tolist(),
              "interval_class_D_A_U": [float(p[X > .75].sum()),
                                         float(p[(X >= .25) & (X <= .75)].sum()),
                                         float(p[X < .25].sum())]}
    if matrix is not None:
        predictive = matrix @ p
        result["predictive_D_A_U"] = predictive.tolist()
        if q is not None:
            result["predictive_l1_misfit"] = float(np.abs(predictive - q).sum())
    return result


def integration_checks():
    fine_x = (np.arange(500001) + .5) / 500001
    checks = []
    for q, n, sigma in (([0., 0., 1.], 10000, .25),
                         ([1., 0., 0.], 10000, .25),
                         ([.7, .3, 0.], 100, .15)):
        matrix = np.array([ndtr((fine_x - .65) / sigma),
                           ndtr((.65 - fine_x) / sigma) - ndtr((.35 - fine_x) / sigma),
                           ndtr((.35 - fine_x) / sigma)])
        p = softmax(n * (np.array(q) @ np.log(matrix)))
        ci = 100 * np.interp([.025, .975],
                            np.concatenate(([0.], np.cumsum(p))),
                            np.linspace(0., 1., len(fine_x) + 1))
        coarse = probit(q, n, sigma)
        checks.append({"q_D_A_U": q, "n": n, "sigma": sigma,
                       "fine_mean_score": float(100 * (p @ fine_x)),
                       "fine_interval95": ci.tolist(),
                       "mean_abs_error": abs(coarse["mean_score"] - 100 * (p @ fine_x)),
                       "max_interval_abs_error": float(np.max(np.abs(ci - coarse["score_interval95"])))})
    for sigma in (.08, .15, .25):
        low = probit([0., 0., 1.], 10000, sigma)
        high = probit([1., 0., 0.], 10000, sigma)
        assert abs(low["mean_score"] + high["mean_score"] - 100) < 1e-8
        assert np.max(np.abs(np.array(low["score_interval95"]) +
                             high["score_interval95"][::-1] - 100)) < 1e-8
    assert max(x["mean_abs_error"] for x in checks) < .002
    assert max(x["max_interval_abs_error"] for x in checks) < .01
    return checks


def probit(q, n, sigma=.15):
    matrix = EMISSIONS[sigma]
    logs = n * (np.asarray(q) @ np.log(matrix))
    return grid_summary(logs, matrix, q)


def grid_checks():
    grid = [np.array([d, a, 20 - d - a]) / 20
            for d in range(21) for a in range(21 - d)]
    summaries = []
    for name, method in [("beta_binomial2", lambda q: beta_model(q, 100)),
                         *[(f"probit_sigma_{s}", lambda q, s=s: probit(q, 100, s))
                           for s in (.08, .15, .25)]]:
        violations = []
        checked = 0
        for q in grid:
            start = method(q)["mean_score"]
            for source, dest in ((2, 1), (1, 0), (2, 0)):
                if q[source] < .05 - 1e-10:
                    continue
                target = q.copy()
                target[source] -= .05
                target[dest] += .05
                score = method(target)["mean_score"]
                checked += 1
                if score < start - 1e-8:
                    violations.append({"before": q.tolist(), "after": target.tolist(),
                                       "score_before": start, "score_after": score})
        summaries.append({"method": name, "grid_points": len(grid),
                          "directed_checks": checked, "violation_count": len(violations),
                          "first_violations": violations[:3]})
    return summaries


def compare_demos():
    output = []
    base = REPO / "examples/process-model-run-2026-09-16"
    for scene in ("SCN-001", "SCN-002"):
        for path in sorted((base / scene).glob("*.report.json")):
            report = json.loads(path.read_text(encoding="utf-8-sig"))
            for item in report["items"]:
                if item["item_id"] == "A-S1-06":
                    continue
                model = report["configuration"]["skill_models"][item["item_id"]]
                cps = item["checkpoints"]
                weight = 1 / len(cps)
                direct = 0.
                dq = np.zeros(3)
                scalar_a, scalar_b = 1., 1.
                probit_logs = np.zeros_like(X)
                evidence = []
                cp_rows = []
                for cp in cps:
                    checkpoint = model["checkpoint_models"][cp["checkpoint_id"]]
                    props = cp["frame_distribution"]["proportions"]
                    q = np.array([props.get(g, 0.) for g in ("D", "A", "U")])
                    assert abs(q.sum() - 1.) < 1e-10
                    direct += weight * float(100 * (q[0] + .5 * q[1]))
                    n = 100 * weight
                    if checkpoint["states"] == ["D", "U"]:
                        # Binary prohibition has no observable A outcome.
                        raw = np.array([1.5 + n * q[0], 1.5 + n * q[2]]) / (n + 3)
                        predictive = np.array([raw[0], 0., raw[1]])
                        scalar_a += n * q[0]
                        scalar_b += n * q[2]
                        probit_logs += n * (q[[0, 2]] @ np.log(emission(.15, binary=True)))
                    else:
                        predictive = (np.ones(3) + n * q) / (n + 3)
                        scalar_a += n * (2 * q[0] + q[1])
                        scalar_b += n * (2 * q[2] + q[1])
                        probit_logs += n * (q @ np.log(EMISSIONS[.15]))
                    dq += weight * predictive
                    cp_rows.append({"checkpoint_id": cp["checkpoint_id"],
                                    "q_D_A_U": q.tolist(),
                                    "effective_n": n,
                                    "dirichlet_predictive_D_A_U": predictive.tolist()})
                    evidence.append((checkpoint, props, weight))
                p_current, score_current = distribution_posterior(model["prior"], model["state_scores"], evidence)
                assert abs(score_current - item["skill_quantification"]["score"]) < 1e-8
                # Deliberately changed time-strength variant, not current code.
                timestamps = [row["timestamp_s"] for row in item["timeline"]]
                duration = max(timestamps) - min(timestamps)
                p_time, score_time = distribution_posterior(model["prior"], model["state_scores"], evidence,
                                                           strength=2 * duration)
                output.append({"scene": scene, "case": path.stem,
                               "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "item_id": item["item_id"], "name": item["name"],
                               "rule_grade": item["grade"], "rule_passed": item["passed"],
                               "current_score": score_current,
                               "current_p_L_M_H": p_current,
                               "time_strength_unimplemented_score": score_time,
                               "time_strength_unimplemented_p_L_M_H": p_time,
                               "nominal_duration_s": duration,
                               "comparison_caveats": [
                                   "nominal duration includes inter-phase gaps, not effective observed exposure",
                                   "Dirichlet prior mass 3 per checkpoint yields total mass 3K",
                                   "Beta ordinal emissions contribute 2 trials, binary emissions 1 trial"
                               ],
                               "direct_performance_score": direct,
                               "dirichlet_predictive_D_A_U": dq.tolist(),
                               "dirichlet_quality_score": float(100 * (dq[0] + .5 * dq[1])),
                               "beta_binomial2_or_binary_mean_score": 100 * scalar_a / (scalar_a + scalar_b),
                               "probit": grid_summary(probit_logs), "checkpoints": cp_rows})
    return output


def main():
    cases = []
    for label, q in CASES.items():
        for n in (10, 100, 10000):
            cases.append({"case": label, "q_D_A_U": q, "effective_n": n,
                          "direct_performance_score": 100 * (q[0] + .5 * q[1]),
                          "beta_binomial2": beta_model(q, n),
                          "probit": {str(s): probit(q, n, s) for s in (.08, .15, .25)}})
    checks = grid_checks()
    demos = compare_demos()
    out = {"status": "offline illustrative models, uncalibrated", "cases": cases,
           "quadrature_convergence_checks": integration_checks(),
           "grid_checks": checks, "same_mean_counterexample": {
               "all_A": beta_model([0., 1., 0.], 100),
               "half_D_half_U": beta_model([.5, 0., .5], 100)},
           "assumptions": {"probit_cutpoints": [.35, .65], "prior_scalar": "Beta(1,1)",
                           "hard_intervals_for_diagnostic_only": [.25, .75],
                           "quadrature_midpoints": len(X),
                           "demo_effective_n_per_item": 100,
                           "demo_weights": "equal checkpoints; fixed total budget",
                           "noninteger_counts": "power likelihood, not independent raw frames"}}
    (HERE / "continuous_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "demo_comparison.json").write_text(json.dumps(demos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_setting_evaluations": len(cases) * 4,
                      "grid_checks": checks, "demo_item_rows": len(demos),
                      "70D30A_n100": next(x for x in cases if x["case"] == "70D30A" and x["effective_n"] == 100)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
