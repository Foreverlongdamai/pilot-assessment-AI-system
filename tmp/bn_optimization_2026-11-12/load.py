"""Shared loader for independent re-computation of the 2026-11-02 discussion doc numbers."""
import hashlib
import glob
import os

import numpy as np
import pandas as pd

ROOT = r"C:\Users\long\Desktop\CranfieldOffer\proj\data"
TASK1 = os.path.join(ROOT, "Mai_task1_accelerate_decelerate")
TASK3 = os.path.join(ROOT, "Mai_task3_hover")


def load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def task1_unique():
    """Return list of (short_name, df) for the 65 unique-content task-1 CSVs (sorted by name)."""
    seen = {}
    out = []
    for p in sorted(glob.glob(os.path.join(TASK1, "*.csv"))):
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if h in seen:
            continue
        seen[h] = p
        name = os.path.basename(p).split("Time_2026_09_24_")[1][:8]
        out.append((name, load_csv(p)))
    return out


def task3_all():
    out = []
    for p in sorted(glob.glob(os.path.join(TASK3, "*.csv"))):
        name = os.path.basename(p).replace("S_5_Time_2026_09_25_", "").replace("_P_1", "").replace(".csv", "")
        out.append((name, load_csv(p)))
    return out


def runs(mask):
    """Return list of (start_idx, end_idx_inclusive) for consecutive True runs."""
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return []
    d = np.diff(np.concatenate([[0], m.astype(int), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0] - 1
    return list(zip(starts, ends))


def first_sustained(t, mask, min_dur, eps=1e-9):
    """Index of the first sample of the first run of True lasting >= min_dur (t_last - t_first)."""
    for s, e in runs(mask):
        if t[e] - t[s] >= min_dur - eps:
            return s
    return None


def wrap180(a):
    return (np.asarray(a) + 180.0) % 360.0 - 180.0


KT = 1852.0 / 3600.0
