"""Prototype of the proposed assessment Bayesian network (2026-11-17 plan) on the 65 real SCN-001 runs.

Design under test
  * Ability layer: J equal-probability quantile points of N(0,1), theta_j = Phi^-1((j-0.5)/J); prior 1/J each.
    J=3 gives Almond's effective thetas (-0.97, 0, 0.97) and the current uniform low/mid/high prior.
    Bands low/mid/high = prior terciles (theta cut at +-0.431); with J=9, three grid points per band.
  * Evidence: each checkpoint observable enters ONCE per attempt (ECD evidence accumulation).
  * CPT: Samejima graded response, P(X>=c | theta) = logistic(1.7 a (theta - b_c)), a = 1.
    3 grades U<A<D: b = (-b0, +b0); b0 chosen so that A is the modal grade exactly on the middle band
    ("modal principle": low band -> U most likely, mid -> A, high -> D). a=1 gives b0 = 0.605.
    5 levels (IATA 1..5 nested 1->U, 2-3->A, 4-5->D): equally spaced b = (-b0, 0, b0, 2 b0).
  * Score: expected grade points at each grid point (U=0, A=50, D=100; IRT expected/true score), EAP over the
    posterior; report SD and band probabilities. Same score scale for 3-level and 5-level evidence.
  * Profile across attempts: AR(1) on theta, rho per attempt; rho=0 -> attempt score, rho=1 -> static ability.
Run: python grm_bn.py   (needs evidence_dec1.json / evidence_dec10.json from evidence.py)
"""
import collections
import json
import math
import os
import time

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm, spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
TO_DAU = {5: "D", 4: "D", 3: "A", 2: "A", 1: "U"}
DAU_IDX = {"U": 0, "A": 1, "D": 2}
EVID = ("e1", "e2a", "e3", "e4")
NAMES = {"e1": "E1 减速航迹与航向", "e2a": "E2 减速平顺性", "e3": "E3 初次停住点", "e4": "E4 末端修正"}
TERCILE = norm.ppf(2 / 3)  # 0.4307


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def modal_b0(a):
    """b0 such that P(A) = P(D) exactly at the mid/high band boundary theta = +0.431 (A-modal region = mid band)."""
    return brentq(lambda b: sig(1.7 * a * (TERCILE + b)) - 2 * sig(1.7 * a * (TERCILE - b)), 0.0, 3.0)


class Model:
    def __init__(self, J=9, a=1.0, b0="modal", five=False, score="tcc"):
        self.J = J
        self.theta = norm.ppf((np.arange(1, J + 1) - 0.5) / J)
        self.prior = np.full(J, 1.0 / J)
        self.a = a
        self.five = five
        self.b0 = modal_b0(a) if b0 == "modal" else float(b0)
        b0 = self.b0
        self.b = np.array((-b0, 0.0, b0, 2 * b0) if five else (-b0, b0))
        self.band = np.digitize(self.theta, [-TERCILE, TERCILE])
        self.cpt = self.grm(self.theta)
        # grade points per category: U=0, A=50, D=100 (5 levels nested 1->U, 2-3->A, 4-5->D)
        self.v = np.array([0, 50, 50, 100, 100] if five else [0, 50, 100], dtype=float)
        self.score = self.cpt @ self.v if score == "tcc" else np.linspace(0, 100, J)

    def grm(self, th):
        pge = sig(1.7 * self.a * (th[:, None] - self.b[None, :]))
        pge = np.hstack([np.ones((len(th), 1)), pge, np.zeros((len(th), 1))])
        return pge[:, :-1] - pge[:, 1:]  # columns: lowest .. highest category

    def cat(self, level):
        if level is None:
            return None
        return level - 1 if self.five else DAU_IDX[TO_DAU[level]]

    def loglik(self, obs):
        ll = np.zeros(self.J)
        for c in obs:
            if c is not None:
                ll += np.log(self.cpt[:, c])
        return ll

    def posterior(self, obs, prior=None):
        lp = np.log(self.prior if prior is None else prior) + self.loglik(obs)
        p = np.exp(lp - lp.max())
        return p / p.sum()

    def report(self, p):
        m = float(p @ self.score)
        sd = float(math.sqrt(max(p @ (self.score - m) ** 2, 0)))
        bands = [float(p[self.band == k].sum()) for k in range(3)]
        return m, sd, bands

    def band_cpt(self):
        return np.array([self.prior[self.band == k] @ self.cpt[self.band == k] / self.prior[self.band == k].sum()
                         for k in range(3)])


