"""Per-attempt evidence for 场景一 · 受控减速与定点停止, recomputed from the CSVs at a chosen decimation.

Same rules as ../evidence_scn1_2026-11-17/{evidence_candidates,five_level}.py (2026-11-17 handoff §3.2–3.3) except E1, which follows D-015,
refactored so the frame step DT is a parameter. Used to (1) feed the GRM/ECD prototype and (2) check that the
per-attempt grades do not depend on the sampling rate (100 Hz vs 10 Hz).
Run: python evidence.py   -> writes evidence_dec1.json, evidence_dec10.json
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bn_optimization_2026-11-12"))
from load import first_sustained, runs, task1_unique, wrap180  # noqa: E402

WORSE = {"D": 0, "A": 1, "U": 2}
LV_DAU = {"D": 5, "A": 3, "U": 1}


def worst(*gs):
    gs = [g for g in gs if g is not None]
    return max(gs, key=WORSE.get) if gs else None


def g3(x, d, a):
    return "D" if x <= d else ("A" if x <= a else "U")


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


def longest(t, mask, dt):
    best = 0.0
    for a, b in runs(mask):
        best = max(best, t[b] - t[a] + dt)
    return best


STOP_V, STOP_T, REST_V, MOVE_V, MOVE_T = 0.5, 0.5, 0.2, 0.5, 0.5
DB, MIN_IN, WIN, HOLD, DX_MIN, MOVING = 5.0, 0.05, 2.0, 1.0, 0.05, 0.2
AX = {"lon": ("Pilot Lon", "V_bx m/s", -1), "lat": ("Pilot Lat", "V_by m/s", +1)}


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same") if n > 1 else x


def initial_rest(t, vh):
    s = first_sustained(t, vh <= STOP_V, STOP_T)
    mv = [(a, b) for a, b in runs(vh[s:] > MOVE_V) if t[b + s] - t[a + s] >= MOVE_T - 1e-9]
    seg = vh[s:(s + mv[0][0]) if mv else len(vh)]
    below = np.where(seg <= REST_V)[0]
    return s + int(below[0] if len(below) else np.argmin(seg))


def grade_initial(dx, dy):
    if 0 <= dx <= 5 and abs(dy) <= 2:
        return "D"
    return "A" if -5 <= dx <= 15 and abs(dy) <= 5 else "U"


def cp4(p2, dt):
    t = p2["Simulation time"].values
    x, y = p2["Xe m"].values, p2["Ye m"].values
    vh = np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values)
    s1 = initial_rest(t, vh)
    out = dict(g41=grade_initial(x[s1] + 500, y[s1]), dx1=float(x[s1] + 500), dy1=float(y[s1]))
    ts = t[s1:]
    n_mv = n_ineff = n_rev = 0
    nsm = max(1, int(round(0.1 / dt)))
    for _, (uc, vc, gain) in AX.items():
        u = p2[uc].values[s1:].astype(float)
        v = smooth(p2[vc].values[s1:].astype(float), nsm)
        pos = np.cumsum(v) * dt
        mv = [(a, b) for a, b in runs(np.abs(v) > MOVE_V) if ts[b] - ts[a] >= MOVE_T - 1e-9]
        ins = [(a, b) for a, b in runs(np.abs(u) > DB) if (b - a + 1) * dt >= MIN_IN - 1e-9]
        for i, (a, b) in enumerate(ins):
            d = gain * np.sign(u[a])
            end = min(b + int(WIN / dt), len(v) - 1)
            if i + 1 < len(ins):
                end = min(end, max(ins[i + 1][0] - 1, b))
            tt = np.arange(end - a + 1) * dt
            dx = float(np.max(d * (pos[a:end + 1] - pos[a] - v[a] * tt)))
            if (b - a + 1) * dt < HOLD and dx < DX_MIN:
                n_ineff += 1
            elif np.sign(v[a]) == -d and abs(v[a]) > MOVING and d * v[end] > MOVING:
                n_rev += 1
        n_mv += len(mv)
    out.update(n_mv=int(n_mv), n_ineff=int(n_ineff), n_rev=int(n_rev))
    return out


def reversals(u, hyst):
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


def lv_turns(n):
    return 5 if n == 0 else 4 if n == 1 else 3 if n == 2 else 2 if n == 3 else 1


def inzone(dx, dy):
    return abs(dx) <= 15 and abs(dy) <= 5


def evidence(df, dec=1):
    df = df.iloc[::dec].reset_index(drop=True)
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    t = p2["Simulation time"].values
    dt = float(np.median(np.diff(t)))
    v = -p2["V_ex m/s"].values
    end = segment(p2)
    ey = np.abs(p2["Ye m"].values[:end])
    ep = np.abs(wrap180(p2["psi deg"].values[:end] - 270.0))
    tt = t[:end]
    fr = [worst(g3(a, 2, 5), g3(b, 5, 10)) for a, b in zip(ey, ep)]
    r = dict(cp2_worst=worst(*fr), cp2_fD=float(np.mean([g == "D" for g in fr])),
             cp2_fU=float(np.mean([g == "U" for g in fr])),
             cp2_lenU=longest(tt, (ey > 5) | (ep > 10), dt),
             cp2_totD=float(np.sum((ey > 2) | (ep > 5)) * dt),
             B=B_metric(tt, v[:end]), H=H_metric(tt, v[:end], p2["Pilot Lon"].values[:end].astype(float)))
    dxe, dye = p2["Xe m"].values[-1] + 500, p2["Ye m"].values[-1]
    hd = abs(float(wrap180(p2["psi deg"].values[-1] - 270.0)))
    pos = "D" if (abs(dxe) <= 5 and abs(dye) <= 2) else ("A" if (abs(dxe) <= 15 and abs(dye) <= 5) else "U")
    r["cp1"] = worst(pos, g3(hd, 5, 10))
    r["gB"] = g3(r["B"], 0.5, 1.0)
    r["gH"] = g3(r["H"], 20, 50) if r["H"] is not None else None
    r.update(cp4(p2, dt))
    e = first_sustained(t, v <= 0.2 * v[0], 0.30)
    turns = max(reversals(p2["Pilot Lon"].values[:e].astype(float), 10.0) - 1, 0)
    r["turns"] = int(turns)
    # E1 per D-015 (2026-11-17): momentary excursions tolerated, sustained ones not.
    #   U  continuously beyond the A band > 1 s
    #   A  beyond the A band only briefly (each <= 1 s), or beyond the D band > 1 s in total
    #   D  beyond the D band <= 1 s in total and never beyond the A band
    # Five-level nesting (optional): 5 never beyond D; 4 momentary beyond D; 3 A with >= 50 % time in D band; 2 other A.
    if r["cp2_lenU"] > 1.0:
        e1 = 1
    elif r["cp2_lenU"] > 0:
        e1 = 2
    elif r["cp2_totD"] == 0:
        e1 = 5
    elif r["cp2_totD"] <= 1.0:
        e1 = 4
    else:
        e1 = 3 if r["cp2_fD"] >= 0.5 else 2
    e2a = min(LV_DAU[r["gH"]], lv_turns(turns), LV_DAU[r["gB"]])
    lh = 5 if r["gH"] == "D" else 3 if r["gH"] == "A" else (3 if turns == 0 else 1)
    e2b = min(lh, lv_turns(turns), LV_DAU[r["gB"]])
    e3 = LV_DAU[r["g41"]]
    if not (r["n_mv"] > 0 or not inzone(r["dx1"], r["dy1"])):
        e4 = None
    elif pos == "U":
        e4 = 1
    elif r["n_mv"] <= 2 and r["n_rev"] == 0 and r["n_ineff"] == 0 and pos == "D":
        e4 = 5
    elif r["n_mv"] <= 3 and r["n_rev"] <= 1 and r["n_ineff"] == 0:
        e4 = 4
    elif r["n_mv"] <= 6 and r["n_rev"] <= 3:
        e4 = 3
    else:
        e4 = 2
    r.update(e1=e1, e2a=e2a, e2b=e2b, e3=e3, e4=e4)
    return r


if __name__ == "__main__":
    data = task1_unique()
    for dec in (1, 10):
        rows = []
        for i, (name, df) in enumerate(data):
            r = evidence(df, dec)
            r.update(i=i, name=name)
            rows.append(r)
        with open(os.path.join(HERE, f"evidence_dec{dec}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        summary = {k: dict(sorted(collections.Counter(r[k] for r in rows if r[k] is not None).items(), reverse=True))
                   for k in ("e1", "e2a", "e2b", "e3", "e4")}
        print(f"dec={dec}", summary, "e4 n/a:", sum(r["e4"] is None for r in rows))
