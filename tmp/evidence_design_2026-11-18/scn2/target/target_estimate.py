"""场景二目标悬停点估算（2026-11-18）。

一条命令（在本目录）：python target_estimate.py > target_output.txt
前提：video_<名>.csv 已由 measure_videos.py 生成（上一级的 run_all.py 会先跑它）。
输出：target_output.txt（设计文档“目标悬停点的确定”一节的全部数字）、target.json（供证据脚本读取）、hold_estimates.csv。

坐标：世界坐标 X、Y（CSV 的 Xe、Ye），高度 h = -Ze。
“初始机体坐标”：以起点 (0, 0) 为原点、起点机头航向 226.0° 为纵轴：纵向 = 沿机头，横向 = 向右为正。
航向约定（场景一、场景二已由数据确定）：机头单位向量 (sin ψ, cos ψ)，右侧单位向量 (cos ψ, −sin ψ)。
"""
import datetime as dt
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "bn_optimization_2026-11-12"))
from load import TASK3, task3_all  # noqa: E402

FT = 0.3048
PSI0 = 226.0
A0 = np.radians(PSI0)
# 录像与 CSV 的对应：按 mp4 内的创建时刻（UTC，+1 h 为英国夏令时）和 CSV 文件名时刻（= 记录保存时刻 = 记录结束）
PAIRS = [("142010", "14_19_06"), ("143450", "14_34_41"), ("145543", "14_55_53")]
REF_RUNS = ["14_01_54_standard", "14_50_03_standard"]
LAT_GUESS, LON_GUESS = 151.5, 150.0   # 只用于选取“目标附近”的帧（±6 m），不进入结果


def body(x, y):
    """世界坐标 → 初始机体坐标（纵向, 横向）。"""
    return x * np.sin(A0) + y * np.cos(A0), x * np.cos(A0) - y * np.sin(A0)


def world(lon, lat):
    return lon * np.sin(A0) + lat * np.cos(A0), lon * np.cos(A0) - lat * np.sin(A0)


def video_start_utc(v):
    p = os.path.join(TASK3, f"Recording 2026-09-25 {v}.mp4")
    s = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time:format=duration", "-of", "json", p],
                       capture_output=True, text=True).stdout
    j = json.loads(s)["format"]
    return dt.datetime.fromisoformat(j["tags"]["creation_time"].replace("Z", "+00:00")), float(j["duration"])


