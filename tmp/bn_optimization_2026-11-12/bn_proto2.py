import contextlib
import io

import numpy as np

with contextlib.redirect_stdout(io.StringIO()):
    import bn_proto as P
from load import task1_unique

rows = {r["name"]: r for r in P.rows}
cur_rel, new_rel = [], []
rec_times = []
track_only = []
dup = []
for name, df in task1_unique():
    gr = P.run_grades(df)
    f100 = P.frames_from(gr, 1)
    r = rows[name]
    # (a) within final-position group, does current final depend on track U fraction?
    # (b) recovery time after a U run in the current per-frame trace (100 Hz, process segment only)
    tf = [{"track": g} for g in gr["track"][: gr["end"]]]
    _, tr = P.current_method(tf)
    g = gr["track"][: gr["end"]]
    i = 1
    while i < len(g):
        if g[i - 1] == "U" and g[i] != "U":
            k = i
            while k < len(g) and g[k] != "D":
                k += 1
            j = k
            while j < len(tr) and tr[j] < 90 and g[j] == "D":
                j += 1
            if k < len(tr) and j < len(tr) and tr[j] >= 90:
                rec_times.append((j - k + 1) * 0.01)
            i = max(i + 1, k)
        else:
            i += 1
    # (c) process-only item at 100 vs 10 Hz
    tf10 = tf[::10]
    if tf10[-1] is not tf[-1]:
        tf10 = tf10 + [tf[-1]]
    pc, _ = P.current_method(tf)
    pc10, _ = P.current_method(tf10)
    pn, _ = P.normalized_method(tf, {"track": 1.0})
    pn10, _ = P.normalized_method(tf10, {"track": 1.0})
    track_only.append((name, pc @ P.SCORES, pc10 @ P.SCORES, pn @ P.SCORES, pn10 @ P.SCORES, r["track_U"], tf[-1]["track"]))
    # (d) duplicating one checkpoint (e.g. lateral and heading entered as two checkpoints with same grade)
    fd = []
    for obs in f100:
        o = dict(obs)
        if "track" in o:
            o["track2"] = o["track"]
        fd.append(o)
    pcd, _ = P.current_method(fd)
    wd = {"track": 1 / 6, "track2": 1 / 6, "smooth": 1 / 3, "pos": 1 / 3}
    pnd, _ = P.normalized_method(fd, wd)
    dup.append((abs(pcd @ P.SCORES - r["cur"]), abs(pnd @ P.SCORES - r["new"])))

groups = {}
for r in P.rows:
    groups.setdefault((r["smooth"], r["pos"]), []).append(r)
print("within groups of equal (smoothness grade, final-position grade), spread of final score caused by track history:")
for key, sel in sorted(groups.items()):
    if len(sel) >= 4:
        cu = np.array([r["cur"] for r in sel]); nu = np.array([r["new"] for r in sel]); tu = np.array([r["track_D"] for r in sel])
        print("  smooth %s pos %s n=%2d  track D share %3.0f-%3.0f%%  CURRENT range %.1f-%.1f  NEW range %.1f-%.1f  corr(track D share, NEW)=%.2f" % (
            key[0], key[1], len(sel), 100 * tu.min(), 100 * tu.max(), cu.min(), cu.max(), nu.min(), nu.max(), np.corrcoef(tu, nu)[0, 1]))
rt = np.array(rec_times)
print("CURRENT, 100 Hz: after a U run ends and D resumes, time to score>=90: n=%d median %.2f s, max %.2f s" % (len(rt), np.median(rt), rt.max()))
to = np.array([x[1:5] for x in track_only], dtype=float)
lastD = sum(1 for x in track_only if x[6] == "D")
print("process-only item: last main-decel frame is D in %d/65 runs; CURRENT final>=99 in %d/65 (track U share up to %.0f%%)" % (
    lastD, int(np.sum(to[:, 0] >= 99)), 100 * max(x[5] for x in track_only if x[1] >= 99)))
print("process-only item 100 vs 10 Hz: CURRENT max |diff| %.2f, NEW max |diff| %.3f" % (np.max(np.abs(to[:, 0] - to[:, 1])), np.max(np.abs(to[:, 2] - to[:, 3]))))
d = np.array(dup)
print("duplicating the track checkpoint: CURRENT final changes up to %.1f points (median %.1f); NEW (shared aspect weight) up to %.3f" % (d[:, 0].max(), np.median(d[:, 0]), d[:, 1].max()))
