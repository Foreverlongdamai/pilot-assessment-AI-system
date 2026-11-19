"""Replay the 6 synthetic demo inputs with the exact per-checkpoint CPTs from configuration.json.

Validates the current-method emulation against the software's own reported scores, then
computes the evidence-normalized method on the same checkpoint grades.
"""
import json
import os

import numpy as np

BASE = r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\examples\task-scope-2026-10-11"
SCORES = np.array([0, 50, 100.0])
TARGET = {"D": np.array([0, 0, 1.0]), "A": np.array([0, 1.0, 0]), "U": np.array([1.0, 0, 0])}


def worst(gs):
    return "U" if "U" in gs else ("A" if "A" in gs else "D")


def current(frames, model):
    p = np.array(model["prior"], float)
    alpha = model["compensation"]["alpha"]
    for obs in frames:
        if not obs:
            continue
        ll = np.zeros(3)
        for cp, g in obs.items():
            c = model["checkpoint_models"][cp]
            ll += np.log(np.array(c["probabilities"])[:, c["states"].index(g)])
        lq = np.log(p) + ll
        q = np.exp(lq - lq.max()); q /= q.sum()
        p = (1 - alpha) * q + alpha * TARGET[worst(list(obs.values()))]
    return p


def normalized(frames, model, kappa=3.0):
    cps = model["checkpoint_models"]
    K = len(cps)
    n = {}
    for obs in frames:
        for cp in obs:
            n[cp] = n.get(cp, 0) + 1
    lp = np.log(np.array(model["prior"], float))
    for obs in frames:
        for cp, g in obs.items():
            c = cps[cp]
            lp = lp + kappa / K / n[cp] * np.log(np.array(c["probabilities"])[:, c["states"].index(g)])
    p = np.exp(lp - lp.max())
    return p / p.sum()


maxerr = 0.0
print("scene    case             item            rule  D/A/U frames      software  replay   NEW")
for scn in ("SCN-001", "SCN-002"):
    cfg = json.load(open(os.path.join(BASE, scn, "configuration.json"), encoding="utf-8"))
    for case in ("01-proficient", "02-marginal", "03-unqualified"):
        rep = json.load(open(os.path.join(BASE, scn, case + ".report.json"), encoding="utf-8"))
        for it in rep["items"]:
            model = cfg["skill_models"].get(it["item_id"])
            if model is None:
                continue
            look = {cp["checkpoint_id"]: {p["frame_index"]: p["grade"] for p in cp["timeline"] if p["grade"] is not None}
                    for cp in it["checkpoints"]}
            frames = []
            for pt in it["timeline"]:
                frames.append({cp: lk[pt["frame_index"]] for cp, lk in look.items() if pt["frame_index"] in lk})
            sw = it["skill_quantification"]["score"]
            rc = current(frames, model) @ SCORES
            nw = normalized(frames, model) @ SCORES
            maxerr = max(maxerr, abs(rc - sw))
            c = it["frame_distribution"]["counts"]
            print("%s  %-15s  %-14s  %s     %3d/%3d/%3d      %7.3f  %7.3f  %5.1f" % (
                scn, case, it["item_id"], it["grade"], c["D"], c["A"], c["U"], sw, rc, nw))
print("max |replay - software score| = %.2e" % maxerr)
