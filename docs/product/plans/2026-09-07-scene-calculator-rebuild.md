# Scene Calculator Rebuild Implementation Plan

**Goal:** 在现有Windows软件中交付SCN-001六item的参数编辑、JSON结果导入、D/A/U与P/F计算及结果导出。

**Architecture:** 同仓独立场景目录和Python纯计算器，独立scene RPC入口，WinUI新默认窗口；复用基础传输和运行环境，保留旧工作台入口。

**Tech Stack:** existing Python 3.11/.venv/pytest/ruff, .NET 10/WinUI 3/xUnit, JSON-RPC 1.0。

共享合同、字段形状和校验规则见[实施规格](../specs/2026-09-07-scene-calculator-rebuild.md)。用户已确认场景并授权coding，本计划直接执行，不另设开工审批。

## 1. 场景目录（主代理）

- [x] 建立`src/pilot_assessment/scene_assessment/scn001.json`，逐一录入六item的30个唯一结果字段、19个检查点及来源；不填容差数字。
- [x] 核对目录与六份方法稿的字段、共享时长、来源标签和短路条件。

## 2. Python内核和RPC（core_rebuild_audit）

- [x] 新建`tests/scene_assessment/test_calculator.py`：闭区间端点；非法/空配置；数值类型；最差档；缺值不等于0；0/false短路；共享时长；快照不受修改影响，先运行观察失败。
- [x] 实现`scene_assessment/catalog.py`、`calculator.py`及最小合同校验，目录由包内JSON读取，RPC返回规格中的稳定形状。
- [x] 新建`__main__.py`与stdio服务，复用dispatcher/framing，不创建旧SystemApplication；测试hello/catalog/evaluate/shutdown真实往返。
- [x] 运行`.venv/Scripts/python.exe -m pytest tests/scene_assessment -q`与新目录ruff检查，处理所有实际失败。

## 3. Desktop.Core（独立代理）

- [x] 新建`SceneAssessment/`下DTO、Gateway、配置编辑模型和workspace状态；RPC DTO显式snake_case，独立于旧RunResult/BN模型。
- [x] 单元测试先验证模板空值、共享参数、取消不写入、输入/参数变化清除旧结果、参数/输入/报告JSON往返。
- [x] 实现调用catalog、validate_configuration、evaluate的gateway；不重复实现Python评分算法。
- [x] 运行`dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo`。

## 4. WinUI流程（desktop_rebuild_audit）

- [x] 新建`Views/SceneAssessmentWindow.xaml(.cs)`与编辑器，左侧场景、右侧item卡片及结果详情；点击item编辑每个数值对应参数。
- [x] 新场景backend连接选择`pilot_assessment.scene_assessment`入口并要求`scene.assessment.v1`能力；旧连接要求不变。
- [x] 修改`App.xaml.cs`默认启动新窗口，只有`--legacy-workbench`进入旧启动流程。
- [x] 实现配置JSON保存/加载、输入模板导出、输入导入、计算、结果导出与错误提示；未保存编辑有明确处理。
- [x] `dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --nologo`。

## 5. 集成验证与交接（主代理）

- [x] 审查代理改动与新RPC/Desktop合同一致，运行新Python、Desktop.Core及针对协议的回归测试。
- [x] 检查`git diff --check`、新代码lint、WinUI构建，完成启动检查；不读取真实样例飞行数据。
- [x] 写用户操作文档和本地启动脚本，更新阶段README、产品handoff的当前状态；参数标定状态与实际软件实现状态分开记录。
- [x] 保护DECISIONS.md已有改动及旧immutable schema；不提交或推送与任务无关内容。
