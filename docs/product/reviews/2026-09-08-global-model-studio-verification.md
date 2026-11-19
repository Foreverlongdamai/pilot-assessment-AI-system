# 全局 Model Studio 验证记录

日期：2026-09-08。范围：场景目录注册、全局图投影、多场景编辑状态、WinUI 导航与 CPT 编辑。未使用真实学员或样例飞行数据，六项原有分档与贝叶斯算法保持。

## 自动验证

| 检查 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/scene_assessment tests/sidecar/test_framing.py tests/sidecar/test_dispatcher.py -q` | 139 passed |
| `dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo` | 144 passed |
| `dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo` | 5 passed |
| Ruff check 和 format --check：scene 包及其测试 | 通过 |
| PowerShell 启动脚本语法解析 | 通过 |
| `git diff --check` | 通过；原有 DECISIONS 换行提示，未改其内容 |

合计 288 项测试通过。新增覆盖：目录发现与未知场景拒绝、旧无参目录接口兼容、两场景重复 item ID 隔离、节点和边唯一性、图投影不伪造等级或分数、编辑状态及报告保留。真实 Python/C# 协议验证当前目录包含 SCN-001，图有 26 个节点、19 条贝叶斯边和 6 条归属边；六项原有 BN/EAP 和 P/F 合同仍通过。

WinUI 最终构建成功，0 警告、0 错误；使用 .NET SDK 10.0.302、Debug x64，独立输出到 `src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/`。命令：

```powershell
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 '-p:OutDir=C:/Users/long/Desktop/CranfieldOffer/proj/pilot_assessment_system/src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/' --nologo
```

初次沿用旧输出目录时，原用户窗口占用 DLL 导致复制失败，因此改用独立输出目录；未关闭或操作用户原来的编辑弹窗。启动脚本也指向独立目录。

## 实际窗口验证

在真实 WinUI 窗口完成以下操作：

1. 默认进入 Model Studio，左侧顶端为总图、下方为 SCN-001；显示 1 个场景、6 个 item、19 个检查点，以及三列布局、虚实连线和图例。
2. 点击“电池与供电区”检查点，右侧显示该点 3×3 CPT；打开编辑器只出现该点的概率表，没有其他检查点或先验输入框。
3. 将低状态行 D 概率从 0.1 临时改为 0.15，点击应用；后端提示该行概率和必须为 1，编辑器保留输入，未提交错误模型。
4. 将同一行 U 概率从 0.65 改为 0.60，再应用成功。右侧 CPT 更新为 0.15 / 0.25 / 0.60，场景出现未保存修改标记。所有检查区间仍为空，证明模型编辑独立于容差填写。
5. 切换到场景页、打开“起飞前检查”、展开贝叶斯技能量化，实际看到同一行 0.15 / 0.25 / 0.60，并保留先验与状态分值。取消此编辑器返回场景页。
6. 关闭测试实例时显示保存、放弃、取消提示；选择放弃本次临时测试修改，不写入用户配置或产品演示参数。
7. 最终构建后重新启动，确认干净配置与工作区就绪；点击“适应全图”，在同一视图看到 Task、6 个 item 与 19 个检查点的完整关系。

临时数值仅用于软件验证，不是推荐 CPT。本轮没有再次执行系统文件选择器的导入/导出完整交互；相关 JSON 与真实协议由测试覆盖。多场景隔离使用测试目录验证，目前产品只发布一个真实场景。此记录不声称未来场景已经设计完成，也不声称已完成全部窗口交互测试。

## 保留边界

Task 仍按规则给出 D/A/U 和 P/F，没有 Task CPT 或场景技能总分。画布的 Task→item 虚线只表达归属；各 item 的贝叶斯网络独立。模型概率与分值未校准，不更改官方依据或用户手填阈值。

`DECISIONS.md` SHA-256 保持 `70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`。保留原有未提交修改、旧工作台及历史数据。没有提交、推送或制作便携发布包。当前入口见[使用指南](../SCENE_CALCULATOR_GUIDE_CN.md)与[实现规格](../specs/2026-09-08-global-model-studio.md)。
