# 加速减速任务范围修订

**Goal:** 根据用户确认的真实任务流程，从 SCN-001 删除正常进近至悬停，并将停止科目名称对应到 FAA 的 Rapid Deceleration/Quick Stop。

**Architecture:** 修改当前 v3 场景目录，由同一目录生成菜单、Model Studio、空白配置与输入模板。保留通用路线计算引擎、旧版目录与历史演示记录。当前六例演示另存到新目录，删除已退出场景的 item，其他科目的帧、参数、CPT 不变。

**Tech Stack:** Python 场景目录与计算器、WinUI/.NET 桌面客户端、JSON 示例。

## 已确认设计

- 实际阶段：phaseID 1 加速并保持 30 knots；phaseID 2 减速并停在指定位置；phaseID 3 确认结束。没有正常进近至悬停阶段。
- 删除 A-S2-23，以及只供该 item 使用的阶段、指标、模板参数与模型。确认结束不新增能力 item。
- A-S2-30 显示名称改为“快速减速／快速停止”，记录官方英文名称 Rapid Deceleration/Quick Stop。ID、检查点、阈值、先验、CPT 和推断方法保持。
- 起飞前检查尚未讨论删除，本次保留。SCN-002 不变。
- FAA-S-ACS-2，Area VI / Task A，印刷第 32 页（PDF 第 37 页），CP.VI.A.S3–S6：航向、最大性能减速、合适功率及推力方向、协调飞行。官方名称不等于目前系统已完整覆盖该任务；固定停止位置是项目任务目标，当前系统不判定最大性能。
- 旧 v3 文件仍含 A-S2-23 时须明确整理，不静默丢弃用户数据。历史示例保留，新示例目录为 examples/task-scope-2026-10-11。

来源：[FAA Commercial Pilot for Powered-Lift ACS](https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=37)。

## 实施与验证

- [x] 修改并运行当前目录合同，确认旧目录不能满足新任务范围。
- [x] 修改 v3 目录；同步当前模板、示例生成器与使用指南。
- [x] 从九月示例生成独立的新演示包；逐项确认保留科目的输入、参数与模型没有变化，重算六例。
- [x] 执行 Python 场景测试、桌面当前场景合同和桌面构建；核对总画布应为 2 Task + 5 item + 18 检查点 = 25 节点。
- [x] 在交接文件顶部记录当前决定、示例路径与验证边界。
