# 06 可视化 Evidence 与贝叶斯网络图编辑器设计

## 1. 文档状态与目标

- 文档版本：1.0
- 目标前端：Windows WinUI
- 对应后端模型：autosaved model workspace + immutable applied revisions
- 核心要求：用户可以在前端分别编辑 Evidence Computation Graph 与 BN Graph；所有 recipe、operator 参数、结构和 CPT 修改必须一一映射到后端 canonical model。

本设计明确取消“v0 只读拓扑”边界。v0 前端允许编辑两张图；draft 每次修改自动保存，用户点击“应用到后续评估”时只需通过最小技术可运行校验。前端不是模型事实来源；后端保存的 canonical `EvidenceRecipe`/BN draft 才是模型事实来源。`publish`、`published revision` 和 `publish validation` 是旧界面术语，当前分别统一为 `apply`、`applied revision` 和 `technical apply validation`，不代表审批流程。

> **当前权威：** [Expert-Editable Evidence and Assessment Model Design](./specs/2026-07-15-expert-editable-evidence-and-model-design.md)。本文件原有 BN 事务细节继续作为设计材料；与“逐次确认、needs_review、强制发布审核”冲突的表述均由 autosave + one-click apply 取代。

## 2. 用户体验

### 2.1 画布能力

WinUI 图编辑器至少支持：

- 平移、缩放、框选和多选；
- 从节点工具箱拖入新节点；
- 拖动节点位置；
- 从输出端口拖线到目标节点以新增 edge；
- 选择 edge 后删除；
- 删除一个或多个节点；
- 修改节点名称、说明、状态、类型和显示样式；
- 打开节点属性面板查看或编辑 prior、CPT 和生成器参数；
- 按 phase 查看 AnchorResult 与聚合明细；只有未来显式 unrolled profile 才显示 phase-specific CPT；
- 切换完整语义图与按 competency/node type 过滤的紧凑视图；两者都引用同一组 canonical nodes；
- 显示 pending、incomplete、invalid、executable、applied 等技术状态；
- 查看每次操作造成的 graph diff、CPT migration 和 validation 结果。

节点位置属于 layout 数据，不改变概率语义；节点、边、状态和 CPT 属于 model 数据，必须提交后端事务。

### 2.2 Guided 模式

Guided 模式服务于一般研究人员和专家，提供以下限制与辅助：

- reference-model-v0.1 palette 只使用 competency、subskill/latent、evidence/anchor 三类节点；context 是 BN 外 session metadata，derived evidence 通过 binding metadata 表达；
- 根据节点类型限制可创建 edge；
- 新增 edge 时打开 CPT 初始化向导；
- 删除 edge 或 node 前显示 CPT 迁移预览；
- 以 ranked-node 参数编辑为主；
- 自动提示孤立节点、无 evidence path 和不完整 CPT；
- 偏离 starter profile 时显示清晰 warning，但允许作为 expert model apply。

Guided 模式默认 edge 规则：

| Source | Target | 默认允许 |
|---|---|---|
| competency | subskill | 允许 |
| subskill | evidence | 允许 |
| context | 任意节点 | reference-model-v0.1 禁止 |
| evidence | derived_evidence | reference-model-v0.1 禁止，使用 `likelihood_strength` |
| 其他组合 |  | 禁止或要求切换 Advanced 模式 |

### 2.3 Advanced DAG 模式

Advanced 模式面向模型设计人员：

- 可以增加 generic_latent 和 generic_observed 节点；
- 可以创建任意有限离散 DAG edge；
- 可以手工编辑完整 CPT；
- 可以删除或替换默认 competency、subskill 和 evidence；
- 可以改变节点状态数量；
- 可以创建不符合默认三层语义的研究 draft。

Context node 与 structural derived-evidence edge 只要在当前 draft 中明确声明状态、CPT、编译和推理语义即可启用。它们会使 draft 偏离 starter snapshot，但不会要求人工创建 major model profile；apply 自动生成新 revision identity。

Advanced 模式仍然不能绕过以下硬约束：

