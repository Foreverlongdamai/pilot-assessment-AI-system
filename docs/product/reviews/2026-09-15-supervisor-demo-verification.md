# 双场景导师演示验证记录

日期：2026-09-15。范围为显式启用的 v3 演示模型、六份人工合成数据、WinUI 展示与离线对比页；不是机型适用性、真实技能测量效度或训练有效性验证。

## 交付物

- `examples/supervisor-demo-2026-09-15/`：两份配置、六份逐帧输入、六份真实计算器报告、六份运动/分布诊断，含来源说明、总览、离线 HTML、方法及响应敏感性文件。
- `tools/Generate-SupervisorDemo.py`、`Generate-LocalResponseSensitivity.py`、`Build-SupervisorDemoPresentation.py`：可从现有项目环境再生；展示页不自行评分。
- 两场景分别 4 item / 14 检查点、3 item / 6 检查点，默认空模板保持 pending。显式演示配置才计算全项分数与局部曲线；检查单无技能分数，Task 无贝叶斯总分。

## 自动检查结果

| 检查 | 实际结果 |
|---|---|
| Python `tests/scene_assessment` | 383 passed |
| Desktop.UnitTests | 244 passed |
| Desktop.ContractTests，筛选 Scene | 10 passed；包括六份实际演示文件经过 C# DTO/工作区与真实 Python stdio 后端 |
| 原有逐帧图形检查 | 7/7 passed |
| 新增/修改 Python 方法、生成器及专项测试 Ruff | 全部通过 |
| WinUI Debug x64 原 scene-studio 输出路径 | 最终构建成功，0 warning / 0 error |
| 六报告 | 全部 complete，issues 为空；前两类均 A/Pass，局部失误类均 U/Fail |
| 展示页代码逻辑 | 39 个 scene/item/checkpoint/metric 选择均生成有限图坐标、结果及局部曲线；未冒称浏览器测试 |

专项检查涵盖后验和为 1、手算结果、重复帧不放大整项证据、帧顺序与局部时序区别、缺失与非法 CPT、默认 pending、已知 U 保留、phase 重置、真实时间戳、超大时间值、因果窗口闭边界及无共同观察窗口之间断线。时间窗口边界采用输入时间可往返的十进制数值精确比较，不靠浮点容差扩大 3 秒窗口。

数据额外检查：悬停位置与速度的有限差分/解析导数相符，偏差在 0.03 m/s 内；激光刚性射线前向重建误差小于 1e-6 m。它们证明合成信号内部关系一致，并非完整飞行动力学仿真。

## 原生软件实跑

重新构建并从原桌面快捷方式启动：`C:\Users\long\Desktop\PilotAssessment.Desktop.exe - 快捷方式.lnk`，目标为仓库 `src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/PilotAssessment.Desktop.exe`。最终 DLL 修改时间 2026-09-15 14:31:08（本机输出）；没有仅凭 apphost EXE 时间判断同步。

1. 两场景分别加载演示配置和局部失误输入并评估，均显示 U/Fail 和各 item 的“演示量化 · 未标定”。
2. 分别导出报告至 `tmp/supervisor_demo_qa/scn001-unqualified-ui.report.json`、`scn002-unqualified-ui.report.json`。逐项回读：输入/配置快照、规则档位、整个量化对象（后验、分数、局部曲线）与 Python 生成报告完全相同。
3. 原生检查点图实际显示平稳、偏离低谷及恢复，保留阶段断线、全量精确时刻明细。截图位于 `tmp/supervisor_demo_qa/scn001-local-visible.png` 等。
4. Model Studio 同时显示两个场景的最新 Fail 与 item 演示分；点击悬停定点模型后，检查器显示低/中/高概率；CPT 编辑器实际读回先验 1/3、Low-D 0.1、Middle-U 0.02、High-U 0.001。没有修改配置。
5. 清理了检查器/编辑器从旧目录带出的“完全不输出分数”固定文案。最终构建重新加载两个场景、评估和 CPT 读回均成功。一次自动化导航紧跟模态框关闭而未生效，等待关闭后重试正常；没有将该次中间失败当作通过。

原生脚本、结构快照及导出回读证据保存在 `tmp/supervisor_demo_qa/`。

## 过程响应与 CPT 敏感性

默认同一 CPT，3 秒窗口，κ=3，插入 1 秒异常：D→U→D 的局部分数 97.10→22.39→97.10；D→A→D 为 97.10→74.90→97.10。第一个异常帧即响应；第一个恢复 D 后约 2.05 秒才开始回升、3 秒后完全恢复，因为窗口仍保留先前异常帧。原值/D/A/U 同时显示实际即时恢复。

固定窗口/强度，只改变中/高状态的 U 概率假设，D→U→D 最低分可为 13.74、22.39、44.00。说明 CPT 对幅度影响显著，不能以演示图好看替代真实校准。全部对照、原始概率表与每个响应点均在敏感性 JSON 中。

## 验证边界

内置浏览器的 URL 安全策略拒绝打开本地 HTML，未使用其他浏览器或本地代理绕过。因此 HTML 只通过代码逻辑检查，浏览器视觉/兼容性验证未完成；可向用户提供文件自行打开。可读 Markdown 总览和已经验证的原生软件不依赖该页面。

保护文件 `docs/product/DECISIONS.md` SHA256 仍为 `70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`，与本次工作开始一致。未更新 PPT、未提交 Git、未安装新依赖或修改默认模拟器数据合同。
