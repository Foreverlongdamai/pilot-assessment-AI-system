"""场景二（悬停）三个科目的证据提取与试算 —— 定稿版（2026-11-18，按 D-015～D-021）。

设计文档：pilot_assessment_system/docs/product/plans/2026-11-18-evidence-scn2.md
复现：在 scn2/ 目录运行  python run_all.py   （依次：录像测量 → 目标估算 → 本脚本 → 插图）
本脚本单独运行：python scn2_evidence.py > scn2_output.txt
输出：scn2_output.txt（文档全部数字，节号与文档对应）、rows_dec1.json / rows_dec10.json（逐趟、逐次结果，供插图脚本使用）。

数据：data/Mai_task3_hover，17 份 CSV（8 份完整经过 phase 0→9；9 份在 phase 3 中途结束）。
坐标：高度 h = -Ze，向上速度 vz = -V_ez。航向约定：机头单位向量 (sin ψ, cos ψ)，右侧单位向量 (cos ψ, −sin ψ)。
目标：target/target.json（由 target/target_estimate.py 从场景几何与录像对准关系估算）。
"""
import collections
import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bn_optimization_2026-11-12"))
from load import KT, first_sustained, runs, task3_all, wrap180  # noqa: E402

FT = 0.3048
P = dict(
    # ADS-33E-PRF Cargo/Utility、良好视觉条件一栏（本项目适配；D-021）
    POS_D=3 * FT, POS_A=6 * FT,          # §3.11.1 / §3.11.6 位置 ±3 ft / ±6 ft；“停止区” = ±6 ft
    HV_ALT_A=4 * FT,                     # §3.11.1 悬停高度可接受 ±4 ft（定点悬停通过与否）
    VM_ALT_D=3 * FT, VM_ALT_A=6 * FT,    # §3.11.6 起止高度 ±3 ft / ±6 ft
    HDG_A=10.0,                          # 航向可接受 ±10°
    T_CAP_D=5.0, T_CAP_A=8.0,            # §3.11.1 减速开始后建立稳定悬停 5 s / 8 s
    V_ENTRY=6 * KT,                      # §3.11.1 进入速度下限 6 kt：减速开始 = 初次停住前最后一帧地速 ≥ 6 kt
    XT_D=10 * FT, XT_A=20 * FT,          # D-017：§3.11.11 / §3.11.7 横向 ±10 ft / ±20 ft
    BRIEF=1.0, FRAC_D=0.90,              # D-015 / D-016
    # D-010 / D-012 常数（场景一已确认）
    STOP_V=0.5, STOP_T=0.5, REST_V=0.2, MOVE_V=0.5, MOVE_T=0.5,
    DB=5.0, MIN_IN=0.05, WIN=2.0, HOLD=1.0, DX_MIN=0.05, MOVING=0.2,
    # 末端修正三档（D-020）
    N_MV_U=6, N_MV_D=2,
    GO_V=1.0, GO_T=1.0,                  # 起飞：地速首次持续 1 s 超过 1 m/s（只用于跳过起点悬停）
)
WORSE = {"D": 0, "A": 1, "U": 2}
NAME = {"D": "期望", "A": "可接受", "U": "不可接受", None: "不适用"}


def load_target():
    with open(os.path.join(HERE, "target", "target.json"), encoding="utf-8") as fh:
        return json.load(fh)["target"]


def worst(*gs):
    gs = [g for g in gs if g is not None]
    return max(gs, key=WORSE.get) if gs else None


def g3(x, d, a):
    return "D" if x <= d + 1e-12 else ("A" if x <= a + 1e-12 else "U")


def dec_df(df, dec):
    return df.iloc[::dec].reset_index(drop=True)


def dt_of(t):
    return float(np.median(np.diff(t)))


def process_grade(beyond_d, beyond_a, dt):
    """过程型证据判档（D-015，第 2 条按 D-016 修改），按顺序：
    1 连续超出可接受边界 > 1 s → 不可接受；2 超出过可接受边界（每次 ≤ 1 s）→ 可接受；
    3 某一次超出期望边界 > 1 s，或期望边界内时间 < 90% → 可接受；4 其余 → 期望。
    持续时间 = 连续帧数 × 步长（与采样率一致）。"""
    ra = [(a, b, (b - a + 1) * dt) for a, b in runs(beyond_a)]
    rd = [(a, b, (b - a + 1) * dt) for a, b in runs(beyond_d)]
    long_a = max([r[2] for r in ra], default=0.0)
    long_d = max([r[2] for r in rd], default=0.0)
    frac_in_d = 1.0 - float(np.mean(beyond_d))
    if long_a > P["BRIEF"]:
        g, rule = "U", 1
    elif ra:
        g, rule = "A", 2
    elif long_d > P["BRIEF"] or frac_in_d < P["FRAC_D"]:
        g, rule = "A", 3
    else:
        g, rule = "D", 4
    return g, dict(long_a=long_a, long_d=long_d, frac_in_d=frac_in_d, n_d=len(rd), n_a=len(ra), rule=rule,
                   seg_d=[(int(a), int(b)) for a, b, _ in rd], seg_a=[(int(a), int(b)) for a, b, _ in ra])


def moves(speed, pos):
    """一次挪动：速度 > 0.2 m/s（D-010“飞机在动”）的连续片段，且片段内位移 ≥ 0.05 m（D-010 位移门槛）。"""
    out = []
    for a, b in runs(speed > P["MOVING"]):
        vec = pos[b] - pos[a]
        disp = float(np.linalg.norm(vec))
        if disp >= P["DX_MIN"]:
            out.append((int(a), int(b), disp, vec))
    return out


def move_reversals(mv):
    """按飞机运动计的反复修正：后一次挪动沿前一次挪动方向退回 ≥ 0.05 m，计一次（D-020）。"""
    n = 0
    for i in range(len(mv) - 1):
        u = mv[i][3] / mv[i][2]
        if float(np.dot(mv[i + 1][3], u)) <= -P["DX_MIN"]:
            n += 1
    return n


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same") if n > 1 else x


def initial_rest(t, sp, start):
    """初次停住点（D-010 2.9、D-012）：从 start 起，速度首次 ≤0.5 m/s 并持续 ≥0.5 s 之后第一帧 ≤0.2 m/s；
    若再移动（>0.5 m/s 持续 ≥0.5 s）前始终未降到 0.2 m/s，取再移动前速度最低的一帧。"""
    k = first_sustained(t[start:], sp[start:] <= P["STOP_V"], P["STOP_T"])
    if k is None:
        return None
    s = start + k
    mv = [(a, b) for a, b in runs(sp[s:] > P["MOVE_V"]) if t[b + s] - t[a + s] >= P["MOVE_T"] - 1e-9]
    seg = sp[s:(s + mv[0][0]) if mv else len(sp)]
    below = np.where(seg <= P["REST_V"])[0]
    return s + int(below[0] if len(below) else np.argmin(seg))


def final_settle(sp):
    """最终稳定：最后一段持续到窗口末尾的 速度 ≤ 0.2 m/s 片段的起点；末帧仍 > 0.2 m/s 返回 None。"""
    if sp[-1] > P["MOVING"]:
        return None
    mv = np.where(sp > P["MOVING"])[0]
    return 0 if len(mv) == 0 else int(mv[-1] + 1)


