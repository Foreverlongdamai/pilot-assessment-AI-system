"""Prototype: current per-frame Bayes+compensation vs evidence-normalized sequential Bayes.

Same checkpoint grades feed both methods, so differences are due to the network only.
Item: SCN-001 '受控减速与定点停止' on 65 real runs.
  CP1 减速过程航迹与航向 (process, per frame in main decel; worst of |e_y| 2/5 m, |e_psi| 5/10 deg)
  CP2 减速平顺性 (event at end of main decel; worst of B 0.5/1.0, H 20/50)
  CP3 最终停点位置 (event at last frame of phase 2; D-004 rectangle)
"""
import json
import math
import os
import sys

import numpy as np

from load import task1_unique, first_sustained, wrap180

THETA = np.array([[0.10, 0.25, 0.65], [0.35, 0.63, 0.02], [0.90, 0.099, 0.001]])  # rows L,M,H ; cols D,A,U
GI = {"D": 0, "A": 1, "U": 2}
TARGET = {"D": np.array([0, 0, 1.0]), "A": np.array([0, 1.0, 0]), "U": np.array([1.0, 0, 0])}
SCORES = np.array([0, 50, 100.0])
PRIOR = np.ones(3) / 3


def worst(gs):
    gs = [g for g in gs if g is not None]
    if not gs:
        return None
    return "U" if "U" in gs else ("A" if "A" in gs else "D")


# ---------------- methods ----------------
def current_method(frames, alpha=0.2, theta=THETA):
    """frames: list of dict cp->grade (only observed cps). Mirrors sequential_compensation.py item trace."""
    p = PRIOR.copy()
    trace = []
    for obs in frames:
        if not obs:
            trace.append(None)
            continue
        loglik = sum(np.log(theta[:, GI[g]]) for g in obs.values())
        q = np.exp(np.log(p) + loglik - np.max(np.log(p) + loglik))
        q /= q.sum()
        p = (1 - alpha) * q + alpha * TARGET[worst(list(obs.values()))]
        trace.append(float(p @ SCORES))
    return p, trace


def normalized_method(frames, weights, kappa=3.0, theta=THETA, prior=PRIOR):
    """Each checkpoint contributes kappa*w_k in total per instance, spread over its observed frames."""
    n = {}
    for obs in frames:
        for k in obs:
            n[k] = n.get(k, 0) + 1
    lp = np.log(prior).copy()
    trace = []
    for obs in frames:
        for k, g in obs.items():
            lp = lp + kappa * weights[k] / n[k] * np.log(theta[:, GI[g]])
        p = np.exp(lp - lp.max())
        p /= p.sum()
        trace.append(float(p @ SCORES))
    return p, trace


# ---------------- real-data grades ----------------
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


def grid(t, y, step):
    tr = t - t[0]
    m = int(np.floor(tr[-1] / step + 1e-9))
    g = np.arange(m + 1) * step
    return g, np.interp(g, tr, y)


def B_metric(t, v):
    g, vg = grid(t, v, 0.1)
    dec = (vg[:-5] - vg[5:]) / 0.5
    d = np.abs(dec[5:] - dec[:-5])
    return float(d.max())


def H_metric(t, v, u):
    v0 = v[0]
    s = first_sustained(t, v <= 0.8 * v0, 0.30)
    e = first_sustained(t, v <= 0.2 * v0, 0.30)
    if s is None or e is None or e <= s or t[e] - t[s] < 1.0:
        return None
    return float(np.percentile(u[s:e], 90) - np.percentile(u[s:e], 10))


def g3(x, d, a):
    return "D" if x <= d else ("A" if x <= a else "U")


