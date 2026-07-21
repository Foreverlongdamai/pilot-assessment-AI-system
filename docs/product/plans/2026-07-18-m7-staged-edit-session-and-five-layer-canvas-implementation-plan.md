# M7 Staged Edit Session and Five-Layer Canvas Implementation Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-18 |
| 状态 | 已完成，engineering verified；用户验收继续 |
| 规格 | `specs/2026-07-18-m7-staged-edit-session-and-five-layer-canvas-amendment.md` |
| 决策 | D-056、D-057 |
| 开发方式 | inline、轻量验证、先合同后实现 |

## 1. 范围

本计划只返修 M7 当前编辑事务和主画布理解层。不执行 D-055 单语言数据迁移，不开始 M8 打包，也不校准 Evidence/BN/CPT。

## 2. 实施顺序

### Task 1：固化设计口径

- 新增本修订规格与计划；
- 写入 D-056/D-057，并标注 D-051/D-053/D-054 的部分取代关系；
- 更新产品文档索引和 implementation status 的当前工作项。

### Task 2：后端持久 edit session

- 新增 `ModelEditSessionManager`；
- 在项目受管目录创建独立 draft SQLite；
- 从 canonical model tables 建立／恢复基线；
- 暴露 draft workspace、status、checkpoint、undo、redo、commit、discard；
- 保存 canonical base fingerprint，并处理异常退出／基线冲突。

### Task 3：sidecar 统一路由

- current-model 读写 RPC 路由到 draft workspace；
- mutation 的 audit/idempotency/checkpoint 使用 draft database；
- 新增 `model.edit.*` 五个方法和稳定错误码；
- dirty 时阻止 preview/preflight/start；
- canonical execution services 保持不变。

### Task 4：WinUI 编辑会话生命周期

- 增加 typed edit-session contracts/gateway/client；
- 主窗口关闭前 flush 全部节点 autosave 与图布局；
- dirty 时显示 Save all / Discard all / Cancel；
- Cancel 保持所有窗口打开；成功 save/discard 后再关闭节点窗口、sidecar 和主窗口；
- 保存失败或冲突时保持应用打开并显示本地化错误。

### Task 5：全局 undo/redo 与长按拖动

- Model Studio 增加 Ctrl+Z/Ctrl+Y；
- undo/redo 后刷新 task list、graph 和已打开节点窗口；
- GraphNodeButton 使用约 350 ms 长按阈值进入拖动；
- 保留单击、双击和空白画布平移。

### Task 6：五层 projection/filter/layout

- 新增 `GraphDisplayLayer`；
- projection 按五层分类，Raw Input Family 不再始终显示；
- 移除 Model Studio 的细粒度 tag/kind 顶层筛选，改为单一层级筛选；
- 使用固定 per-layer render offsets；
- 保持 canonical BN arrow 方向和 reversible layout persistence。

### Task 7：轻量验证与交付

- Python focused：draft/canonical 隔离、undo、commit、discard、dirty run guard；
- C# focused：五层筛选、固定 lane、family visibility、offset round-trip、RPC serialization；
- `git diff --check`、定向 Python lint/type、focused .NET tests；
- x64 Debug build；
- 启动真实 WinUI、确认 sidecar 与窗口可用，并将应用留给用户验收。

## 3. 非目标

- 不创建新的业务 Draft/Published/Publish 状态；
- 不把草稿用于 assessment run；
- 不把 operator 放到主画布；
- 不反转 BN canonical DAG；
- 不新增重量级大数据测试；
- 不修改 starter 算法以追求科学有效性。

## 4. 完成门

只有 Task 1–7 均完成且真实应用成功启动后，才能称本次 M7 返修工程完成；用户手工验收仍是 M7 最终接受门。

## 5. 完成证据（2026-07-18）

- Python edit-session/runtime/sidecar focused：`6 passed`；
- desktop Unit：`90 passed`；
- real-sidecar Contract：`4 passed`，包含 dirty status、显式 commit 后 preflight/run 与 reopen replay；
- targeted Ruff lint/format 与 `ty check`：通过；
- x64 Debug build：`0 warning / 0 error`；
- 真实 `PilotAssessment.Desktop.exe` 已启动并获得非零主窗口句柄。

上述证据关闭本计划的工程门，但不关闭 M7 用户验收，也不实施 D-055 或任何 M8 内容。