- 不允许 self-loop；
- 不允许 duplicate edge；
- 不允许 directed cycle；
- 已提供的 CPT 必须与 parent order 和 cardinality 一致；
- 已提供的概率必须合法；
- 只有 compile 成功的 draft 才能成为 draft_executable；incomplete/invalid draft 仍会 autosave，但不能 preview 或 apply。

若 Advanced draft 删除 TCP、PC、SM、OC 或改变输出契约，它不再等同于原 starter snapshot，但仍可作为新的 expert model apply。系统自动记录 structured diff 和新 revision identity，不要求专家恢复默认节点或手工提升 major version。

## 3. 后端权威模型

### 3.1 Stable ID

每个 revision、draft、node、edge、CPT、anchor binding 和 transaction 都使用 stable ID。Stable ID 不从可编辑名称生成。Reference model 现有的 O1、TCP.1 等 immutable IDs 保持兼容；前端为新增 node、edge、binding 和 transaction 生成 UUIDv4，后端验证唯一性并在 canonical response 中原样确认。revision_id 和 draft_id 由后端签发。

节点重命名不得改变：

- node_id；
- edge endpoints；
- CPT parent references；
- audit history；
- 已保存 inference trace。

Edge ID 固定使用独立 UUIDv4；后端另以 unique(source_node_id, target_node_id) 约束拒绝 duplicate edge，不从 endpoints 派生 edge_id。

### 3.2 Canonical draft

前端打开模型时，后端返回：

- model_id；
- draft_id；
- base_revision_id；
- graph_version；
- layout_version；
- canonical graph；
- CPT 与 generator metadata；
- validation 状态；
- draft content hash。

前端不能直接修改 YAML、JSON 或本地数据库。所有 model 变更都通过后端 transaction。后端提交成功后返回的新 canonical graph_version 才能成为前端新的 committed state。

### 3.3 Draft graph version

graph_version 是 draft 内单调递增整数。每个事务请求必须携带 expected_graph_version。

尽管名称保留为 graph_version，它版本化的是整个 semantic draft：node、edge、state、CPT、anchor binding、anchor parameters 和 profile。任一语义修改都在同一原子 transaction 中使 graph_version 加一；v0.1 不另设可独立覆盖的 parameter version。各组件 hash 只用于 diff、cache 和 provenance。纯 layout 修改使用独立 layout_version。

若：

expected_graph_version ≠ backend graph_version

后端返回 GRAPH_VERSION_CONFLICT，不执行任何 operation，并附带：

- current_graph_version 或 current_layout_version；
- 自 expected_graph_version 之后的 entity diff；
- 冲突 node/edge/CPT ID；
- 是否可以安全 rebase。

后端只允许对完全不相交的实体进行显式 rebase。不得静默使用 last-write-wins 覆盖别人的模型修改。

## 4. 事务策略选择

### 4.1 方案 A：每一个鼠标动作直接提交

优点：

- 实现简单；
- audit 非常细。

缺点：

- add node 与 add edge 之间会产生无效中间状态；
- round-trip 次数多；
- CPT 可能反复展开；
- undo 粒度不符合用户意图。

不推荐作为主方案。

### 4.2 方案 B：前端本地修改，最后一次性保存

优点：

- 交互最流畅；
- 后端请求少。

缺点：

- 保存前的画布不是后端实际 BN；
- 长时间本地 draft 容易与后端发生大规模冲突；
- 崩溃时可能丢失全部修改；
- 难以满足“一一映射到后端实际 BN”。

不推荐。

### 4.3 方案 C：后端权威 draft + 用户意图级原子事务

推荐方案。

一个完整用户意图作为一个事务，例如：

- 新增 subskill + 连接 competency + 初始化 CPT；
- 新增 evidence + 创建两个 parent edge + 生成 CPT；
- 删除 node + 删除 incident edges + 迁移受影响 CPT；
- 修改状态集 + 迁移本节点及所有 child CPT。

前端可以先显示 pending ghost，但事务成功前不得把修改标记为 committed。该方案兼顾交互速度、后端一致性、可恢复性和审计能力。

连续的小型参数编辑可以在 300–500 ms 内合并为一个事务，但结构操作和 destructive operation 不应被自动合并。

## 5. 原子事务生命周期

后端处理 graph transaction 的固定顺序：

