# Expert-Editable Evidence and Assessment Model Design

| 字段 | 当前值 |
|---|---|
| 设计基线 | Expert-designer architecture v0.1；产品设计基线 v0.2 |
| 日期 | 2026-07-15 |
| 状态 | Approved：用户于 2026-07-15 明确批准本规格并授权开始实施；M4R 按独立实施计划推进 |
| 取代范围 | 取代旧 M4 规格中“普通公式修改必须发布 AnchorPlugin”“固定 18 个算法 golden 是 M4 完成门”及 replacement plan Task 29–36 的继续执行授权；不改写 Task 0–28 的历史事实 |
| 保留范围 | M1–M3、AnchorResult v0.2、AnchorMeasurement、calculation status、no-quality-gate、typed dependency、trace/artifact、差表现为有效 evidence 等已实现合同继续保留 |
| 产品目标 | 为领域专家提供可视化、自由增删改 Evidence、计算方法、BN 节点/边、状态与 CPT 的 Windows 本地设计系统 |
| M5 口径 | 2026-07-16 的 [M5 Shared Versioned Model Library and Bayesian Workspace Design](./2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) 已细化全局组件版本、任务方案、三类节点、两类边和 BN/inference 语义；发生冲突时以该 M5 规格为准 |

## 1. 方向纠正

本产品的首要交付不是证明当前 O1–O13、H1–H5、阈值或 CPT 科学有效，而是提供一套专家可以自行设计、查看、修改、运行和比较整个评估模型的系统框架。

当前 18 个 Anchor 及其 BN 只是 starter template。它们用于：

- 演示多模态数据如何进入 evidence；
- 让端到端软件在没有最终专家算法时可以运行；
- 为专家提供可复制、可删除、可替换的初始材料；
- 验证框架能够承载轨迹、控制、视觉、眼动、EEG 和 ECG 等数据。

它们不用于：

- 宣称当前公式能够正确衡量飞行员能力；
- 阻止专家修改算法、阈值、Anchor inventory 或 BN；
- 把一次参数或公式修改变成 Python 开发、审批或完整软件发布；
- 以大量模型特定 golden 证明 provisional scientific model 正确。

因此，后续设计以 **free to modify, welcome to modify** 为原则。可恢复性、历史重放和最小技术校验在后台完成，不变成专家操作负担。

## 2. 两张相互连接的图

系统包含两张职责不同的可编辑图：

```text
Session data / semantics / references
                |
                v
Evidence Computation Graphs (one EvidenceRecipe per Anchor)
                |
                v
AnchorMeasurement -> AnchorResult
                |
                v
Bayesian Network Graph
                |
                v
Sub-skill / Competency posterior and explanation
```

### 2.1 Evidence Computation Graph

Evidence Computation Graph 描述“原始或派生数据怎样变成一个 evidence”。专家可以修改输入、算子、参数、边、公式、窗口、聚合和 scorer。

### 2.2 Bayesian Network Graph

BN Graph 描述 evidence 怎样连接 sub-skill/competency，以及节点状态、边和 CPT。BN evidence node 通过稳定 binding 指向一个 Anchor/EvidenceRecipe output。

### 2.3 联动

专家在 BN 图中点击 evidence node 时，可以进入其 Evidence Computation Graph；从计算图也可以回到其 BN consumers。新增 evidence 可以在一个用户意图中同时创建 recipe、Evidence output、BN observation binding 和必要的概率定义。两种图语义共同属于同一个 scheme draft；apply 后形成 exact-pinned component/scheme versions，布局版本可以独立更新。

### 2.4 M5 集成画布与两类边

M5 前端可以把两张职责不同的图整合到同一高层工作区，但不会合并其语义。高层节点固定为 Raw Input、Evidence 与 BN Node；Evidence 内部 operator graph 可展开查看。`Raw/task source -> Evidence` 是 data/extraction edge，Raw Input 不属于 BN；probabilistic BN edge 才定义 `P(child | parents)`。Hover starter 的 canonical BN 为 `Competency -> Sub-skill -> Evidence`，实际观察 Evidence 后的 posterior influence 可用只读 overlay 反向显示，但不能改写 canonical topology。

