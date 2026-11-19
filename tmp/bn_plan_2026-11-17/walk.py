"""Worked example: whole-process analysis of one attempt -> evidence E1..E4 -> sequential update of the 科目 ability.

Run: python walk.py [run_name]   (default 15_21_09)
"""
import sys

import numpy as np

from evidence import (B_metric, H_metric, first_sustained, initial_rest, reversals, runs, segment, wrap180)
from grm_bn import EVID, NAMES, TO_DAU, Model, load, obs_of, woe_high
from load import task1_unique

name = sys.argv[1] if len(sys.argv) > 1 else "15_21_09"
df = dict(task1_unique())[name]
r = next(x for x in load(1) if x["name"] == name)
p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
t = p2["Simulation time"].values - p2["Simulation time"].values[0]
dt = 0.01

print("=== 全过程分析：", name, " phase 2 时长 %.1f s ===" % t[-1])
end = segment(p2)
ey = np.abs(p2["Ye m"].values[:end])
ep = np.abs(wrap180(p2["psi deg"].values[:end] - 270.0))
fr = np.where((ey > 5) | (ep > 10), 2, np.where((ey > 2) | (ep > 5), 1, 0))
print("[E1 减速航迹与航向] 窗口 0–%.2f s（主减速段，至首次持续0.5 s低于0.5 m/s）" % t[end - 1])
print("  逐帧档位占比 D %.0f%% A %.0f%% U %.0f%%；横向偏差峰值 %.2f m，航向差峰值 %.2f°" % (
    100 * np.mean(fr == 0), 100 * np.mean(fr == 1), 100 * np.mean(fr == 2), ey.max(), ep.max()))
for lvl, lab in ((1, "超出D带"), (2, "超出A带")):
    eps = [(t[a], t[b] - t[a] + dt) for a, b in runs(fr >= lvl)]
    print("  %s的片段 %d 段%s" % (lab, len(eps), ("：" + ", ".join("%.1fs起持续%.2fs" % e for e in eps[:5])) if eps else ""))
print("  -> 规则：未超出A带、D带内时间≥99.9%% -> 第%d档 = %s" % (r["e1"], TO_DAU[r["e1"]]))

v = -p2["V_ex m/s"].values
u = p2["Pilot Lon"].values.astype(float)
B = B_metric(p2["Simulation time"].values[:end], v[:end])
H = H_metric(p2["Simulation time"].values[:end], v[:end], u[:end])
e = first_sustained(p2["Simulation time"].values, v <= 0.2 * v[0], 0.30)
print("[E2 减速平顺性] 入段速度 %.1f m/s" % v[0])
print("  B（相邻0.5 s窗口减速度差最大值）%.2f m/s² -> %s；H（0.8→0.2 v0 杆位P90−P10）%.1f -> %s；来回推拉 %d 次" % (
    B, r["gB"], H, r["gH"], r["turns"]))
print("  -> 规则：min(H档, 推拉档, B档) -> 第%d档 = %s" % (r["e2a"], TO_DAU[r["e2a"]]))

vh = np.hypot(p2["V_ex m/s"].values, p2["V_ey m/s"].values)
s1 = initial_rest(p2["Simulation time"].values, vh)
print("[E3 初次停住点] 初次停住时刻 %.2f s，ΔX₁ = %+.1f m（正为停短），ΔY₁ = %+.1f m" % (t[s1], r["dx1"], r["dy1"]))
print("  -> 规则（D-013）：D 0≤ΔX₁≤5 且|ΔY₁|≤2；A −5≤ΔX₁≤15 且|ΔY₁|≤5 -> %s" % TO_DAU[r["e3"]])

mv = [(t[a + s1], t[b + s1]) for a, b in runs(vh[s1:] > 0.5) if t[b + s1] - t[a + s1] >= 0.5 - 1e-9]
print("[E4 末端修正] 初次停住后的挪动 %d 次（两轴合计），反复修正 %d 次，无效修正 %d 次；最终停点 ΔX %+.1f ΔY %+.1f -> 检查点一 %s" % (
    r["n_mv"], r["n_rev"], r["n_ineff"], p2["Xe m"].values[-1] + 500, p2["Ye m"].values[-1], r["cp1"]))
print("  -> 规则：挪动≤3、反复≤1、无效0 -> 第%d档 = %s" % (r["e4"], TO_DAU[r["e4"]]))

print("\n=== 逐条更新科目能力（9个格点） ===")
m = Model()
p = m.prior.copy()
times = {"e1": t[end - 1], "e2a": t[end - 1], "e3": t[s1], "e4": t[-1]}
sc, sd, b = m.report(p)
print("  先验                     能力分 %5.1f ± %4.1f  低%.2f 中%.2f 高%.2f" % (sc, sd, *b))
for k, c in zip(EVID, obs_of(m, r)):
    if c is None:
        print("  %s 不适用" % NAMES[k])
        continue
    p = p * m.cpt[:, c]
    p /= p.sum()
    sc, sd, b = m.report(p)
    print("  t=%5.1f s  %-12s %s (WOE %+.2f) -> 能力分 %5.1f ± %4.1f  低%.2f 中%.2f 高%.2f" % (
        times[k], NAMES[k], "UAD"[c], woe_high(m, c), sc, sd, *b))
print("  格点后验:", np.round(p, 3))
print("  门控（检查点一、二）：", "Fail" if "U" in (TO_DAU[r["e1"]], r["cp1"]) else "Pass")
