# Checkpoint raw-series v2 验证记录

日期：2026-09-14。验证对象为当前工作区增量改造，不是航空训练有效性或 CPT 科学标定。

## 最终行为

- 当前目录、配置、输入和报告为 schema 2.0：4 个 item、16 个检查点、25 个数据量；全局 Model Studio 共 21 个节点。
- Checklist 读取 true/false。连续值按检查点输入明确的时间区间与原始值，系统计算有符号差及 D/A/U；航向正确处理跨 0°。没有阶段识别、截取或模拟器字段提取。
- D/A 容差相对期望值定义，支持不对称；规则、过程、有效时长分布、缺口和 A/U 事件分别保留。恢复不撤销已知 Fail。
- 三个飞行 item 保留空白 CPT 草稿编辑，不运行未定稿的整段或动态贝叶斯算法。模型问题单独记录，不改变有完整证据的规则结果。
- 1.0 后端仍需显式选择；v2 桌面拒绝旧格式的静默转换。旧模板保留，新模板位于 examples/scenes/SCN-001/v2。

## 自动化验证

| 检查 | 最终结果 | 覆盖 |
|---|---|---|
| Python scene 与相关 framing/dispatcher | 200 passed，7.96s | 原值/期望、signed/asymmetric/heading、时间权重、细分不变性、缺口/非法时间、布尔与事件、快照、版本、CPT 草稿校验 |
| Desktop.UnitTests | 175 passed | source-generated DTO、workspace 版本与状态、草稿保存及拒绝非法值、graph、报告保真 |
| Desktop.ContractTests | 6 passed | 真实 Python stdio、模型问题独立于规则、80,000 区间完整请求/报告往返 |
| SceneTimelineDrawingChecks | 5/5 passed | 唯一 U 不丢失、10 万段有界绘制、不等长区间、边界、缺失偏差但已知 U |
| WinUI 最终 scene-studio 构建 | 成功，0 warning / 0 error，15.29s | 最终源码及修正后的 Desktop.Core、绘图 helper |
| Ruff 与 whitespace | 通过 | scene Python、测试、示例生成器；既有 DECISIONS CRLF 提示不属于本轮修改 |

使用既有 .venv Python 3.11.15 与 .NET 10.0.302，无新增依赖或环境。主要复查命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/scene_assessment tests/sidecar/test_framing.py tests/sidecar/test_dispatcher.py -q
.venv/Scripts/python.exe -m ruff check src/pilot_assessment/scene_assessment tests/scene_assessment tools/Generate-SceneSeriesExamples.py
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --nologo
dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj --nologo
dotnet run --project tests/SceneTimelineDrawingChecks/SceneTimelineDrawingChecks.csproj --no-restore
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 -p:OutDir=C:/Users/long/Desktop/CranfieldOffer/proj/pilot_assessment_system/src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/ --nologo
```

新增关键用例先观察失败再实现。复核额外发现并修正了两项实际问题：旧 stride 绘图会遗漏第 1 帧唯一 U；模型草稿校验曾跳过已填写的非法 CPT。现在按时间桶保留边界、偏差极值与最差档，最多绘制 1800 个时段；已填概率和状态分值严格校验，同时允许合法 null/部分草稿。

## 实际桌面验证

通过 Windows computer-use 启动已核实的快捷方式目标，直接检查原生 WinUI。第一轮验证完成配置导入 → 检查点数据导入 → 评估 → 曲线与事件展开 → 报告导出。修正后重建并重启最终 EXE，再核查目录、checklist 与非法 CPT 拒绝行为。

1. Model Studio 位于菜单顶部，下面为加速减速任务，目录显示 4 item / 16 检查点。
2. 地面起飞编辑器显示实际目标 10、D 偏差 −2/+2、A 偏差 −5/+5；这些来自工程演示配置，默认仍为空。
3. 飞行模型的先验、状态分值和 CPT 可展开，全部初始空白；检查单的检查器明确仅评价完成性，没有技能 CPT 入口。
4. 合成航向数据按 D→U→A→D 展示，D/A/U 为 70%/20%/10%，空中滑行与场景保留 U/Fail。U 事件 [44,45) 秒、最大绝对偏差 8°；A 事件 [45,47) 秒、最大绝对偏差 3°。
5. 导出 engineering-demo-ui-report.json，并从文件回读，确认 input/configuration 与导入 JSON 完全一致，完整时序、占比、事件及 Fail 正确。
6. 最终构建中输入 prior=−1 后应用，界面显示“已填数值必须有限且在 0 至 1 范围内”，未应用非法值；随后取消测试输入，留下干净的空白工作区。

真实截图：[恢复过程与异常片段](assets/2026-09-14-air-taxi-recovery.png)、[最终构建的概率校验](assets/2026-09-14-cpt-validation.png)。前者来自修正绘图选点前的小样本端到端验证，小样本未触发抽样；修正后的大样本绘图选择由 5 项独立测试和最终构建验证。

## 启动路径与边界

桌面 PilotAssessment.Desktop.exe - 快捷方式.lnk 指向：

`C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\src\PilotAssessment.Desktop\bin\x64\Debug\scene-studio\PilotAssessment.Desktop.exe`

已重建该目录并实际启动最终版本。该版本仍依赖当前开发机器环境，没有重新制作便携安装包。

整段时间占比到后验概率的公式、动态 item 状态模型和参数标定仍待确定。本轮交付的是确定性规则与过程统计，不能称为已标定的能力分数。未读取真实 simulator 样例，未改 PPT、旧数据库或 DECISIONS.md；后者 SHA256 仍为 70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE。