1. 验证身份、权限、model_id、draft_id 和 transaction_id/idempotency；
2. 比较 expected_graph_version；
3. 从当前 canonical draft 创建内存 candidate；
4. 按 operation 顺序修改 candidate；
5. 执行 CPT migration；
6. 执行不可绕过的 hard-safety validation：schema、ID/reference、DAG、已提供概率值、size cap 和 safe binding；
7. 执行 technical completeness validation，并把 candidate 标为 draft_incomplete、draft_invalid 或 draft_executable；
8. 普通 autosave 不运行 inference smoke；只有用户触发 preview/apply 时才编译 exact draft，失败则保存可定位诊断；
9. 将完整 candidate snapshot、diff、inverse patch、validation report 和 audit event 原子写入；
10. graph_version 加一，返回 canonical diff、CPT migration、draft state 和新 hash。

身份/版本、operation、migration、hard-safety validation 或持久化失败时：

- candidate 整体丢弃；
- graph_version 不变；
- 不保留部分 node、edge 或 CPT 修改；
- 返回定位到 operation index 和 entity ID 的结构化错误。

缺少 binding、CPT 或 selected output path 属于 technical incomplete，可以保存到 draft；它阻止 preview/apply，但不应让用户无法分步设计。Apply 只要求本规格 §11 的 technical validation 与 compile 成功。

Transaction ID 同时作为 idempotency key。客户端重试相同 transaction ID 时，后端必须返回第一次提交的结果，不能重复执行。

## 6. Operation 与 CPT 迁移

### 6.1 Add node

Add node 必须包含：

- stable node_id；
- node_type；
- state IDs 和顺序；
- label；
- 可选 parent IDs；
- CPT 初始化策略。

初始画布坐标不属于 node.add。前端先在 pending ghost 中保留 drop position；semantic batch 成功后，立即用独立 expected_layout_version 调用 layout.update。若位置提交冲突，node 仍已存在，后端给它 unpositioned/auto-layout 状态，前端刷新后可重新应用位置；graph_version 不因坐标改变。

默认初始化：

| Node 类型 | 默认初始化 |
|---|---|
| competency / generic root latent | uniform prior |
| subskill | 若同时提供 parent，使用单父有序 CPT；否则标记 unconfigured |
| evidence | 若同时提供 parents，使用单父表或 ranked-node generator；否则标记 unconfigured |

Context 与 structural derived-evidence 可以作为可选 palette items；若当前 draft 尚未配置其状态/CPT 语义，则先创建为 incomplete，待专家补全后再 preview/apply。

Draft 可以暂时保存 unconfigured node，但不能 preview/apply。Guided 模式应优先把 add node、add edge 和 CPT init 合并为同一事务。

#### 6.1.1 Evidence node 的 AnchorBinding

新增 evidence node 不能只创建图形。它必须在同一 batch 或后续 draft operation 中建立 AnchorBinding：

~~~yaml
binding_id: 550e8400-e29b-41d4-a716-446655440050
node_id: 550e8400-e29b-41d4-a716-446655440051
mode: recipe_output
target:
  recipe_id: gaze_aoi_dwell
  output_id: evidence_likelihood
required_inputs: [I, G, dynamic_aoi_map]
modality_attribution_weights: {I: 0.5, G: 0.5}
result_contract: anchor-result-0.2.0
binding_version: 1
content_identity: sha256:...
~~~

mode 支持：

- recipe_output：绑定 canonical EvidenceRecipe 的一个声明 output；这是普通 evidence node 的默认模式；
- legacy_plugin_output：只用于历史 revision replay，不作为新增 Anchor 的默认入口。

从 session field、existing Anchor clone 或 safe formula 创建 evidence 时，向导先生成同一个 canonical `EvidenceRecipe`，再建立 `recipe_output` binding。`session_field` 由 Input/Statistics operators 表达，`safe_formula` 由 deterministic safe-expression operator 执行。它们不得动态生成/import Python，也不得绕过 operator registry、typed ports、unit、artifact、identity 或 AnchorResult v0.2 校验。

