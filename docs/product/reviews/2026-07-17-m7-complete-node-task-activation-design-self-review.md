# M7 Complete-Node / Task-Activation Design Self-Review

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-17 |
| 审查对象 | M7 WinUI Expert Designer and Task Activation Workspace Design |
| 审查类型 | 跨文档语义、可实现性、历史兼容与用户讨论逐项核对 |
| 结论 | 书面设计已获用户确认；M7 roadmap、M7A 与 M7B implementation plans 已编写，代码尚未实现 |

## 1. 已核对的用户口径

| 已确认口径 | 书面落点 | 结论 |
|---|---|---|
| 每个节点只有一个完整当前定义 | M7 §3、D-047 | 已覆盖 |
| Task-specific 差异使用复制后的新节点 | M7 §3/§6、D-047/D-050 | 已覆盖 |
| 同一节点可被多个任务共享 | M7 §4.1、D-048 | 已覆盖；修改影响未来 runs |
| 任务只选择启用哪些完整节点 | M7 §4、D-048 | 已覆盖 |
| active 亮、inactive 暗 | M7 §4.4/§7、D-052 | 已覆盖 |
| 启用 child 自动启用 fixed parents | M7 §5.1、D-049 | 已覆盖；无提示 |
| 停用 parent 时列出下游并继续/取消 | M7 §5.2、D-049 | 已覆盖；原子级联 |
| 默认复制节点、不复制 parents | M7 §6.1、D-050 | 已覆盖 |
| 复制方案立即加入左侧并可编辑 | M7 §6.3、D-050 | 已覆盖 |
| 多个可移动/缩放/最大化浮动节点窗口 | M7 §8、D-052 | 已覆盖 |
| CPT/graph 修改真实落到后端 | M7 §9/§11、D-053 | 已覆盖 |
| 中英文切换 | M7 §13、D-052 | 已覆盖 |
| 取消 Draft/Published/Apply/Publish | M7 §10、D-051 | 已覆盖 |
| 历史可复现由 run snapshot 保证 | M7 §10.3、D-051 | 已覆盖 |
| 普通编辑不需要 Python plugin | M7 §11、D-053 | 已覆盖 |

## 2. 发现并关闭的主要冲突

### 2.1 M5 同 concept 多版本 vs 完整独立节点

旧 M5/D-036 允许 Hover 与 Straight 选择同一 concept 的不同 immutable versions；这与用户最终确认的 `Precise`、`hover.Precise`、`straight.Precise` 是三个独立节点冲突。

处理：D-047 明确取代 task-specific parallel-version UX；旧 records 只作 migration/replay。M7 migration 把不同功能定义物化为不同 `node_id`，不在同一圆形节点中切换版本。

### 2.2 Draft/Publish vs 并列可编辑任务方案

旧 D-033/M5/M6 要求 draft → apply/publish → run。用户已确认所有方案本来就是左侧可切换、可编辑的并列对象，发布状态没有必要。

处理：D-051 取消正常 UI 的 Draft/Published/Apply/Publish；运行开始时自动冻结 RunSnapshot。Change journal 保留 undo/audit，但不变成业务版本列表。

### 2.3 “前端修改后端代码”可能被误解为改写 Python

用户要求前端新增、复制、修改节点后真实改变后端计算；如果理解成生成或改写 `.py`，会引入任意代码执行和双重逻辑。

处理：M7 §11/D-053 将 EvidenceRecipe、parameters、parents、states 和 CPT 定义为后端 canonical executable definitions；通用 Python engine 执行这些定义。只有缺少新 operator capability 时才安装 trusted plugin。

### 2.4 Edge 与完整节点的归属

若任务方案独立保存 edges，同一节点可能在不同任务拥有不同 parents，违反“parent 不同就是两个节点”。

处理：两类 edges 都从 child 完整定义投影；TaskScheme 只激活节点，不能 override parent/CPT。Add/remove edge 是 child-node update，并与 CPT migration 原子提交。

### 2.5 任务画布 Delete 的歧义

全局共享节点若在一个任务中直接物理删除，会破坏其他任务。

处理：任务画布 Delete 默认表示当前方案停用；全局归档是 Library 独立操作。被方案或 RunSnapshot 引用的节点不物理删除。

## 3. BN 与 Evidence 语义核对

- Evidence 的 **data parents** 只闭合到 Raw Input 类别（X/U/I/G/P 及其 typed task resources）；
- Evidence/BN 的 **probabilistic parents** 定义 child CPD/CPT；
- Starter canonical BN 保持 `Competency → Sub-skill → Evidence`；
- 运行先由 raw data 提取 Evidence，再观察 Evidence 计算 posterior；
- inference overlay 只读，不反转 canonical BN edges；
- 差表现继续产生 `computed + Unacceptable`，不由 M7 重新引入 quality gate。

结论：D-037/D-038 与 D-047–D-053 可以同时成立，没有把程序计算顺序错误画成 BN 生成方向。

## 4. 实现现实核对

当前代码已经完成的是 M5/M6 immutable versions、draft/publish、published-scheme run lock、managed project/session/artifact、BN inference 与 stdio sidecar。当前代码**尚未**完成：

- current `ModelNode` / mutable `TaskScheme` persistence；
- active closure 与 cascade disable；
- node-only copy/paste 和 scheme copy 的新合同；
- run-from-current-scheme automatic snapshot；
- 新 sidecar methods；
- .NET client、WinUI shell、Model Studio、floating windows 和 bilingual UI。

因此文档明确区分“规格已批准、计划已编写”和“代码尚未实现”。M7A plan 先做 backend compatibility/current-model slice，关闭其运行快照与 sidecar 门后，M7B plan 才进入 WinUI。

## 5. 轻量工程验证建议

实施阶段只需要验证平台不变量，不为 starter 科学内容建立重型 golden：

1. 一个 5–8 节点 micro graph 验证 enable closure、disable cascade 和 task isolation；
2. 一个 Evidence 与一个 BN node 验证 node-only copy 保持 parent references；
3. 两个 schemes 共享一个 node，验证修改影响未来 run、旧 RunSnapshot 不变；
4. 一次 parent/CPT atomic migration 与 rollback；
5. 一个 sidecar current-object autosave/run snapshot smoke；
6. 一个 WinUI contract smoke 验证多个浮窗收到 canonical save/conflict state；
7. 中英文切换只验证 resource/model metadata，不比较科学输出。

不生成四套长 session、万行级多模态数据或 18 个 Evidence 科学 golden。

## 6. 剩余非阻塞选择

- 具体 JSON-RPC method names、SQLite table migration 和 .NET graph-control 技术选型留给实施计划；
- 跨项目节点复制/merge 留给 M8/未来版本；M7 copy/paste 限于同一受管项目；
- 节点默认布局采用 global base + per-scheme overrides，实施时可根据画布性能细化，但不得改变 complete-node/activation 语义。

上述选择不会改变用户已经确认的产品模型。

## 7. 自审结论

设计内部一致，已明确覆盖用户本轮全部决定，并保留 M1–M6 的可重放工程资产。用户已完成书面规格复核；对应 [M7 roadmap](../plans/2026-07-17-m7-winui-expert-designer-implementation-roadmap.md)、[M7A plan](../plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md) 与 [M7B plan](../plans/2026-07-17-m7b-winui-expert-designer-implementation-plan.md) 已形成。下一步按 M7A → M7B INLINE 执行；不能沿旧 Draft/Publish UI 实施，也不能提前开始 M8 packaging。
