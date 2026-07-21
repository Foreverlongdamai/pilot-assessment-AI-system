# M7 Staged Edit Session and Five-Layer Canvas Amendment

| 字段 | 值 |
|---|---|
| 设计基线 | M7 v0.3 amendment |
| 日期 | 2026-07-18 |
| 状态 | 已批准，进入实施 |
| 上游 | M7 WinUI Expert Designer and Task Activation Workspace Design；M7 Raw-Input Provenance Amendment |
| 决策 | D-056、D-057 |
| 科学状态 | 不改变 starter Evidence、BN、CPT 或 `formal_run_authorized=false` |

## 1. 目的与取代关系

本修订收口本轮 M7 手工验收确认的两项产品语义：

1. 专家在一次应用会话中的节点、边、参数、CPT、任务方案和布局修改先写入 **后端受管的持久临时草稿**，不实时覆盖正式模型；
2. 主画布和筛选统一为五个理解层级：`Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency`。

本修订仅取代下列旧口径：

- M7 主规格中“每次 autosave 直接成为 canonical current object”的提交时机；
- D-051 中“autosaved current object 可随时直接运行”的 autosave 部分；
- D-053 中“每次前端 mutation 立即写 canonical definitions”的提交时机；
- D-054 中“五个输入族无条件始终显示”和“所有 canonical 节点统一平移”的展示细节；
- Raw-Input Provenance Amendment §2.1、§4.1、§4.3、§6.3、§8、§9.1 中与上述旧口径相冲突的句子。

以下原则继续有效：没有 Draft/Published/Apply/Publish 业务生命周期；全部计算逻辑仍由 Python backend 执行；前端每项编辑仍一一映射为 typed backend operation；正式运行仍冻结 immutable `RunSnapshot`。这里的“临时草稿”只是一次编辑会话的技术事务边界，不是可切换的业务版本。

## 2. 权威状态模型

```text
Python canonical workspace
        |
        | open/rebase
        v
backend-managed edit session (durable SQLite)
        |
        | typed node/edge/CPT/scheme/layout mutations
        | validation + global undo/redo
        v
WinUI current editing view

Close -> Save all    -> one atomic canonical commit -> close
Close -> Discard all -> delete/rebase edit session  -> close
Close -> Cancel      -> keep edit session and app open
```

### 2.1 Canonical workspace

- 只保存上一次用户明确确认过的正式 ModelNode、TaskScheme 和关系；
- assessment/preview/run 只能使用 canonical workspace；
- `run.start` 的 immutable snapshot 语义不变；
- 不因节点窗口关闭、字段离焦、拖拽结束或 autosave debounce 而修改。

### 2.2 Edit session

- 每个打开项目最多存在一个当前 edit session；
- edit session 位于受管项目存储中，并使用独立 SQLite 数据库，不污染 canonical 表；
- 打开项目时从 canonical workspace 建立基线；若上次异常退出留下与同一 canonical 基线兼容的 dirty session，则恢复它；
- 所有 Model Studio 读写、浮动节点窗口、任务侧栏、图操作、CPT 编辑和布局编辑都读取／修改 edit session；
- Python backend 在草稿上继续执行 DAG、CPT、schema、binding、revision 和 domain validation；C# 不复制计算或验证实现；
- 每次成功 mutation 生成一个持久全局 checkpoint，供应用级 Ctrl+Z/Ctrl+Y 使用。

### 2.3 关闭语义

主窗口关闭时必须先把所有 debounce 中的前端输入 flush 到 backend edit session，然后读取 edit-session status：

- 无改动：直接关闭；
- 有改动：显示三个明确选项；
  - **保存全部并关闭**：将 edit session 相对基线的最终差异在一个 canonical transaction 中提交；全部成功后关闭；
  - **放弃全部并关闭**：丢弃 edit session，canonical workspace 保持逐字不变，然后关闭；
  - **取消**：不关闭窗口，不提交也不丢弃任何 edit-session 内容。

单独关闭节点浮动窗口只 flush 到 edit session，不弹出整项目保存对话框，也不提交 canonical workspace。

### 2.4 原子提交、冲突与恢复

- edit session 记录 canonical `base_fingerprint`；
- Save all 前重新计算 canonical fingerprint。若基线已由另一个进程改变，拒绝提交并保留草稿，不能静默覆盖；
- 一次 Save all 使用一个稳定 `transaction_id` 和同一个 SQLite transaction；任何节点、方案或关系失败时 canonical workspace 全部回滚；
- 同一对象在会话内的多次编辑折叠为一次最终 canonical revision 变化；历史运行快照不改写；
- commit 成功或 discard 后，backend 立即从新 canonical 状态重建干净 edit session；
- 异常退出不会自动视为“保存”，下次打开同一项目时恢复兼容草稿。

### 2.5 Undo/redo