def load(dec):
    with open(os.path.join(HERE, f"evidence_dec{dec}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def obs_of(model, r, keys=EVID):
    return [model.cat(r[k]) for k in keys]


def kappa_method(r, kappa=3.0):
    """§9 proposal re-run: current CPT, kappa per instance split over 3 checkpoints (CP2 process, CP3 worst(B,H), CP1)."""
    th = np.array([[.10, .25, .65], [.35, .63, .02], [.90, .099, .001]])  # rows low/mid/high, cols D/A/U
    gi = {"D": 0, "A": 1, "U": 2}
    lp = np.log(np.ones(3) / 3)
    fA = 1 - r["cp2_fD"] - r["cp2_fU"]
    lp = lp + kappa / 3 * (r["cp2_fD"] * np.log(th[:, 0]) + fA * np.log(th[:, 1]) + r["cp2_fU"] * np.log(th[:, 2]))
    gs = max(r["gB"], r["gH"], key=lambda g: gi[g])
    lp = lp + kappa / 3 * (np.log(th[:, gi[gs]]) + np.log(th[:, gi[r["cp1"]]]))
    p = np.exp(lp - lp.max())
    p /= p.sum()
    return float(p @ np.array([0, 50, 100]))


def ar1_kernel(model, rho):
    """P(theta_t in bin j | theta_{t-1} = theta_i) for theta_t = rho theta + sqrt(1-rho^2) eps (stationary N(0,1))."""
    J = model.J
    cuts = np.concatenate([[-np.inf], norm.ppf(np.arange(1, J) / J), [np.inf]])
    if rho >= 1.0:
        return np.eye(J)
    s = math.sqrt(1 - rho ** 2)
    mu = rho * model.theta
    K = norm.cdf((cuts[None, 1:] - mu[:, None]) / s) - norm.cdf((cuts[None, :-1] - mu[:, None]) / s)
    return K / K.sum(axis=1, keepdims=True)


def forward(model, rows, rho, keys=EVID):
    K = ar1_kernel(model, rho)
    p = model.prior.copy()
    ll, traj = 0.0, []
    for t, r in enumerate(rows):
        if t > 0:
            p = p @ K
        lik = np.exp(model.loglik(obs_of(model, r, keys)))
        z = float(p @ lik)
        ll += math.log(z)
        p = p * lik / z
        traj.append(model.report(p))
    return ll, traj


def q3(model, rows, keys=EVID):
    """Yen's Q3 on grade points: correlation of (observed - posterior-expected) between evidence pairs."""
    vals = {k: [] for k in keys}
    for r in rows:
        obs = obs_of(model, r, keys)
        p = model.posterior(obs)
        for k, c in zip(keys, obs):
            if c is None:
                vals[k].append(np.nan)
                continue
            vals[k].append(model.v[c] / 100 - float(p @ (model.cpt @ model.v)) / 100)
    out = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            x, y = np.array(vals[a]), np.array(vals[b])
            ok = ~(np.isnan(x) | np.isnan(y))
            out[(a, b)] = float(np.corrcoef(x[ok], y[ok])[0, 1])
    return out


def woe_high(model, c, k_band=2):
    """Good's weight of evidence (natural log) of one observation for H = 'high band' vs not-high, prior-weighted."""
    h = model.band == k_band
    ph = float(model.prior[h] @ model.cpt[h, c] / model.prior[h].sum())
    pn = float(model.prior[~h] @ model.cpt[~h, c] / model.prior[~h].sum())
    return math.log(ph / pn)


def fmt_bands(b):
    return "低%.2f/中%.2f/高%.2f" % tuple(b)


def main():
    R = load(1)
    R10 = load(10)
    base = Model()
    print("=== 1. 能力格与CPT (J=9, a=1, b0=%.3f, 众数对应) ===" % base.b0)
    print("theta:", np.round(base.theta, 3))
    print("score = expected grade points per level:", np.round(base.score, 1))
    for j in range(base.J):
        print("  level %d theta %+.2f  U %.3f  A %.3f  D %.3f  score %.1f" % (j + 1, base.theta[j], *base.cpt[j], base.score[j]))
    bc = base.band_cpt()
    print("band-averaged CPT (rows low/mid/high; cols U/A/D):")
    print(np.round(bc, 3))
    marg = base.prior @ base.cpt
    print("prior predictive grade mix U/A/D: %.2f/%.2f/%.2f" % tuple(marg))
    for g, k in (("U", 0), ("A", 1), ("D", 2)):
        lr = math.log(bc[2, k] / bc[0, k])
        print("  one %s: ln LR high vs low band %+.2f (2lnB %.2f); WOE high vs not-high %+.2f" % (g, lr, 2 * abs(lr), woe_high(base, k)))
    print("  current CPT one U: ln LR high vs low %.2f (2lnB %.2f)" % (math.log(.001 / .65), 2 * abs(math.log(.001 / .65))))

    print("\n=== 2. 锚点：单次动作 ===")
    for pattern in ("DDDD", "DDD", "AAAA", "AAA", "UUUU", "UUU", "DDDU", "DDDA", "DDAA", "AAAU", "DAUU", "UUUD", "DDUU"):
        m, sd, b = base.report(base.posterior([DAU_IDX[g] for g in pattern]))
        print("  %-5s score %5.1f  SD %4.1f  %s   (raw mean grade points %.0f)" % (
            pattern, m, sd, fmt_bands(b), np.mean([{"D": 100, "A": 50, "U": 0}[g] for g in pattern])))
    for n in (1, 2, 4, 8, 16, 32):
        obs = [2] * (7 * n) + [1] * (2 * n) + [0] * n
        m, sd, _ = base.report(base.posterior(obs))
        obs2 = [2] * (2 * n) + [1] * (5 * n) + [0] * (3 * n)
        m2, sd2, _ = base.report(base.posterior(obs2))
        print("  %3d obs: 70%%D/20%%A/10%%U (raw 80) -> %5.1f ± %4.1f | 20/50/30 (raw 45) -> %5.1f ± %4.1f" % (
            len(obs), m, sd, m2, sd2))

    print("\n=== 3. 65 趟：单次表现分 (E1..E4, 三档) ===")
    res = []
    for r in R:
        obs = obs_of(base, r)
        m, sd, b = base.report(base.posterior(obs))
        e1 = TO_DAU[r["e1"]]
        g = "Fail" if ("U" in (e1, r["cp1"])) else "Pass"
        grades = [TO_DAU[r[k]] for k in EVID if r[k] is not None]
        worst = max(grades, key=lambda x: {"D": 0, "A": 1, "U": 2}[x])
        raw = float(np.mean([{"D": 100, "A": 50, "U": 0}[x] for x in grades]))
        res.append(dict(name=r["name"], score=m, sd=sd, bands=b, gate=g, worst=worst, raw=raw,
                        pattern="".join(TO_DAU[r[k]] if r[k] is not None else "-" for k in EVID), kappa=kappa_method(r)))
    sc = np.array([x["score"] for x in res])
    sds = np.array([x["sd"] for x in res])
    raw = np.array([x["raw"] for x in res])
    print("score: min %.1f p10 %.1f median %.1f p90 %.1f max %.1f; SD median %.1f (range %.1f-%.1f)" % (
        sc.min(), np.percentile(sc, 10), np.median(sc), np.percentile(sc, 90), sc.max(), np.median(sds), sds.min(), sds.max()))
    print("Spearman with raw mean grade points %.3f; max |score-raw| %.1f" % (spearmanr(sc, raw)[0], np.abs(sc - raw).max()))
    for g in ("Pass", "Fail"):
        s = sc[[x["gate"] == g for x in res]]
        print("  门控 %s (CP1/CP2 无U): n=%d  score %.1f-%.1f mean %.1f" % (g, len(s), s.min(), s.max(), s.mean()))
    for w in ("D", "A", "U"):
        s = sc[[x["worst"] == w for x in res]]
        if len(s):
            print("  证据最差档 %s: n=%d score %.1f-%.1f mean %.1f" % (w, len(s), s.min(), s.max(), s.mean()))
    pat = collections.Counter(x["pattern"] for x in res)
    print("distinct evidence patterns:", len(pat), " most common:", pat.most_common(6))
    hb = collections.Counter(int(np.argmax(x["bands"])) for x in res)
    print("modal band low/mid/high:", [hb.get(k, 0) for k in range(3)])
    ks = np.array([x["kappa"] for x in res])
    print("vs §9 kappa method: Spearman %.2f; kappa range %.1f-%.1f" % (spearmanr(sc, ks)[0], ks.min(), ks.max()))

    print("\n=== 4. 五档证据 vs 三档证据 (同一分数尺度) ===")
    five = Model(five=True)
    print("5-level thresholds", np.round(five.b, 3), "; score per level identical to 3-level:",
          np.allclose(five.score, base.score))
    sc5 = np.array([five.report(five.posterior(obs_of(five, r)))[0] for r in R])
    sd5 = np.array([five.report(five.posterior(obs_of(five, r)))[1] for r in R])
    print("5-level: score median %.1f range %.1f-%.1f, SD median %.1f (3-level %.1f); Spearman with 3-level %.3f; "
          "distinct scores %d vs %d; max|Δ| %.1f" % (
              np.median(sc5), sc5.min(), sc5.max(), np.median(sd5), np.median(sds), spearmanr(sc, sc5)[0],
              len(set(np.round(sc5, 2))), len(set(np.round(sc, 2))), np.abs(sc5 - sc).max()))
    for lv in (5, 4, 3, 2, 1):
        m, sd, b = five.report(five.posterior([lv - 1] * 4))
        print("  4 x level %d: score %.1f SD %.1f %s" % (lv, m, sd, fmt_bands(b)))

    print("\n=== 5. 敏感性 (基准 J=9, a=1, b0=%.3f, 期望得分映射) ===" % base.b0)

    def run_all(model):
        return np.array([model.report(model.posterior(obs_of(model, r)))[0] for r in R])

    for label, mdl in (("J=3", Model(J=3)), ("J=5", Model(J=5)), ("J=7", Model(J=7)), ("J=11", Model(J=11)),
                       ("J=41", Model(J=41)), ("a=0.7 modal", Model(a=0.7)), ("a=1.5 modal", Model(a=1.5)),
                       ("a=2.0 modal", Model(a=2.0)), ("a=0.7 fixb", Model(a=0.7, b0=base.b0)),
                       ("a=1.5 fixb", Model(a=1.5, b0=base.b0)), ("b0=0.431", Model(b0=TERCILE)),
                       ("b0=0.967", Model(b0=0.967)), ("linear J9", Model(score="linear")),
                       ("linear J41", Model(J=41, score="linear"))):
        s = run_all(mdl)
        mD = mdl.report(mdl.posterior([2, 2, 2, 2]))[0]
        mU = mdl.report(mdl.posterior([0, 0, 0, 0]))[0]
        sdm = np.median([mdl.report(mdl.posterior(obs_of(mdl, r)))[1] for r in R])
        print("  %-11s Spearman %.3f  max|Δ| %5.1f  mean|Δ| %4.1f  DDDD %5.1f  UUUU %5.1f  range %5.1f-%5.1f  SDmed %4.1f" % (
            label, spearmanr(sc, s)[0], np.abs(s - sc).max(), np.abs(s - sc).mean(), mD, mU, s.min(), s.max(), sdm))

    print("\n=== 6. 采样率：100 Hz vs 10 Hz ===")
    sc10 = np.array([base.report(base.posterior(obs_of(base, r)))[0] for r in R10])
    changed = [(R[i]["name"], k, R[i][k], R10[i][k]) for i in range(len(R)) for k in EVID if R[i][k] != R10[i][k]]
    print("5-level evidence changed:", changed)
    print("3-level score max|Δ| %.2f" % np.abs(sc10 - sc).max())
    sc510 = np.array([five.report(five.posterior(obs_of(five, r)))[0] for r in R10])
    print("5-level score max|Δ| %.2f" % np.abs(sc510 - sc5).max())

    print("\n=== 7. 局部相关 Q3 (三档) ===")
    qq = q3(base, R)
    mean = np.mean(list(qq.values()))
    for (a, b), v in qq.items():
        print("  %s ~ %s : %+.3f   (Q3 - mean = %+.3f)" % (a, b, v, v - mean))
    print("  mean Q3 %.3f; max(Q3 - mean) %.3f" % (mean, max(v - mean for v in qq.values())))

    print("\n=== 8. 检查点诊断：观察得分率 vs 模型期望 ===")
    for k in EVID:
        o = e = 0.0
        n = 0
        for r in R:
            if r[k] is None:
                continue
            p = base.posterior(obs_of(base, r))
            c = base.cat(r[k])
            o += base.v[c] / 100
            e += float(p @ (base.cpt @ base.v)) / 100
            n += 1
        print("  %-12s n=%2d observed %.2f expected %.2f  diff %+.2f" % (NAMES[k], n, o / n, e / n, (o - e) / n))

    print("\n=== 9. 证据权重示例 ===")
    for name in ("14_34_26", "15_17_23", "16_54_31", "15_42_13"):
        r = next(x for x in R if x["name"] == name)
        obs = obs_of(base, r)
        m, sd, b = base.report(base.posterior(obs))
        parts = []
        for k, c in zip(EVID, obs):
            parts.append("%s 不适用" % NAMES[k] if c is None else "%s %s WOE %+.2f" % (NAMES[k], "UAD"[c], woe_high(base, c)))
        print("  %s score %.1f ± %.1f %s | %s" % (name, m, sd, fmt_bands(b), "; ".join(parts)))

    print("\n=== 10. 能力档案：AR(1)，65 趟按时间顺序 ===")
    best = None
    for rho in (0.0, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 1.0):
        ll, traj = forward(base, R, rho)
        print("  rho %.3f  log marginal likelihood %.2f   final profile %.1f ± %.1f" % (rho, ll, traj[-1][0], traj[-1][1]))
        if best is None or ll > best[1]:
            best = (rho, ll, traj)
    rho, ll, traj = best
    print("best rho %.3f; profile at runs:" % rho,
          ["%d:%.0f±%.0f" % (n, traj[n - 1][0], traj[n - 1][1]) for n in (1, 3, 5, 10, 20, 30, 40, 50, 65)])
    print("attempt score mean first 20 %.1f / last 20 %.1f; Spearman(score, order) %.2f" % (
        np.mean(sc[:20]), np.mean(sc[-20:]), spearmanr(sc, np.arange(len(sc)))[0]))
    for k in EVID:
        x = [base.v[base.cat(r[k])] for r in R if r[k] is not None]
        o = [i for i, r in enumerate(R) if r[k] is not None]
        print("  %s Spearman(grade points, order) %+.2f" % (NAMES[k], spearmanr(x, o)[0]))
    rho_day = 0.05 ** (1 / 180)
    print("between-session rule: rho_day %.4f (T = %.0f days); after 1/7/30/90 days rho = %s" % (
        rho_day, -1 / math.log(rho_day), [round(rho_day ** d, 3) for d in (1, 7, 30, 90)]))
    p = base.posterior(sum((obs_of(base, r) for r in R), []))
    for d in (0, 1, 7, 30, 90):
        q = p @ ar1_kernel(base, rho_day ** d)
        print("  profile after 65 runs, then %2d days without training: %.1f ± %.1f %s" % ((d,) + base.report(q)[:2] + (fmt_bands(base.report(q)[2]),)))

    print("\n=== 11. 重复实例：连续 4 趟当作一次训练的 4 个实例 ===")
    for start in (0, 20, 40):
        grp = R[start:start + 4]
        each = [base.report(base.posterior(obs_of(base, r)))[0] for r in grp]
        m, sd, b = base.report(base.posterior(sum((obs_of(base, r) for r in grp), [])))
        print("  runs %d-%d: per-instance %s -> combined %.1f ± %.1f %s" % (
            start + 1, start + 4, ["%.0f" % x for x in each], m, sd, fmt_bands(b)))

    print("\n=== 12. 计算量 ===")
    t0 = time.perf_counter()
    for _ in range(2000):
        for r in R:
            base.posterior(obs_of(base, r))
    print("posterior per attempt: %.1f µs" % ((time.perf_counter() - t0) / (2000 * len(R)) * 1e6))

    with open(os.path.join(HERE, "grm_bn_results.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
