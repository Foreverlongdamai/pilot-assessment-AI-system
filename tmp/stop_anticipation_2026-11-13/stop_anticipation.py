"""Recompute the data statistics cited in design-doc §8.3.1 and §8.3.4 (D-010, D-012, 2026-11-13).

Checkpoint 4 of SCN-001 'controlled deceleration and stop at designated point':
initial rest position, repositioning after it (aircraft side), repositioning control
corrections (stick side) and timing, plus checkpoint 1 final heading, on the 65 unique task-1 runs.
Run: python stop_anticipation.py   (needs numpy, pandas; reuses ../bn_optimization_2026-11-12/load.py)
"""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bn_optimization_2026-11-12"))
from load import first_sustained, runs, task1_unique, wrap180  # noqa: E402

DT = 0.01            # s, CSV sample interval
STOP_V, STOP_T = 0.5, 0.5     # speed first <= 0.5 m/s for >= 0.5 s: search start for the initial rest point
REST_V = 0.2                  # initial rest point: first Vh <= 0.2 m/s after that, else min Vh before the first move
MOVE_V, MOVE_T = 0.5, 0.5     # repositioning move: |axis velocity| > 0.5 m/s for >= 0.5 s
DB, MIN_IN = 5.0, 0.05        # stick input: |u| > 5 (full scale 100) for >= 0.05 s
WIN = 2.0                     # response window after input end, s
HOLD, DX_MIN = 1.0, 0.05      # ineffective: hold < 1 s and induced displacement < 0.05 m
MOVING = 0.2                  # 'aircraft moving' for braking/reversal classification, m/s
AX = {"fore/aft": ("Pilot Lon", "V_bx m/s", -1), "lateral": ("Pilot Lat", "V_by m/s", +1)}


def grade(dx, dy):
    if abs(dx) <= 5 and abs(dy) <= 2:
        return "D"
    return "A" if abs(dx) <= 15 and abs(dy) <= 5 else "U"


def episodes(t, mask, mind):
    return [(a, b) for a, b in runs(mask) if t[b] - t[a] >= mind - 1e-9]


def smooth(x, n=10):
    return np.convolve(x, np.ones(n) / n, mode="same")


def rank_corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def initial_rest(t, vh):
    """D-012: index where the aircraft first actually comes to rest, before any repositioning move."""
    s = first_sustained(t, vh <= STOP_V, STOP_T)
    mv = [(a, b) for a, b in runs(vh[s:] > MOVE_V) if t[b + s] - t[a + s] >= MOVE_T - 1e-9]
    seg = vh[s:(s + mv[0][0]) if mv else len(vh)]
    below = np.where(seg <= REST_V)[0]
    return s + int(below[0] if len(below) else np.argmin(seg))


def grade_initial(dx, dy, over_d, over_a):
    """Checkpoint 4.1: D-004 rectangle on the short side; overshoot (dx < 0) limited to over_d / over_a."""
    if -over_d <= dx <= 5 and abs(dy) <= 2:
        return "D"
    return "A" if -over_a <= dx <= 15 and abs(dy) <= 5 else "U"


def heading_grade(e):
    return "D" if e <= 5 else ("A" if e <= 10 else "U")


OVERSHOOT_OPTIONS = {"symmetric 5/15": (5, 15), "ADS-33 style 0/5": (0, 5), "half 2.5/7.5": (2.5, 7.5)}
WORSE = {"D": 0, "A": 1, "U": 2}


