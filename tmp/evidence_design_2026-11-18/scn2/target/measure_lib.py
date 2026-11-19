"""录像中目标方块与红色参考点的像素测量（场景二目标点估算用）。
画面：远处立杆上有上下两个目标方块（外黄框 = 可接受区，内绿方块 = 期望区）；近处立杆上有上下两个红色参考点。
飞机在正确位置时，红色参考点落在绿方块中心（与 ADS-33E-PRF 图 24 的悬停板 + 参考标志相同的视线对准原理）。
"""
import subprocess
import numpy as np
from scipy import ndimage

FFMPEG = "ffmpeg"


def frames(path, fps, t0=0.0, t1=None):
    """逐帧读取视频（RGB），返回生成器 (t, img)。t 为视频内时刻。"""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    cmd = [FFMPEG, "-v", "error", "-ss", f"{t0:.3f}"] + (["-to", f"{t1:.3f}"] if t1 else []) + \
          ["-i", path, "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    k = 0
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield t0 + k / fps, np.frombuffer(b, np.uint8).reshape(h, w, 3)
        k += 1
    p.wait()


def masks(im):
    r, g, b = im[..., 0].astype(int), im[..., 1].astype(int), im[..., 2].astype(int)
    green = (g > 215) & (r < 175) & (b < 150) & (g - r > 60)
    yellow = (r > 195) & (g > 215) & (b < 170) & (r - b > 70)
    red = (r - g > 35) & (r - b > 60) & (g < 215) & (r > 80)
    return green, yellow, red


def _half_max_center(p):
    """一维剖面在半高处左右边缘（线性插值）的中点。"""
    p = np.asarray(p, float)
    hm = p.max() / 2.0
    idx = np.where(p >= hm)[0]
    a, b = idx[0], idx[-1]
    left = a - 1 + (hm - p[a - 1]) / (p[a] - p[a - 1]) if a > 0 else float(a)
    right = b + (p[b] - hm) / (p[b] - p[b + 1]) if b + 1 < len(p) else float(b)
    return (left + right) / 2.0


def detect(im):
    """返回两个目标方块（按上下排序）及红点。
    每个方块：绿方块中心 (cx, cy)、宽 w、高 h（像素，按像素计数的包围盒）。红点：列表 [(cx, cy, n)]。
    只认被黄框包围的绿色块，排除仪表上的绿色字符。"""
    green, yellow, red = masks(im)
    lab, n = ndimage.label(ndimage.binary_closing(yellow | green, structure=np.ones((3, 5)), iterations=1))
    boxes = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if hh < 8 or ww < 6 or hh > 200:
            continue
        reg = lab[sl] == i
        if not (green[sl] & reg).any():
            continue
        gy = green[sl] & reg
        yy = yellow[sl] & reg
        if gy.sum() < 12 or yy.sum() < 20:
            continue
        # 绿方块：用逐行 / 逐列的绿色像素数确定边界（穿过方块的黑色立杆会切掉 1～2 列，用中位行宽补偿）
        rows = np.where(gy.sum(1) >= 2)[0]
        cols = np.where(gy.sum(0) >= 2)[0]
        if len(rows) < 3 or len(cols) < 3:
            continue
        y0, y1 = rows[0], rows[-1]
        x0, x1 = cols[0], cols[-1]
        yrows = np.where(yy.sum(1) >= 2)[0]
        ycols = np.where(yy.sum(0) >= 2)[0]
        # 亚像素：绿色程度（G−R，在黄框 ≈ 15、绿方块 ≈ 135 之间线性取 0～1）沿行、列求和，取半高处插值得到边缘
        sub = im[sl].astype(float)
        gs = np.clip((sub[..., 1] - sub[..., 0] - 15.0) / 120.0, 0, 1) * reg
        cx_s = _half_max_center(gs[y0:y1 + 1].sum(0))
        cy_s = _half_max_center(gs[:, x0:x1 + 1].sum(1))
        boxes.append(dict(cx=sl[1].start + cx_s, cy=sl[0].start + cy_s,
                          w=float(x1 - x0 + 1), h=float(y1 - y0 + 1),
                          yw=float(ycols[-1] - ycols[0] + 1), yh=float(yrows[-1] - yrows[0] + 1),
                          ycx=sl[1].start + (ycols[0] + ycols[-1]) / 2.0, ycy=sl[0].start + (yrows[0] + yrows[-1]) / 2.0))
    boxes.sort(key=lambda b: b["cy"])
    dots = []
    if boxes:
        wmax = max(b["yw"] for b in boxes)
        lab2, n2 = ndimage.label(red)
        cand = []
        for i, sl in enumerate(ndimage.find_objects(lab2), 1):
            yy, xx = np.where(lab2[sl] == i)
            if 1 <= len(yy) <= 16 and (sl[0].stop - sl[0].start) <= 6:
                wgt = (im[sl][..., 0].astype(float) - im[sl][..., 1].astype(float))[yy, xx]
                cand.append((float((xx * wgt).sum() / wgt.sum() + sl[1].start), float((yy * wgt).sum() / wgt.sum() + sl[0].start), int(len(yy))))
        # 红白标杆的条纹在同一竖列上成串出现（≥3 个），参考点每列最多 2 个
        keep = []
        for c in cand:
            same_col = [d for d in cand if abs(d[0] - c[0]) <= 0.6 * wmax + 2 and abs(d[1] - c[1]) <= 3 * wmax]
            if len(same_col) <= 2:
                keep.append(c)
        # 只保留落在目标板竖列附近（横向不超过 0.7 个黄框宽）、面积 ≤8 像素的点
        for c in keep:
            if c[2] <= 8 and any(abs(c[0] - b["cx"]) <= 0.7 * b["yw"] and abs(c[1] - b["cy"]) <= 8 * b["yh"] for b in boxes):
                dots.append(c)
    return boxes, dots


def board_pair(boxes):
    """在检出的方块中找上下成对（横向相差 < 0.6 个黄框宽）的一组；有多组时取面积最大的一组（最近的目标板）。"""
    best = None
    for i in range(len(boxes)):
        for j in range(len(boxes)):
            a, b = boxes[i], boxes[j]
            if b["cy"] <= a["cy"] or abs(a["cx"] - b["cx"]) > 0.6 * max(a["yw"], b["yw"]):
                continue
            if b["cy"] - a["cy"] > 6 * max(a["yh"], b["yh"]):
                continue
            s = a["w"] * a["h"] + b["w"] * b["h"]
            if best is None or s > best[0]:
                best = (s, a, b)
    return None if best is None else (best[1], best[2])


def measure(im):
    """返回 dict：上下方块几何，及上参考点相对上方块、下参考点相对下方块的偏移（像素与方块单位）。"""
    boxes, dots = detect(im)
    pr = board_pair(boxes)
    if pr is None:
        return None
    up, lo = pr
    mid = (up["cy"] + lo["cy"]) / 2.0
    out = dict(up_cx=up["cx"], up_cy=up["cy"], up_w=up["w"], up_h=up["h"], up_yw=up["yw"], up_yh=up["yh"],
               lo_cx=lo["cx"], lo_cy=lo["cy"], lo_w=lo["w"], lo_h=lo["h"], lo_yw=lo["yw"], lo_yh=lo["yh"],
               spacing=lo["cy"] - up["cy"])
    cols = [d for d in dots if abs(d[0] - (up["cx"] + lo["cx"]) / 2) <= 0.7 * max(up["yw"], lo["yw"])]
    ups = [d for d in cols if d[1] < mid]
    los = [d for d in cols if d[1] >= mid]
    if ups:
        d = min(ups, key=lambda d: abs(d[0] - up["cx"]))
        out.update(du_x=d[0], du_y=d[1])
    if los:
        d = min(los, key=lambda d: abs(d[0] - lo["cx"]))
        out.update(dl_x=d[0], dl_y=d[1])
    return out
