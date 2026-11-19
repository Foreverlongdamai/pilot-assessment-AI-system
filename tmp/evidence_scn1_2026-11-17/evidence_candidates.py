"""Per-attempt evidence candidates for 场景一 · 受控减速与定点停止 on the 65 unique runs (2026-11-17).

For each run (= one attempt) compute the candidate observables that would enter the Bayesian network once:
  CP1 final stop (D-004/D-012), CP2 track/heading in main deceleration (frame grades -> per-attempt rules),
  CP3 B and H (D-005/D-007), CP4 initial rest accuracy (D-013) + repositioning + stick corrections + time (D-010).
Also: joint tables (dependence between checkpoints) and Spearman correlation with run order (the runs are one
pilot practising through the day, so run order is a label-free proxy for practice).
Run: python evidence_candidates.py   (reuses ../bn_optimization_2026-11-12/load.py)
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bn_optimization_2026-11-12"))
from load import first_sustained, runs, task1_unique, wrap180  # noqa: E402

DT = 0.01
WORSE = {"D": 0, "A": 1, "U": 2}


def worst(*gs):
    gs = [g for g in gs if g is not None]
    return max(gs, key=WORSE.get) if gs else None


def g3(x, d, a):
    return "D" if x <= d else ("A" if x <= a else "U")


def rank_corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


# ---- main deceleration segment (8.3.2 / 8.3.3 replay rule) ----
def segment(p2):
    t = p2["Simulation time"].values
    vx = -p2["V_ex m/s"].values
    vh = np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values)
    low = first_sustained(t, vh <= 0.5, 0.5)
    end = low if low is not None else len(t)
    rev = first_sustained(t, vx <= -0.5, 0.5)
    if rev is not None and (low is None or rev < low):
        k = rev
        while k > 0 and not (vx[k - 1] >= 0 and vx[k] < 0):
            k -= 1
        end = k
    return end


def B_metric(t, v):
    tr = t - t[0]
    g = np.arange(int(np.floor(tr[-1] / 0.1 + 1e-9)) + 1) * 0.1
    vg = np.interp(g, tr, v)
    dec = (vg[:-5] - vg[5:]) / 0.5
    return float(np.abs(dec[5:] - dec[:-5]).max())


def H_metric(t, v, u):
    v0 = v[0]
    s = first_sustained(t, v <= 0.8 * v0, 0.30)
    e = first_sustained(t, v <= 0.2 * v0, 0.30)
    if s is None or e is None or e <= s or t[e] - t[s] < 1.0:
        return None
    return float(np.percentile(u[s:e], 90) - np.percentile(u[s:e], 10))


def longest(t, mask):
    best = 0.0
    for a, b in runs(mask):
        best = max(best, t[b] - t[a] + DT)
    return best


# ---- checkpoint 4 (same parameters as stop_anticipation.py, D-010/D-012/D-013) ----
STOP_V, STOP_T, REST_V, MOVE_V, MOVE_T = 0.5, 0.5, 0.2, 0.5, 0.5
DB, MIN_IN, WIN, HOLD, DX_MIN, MOVING = 5.0, 0.05, 2.0, 1.0, 0.05, 0.2
AX = {"lon": ("Pilot Lon", "V_bx m/s", -1), "lat": ("Pilot Lat", "V_by m/s", +1)}


def smooth(x, n=10):
    return np.convolve(x, np.ones(n) / n, mode="same")


def initial_rest(t, vh):
    s = first_sustained(t, vh <= STOP_V, STOP_T)
    mv = [(a, b) for a, b in runs(vh[s:] > MOVE_V) if t[b + s] - t[a + s] >= MOVE_T - 1e-9]
    seg = vh[s:(s + mv[0][0]) if mv else len(vh)]
    below = np.where(seg <= REST_V)[0]
    return s + int(below[0] if len(below) else np.argmin(seg))


def grade_initial(dx, dy):  # D-013: overshoot side D 0 m, A 5 m
    if 0 <= dx <= 5 and abs(dy) <= 2:
        return "D"
    return "A" if -5 <= dx <= 15 and abs(dy) <= 5 else "U"


def cp4(p2):
    t = p2["Simulation time"].values
    x, y = p2["Xe m"].values, p2["Ye m"].values
    vh = np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values)
    s1 = initial_rest(t, vh)
    mv_all = [(a + s1, b + s1) for a, b in runs(vh[s1:] > MOVE_V) if t[b + s1] - t[a + s1] >= MOVE_T - 1e-9]
    if mv_all:
        tail = np.where(vh[mv_all[-1][1] + 1:] <= REST_V)[0]
        k_end = mv_all[-1][1] + 1 + int(tail[0]) if len(tail) else len(t) - 1
    else:
        k_end = s1
    out = dict(g41=grade_initial(x[s1] + 500, y[s1]), dx1=float(x[s1] + 500), dy1=float(y[s1]),
               t_first=float(t[s1] - t[0]), t_total=float(t[k_end] - t[0]))
    ts = t[s1:]
    n_mv = path = n_ineff = n_rev = effort = 0.0
    path_moved = 0.0
    for k, (uc, vc, gain) in AX.items():
        u = p2[uc].values[s1:].astype(float)
        v = smooth(p2[vc].values[s1:].astype(float))
        pos = np.cumsum(v) * DT
        mv = [(a, b) for a, b in runs(np.abs(v) > MOVE_V) if ts[b] - ts[a] >= MOVE_T - 1e-9]
        p_ax = float(np.sum(np.abs(v)) * DT)
        ins = [(a, b) for a, b in runs(np.abs(u) > DB) if (b - a + 1) * DT >= MIN_IN - 1e-9]
        e_ax = 0.0
        for i, (a, b) in enumerate(ins):
            d = gain * np.sign(u[a])
            e_ax += float(np.sum(np.abs(u[a:b + 1])) * DT)
            end = min(b + int(WIN / DT), len(v) - 1)
            if i + 1 < len(ins):
                end = min(end, max(ins[i + 1][0] - 1, b))
            tt = np.arange(end - a + 1) * DT
            dx = float(np.max(d * (pos[a:end + 1] - pos[a] - v[a] * tt)))
            if (b - a + 1) * DT < HOLD and dx < DX_MIN:
                n_ineff += 1
            elif np.sign(v[a]) == -d and abs(v[a]) > MOVING and d * v[end] > MOVING:
                n_rev += 1
        n_mv += len(mv)
        path += p_ax
        if mv:
            effort += e_ax
            path_moved += p_ax
    out.update(n_mv=int(n_mv), path=path, n_ineff=int(n_ineff), n_rev=int(n_rev),
               eff_per_m=(effort / path_moved) if path_moved > 0 else float("nan"))
    return out


rows = []
for idx, (name, df) in enumerate(task1_unique()):
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    t = p2["Simulation time"].values
    v = -p2["V_ex m/s"].values
    end = segment(p2)
    ey = np.abs(p2["Ye m"].values[:end])
    ep = np.abs(wrap180(p2["psi deg"].values[:end] - 270.0))
    tt = t[:end]
    fr = [worst(g3(a, 2, 5), g3(b, 5, 10)) for a, b in zip(ey, ep)]
    r = dict(i=idx, name=name,
             cp2_worst=worst(*fr),
             cp2_fD=float(np.mean([g == "D" for g in fr])), cp2_fU=float(np.mean([g == "U" for g in fr])),
             cp2_lenA=longest(tt, (ey > 2) | (ep > 5)),      # longest continuous time outside the D band
             cp2_lenU=longest(tt, (ey > 5) | (ep > 10)),     # longest continuous time outside the A band
             cp2_peak_y=float(ey.max()), cp2_peak_psi=float(ep.max()),
             B=B_metric(tt, v[:end]), H=H_metric(tt, v[:end], p2["Pilot Lon"].values[:end].astype(float)))
    dxe, dye = p2["Xe m"].values[-1] + 500, p2["Ye m"].values[-1]
    hd = abs(float(wrap180(p2["psi deg"].values[-1] - 270.0)))
    pos = "D" if (abs(dxe) <= 5 and abs(dye) <= 2) else ("A" if (abs(dxe) <= 15 and abs(dye) <= 5) else "U")
    r["cp1"] = worst(pos, g3(hd, 5, 10))
    r["cp1_pos"] = pos
    r["gB"] = g3(r["B"], 0.5, 1.0)
    r["gH"] = g3(r["H"], 20, 50) if r["H"] is not None else None
    r.update(cp4(p2))
    rows.append(r)

N = len(rows)
cnt = lambda key: dict(collections.Counter(r[key] for r in rows))  # noqa: E731
print("runs:", N)
print("CP1 final stop:", cnt("cp1"))
print("CP2 worst-frame:", cnt("cp2_worst"))


def cp2_rule(r, ta, tu):
    if r["cp2_lenU"] > tu:
        return "U"
    if r["cp2_lenA"] > ta or r["cp2_lenU"] > 0:
        return "A"
    return "D"


for ta, tu in ((0, 0), (0.5, 0.5), (1, 1), (2, 1), (2, 2), (3, 2)):
    print(f"CP2 tolerant rule (outside D > {ta}s -> A, outside A > {tu}s -> U):",
          dict(collections.Counter(cp2_rule(r, ta, tu) for r in rows)))
la = np.array([r["cp2_lenA"] for r in rows]); lu = np.array([r["cp2_lenU"] for r in rows])
print("CP2 longest time outside D band: median %.2f s, p75 %.2f, p90 %.2f, max %.2f; zero in %d runs" % (
    np.median(la), np.percentile(la, 75), np.percentile(la, 90), la.max(), int((la == 0).sum())))
print("CP2 longest time outside A band: nonzero in %d runs, values:" % int((lu > 0).sum()), sorted(round(x, 2) for x in lu if x > 0))
print("CP3 B grades:", cnt("gB"), " H grades:", cnt("gH"))
jt = collections.Counter((r["gB"], r["gH"]) for r in rows)
print("CP3 joint (B,H):", dict(jt))
print("CP4.1 initial rest:", cnt("g41"))
print("CP1 x CP4.1:", dict(collections.Counter((r["cp1"], r["g41"]) for r in rows)))
nm = [r for r in rows if r["n_mv"] == 0]
print("no-reposition runs:", len(nm), " CP1 x CP4.1 among them:", dict(collections.Counter((r["cp1"], r["g41"]) for r in nm)))
print("repositioning moves (both axes):", dict(sorted(collections.Counter(min(r["n_mv"], 6) for r in rows).items())), "(6 = 6+)")
print("ineffective inputs:", dict(sorted(collections.Counter(min(r["n_ineff"], 4) for r in rows).items())),
      " reversal inputs:", dict(sorted(collections.Counter(min(r["n_rev"], 6) for r in rows).items())))
tot = np.array([r["t_total"] for r in rows]); tf = np.array([r["t_first"] for r in rows])
print("time to initial rest: median %.1f p75 %.1f p90 %.1f;  total time: median %.1f p75 %.1f p90 %.1f" % (
    np.median(tf), np.percentile(tf, 75), np.percentile(tf, 90), np.median(tot), np.percentile(tot, 75), np.percentile(tot, 90)))
print("total-minus-first (time spent repositioning): median %.1f p75 %.1f p90 %.1f" % tuple(
    np.percentile(tot - tf, q) for q in (50, 75, 90)))

# label-free check: does each candidate observable change with practice (run order)?
num = {
    "CP1 |dx| final": [abs(r["dx1"]) if False else None for r in rows],
}
order = [r["i"] for r in rows]
cands = {
    "CP2 longest outside D (s)": [r["cp2_lenA"] for r in rows],
    "CP2 peak lateral (m)": [r["cp2_peak_y"] for r in rows],
    "CP3 B": [r["B"] for r in rows],
    "CP3 H": [r["H"] if r["H"] is not None else np.nan for r in rows],
    "CP4.1 |dx1| (m)": [abs(r["dx1"]) for r in rows],
    "CP4 moves": [r["n_mv"] for r in rows],
    "CP4 path (m)": [r["path"] for r in rows],
    "CP4 ineffective": [r["n_ineff"] for r in rows],
    "CP4 reversal": [r["n_rev"] for r in rows],
    "CP4 time to initial rest (s)": [r["t_first"] for r in rows],
    "CP4 total time (s)": [r["t_total"] for r in rows],
    "CP4 repositioning time (s)": list(tot - tf),
}
print("\nSpearman with run order (negative = improves with practice):")
for k, v in cands.items():
    print(f"  {k:32s} {rank_corr(order, v):+.2f}")
print("\nSpearman between candidates:")
keys = list(cands)
for a in range(len(keys)):
    for b in range(a + 1, len(keys)):
        c = rank_corr(cands[keys[a]], cands[keys[b]])
        if abs(c) >= 0.5:
            print(f"  {keys[a]} ~ {keys[b]}: {c:+.2f}")
json.dump(rows, open(os.path.join(HERE, "evidence_candidates_rows.json"), "w"), ensure_ascii=False, indent=1, default=float)
