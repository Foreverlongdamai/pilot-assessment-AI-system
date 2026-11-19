"""场景二汇报插图（2026-11-18）。输出到 ../figures/scn2/，PNG，200 dpi。
运行：python make_figures.py   （需先运行 target/target_estimate.py 与 scn2_evidence.py；run_all.py 会按顺序运行）
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scn2_evidence as S  # noqa: E402
from scn2_evidence import FT, P  # noqa: E402

OUT = os.path.join(HERE, "..", "figures", "scn2")
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei"], "axes.unicode_minus": False, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e3df",
                     "grid.linewidth": 0.6, "axes.edgecolor": "#8a8984", "axes.labelcolor": "#52514e",
                     "xtick.color": "#52514e", "ytick.color": "#52514e", "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
                     "savefig.facecolor": "#fcfcfb"})
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
BLUE, ORANGE, AQUA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
GCOL = {"D": GOOD, "A": WARN, "U": CRIT}
BAND_D, BAND_A = "#e3f3e3", "#fdf1d6"
NAME = S.NAME


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("写出", name)


def grade_tag(ax, g, x=0.99, y=0.97, prefix=""):
    ax.text(x, y, f"{prefix}{NAME[g]}", transform=ax.transAxes, ha="right", va="top", fontsize=11, color=INK, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=GCOL.get(g, MUTED), lw=2))


def body(x, y, psi=226.0):
    a = np.radians(psi)
    return x * np.sin(a) + y * np.cos(a), x * np.cos(a) - y * np.sin(a)


def main():
    data = dict(S.task3_all())
    T = S.load_target()
    tgt = (T["X"], T["Y"])
    rows = json.load(open(os.path.join(HERE, "rows_dec1.json"), encoding="utf-8"))
    r3, r4, r5 = rows["subject3"], rows["subject4"], rows["subject5"]
    complete = {r["name"] for r in r3 if r["complete"]}

    # ------------------------------------------------------------------ 1 目标点估算示意（俯视）
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6.4), gridspec_kw=dict(width_ratios=[1, 1]))
    for n, df in data.items():
        d = df[df["Phase ID"].isin([1, 2])]
        lo_, la_ = body(d["Xe m"].values, d["Ye m"].values)
        a1.plot(la_, lo_, color=BLUE if n in complete else ORANGE, lw=0.8, alpha=0.7)
    a1.plot([0, T["lat"]], [0, T["lon"]], color=INK, lw=1.2, ls="--", label="参考航线：起点 → 目标点")
    a1.plot(0, 0, "o", color=INK, ms=8)
    a1.annotate("", xy=(0, 30), xytext=(0, 0), arrowprops=dict(arrowstyle="->", color=INK2, lw=1.4))
    a1.text(30, 2, "起点 (0, 0)；箭头为起点机头航向 226.0°（纵轴方向）", fontsize=9, color=INK2)
    a1.plot(T["lat"], T["lon"], marker="*", color=CRIT, ms=16, mec="white", mew=1.2, zorder=5)
    a1.annotate(f"目标悬停点\n沿机头 {T['lon']:.1f} m、向右 {T['lat']:.2f} m\n（世界坐标 X {T['X']:.2f}、Y {T['Y']:.2f}）\n"
                f"距起点 {np.hypot(T['lon'], T['lat']):.1f} m，在机头右侧 {np.degrees(np.arctan2(T['lat'], T['lon'])):.1f}°",
                (T["lat"], T["lon"]), xytext=(95, 30), textcoords="data", fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED))
    a1.plot([], [], color=BLUE, lw=1.2, label="完整记录 8 趟航迹")
    a1.plot([], [], color=ORANGE, lw=1.2, label="中途结束记录 9 趟航迹")
    a1.set_aspect("equal")
    a1.set_xlim(-15, 185)
    a1.set_ylim(-15, 175)
    a1.set_xlabel("初始机体横向（m，向右为正）")
    a1.set_ylabel("初始机体纵向（m，沿起点机头方向）")
    a1.set_title("俯视：17 趟 45°斜向移位航迹与参考航线", color=INK, loc="left")
    a1.legend(loc="upper left", fontsize=8.5, frameon=False)
    # 右：目标附近，机体坐标（相对目标）
    for s, fc, lab in ((P["POS_A"], BAND_A, "可接受区 ±6 ft（1.83 m）"), (P["POS_D"], BAND_D, "期望区 ±3 ft（0.91 m）")):
        a2.add_patch(Rectangle((-s, -s), 2 * s, 2 * s, fc=fc, ec="none", label=lab))
    a2.add_patch(Rectangle((-T["u_lat"], -T["u_lon"]), 2 * T["u_lat"], 2 * T["u_lon"], fill=False, ec=CRIT, lw=1.5, ls="--",
                           label=f"目标不确定度（横向 ±{T['u_lat']:.2f} m，纵向 ±{T['u_lon']:.2f} m）"))
    for r in r3:
        df = data[r["name"]]
        p2 = df[df["Phase ID"] == 2]
        lo, la = body(float(p2["Xe m"].iloc[-1]) - tgt[0], float(p2["Ye m"].iloc[-1]) - tgt[1])
        std = "standard" in r["name"]
        mk = "D" if std else "o"
        c = BLUE if r["complete"] else ORANGE
        a2.plot(la, lo, mk, color=c, ms=8 if std else 6, mec="white", mew=0.8, zorder=4)
        if std:
            a2.annotate("参考示范 " + r["name"][:8], (la, lo), xytext=(-120, 50) if r["complete"] else (40, -55), textcoords="offset points",
                        fontsize=8, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    hd = pd.read_csv(os.path.join(HERE, "target", "hold_estimates.csv"))
    for la in hd["lat_align"].values:
        a2.axvline(la - T["lat"], color=VIOLET, lw=0.8, alpha=0.6)
    a2.plot([], [], color=VIOLET, lw=1, label=f"录像对准估计的横向位置（{len(hd)} 段保持）")
    a2.plot([], [], "o", color=BLUE, label="完整记录最终位置")
    a2.plot([], [], "o", color=ORANGE, label="中途结束记录最终位置")
    a2.plot(0, 0, marker="*", color=CRIT, ms=16, mec="white", mew=1.2, zorder=5)
    a2.set_xlim(-4, 9)
    a2.set_ylim(-7, 4)
    a2.set_aspect("equal")
    a2.set_xlabel("机体横向（m，向右为正）")
    a2.set_ylabel("机体纵向（m，沿机头为正）")
    a2.set_title("目标附近：最终位置、悬停区与不确定度", color=INK, loc="left")
    a2.legend(loc="lower right", fontsize=8, frameon=True, framealpha=0.9)
    save(fig, "scn2_target_topview.png")

    # ------------------------------------------------------------------ 2 录像对准测量
    vd = pd.read_csv(os.path.join(HERE, "target", "video_142010.csv"))
    tj = json.load(open(os.path.join(HERE, "target", "target.json"), encoding="utf-8"))
    off = tj["calib"]["142010"]["offset"]
    df = data["14_19_06"]
    t = df["Simulation time"].values
    h = -df["Ze m"].values
    lo_all, la_all = body(df["Xe m"].values, df["Ye m"].values)
    tc = vd["t"].values + off
    H, LA = np.interp(tc, t, h), np.interp(tc, t, la_all)
    uy = ((vd.du_y - vd.up_cy) / vd.spacing).values
    lx = ((vd.dl_x - vd.lo_cx) / vd.spacing).values
    fig = plt.figure(figsize=(14, 5.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[0.9, 1, 1])
    a0 = fig.add_subplot(gs[0])
    import subprocess
    tmp = os.path.join(HERE, "target", "frame_hover_142010.png")
    if not os.path.exists(tmp):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(99.5 - off):.2f}", "-i",
                        os.path.join(S.TASK3 if hasattr(S, "TASK3") else r"C:\Users\long\Desktop\CranfieldOffer\proj\data\Mai_task3_hover", "Recording 2026-09-25 142010.mp4"),
                        "-frames:v", "1", tmp], check=True)
    im = Image.open(tmp)
    a0.imshow(im.crop((560, 330, 900, 720)))
    a0.set_xticks([])
    a0.set_yticks([])
    a0.grid(False)
    a0.set_title("下方悬停时的画面（录像 142010，记录 14_19_06 第 99.5 s）", color=INK, loc="left", fontsize=9.5)
    a0.annotate("上方目标方块\n（外黄框、内绿方块）", (170, 170), xytext=(5, 60), color="white", fontsize=8.5,
                arrowprops=dict(arrowstyle="->", color="white"))
    a0.annotate("下方目标方块：红色参考点\n落在绿方块中心 = 已对准", (171, 253), xytext=(5, 330), color="white", fontsize=8.5,
                arrowprops=dict(arrowstyle="->", color="white"))
    a0.annotate("上方红色参考点\n（升到上方目标高度时落入上方方块）", (167, 92), xytext=(60, 25), color="white", fontsize=8,
                arrowprops=dict(arrowstyle="->", color="white"))
    a1 = fig.add_subplot(gs[1])
    climb = np.isin(np.round(np.interp(tc, t, df["Phase ID"].values)), [3, 5, 7, 4, 8])
    s, c, rms, n = tj["calib"]["142010"]["u_y"]
    m = climb & ~np.isnan(uy) & (np.abs(uy - (s * H + c)) < 0.1)
    a1.plot(H[m], uy[m], ".", color=BLUE, ms=3, label=f"升降与上方保持期间的各帧（{int(m.sum())} 帧；剔除参考点被遮挡、误认的帧）")
    xx = np.linspace(40, 67, 50)
    a1.plot(xx, s * xx + c, color=INK, lw=1, label=f"拟合直线（每米 {s:.4f}）")
    a1.axhline(0, color=MUTED, lw=0.8)
    a1.axvline(T["h_U"], color=CRIT, lw=1.2, ls="--", label=f"上方目标高度 {T['h_U']:.2f} m")
    a1.set_xlabel("飞机高度（m，CSV）")
    a1.set_ylabel("上方参考点相对上方绿方块的竖向偏移\n（以两方块间距为单位，向下为正）")
    a1.set_title("竖向：偏移为零处即上方目标高度", color=INK, loc="left", fontsize=10)
    a1.legend(fontsize=8, frameon=False, loc="upper left")
    a2 = fig.add_subplot(gs[2])
    ph_v = np.round(np.interp(tc, t, df["Phase ID"].values))
    s, c, rms, n = tj["calib"]["142010"]["l_x"]
    m = np.isin(ph_v, [1, 2]) & ~np.isnan(lx) & (np.abs(lx - (s * LA + c)) < 0.05) & (np.abs(LA - 151.5) < 6)
    a2.plot(LA[m], lx[m], ".", color=BLUE, ms=3, label=f"到点前后各帧（{int(m.sum())} 帧；剔除误认帧）")
    xx = np.linspace(145.5, 157.5, 50)
    a2.plot(xx, s * xx + c, color=INK, lw=1, label=f"拟合直线（每米 {s:.4f}）")
    a2.axhline(0, color=MUTED, lw=0.8)
    a2.axvline(T["lat"], color=CRIT, lw=1.2, ls="--", label=f"目标横向位置 {T['lat']:.2f} m")
    a2.set_xlabel("飞机横向位置（m，初始机体坐标，CSV）")
    a2.set_ylabel("下方参考点相对下方绿方块的横向偏移\n（以两方块间距为单位，向右为正）")
    a2.set_title("横向：偏移为零处即目标横向位置", color=INK, loc="left", fontsize=10)
    a2.legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    save(fig, "scn2_target_video_alignment.png")

    # ------------------------------------------------------------------ 3 科目三 移位航迹（两趟）
    fig, axs = plt.subplots(2, 1, figsize=(12, 6.8), sharex=False)
    for ax, n in zip(axs, ("14_19_06", "14_23_41")):
        r = S.subject3(data[n], tgt, keep_series=True)
        se = r["series"]
        tt, xt = np.array(se["t"]), np.array(se["xt"])
        k6 = se["k6"]
        ax.axhspan(-P["XT_A"], P["XT_A"], color=BAND_A, lw=0)
        ax.axhspan(-P["XT_D"], P["XT_D"], color=BAND_D, lw=0)
        ax.plot(tt[:k6 + 1], xt[:k6 + 1], color=BLUE, lw=1.6, label="横向偏差（右为正）")
        ax.plot(tt[k6:], xt[k6:], color=MUTED, lw=1, label="减速开始之后（不计入本证据）")
        for a_, b_ in se["seg_d"]:
            ax.axvspan(tt[a_], tt[b_], color=WARN, alpha=0.35, lw=0)
        ax.axvline(tt[k6], color=INK2, lw=1, ls="--")
        ax.text(tt[k6], ax.get_ylim()[1] if False else P["XT_A"] + 0.3, " 减速开始\n （窗口结束）", fontsize=8.5, color=INK2, va="bottom")
        for yv, lab in ((P["XT_D"], "期望边界 ±10 ft（3.05 m）"), (P["XT_A"], "可接受边界 ±20 ft（6.10 m）")):
            ax.text(tt[0] + 0.5, yv + 0.1, lab, fontsize=8, color=INK2)
        ax.set_ylim(-7.5, 8.2)
        ax.set_xlim(0, tt[-1])
        ax.set_ylabel("横向偏差（m）")
        rule_txt = {1: "连续超出可接受边界 > 1 s", 2: "超出过可接受边界（每次 ≤ 1 s）", 3: "某次超出期望边界 > 1 s 或期望内 < 90%", 4: "全程符合期望"}[r["track_rule"]]
        ax.set_title(f"{n}：峰值 {r['xt_max']:.2f} m；最长一次超出期望边界 {r['track_long_d']:.1f} s；期望边界内 {r['track_frac_in_d']:.0%} → {rule_txt}",
                     color=INK, loc="left", fontsize=10)
        grade_tag(ax, r["track"], prefix="移位航迹：")
    axs[0].legend(loc="lower left", fontsize=8.5, frameon=False, ncol=2)
    axs[1].plot([], [], color=WARN, alpha=0.5, lw=6, label="超出期望边界的片段")
    axs[1].legend(loc="lower left", fontsize=8.5, frameon=False)
    axs[1].set_xlabel("自 phase 1 开始的时间（s）")
    fig.suptitle("45°斜向移位与到点悬停：移位航迹证据（相对“起点 → 目标点”参考航线的横向偏差）", x=0.01, ha="left", color=INK)
    fig.tight_layout()
    save(fig, "scn2_s3_transfer_track.png")

    # ------------------------------------------------------------------ 4 科目三 一次到位 + 到点修正（14_19_06、14_37_44）
    for n in ("14_19_06", "14_37_44"):
        r = S.subject3(data[n], tgt, keep_series=True)
        se = r["series"]
        tt, vh = np.array(se["t"]), np.array(se["vh"])
        x, y, psi = np.array(se["x"]), np.array(se["y"]), np.array(se["psi"])
        lon_e, lat_e = S.body_err(x, y, psi, *tgt)
        k6, s1 = se["k6"], se["s1"]
        t0 = tt[k6] - 8
        fig = plt.figure(figsize=(13, 7.2))
        gs = fig.add_gridspec(3, 2, width_ratios=[2.2, 1], height_ratios=[1, 1, 0.8])
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.plot(tt, vh, color=BLUE, lw=1.4)
        ax1.axhline(P["V_ENTRY"], color=MUTED, lw=0.8, ls=":")
        ax1.text(t0 + 0.3, P["V_ENTRY"] + 0.1, "6 kt（减速开始判据）", fontsize=8, color=INK2)
        ax1.axhline(P["MOVING"], color=MUTED, lw=0.8, ls=":")
        ax1.text(t0 + 0.3, P["MOVING"] + 0.05, "0.2 m/s（飞机在动）", fontsize=8, color=INK2)
        ax1.axvspan(tt[k6], tt[s1], color=BAND_D, lw=0)
        ax1.text((tt[k6] + tt[s1]) / 2, ax1.get_ylim()[1] * 0.85 if False else max(vh) * 0.75, f"减速用时\n{r['t_cap']:.2f} s", ha="center", fontsize=8.5, color=INK)
        for a_, b_ in se["mv"]:
            ax1.axvspan(tt[a_], tt[b_], color=WARN, alpha=0.3, lw=0)
        ax1.set_ylabel("地速（m/s）")
        ax1.set_xlim(t0, tt[-1])
        ax1.set_title(f"45°斜向移位与到点悬停（{n}）：一次到位与到点修正的窗口、事件", color=INK, loc="left")
        for tv, lab, ha in ((tt[k6], "减速开始 ", "right"), (tt[s1], " 初次停住", "left")):
            ax1.axvline(tv, color=INK2, lw=1, ls="--")
            ax1.text(tv, max(vh) * 1.02, lab, fontsize=8.5, color=INK2, ha=ha)
        ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax2.axhspan(-P["POS_A"], P["POS_A"], color=BAND_A, lw=0)
        ax2.axhspan(-P["POS_D"], P["POS_D"], color=BAND_D, lw=0)
        ax2.plot(tt, lon_e, color=BLUE, lw=1.4, label="机体纵向误差")
        ax2.plot(tt, lat_e, color=ORANGE, lw=1.4, label="机体横向误差")
        for i, (a_, b_) in enumerate(se["mv"], 1):
            ax2.axvspan(tt[a_], tt[b_], color=WARN, alpha=0.3, lw=0)
            ax2.text((tt[a_] + tt[b_]) / 2, 5.6, f"挪动{i}", ha="center", fontsize=8, color=INK2)
        ax2.axvline(tt[s1], color=INK2, lw=1, ls="--")
        ax2.set_ylim(-max(7, np.abs(np.r_[lon_e[s1:], lat_e[s1:]]).max() + 1.5), 7)
        ax2.set_ylabel("相对目标的误差（m）")
        ax2.legend(loc="lower right", fontsize=8.5, frameon=False, ncol=2)
        ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)
        ax3.plot(tt, se["lon"], color=BLUE, lw=1.1, label="纵向杆")
        ax3.plot(tt, se["lat"], color=ORANGE, lw=1.1, label="横向杆")
        ax3.axhspan(-P["DB"], P["DB"], color="#efeeea", lw=0)
        for ax_, tt_, du, dx, kind in r["stick_ev"]:
            if kind in ("反复修正", "无效修正"):
                ax3.annotate(kind, (tt_, 0), xytext=(0, 22), textcoords="offset points", fontsize=8, color=CRIT, ha="center",
                             arrowprops=dict(arrowstyle="->", color=CRIT))
        ax3.set_ylabel("杆量（满量程 ±100）")
        ax3.set_xlabel("自 phase 1 开始的时间（s）")
        ax3.legend(loc="lower right", fontsize=8.5, frameon=False, ncol=2)
        # 右上：初次停住点与最终位置
        ax4 = fig.add_subplot(gs[0:2, 1])
        lim = max(7, np.abs([lon_e[s1], lat_e[s1]]).max() + 1.5)
        ax4.add_patch(Rectangle((-P["POS_A"], -P["POS_A"]), 2 * P["POS_A"], 2 * P["POS_A"], fc=BAND_A, ec="none"))
        ax4.add_patch(Rectangle((-P["POS_D"], -P["POS_D"]), 2 * P["POS_D"], 2 * P["POS_D"], fc=BAND_D, ec="none"))
        ax4.plot(lat_e[s1:], lon_e[s1:], color=MUTED, lw=1)
        ax4.plot(lat_e[s1], lon_e[s1], "o", color=CRIT, ms=9, mec="white", label=f"初次停住点（纵 {r['lon1']:+.2f}，横 {r['lat1']:+.2f} m）")
        ax4.plot(lat_e[-1], lon_e[-1], "s", color=GOOD, ms=8, mec="white", label=f"最终位置（纵 {r['lonE']:+.2f}，横 {r['latE']:+.2f} m）")
        ax4.plot(0, 0, "*", color=INK, ms=12)
        ax4.set_xlim(-lim, lim)
        ax4.set_ylim(-lim, lim)
        ax4.set_aspect("equal")
        ax4.set_xlabel("机体横向（m）")
        ax4.set_ylabel("机体纵向（m）")
        ax4.legend(loc="lower center", bbox_to_anchor=(0.5, -0.42), fontsize=8, frameon=False)
        ax4.set_title("初次停住后的路径（绿：期望区；黄：可接受区）", color=INK, loc="left", fontsize=9.5)
        ax5 = fig.add_subplot(gs[2, 1])
        ax5.axis("off")
        ax5.grid(False)
        txt = (f"一次到位：用时 {r['t_cap']:.2f} s（{NAME[r['once_time']]}）；初停误差 {r['m1']:.2f} m（{NAME[r['once_pos']]}）→ {NAME[r['once']]}\n"
               f"到点修正：挪动 {r['n_mv']} 次，反复修正 {r['n_rev']} 次（杆 {r['n_rev_stick']}／飞机 {r['n_mvrev']}），无效修正 {r['n_ineff']} 次，\n"
               f"最终位置误差 {r['mE']:.2f} m → {NAME[r['corr']]}")
        ax5.text(0, 0.5, txt, fontsize=9, color=INK, va="center")
        fig.tight_layout()
        save(fig, f"scn2_s3_once_and_correction_{n}.png")

    # ------------------------------------------------------------------ 5 科目四 定点悬停保持曲线
    n = "14_19_06"
    qs = S.subject4(data[n], tgt, T["h_L"], T["h_U"], keep_series=True)
    fig, axs = plt.subplots(3, 4, figsize=(14, 7), sharey="row")
    for j, q in enumerate(qs):
        se = q["series"]
        tt = np.array(se["t"])
        pe = np.maximum(np.abs(se["lon"]), np.abs(se["lat"]))
        for i, (yv, lim, lab) in enumerate(((pe, P["POS_A"], "位置误差（m，两轴较大者）"), (np.abs(se["h"]), P["HV_ALT_A"], "高度误差（m）"),
                                             (np.abs(se["hdg"]), P["HDG_A"], "航向偏差（°）"))):
            ax = axs[i, j]
            ax.axhspan(0, lim, color=BAND_D, lw=0)
            ax.axhline(lim, color=CRIT, lw=1.2, ls="--")
            ax.plot(tt, yv, color=BLUE, lw=1.6)
            ax.set_ylim(0, lim * 1.25)
            if j == 0:
                ax.set_ylabel(lab)
            if i == 0:
                hs = "下方" if q["phase"] in (2, 6) else "上方"
                ax.set_title(f"phase {q['phase']}（{hs}保持，{q['dur']:.1f} s）→ {q['pass4']}", color=INK, loc="left", fontsize=9.5)
            if i == 2:
                ax.set_xlabel("保持时间（s）")
    axs[0, 0].text(0.1, P["POS_A"] * 1.05, "不通过线 ±6 ft（1.83 m）", fontsize=8, color=CRIT)
    axs[1, 0].text(0.1, P["HV_ALT_A"] * 1.05, "不通过线 ±4 ft（1.22 m）", fontsize=8, color=CRIT)
    axs[2, 0].text(0.1, P["HDG_A"] * 1.05, "不通过线 10°", fontsize=8, color=CRIT)
    fig.suptitle(f"定点悬停（{n}）：四段保持期间四杆全为零，曲线由模拟器保持；只判通过与否", x=0.01, ha="left", color=INK)
    fig.tight_layout()
    save(fig, "scn2_s4_hold_curves.png")

    # ------------------------------------------------------------------ 6 科目五 两个实例
    for n, ph in (("13_55_01", 5), ("14_01_54_standard", 5), ("14_30_44", 3)):
        q = next(x for x in S.subject5(data[n], T["h_L"], T["h_U"], keep_series=True) if x.get("phase") == ph)
        se = q["series"]
        tt, hh, u = np.array(se["t"]), np.array(se["h"]), np.array(se["u"])
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, gridspec_kw=dict(height_ratios=[2, 1]))
        hs = q["hstar"]
        ax1.axhspan(hs - P["VM_ALT_A"], hs + P["VM_ALT_A"], color=BAND_A, lw=0)
        ax1.axhspan(hs - P["VM_ALT_D"], hs + P["VM_ALT_D"], color=BAND_D, lw=0)
        h0 = q["h0"]
        ax1.axhspan(h0 - P["VM_ALT_A"], h0 + P["VM_ALT_A"], color=BAND_A, lw=0)
        ax1.axhspan(h0 - P["VM_ALT_D"], h0 + P["VM_ALT_D"], color=BAND_D, lw=0)
        ax1.plot(tt, hh, color=BLUE, lw=1.6, label="高度")
        ax1.axhline(hs, color=CRIT, lw=1, ls="--")
        ax1.text(tt[-1], hs, f" 目标高度 {hs:.2f} m", fontsize=8.5, color=CRIT, va="center")
        ax1.text(tt[-1], h0, f" 起始高度 {h0:.2f} m", fontsize=8.5, color=INK2, va="center")
        for k, lab, ha in ((se["i_in"], "首次输入", "right"), (se["go"], "主运动开始", "left"), (se["s1"], "初次停住", "right")):
            ax1.axvline(tt[k], color=INK2, lw=0.9, ls="--")
            ax1.text(tt[k], 0.3, " " + lab, fontsize=8.5, color=INK2, ha=ha, va="bottom", rotation=90, transform=ax1.get_xaxis_transform())
        for i, (a_, b_) in enumerate(se["mv"], 1):
            ax1.axvspan(tt[a_], tt[b_], color=WARN, alpha=0.35, lw=0)
        ax1.set_ylabel("高度（m）")
        ax1.set_title(f"{n} phase {ph}（{'上升' if q['sg'] > 0 else '下降'}）：停止高度精度 {NAME[q['stop_acc']]}（初停误差 {q['stop_err']:+.2f} m）\n"
                      f"起停控制 {NAME[q['startstop']]}（起动反向偏离 {q['wrong']:.2f} m → {NAME[q['g_start']]}；停住后挪动 {q['n_mv']} 次、反复修正 {q['n_rev']} 次 → {NAME[q['g_stop']]}）",
                      color=INK, loc="left", fontsize=9)
        if q["wrong"] > 0.05:
            k = int(np.argmax(-q["sg"] * (hh[:se["go"] + 1] - h0)))
            ax1.annotate(f"反方向偏离 {q['wrong']:.2f} m", (tt[k], hh[k]), xytext=(40, 0 if q['sg'] < 0 else -30), textcoords="offset points",
                         fontsize=9, color=CRIT, arrowprops=dict(arrowstyle="->", color=CRIT))
        ax2.plot(tt, u, color=ORANGE, lw=1.4)
        ax2.axhspan(-P["DB"], P["DB"], color="#efeeea", lw=0)
        ax2.set_ylabel("升降杆（±100）")
        ax2.set_xlabel("自本段开始的时间（s）")
        grade_tag(ax1, q["startstop"], x=0.995, y=0.6, prefix="起停控制：")
        fig.tight_layout()
        save(fig, f"scn2_s5_vertical_{n}_phase{ph}.png")

    # ------------------------------------------------------------------ 7 三档分布
    def bars(ax, items, title, note):
        labels = [k for k, _ in items]
        ys = np.arange(len(labels))[::-1]
        for y, (lab, vals) in zip(ys, items):
            c = {g: sum(v == g for v in vals) for g in ("D", "A", "U")}
            na = sum(v is None for v in vals)
            left = 0
            total = len(vals)
            outside = []   # 段太窄放不下文字的，标签改写在条形右侧，避免互相重叠
            for g in ("D", "A", "U"):
                if c[g]:
                    ax.barh(y, c[g], left=left, color=GCOL[g], height=0.55, edgecolor="#fcfcfb", linewidth=2)
                    if c[g] / total >= 0.15:
                        ax.text(left + c[g] / 2, y, f"{NAME[g]} {c[g]}", ha="center", va="center", fontsize=8.5,
                                color="white" if g != "A" else INK)
                    else:
                        outside.append((g, f"{NAME[g]} {c[g]}"))
                    left += c[g]
            if na:
                ax.barh(y, na, left=left, color="#d9d8d3", height=0.55, edgecolor="#fcfcfb", linewidth=2)
                if na / total >= 0.15:
                    ax.text(left + na / 2, y, f"不适用 {na}", ha="center", va="center", fontsize=8.5, color=INK2)
                else:
                    outside.append((None, f"不适用 {na}"))
                left += na
            if outside:
                ax.text(left + 0.012 * total, y, "（" + "、".join(t for _, t in outside) + "）", ha="left", va="center", fontsize=8.5, color=INK)
                ax.set_xlim(0, total * 1.28)
        ax.set_axisbelow(True)
        ax.set_yticks(ys)
        ax.set_yticklabels(labels)
        ax.set_xlabel("次数")
        ax.grid(axis="y", visible=False)
        ax.set_title(title, color=INK, loc="left")
        ax.text(0, -0.28, note, transform=ax.transAxes, fontsize=8.5, color=INK2)

    fig, ax = plt.subplots(figsize=(10, 3.4))
    bars(ax, [("移位航迹（过程型）", [r["track"] for r in r3]), ("一次到位（结果型）", [r["once"] for r in r3]),
              ("到点修正（条件型）", [r["corr"] for r in r3])],
         "45°斜向移位与到点悬停：17 趟的三档分布", "通过与否（任务结果）：通过 %d、不通过 %d；样本 17 趟（8 趟完整、9 趟中途结束）。脚本 scn2_evidence.py"
         % (sum(r["pass3"] == "通过" for r in r3), sum(r["pass3"] == "不通过" for r in r3)))
    save(fig, "scn2_s3_distribution.png")
    fig, ax = plt.subplots(figsize=(10, 2.8))
    p_ = [q["pass4"] for q in r4]
    for y, (lab, sub) in enumerate((("phase 2（下方，17 次）", [q for q in r4 if q["phase"] == 2]), ("phase 4、6、8（24 次）", [q for q in r4 if q["phase"] != 2]))[::-1]):
        ok = sum(q["pass4"] == "通过" for q in sub)
        bad = len(sub) - ok
        ax.barh(y, ok, color=GOOD, height=0.55, edgecolor="#fcfcfb", linewidth=2)
        ax.text(ok / 2, y, f"通过 {ok}", ha="center", va="center", color="white", fontsize=9)
        if bad:
            ax.barh(y, bad, left=ok, color=CRIT, height=0.55, edgecolor="#fcfcfb", linewidth=2)
            ax.text(ok + bad / 2, y, f"不通过 {bad}", ha="center", va="center", color="white", fontsize=9)
    ax.set_axisbelow(True)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["phase 4、6、8（24 次）", "phase 2（下方，17 次）"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("保持段数")
    ax.set_title("定点悬停：只判通过与否（共 %d 段；不通过的 5 段都是最终位置在停止区外）" % len(p_), color=INK, loc="left")
    save(fig, "scn2_s4_distribution.png")
    r5c = [r for r in r5 if r["complete"]]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    bars(ax, [("停止高度精度（结果型）", [r["stop_acc"] for r in r5c]), ("起停控制（操纵型）", [r["startstop"] for r in r5c]),
              ("　其中：起动", [r["g_start"] for r in r5c]), ("　其中：停止后修正", [r["g_stop"] for r in r5c])],
         "垂直升降与悬停建立：24 次升降的三档分布", "通过与否（任务结果）：通过 %d、不通过 %d；样本 8 趟完整记录 × 3 次升降。脚本 scn2_evidence.py"
         % (sum(r["pass5"] == "通过" for r in r5c), sum(r["pass5"] == "不通过" for r in r5c)))
    save(fig, "scn2_s5_distribution.png")


if __name__ == "__main__":
    main()