def run_grades(df):
    p2 = df[df["Phase ID"] == 2].reset_index(drop=True)
    t = p2["Simulation time"].values
    v = -p2["V_ex m/s"].values
    u = p2["Pilot Lon"].values
    end = segment(p2)
    ey = np.abs(p2["Ye m"].values)
    ep = np.abs(wrap180(p2["psi deg"].values - 270.0))
    track = []
    for i in range(len(t)):
        if i < end:
            track.append(worst([g3(ey[i], 2, 5), g3(ep[i], 5, 10)]))
        else:
            track.append(None)
    B = B_metric(t[:end], v[:end])
    H = H_metric(t[:end], v[:end], u[:end])
    smooth = worst([g3(B, 0.5, 1.0), g3(H, 20, 50) if H is not None else None])
    dx, dy = abs(p2["Xe m"].values[-1] + 500), abs(p2["Ye m"].values[-1])
    pos = "D" if (dx <= 5 and dy <= 2) else ("A" if (dx <= 15 and dy <= 5) else "U")
    return dict(track=track, end=end, smooth=smooth, pos=pos, n=len(t), B=B, H=H)


def frames_from(gr, decimate=1):
    frames = []
    idx = list(range(0, gr["n"], decimate))
    if idx[-1] != gr["n"] - 1:
        idx.append(gr["n"] - 1)
    smooth_at = gr["end"] - 1
    # ensure the smoothness event frame is kept when decimating
    if smooth_at not in idx:
        idx = sorted(set(idx) | {smooth_at})
    for i in idx:
        obs = {}
        if gr["track"][i] is not None:
            obs["track"] = gr["track"][i]
        if i == smooth_at:
            obs["smooth"] = gr["smooth"]
        if i == gr["n"] - 1:
            obs["pos"] = gr["pos"]
        frames.append(obs)
    return frames


W = {"track": 1 / 3, "smooth": 1 / 3, "pos": 1 / 3}

rows = []
for name, df in task1_unique():
    gr = run_grades(df)
    f100 = frames_from(gr, 1)
    f10 = frames_from(gr, 10)
    pc, trc = current_method(f100)
    pc10, _ = current_method(f10)
    pn, trn = normalized_method(f100, W)
    pn10, _ = normalized_method(f10, W)
    tg = [g for g in gr["track"] if g is not None]
    comp = {g: tg.count(g) / len(tg) for g in "DAU"}
    item_grade = worst(tg + [gr["smooth"], gr["pos"]])
    cur_vals = [x for x in trc if x is not None]
    rows.append(dict(name=name, track_D=comp["D"], track_A=comp["A"], track_U=comp["U"],
                     smooth=gr["smooth"], pos=gr["pos"], item=item_grade,
                     cur=float(pc @ SCORES), cur10=float(pc10 @ SCORES),
                     new=float(pn @ SCORES), new10=float(pn10 @ SCORES),
                     cur_min=min(cur_vals), cur_post=[round(x, 4) for x in pc], new_post=[round(x, 4) for x in pn]))

cur = np.array([r["cur"] for r in rows]); new = np.array([r["new"] for r in rows])
print("=== 65 real runs, item '受控减速与定点停止' (3 checkpoints) ===")
print("rule item grade counts:", {g: sum(r["item"] == g for r in rows) for g in "DAU"})
print("CURRENT final score: distinct rounded values:", sorted(set(np.round(cur, 1)))[:12], "...")
print("CURRENT final by final-position grade:", {g: (round(float(np.mean([r['cur'] for r in rows if r['pos'] == g])), 1), sum(r['pos'] == g for r in rows)) for g in "DAU"})
print("CURRENT: runs with an U-grade checkpoint that still end >= 90:", sum(1 for r in rows if r["item"] == "U" and r["cur"] >= 90))
print("NEW final score: min %.1f median %.1f max %.1f" % (new.min(), np.median(new), new.max()))
for g in "DAU":
    sel = [r["new"] for r in rows if r["item"] == g]
    if sel:
        print("  NEW by rule item grade %s: n=%d mean %.1f range [%.1f, %.1f]" % (g, len(sel), np.mean(sel), min(sel), max(sel)))
    sel = [r["cur"] for r in rows if r["item"] == g]
    if sel:
        print("  CUR by rule item grade %s: n=%d mean %.1f range [%.1f, %.1f]" % (g, len(sel), np.mean(sel), min(sel), max(sel)))