组件不再只作为整套 model revision 的内部副本。全局库保存 `EvidenceConcept/EvidenceVersion`、`BnNodeConcept/BnNodeVersion`、binding/CPT versions；`AssessmentSchemeVersion` 为某个任务方案锁定 exact versions。编辑和发布采用 copy-on-write，旧方案不被覆盖。

## 3. Canonical EvidenceRecipe

`EvidenceRecipe` 是前端显示、后端保存和运行时执行的唯一计算方法来源。前端不得复制公式或在 C# 中重新实现 evidence 逻辑；后端也不得维护与 recipe 不一致的隐藏 Anchor 配置。

建议的逻辑合同如下：

```yaml
recipe_id: stable-id
recipe_version: 1
anchor:
  anchor_id: stable-id
  name: editable label
  description: human-readable purpose
  lifecycle: active | disabled | retired
  scientific_status: starter_template | expert_defined | calibrated
inputs:
  stream_bindings: []
  semantic_bindings: []
  reference_bindings: []
graph:
  nodes: []
  edges: []
outputs:
  primary_value: node-port reference
  raw_metrics: []
  breakdowns: []
  traces: []
scoring:
  mode: ordered_dau | soft_likelihood | custom_operator
  parameters: {}
documentation:
  summary: human-readable method
  assumptions: []
  parameter_notes: {}
  references: []
ui:
  groups: []
  preferred_layout: {}
```

确切 DTO 和 JSON Schema 在新 M4 实施计划中定义，但必须满足以下不变量：

1. 所有 node、edge、binding、output 和 parameter 都有稳定 ID 或稳定 schema path；
2. graph edge 明确 source port 与 target port；
3. 参数值只存在于 recipe/draft，不在 Anchor-specific Python 中重复维护；
4. 输出明确绑定 `primary_value`、raw metrics、breakdown 和可选 trace；
5. scorer 是 recipe 的可编辑部分，不由显示名称或 Anchor ID 猜测；
6. 文档和 UI metadata 与执行定义一起保存；
7. recipe 可以 incomplete 并自动保存，但只有技术上 executable 时才能应用到后续评估；
8. recipe 内容变化在 apply 时自动形成新的 EvidenceVersion 与 scheme identity，不要求专家理解 hash 或 semantic versioning。

## 4. 通用算子

通用算子是 Evidence Computation Graph 的可复用计算积木，不等于一个完整 evidence。每个 `OperatorDefinition` 至少声明：

- `operator_id` 与 implementation version；
- 人类可读名称、说明和可选公式/伪代码；
- typed input/output ports；
- 时间语义、cardinality 与单位；
- parameter JSON Schema；
- 前端控件 metadata，例如 label、group、unit、slider/text/select、help；
- 是否可输出中间 trace；
- built-in 或 trusted extension implementation identity。

每个 recipe node 只引用一个 operator，并保存该实例自己的参数。专家可以拖拽、复制、删除、重连或替换 node。

### 4.1 首批算子族

新 M4 至少需要以下 operator families：

| 算子族 | 典型功能 |
|---|---|
| Input | stream/table/field/channel、semantic phase/event/baseline、reference、常量 |
| Temporal | event select、phase select、window、offset、interval intersect/clip、left-hold support |
| Signal | unit conversion、filter、smooth、detrend、difference、resample（仅 recipe 显式选择时） |
| Event | threshold crossing、hold/run、peak、turning point、movement、reversal、recovery |
| Gaze/vision | gaze-AOI association、AOI filter、fixation、first match、dwell interval |
| Flight geometry | target/reference error、envelope membership、distance、angle、capture |
| Statistics | count、sum duration、mean、median、RMS、percentile、rate、ratio |
| Composition | safe formula、boolean logic、weighted combination、clip（仅公式声明） |
| Aggregation | per-window/per-event/per-phase/session worst、best、mean、median、pooled ratio |
| Scoring | ordered D/A/U、soft likelihood、classification override mapping |

