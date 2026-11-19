# SCN-001场景计算器：开发版验证记录

日期：2026-09-07。范围：六item独立结果型计算器、新默认WinUI场景工作区及两端协议。本记录证明软件在所列边界内按规则工作，不是数值阈值验证或便携发布完成记录。

## 自动检查

| 检查 | 结果 |
|---|---|
| `pytest tests/scene_assessment tests/sidecar/test_framing.py tests/sidecar/test_dispatcher.py -q` | 50 passed；45个新场景测试与5个已有协议回归 |
| `dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo` | 127 passed，0 skipped，0 failed |
| `dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo` | 5 passed，0 skipped，0 failed；含真实Python→SceneGateway→C#完整目录与全D计算 |
| `dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --nologo` | 成功，0警告、0错误 |
| 新Python模块及测试的Ruff lint和format | 通过，8个Python文件格式一致 |
| 空白示例模板与运行时目录比较 | 一致，27参数行、30唯一结果字段，输入全部null |
| `Start-SceneAssessment.ps1` PowerShell语法解析 | 通过 |
| `git diff --check` | 通过；已有DECISIONS文件出现换行提示，未改其内容 |

测试覆盖闭区间、严格嵌套、期望值、非法类型/非有限数值、无上限与缺参区别、最差档、0/false事实、缺值不补0、共享末端保持、未发生保持的航向缺值豁免、编辑取消、参数/输入变更清旧报告、快照深复制和文件往返。

真实协议测试发现并修复了dispatcher附加`trace_id`与严格DTO不兼容的问题。现仅响应对象接纳trace_id，配置与输入仍拒绝未知属性。非法NaN/Infinity被stdio拒绝，进程仍可正常关闭。独立后端测试未创建旧数据库或模型seed。

## 实际Windows窗口检查

以新默认入口启动本机Debug x64程序，获得真实窗口后完成以下检查：

- 主窗口成功连接新计算器，显示“场景已就绪”和全部六个item。
- 实际点击“起飞前检查”，打开包含检查内容、空参数、D/A上下界、无上限复选框和来源链接的编辑器。
- 对全空参数点击应用，弹窗保持打开，逐区域显示缺项提示。
- 点击取消，弹窗关闭，没有产生未保存参数修改。
- 正常关闭主窗口，进程退出；没有遗留该测试进程的后端子进程。

实际截图：[主界面](assets/scene-calculator-2026-09-07/main-window.png)、[item编辑器](assets/scene-calculator-2026-09-07/item-editor.png)。

本轮没有逐一手动走完Windows文件选择器的所有保存/导入/导出操作；文件JSON往返和完整评估由自动合同测试覆盖。未使用真实学员或样例飞行数据，未新增或安装依赖。

## 历史边界与交付状态

业务新增集中在独立scene包、Desktop.Core场景模块、新窗口及启动分路。旧已发布schema、旧数据库、模型和运行记录未迁移。DECISIONS.md的SHA-256仍为`70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`，与开工前一致。

当前交付是本地可运行开发版，启动方式见[使用指南](../SCENE_CALCULATOR_GUIDE_CN.md)。旧工作台可通过`--legacy-workbench`进入；本轮未重新发布便携包、未推送远端。