rows = []
axis = {k: dict(cls=collections.Counter(), cls_runs=collections.defaultdict(set), moves=[], path=[], effort=[]) for k in AX}
for ri, (name, df) in enumerate(task1_unique()):
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    t = p2["Simulation time"].values
    x, y = p2["Xe m"].values, p2["Ye m"].values
    vh_all = np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values)
    s1 = initial_rest(t, vh_all)          # checkpoint 4 anchor: initial rest point (D-012)
    moving = np.where(vh_all > MOVE_V)[0]
    mv_all = [(a + s1, b + s1) for a, b in runs(vh_all[s1:] > MOVE_V) if t[b + s1] - t[a + s1] >= MOVE_T - 1e-9]
    if mv_all:                            # D-013: final adjustment complete = first Vh <= REST_V after the last move
        tail = np.where(vh_all[mv_all[-1][1] + 1:] <= REST_V)[0]
        k_end = mv_all[-1][1] + 1 + int(tail[0]) if len(tail) else len(t) - 1
    else:
        k_end = s1
    hd_end = abs(float(wrap180(p2["psi deg"].values[-1] - 270.0)))
    gpos = grade(x[-1] + 500, y[-1])
    rows.append(dict(g1={o: grade_initial(x[s1] + 500, y[s1], *b) for o, b in OVERSHOOT_OPTIONS.items()},
                     gf=gpos, ghd=heading_grade(hd_end), hd_end=hd_end,
                     g_cp1=max(gpos, heading_grade(hd_end), key=WORSE.get), over=float(-(x[s1] + 500)),
                     t_first=t[s1] - t[0], t_total=t[k_end] - t[0], n_mv=len(mv_all), t_last=(t[moving[-1]] - t[0]) if len(moving) else 0.0))
    ts = t[s1:]
    any_move = False
    for k, (uc, vc, gain) in AX.items():
        u = p2[uc].values[s1:].astype(float)
        v = smooth(p2[vc].values[s1:].astype(float))
        pos = np.cumsum(v) * DT
        mv = episodes(ts, np.abs(v) > MOVE_V, MOVE_T)
        any_move |= bool(mv)
        path = float(np.sum(np.abs(v)) * DT)
        ins = [(a, b) for a, b in runs(np.abs(u) > DB) if (b - a + 1) * DT >= MIN_IN - 1e-9]
        effort = 0.0
        for i, (a, b) in enumerate(ins):
            d = gain * np.sign(u[a])
            hold = (b - a + 1) * DT
            effort += float(np.sum(np.abs(u[a:b + 1])) * DT)
            end = min(b + int(WIN / DT), len(v) - 1)
            if i + 1 < len(ins):
                end = min(end, max(ins[i + 1][0] - 1, b))
            tt = np.arange(end - a + 1) * DT
            dx = float(np.max(d * (pos[a:end + 1] - pos[a] - v[a] * tt)))
            if hold < HOLD and dx < DX_MIN:
                c = "ineffective"
            elif np.sign(v[a]) == -d and abs(v[a]) > MOVING:
                c = "reversal" if d * v[end] > MOVING else "braking"
            else:
                c = "driving/fine"
            axis[k]["cls"][c] += 1
            axis[k]["cls_runs"][c].add(ri)
        axis[k]["moves"].append(len(mv))
        axis[k]["path"].append(path)
        axis[k]["effort"].append(effort)
    rows[-1]["any_move"] = any_move

print("runs:", len(rows))
for o in OVERSHOOT_OPTIONS:
    print(f"initial-rest grade ({o}):", {g: sum(r["g1"][o] == g for r in rows) for g in "DAU"})
ov = sorted(r["over"] for r in rows if r["over"] > 0)
print("initial rest point beyond 500 m: n =", len(ov), "overshoot (m):", [round(v, 2) for v in ov])
hd = np.array([r["hd_end"] for r in rows])
print("checkpoint 1 final position grade:", {g: sum(r["gf"] == g for r in rows) for g in "DAU"},
      "| final heading grade:", {g: sum(r["ghd"] == g for r in rows) for g in "DAU"},
      f"(median {np.median(hd):.2f} deg, max {hd.max():.2f} deg)",
      "| combined:", {g: sum(r["g_cp1"] == g for r in rows) for g in "DAU"})
print("rank corr total time (D-013) vs repositioning move count: %.2f, vs time to initial rest: %.2f" % (
    rank_corr([r["t_total"] for r in rows], [r["n_mv"] for r in rows]), rank_corr([r["t_total"] for r in rows], [r["t_first"] for r in rows])))
print("runs with no repositioning move (either axis):", sum(not r["any_move"] for r in rows))
for lab, key in (("phase-2 start -> initial rest point", "t_first"), ("phase-2 start -> final adjustment complete (D-013)", "t_total"), ("phase-2 start -> last movement", "t_last")):
    v = np.array([r[key] for r in rows])
    print(f"{lab}: median {np.median(v):.1f} s, p90 {np.percentile(v, 90):.1f} s, max {v.max():.1f} s")
