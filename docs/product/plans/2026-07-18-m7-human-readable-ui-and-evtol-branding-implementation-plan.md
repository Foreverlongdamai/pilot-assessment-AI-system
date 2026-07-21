# M7 Human-readable UI and eVTOL Branding Implementation Plan

> **执行方式：** INLINE；本计划是已批准的轻量用户验收返修，不引入新的科学计算或重型数据测试。

**Goal:** 普通 WinUI 界面只呈现清晰语义名称，清除 fallback 标记和不必要的技术 ID，并换用统一的极简 eVTOL 产品图标。

**Architecture:** 在 Desktop Core 增加确定性 `ModelDisplayNameResolver`，让图、方案、运行与结果共享同一显示规则；exact identity 仍留在原合同和诊断区域。图标由一个项目内 master 派生所有 Windows assets。

**Technology:** .NET 10 / C# 14、WinUI 3、xUnit、内置 image generation、Pillow 资产派生。

## Task 1：记录口径并盘点展示路径

- [x] 写入补充规格与实施计划；
- [x] 确认普通显示面与诊断显示面的 ID 边界；
- [x] 确认 `.NET 10` / unpackaged WinUI x64 构建路径。

## Task 2：统一语义名称解析

- [x] 新增 `ModelDisplayNameResolver`；
- [x] Raw Input 从 source/family 解析，Evidence 从 recipe anchor 解析，BN 从 role/metadata 解析；
- [x] Task Scheme 从名称或任务语义解析；
- [x] 修改图、任务侧栏、Runs、Results、节点窗口和 BN 选择器使用统一解析器；
- [x] 删除面向用户的 fallback marker。

## Task 3：整理普通界面的技术 ID

- [x] 删除 Results Evidence/posterior 的 ID 副标题；
- [x] 普通 run/result 标题不拼接 run/result/snapshot hash；
- [x] graph tooltip 与 accessibility name 不拼接节点 ID；
- [x] 节点窗口只在默认折叠的 Technical identity 区域提供 exact identity；
- [x] Diagnostics、Provenance、Artifacts 与精确技术编辑字段保持不变。

## Task 4：生成并接入品牌图标

- [x] 生成并检查 1024 px 原创 eVTOL master；
- [x] 保存 master 到项目 Assets；
- [x] 确定性派生 `.ico` 和所有 manifest PNG；
- [x] 检查 44 px、150 px 与 256 px 视觉可读性。

## Task 5：文档、测试与真实启动

- [x] 写入 D-058/D-059、产品阅读索引和实施状态；
- [x] 更新 localization/name resolver/result projection 轻量测试；
- [x] 运行完整 Desktop Unit 与 Contract tests；
- [x] x64 Debug build 必须为 0 warning / 0 error；
- [x] 从实际 unpackaged `.exe` 启动，验证真实顶层窗口并保留运行供用户验收。

## 完成记录

2026-07-18 已完成本计划。缺失名称不显示“未命名节点”，而是由 typed node content 确定性生成简短英文语义名称；普通界面不再显示 fallback marker 或长技术 ID，精确身份仅保留在默认折叠的 Technical identity、Diagnostics、Provenance 与 Artifacts 等必要区域。原创 eVTOL master 已派生为 Windows `.ico` 与 manifest assets。

Fresh gate：Desktop Unit `95/95`、real-sidecar Contract `4/4`、x64 Debug build `0 warning / 0 error`；实际 unpackaged 前端已启动并取得非零主窗口句柄。D-055 的 canonical single-English field contract migration 仍是独立待办，本计划没有修改 Python 模型、Evidence/BN 计算或科学参数。

2026-07-19 用户验收发现窗口内图标已经生效，但 EXE、桌面快捷方式与任务栏入口仍可显示 Windows 通用图标。根因是 `.ico` 仅作为 Content 复制并由 `AppWindow.SetIcon` 在运行时读取，`.csproj` 缺少 `ApplicationIcon`，所以品牌资源没有写入 PE executable。现已增加 `ApplicationIcon=Assets\AppIcon.ico` 和项目配置回归测试，并刷新现有桌面快捷方式的显式 icon location。修复后从新 EXE 与快捷方式直接提取的 associated icon 均为项目 eVTOL 图标；当前 fresh gate 为 Desktop Unit `96/96`、real-sidecar Contract `4/4`、x64 Debug build `0 warning / 0 error`，真实应用窗口再次启动。