def stick_events(u_list, v_list, gains, dt, t0):
    """杆输入分类（D-010 2.9，与场景一相同）：杆量 |u| > 5 持续 ≥ 0.05 s 为一次输入；响应观察窗为输入结束后 2 s（遇下一次输入截止）。
    无效修正：保持 < 1 s 且引起位移 < 0.05 m。按杆输入计的反复修正：输入开始时飞机以 > 0.2 m/s 反向运动，观察窗结束时已沿输入方向运动。"""
    n_ineff = n_rev = n_in = 0
    ev = []
    nsm = max(1, int(round(0.1 / dt)))
    for ax, (u, v0, gain) in enumerate(zip(u_list, v_list, gains)):
        v = smooth(v0.astype(float), nsm)
        pos = np.cumsum(v) * dt
        ins = [(a, b) for a, b in runs(np.abs(u) > P["DB"]) if (b - a + 1) * dt >= P["MIN_IN"] - 1e-9]
        for i, (a, b) in enumerate(ins):
            n_in += 1
            d = gain * np.sign(u[a])
            end = min(b + int(P["WIN"] / dt), len(v) - 1)
            if i + 1 < len(ins):
                end = min(end, max(ins[i + 1][0] - 1, b))
            tt = np.arange(end - a + 1) * dt
            dx = float(np.max(d * (pos[a:end + 1] - pos[a] - v[a] * tt)))
            kind = "细调或驱动"
            if (b - a + 1) * dt < P["HOLD"] and dx < P["DX_MIN"]:
                n_ineff += 1
                kind = "无效修正"
            elif np.sign(v[a]) == -d and abs(v[a]) > P["MOVING"] and d * v[end] > P["MOVING"]:
                n_rev += 1
                kind = "反复修正"
            elif np.sign(v[a]) == -d and abs(v[a]) > P["MOVING"]:
                kind = "刹车"
            ev.append((ax, round(t0 + a * dt, 2), round((b - a + 1) * dt, 2), round(dx, 3), kind))
    return n_ineff, n_rev, n_in, ev


def correction_grade(n_mv, n_rev, n_ineff, final_out):
    """末端修正三档（D-020）：最终位置在停止区外，或挪动 ≥ 6 次 → 不可接受；挪动 ≤ 2 次且无无效修正、无反复修正 → 期望；其余 → 可接受。"""
    if final_out or n_mv >= P["N_MV_U"]:
        return "U"
    if n_mv <= P["N_MV_D"] and n_rev == 0 and n_ineff == 0:
        return "D"
    return "A"


def reversals(u, hyst):
    """杆量反向次数（带滞环），只作报告。"""
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


def spawn(df):
    p0 = df[df["Phase ID"] == 0]
    return float(-p0["Ze m"].iloc[0]), float(p0["psi deg"].iloc[0]), float(p0["Xe m"].iloc[0]), float(p0["Ye m"].iloc[0])


def body_err(x, y, psi_deg, xt, yt):
    """水平误差分解为机体纵向（机头方向为正）与横向（右为正），对应 ADS-33 的 'longitudinal and lateral position'。"""
    a = np.radians(psi_deg)
    dx, dy = x - xt, y - yt
    return dx * np.sin(a) + dy * np.cos(a), dx * np.cos(a) - dy * np.sin(a)


def check_heading_convention(data):
    eb = ey = 0.0
    for _, df in data:
        p = df[(df["Phase ID"] == 1)]
        vh = np.hypot(p["V_ex m/s"], p["V_ey m/s"]).values
        m = vh > 2.0
        a = np.radians(p["psi deg"].values[m])
        vx, vy = p["V_ex m/s"].values[m], p["V_ey m/s"].values[m]
        eb = max(eb, float(np.abs(vx * np.sin(a) + vy * np.cos(a) - p["V_bx m/s"].values[m]).max()))
        ey = max(ey, float(np.abs(vx * np.cos(a) - vy * np.sin(a) - p["V_by m/s"].values[m]).max()))
    return eb, ey


def pos_box(lon, lat):
    m = max(abs(lon), abs(lat))
    return g3(m, P["POS_D"], P["POS_A"]), m


# ----------------------------------------------------------------------------------------------
# 科目三 45°斜向移位与到点悬停（phase 1 + phase 2；D-025 更名，原名低速移位与到点悬停）
# ----------------------------------------------------------------------------------------------
def subject3(df, target, dec=1, keep_series=False):
    xt_, yt_ = target
    h_l0, psi0, x0, y0 = spawn(df)
    d = dec_df(df[df["Phase ID"].isin([1, 2])], dec)
    t = d["Simulation time"].values
    dt = dt_of(t)
    ph = d["Phase ID"].values
    x, y = d["Xe m"].values, d["Ye m"].values
    vh = np.hypot(d["V_ex m/s"].values, d["V_ey m/s"].values)
    psi = d["psi deg"].values
    r = dict(T1=float(t[ph == 1][-1] - t[0] + dt), vmax=float(vh.max()), vmax_kt=float(vh.max() / KT))
    go = first_sustained(t, vh > P["GO_V"], P["GO_T"])
    s1 = initial_rest(t, vh, go)
    k6 = np.where(vh[:s1] >= P["V_ENTRY"])[0]
    k6 = int(k6[-1]) if len(k6) else go
    tf = final_settle(vh)
    r.update(t_go=float(t[go] - t[0]), t_dec=float(t[k6] - t[0]), t_s1=float(t[s1] - t[0]), s1_in_phase=int(ph[s1]),
             v_dec_kt=float(vh[k6] / KT), t_stab=None if tf is None else float(t[tf] - t[0]), stab_phase=None if tf is None else int(ph[tf]))
    # 移位航迹（过程型）：起点 → 目标连线的横向偏差，窗口 = phase 1 首帧到减速开始
    L = np.hypot(xt_ - x0, yt_ - y0)
    ux, uy = (xt_ - x0) / L, (yt_ - y0) / L
    xt = (x - x0) * uy - (y - y0) * ux   # 右为正
    w = slice(0, k6 + 1)
    axt = np.abs(xt[w])
    g, st = process_grade(axt > P["XT_D"], axt > P["XT_A"], dt)
    r.update(track=g, xt_max=float(axt.max()), **{"track_" + k: v for k, v in st.items() if k not in ("seg_d", "seg_a")})
    r["rev_lon_tr"] = reversals(d["Pilot Lon"].values[w].astype(float), 10.0)
    r["rev_lat_tr"] = reversals(d["Pilot Lat"].values[w].astype(float), 10.0)
    # 斜向几何（只报告）：移位窗口内地速 > 2 m/s 的帧上，地速方向相对机头的夹角（机体速度 V_by、V_bx，右为正）；
    # 起点 → 初次停住点的方向相对起点机头；纵、横两杆同时 |杆量| > 5 的时间比例
    fast = np.zeros(len(t), bool)
    fast[go:k6 + 1] = vh[go:k6 + 1] > 2.0
    ang = np.degrees(np.arctan2(d["V_by m/s"].values[fast], d["V_bx m/s"].values[fast]))
    a0 = np.radians(psi0)
    dxs, dys = x[s1] - x0, y[s1] - y0
    r.update(trk_med=float(np.median(ang)), trk_p5=float(np.percentile(ang, 5)), trk_p95=float(np.percentile(ang, 95)),
             disp_ang=float(np.degrees(np.arctan2(dxs * np.cos(a0) - dys * np.sin(a0), dxs * np.sin(a0) + dys * np.cos(a0)))))
    lon_on = np.abs(d["Pilot Lon"].values[go:k6 + 1]) > P["DB"]
    lat_on = np.abs(d["Pilot Lat"].values[go:k6 + 1]) > P["DB"]
    r.update(both_frac=float(np.mean(lon_on & lat_on)), any_frac=float(np.mean(lon_on | lat_on)),
             lon_only=float(np.mean(lon_on & ~lat_on)), lat_only=float(np.mean(lat_on & ~lon_on)))
    # 一次到位（结果型）：减速开始 → 初次停住 的用时；初次停住点位置误差
    r["t_cap"] = float(t[s1] - t[k6])
    g_t = g3(r["t_cap"], P["T_CAP_D"], P["T_CAP_A"])
    lon1, lat1 = body_err(x[s1], y[s1], psi[s1], xt_, yt_)
    g_p, m1 = pos_box(lon1, lat1)
    r.update(lon1=float(lon1), lat1=float(lat1), m1=m1, d1=float(np.hypot(lon1, lat1)), once_pos=g_p, once_time=g_t, once=worst(g_t, g_p))
    r["along1"] = float(((x[s1] - xt_) * ux + (y[s1] - yt_) * uy))   # >0 越过，<0 停短
    # 到点修正（条件型）：初次停住后到 phase 2 末
    seg = slice(s1, len(t))
    mv = moves(vh[seg], np.c_[x[seg], y[seg]])
    n_ineff, n_rev_st, n_in, ev = stick_events([d["Pilot Lon"].values[seg].astype(float), d["Pilot Lat"].values[seg].astype(float)],
                                               [d["V_bx m/s"].values[seg], d["V_by m/s"].values[seg]], [-1, +1], dt, float(t[s1] - t[0]))
    n_mvrev = move_reversals(mv)
    fin = len(t) - 1
    lonE, latE = body_err(x[fin], y[fin], psi[fin], xt_, yt_)
    pos_end, mE = pos_box(lonE, latE)
    applicable = len(mv) > 0 or g_p == "U"
    r.update(n_mv=len(mv), mv=[(round(float(t[s1 + a] - t[0]), 2), round(float((b - a + 1) * dt), 2), round(dd, 2)) for a, b, dd, _ in mv],
             n_ineff=n_ineff, n_rev_stick=n_rev_st, n_mvrev=n_mvrev, n_rev=max(n_rev_st, n_mvrev), n_in=n_in, stick_ev=ev,
             t_corr=None if tf is None else float(t[tf] - t[s1]), t_total=None if tf is None else float(t[tf] - t[k6]),
             lonE=float(lonE), latE=float(latE), mE=mE, dE=float(np.hypot(lonE, latE)), pos_end=pos_end,
             corr_applicable=applicable,
             corr=correction_grade(len(mv), max(n_rev_st, n_mvrev), n_ineff, pos_end == "U") if applicable else None)
    # 通过与否（任务结果）：phase 2 末仍在移动、最终位置在停止区外、高度或航向越出可接受值
    hdg_end = abs(float(wrap180(psi[fin] - psi0)))
    h_err_end = float(-d["Ze m"].values[fin] - h_l0)
    why = []
    if vh[fin] > P["STOP_V"]:
        why.append("phase 2 结束时仍在移动")
    if pos_end == "U":
        why.append("最终位置在停止区外")
    if hdg_end > P["HDG_A"]:
        why.append("航向偏离超过 10°")
    if abs(h_err_end) > P["HV_ALT_A"]:
        why.append("高度偏离超过 ±4 ft")
    r.update(pass3="不通过" if why else "通过", pass3_why=why, hdg_end=hdg_end, h_err_end=h_err_end, v_end=float(vh[fin]))
    if keep_series:
        r["series"] = dict(t=(t - t[0]).tolist(), xt=xt.tolist(), vh=vh.tolist(), x=x.tolist(), y=y.tolist(), psi=psi.tolist(),
                           lon=d["Pilot Lon"].values.astype(float).tolist(), lat=d["Pilot Lat"].values.astype(float).tolist(),
                           k6=int(k6), s1=int(s1), tf=None if tf is None else int(tf), seg_d=st["seg_d"], seg_a=st["seg_a"],
                           mv=[(a + s1, b + s1) for a, b, _, _ in mv], x0=x0, y0=y0)
    return r


