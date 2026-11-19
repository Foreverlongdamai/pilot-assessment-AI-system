"""One-off: rewrite the Python-environment lines in the three employee profiles (2026-11-18 env switch)."""
import pathlib

AG = pathlib.Path(r"C:\Users\long\Desktop\CranfieldOffer\proj\.claude\agents")
OUT = pathlib.Path(r"C:\Users\long\AppData\Local\Temp")

ENV = ("本项目登记的 conda 环境是 `claude-skills`（`D:\\Anaconda\\envs\\claude-skills`，Python 3.11），"
       "直接运行的 `python` 就是它。产品代码的测试与检查沿用 `pilot_assessment_system\\.venv`"
       "（以 claude-skills 的 Python 建立的 uv 虚拟环境，已装项目包），用完整路径运行，如 "
       "`pilot_assessment_system\\.venv\\Scripts\\python.exe -m pytest -q`。不往 base 装包，不另建环境。")

reps = {
    "evidence-designer.md": [(
        "- Python：本项目 conda 环境 `pilot-assessment`（numpy、scipy、pandas、polars、matplotlib、pytest、ruff）。不用 venv，不往 base 装包。",
        "- Python：" + ENV + "分析脚本所需的 numpy、scipy、pandas、matplotlib、opencv 都在 claude-skills 中。")],
    "report-designer.md": [(
        "- **python-pptx 所在环境。** python-pptx 等 Office 依赖装在 conda 环境 `claude-skills`，制作 PPT 的脚本用 `D:\\Anaconda\\envs\\claude-skills\\python.exe` 运行。本项目登记的 `pilot-assessment` 环境目前没有这些包，不往 base 装包，不用 venv。",
        "- **Python 环境。** 本项目登记的 conda 环境是 `claude-skills`，直接运行的 `python` 就是它，其中已有 python-pptx、openpyxl、matplotlib 等。不往 base 装包，不另建环境。")],
    "env-steward.md": [
        ("3. **Python 与工具环境。** 本项目登记的 conda 环境是 `pilot-assessment`（`D:\\Anaconda\\envs\\pilot-assessment`），Office skills 使用 `claude-skills` 环境。检查：",
         "3. **Python 与工具环境。** " + ENV + "Office skills 也用 claude-skills。2026-11-18 用户决定切回以前用的环境，`D:\\Anaconda\\envs\\pilot-assessment` 不再使用。检查："),
        ("   - 有没有往 base 环境装包或使用 venv 的情况。项目规定只用 conda，不用 venv。",
         "   - 有没有往 base 环境装包，或另建了不必要的环境；`pilot_assessment_system\\.venv` 是项目原有的产品测试环境，保留。"),
    ],
}

for name, pairs in reps.items():
    text = (AG / name).read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[2].lstrip("\n")
    for a, b in pairs:
        assert body.count(a) == 1, (name, a[:30])
        body = body.replace(a, b)
    (OUT / f"profile_{name}").write_text(body, encoding="utf-8")
    print(name, len(body))
