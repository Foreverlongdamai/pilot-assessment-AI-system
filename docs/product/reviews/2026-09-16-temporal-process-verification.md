# 时序过程分析实现与验证

日期：2026-09-16。用户批准将“固定 item 能力 S＋时间相关观察”用于各检查点/item 的过程描述；未来是否用于最终评估另行讨论。

## 已实现范围

- 两场景共 5 个飞行 item、14 个飞行检查点，统一接入 `fixed_skill_markov_v1`。起飞前检查的 6 项 true/false 检查保持完成性记录，不生成连续操纵能力曲线。
- 每个检查点累计自己的条件观察似然；item 融合各检查点的条件似然，先验只计一次。没有把检查点后验再相乘，也没有把旧最终评分的 κ=3 用入新过程算法。
- item 结果窗口及展开后的检查点增加完整时轴的后验期望曲线和本帧 log BF（高/低）证据图。后验表示对本次固定能力的累计认识；log BF 表示新证据方向。二者均不替代原累计质量分、最终分或规则 P/F。
- 参数编辑器支持显式启用/关闭以及每个检查点低/中/高三态的相关时间 τ。演示配置采用 [5,5,5] 秒；这是未标定的工程起点，既不是官方数值，也不是平均恢复耗时。
- 原 `items[item_id].frames` 输入不变。阶段/不适用边界重开观察链但不清除已有能力证据；缺测留空并标记不完整，不插值学员观测。旧配置未提供 `process_model` 时明确显示未启用。
- DTO、模型克隆、参数变更判断、报告快照和导出均保留新增字段。过程参数错误单独阻断过程结果，不改变旧评分或规则计算。
- 两场景六份配置/报告、方法说明和离线对比页已更新。新版过程图使用报告已有数据，不在浏览器另算贝叶斯后验。

## 执行过的检查

| 检查 | 实际结果 |
|---|---|
| Python 场景套件 | 505 passed，含本轮 45 个时序测试 |
| Desktop UnitTests | 297 passed |
| 六例真实 Python → Desktop 合同 | 6 passed；新 DTO、全帧、无证据空值、后验归一化及导出回读 |
| 既有绘图检查 | 7 帧选择检查＋11 原值绘图检查通过；新过程分段与精确时刻由 UnitTests 覆盖 |
| 独立高精度审查 | 150 条随机记录，14,078 个后验向量；最大概率误差 4.13e-14 |
| 六报告独立重算 | 9,180 个过程点；最大数值误差 4.41e-13；15 条 item trace、42 条检查点 trace |
| 原行为保持 | 六份输入 SHA-256、规则阈值、CPT、先验、原最终后验/分数、原累计曲线及 P/F 与备份完全一致 |
| 离线页渲染检查 | 38 个选择组合、6,468 个检查点过程点通过，未产生 NaN/Infinity 坐标 |
| 浏览器实际视验 | 已查看空中滑行的 item/速度检查点双图；完整 28.3–44.4 s 时间轴、三案例、阶段间隔、正负证据均可见 |
| 原快捷方式目标 build | 成功，0 警告、0 错误；目标 `src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/` |
| ZIP 演示包 | 36 个条目与当前目录逐字节一致，CRC 检查通过；原 ZIP 已另存备份 |

独立数学审查发现并修正了极小 CPT 下丢失非零转移保持项、完整适用阶段缺失却把检查点过程标为 complete 两处问题。反例和修复复验详见[独立审查](2026-09-16-temporal-process-independent-review.md)。

## 原生窗口验收边界

已启动更新后的原快捷方式目标 EXE，并读取到 Model Studio 主界面。随后电脑出现同时操作：最初的工具栏动作返回 `coordinate input geometry is unavailable`，刷新截图显示另一窗口遮挡；恢复时分别遇到 `no screenshot targets found`、`user input was detected in this window`。因此暂停进一步原生 UI 操作，避免干扰用户。

**本轮没有声称已完成桌面逐项点选、参数编辑保存或通过原生文件框导出报告的验收。** C# 构建、真实报告合同测试和浏览器实际显示已经通过；原生结果窗口的最终视觉验收仍待空闲窗口条件。未关闭用户的其他应用。

## 复现与文件

```powershell
.\.venv\Scripts\python.exe -m pytest tests/scene_assessment -q
dotnet test tests/PilotAssessment.Desktop.UnitTests --nologo
dotnet test tests/PilotAssessment.Desktop.ContractTests --filter FullyQualifiedName~SceneSupervisorDemoContractTests --nologo
dotnet run --project tests/SceneTimelineDrawingChecks --no-restore
.\.venv\Scripts\python.exe tools/Generate-SupervisorDemo.py --with-reports
.\.venv\Scripts\python.exe tools/Verify-TemporalDemo.py
.\.venv\Scripts\python.exe tools/Build-SupervisorDemoPresentation.py
node tools/Check-TemporalDemoViewer.cjs
```

本轮原演示包备份在 `tmp/temporal_process_qa/before/`。重算输出在 `tmp/temporal_process_qa/demo-verification.json`；高精度 oracle 和数值探测在 `tmp/temporal_math_probes/`。独立重算与页面检查脚本已放入 `tools/`，不依赖新增包。

最新 `examples/supervisor-demo-2026-09-15.zip` 为 3,542,633 字节，SHA-256：`682ec4f26f8ddece7040c1c1322cf6f7cf7bf6ca302c290f0a0267f30114dacc`。旧包备份为 `tmp/temporal_process_qa/supervisor-demo-before-temporal.zip`。本轮未修改既有 `docs/product/DECISIONS.md`；其 SHA-256 保持 `70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`。

这些检查证明实现与所声明模型一致，不证明 CPT、相关时间、检查点条件独立假设或训练效度已由真实飞行员验证。长时间良好表现后，固定 S 的后验仍可饱和；不能将“每次失误都必须显著拉低累计分”作为本模型正确性的要求。
