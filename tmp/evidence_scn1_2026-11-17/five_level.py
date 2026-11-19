"""Whole-process multi-level grading trial for the evidence of 场景一 · 受控减速与定点停止 (2026-11-17).

Level scale follows the IATA CBTA grading (1 ineffectively, 2 minimal acceptable, 3 adequately, 4 effectively,
5 exemplary manner; HOW WELL = lowest of the dimensions; IATA Competency Assessment and Evaluation GM §8.2–8.3,
§9.1–9.2). Nesting in the existing D/A/U: 5,4 -> D; 3,2 -> A; 1 -> U.
"Prompt correction" = FAA ACS unsatisfactory-performance wording (FAA-S-ACS-13 appendix, PDF p.72) with the 1 s
response-lag basis. Numeric cut points for the word pictures are project choices recorded here.
Run: python five_level.py  (needs evidence_candidates_rows.json from evidence_candidates.py)
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bn_optimization_2026-11-12"))
from load import first_sustained, task1_unique  # noqa: E402

TO_DAU = {5: "D", 4: "D", 3: "A", 2: "A", 1: "U"}
LV_DAU = {"D": 5, "A": 3, "U": 1}


def reversals(u, hyst=5.0):
    """Number of direction changes of the stick larger than `hyst` units (turning points with hysteresis).
    A single pull-and-release counts 1; every extra count is a re-pull or re-release (push-pull)."""
    n, d, hi, lo, ext = 0, 0, u[0], u[0], None
    for x in u[1:]:
        if d == 0:
            hi, lo = max(hi, x), min(lo, x)
            if x < hi - hyst:
                d, ext = -1, x
            elif x > lo + hyst:
                d, ext = 1, x
        elif d == 1:
            if x > ext:
                ext = x
            elif x < ext - hyst:
                n, d, ext = n + 1, -1, x
        else:
            if x < ext:
                ext = x
            elif x > ext + hyst:
                n, d, ext = n + 1, 1, x
    return n


assert reversals([0, 10, 0, 10, 0.0], 1) == 3 and reversals([0, 100, 0.0], 5) == 1 and reversals([0, 50, 100, 60, 80, 40, 0.0], 5) == 3


def show(name, levels):
    c = collections.Counter(levels)
    dau = collections.Counter(TO_DAU[x] for x in levels if x is not None)
    print(f"{name}: " + "  ".join(f"L{k}={c.get(k, 0)}" for k in (5, 4, 3, 2, 1))
          + (f"  n/a={c[None]}" if None in c else "") + f"   -> D/A/U {dau.get('D', 0)}/{dau.get('A', 0)}/{dau.get('U', 0)}")


# evidence 1: HOW OFTEN = share of main-deceleration time inside the D band; OUTCOME = A-band exceedance
def e1(r):
    if r["cp2_lenU"] > 1.0:
        return 1                       # sustained beyond the A band: no prompt correction
    if r["cp2_lenU"] > 0:
        return 2                       # briefly beyond the A band, corrected within 1 s
    f = r["cp2_fD"]
    return 5 if f >= 0.999 else 4 if f >= 0.75 else 3 if f >= 0.5 else 2


# evidence 2: push-pull turns of the longitudinal stick before 0.2 v0 (>= TURN units), H (D-007), B (D-005)
TURN = 10.0                            # about 0.23 m/s^2 commanded deceleration (full stick ~2.3 m/s^2)


def lv_turns(n):
    return 5 if n == 0 else 4 if n == 1 else 3 if n == 2 else 2 if n == 3 else 1


def e2a(r, n):                         # option a: D-007 grades kept as one dimension
    return min(LV_DAU[r["gH"]], lv_turns(n), LV_DAU[r["gB"]])


def e2b(r, n):                         # option b: wide H from a one-way gradual release counts as adequate
    lh = 5 if r["gH"] == "D" else 3 if r["gH"] == "A" else (3 if n == 0 else 1)
    return min(lh, lv_turns(n), LV_DAU[r["gB"]])


# evidence 3: initial rest point (D-013), kept at three grades
def e3(r):
    return LV_DAU[r["g41"]]


# evidence 4: HOW MANY = moves, HOW OFTEN = reversal / ineffective inputs, OUTCOME = final position (conditional)
def inzone(dx, dy):
    return abs(dx) <= 15 and abs(dy) <= 5


def e4(r):
    if not (r["n_mv"] > 0 or not inzone(r["dx1"], r["dy1"])):
        return None
    if r["cp1_pos"] == "U":
        return 1
    if r["n_mv"] <= 2 and r["n_rev"] == 0 and r["n_ineff"] == 0 and r["cp1_pos"] == "D":
        return 5
    if r["n_mv"] <= 3 and r["n_rev"] <= 1 and r["n_ineff"] == 0:
        return 4
    if r["n_mv"] <= 6 and r["n_rev"] <= 3:
        return 3
    return 2


if __name__ == "__main__":
    R = json.load(open(os.path.join(HERE, "evidence_candidates_rows.json"), encoding="utf-8"))
    turns = {}
    for (name, df), r in zip(task1_unique(), R):
        p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
        t, v, u = p2["Simulation time"].values, -p2["V_ex m/s"].values, p2["Pilot Lon"].values.astype(float)
        e = first_sustained(t, v <= 0.2 * v[0], 0.30)
        turns[name] = max(reversals(u[:e], TURN) - 1, 0)
    print("runs", len(R))
    show("E1 track/heading", [e1(r) for r in R])
    print("   push-pull turns:", dict(sorted(collections.Counter(min(n, 4) for n in turns.values()).items())),
          "| H=U runs with 0 turns:", sum(1 for r in R if r["gH"] == "U" and turns[r["name"]] == 0), "of", sum(r["gH"] == "U" for r in R))
    show("E2 option a", [e2a(r, turns[r["name"]]) for r in R])
    show("E2 option b", [e2b(r, turns[r["name"]]) for r in R])
    show("E3 initial rest", [e3(r) for r in R])
    show("E4 terminal correction", [e4(r) for r in R])
