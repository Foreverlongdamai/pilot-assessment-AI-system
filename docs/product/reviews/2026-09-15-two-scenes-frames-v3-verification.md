# 两场景逐帧 v3 实现验证

日期：2026-09-15。范围：现有 Python 计算器、WinUI 场景页与 Model Studio 的 v3 改造。不是飞行员训练有效性或阈值标定结果。

## 已交付

- SCN-001：起飞前检查、起点就位、空中滑行（加速与保速）、快速减速／急停，4 item / 15 检查点。
- SCN-002：起点就位、悬停高度保持、悬停定点保持、垂直升降控制，4 item / 9 检查点；下、上、下、上四次各 5 秒悬停和三次转移。
- 同一目录注册表驱动左侧菜单、总画布、模板和后端。总画布有 34 个节点：2 Task、8 item、24 检查点。
- 输入改为 scene → item → frames，每帧使用精确 timestamp_s、明确 phase_id 和原始 values。支持可选 controls 原样保留。
- 逐帧偏差、D/A/U、P/F、有效帧分布、阶段结果、输入与配置完整快照。已知 U 不因后续恢复而消失。
- 场景页与 Model Studio 共用参数；编辑器显示低于／高于目标允许量，上下激光靶几何可分别编辑。
- 七个飞行 item 保留先验、状态分值及 CPT 草稿编辑。量化方法 pending_method，不运行未经确定的整段推断或生成能力分数。

## 自动验证

| 验证范围 | 结果 |
|---|---|
| Python 场景与 sidecar framing/dispatcher 相关套件 | 263 passed，10.98 s |
| 场景 Python 源码与测试 Ruff | 全部通过 |
| .NET Desktop UnitTests | 191 / 191 passed |
| .NET 真实 v3 Gateway 合同，两场景 | 2 / 2 passed；最终时间一致性补丁后重跑通过 |
| .NET 旧版 1.0 / 2.0 Gateway 合同 | 2 / 2 passed，包含 80,000 样本传输 |
| 时间线绘制选择检查 | 7 / 7 passed |
| 最终 WinUI Debug x64 构建 | 0 警告，0 错误；12.96 s |

上述 Python 套件包括新增逐帧、径向边界、缺失、顺序和一致性测试，以及两个场景经真实 JSON-RPC 的输入／配置／报告往返检查。保留显式旧版本路径，当前界面不静默转换旧文件。

最终构建命令：

```powershell
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 -p:OutDir=C:/Users/long/Desktop/CranfieldOffer/proj/pilot_assessment_system/src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/ --nologo
```

## 实际窗口验证

使用本次构建的程序及工程演示数据，经过真实文件选择器完成以下操作：

1. 启动实际窗口：左侧 Model Studio 位于两个场景之上，总图显示 2 场景 / 8 item / 24 检查点。
2. SCN-002 加载配置、导入帧、评估并导出报告。起点、高度、升降为 D；悬停定点为 U。定点保持 204 个有效帧：D 176、A 20、U 8；四阶段为 A/U/U/A，首末帧跨度均为 5 秒。
3. 展开定点报告：可见逐帧原值／目标／偏差、激光 u/v 与靶心距离、有效帧比例、阶段说明和 A/U 帧明细入口。
4. 打开参数编辑器：上下靶各有靶心、实体靶半径、D/A 半径；固定距离定义显示当前实际值且打开不改配置。其还原按钮只修复距离定义，不替用户填写几何或半径。
5. 将工程配置的下靶 D 半径从 0.2 改为 0.25 并应用。旧报告失效；从 Model Studio 再次打开该 item，读回值确为 0.25。此修改仅用于 UI 验证，不是推荐值。
6. 从总图打开 CPT 编辑器，确认先验与各检查点 D/A/U 概率字段可见、草稿为空、量化方法待定提示可见。
7. SCN-001 加载配置、导入帧、评估并导出报告。检查单、起点、急停为 D；空中滑行保留短暂航向 U。急停显示停止位置精度、减速过程控制、限制与禁止接触三个检查点；停止位置只有明确 stop 状态的一帧。
8. 对两个窗口导出的 JSON 做内容验证：configuration 与 input 分别等于加载的原文件，完整计算状态与预期档位一致。无需依赖界面摘要猜测导出内容。

本轮 QA 数据与 UI 控件快照在工作区 tmp/scene_v3_qa/；可重新生成的正式工程示例见下方入口。UI 验证使用合成数据，没有读取或处理真实 CSV。自动测试与窗口操作验证软件行为，不代表科学标定。

## 启动与后续打磨

实际桌面快捷方式 `PilotAssessment.Desktop.exe - 快捷方式.lnk` 已核对指向本次构建的 scene-studio/PilotAssessment.Desktop.exe；未改快捷方式。验证结束后放弃本轮临时半径修改，正常关闭 QA 实例，并直接通过该快捷方式重新打开；新进程窗口确认显示干净的 Model Studio、两个场景及 34 个节点。运行 [启动脚本](../../../tools/Start-SceneAssessment.ps1) 也进入此版本。这是依赖本机现有运行环境的开发构建，不是新的便携发布包。

- [当前使用指南](../SCENE_CALCULATOR_GUIDE_CN.md)
- [SCN-001 输入与配置模板](../../../examples/scenes/SCN-001/v3/README.md)
- [SCN-002 输入与配置模板](../../../examples/scenes/SCN-002/v3/README.md)

默认模板不填未经确认的飞行容差、激光半径或概率。帧比例仅是有效帧比例；不假定帧间持续状态，不生成时间积分。5 秒要求只检查所提供首末帧跨度，不证明连续采样质量。阶段已经由上游标明，系统只检查数据一致性，不检测事件或自动切段。

后续与用户逐项打磨检查方法、可配置参数及界面；再确定整段证据进入贝叶斯模型的算法和参数来源。现有 DECISIONS.md、PPT、环境和无关修改均保留，本轮没有提交或重置 Git 工作树。