# ----------------------------------------------------------------------------------------------
# 科目四 定点悬停（phase 2、4、6、8）：只判通过与否（D-021）
# ----------------------------------------------------------------------------------------------
def subject4(df, target, h_l, h_u, dec=1, keep_series=False):
    _, psi0, _, _ = spawn(df)
    out = []
    for ph in (2, 4, 6, 8):
        d = dec_df(df[df["Phase ID"] == ph], dec)
        if len(d) == 0:
            continue
        t = d["Simulation time"].values
        dt = dt_of(t)
        vh = np.hypot(d["V_ex m/s"].values, d["V_ey m/s"].values)
        start = 0
        if ph == 2:   # phase 2 中仍在调整位置的，保持窗口从最终稳定开始，之前的挪动归到点修正
            k = final_settle(vh)
            start = k if k is not None else len(t) - 1
        w = slice(start, len(t))
        x, y, h, psi = d["Xe m"].values[w], d["Ye m"].values[w], -d["Ze m"].values[w], d["psi deg"].values[w]
        lon, lat = body_err(x, y, psi, *target)
        hstar = h_l if ph in (2, 6) else h_u
        pos_e = np.maximum(np.abs(lon), np.abs(lat))
        h_e = h - hstar
        hdg_e = wrap180(psi - psi0)
        sticks = float(np.mean((np.abs(d[["Pilot Lon", "Pilot Lat", "Pilot Heave", "Pilot Yaw"]].values[w]) > P["DB"]).any(axis=1)))
        why = []
        if pos_e.max() > P["POS_A"]:
            why.append("位置偏离超过 ±6 ft")
        if np.abs(h_e).max() > P["HV_ALT_A"]:
            why.append("高度偏离超过 ±4 ft")
        if np.abs(hdg_e).max() > P["HDG_A"]:
            why.append("航向偏离超过 10°")
        q = dict(phase=ph, dur=float((len(t) - start) * dt), hold_start=float(t[start] - t[0]), pos_max=float(pos_e.max()),
                 h_max=float(np.abs(h_e).max()), h_mean=float(np.mean(h_e)), hdg_max=float(np.abs(hdg_e).max()),
                 drift_h=float(np.hypot(x[-1] - x[0], y[-1] - y[0])), drift_v=float(abs(h[-1] - h[0])), stick_frac=sticks,
                 pass4="不通过" if why else "通过", why=why)
        if keep_series:
            q["series"] = dict(t=(t[w] - t[start]).tolist(), lon=lon.tolist(), lat=lat.tolist(), h=h_e.tolist(), hdg=hdg_e.tolist())
        out.append(q)
    return out