- `Ctrl+Z` 撤销当前 edit session 最近一次成功的模型工作区 mutation；
- `Ctrl+Y` 可恢复最近一次被撤销的 mutation；
- undo/redo 包含节点定义、边、CPT、任务激活和布局，不跨过本次 edit-session 基线；
- undo 后再产生新 mutation 时删除 redo 分支；
- 文本框自身获得输入焦点且可执行原生文字 undo 时，优先执行文本框 undo；画布／工作区焦点下执行全局 edit-session undo。

### 2.6 Dirty run guard

当 edit session dirty 时，`model.preview.node`、`model.preview.scheme`、`model.run.preflight` 和 `model.run.start` 不得静默使用草稿或过期 canonical 模型。M7 首版统一返回稳定的 `MODEL_EDIT_SESSION_DIRTY` 错误，前端提示用户先“保存全部”或“放弃全部”。

## 3. 五层画布语义

### 3.1 唯一顶层分类

| 层级 | 内容 | canonical 状态 | 默认视觉 |
|---|---|---|---|
| Raw Input Family | 五个 X/U/I/G/P 投影根 | 非 canonical UI projection | 较大绿色圆形 |
| Extracted Data | 现有细粒度 Raw Input `ModelNode` | canonical | 蓝色圆形 |
| Evidence | Evidence `ModelNode` | canonical | Evidence 主题色 |
| Sub-skill | 非 AggregateCompetency 的 BN `ModelNode` | canonical | BN 子技能主题色 |
| Competency | `BnNodeRole.AggregateCompetency` | canonical | 聚合能力主题色 |

Model Studio 的“层级”筛选只能使用以上五项与“全部”。`evidence.O1`、source tag、group tag 等技术标签不再充当主画布的顶层分类。任务方案侧栏自己的任务标签筛选不受影响。

### 3.2 固定从左到右布局

默认投影 lane 必须稳定为：

```text
Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency
```

BN canonical 生成方向仍是 `Competency -> Sub-skill -> Evidence`。因此紫色概率边在该理解型布局中可以从右向左指向，绝不能为了视觉方向而反转 parent、CPT 或 DAG 语义。

每类 canonical 节点使用确定的 render-only lane offset。拖动保存时扣除该节点所属层的 offset，避免累计漂移。筛选不得改变节点的投影坐标。

### 3.3 筛选行为

- “全部”显示五层及其可见关系；
- 选择 Raw Input Family 时只显示五个族根；
- 选择 Extracted Data、Evidence、Sub-skill 或 Competency 时，不再强制显示五个族根；
- 仅在两端都可见时绘制 edge；
- active/dim、搜索、group 和 view mode 在层级筛选结果上继续组合；
- operator 继续只在节点浮动窗口显示，不成为主画布层级或节点。

## 4. 画布交互

- 快速单击：选择节点；
- 双击：打开／聚焦该节点浮动窗口；
- 按住约 350 ms 后移动：进入节点拖动，释放时把新位置写入 backend edit session；
- 未达到长按阈值的轻微移动不能误触拖动；
- 空白画布拖动继续平移视野；滚轮／缩放和 Fit 继续有效；
- 所有未保存修改统一由主窗口关闭对话框管理。

## 5. JSON-RPC 增量

新增稳定方法：

- `model.edit.status`
- `model.edit.undo`
- `model.edit.redo`
- `model.edit.commit`
- `model.edit.discard`

现有 `model.node.*`、`model.scheme.*`、`model.graph.*`、`model.edge.*`、`model.layout.update` 与 `model.cpt.*` method 名称不变，但在已打开项目中路由到 edit session。响应仍返回 backend 生成的完整对象／graph snapshot 和 revision。

## 6. 验收条件

1. 修改节点后直接读取 canonical repository，正式对象不变；读取 Model Studio 时能看到草稿值；
2. 异常关闭后重开同一项目可恢复兼容草稿；
3. Ctrl+Z 能撤销最近一次图／表单修改并刷新所有相关窗口；
4. Save all 将最终差异原子提交，canonical 对象只增加一次相应 revision；
5. Discard all 后 canonical hash 与打开应用时一致；Cancel 后应用和草稿保持打开；
6. dirty session 下 preview/preflight/run 被明确阻止；clean session 下继续走既有 RunSnapshot 路径；
7. 层级筛选只有五类；选择非 Raw Input Family 时五个绿色根不会强制出现；
8. 默认物理顺序严格为五层从左到右，BN 紫色箭头保持 canonical 方向；
9. 节点需长按后才能拖动，快速单击与双击行为不退化；
10. 轻量 Python focused tests、C# projection/contract tests、x64 Debug build 和一次真实 WinUI 启动通过。

这些验证只证明事务、交互和计算工作流一致，不证明 starter Evidence、BN 或 CPT 科学有效。