def csv_start_bst(run, dur):
    hh, mm, ss = (int(v) for v in run.split("_")[:3])
    end = dt.datetime(2026, 9, 25, hh, mm, ss, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    return end - dt.timedelta(seconds=dur)


def load_video(v):
    vd = pd.read_csv(os.path.join(HERE, f"video_{v}.csv"))
    for k, (dc, bc) in {"l_x": ("dl_x", "lo_cx"), "l_y": ("dl_y", "lo_cy"), "u_x": ("du_x", "up_cx"), "u_y": ("du_y", "up_cy")}.items():
        vd[k] = (vd[dc] - vd[bc]) / vd["spacing"]   # 参考点相对绿方块中心的偏移，以上下两方块的间距为单位（与远近、画面缩放无关）
    return vd


def robust_line(xv, yv, it=3):
    """最小二乘直线，迭代剔除残差 > 4×中位绝对残差 的点。返回 (斜率, 截距, 残差均方根, 点数)。"""
    m = np.ones(len(xv), bool)
    for _ in range(it):
        p = np.polyfit(xv[m], yv[m], 1)
        r = yv - np.polyval(p, xv)
        m = np.abs(r) <= 4 * np.median(np.abs(r[m])) + 1e-6
    p = np.polyfit(xv[m], yv[m], 1)
    r = yv[m] - np.polyval(p, xv[m])
    return float(p[0]), float(p[1]), float(np.sqrt(np.mean(r ** 2))), int(m.sum())


def sync_offset(vd, t, sig, sel, col, nominal, span=3.0):
    """在名义时差 ±span 内找使“偏移 ~ 飞行量”线性拟合残差最小的时差（步长 0.02 s）。"""
    best = None
    for off in np.arange(nominal - span, nominal + span, 0.02):
        tc = vd["t"].values + off
        val = vd[col].values
        m = ~np.isnan(val) & (tc > t[0]) & (tc < t[-1])
        s = np.interp(tc[m], t, sig)
        ok = (np.interp(tc[m], t, sel) > 0.5) & (np.abs(val[m]) < 0.6)
        if ok.sum() < 20:
            continue
        sl, ic, rms, n = robust_line(s[ok], val[m][ok])
        if best is None or rms < best[1]:
            best = (float(off), rms, sl, ic, n)
    return best


def summ(lab, a):
    a = np.asarray(a, float)
    sd = float(np.std(a, ddof=1)) if len(a) > 1 else float("nan")
    se = sd / np.sqrt(len(a)) if len(a) > 1 else float("nan")
    print(f"  {lab}：{len(a)} 段，均值 {np.mean(a):.3f}，范围 {np.min(a):.3f}～{np.max(a):.3f}，标准差 {sd:.3f}，均值标准误 {se:.3f}")
    return float(np.mean(a)), float(np.min(a)), float(np.max(a)), sd


def main():
    data = dict(task3_all())
    complete = [n for n, df in data.items() if 9 in set(df["Phase ID"])]
    print("== 1. 场景几何：各趟悬停位置在初始机体坐标中的位置 ==")
    print("phase 2 末帧位置（科目三的最终位置）；完整记录另列 phase 4、6、8 的平均高度。")
    rows = []
    for n, df in data.items():
        p2 = df[df["Phase ID"] == 2]
        x, y = float(p2["Xe m"].iloc[-1]), float(p2["Ye m"].iloc[-1])
        lo, la = body(x, y)
        r = float(np.hypot(x, y))
        brg = float(np.degrees(np.arctan2(x, y)) % 360)
        hs = {ph: float(-df[df["Phase ID"] == ph]["Ze m"].mean()) for ph in (4, 6, 8) if (df["Phase ID"] == ph).any()}
        rows.append(dict(name=n, complete=n in complete, x=x, y=y, lon=lo, lat=la, r=r, brg=brg, **{f"h{k}": v for k, v in hs.items()}))
        print(f"{n:<18} X {x:9.3f} Y {y:6.3f} | 纵 {lo:8.3f} 横 {la:8.3f} | 距起点 {r:7.3f} m（{r / FT:6.1f} ft） 方位 {brg:6.2f}°（机头右 {brg - PSI0:5.2f}°）"
              + "".join(f" | h{k} {v:6.3f}" for k, v in hs.items()))
    G = pd.DataFrame(rows)
    C = G[G.complete]
    print(f"完整 8 趟：纵向 {C.lon.min():.2f}～{C.lon.max():.2f}（中位 {C.lon.median():.2f}）；横向 {C.lat.min():.2f}～{C.lat.max():.2f}（中位 {C.lat.median():.2f}）；"
          f"方位 {C.brg.min():.2f}～{C.brg.max():.2f}°；距离 {C.r.min():.2f}～{C.r.max():.2f} m")
    for n in REF_RUNS:
        g = G[G.name == n].iloc[0]
        print(f"参考示范 {n}：纵 {g.lon:.3f} 横 {g.lat:.3f}")
    print("\n整齐几何假设检验（与完整 8 趟比较；“偏差”为假设点减完整 8 趟中位）：")
    hyps = [("机头右 45°、距离 700 ft（213.36 m）", 213.36 * np.cos(np.radians(45)), 213.36 * np.sin(np.radians(45))),
            ("机头右 45°、距离 213 m", 213 * np.cos(np.radians(45)), 213 * np.sin(np.radians(45))),
            ("纵向 150 m、横向 150 m", 150.0, 150.0),
            ("世界坐标 X −213.36（−700 ft）、Y 5.0", *body(-213.36, 5.0))]
    for lab, lo, la in hyps:
        x, y = world(lo, la)
        print(f"  {lab}：纵 {lo:7.2f} 横 {la:7.2f}（X {x:8.2f} Y {y:5.2f}）；偏差 纵 {lo - C.lon.median():+5.2f} 横 {la - C.lat.median():+5.2f} m；"
              f"完整 8 趟纵向在 ±0.30 m 内 {int((np.abs(C.lon - lo) <= 0.3).sum())} 趟、横向 {int((np.abs(C.lat - la) <= 0.3).sum())} 趟")

    print("\n== 2. 录像对准测量 ==")
    print("画面元素：远处立杆上上下两个目标方块（外黄框、内绿方块），近处立杆上上下两个红色参考点。")
    print("测量量：参考点中心相对绿方块中心的偏移，除以上下两方块中心的像素间距（随距离同比缩放，抵消远近与画面缩放）。")
    print("对准时偏移为 0；先用飞机移动（升降、横移）时偏移随 CSV 位置的线性变化求比例，再由静止保持时的偏移换算对准位置。")
    holds, calib, store = [], {}, []
    for v, run in PAIRS:
        df = data[run]
        t = df["Simulation time"].values
        h = -df["Ze m"].values
        ph = df["Phase ID"].values
        lo, la = body(df["Xe m"].values, df["Ye m"].values)
        vh = np.hypot(df["V_ex m/s"], df["V_ey m/s"]).values
        vz = -df["V_ez m/s"].values
        vs, vdur = video_start_utc(v)
        nominal = (vs - csv_start_bst(run, float(t[-1]))).total_seconds()
        vd = load_video(v)
        print(f"\n[录像 {v} ↔ 记录 {run}] 录像长 {vdur:.1f} s；按文件时刻，录像开始 = 记录第 {nominal:.1f} s；检出目标板的帧 {int(vd['up_cx'].notna().sum())}/{len(vd)}")
        offs = []
        if np.isin(ph, [3, 5, 7]).any() and 9 in set(ph):
            offs.append(("上方参考点竖向偏移 ~ 高度（升降段）", sync_offset(vd, t, h, np.isin(ph, [3, 5, 7]).astype(float), "u_y", nominal)))
        lat_move = (np.isin(ph, [1, 2]) & (vh > 0.05) & (vh < 2.5) & (np.abs(la - LAT_GUESS) < 6)).astype(float)
        offs.append(("下方参考点横向偏移 ~ 横向位置（到点前后的低速移动）", sync_offset(vd, t, la, lat_move, "l_x", nominal)))
        for lab, b in offs:
            print(f"  时差拟合 {lab}：{b[0]:.2f} s（残差均方根 {b[1]:.4f}，{b[4]} 帧）")
        off = float(np.mean([b[0] for _, b in offs]))
        print(f"  采用时差 {off:.2f} s（与按文件时刻的名义值相差 {off - nominal:+.2f} s）")
        tc = vd["t"].values + off
        inr = (tc > t[0]) & (tc < t[-1])

        def I(s):
            return np.interp(tc, t, s)
        H, LA, LO, PH, VH, VZ = I(h), I(la), I(lo), np.round(I(ph)), I(vh), I(vz)
        cal = dict(offset=off, nominal=nominal)
        for k in ("u_y", "l_y"):
            sel = inr & np.isin(PH, [3, 5, 7]) & (np.abs(vd[k].values) < 0.4) & vd[k].notna().values
            if sel.sum() > 20:
                cal[k] = robust_line(H[sel], vd[k].values[sel])
        sel = inr & np.isin(PH, [1, 2]) & (VH < 2.5) & (np.abs(LA - LAT_GUESS) < 6) & vd["l_x"].notna().values & (np.abs(vd["l_x"].values) < 0.4)
        cal["l_x"] = robust_line(LA[sel], vd["l_x"].values[sel])
        A = np.c_[LA[sel] - LAT_GUESS, LO[sel] - LON_GUESS, np.ones(sel.sum())]
        cxy = np.linalg.lstsq(A, vd["l_x"].values[sel], rcond=None)[0]
        cal["l_x_lat2"], cal["l_x_lon2"] = float(cxy[0]), float(cxy[1])
        cal["lo_range_x"] = (float(LO[sel].min()), float(LO[sel].max()))
        sel2 = inr & np.isin(PH, [1, 2]) & (VH < 2.5) & (np.abs(LO - LON_GUESS) < 6) & vd["l_y"].notna().values & (np.abs(vd["l_y"].values) < 0.4)
        if sel2.sum() > 20:
            A2 = np.c_[LO[sel2] - LON_GUESS, LA[sel2] - LAT_GUESS, np.ones(sel2.sum())]
            cly = np.linalg.lstsq(A2, vd["l_y"].values[sel2], rcond=None)[0]
            cal["l_y_lon"] = float(cly[0])
            cal["lo_range_y"] = (float(LO[sel2].min()), float(LO[sel2].max()))
        calib[v] = cal
        for k in ("u_y", "l_y", "l_x"):
            if k in cal:
                s, c, rms, n = cal[k]
                unit = "高度" if k.endswith("_y") else "横向位置"
                print(f"  比例 {k}（对{unit}）：每米 {s:+.5f}，零点 {-c / s:.3f} m，残差均方根 {rms:.4f}（折合 {rms / abs(s):.2f} m），{n} 帧")
        store.append((v, run, cal, H, LA, LO, PH, VH, VZ, inr, vd))
    # 比例的采用：斜率方向正确、残差折合 < 0.5 m 的拟合才采用；某段录像某项不合格（升降段下方参考点被锥标、建筑遮挡误认，或该段没有升降）时，用其余录像合格值的平均
    sign = {"u_y": 1, "l_y": 1, "l_x": -1}
    good = {k: [c[k][0] for _, _, c, *_ in store if k in c and np.sign(c[k][0]) == sign[k] and c[k][2] / abs(c[k][0]) < 0.5] for k in sign}
    pooled = {k: float(np.mean(v_)) for k, v_ in good.items()}
    print("\n比例采用（合格拟合的平均，用于替代不合格者）：" + "；".join(f"{k} 合格 {len(good[k])} 段，平均每米 {pooled[k]:+.5f}" for k in sign))
    for v, run, cal, H, LA, LO, PH, VH, VZ, inr, vd in store:
        use = {k: (cal[k][0] if cal.get(k) and cal[k][0] in good[k] else pooled[k]) for k in sign}
        cal["used"] = use
        if "l_y_lon" in cal:
            print(f"  录像 {v} 纵向敏感度：高度不变时，下方竖向偏移对纵向位置的系数 {cal['l_y_lon']:+.5f}/m（纵向范围 {cal['lo_range_y'][0]:.1f}～{cal['lo_range_y'][1]:.1f} m），"
                  f"折合纵向移动 1 m 相当于高度变化 {cal['l_y_lon'] / use['l_y']:+.3f} m")
        for p in (2, 4, 6, 8):
            m = inr & (PH == p) & (VH < 0.05) & (np.abs(VZ) < 0.05)
            if m.sum() < 5:
                continue
            hb = "l" if p in (2, 6) else "u"
            yy, xx = vd[f"{hb}_y"].values[m], vd[f"{hb}_x"].values[m]
            # 保持帧中参考点被立杆、锥标遮挡或误认的帧，偏移会离开方块（|偏移| ≥ 0.3，约 7 m）；剔除后取中位数
            ok = ~np.isnan(yy) & ~np.isnan(xx) & (np.abs(yy) < 0.3) & (np.abs(xx) < 0.3)
            if ok.sum() < 5:
                continue
            sy, sx = use[f"{hb}_y"], use["l_x"]
            oy, ox = float(np.median(yy[ok])), float(np.median(xx[ok]))
            hh, ll = float(np.mean(H[m][ok])), float(np.mean(LA[m][ok]))
            holds.append(dict(video=v, run=run, phase=p, box="下方" if hb == "l" else "上方", n=int(ok.sum()), n_all=int(m.sum()),
                              h=hh, off_y=oy, sd_y=float(np.std(yy[ok])), lat=ll, lon=float(np.mean(LO[m][ok])), off_x=ox, sd_x=float(np.std(xx[ok])),
                              h_align=hh - oy / sy, lat_align=ll - ox / sx))
    HD = pd.DataFrame(holds)
    HD.to_csv(os.path.join(HERE, "hold_estimates.csv"), index=False, float_format="%.4f")
    print("\n逐段保持的独立估计（静止帧：地速 <0.05 m/s 且垂直速度 <0.05 m/s）：")
    for _, r in HD.iterrows():
        print(f"  录像 {r.video} 记录 {r.run} phase {r.phase} {r.box}方块 {r.n:3d}/{r.n_all:3d} 帧 | 高度 {r.h:7.3f}，竖向偏移中位 {r.off_y:+.4f}（帧间标准差 {r.sd_y:.4f}）→ 对准高度 {r.h_align:7.3f} | "
              f"横向 {r.lat:7.3f}，横向偏移 {r.off_x:+.4f}（{r.sd_x:.4f}）→ 对准横向 {r.lat_align:7.3f}")

    print("\n== 3. 合成 ==")
    hL = summ("下方对准高度", HD[HD.box == "下方"].h_align)
    hU = summ("上方对准高度", HD[HD.box == "上方"].h_align)
    LAT = summ("对准横向位置（四段保持全部）", HD.lat_align)
    ref = G[G.name.isin(REF_RUNS)]
    print(f"  纵向：录像不能确定（见第 2 节纵向敏感度）；场景几何取 150.0 m。两份参考示范 {ref.lon.round(3).tolist()}；完整 8 趟中位 {C.lon.median():.3f}（只作核对）")
    LON = 150.0
    lat_c = round(LAT[0], 2)
    q1, q3 = np.percentile(C.lon, [25, 75])
    u_lon = round(max(float(np.max(np.abs(ref.lon - LON))), float((q3 - q1) / 2), 0.25), 2)
    u_lat = round(max(0.25, (LAT[2] - LAT[1]) / 2), 2)
    # 下方目标高度：取场景初始条件（17 趟 phase 0 首帧高度 40.920 m；phase 1、2 无升降杆输入、高度不变），录像对准作核对
    H_L0 = float(-data[REF_RUNS[0]]["Ze m"].iloc[0])  # 17 趟 phase 0 首帧高度相同（证据脚本第 0 节核对）
    u_hL = round(max(0.15, (hL[2] - hL[1]) / 2, abs(hL[0] - H_L0)), 2)
    print(f"  下方目标高度取起点高度 {H_L0:.3f} m（场景初始条件）；录像 5 段估计均值 {hL[0]:.3f}，与之相差 {hL[0] - H_L0:+.3f} m，在不确定度内")
    u_hU = round(max(0.15, (hU[2] - hU[1]) / 2), 2)
    print(f"  不确定度取法：横向、高度取逐段估计范围的一半，不小于 0.25 m（横向）、0.15 m（高度）；纵向取参考示范偏离 150 m 的最大值、完整 8 趟纵向四分位距的一半、0.25 m 三者较大者。"
          f"纵向四分位距之半 {(q3 - q1) / 2:.3f}，参考示范最大偏离 {float(np.max(np.abs(ref.lon - LON))):.3f}")
    X, Y = world(LON, lat_c)
    tgt = dict(lon=LON, lat=lat_c, X=round(float(X), 3), Y=round(float(Y), 3), h_L=round(H_L0, 2), h_U=round(hU[0], 2), psi=PSI0,
               u_lon=float(u_lon), u_lat=float(u_lat), u_hL=float(u_hL), u_hU=float(u_hU))
    print(f"\n目标：初始机体坐标 纵 {tgt['lon']:.2f} ± {tgt['u_lon']:.2f} m、横 {tgt['lat']:.2f} ± {tgt['u_lat']:.2f} m；"
          f"世界坐标 X* {tgt['X']:.3f}、Y* {tgt['Y']:.3f}；下方目标高度 {tgt['h_L']:.2f} ± {tgt['u_hL']:.2f} m；上方目标高度 {tgt['h_U']:.2f} ± {tgt['u_hU']:.2f} m；期望航向 {PSI0:.1f}°")
    corners = [world(LON + a, lat_c + b) for a in (-u_lon, u_lon) for b in (-u_lat, u_lat)]
    tgt["corners"] = [[round(float(a), 3), round(float(b), 3)] for a, b in corners]
    print("  不确定度矩形四角（世界坐标）：", tgt["corners"])
    print(f"  上下对准高度差 {tgt['h_U'] - tgt['h_L']:.2f} m；起点高度 40.920 m")
    print("\n交叉核对：")
    for n in REF_RUNS:
        g = G[G.name == n].iloc[0]
        s = f"  参考示范 {n} 最终位置相对目标：纵 {g.lon - LON:+.2f}、横 {g.lat - lat_c:+.2f} m"
        if g.complete:
            s += f"；上方保持 {g.h4:.2f}／{g.h8:.2f} m（相对上方目标 {g.h4 - tgt['h_U']:+.2f}／{g.h8 - tgt['h_U']:+.2f}），下降后下方保持 {g.h6:.2f} m（相对 {g.h6 - tgt['h_L']:+.2f}）"
        print(s)
    print(f"  完整 8 趟最终位置相对目标：纵 {np.min(C.lon - LON):+.2f}～{np.max(C.lon - LON):+.2f}，横 {np.min(C.lat - lat_c):+.2f}～{np.max(C.lat - lat_c):+.2f} m")
    hu = C[["h4", "h8"]].values.ravel() - tgt["h_U"]
    print(f"  完整 8 趟上方保持高度相对上方目标 {hu.min():+.2f}～{hu.max():+.2f} m（中位 {np.median(hu):+.2f}）；下降后下方保持相对下方目标 {np.min(C.h6 - tgt['h_L']):+.2f}～{np.max(C.h6 - tgt['h_L']):+.2f} m")
    with open(os.path.join(HERE, "target.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(target=tgt, calib=calib, holds=holds), fh, ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main()