# ----------------------------------------------------------------------------------------------
# 科目五 垂直升降与悬停建立（phase 3、5、7）
# ----------------------------------------------------------------------------------------------
def subject5(df, h_l, h_u, dec=1, keep_series=False):
    _, psi0, _, _ = spawn(df)
    out = []
    for ph in (3, 5, 7):
        if ph + 1 not in set(df["Phase ID"]):
            out.append(dict(phase=ph, complete=False))
            continue
        d = dec_df(df[df["Phase ID"].isin([ph, ph + 1])], dec)
        t = d["Simulation time"].values
        dt = dt_of(t)
        pid = d["Phase ID"].values
        h, vz, u = -d["Ze m"].values, -d["V_ez m/s"].values, d["Pilot Heave"].values.astype(float)
        sg = 1 if ph in (3, 7) else -1
        hstar = h_u if sg > 0 else h_l
        h0 = float(h[0])
        r = dict(phase=ph, complete=True, sg=sg, h0=h0, hstar=hstar)
        i_in = int(np.where(np.abs(u) > P["DB"])[0][0])
        go = first_sustained(t, sg * vz >= P["STOP_V"], P["STOP_T"])
        av = np.abs(vz)
        s1 = initial_rest(t, av, go)
        tf = final_settle(av)
        pre_in = np.where(np.abs(u[:s1 + 1]) > P["DB"])[0]
        r["stop_latency"] = float(t[s1] - t[pre_in[-1]]) if len(pre_in) else None
        r.update(t_in=float(t[i_in] - t[0]), t_go=float(t[go] - t[0]), t_s1=float(t[s1] - t[0]),
                 t_stab=None if tf is None else float(t[tf] - t[0]), s1_phase=int(pid[s1]), vz_max=float(av.max()))
        # 停止高度精度（结果型）
        e1 = float(h[s1] - hstar)
        r.update(stop_err=e1, stop_acc=g3(abs(e1), P["VM_ALT_D"], P["VM_ALT_A"]))
        # 起停控制（操纵型）：起动 = 主运动开始前反方向偏离起始高度的最大值；停止 = 初次停住后的修正（D-020 三档）
        wrong = float(max(0.0, -(sg * (h[:go + 1] - h0)).min()))
        g_start = g3(wrong, P["VM_ALT_D"], P["VM_ALT_A"])
        fin = tf if tf is not None else len(t) - 1
        ext = (h[go:fin + 1].max() if sg > 0 else h[go:fin + 1].min())
        e_end = float(h[fin] - hstar)
        seg = slice(s1, len(t))
        mv = moves(av[seg], h[seg][:, None])
        n_ineff, n_rev_st, n_in, ev = stick_events([u[seg]], [vz[seg]], [+1], dt, float(t[s1] - t[0]))
        n_mvrev = move_reversals(mv)
        n_rev = max(n_rev_st, n_mvrev)
        g_stop = correction_grade(len(mv), n_rev, n_ineff, abs(e_end) > P["VM_ALT_A"])
        r.update(wrong=wrong, g_start=g_start, over=float(max(0.0, sg * (ext - h[fin]))), e_end=e_end, n_mv=len(mv),
                 mv=[(round(float(t[s1 + a] - t[0]), 2), round(float((b - a + 1) * dt), 2), round(dd, 2)) for a, b, dd, _ in mv],
                 n_ineff=n_ineff, n_rev_stick=n_rev_st, n_mvrev=n_mvrev, n_rev=n_rev, stick_ev=ev, g_stop=g_stop,
                 startstop=worst(g_start, g_stop), rev_heave=reversals(u[pid == ph], 10.0))
        # 只在报告中显示：完成时间（首次输入 → 最终稳定）、超出速率上限最短时间的部分
        r["t_total"] = None if tf is None else float(t[tf] - t[i_in])
        r["t_excess"] = None if tf is None else float(r["t_total"] - abs(hstar - h0) / float(av.max()))
        # 通过与否（任务结果）
        hdg = float(np.max(np.abs(wrap180(d["psi deg"].values - psi0))))
        xy = float(np.hypot(d["Xe m"].values - d["Xe m"].values[0], d["Ye m"].values - d["Ye m"].values[0]).max())
        why = []
        if abs(e_end) > P["VM_ALT_A"]:
            why.append("最终高度偏离超过 ±6 ft")
        if av[-1] > P["STOP_V"]:
            why.append("窗口结束时仍在升降")
        if hdg > P["HDG_A"]:
            why.append("航向偏离超过 10°")
        if xy > P["POS_A"]:
            why.append("水平漂移超过 ±6 ft")
        r.update(pass5="不通过" if why else "通过", why=why, hdg_max=hdg, xy_drift=xy,
                 stick_other=float(np.mean((np.abs(d[["Pilot Lon", "Pilot Lat", "Pilot Yaw"]].values[pid == ph]) > P["DB"]).any(axis=1))))
        if keep_series:
            r["series"] = dict(t=(t - t[0]).tolist(), h=h.tolist(), vz=vz.tolist(), u=u.tolist(), ph=pid.tolist(),
                               i_in=i_in, go=int(go), s1=int(s1), tf=None if tf is None else int(tf), mv=[(a + s1, b + s1) for a, b, _, _ in mv])
        out.append(r)
    return out


# ----------------------------------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------------------------------
def cnt(vals):
    c = collections.Counter(v for v in vals if v is not None)
    s = " / ".join(f"{NAME[k]} {c.get(k, 0)}" for k in ("D", "A", "U"))
    n_na = sum(v is None for v in vals)
    return s + (f"（不适用 {n_na}）" if n_na else "")


def pf(vals):
    c = collections.Counter(vals)
    return f"通过 {c.get('通过', 0)} / 不通过 {c.get('不通过', 0)}"


def pct(a, qs=(0, 50, 100)):
    a = np.asarray([v for v in a if v is not None], float)
    return " ".join(("最小" if q == 0 else "最大" if q == 100 else ("中位" if q == 50 else f"p{q}")) + f" {np.percentile(a, q):.2f}" for q in qs)


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 4 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return float("nan")
    return float(spearmanr(a[m], b[m])[0])


def gnum(g):
    return np.nan if g is None else {"D": 2, "A": 1, "U": 0}[g]


def run_all(data, target, h_l, h_u, dec=1):
    r3, r4, r5 = [], [], []
    complete = {n for n, df in data if 9 in set(df["Phase ID"])}
    for n, df in data:
        r = subject3(df, target, dec)
        r.update(name=n, complete=n in complete)
        r3.append(r)
        for q in subject4(df, target, h_l, h_u, dec):
            q.update(name=n)
            r4.append(q)
        for q in subject5(df, h_l, h_u, dec):
            q.update(name=n)
            r5.append(q)
    return r3, r4, r5