binding.create、binding.update 和 binding.remove 都是 semantic operation，与 node/edge/CPT 一起走 graph.operations.apply 并增加 graph_version。Binding validation 至少检查 node 类型、EvidenceRecipe output 存在、operator compatibility、参数 schema、输入/单位、依赖无环、safe formula AST 白名单、measurement/scorer 与 AnchorResult v0.2 合同。Legacy plugin binding 只用于旧 revision replay。

`modality_attribution_weights` 的 key 只能是 `required_inputs` 中声明的 core stream modality；`dynamic_aoi_map` 等非模态依赖不进入该 map。权重必须 finite、非负且和为 1；省略时对 distinct required core modalities 等分。该字段进入 binding content hash，供 per-modality coverage 使用。

安装 trusted operator extension 不属于图 transaction。`extension.operator.install` 通过受信任流程完成 manifest 和兼容性检查；UI 不得把任意 Python 文本当作 operator 执行。未绑定或 operator target 尚不可用的 evidence node 可以保存在 incomplete draft，并明确显示 `operator_unavailable`，但不能 preview/apply/run；它不得伪装成 session `not_computable`。

### 6.2 Add edge

增加 X → Y 后，Y 的 CPT 必须增加 X 这一维。

对 manual CPT，安全默认是 neutral replication：

Pnew(Y | existing parents, X=x)
=
Pold(Y | existing parents)

即把旧 CPT 的每一行复制到 X 的每个状态。这样新 edge 在初始时对推理零影响，保留修改前行为。Edge 和 CPT 可显示非阻断 `parameter_attention` warning。

对 generated CPT：

- 将新 parent 加入生成器；
- 默认新 parent weight = 0；
- 保留其他参数；
- 物化完整 CPT；
- 可标记非阻断 `parameter_attention` warning。

Add-edge 向导允许用户直接指定非零 weight、weakest-link 和 sigma，并可即时展示：

- 新 CPT 维度；
- 新旧 posterior 的测试差异；
- monotonicity；
- 受影响节点。

### 6.3 Remove edge

删除 X → Y 后，Y 的 CPT 必须消除 X 这一维。安全默认采用 probability-weighted marginalization：

Pnew(Y | R)
=
Σx Pold(Y | R, X=x) × q(X=x | R)

其中 R 是其余 parents，q 来自删除前 canonical draft 的 prior-predictive distribution。若无法可靠计算 q，则使用用户明确选择的 reference distribution；不得静默使用任意一行。

后端在提交前返回：

- reference distribution；
- 新 CPT；
- KL divergence 或最大行差；
- 可选的受影响 posterior preview diff；
- warning level。

Generated CPT 删除 parent 后也先按上述规则生成行为保持型表。用户可以随后选择重新拟合 generator；不得无提示地重新等分权重。

### 6.4 Remove node

删除 node 操作必须明确返回影响摘要，前端可以在提交前即时展示：

- incident edges；
- 所有需要迁移 CPT 的 child；
- 将变成 orphan 的节点；
- 将失去 evidence path 的 competency；
- profile 违规；
- 运行结果可能变化的范围；
- inverse patch 大小。

实际删除意图必须包含：

- deletion_mode = detach 或 cascade；
- orphan_policy；
- CPT migration strategy；

detach 删除目标 node 与 incident edges，但保留其他 nodes，并按所选策略迁移受影响 child CPT。cascade 必须在同一 operation 中显式列出附加删除的 node IDs；不得把“可达后代”隐式全部删除。无需人工审批或强制 preview token，成功操作立即进入 autosaved draft，并可 undo。

若 UI 使用可选 preview_token，它只用于确认 graph_version/影响摘要仍新鲜；不使用 token 也可直接提交明确的删除意图。

默认不静默删除 orphan child。可选 orphan_policy：

- keep_unconfigured；
- promote_to_root_with_prior；
- explicitly_delete，且需在同一事务列出被删节点。

### 6.5 Move node

Move node 只修改 layout metadata，不修改 BN 概率结构或 scientific model hash。它使用独立 layout_version，避免频繁移动与 CPT 编辑冲突。

多人协作时，layout 使用独立 expected_layout_version；冲突只影响位置，但仍不得静默 last-write-wins。

前端在拖动过程中本地实时渲染，在 drag end 时批量提交一个 layout.update；不要为每个 pointer move 发送 RPC。Canonical 请求：