print("sample-rate 100 Hz vs 10 Hz: CURRENT max |diff| %.2f, NEW max |diff| %.3f" % (
    np.max(np.abs(cur - np.array([r["cur10"] for r in rows]))), np.max(np.abs(new - np.array([r["new10"] for r in rows])))))
# Monotonic sanity: correlation of new score with checkpoint composition
quality = np.array([r["track_D"] - r["track_U"] + {"D": 1, "A": 0, "U": -1}[r["smooth"]] + {"D": 1, "A": 0, "U": -1}[r["pos"]] for r in rows])
print("Spearman-like rank corr (new vs simple quality index): %.2f ; current: %.2f" % (
    np.corrcoef(np.argsort(np.argsort(new)), np.argsort(np.argsort(quality)))[0, 1],
    np.corrcoef(np.argsort(np.argsort(cur)), np.argsort(np.argsort(quality)))[0, 1]))
print("current min-along-trace median %.1f (how far it swings during the run)" % np.median([r["cur_min"] for r in rows]))

# examples
print("\nexamples (name | track D/A/U % | smooth | pos | rule | CURRENT | NEW):")
order = sorted(rows, key=lambda r: r["new"])
for r in order[:4] + order[30:33] + order[-4:]:
    print("  %s | %3.0f/%3.0f/%3.0f | %s | %s | %s | %6.1f | %6.1f" % (
        r["name"], 100 * r["track_D"], 100 * r["track_A"], 100 * r["track_U"], r["smooth"], r["pos"], r["item"], r["cur"], r["new"]))

# ---------------- synthetic demo cases ----------------
print("\n=== 6 synthetic demo inputs (existing report checkpoint grades) ===")
base = r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\examples\task-scope-2026-10-11"
for scn in ("SCN-001", "SCN-002"):
    for case in ("01-proficient", "02-marginal", "03-unqualified"):
        rep = json.load(open(os.path.join(base, scn, case + ".report.json"), encoding="utf-8"))
        for it in rep["items"]:
            if not it["checkpoints"] or it["item_id"] == "A-S1-06":
                continue
            K = len(it["checkpoints"])
            lookups = [{p["frame_index"]: p["grade"] for p in cp["timeline"] if p["grade"] is not None} for cp in it["checkpoints"]]
            frame_ids = [p["frame_index"] for p in it["timeline"]]
            frames = []
            for fi in frame_ids:
                obs = {}
                for k, lk in enumerate(lookups):
                    if fi in lk:
                        obs[k] = lk[fi]
                frames.append(obs)
            pc, _ = current_method(frames)
            pn, _ = normalized_method(frames, {k: 1 / K for k in range(K)})
            cnt = it["frame_distribution"]["counts"]
            print("  %s %-15s %-15s rule %s  D/A/U frames %3d/%3d/%3d  CURRENT %6.1f  NEW %6.1f" % (
                scn, case, it["item_id"], it["grade"], cnt["D"], cnt["A"], cnt["U"], pc @ SCORES, pn @ SCORES))

# ---------------- anchor table for kappa ----------------
print("\n=== kappa anchors with current CPT (single checkpoint or all checkpoints same composition) ===")
for kappa in (2, 3, 4, 5):
    out = []
    for comp in ((1, 0, 0), (0.9, 0.1, 0), (0.7, 0.3, 0), (0.5, 0.5, 0), (0, 1, 0), (0.9, 0, 0.1), (0.8, 0, 0.2), (0.5, 0.3, 0.2), (0, 0, 1)):
        lp = np.log(PRIOR) + kappa * (np.log(THETA) @ np.array(comp))
        p = np.exp(lp - lp.max()); p /= p.sum()
        out.append("%s:%.1f" % ("/".join(str(int(100 * c)) for c in comp), p @ SCORES))
    print("  kappa=%d  " % kappa + "  ".join(out))

json.dump(rows, open("bn_proto_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