def main():
    data = task3_all()
    T = load_target()
    target = (T["X"], T["Y"])
    h_l, h_u = T["h_L"], T["h_U"]
    complete = [n for n, df in data if 9 in set(df["Phase ID"])]
    print("== 0. 数据与目标 ==")
    print(f"记录 {len(data)} 份；完整 0→9：{len(complete)} 份 {complete}")
    sp0 = {n: spawn(df) for n, df in data}
    print("phase 0 首帧（高度, 航向, X, Y）取值：", sorted(set((round(v[0], 3), round(v[1], 2), v[2], v[3]) for v in sp0.values())))
    eb, ey = check_heading_convention(data)
    print(f"航向约定检验（17 趟 phase 1，地速 >2 m/s 帧）：纵向速度差最大 {eb:.3f} m/s；横向速度差最大 {ey:.3f} m/s")
    print(f"目标（target/target.json）：X* {T['X']:.3f}、Y* {T['Y']:.3f}（初始机体坐标 纵 {T['lon']:.2f} ± {T['u_lon']:.2f}、横 {T['lat']:.2f} ± {T['u_lat']:.2f} m）；"
          f"下方目标高度 {h_l:.2f} ± {T['u_hL']:.2f} m；上方目标高度 {h_u:.2f} ± {T['u_hU']:.2f} m；期望航向 {T['psi']:.1f}°")

    print("\n== 1. 飞行员负责什么：各阶段四杆 |u|>5 的时间比例（%），中位/最大 ==")
    for ph in range(0, 10):
        rows = []
        for n, df in data:
            d = df[df["Phase ID"] == ph]
            if len(d):
                rows.append([100 * np.mean(np.abs(d[c].values) > P["DB"]) for c in ("Pilot Lon", "Pilot Lat", "Pilot Heave", "Pilot Yaw")])
        rows = np.array(rows)
        print(f"phase {ph}（{len(rows)} 趟）：纵向杆 {np.median(rows[:,0]):.0f}/{rows[:,0].max():.0f}  横向杆 {np.median(rows[:,1]):.0f}/{rows[:,1].max():.0f}  "
              f"升降杆 {np.median(rows[:,2]):.0f}/{rows[:,2].max():.0f}  航向踏板 {np.median(rows[:,3]):.0f}/{rows[:,3].max():.0f}")
    dh1 = max(float((-df[df["Phase ID"] == 1]["Ze m"]).max() - (-df[df["Phase ID"] == 1]["Ze m"]).min()) for _, df in data)
    psi1 = [float(df[df["Phase ID"] == 1]["psi deg"].iloc[-1]) for _, df in data]
    z2 = [n for n, df in data if not (np.abs(df[df["Phase ID"] == 2][["Pilot Lon", "Pilot Lat", "Pilot Heave", "Pilot Yaw"]].values) > 0).any()]
    hv = {ph: [100 * np.mean(np.abs(df[df["Phase ID"] == ph]["Pilot Heave"].values) > P["DB"]) for n, df in data if n in complete] for ph in (3, 5, 7)}
    print("完整 8 趟升降杆活动比例中位（%）：", {ph: round(float(np.median(v)), 0) for ph, v in hv.items()}, "最大", {ph: round(float(np.max(v)), 0) for ph, v in hv.items()})
    print(f"phase 1 高度变化最大 {dh1:.3f} m；phase 1 末航向 {min(psi1):.1f}～{max(psi1):.1f}°；phase 2 四杆全为 0 的 {len(z2)} 趟")

    res = {}
    for dec in (1, 10):
        res[dec] = run_all(data, target, h_l, h_u, dec)
        r3, r4, r5 = res[dec]
        with open(os.path.join(HERE, f"rows_dec{dec}.json"), "w", encoding="utf-8") as fh:
            json.dump(dict(subject3=r3, subject4=r4, subject5=r5, target=T, params=P), fh, ensure_ascii=False, indent=1, default=float)
    r3, r4, r5 = res[1]
    r5c = [r for r in r5 if r["complete"]]

    # ---------------- 科目三 ----------------
    print("\n== 3. 科目三 45°斜向移位与到点悬停（17 趟；括号内为完整 8 趟）==")
    print("逐趟：名称 | phase1 时长 最大地速(kt) 减速开始地速(kt) | 横向偏差峰值 最长超可接受 最长超期望 期望内比例 → 移位航迹 | "
          "减速用时 初停纵 初停横 → 一次到位 | 挪动 反复(杆/飞机) 无效 最终纵 最终横 → 到点修正 | 通过与否")
    for r in r3:
        print(f"{r['name']:<18} | {r['T1']:5.1f} {r['vmax_kt']:5.1f} {r['v_dec_kt']:4.1f} | {r['xt_max']:5.2f} {r['track_long_a']:5.2f} {r['track_long_d']:5.2f} "
              f"{r['track_frac_in_d']:6.1%} → {NAME[r['track']]} | {r['t_cap']:4.2f} {r['lon1']:+6.2f} {r['lat1']:+6.2f} → {NAME[r['once']]} | "
              f"{r['n_mv']} {r['n_rev_stick']}/{r['n_mvrev']} {r['n_ineff']} {r['lonE']:+5.2f} {r['latE']:+5.2f} → {NAME[r['corr']]} | {r['pass3']} {'、'.join(r['pass3_why'])}")
    for lab, sub in (("17 趟", r3), ("完整 8 趟", [r for r in r3 if r["complete"]]), ("中途结束 9 趟", [r for r in r3 if not r["complete"]])):
        print(f"[{lab}] 移位航迹 {cnt([r['track'] for r in sub])}；判档所用规则序号 {dict(collections.Counter(r['track_rule'] for r in sub))}")
        print(f"[{lab}] 一次到位 {cnt([r['once'] for r in sub])}（用时 {cnt([r['once_time'] for r in sub])}；位置 {cnt([r['once_pos'] for r in sub])}）")
        print(f"[{lab}] 到点修正 {cnt([r['corr'] for r in sub])}")
        print(f"[{lab}] 通过与否 {pf([r['pass3'] for r in sub])}")
    print("斜向几何（移位窗口：起飞 → 减速开始；只报告）：")
    for r in r3:
        print(f"   {r['name']:<18} 地速方向相对机头（右为正）中位 {r['trk_med']:5.1f}°（5%～95% {r['trk_p5']:5.1f}～{r['trk_p95']:5.1f}°）；"
              f"起点→初次停住点方向 {r['disp_ang']:5.1f}°；两杆同时有输入 {r['both_frac']:5.1%}，只有纵向杆 {r['lon_only']:5.1%}，只有横向杆 {r['lat_only']:5.1%}")
    print("   17 趟：地速方向中位", pct([r["trk_med"] for r in r3]), "° | 各趟 5% 分位最小", round(min(r["trk_p5"] for r in r3), 1),
          "、95% 分位最大", round(max(r["trk_p95"] for r in r3), 1), "° | 起点→初次停住点方向", pct([r["disp_ang"] for r in r3]),
          "° | 两杆同时有输入", pct([100 * r["both_frac"] for r in r3]), "% | 至少一杆有输入", pct([100 * r["any_frac"] for r in r3]), "% | 只用一杆的时间每趟最大",
          round(100 * max(r["lon_only"] + r["lat_only"] for r in r3), 1), "%")
    print("移位航迹维度：横向偏差峰值", pct([r["xt_max"] for r in r3]), "| 最长超可接受", pct([r["track_long_a"] for r in r3]),
          "| 最长超期望", pct([r["track_long_d"] for r in r3]), "| 期望内比例", pct([r["track_frac_in_d"] for r in r3]))
    print("一次到位：减速用时 s", pct([r["t_cap"] for r in r3]), "| 初停两轴较大误差 m", pct([r["m1"] for r in r3]),
          "| 初停沿航线分量（>0 越过）", [(r["name"], round(r["along1"], 2)) for r in r3])
    print("到点修正：适用", sum(r["corr_applicable"] for r in r3), "趟；挪动次数分布（适用者）",
          dict(sorted(collections.Counter(r["n_mv"] for r in r3 if r["corr_applicable"]).items())),
          "；完整 8 趟", sorted(r["n_mv"] for r in r3 if r["complete"]))
    print("  反复修正 杆/飞机/采用：", [(r["name"], r["n_rev_stick"], r["n_mvrev"], r["n_rev"]) for r in r3 if r["n_mv"] > 0])
    print("  无效修正：", [(r["name"], r["n_ineff"]) for r in r3 if r["n_ineff"] > 0])
    print("  到点修正判不可接受的原因：", [(r["name"], "最终位置在停止区外" if r["pos_end"] == "U" else f"挪动 {r['n_mv']} 次") for r in r3 if r["corr"] == "U"])
    print("只在报告中显示：最大地速 kt", pct([r["vmax_kt"] for r in r3]), "| 完整 8 趟", pct([r["vmax_kt"] for r in r3 if r["complete"]]),
          "| 中途结束 9 趟", pct([r["vmax_kt"] for r in r3 if not r["complete"]]),
          "| >15 kt（超出 ADS-33 §6.2.15.2 悬停速度范围）：", [r["name"] for r in r3 if r["vmax_kt"] > 15])
    print("只在报告中显示：减速开始→最终稳定 用时 s", pct([r["t_total"] for r in r3]), "| 初停→最终稳定 s", pct([r["t_corr"] for r in r3]))
    print("最终位置两轴较大误差 m：完整 8 趟", pct([r["mE"] for r in r3 if r["complete"]]), "| 中途结束 9 趟", pct([r["mE"] for r in r3 if not r["complete"]]))

    print("\n末端修正门槛检查（挪动 6 次、2 次是否落在数据密集处）：")
    nm = [r["n_mv"] for r in r3 if r["corr_applicable"]]
    print("  挪动次数（适用 {} 趟）：".format(len(nm)), dict(sorted(collections.Counter(nm).items())))
    def cg(rr):
        return cnt([correction_grade(r["n_mv"], r["n_rev"], r["n_ineff"], r["pos_end"] == "U") if r["corr_applicable"] else None for r in rr])
    for key, vals, lab in (("N_MV_U", (4, 5, 6, 7, 8, 9), "不可接受门槛（挪动 ≥ N 次）"), ("N_MV_D", (1, 2, 3), "期望门槛（挪动 ≤ N 次）")):
        for thr in vals:
            P0 = dict(P)
            P[key] = thr
            print(f"  {lab} N = {thr}：全部 {cg(r3)}；完整 8 趟 {cg([r for r in r3 if r['complete']])}")
            P.update(P0)
    # 挪动定义改用场景一的 0.5 m/s 门槛时的挪动次数（对照）
    alt = []
    for n, df in data:
        d = df[df["Phase ID"].isin([1, 2])]
        vh = np.hypot(d["V_ex m/s"].values, d["V_ey m/s"].values)
        r = next(q for q in r3 if q["name"] == n)
        s1 = int(np.searchsorted(d["Simulation time"].values - d["Simulation time"].values[0], r["t_s1"] - 1e-9))
        P0 = dict(P)
        P["MOVING"] = 0.5
        alt.append((n, len(moves(vh[s1:], np.c_[d["Xe m"].values[s1:], d["Ye m"].values[s1:]]))))
        P.update(P0)
    print("  对照：挪动速度门槛取场景一的 0.5 m/s 时的挪动次数：", alt, "；完整 8 趟", sorted(c for n, c in alt if n in complete))
    pk = []
    for n, df in data:
        r = next(q for q in r3 if q["name"] == n)
        d = df[df["Phase ID"].isin([1, 2])]
        tt = d["Simulation time"].values - d["Simulation time"].values[0]
        vh = np.hypot(d["V_ex m/s"].values, d["V_ey m/s"].values)
        for (t0, dur, disp) in r["mv"]:
            m = (tt >= t0 - 1e-6) & (tt <= t0 + dur + 1e-6)
            pk.append((float(vh[m].max()), disp))
    low = [p for p in pk if p[0] < 0.5]
    print(f"  初停后挪动共 {len(pk)} 次，其中峰值地速 <0.5 m/s 的 {len(low)} 次，位移 {min(p[1] for p in low):.2f}～{max(p[1] for p in low):.2f} m（按 0.5 m/s 计会漏掉）")

    print("\n科目三秩相关（Spearman，17 趟）")
    num = dict(横偏峰值=[r["xt_max"] for r in r3], 初停误差=[r["m1"] for r in r3], 减速用时=[r["t_cap"] for r in r3],
               挪动=[r["n_mv"] for r in r3], 反复=[r["n_rev"] for r in r3], 无效=[r["n_ineff"] for r in r3],
               总用时=[r["t_total"] for r in r3], 最终误差=[r["mE"] for r in r3], 最大地速=[r["vmax"] for r in r3],
               移位航迹=[gnum(r["track"]) for r in r3], 一次到位=[gnum(r["once"]) for r in r3], 到点修正=[gnum(r["corr"]) if r["corr"] else 2 for r in r3])
    keys = list(num)
    print("        " + " ".join(f"{k:>6}" for k in keys))
    for a in keys:
        print(f"{a:>6}" + " ".join(f"{sp(num[a], num[b]):8.2f}" for b in keys))

    print("\n科目三敏感性")
    def s3(tg=target):
        rr = [dict(subject3(df, tg), name=n) for n, df in data]
        return f"移位航迹 {cnt([r['track'] for r in rr])}；一次到位 {cnt([r['once'] for r in rr])}；到点修正 {cnt([r['corr'] for r in rr])}；{pf([r['pass3'] for r in rr])}", rr
    base_s, base_rr = s3()
    print(" 基准：", base_s)
    a0 = np.radians(T["psi"])
    changed = set()
    for dlo in (-T["u_lon"], 0.0, T["u_lon"]):
        for dla in (-T["u_lat"], 0.0, T["u_lat"]):
            if dlo == 0 and dla == 0:
                continue
            lo, la = T["lon"] + dlo, T["lat"] + dla
            tg = (lo * np.sin(a0) + la * np.cos(a0), lo * np.cos(a0) - la * np.sin(a0))
            s, rr = s3(tg)
            for a, b in zip(base_rr, rr):
                if (a["track"], a["once"], a["corr"], a["pass3"]) != (b["track"], b["once"], b["corr"], b["pass3"]):
                    changed.add(a["name"])
            print(f" 目标 纵 {dlo:+.2f}、横 {dla:+.2f} m：{s}")
    print(" 目标在不确定度范围内移动时档位或通过与否有变化的记录：",
          [(n, round(next(r for r in r3 if r["name"] == n)["m1"], 2), round(next(r for r in r3 if r["name"] == n)["mE"], 2)) for n in sorted(changed)])
    for lab, tg in (("目标改用参考示范 14_01_54_standard 的 phase 2 平均位置（原方案）", None),):
        df = dict(data)["14_01_54_standard"]
        p2 = df[df["Phase ID"] == 2]
        tg = (float(p2["Xe m"].mean()), float(p2["Ye m"].mean()))
        print(f" {lab} ({tg[0]:.3f}, {tg[1]:.3f})：", s3(tg)[0])
    for f in (0.8, 1.2):
        P0 = dict(P)
        P.update(XT_D=P0["XT_D"] * f, XT_A=P0["XT_A"] * f)
        print(f" 横向边界 ×{f}（{P['XT_D']:.2f} / {P['XT_A']:.2f} m）：移位航迹", cnt([subject3(df, target)["track"] for _, df in data]))
        P.update(P0)
    P0 = dict(P)
    P.update(XT_D=2.0, XT_A=5.0)
    print(" 横向边界取原设计 2 / 5 m（已由 D-017 取代，对照）：移位航迹", cnt([subject3(df, target)["track"] for _, df in data]))
    P.update(P0)
    for b in (0.5, 2.0):
        P0 = dict(P)
        P["BRIEF"] = b
        print(f" “短暂”取 {b} s：移位航迹", cnt([subject3(df, target)["track"] for _, df in data]))
        P.update(P0)
    for fr in (0.8, 0.95):
        P0 = dict(P)
        P["FRAC_D"] = fr
        print(f" 期望内比例门槛 {fr:.0%}：移位航迹", cnt([subject3(df, target)["track"] for _, df in data]))
        P.update(P0)
    for f in (0.8, 1.2):
        P0 = dict(P)
        P.update(POS_D=P0["POS_D"] * f, POS_A=P0["POS_A"] * f, T_CAP_D=P0["T_CAP_D"] * f, T_CAP_A=P0["T_CAP_A"] * f)
        rr = [subject3(df, target) for _, df in data]
        print(f" 位置与用时边界 ×{f}：一次到位 {cnt([r['once'] for r in rr])}；到点修正 {cnt([r['corr'] for r in rr])}；{pf([r['pass3'] for r in rr])}")
        P.update(P0)
    P0 = dict(P)
    P.update(POS_D=2 * FT, POS_A=4 * FT)
    rr = [subject3(df, target) for _, df in data]
    print(f" 位置边界改用美国联邦航空管理局商照 ±2 ft／私照 ±4 ft（对照）：一次到位 {cnt([r['once'] for r in rr])}；到点修正 {cnt([r['corr'] for r in rr])}；{pf([r['pass3'] for r in rr])}")
    P.update(P0)
    P0 = dict(P)
    P["DX_MIN"] = 0.10
    rr = [subject3(df, target) for _, df in data]
    print(f" 挪动位移门槛 0.10 m：到点修正 {cnt([r['corr'] for r in rr])}")
    P.update(P0)

    # ---------------- 科目四 ----------------
    print("\n== 4. 科目四 定点悬停（phase 2：17 次；phase 4、6、8：8 趟 × 3 = 24 次）——只判通过与否 ==")
    for ph in (2, 4, 6, 8):
        sub = [q for q in r4 if q["phase"] == ph]
        print(f"phase {ph}（{len(sub)} 次）：保持时长 {pct([q['dur'] for q in sub])} s | 有杆量比例 最大 {max(q['stick_frac'] for q in sub):.3f} | "
              f"水平漂移 {pct([q['drift_h'] for q in sub])} m | 高度漂移 {pct([q['drift_v'] for q in sub])} m | 位置误差 {pct([q['pos_max'] for q in sub])} m | "
              f"高度误差 {pct([q['h_max'] for q in sub])} m | 航向误差 最大 {max(q['hdg_max'] for q in sub):.2f}° | {pf([q['pass4'] for q in sub])}")
    print("不通过的保持：", [(q["name"], q["phase"], q["why"], round(q["pos_max"], 2)) for q in r4 if q["pass4"] == "不通过"])
    print("phase 2 保持窗口从最终稳定算起的：", [(q["name"], round(q["hold_start"], 1), round(q["dur"], 1)) for q in r4 if q["phase"] == 2 and q["hold_start"] > 0])
    by_run = collections.defaultdict(list)
    for q in r4:
        by_run[q["name"]].append(q["pass4"])
    sub_c = {n: ("通过" if all(v == "通过" for v in vs) else "不通过") for n, vs in by_run.items() if n in complete}
    print(f"科目四（完整 8 趟，四段全部通过才通过）：{pf(list(sub_c.values()))}；中途结束 9 趟只有 phase 2 一段，记为不完整")
    print("保持段位置误差与前一段末位置误差的关系：phase 4、6、8 的位置误差与 phase 2 末（科目三最终位置）误差之差最大",
          f"{max(abs(q['pos_max'] - next(p for p in r4 if p['name'] == q['name'] and p['phase'] == 2)['pos_max']) for q in r4 if q['phase'] in (4, 6, 8)):.3f} m")
    for dh in (-T["u_hU"], T["u_hU"]):
        rr = [q for _, df in data for q in subject4(df, target, h_l, h_u + dh)]
        print(f" 上方目标高度 {dh:+.2f} m：{pf([q['pass4'] for q in rr])}")
    for dh in (-T["u_hL"], T["u_hL"]):
        rr = [q for _, df in data for q in subject4(df, target, h_l + dh, h_u)]
        print(f" 下方目标高度 {dh:+.2f} m：{pf([q['pass4'] for q in rr])}")

    # ---------------- 科目五 ----------------
    print("\n== 5. 科目五 垂直升降与悬停建立（8 趟 × 3 = 24 次；9 趟 phase 3 中断不判）==")
    print("逐次：名称 phase | 首次输入 反向偏离 → 起动 | 初停 误差 → 停止高度精度 | 超调 挪动 反复(杆/飞机) 无效 最终误差 → 停止 | 起停控制 | 完成时间 超出部分 | 通过与否")
    for r in r5c:
        print(f"{r['name']:<18} {r['phase']} | {r['t_in']:4.2f} {r['wrong']:4.2f} → {NAME[r['g_start']]} | {r['t_s1']:5.2f} {r['stop_err']:+5.2f} → {NAME[r['stop_acc']]} | "
              f"{r['over']:4.2f} {r['n_mv']} {r['n_rev_stick']}/{r['n_mvrev']} {r['n_ineff']} {r['e_end']:+5.2f} → {NAME[r['g_stop']]} | {NAME[r['startstop']]} | "
              f"{r['t_total']:5.2f} {r['t_excess']:4.2f} | {r['pass5']}")
    print(f"[24 次] 停止高度精度 {cnt([r['stop_acc'] for r in r5c])} | 起停控制 {cnt([r['startstop'] for r in r5c])}"
          f"（起动 {cnt([r['g_start'] for r in r5c])}；停止 {cnt([r['g_stop'] for r in r5c])}）| {pf([r['pass5'] for r in r5c])}")
    for ph in (3, 5, 7):
        sub = [r for r in r5c if r["phase"] == ph]
        print(f"  phase {ph}：停止高度精度 {cnt([r['stop_acc'] for r in sub])}；起停控制 {cnt([r['startstop'] for r in sub])}；初停误差 {pct([r['stop_err'] for r in sub])} m")
    print("初停误差绝对值", pct([abs(r["stop_err"]) for r in r5c]), "| 最终误差绝对值", pct([abs(r["e_end"]) for r in r5c]), "| 超调", pct([r["over"] for r in r5c]),
          "| 反向偏离", pct([r["wrong"] for r in r5c]), "| 挪动", pct([r["n_mv"] for r in r5c]), "| 最大垂直速度", pct([r["vz_max"] for r in r5c]))
    print("只在报告中显示：完成时间", pct([r["t_total"] for r in r5c]), "s | 超出速率上限最短时间的部分", pct([r["t_excess"] for r in r5c]), "s")
    print("松杆（初次停住前最后一帧 |升降杆| > 5）到初次停住：", pct([r["stop_latency"] for r in r5c]), "s")
    print("升降期间其他三杆有输入比例 最大", max(r["stick_other"] for r in r5c), "| 水平漂移 最大", round(max(r["xy_drift"] for r in r5c), 3), "m | 航向变化 最大", round(max(r["hdg_max"] for r in r5c), 2), "°")
    print("停止部分非期望的：", [(r["name"], r["phase"], NAME[r["g_stop"]], r["n_mv"], r["n_rev"], r["n_ineff"]) for r in r5c if r["g_stop"] != "D"])
    print("\n科目五秩相关（Spearman，24 次）")
    num = dict(初停误差=[abs(r["stop_err"]) for r in r5c], 最终误差=[abs(r["e_end"]) for r in r5c], 超调=[r["over"] for r in r5c], 反向偏离=[r["wrong"] for r in r5c],
               挪动=[r["n_mv"] for r in r5c], 反复=[r["n_rev"] for r in r5c], 杆反向=[r["rev_heave"] for r in r5c], 超出时间=[r["t_excess"] for r in r5c],
               停止精度=[gnum(r["stop_acc"]) for r in r5c], 起停控制=[gnum(r["startstop"]) for r in r5c])
    keys = list(num)
    print("        " + " ".join(f"{k:>6}" for k in keys))
    for a in keys:
        print(f"{a:>6}" + " ".join(f"{sp(num[a], num[b]):8.2f}" for b in keys))
    print("\n科目五敏感性（目标高度取不确定度两端）")
    for lab, hl, hu in (("上方目标 −", h_l, h_u - T["u_hU"]), ("上方目标 +", h_l, h_u + T["u_hU"]),
                        ("下方目标 −", h_l - T["u_hL"], h_u), ("下方目标 +", h_l + T["u_hL"], h_u)):
        rr = [q for _, df in data for q in subject5(df, hl, hu) if q["complete"]]
        print(f" {lab}（下 {hl:.2f}，上 {hu:.2f}）：停止高度精度 {cnt([q['stop_acc'] for q in rr])}；起停控制 {cnt([q['startstop'] for q in rr])}；{pf([q['pass5'] for q in rr])}")
    for lab, hl, hu in (("原方案：下方 = 起点高度、上方 = 起点 + 25 m", 40.92, 65.92),):
        rr = [q for _, df in data for q in subject5(df, hl, hu) if q["complete"]]
        print(f" {lab}：停止高度精度 {cnt([q['stop_acc'] for q in rr])}；起停控制 {cnt([q['startstop'] for q in rr])}")
    for f in (0.8, 1.2):
        P0 = dict(P)
        P.update(VM_ALT_D=P0["VM_ALT_D"] * f, VM_ALT_A=P0["VM_ALT_A"] * f)
        rr = [q for _, df in data for q in subject5(df, h_l, h_u) if q["complete"]]
        print(f" 高度边界 ×{f}：停止高度精度 {cnt([q['stop_acc'] for q in rr])}；起停控制 {cnt([q['startstop'] for q in rr])}")
        P.update(P0)
    P0 = dict(P)
    P["DX_MIN"] = 0.10
    rr = [q for _, df in data for q in subject5(df, h_l, h_u) if q["complete"]]
    print(f" 挪动位移门槛 0.10 m：起停控制 {cnt([q['startstop'] for q in rr])}")
    P.update(P0)

    # ---------------- 10 Hz ----------------
    print("\n== 6. 每秒 10 帧复算（每 10 帧取 1 帧）==")
    a3, a4, a5 = res[1]
    b3, b4, b5 = res[10]
    for k, lab in (("track", "移位航迹"), ("once", "一次到位"), ("corr", "到点修正"), ("pass3", "科目三通过与否")):
        diff = [(x["name"], x[k], y[k]) for x, y in zip(a3, b3) if x[k] != y[k]]
        print(f" 科目三 {lab}：档位变化 {len(diff)} 趟 {diff}")
    for k, lab in (("n_mv", "挪动"), ("n_rev", "反复修正"), ("n_ineff", "无效修正")):
        diff = [(x["name"], x[k], y[k]) for x, y in zip(a3, b3) if x[k] != y[k]]
        print(f"   科目三 {lab}次数变化 {len(diff)} 趟 {diff}")
    print(f"   减速用时最大差 {max(abs(x['t_cap'] - y['t_cap']) for x, y in zip(a3, b3)):.2f} s；初停误差最大差 {max(abs(x['m1'] - y['m1']) for x, y in zip(a3, b3)):.3f} m；"
          f"横向偏差峰值最大差 {max(abs(x['xt_max'] - y['xt_max']) for x, y in zip(a3, b3)):.3f} m")
    diff = [(x["name"], x["phase"], x["pass4"], y["pass4"]) for x, y in zip(a4, b4) if x["pass4"] != y["pass4"]]
    print(f" 科目四 通过与否：变化 {len(diff)} 次 {diff}")
    a5c, b5c = [r for r in a5 if r["complete"]], [r for r in b5 if r["complete"]]
    for k, lab in (("stop_acc", "停止高度精度"), ("startstop", "起停控制"), ("g_start", "起动"), ("g_stop", "停止"), ("pass5", "通过与否"),
                   ("n_mv", "挪动"), ("n_rev", "反复修正"), ("n_ineff", "无效修正")):
        diff = [(x["name"], x["phase"], x[k], y[k]) for x, y in zip(a5c, b5c) if x[k] != y[k]]
        print(f" 科目五 {lab}：变化 {len(diff)} 次 {diff}")
    print(f"   初停高度误差最大差 {max(abs(x['stop_err'] - y['stop_err']) for x, y in zip(a5c, b5c)):.3f} m")

    # ---------------- 典型实例 ----------------
    print("\n== 7. 典型实例逐步演示 ==")
    for n in ("14_19_06", "14_37_44", "14_45_19"):
        r = next(x for x in r3 if x["name"] == n)
        print(f"\n[科目三] {n}（{'完整' if r['complete'] else '中途结束'}）")
        print(f" ① 窗口：起飞 {r['t_go']:.2f} s；减速开始（初停前最后一次 ≥6 kt）{r['t_dec']:.2f} s，地速 {r['v_dec_kt']:.1f} kt；初次停住 {r['t_s1']:.2f} s；"
              f"最终稳定 {r['t_stab']} s（phase {r['stab_phase']}）；phase 1 长 {r['T1']:.1f} s；最大地速 {r['vmax_kt']:.1f} kt（只报告）")
        print(f" ② 移位航迹：横向偏差峰值 {r['xt_max']:.2f} m；超出期望边界（3.05 m）{r['track_n_d']} 段，最长 {r['track_long_d']:.2f} s；超出可接受边界（6.10 m）{r['track_n_a']} 段，"
              f"最长 {r['track_long_a']:.2f} s；期望内 {r['track_frac_in_d']:.1%} → 第 {r['track_rule']} 条 → {NAME[r['track']]}")
        print(f" ③ 一次到位：减速用时 {r['t_cap']:.2f} s（{NAME[r['once_time']]}）；初停点机体纵向 {r['lon1']:+.2f} m、横向 {r['lat1']:+.2f} m（{NAME[r['once_pos']]}）→ {NAME[r['once']]}")
        print(f" ④ 到点修正：适用 {'是' if r['corr_applicable'] else '否'}；挪动 {r['n_mv']} 次 {r['mv']}；反复修正 杆 {r['n_rev_stick']}／飞机 {r['n_mvrev']} → {r['n_rev']}；无效修正 {r['n_ineff']}；"
              f"最终纵 {r['lonE']:+.2f}、横 {r['latE']:+.2f} m → {NAME[r['corr']]}")
        print(f"    杆输入（轴 0 纵向杆、1 横向杆；时刻 s、持续 s、引起位移 m、分类）：{r['stick_ev'][:12]}{' …' if len(r['stick_ev']) > 12 else ''}")
        print(f" ⑤ 通过与否：{r['pass3']} {r['pass3_why']}；末帧地速 {r['v_end']:.2f} m/s，航向差 {r['hdg_end']:.1f}°，高度差 {r['h_err_end']:+.2f} m")
    for n in ("14_19_06",):
        print(f"\n[科目四] {n}")
        for q in [q for q in r4 if q["name"] == n]:
            print(f" phase {q['phase']}：保持 {q['dur']:.2f} s（从 {q['hold_start']:.2f} s 起）；位置最大 {q['pos_max']:.2f} m、高度最大 {q['h_max']:.2f} m、航向最大 {q['hdg_max']:.2f}°；"
                  f"有杆量 {q['stick_frac']:.1%} → {q['pass4']}")
    for n, ph in (("14_30_44", 3), ("13_55_01", 5), ("14_01_54_standard", 5)):
        r = next(x for x in r5c if x["name"] == n and x["phase"] == ph)
        print(f"\n[科目五] {n} phase {ph}（{'上升' if r['sg'] > 0 else '下降'}，起始 {r['h0']:.2f} m → 目标 {r['hstar']:.2f} m）")
        print(f" ① 窗口：首次升降杆输入 {r['t_in']:.2f} s；主运动开始 {r['t_go']:.2f} s；初次停住 {r['t_s1']:.2f} s；最终稳定 {r['t_stab']} s；最大垂直速度 {r['vz_max']:.2f} m/s")
        print(f" ② 停止高度精度：初停高度误差 {r['stop_err']:+.2f} m → {NAME[r['stop_acc']]}")
        print(f" ③ 起停控制·起动：反方向偏离起始高度 {r['wrong']:.2f} m → {NAME[r['g_start']]}")
        print(f" ④ 起停控制·停止：挪动 {r['n_mv']} 次 {r['mv']}；反复修正 杆 {r['n_rev_stick']}／飞机 {r['n_mvrev']}；无效修正 {r['n_ineff']}；最终误差 {r['e_end']:+.2f} m → {NAME[r['g_stop']]}")
        print(f" ⑤ 起停控制 = 较差者 → {NAME[r['startstop']]}；完成时间 {r['t_total']:.2f} s（超出速率上限最短时间 {r['t_excess']:.2f} s，只报告）；{r['pass5']}")


if __name__ == "__main__":
    main()