当前 `movement`、`gaze_aoi`、`fixation`、`envelopes`、`events`、`reference_join` 和 scorer 等 pure/runtime primitives 是首批 operator implementation 的主要迁移来源。

### 4.2 示例：扰动期间关注目标仪表区域

专家无需编写 Python，可以组合：

```text
EventSelect(disturbance)
  -> EventWindow(start_offset=0, end_offset=5 s)
GazeAoiIntervals(source=assigned AOI or gaze-ray/scene association)
  -> IntervalIntersect(event windows)
  -> AoiFilter(expected instrument AOIs)
  -> FirstMatchLatency
  -> DurationSum / DwellRatio
  -> EventAggregate(worst | mean | all)
  -> OrderedDauScorer(expert thresholds)
```

如果数据直接提供逐帧 AOI label，则 gaze operator 使用 label-to-interval mode；如果只提供 gaze ray、head pose 和 scene AOI，则使用 geometry-association mode。两种模式都由 recipe 显式选择，不由运行时猜测。

## 5. Plugin 边界

普通专家修改不需要 Python plugin。以下操作只修改 component/scheme draft：

- 修改参数值；
- 修改字段、通道、AOI、phase、event 或 baseline binding；
- 修改窗口、滤波参数、阈值和聚合；
- 使用已有算子重连计算图；
- 编写 safe formula；
- 复制、新增、disabled 或 retired Anchor；
- 修改 scorer；
- 修改 BN 节点、边、状态和 CPT。

只有现有算子库无法表达新的计算能力时，开发者才增加 trusted operator plugin。Plugin 提供新算子，不要求每个新 Anchor 都有一个新 Python module。安装后，operator definition、parameter schema、说明和前端 metadata 自动进入 operator palette。

普通编辑器不执行任意 Python、`eval` 或未注册脚本。`safe_formula` 使用有限 AST 和 typed/unit-aware operators；其目标是让专家自由组合已有能力，而不是把前端变成代码 IDE。

## 6. 前端与后端一一对应

### 6.1 前端职责

前端根据 backend schema/metadata 自动生成：

- Evidence graph canvas 与 operator palette；
- Anchor/recipe inspector；
- 参数表单、单位和帮助文本；
- safe formula editor；
- intermediate trace selector；
- BN graph、CPT editor 和 binding inspector；
- 修改前后 recipe/BN/result diff；
- undo/redo 与历史版本入口。

### 6.2 后端职责

后端是 canonical state source，负责：

- draft 自动保存；
- operation 应用和 canonical response；
- recipe/BN technical validation；
- recipe compile/execute；
- preview；
- component/scheme version 原子创建；
- historical revision replay；
- run 对固定 revision 的锁定。

前端不得直接编辑 package JSON/YAML 或数据库文件。它提交 domain operations，收到后端 canonical recipe/graph 后更新 committed state。

## 7. 自由编辑生命周期

用户已选择以下交互：

1. 打开一个 published scheme version 或 starter template；
2. 系统创建或恢复 autosaved draft；
3. 每次参数或图修改自动保存，支持 undo/redo；
4. incomplete draft 可以继续编辑；
5. 用户可随时对选定 session 执行 preview；
6. 点击“应用到后续评估”时，后端只执行最小技术可运行检查；
7. 通过后 copy-on-write 创建 immutable component versions 与新的 scheme version，供后续新 run 显式选择；
8. 当前运行、历史 run 和旧 revision 不改变；
9. 从历史版本恢复实际上是基于该版本创建新 draft，不移动或重写历史记录。

`apply` 不是科学审批、专家委员会审核、测试套件或软件发布。版本、author、time、structured diff 和 content identity 在后台自动记录；用户 note/reason 可选，主要服务于撤销、比较和重放。

## 8. 最小技术校验