for k, a in axis.items():
    m = np.array(a["moves"]); p = np.array(a["path"]); e = np.array(a["effort"])
    print(f"\n[{k}] moves per run:", dict(sorted(collections.Counter(int(min(n, 4)) for n in m).items())), "(4 = 4+)")
    print(f"[{k}] stick inputs by class:", {c: f"{n} in {len(a['cls_runs'][c])} runs" for c, n in sorted(a['cls'].items())})
    sel = m > 0                       # effort per metre only where this axis had at least one repositioning move
    per_m = e[sel] / p[sel]
    print(f"[{k}] stick effort per metre moved (axes with >=1 move): n={int(sel.sum())}, median {np.median(per_m):.0f}, p90 {np.percentile(per_m, 90):.0f}, max {per_m.max():.0f}")
    small = (p > 0.5) & (m == 0)
    if small.any():
        print(f"[{k}]   (axes without a move but >0.5 m path: n={int(small.sum())}, effort/m median {np.median(e[small] / p[small]):.0f}, max {np.max(e[small] / p[small]):.0f} -- excluded)")
    print(f"[{k}] rank corr: total effort vs distance {rank_corr(e, p):.2f}; effort-per-metre vs distance {rank_corr(per_m, p[sel]):.2f}")


# ---------------- control response and hold-time basis for the 1 s threshold ----------------
def best_lag(u, yv, step=5, maxlag=2.0):
    best = (0.0, 0.0)
    for k in range(0, int(maxlag / DT) + 1, step):
        a, b = (u[:len(u) - k], yv[k:]) if k else (u, yv)
        if len(a) < 50 or a.std() < 1e-9 or b.std() < 1e-9:
            continue
        c = np.corrcoef(a, b)[0, 1]
        if abs(c) > abs(best[1]):
            best = (k * DT, c)
    return best


ATT = {"fore/aft": "theta deg", "lateral": "phi deg"}
BINS = [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 99]
rel = {k: {"velocity": [], "acceleration": [], "attitude": []} for k in AX}
holds = {k: [] for k in AX}
cmd = {k: collections.Counter() for k in AX}
for name, df in task1_unique():
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    t = p2["Simulation time"].values
    s1 = initial_rest(t, np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values))
    ts = t[s1:]
    if len(ts) < 50:                  # less than 0.5 s after the initial rest point: nothing to analyse
        continue
    for k, (uc, vc, gain) in AX.items():
        u = p2[uc].values[s1:].astype(float)
        vraw = p2[vc].values[s1:].astype(float)
        v = smooth(vraw)
        acc = smooth(np.gradient(smooth(vraw, 20), ts), 20)
        if u.std() > DB / 2:
            for key, yv in (("velocity", vraw), ("acceleration", acc), ("attitude", p2[ATT[k]].values[s1:].astype(float))):
                rel[k][key].append(best_lag(u, yv))
        pos = np.cumsum(v) * DT
        ins = [(a, b) for a, b in runs(np.abs(u) > DB) if (b - a + 1) * DT >= MIN_IN - 1e-9]
        for i, (a, b) in enumerate(ins):
            d = gain * np.sign(u[a])
            end = min(b + int(WIN / DT), len(v) - 1)
            if i + 1 < len(ins):
                end = min(end, max(ins[i + 1][0] - 1, b))
            tt = np.arange(end - a + 1) * DT
            holds[k].append(((b - a + 1) * DT, float(np.max(d * (pos[a:end + 1] - pos[a] - v[a] * tt)))))
        for a, b in episodes(ts, np.abs(v) > MOVE_V, MOVE_T):
            cmd[k]["with stick input" if any(ia <= b and ib >= a - int(WIN / DT) for ia, ib in ins) else "without"] += 1

for k in AX:
    print(f"\n[{k}] stick -> response (after the initial rest point, runs with stick activity):")
    for key, r in rel[k].items():
        r = np.array(r)
        print(f"   {key:12s} n={len(r)}  |corr| median {np.median(np.abs(r[:, 1])):.2f}  lag median {np.median(r[:, 0]):.2f} s")
    vb = sum(1 for a, b in zip(rel[k]["velocity"], rel[k]["acceleration"]) if abs(a[1]) > abs(b[1]))
    print(f"   velocity fits better than acceleration in {vb}/{len(rel[k]['velocity'])} runs")
    print(f"   repositioning moves:", dict(cmd[k]))
    h = np.array(holds[k])
    print("   share of stick inputs that moved the aircraft (induced displacement >= 0.05 m) by hold time:")
    for lo, hi in zip(BINS, BINS[1:]):
        s = h[(h[:, 0] >= lo) & (h[:, 0] < hi)]
        if len(s):
            print(f"     {lo:.2f}-{hi if hi < 99 else float('inf'):.2f} s: n={len(s):3d}, moved {np.mean(s[:, 1] >= DX_MIN):.0%}")
    for th in (0.5, 1.0, 1.5):
        n_in = int(np.sum((h[:, 0] < th) & (h[:, 1] < DX_MIN)))
        print(f"   ineffective inputs if the hold threshold were {th:.1f} s: {n_in}")
