# 悬停 item 合并实施计划

日期：2026-09-15。用户已批准将悬停高度纳入定点悬停，同步修改软件、模板和演示数据；本计划直接执行，不增加审批环节。

**目标：** SCN-002 将同一次悬停的水平位置、高度、航向和激光表现放入一个 `A-S2-02`「定点悬停保持」item，得到一份包含高度证据的整项结果。

**结构：** 沿用 v3 `items[item_id].frames`、已有标量偏差/航向最短角差/激光半径计算。调整目录内的归属，不新增观测提取、阶段识别或三维合成距离。前端、输入模板、检查点 CPT 和总画布继续由同一目录生成。

**技术范围：** Python 场景目录和计算器、.NET 10 Desktop.Core/WinUI、既有示例与演示生成器；使用现有环境，不提交 Git，不修改历史评审、`DECISIONS.md` 或 PPT。

## 已批准合同

删除独立 `A-S2-01`「悬停高度保持」。`A-S2-02` 改名「定点悬停保持」，四个检查点顺序固定为：

| 顺序与检查点 | 每帧原始量 | 计算与归属 |
|---|---|---|
| 1 · `A-S2-02-01` 水平位置保持 | `hover_x_m`、`hover_y_m`、`hover_vx_mps`、`hover_vy_mps` | X/Y 分别计算有符号位置偏差；水平速度作为停稳的补充检查，不合成 X/Y 距离。 |
| 2 · `A-S2-02-04` 悬停高度保持 | `hover_lower_height_m` 或 `hover_upper_height_m`、`hover_vz_mps` | 只读取当前阶段适用的高度；垂直速度作为高度稳定的补充检查，不把上下两个目标同时要求于同一帧。 |
| 3 · `A-S2-02-02` 航向保持 | `hover_heading_deg` | 最短航向角差，不再重复包含速度。 |
| 4 · `A-S2-02-03` 激光指向保持 | `laser_lower_spot` 或 `laser_upper_spot` | 按当前应评靶的命中状态、靶心距离和 D/A 半径判断。 |

四次悬停仍为 `lower_1 → upper_1 → lower_2 → upper_2`，各要求已提供帧首末跨度至少 5 秒。`SCENE-VERTICAL`「垂直升降控制」及其 `rise_1 / descend_1 / rise_2`、两检查点和三个原始指标不变。全场景阶段顺序仍为下方悬停、上升、上方悬停、下降、下方悬停、上升、上方悬停。

SCN-002 为 **2 item / 6 检查点 / 13 指标键**。定点悬停每帧提供 8 个适用指标值：当前高度、X/Y、三个速度分量、航向、当前激光靶落点。上下高度与上下激光分别配置；保留原始指标名，不复制跨 item 数据，不补空值。

四检查点各自产生 D/A/U，进入同一悬停 item 的四份 CPT。显式演示模式的整项公式沿用固定 κ=3、等检查点权重，因此本项每个检查点权重为 1/4；不是给每个原始指标各 1/4。上下高度共用高度检查点，不分别重复加权。每个检查点的局部近 3 秒曲线仍独立使用该检查点 CPT，不将四条线拼成动态 item 技能。

规则 D/A/U 与 P/F 独立保留：D/A 为 Pass，已知 U 为 Fail；缺失不伪造 U 或完整 Pass。默认空配置仍不启用演示模型；新演示配置才计算未标定后验和分数。合并改变了证据集合，不能把新分数视为旧两个 item 分数的平均。

## 官方内容与项目适配

- [FAA-S-ACS-2，印刷第18页／PDF第23页，CP.IV.A.S5/S6/S8](https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=23)在同一悬停机动任务中分别检查推荐高度、指定点位置和航向；支持把它们放入同一悬停能力项，仍逐维呈现证据。S5 的高度容差随离地高度条件变化，不可无条件套成一个固定米数。
- [UK CAA Standards Document 03(H)，V6，印刷第18页，Section 2(c)](https://www.caa.co.uk/publication/download/12966#page=18)将定常悬停的航向、高度和地面位置同时列为检查内容，包含迎风、侧风和顺风条件。本场景未覆盖全部风况或完整资格考试。
- [EASA Flight Examiner Manual，Module 3.3 CPL(H)，第10页 Section 2(c)及第20页技能说明](https://www.easa.europa.eu/en/downloads/138658/en)列出定常悬停，并在技能说明中共同检查航向、高度和地面位置；作为本次合并的直升机考核交叉参照，不据此增加数值，也不将直升机手册直接称为所有 eVTOL 的通用要求。

四检查点划分、速度补充检查、激光圆盘、两高度往返、每次 5 秒、逐帧最差档及 CPT/分数均为项目适配。FAA 的位置条款不等于规定本系统采用 X/Y/Z 合距；本轮维持分量分别检查，不自动换算或改写容差。

## 实施与验收

- [x] 修改 `src/pilot_assessment/scene_assessment/scn002_v3.json`：两 item、四个定点悬停检查点及明确来源；核对每个原始指标只归属一个适用检查点。
- [x] 更新 `tests/scene_assessment/test_v3_catalog_contract.py` 及悬停专项检查：目录数量、8值帧模板、上下阶段适用性；仅高度出现 U 时须影响合并 item 的规则结果及演示后验。
- [x] 更新 C# 真实后端合同：`tests/PilotAssessment.Desktop.ContractTests/SceneFramesContractTests.cs` 验证 2/6/13；旧 `A-S2-01` 输入和旧 CPT 配置明确拒绝，工作区不部分覆盖或静默丢字段。
- [x] 通过 `tools/Generate-SceneFrameExamples.py`、`Generate-SupervisorDemo.py` 重新生成当前 v3 示例与导师包；导入当前统一帧结构，生成三类悬停报告，明确新模型结构，不平均合并旧 CPT。
- [x] 更新当前指南、交接顶部及本轮验证记录；SCN-001 保持 4/14/26，全局变为 2 Task / 6 item / 20 检查点，共 28 节点，飞行 item 总数为 5。
- [x] 自动验证：运行 `.venv/Scripts/python.exe -m pytest tests/scene_assessment -q`、`dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --no-restore`、`dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj --filter FullyQualifiedName~Scene --no-restore`，记录本次实际输出。
- [x] 重建原 `scene-studio` 输出并从原桌面快捷方式启动；确认 SCN-002 两张 item 卡、定点悬停四检查点及高度参数、四份 CPT/局部曲线；导入、评估、导出回读与 Python 报告一致。

旧文件须按新模板明确重新整理：删除旧独立 item 前应把其原始高度帧按真实时间与阶段放入定点悬停帧；若不能明确对应则保留缺失并提示问题。软件本身不执行该迁移，不插值、不挑最近帧拼接、不复制高度或自动合并旧 CPT。

验收证据写入[本次验证记录](../reviews/2026-09-15-hover-item-consolidation-verification.md)，不复用上轮测试计数冒充本轮验证。