系统不得判断算法“是否科学合理”。Apply 只可因以下技术问题被阻止：

- DTO/schema 无法解析；
- dangling node、edge、port、binding 或 output；
- computation graph 或 BN graph 有环；
- operator 不存在或版本不兼容；
- input/output type、cardinality 或 unit 无法连接；
- required parameter 缺失、类型错误或非有限；
- safe formula 无法编译；
- scorer 无法产生合同规定的 evidence 输出；
- BN CPT 缺行、概率非法或 shape 与 parent/state 不一致；
- selected model 无法形成 executable run plan。

以下事项只显示 metadata/warning，不能阻止保存或 apply：

- 当前公式没有文献支持；
- 参数未经校准；
- Anchor 与能力的关系未获共识；
- CPT 是工程初值；
- 专家选择了与 starter template 不同的算法；
- preview 结果表现极差或极端。

## 9. 验证策略重置

测试目标是证明平台按用户 recipe 执行，不是证明 starter template 科学正确。

### 9.1 需要工程测试

- 每个 built-in operator 的输入、输出和参数合同；
- recipe graph compile、execute、trace 和 error localization；
- type/unit/port/DAG 检查；
- autosave、undo/redo、apply revision 和 replay；
- 前端 schema/form 与 backend contract 一致；
- 新增/复制/disabled/retired Anchor 不需要修改 orchestrator；
- 一个轻量端到端 smoke：创建“扰动期间目标 AOI 关注”Anchor，修改参数，preview 结果变化，apply 后旧 revision 仍可重放；
- 新 operator plugin 的 focused implementation test。

### 9.2 不再作为普通编辑门槛

- 每次参数修改运行 pytest、build 或 isolated-wheel；
- 每个 expert recipe 编写独立 hand-calculated golden；
- 要求 starter template 的 all-Desired/all-Unacceptable 结果证明科学合理；
- 修改公式必须更新 Python plugin version；
- apply 前要求人工审批或复核记录；
- 把 scientific validation status 当作可运行 gate。

现有 Task 0–28 测试和提交保留为历史工程证据。迁移当前 15 个 Anchor 时只需要少量代表性 comparison smoke 证明 recipe runner 没有明显接错输入/输出；专家随后修改不需要维持旧算法等价。

## 10. 现有实现迁移

### 10.1 保留

- M1/M2/M3 contracts、ingestion、synchronization 和 aligned views；
- `AnchorMeasurement`、`AnchorResultV2`、calculation status、breakdown、trace 和 artifact refs；
- no-quality-gate 与 poor-performance-is-evidence 原则；
- generic catalog cardinality、dependency scheduling 和 central scoring 中可复用的部分；
- 已有 pure primitives 和 shared providers 的算法代码；
- 已完成 Git 历史和 historical replay identity。

### 10.2 改造

- 从 whole-Anchor plugin registry 转向 operator registry + recipe catalog；
- 将 Anchor-specific parameters、temporal recipe 和 scorer 统一进 EvidenceRecipe；
- 将已有 primitives 包装为 typed operators；
- 将 O1–O12、H1–H3 转为 starter EvidenceRecipes；
- 将现有 whole-Anchor plugins 标为 legacy reference implementation，供历史重放和迁移比较，不再作为新 Anchor 的默认扩展方式；
- H4、H5、O13 直接按 recipe/operator 路线实现，不执行旧 replacement Task 29–31 的固定插件方案。

### 10.3 不做

- 不删除已完成代码或测试来伪造一条干净历史；
- 不重写 M1–M3；
- 不要求新 recipe 保持当前临时公式；
- 不用 exact-18 inventory 约束通用 engine；starter template 可以有 18 个，但 expert model cardinality 可变。

## 11. 里程碑重基线

### M4R — Editable Evidence Computation Foundation