~~~json
{
  "jsonrpc": "2.0",
  "id": "req-layout-12",
  "method": "layout.update",
  "params": {
    "project_id": "project-01",
    "draft_id": "draft-20260710-a",
    "expected_layout_version": 8,
    "transaction_id": "550e8400-e29b-41d4-a716-446655440020",
    "actor": "user@example",
    "positions": [
      {"node_id": "TCP.1", "x": 420.0, "y": 180.0},
      {"node_id": "O1", "x": 680.0, "y": 120.0}
    ]
  }
}
~~~

成功响应返回 layout_version，不改变 graph_version 或 scientific model hash：

~~~json
{
  "jsonrpc": "2.0",
  "id": "req-layout-12",
  "result": {
    "draft_id": "draft-20260710-a",
    "transaction_id": "550e8400-e29b-41d4-a716-446655440020",
    "previous_layout_version": 8,
    "layout_version": 9,
    "layout_hash": "sha256:...",
    "graph_version": 42,
    "audit_event_id": "audit-layout-12",
    "trace_id": "trace-layout-12"
  }
}
~~~

LAYOUT_VERSION_CONFLICT 时前端获取 canonical positions 后可让用户重新应用本次位置；不得把位置冲突升级成 scientific model conflict。

### 6.6 Remove or reverse edge

Reverse edge 不是基础 operation。它必须被表示为同一原子事务中的：

1. edge.remove；
2. edge.add；
3. 两端受影响 CPT 的迁移或初始化。

后端在整个事务完成后统一执行 cycle detection 和 compile。

### 6.7 Change node states

状态 ID 是概率表索引，不能像 label 一样直接重命名。

仅修改显示 label 不需要 CPT migration。增加、删除、合并或拆分 state 必须提供 migration matrix M：

M(old_state, new_state) ≥ 0

且每个 old_state 对所有 new_state 的映射概率和为 1。

M 只足以迁移该节点自身作为 child 的分布：

P_new(new_state | parents) = Σ_old P_old(old_state | parents) × M(old_state, new_state)

当该节点作为其他节点的 parent 时，还必须提供 reverse matrix：

R(new_state, old_state) = P(old_state | new_state)

默认可用明确记录的 reference prior q(old_state) 通过 Bayes 生成：

