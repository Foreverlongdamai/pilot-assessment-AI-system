# 悬停合并：桌面构建与原生验证

日期：2026-09-15。验证的是原桌面快捷方式指向的 WinUI 程序。

## 构建

原 PID 44444 的界面没有“有未保存修改”标记或编辑对话框，正常关闭后构建；未强制结束未保存工作。

执行命令：

```powershell
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 -p:OutDir=C:/Users/long/Desktop/CranfieldOffer/proj/pilot_assessment_system/src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/ --no-restore --nologo --verbosity quiet
```

构建工具输出记录：

```text
已成功生成。
    0 个警告
    0 个错误

已用时间 00:00:14.90
```

## 自动验证

- C# 单元测试 247 / 247 通过。
- C# 场景合同测试 10 / 10 通过，连接真实 Python 后端，其中六个案例使用本次再生的演示配置、输入和报告。
- 新增旧 item / 旧 CPT 结构报错文案回归，最初 3 项失败，修正文案后通过；拒绝导入时保留当前工作区和已有报告。
- 实际 SCN-002 合同验证 2 个 item、6 个检查点、13 个原始指标；A-S2-02 下四个 CPT，含 -04 悬停高度保持。
- 参数编辑草稿包含上下悬停高度；水平速度归入水平位置、垂速归入高度、航向独立。

## 原生窗口验证

从原快捷方式启动，最终 PID 29576。

1. 加载新 SCN-002 配置及 03-unqualified.input.json，实际评估 complete / U / Fail。
2. 场景页显示“定点悬停保持”，不再显示独立 A-S2-01 item。
3. 实际导出输入模板和报告。模板含两个 item，高度原始量位于 A-S2-02 同一组帧。报告含四个悬停检查点、四项模型证据，以及高度的局部时序结果。
4. Model Studio 有“水平位置保持 / 悬停高度保持 / 航向保持 / 激光指向保持”四个检查点节点。
5. CPT 编辑器中上述四组高技能 U 概率均读取为 0.001；没有自动生成或合并旧模型参数。
6. 同一 item 的参数编辑器显示下方与上方悬停高度字段。
7. 导入含旧 A-S2-01 的输入时显示新模板与禁止自动合并提示，已有可导出的报告保留。
8. 最终重新评估当前有效输入，窗口停留在悬停高度保持的局部曲线。native-height-curve-final.png 为实际截图，已目视核对。

导出回读比较是结构与数值比较，不是逐字节比较：C# 会省略可空字段 minimum_frame_count:null；当前输入、配置和实际判定/量化数据保持一致。

原生 QA 脚本首次暴露其自身异步等待不足：需等待“报告已导出”后再读文件，并在关闭对话框后等动作可用。脚本已调整并完整复跑通过；这些是测试工具竞态，不是产品错误。

## 证据

- VerifyNativeHoverMerge.ps1：完整主流程。
- native-export-input-template.json：原生导出的当前模板。
- native-export-report.json：原生导出的当前报告。
- model-studio-ui.json：合并后画布控件树。
- four-cpt-editor-ui.json：四 CPT 的控件树。
- height-parameter-editor-ui.json：同一 item 的上下高度参数入口。
- old-item-rejection-ui.json：旧输入拒绝提示和现有报告保留。
- final-visible-ui.json / native-height-curve-final.png：最终实际窗口。
