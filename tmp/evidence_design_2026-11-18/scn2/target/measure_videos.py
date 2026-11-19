"""对三段录像逐帧（每秒 10 帧）测量目标方块与红色参考点，输出 video_<名>.csv。约 5 分钟。"""
import os, sys, csv
import numpy as np
from measure_lib import frames, measure
HERE = os.path.dirname(os.path.abspath(__file__))
VD = r"C:\Users\long\Desktop\CranfieldOffer\proj\data\Mai_task3_hover"
VIDEOS = ["142010", "143450", "145543"]
KEYS = ["up_cx", "up_cy", "up_w", "up_h", "up_yw", "up_yh", "lo_cx", "lo_cy", "lo_w", "lo_h", "lo_yw", "lo_yh", "spacing",
        "du_x", "du_y", "dl_x", "dl_y"]
if __name__ == "__main__":
    for v in (sys.argv[1:] or VIDEOS):
        path = os.path.join(VD, f"Recording 2026-09-25 {v}.mp4")
        with open(os.path.join(HERE, f"video_{v}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t"] + KEYS)
            for t, im in frames(path, 10):
                m = measure(im)
                w.writerow([f"{t:.2f}"] + ([("" if m is None or k not in m else f"{m[k]:.2f}") for k in KEYS]))
        print("done", v)