R(new, old) = q(old) × M(old, new) / Σ_old' q(old') × M(old', new)

q 默认来自变更前 canonical draft 的 prior-predictive distribution；用户也可以选择 approved reference distribution。分母为 0 时必须手工提供 R。随后迁移每个 child CPT：

P_new(child | new_state, remaining_parents) =
Σ_old P_old(child | old_state, remaining_parents) × R(new_state, old_state)

后端同时迁移 virtual evidence schema、coverage 和 explanation state references，并把 M、R、q 及其来源写入 audit/provenance。

增加新 state 时，M 通常会让拆分后的新 states 初始复制相同行为。Guided 模式要求用户选择：

- 从某个旧 state 拆分；
- 从相邻 states 插值；
- 使用明确的新 prior；
- 对 child CPT 使用 clone、interpolate 或 manual reverse matrix。

删除 state 时必须选择 merge target 或完整 migration matrix。系统不得自动丢弃概率质量。

State migration 在编辑过程中自动计算并显示 M、R、q、迁移前后 CPT、归一化误差、monotonicity 和 inference diff；不要求额外审批确认。

## 7. Draft、技术校验与应用

### 7.1 Draft 状态

Draft 状态包括：

- draft_incomplete；
- draft_invalid；
- draft_executable。

每个用户意图都自动保存。允许保存 incomplete 或 invalid draft，便于分步设计；draft_executable 可以 preview，也可以 apply。正式 run.start 只接受 applied revision_id。

### 7.2 Applied revision

Applied revision 不可变。用户点击“应用到后续评估”时：

1. 对 expected_graph_version 做并发检查；
2. 运行最小 technical validation；
3. 编译 recipe 与 inference artifacts；
4. 生成 content identity；
5. 冻结 EvidenceRecipe、BN graph、CPT、bindings 和 schema；
6. 原子更新 active applied pointer。

这里不运行 per-model pytest、golden 或科学审批。Apply 后的任何编辑都自动从该 revision 创建新 draft，不得在原 revision 上原地修改。

### 7.3 Profile

Starter profile 的 apply validation 只要求：

- 用户选定的输出 nodes 存在且 state schema 合法；
- 每个 active output 有可执行 inference path；
- 所有 active EvidenceRecipe、bindings、BN nodes 和 CPT 已配置；
- graph/recipe 可以编译。

TCP/PC/SM/OC 和 33-node inventory 是 starter template，不是 generic engine 的硬要求。系统在后台自动产生新的 revision identity，不要求专家手工修改 major version。

## 8. Undo 与 redo

Undo/redo 必须由后端 command log 和 graph_version 实现，不能只恢复前端画面。

每次成功事务保存：

- forward operations；
- inverse patch；
- touched entity IDs；
- before/after CPT snapshots；
- actor、timestamp 和可选 note。

Undo 是一个新的事务：

- 使用当前 expected_graph_version；
- 应用目标 transaction 的 inverse patch；
- 产生新的 graph_version；
- 保留完整 audit history。

Redo 同样是新事务，重新应用 forward operations。若目标操作之后的其他事务修改了相同实体，后端返回 UNDO_CONFLICT，并要求用户 preview 或手工合并。系统不得通过移动 revision pointer 抹去历史。

## 9. 前端 optimistic / pessimistic 行为

### 9.1 Optimistic

适合：

- node layout 移动；
- 画布视觉属性；
- 非 destructive metadata 修改。

结构编辑时可以显示 optimistic ghost：

- pending node 使用虚线边框；
- pending edge 使用虚线；
- 属性面板只读；
- Run 和 Apply 按钮禁用；
- 后端成功后切换为 committed；
- 后端失败后自动回滚并显示原因。

### 9.2 可恢复的结构编辑

下列操作作为一个可撤销的后端原子事务自动保存：

- 删除 node；
- 删除或反转 edge；
- 改变状态集；
- 手工覆盖大块 CPT；
- apply；
- 任何会改变输出 profile 的操作。

前端可在操作前显示影响摘要，但不得为每次修改增加强制审批步骤。后端拒绝技术上非法的事务时，前端恢复上一 committed state 并精确定位错误；合法修改立即进入 autosaved draft，可通过 undo/redo 恢复。

## 10. 运行时 revision 锁定

推理永远针对 immutable model snapshot。

Run 请求必须指定：

- model_id；
- applied revision_id；
- expected canonical content hash；
- session ID。

编辑 draft 不会修改正在运行的 compiled model。Apply 时只需要短时间 exclusive apply lock：

1. 编译新 revision；
2. 原子切换 active applied pointer；
3. 已开始的 run 继续使用旧 snapshot；
4. 新 run 使用新 applied revision。

若用户对 executable draft 执行 preview，后端先为该 exact draft_id + graph_version 生成 immutable preview snapshot。随后发生的新编辑不会影响该次 preview；输出标记 draft/non-applied，不得覆盖已应用 revision 的历史结果。

## 11. 后端验证

### 11.1 每个事务的硬验证

- JSON schema；
- stable ID 唯一；
- referenced entity 存在；
- no self-loop；
- no duplicate edge；
- DAG cycle detection；
- parent order 稳定；
- state cardinality；
- 已提供 CPT 的 shape；尚未配置则标记 draft_incomplete；
- finite probabilities；
- 0 ≤ p ≤ 1；
- row sum = 1，容差 1e-9；
- generator 参数合法；
- evidence AnchorBinding 唯一、target EvidenceRecipe output 可解析、recipe/operator 依赖无环，executor 输出满足 measurement/result contracts；
- Guided Mode 每个节点最多 3 个 parents；Advanced DAG Mode 默认最多 6 个 parents；
- 物化前计算 CPT 大小，默认不得超过 4096 rows、16384 probability cells 或 2 MiB serialized size；
- migration 后概率质量守恒。

### 11.2 Apply technical validation

Apply 仅在硬验证之外增加可执行性检查：

- 每个 active EvidenceRecipe 的 operator、port、binding、output、parameter、formula 与 scorer 可编译；
- 每个 active BN output 的 evidence reachability 成立；
- 无 unconfigured active node；
- CPT shape、概率范围与 parent/state order 一致；
- model content identity 和自动 audit chain 可生成。

Apply 不检查文献支持、科学合理性、单调性偏好、专家共识或 preview 表现，也不要求 reviewer waiver、固定 inference golden 或测试套件。

### 11.3 Warning

以下问题可显示为非阻断 warning，由专家自行决定是否处理：

- isolated node；
- zero-influence edge；
- posterior 对单个 evidence 极度敏感；
- manual CPT 非单调；
- derived evidence 潜在重复计数；
- competency evidence coverage 过低；
- 新结构偏离 default semantic profile。

## 12. JSON-RPC 协议

### 12.1 方法

后端 sidecar 至少提供：

- model.revision.list / model.revision.get / model.revision.diff；
- model.draft.create / model.draft.get / model.draft.discard / model.draft.apply；
- graph.snapshot.get；
- graph.operations.preview / graph.operations.apply；
- graph.validate / graph.undo / graph.redo；
- layout.update；
- node.get / node.add / node.update / node.remove；
- edge.add / edge.remove；
- binding.get；
- evidence.recipe.get / evidence.recipe.create / evidence.recipe.clone / evidence.recipe.update / evidence.recipe.disable / evidence.recipe.retire / evidence.recipe.preview；
- operator.catalog.list / operator.definition.get / extension.operator.list / extension.operator.install；
- cpt.get / cpt.migration.preview / cpt.generate / cpt.validate / cpt.update；
- run.start / run.status / run.preview；
- audit.events.list。

CPT 修改最终也作为 graph.operations.apply 的同一原子 batch 提交，避免 graph_version 和 CPT 内容脱节。单操作方法是便利入口，后端内部仍转换为相同的 domain operation。

### 12.2 Operation 类型

- node.add；
- node.remove；
- node.metadata.update；
- edge.add；
- edge.remove；
- binding.create；
- binding.update；
- binding.remove；
- cpt.replace；
- cpt.rows.patch；
- cpt.generator.update；
- evidence.recipe.create / evidence.recipe.update / evidence.recipe.disable / evidence.recipe.retire；
- node.states.change；
- profile.set；

### 12.3 原子新增示例

~~~json
{
  "jsonrpc": "2.0",
  "id": "req-9812",
  "method": "graph.operations.apply",
  "params": {
    "project_id": "project-01",
    "draft_id": "draft-20260710-a",
    "expected_graph_version": 41,
    "transaction_id": "550e8400-e29b-41d4-a716-446655440030",
    "actor": "user@example",
    "note": "Add an expert-defined visual scanning sub-skill",
    "validation_mode": "draft",
    "operations": [
      {
        "op_id": "op-1",
        "type": "node.add",
        "node": {
          "node_id": "550e8400-e29b-41d4-a716-446655440001",
          "node_type": "subskill",
          "label": "Visual scanning discipline",
          "states": ["at_risk", "developing", "proficient"]
        }
      },
      {
        "op_id": "op-2",
        "type": "edge.add",
        "edge": {
          "edge_id": "550e8400-e29b-41d4-a716-446655440002",
          "source_node_id": "SM",
          "target_node_id": "550e8400-e29b-41d4-a716-446655440001"
        },
        "cpt_migration": {
          "strategy": "ordered_default"
        }
      }
    ]
  }
}
~~~

成功响应：

~~~json
{
  "jsonrpc": "2.0",
  "id": "req-9812",
  "result": {
    "committed": true,
    "transaction_id": "550e8400-e29b-41d4-a716-446655440030",
    "previous_graph_version": 41,
    "graph_version": 42,
    "draft_hash": "sha256:...",
    "applied_operations": 2,
    "canonical_patch": {
      "nodes": [
        {
          "node_id": "550e8400-e29b-41d4-a716-446655440001",
          "node_type": "subskill",
          "label": "Visual scanning discipline",
          "states": ["at_risk", "developing", "proficient"]
        }
      ],
      "edges": [
        {
          "edge_id": "550e8400-e29b-41d4-a716-446655440002",
          "source_node_id": "SM",
          "target_node_id": "550e8400-e29b-41d4-a716-446655440001"
        }
      ]
    },
    "cpt_migrations": [
      {
        "node_id": "550e8400-e29b-41d4-a716-446655440001",
        "strategy": "ordered_default",
        "parameter_attention": false
      }
    ],
    "validation": {
      "draft_validation_state": "draft_runnable",
      "errors": [],
      "warnings": []
    },
    "audit_event_id": "audit-77a1",
    "trace_id": "trace-77a1"
  }
}
~~~

Revision conflict：

~~~json
{
  "jsonrpc": "2.0",
  "id": "req-9812",
  "error": {
    "code": -32009,
    "message": "GRAPH_VERSION_CONFLICT",
    "data": {
      "expected_graph_version": 41,
      "current_graph_version": 43,
      "transaction_id": "550e8400-e29b-41d4-a716-446655440030",
      "failed_operation_index": null,
      "conflicting_entities": ["SM"],
      "retryable_after_rebase": false,
      "recovery": "Fetch graph.snapshot.get and reapply the intended operation.",
      "trace_id": "trace-conflict-43"
    }
  }
}
~~~

### 12.4 删除预览

`graph.operations.preview` 是可选的影响预览，可返回 preview_token；`graph.operations.apply` 不强制要求该 token。若客户端携带 token，后端可用它确认：

- graph_version 未改变；
- operation 未改变；
- migration strategy 未改变。

若任一条件变化，返回 PREVIEW_STALE，不执行删除。

## 13. 错误与回滚

结构化错误至少包括：

- GRAPH_VERSION_CONFLICT；
- LAYOUT_VERSION_CONFLICT；
- GRAPH_CYCLE_DETECTED；
- INVALID_EDGE_TYPE；
- CPT_DIMENSION_INVALID；
- CPT_ROW_SUM_INVALID；
- CPT_MIGRATION_REQUIRED；
- CPT_SIZE_LIMIT_EXCEEDED；
- ANCHOR_BINDING_INVALID；
- OPERATOR_NOT_FOUND / OPERATOR_EXTENSION_NOT_TRUSTED；
- PROFILE_VIOLATION；
- PREVIEW_STALE；
- MODEL_NOT_RUNNABLE；
- MODEL_LOCKED_FOR_APPLY；
- UNDO_CONFLICT；
- INFERENCE_COMPILE_FAILED。

错误响应必须包含：

- transaction_id；
- failed operation index；
- entity IDs；
- human-readable message；
- machine-readable details；
- current_graph_version；
- suggested recovery action。

所有 model transaction 使用 copy-on-write candidate 和原子提交。失败时前端：

1. 删除 pending ghost；
2. 恢复最后一个 canonical draft snapshot；
3. 保留用户输入到临时 recovery buffer；
4. 显示错误和可执行修复；
5. 必要时提供 refresh、rebase 或 reopen preview。

## 14. 审计

每个成功或失败事务都记录：

- request ID、transaction ID；
- model/revision/draft/graph_version；
- expected_graph_version；
- author、timestamp、可选 note；
- operations；
- before/after hashes；
- CPT migration；
- validation；
- success 或 error code。

失败事务只记录技术错误，不改变 graph_version。成功 undo/redo 产生新的 graph_version；只有 apply 才产生新的不可变 model revision。

## 15. 验收条件

图编辑器完成的最低验收条件：

1. 前端可拖拽新增、删除、移动 node 和 edge；
2. 每个 committed 结构变化都能在后端 canonical graph 查询到；
3. add/remove edge 后 CPT 维度和数值迁移正确；
4. 删除 node 前可以查看完整 cascade preview；
5. state change 不丢失概率质量；
6. 两个客户端用同一 expected_graph_version 修改时，只有一个成功；
7. 任一 operation 失败时没有部分提交；
8. undo/redo 产生新的 backend graph_version；
9. applied revision 不可原地修改；
10. 运行中的 inference 始终绑定 immutable revision；
11. Guided 与 Advanced 模式都不能绕过 DAG 和 CPT 硬验证；
12. 前端 pending、rollback、conflict 和 validation 状态清晰可见。
