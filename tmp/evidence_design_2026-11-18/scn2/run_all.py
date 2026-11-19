"""场景二证据设计：一条命令复现全部数字与插图（2026-11-18）。

在本目录运行：
    python run_all.py              # 全部：录像测量（约 7 分钟）→ 目标估算 → 证据试算 → 插图
    python run_all.py --skip-video # 跳过录像测量，沿用 target/video_*.csv
输出：target/target_output.txt、target/target.json、target/hold_estimates.csv、scn2_output.txt、rows_dec1.json、rows_dec10.json、
      ../figures/scn2/*.png
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TG = os.path.join(HERE, "target")


def run(args, cwd, out=None):
    print(">", " ".join(args), "（目录", os.path.relpath(cwd, HERE) or ".", "）", flush=True)
    if out:
        with open(os.path.join(cwd, out), "w", encoding="utf-8") as fh:
            subprocess.run([sys.executable] + args, cwd=cwd, check=True, stdout=fh, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    else:
        subprocess.run([sys.executable] + args, cwd=cwd, check=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


if __name__ == "__main__":
    if "--skip-video" not in sys.argv:
        run(["measure_videos.py"], TG)
    run(["-W", "ignore", "target_estimate.py"], TG, "target_output.txt")
    run(["scn2_evidence.py"], HERE, "scn2_output.txt")
    run(["-W", "ignore", "make_figures.py"], HERE)
    print("完成")
