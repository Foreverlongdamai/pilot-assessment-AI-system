"""Offline mechanism probes; these do not change application scoring.

The bounded-memory candidate is generalized Bayes, not an exact HMM filter.
Synthetic grades are piecewise constant on known, fully observed intervals.
That interval convention is a simulation assumption, not a new input contract.
"""

import json
import math
from pathlib import Path

from pilot_assessment.scene_assessment.temporal_analysis import _transition_log


THETA = ((0.10, 0.25, 0.65), (0.35, 0.63, 0.02), (0.90, 0.099, 0.001))
PRIOR = (1 / 3,) * 3
LOG_PRIOR = [math.log(p) for p in PRIOR]


def normalize(logs):
    maximum = max(logs)
    raw = [math.exp(x - maximum) for x in logs]
    total = math.fsum(raw)
    return [x / total for x in raw]


def simulate(segments, hz=100, memory_s=20.0, budget=3.0):
    logs = LOG_PRIOR.copy()
    evidence = [0.0] * 3
    dt = 1 / hz
    rho = math.exp(-dt / memory_s)
    weight = budget * -math.expm1(-dt / memory_s)
    previous = None
    time_s = 0.0
    rows = []
    for grade, duration_s, label in segments:
        for _ in range(round(duration_s * hz)):
            for s in range(3):
                increment = (
                    math.log(THETA[s][grade]) if previous is None
                    else _transition_log(THETA[s][grade], previous == grade, dt, 5.0)
                )
                logs[s] += increment
                evidence[s] = rho * evidence[s] + weight * math.log(THETA[s][grade])
            previous = grade
            time_s += dt
        current = normalize(logs)
        bounded = normalize([p + z for p, z in zip(LOG_PRIOR, evidence)])
        rows.append({
            "label": label,
            "elapsed_s": round(time_s, 6),
            "current_markov": current,
            "bounded_memory": bounded,
            "current_log_odds_high_middle": logs[2] - logs[1],
            "bounded_log_odds_high_middle": evidence[2] - evidence[1],
        })
    return rows


def main():
    imperfect = [(0, 90, "90s D"), (1, 10, "history:90D/10A")]
    tail = [(2, 1, "U 1s"), (2, 4, "U 5s"), (2, 5, "U 10s"),
            (2, 10, "U 20s"), (2, 30, "U 50s"),
            (0, 1, "recovery D 1s"), (0, 9, "recovery D 10s"),
            (0, 10, "recovery D 20s"), (0, 20, "recovery D 40s")]
    result = {
        "scope": "single checkpoint, synthetic; no flight-skill calibration",
        "states": ["Low", "Middle", "High"],
        "theta_D_A_U": THETA,
        "current_tau_s": 5.0,
        "candidate_memory_s": 20.0,
        "candidate_evidence_budget": 3.0,
        "hz": 100,
        "imperfect_history": simulate(imperfect + tail),
        "perfect_history": simulate([(0, 100, "history:100s D")] + tail),
        "history_length": {
            str(seconds): simulate([(0, seconds, "D history"), (2, 10, "U 10s")])
            for seconds in (10, 100, 1000)
        },
        "sampling": {
            str(hz): simulate(imperfect + tail, hz=hz)
            for hz in (10, 100, 200)
        },
        "sensitivity": {
            f"T{memory}:B{budget}": simulate(imperfect + tail, memory_s=memory, budget=budget)
            for memory in (5, 20, 60) for budget in (1, 3, 8)
        },
    }
    # Known-interval constant grades must compose exactly for the candidate.
    baseline = result["sampling"]["100"]
    for candidate in result["sampling"].values():
        for reference_row, row in zip(baseline, candidate):
            for a, b in zip(reference_row["bounded_memory"], row["bounded_memory"]):
                assert abs(a - b) < 1e-10
    for case in (result["imperfect_history"], result["perfect_history"]):
        for row in case:
            for key in ("current_markov", "bounded_memory"):
                assert abs(sum(row[key]) - 1.0) < 1e-12
    target = Path(__file__).with_name("results.json")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"imperfect_history": result["imperfect_history"],
                      "history_length": result["history_length"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