交付 EvidenceRecipe/OperatorDefinition/recipe compiler/executor、operator registry、初始 operator families、starter-template migration，以及 backend-only 的 create/edit/clone/disable/preview/apply/replay 能力。M4R 完成条件是无需新增 Python AnchorPlugin 就能创建并修改示例 evidence，而不是证明 18 个临时算法科学正确。

### M5 — Expert Model Workspace and Bayesian Network

交付全局 versioned component library、TaskProfile/AssessmentScheme composition、autosaved scheme draft、integrated three-node/two-edge workspace、EvidenceBinding、BN node/edge/state/CPT 编辑、exact inference、technical validation、copy-on-write atomic publish 和 diff/undo/replay。Starter Hover BN 只是可编辑模板。正式合同见 [M5 Shared Versioned Model Library and Bayesian Workspace Design](./2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)。

### M6 — Local Runtime, Persistence and Protocol

交付 project/session/model/run persistence、sidecar、JSON-RPC、run orchestration、artifact management、progress/cancel/error、revision lock 和 backend end-to-end workflow。

### M7 — Windows Expert Designer

交付 WinUI 3 应用、session import、Evidence Designer、BN Designer、参数/CPT 表单、preview/result/trace、版本历史和后端生命周期管理。

### M8 — Integration, Packaging and Handoff

交付安装包、示例项目、用户/专家文档、扩展算子开发指南、备份/恢复和从导入 session 到设计模型、应用版本、运行评估、查看结果的完整验收。

每个里程碑在实施前分别拥有独立 spec 与 plan，避免把 Evidence engine、BN workspace、runtime 和 WinUI 混成一个不可执行的大计划。

## 12. M4 权威迁移

自本规格生效起：

1. `2026-07-13-m4-anchor-evidence-availability-design.md` 的 Task 0–28 已实现部分保留历史与当前代码合同；
2. 其中“普通算法变化必须发布 whole-Anchor plugin version”的要求被本规格取代；
3. D-025/D-026/D-027 对固定 18-plugin completion gate 的要求不再定义新 M4R 完成条件；
4. replacement implementation plan Task 29–36 暂停且不再授权执行；
5. 新 M4R plan 已在本规格获批后另行编写并成为当前实施入口；
6. M5–M8 各自另写正式 spec/plan；
7. 本规格获批时的代码基线为 M1–M3 complete、旧 M4 Task 0–28 complete、15 个 legacy/reference production plugins implemented；此后 M4R 状态以实施计划和 11_IMPLEMENTATION_STATUS.md 为准。

## 13. 验收标准

设计与后续实现至少满足：

1. 初始 18 Anchor 和 BN 明确标为 starter templates，不被描述为科学有效模型；
2. 前端显示的 recipe 与后端执行的 recipe 是同一 canonical object；
3. 专家可在不写 Python 的情况下创建、修改、复制、disabled 或 retired Anchor；
4. 参数、输入、窗口、公式、聚合和 scorer 均可编辑；
5. BN 节点、边、state 和 CPT 均可编辑；
6. 普通修改 autosave，点击 apply 后用于后续 run，无审批或工程测试门；
7. only-technical validation 不判断科学合理性；
8. 新 Python 只在增加现有 operator library 不具备的能力时需要；
9. 当前 15 个插件和 primitives 有明确迁移路径，H4/H5/O13 不继续旧固定插件路线；
10. 历史 revision/run 可重放，正在运行的评估不受 draft 修改影响；
11. 现有 M1–M3 与差表现 evidence/no-quality-gate 边界不回退；
12. M4R–M8 的独立规格和计划覆盖直至 Windows 产品交付。

## 14. 明确非声明

本规格不声明：

- 当前 starter Anchor 能有效提取真实能力 evidence；
- 当前 BN 能合理估计飞行员能力；
- 任一默认阈值、频段、AOI、权重或 CPT 已获专家认可；
- 软件可运行等于科学有效；
- 技术上 executable 的 expert model 一定具有研究或航空用途。

这些判断属于后续领域专家的模型设计、校准和研究工作；产品负责让其修改过程透明、直接、可执行和可恢复。
