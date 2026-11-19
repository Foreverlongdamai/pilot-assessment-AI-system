"""Data reconnaissance for evidence design of the not-yet-designed 科目 (2026-11-17).

SCN-001 科目1 直线飞行与速度变换 (phase 1, 65 runs); SCN-002 科目 低速移位与到点悬停 (phase 1+2, 17 runs),
垂直升降与悬停建立 (phases 3/5/7, 8 complete runs). Target-free observables only; target coordinates are not in the CSV.
Run: python subjects_recon.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bn_optimization_2026-11-12"))
from load import KT, first_sustained, runs, task1_unique, task3_all, wrap180  # noqa: E402


def pct(a, qs=(0, 10, 50, 90, 100)):
    a = np.asarray(a, float)
    return " ".join("%s%.2f" % ("min " if q == 0 else "max " if q == 100 else "p%d " % q, np.percentile(a, q)) for q in qs)


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


print("=== SCN-001 科目1 直线飞行与速度变换 (phase 1) ===")
cap_t, peak, over32, never, dev_after, out5, out10, ymax, lat_act, lon_int, psimax = ([] for _ in range(11))
for name, df in task1_unique():
    p = df[df["Phase ID"] == 1].reset_index(drop=True)
    t = p["Simulation time"].values - p["Simulation time"].values[0]
    v = np.hypot(p["V_ex m/s"].values, p["V_ey m/s"].values) / KT
    k = first_sustained(t, v >= 29.0, 0.3)
    peak.append(v.max())
    ymax.append(np.abs(p["Ye m"].values).max())
    psimax.append(np.abs(wrap180(p["psi deg"].values - 270)).max())
    lat_act.append(100 * np.mean(np.abs(p["Pilot Lat"].values) > 5))
    if k is None:
        never.append(name)
        continue
    cap_t.append(t[k])
    after = v[k:]
    dev_after.append(np.abs(after - 30).max())
    out5.append(np.sum(np.abs(after - 30) > 5) * 0.01)
    out10.append(np.sum(np.abs(after - 30) > 10) * 0.01)
    lon_int.append(100 * np.mean(np.abs(p["Pilot Lon"].values[k:]) > 5))
print("runs never sustaining >=29 kt:", never)
print("time to capture 29 kt (s):", pct(cap_t))
print("peak ground speed (kt):", pct(peak), "| >32 kt:", sum(x > 32 for x in peak), " >35 kt:", sum(x > 35 for x in peak), " >40 kt:", sum(x > 40 for x in peak))
print("after capture: max |v-30| (kt):", pct(dev_after))
print("after capture: time with |v-30|>5 kt (s):", pct(out5), "| runs with any:", sum(x > 0 for x in out5))
print("after capture: time with |v-30|>10 kt (s):", pct(out10), "| runs with any:", sum(x > 0 for x in out10))
print("after capture: % time |Lon|>5:", pct(lon_int), "| runs intervening >5% of time:", sum(x > 5 for x in lon_int))
print("phase-1 max |Y| (m):", pct(ymax), "| >2 m:", sum(x > 2 for x in ymax), " >5 m:", sum(x > 5 for x in ymax))
print("phase-1 max heading error (deg):", pct(psimax), "| % time |Lat|>5:", pct(lat_act))

print("\n=== SCN-002 低速移位与到点悬停 (phase 1 -> 2) ===")
xt, vmax, rev_lon, rev_lat, t_dec, creep, v_arr, drift2, endxy = ([] for _ in range(9))
for name, df in task3_all():
    p1 = df[df["Phase ID"] == 1].reset_index(drop=True)
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    if len(p1) == 0 or len(p2) == 0:
        continue
    t = p1["Simulation time"].values - p1["Simulation time"].values[0]
    x, y = p1["Xe m"].values, p1["Ye m"].values
    vh = np.hypot(p1["V_ex m/s"].values, p1["V_ey m/s"].values)
    ex, ey = x[-1] - x[0], y[-1] - y[0]
    L = np.hypot(ex, ey)
    cross = np.abs((x - x[0]) * ey - (y - y[0]) * ex) / L  # distance to the run's own start->end line
    xt.append(cross.max())
    vmax.append(vh.max())
    rev_lon.append(reversals(p1["Pilot Lon"].values.astype(float), 10.0))
    rev_lat.append(reversals(p1["Pilot Lat"].values.astype(float), 10.0))
    # final deceleration: last time vh was >= 50% of its max, then time until first sustained vh <= 0.2 m/s
    hi = np.where(vh >= 0.5 * vh.max())[0][-1]
    st = first_sustained(t[hi:], vh[hi:] <= 0.2, 1.0)
    t_dec.append(t[hi + st] - t[hi] if st is not None else np.nan)
    dist_left = np.hypot(x[-1] - x[hi], y[-1] - y[hi])
    creep.append(dist_left)
    v_arr.append(vh[-1])
    p2x, p2y = p2["Xe m"].values, p2["Ye m"].values
    drift2.append(np.hypot(p2x[-1] - p2x[0], p2y[-1] - p2y[0]))
    endxy.append((x[-1], y[-1]))
endxy = np.array(endxy)
print("runs:", len(xt))
print("max cross-track from own start->end line (m):", pct(xt))
print("max ground speed (m/s):", pct(vmax), "(kt %.1f-%.1f)" % (min(vmax) / KT, max(vmax) / KT))
print("Lon reversals (>10 units):", pct(rev_lon), "| Lat reversals:", pct(rev_lat))
print("final decel: time from last vh>=50%% max to sustained vh<=0.2 (s):", pct([z for z in t_dec if z == z]))
print("distance remaining at that moment (m):", pct(creep))
print("speed at end of phase 1 (m/s):", pct(v_arr), "| horizontal drift during phase 2 (m):", pct(drift2))
print("end-of-phase-1 position spread: X %.2f..%.2f  Y %.2f..%.2f" % (endxy[:, 0].min(), endxy[:, 0].max(), endxy[:, 1].min(), endxy[:, 1].max()))

print("\n=== SCN-002 垂直升降与悬停建立 (phases 3/5/7) ===")
over, settle, hrev, endh, hold_drift, dur, vzmax = ([] for _ in range(7))
for name, df in task3_all():
    if not set(range(1, 10)) <= set(df["Phase ID"].unique()):
        continue
    for ph in (3, 5, 7):
        d = df[df["Phase ID"] == ph].reset_index(drop=True)
        nxt = df[df["Phase ID"] == ph + 1]
        t = d["Simulation time"].values - d["Simulation time"].values[0]
        h = -d["Ze m"].values
        sgn = 1 if h[-1] > h[0] else -1
        h_final = float(np.mean(-nxt["Ze m"].values))  # settled height in the following hold
        over.append(max(0.0, sgn * (np.max(sgn * h) * sgn - h_final)) if sgn > 0 else max(0.0, h_final - h.min()))
        within = np.abs(h - h_final) <= 0.3
        k = first_sustained(t, within, 1.0)
        settle.append(t[-1] - t[k] if k is not None else np.nan)
        hrev.append(reversals(d["Pilot Heave"].values.astype(float), 10.0))
        endh.append((ph, h_final))
        hn = -nxt["Ze m"].values
        hold_drift.append(abs(hn[-1] - hn[0]))
        dur.append(t[-1])
        vzmax.append(np.abs(d["V_ez m/s"].values).max())
print("instances:", len(over))
print("overshoot beyond the settled height (m):", pct(over))
print("Heave reversals (>10 units):", pct(hrev))
print("transfer duration (s):", pct(dur), "| max |Vz| (m/s):", pct(vzmax))
print("height drift during following hold (m):", pct(hold_drift))
up = [h for ph, h in endh if ph in (3, 7)]
lo = [h for ph, h in endh if ph == 5]
print("settled upper heights: %.2f..%.2f  lower: %.2f..%.2f" % (min(up), max(up), min(lo), max(lo)))
