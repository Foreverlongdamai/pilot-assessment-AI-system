# M5 Shared Versioned Model Library and Bayesian Workspace Design

| 字段 | 当前值 |
|---|---|
| 设计基线 | M5 v0.1 |
| 日期 | 2026-07-16 |
| 状态 | Approved；已完成仓库一致性复核，可进入轻量 implementation plan |
| 上位设计 | [Expert-Editable Evidence and Assessment Model Design](./2026-07-15-expert-editable-evidence-and-model-design.md) |
| 决策 | D-036–D-040 |
| 实施状态 | 实施中；Task 1–3 generic typed content identity、public contracts/Schema、typed source provenance 与 M4R migration preflight 已完成，Task 4–12 尚未完成；M4R 已完成，M5 implementation plan 与本文配套保存 |

## 1. 目的

M5 把 M4R 已实现的单个可编辑 `EvidenceRecipe` 能力提升为完整的专家模型工作区。系统必须让专家能够：

1. 在全局组件库中持续增加 Evidence 与 BN 节点的并行版本；
2. 为不同飞行任务自由选择这些版本并组成评估方案；
3. 从任意既有方案继续修改和发布新方案，同时不覆盖旧方案；
4. 在一个前端工作区中看清原始输入、Evidence 提取和 BN 概率关系；
5. 修改 Evidence 算法、参数、BN 拓扑、状态和 CPT，并让前端修改一一映射到后端 canonical model；
6. 用固定、可追溯的方案版本运行评估。

M5 的交付目标是**可设计、可执行、可追溯的评估建模平台**，不是证明 starter Evidence、阈值或 CPT 科学正确。

## 2. 非目标

M5 不负责：

- 决定何种飞行任务、Evidence、子技能或能力划分在科学上正确；
- 要求专家修改前通过人工审批、文献审查或整套工程测试；
- 自动从 session 学习 BN 拓扑或 CPT；
- 实现 M6 的完整 project persistence、sidecar JSON-RPC 和 run orchestration；
- 实现 M7 的 WinUI 3 页面；
- 把当前 Hover starter、18 个 Evidence、11 个 sub-skills 或 4 个 competencies 写成通用引擎上限。

## 3. 一句话架构

> 全局不可变版本库保存所有可复用 Evidence 与 BN 组件；任务评估方案只负责选择并锁定这些组件的确切版本，把 session 原始输入先转换为可观测 Evidence，再在所选 BN 中进行后验推断。

```text
Global versioned component library
  EvidenceConcept -> EvidenceVersion 1, 2, 3, ...
  BnNodeConcept   -> BnNodeVersion 1, 2, 3, ...
  CPT / binding   -> immutable versions
                         |
                         | exact version references
                         v
TaskProfileVersion + AssessmentSchemeVersion
                         |
Session X/U/I/G/P -------+--> Evidence extraction --> observations
                                                     |
                                                     v
                                      Bayesian posterior inference
                                                     |
                                                     v
                                   sub-skill / competency posteriors
```

全局库不是“当前生效模型”。只有被某个 `AssessmentSchemeVersion` 明确引用的组件才参与该方案的评估。

## 4. 核心对象与身份

### 4.1 Concept 与 Version 分离

`Concept` 表示长期稳定的“它是什么”，`Version` 表示某一次精确、不可变的实现。

| 对象 | 作用 | 关键内容 |
|---|---|---|
| `EvidenceConcept` | 给同一类可观测证据稳定身份 | `concept_id`、名称、说明、标签 |
| `EvidenceVersion` | 一种精确 Evidence 提取方法 | `evidence_version_id`、`concept_id`、`EvidenceRecipe`、参数、scorer、source bindings、content hash、lineage |
| `BnNodeConcept` | 给一类潜在能力/聚合能力稳定身份 | `concept_id`、名称、语义、节点类别 |
| `BnNodeVersion` | 一个精确 BN 随机变量定义 | `bn_node_version_id`、状态空间、probabilistic parents、CPD/CPT reference、content hash、lineage |
| `EvidenceBindingVersion` | 把一个 Evidence 输出解释为 BN 中的可观测随机变量 | Evidence version、观测状态映射、probabilistic parents、CPD/likelihood table |
| `CptVersion` | 一个精确、不可变的条件概率定义 | child、ordered parents、states、probabilities、normalization policy、content hash |
| `TaskProfileVersion` | 描述某类飞行任务及其版本化上下文 | task identity、期望轨迹/包线、phase/event/AOI 语义、适用输入 |
| `AssessmentSchemeVersion` | 一次可运行的方案发布 | exact component version references、task profile、graph/layout、coverage/输出规则、content hash |

同名不等于同一版本。例如“轨迹偏差”可以有 Hover 版、直线保持版和其他专家版；它们可以属于同一 `EvidenceConcept`，但必须拥有不同的 `EvidenceVersion`，并长期并列存在。

`BnNodeVersion.probabilistic_parents` 可以引用 exact BN-node versions，或在专家定义的其他 DAG 中引用 exact Evidence observation bindings。`EvidenceVersion.recipe.inputs` 是 extraction source bindings 的唯一 canonical 存储，只能引用 raw/session/task sources，不得引用 latent BN posterior；两种 parent/dependency namespace 永不共用。

### 4.2 不可变与 copy-on-write

- 已发布 version 永不原地修改；
- draft 可以持续自动保存、撤销和重做；
- 从任意 component/scheme version 开始编辑时，未改部分继续引用原版本；
- 改动部分在 draft 中形成新候选版本；
- 发布时原子创建全部新增 component versions 和新的 scheme version；
- 发布失败不得留下“方案已发布但部分组件未发布”的半成品；
- 历史 run 始终锁定原 scheme ID、component version IDs 和 content hashes；
- “回滚”是基于历史版本创建新 draft，不改写历史。

### 4.3 方案不是组件的完整复制

方案保存 exact references，而不是复制全局库的所有内容。这样可以：

- 让不同任务安全共享完全相同的组件版本；
- 让不同任务选择同一 concept 的不同版本；
- 避免修改一个方案时覆盖另一个方案；
- 保持组件来源、复用关系和运行 provenance 清晰。

系统不限制“一个任务只能有一套方案”。专家可以为同一任务保存任意多套并行方案，也可以从任意方案派生新方案。

## 5. 三类可视节点

专家工作区只使用三类高层节点：

### 5.1 Raw Input Node

表示 Evidence 提取可读取的数据源。五个概念输入族为：

- `X(t)`：飞行状态；
- `U(t)`：操纵输入；
- `I(t)`：飞行员在 VR 中实际看到的第一视角场景；
- `G(t)`：gaze、stare、fixation 与 AOI；
- `P(t)`：生理信号族，manifest 中至少可拆分为 EEG、ECG。

`pilot_camera` 是独立的物理 stream，可在界面中显示为输入端口；它属于驾驶员视觉/行为数据接口，不等同于 VR 第一视角 `I(t)`。任务 reference、phase/event annotation、AOI 定义和期望轨迹由 `TaskProfileVersion` 提供给 extraction binding；它们是数据/配置依赖，不是 BN 能力节点。

Raw Input Node **不属于 Bayesian Network 的随机变量集合**，也没有 CPT。

### 5.2 Evidence Node

表示一个可从 session 中提取、可在 BN 中观察的变量。它组合两个互相区分的定义：

1. `EvidenceVersion`：怎样从 raw/session/task sources 计算值、trace 与 D/A/U 或 soft likelihood；
2. `EvidenceBindingVersion`：该输出怎样映射为 BN observation，以及在 BN 中由哪些概率父节点解释。

点击节点必须同时显示“提取方法”和“BN 解释”两个区域，不能把它们混成一组父节点。

### 5.3 BN Node

表示 sub-skill、aggregate competency 或专家自定义的其他 latent/derived random variable。其 `BnNodeVersion` 定义状态空间、BN parents 和 CPD/CPT。Starter 模型中的 TCP、PC、SM、OC 和 11 个 sub-skills 只是这类节点的初始示例。

## 6. 两类边，禁止混义

### 6.1 Data / Extraction Edge

```text
Raw Input / task source  ──data──>  Evidence
```

它回答“EvidenceRecipe 读取什么”。后端 canonical 字段为 `EvidenceVersion.recipe.inputs` 和 recipe 内的 typed operator ports。它：

- 决定数据依赖和 recipe execution plan；
- 可以连接 X/U/I/G/P、具体 stream/channel、task reference、phase/event/AOI；
- 不表达概率条件独立；
- 不进入 BN factorization；
- 不能从 BN node 指向 EvidenceRecipe；
- 高层 Evidence 不能把 latent ability 当作提取输入；
- M5 高层图不允许 `Evidence -> Evidence` extraction edge。若多个 Evidence 复用计算，应复用 operator/subgraph 或由 raw/task sources 产生的 typed derived artifact；不得把另一个已评分 Evidence observation 当作原始输入。Evidence variables 之间若有概率关系，必须建为 probabilistic BN edge 并提供相应 CPD。

### 6.2 Probabilistic BN Edge

```text
BN parent  ──probability──>  BN child or observable Evidence variable
```

它回答“child 的条件分布依赖哪些 parent”。若 BN 节点集合为 `V`，则模型联合分布为：

```text
P(V) = product over v in V of P(v | Parents(v))
```

概率边：

- 必须构成 DAG；
- 改变后必须使 child 的 CPD/CPT 与有序 parent state space 一致；
- 不代表程序必须沿箭头方向逐节点计算；
- 不等于 raw data 到 Evidence 的 extraction edge。

两类边使用不同 DTO、不同视觉样式、不同校验器和不同 operation type。任何接口都不得用一个无类型 `edge` 同时表达两者。

## 7. BN 方向与实际推断

### 7.1 Starter 的标准评估建模方向

Hover starter 采用教育测量中常见的生成式方向：

```text
Competency  ──probability──>  Sub-skill  ──probability──>  Evidence
```

因此：

- sub-skill CPD 表示 `P(SubSkill | Competency parents)`；
- Evidence likelihood/CPT 表示 `P(EvidenceState | SubSkill parents)`；
- EvidenceRecipe 仍先从 session 计算 observation，但这不改变 BN 箭头。

### 7.2 评估时的信息流

实际运行先完成数据处理，随后把 Evidence 作为观测输入 BN：

```text
Session -> EvidenceRecipe -> observed Evidence
                                  ⇢ posterior(Sub-skill)
                                  ⇢ posterior(Competency)
```

这里的 `⇢` 表示后验信息影响，不是存储的 BN edge。推理引擎根据 Bayes rule 和完整 joint factorization 计算后验，因此可以沿图中多个方向传播信息。不得因为用户想看到“Evidence 推断能力”，就在显示层把 canonical BN edges 永久反转。

### 7.3 专家自定义方向

通用引擎不把 `Competency -> Sub-skill -> Evidence` 写死为唯一合法拓扑。专家可以发布其他 DAG 方向，但必须满足：

- 每个随机变量有完整、有效且与 parents/states 一致的 CPD；
- 图无环；
- observation binding 明确；
- 新方向发布为新的 BN component/scheme versions；
- UI 明确显示这是一套不同概率模型，而不是同一模型的“反向展示”。

例如 `Evidence -> Skill -> Competency` 可以成为一个技术上有效的 BN，但它需要 `P(Evidence)`、`P(Skill | Evidence)` 和 `P(Competency | Skill)`；它与 starter 的生成式模型不是同一个模型。

## 8. 前端工作区语义

### 8.1 Integrated Design View

主画布显示三类节点和两类边：

- Raw Input Nodes；
- Evidence Nodes；
- BN Nodes；
- 实线或数据色 extraction edges；
- 另一种颜色/线型的 probabilistic edges。

默认可以折叠 Evidence 内部的 operator graph。展开后显示 `EvidenceRecipe` 的 operator nodes/ports；operator nodes 是 Evidence 的内部实现细节，不成为第四类高层模型节点。

### 8.2 Inference Overlay

用户可以开启只读 overlay，显示本次 observation 对后验的影响方向、贡献或敏感度：

```text
Evidence ⇢ Sub-skill ⇢ Competency
```

Overlay 不能被拖拽编辑，不能保存为 BN topology，也不能改变 canonical arrows。

### 8.3 Inspector

点击不同节点时至少显示：

| 节点 | Inspector 内容 |
|---|---|
| Raw input | stream/field/channel、时间语义、manifest 状态、被哪些 Evidence 使用 |
| Evidence | concept/version、recipe graph、parameters、scorer、source bindings、observation mapping、BN parents/CPD、consumers、lineage |
| BN node | concept/version、states、probabilistic parents/children、CPT、说明、lineage |

### 8.4 Library 与 Scheme Composer

前端应允许：

- 搜索全局 Evidence/BN concepts；
- 查看所有并行 versions、来源和使用它们的 schemes；
- 把 exact version 加入当前 scheme draft；
- clone 后修改为新版本；
- 新建全新 concept；
- 从 scheme 移除引用而不删除全局组件；
- 将不再推荐的版本标记 archived/retired，但仍允许历史 replay；
- 从任意已发布 scheme 创建新 draft。

## 9. Scheme 组成与闭包

一个可执行 `AssessmentSchemeVersion` 至少锁定：

```yaml
scheme_version_id: immutable-id
task_profile_version_id: immutable-id
evidence_version_ids: []
evidence_binding_version_ids: []
bn_node_version_ids: []
cpt_version_ids: []
output_node_version_ids: []
coverage_and_reporting_policy_version_id: immutable-id
layout_version_id: immutable-id
content_hash: sha256:...
```

方案必须形成引用闭包：

1. 选中的 BN child 所声明的每个 probabilistic parent version 都在方案中；
2. 每个 Evidence binding 引用的 EvidenceVersion、parent 和 CPT 都存在；
3. 每个 EvidenceVersion 所需的 operator/version 与 source type 可解析；
4. task profile 提供方案声明为 required 的 reference/annotation semantics；
5. output nodes 可从 scheme 的 BN DAG 到达并推理；
6. 所有 exact IDs 与 content hashes 匹配。

编辑器可以自动提出“同时加入缺失依赖”，但不能静默替换为同 concept 的最新版本。

## 10. Draft、Preview 与 Publish

### 10.1 Draft

- draft 允许 incomplete；
- 每个用户意图自动保存；
- domain operations 返回后端 canonical state；
- undo/redo 作用于 draft operation history；
- 并行编辑冲突通过 expected draft version 检测；
- 普通编辑不要求 Python package 发布。

### 10.2 Preview

Preview 锁定 exact draft snapshot 和 session snapshot。它可以运行未发布但技术可执行的方案，结果必须标记 non-formal，并记录 draft content hash。

### 10.3 Publish / Apply

用户点击“应用到后续评估”后：

1. 后端冻结 draft snapshot；
2. 执行最小技术校验；
3. 为改动的 components 生成新 immutable versions；
4. 保留未改 components 的原 exact references；
5. 原子创建新的 `AssessmentSchemeVersion`；
6. 返回 canonical IDs、hashes 和 structured diff；
7. 后续 run 可以选择该版本，旧 schemes/runs 不改变。

Apply 不是科学审批。缺少文献、参数未校准或专家意见不一致只能形成 warning/metadata，不得阻止技术上可执行的方案发布。

## 11. 最小技术校验

只有下列问题可以阻止 publish 或正式 run：

- schema/DTO 无法解析；
- ID、exact version 或 content hash 不存在/不匹配；
- dangling node、port、binding、edge 或 output；
- EvidenceRecipe 或 BN graph 有环；
- operator/version 不可用；
- input/output type、cardinality、time semantics 或 unit 不兼容；
- required parameter 缺失、类型错误或非有限；
- safe formula/scorer 无法编译或不能产生声明输出；
- BN state space 不合法；
- CPD/CPT 缺行、shape 与 ordered parents 不一致、概率非有限/为负或未归一；
- observation mapping 与 Evidence 输出/BN states 不兼容；
- scheme reference closure 不完整；
- 无法生成可执行 inference plan。

以下内容不能成为技术阻断项：

- 算法是否“看起来合理”；
- 飞行表现是否极差；
- 生理数值是否极端；
- Evidence 或 BN 与 starter 不同；
- 新组件尚未有论文、专家共识或科学校准。

## 12. 推理引擎边界

M5 定义 transport-neutral `InferenceEngine` 接口，而不让 UI 依赖某个第三方库：

```text
compile(scheme_version) -> InferencePlan
observe(plan, evidence_observations) -> ObservationSet
infer(plan, observations, query_nodes) -> PosteriorResult
explain(plan, observations, query_nodes) -> InferenceTrace
```

v0 至少支持有限离散状态 BN、hard evidence、soft likelihood evidence 和 exact posterior inference。实现可以采用 variable elimination 或经过验证的等价方法；选库属于 M5 实施计划，不改变本规格的概率语义。

输入 Evidence 提取失败、任务不适用或依赖缺失时，observation adapter 按 scheme policy 选择“不观测该变量”或阻断相关输出；不得把缺失自动转换为 `Unacceptable`。相反，`computed + Unacceptable` 是正常、方向明确的负面 observation。

## 13. Starter Hover Package

M5 可以用当前 Hover 设计建立首个 starter package：

- X/U/I/G/P 多模态输入接口；
- O1–O13、H1–H5 的 18 个 Evidence concepts，以及可进入当前 scheme 的 D-037-compliant starter versions；现有 `starter.o8` 旧 recipe 只保留为 legacy migration/replay，TPX 使用新的并行 compliant version；
- 11 个 sub-skill 和 TCP/PC/SM/OC；
- `Competency -> Sub-skill -> Evidence` 概率图；
- 工程初值 CPT、coverage 和报告规则。

这些内容必须标记 `starter_template` / `engineering_default`。通用代码、schema、数据库、API、UI 和测试不得依赖这些 ID、名称或数量。真实 Hover、直线保持或其他任务方案由专家在 starter 基础上另行发布，并与 starter 并列存在。

## 14. 从 M4R 迁移

M4R 当前 canonical `EvidenceRecipe`、operator registry、validator、compiler/executor、draft/preview/apply/replay 和 18 个 starter resources 是 M5 的迁移输入，不推翻已有算子或算法代码，也不表示每个旧 resource 都可以未经 compatibility 检查直接成为 active M5 `EvidenceVersion`。

迁移原则：

1. 每个现有 recipe 先建立稳定 `EvidenceConcept` 和 migration lineage；只有通过 D-037 source-binding compatibility 检查的内容才导入为 active starter `EvidenceVersion`；
2. M4R applied revision 作为 migration lineage 记录，不在原地改写；
3. Migration preflight 通用检测 `EvidenceVersion.recipe.inputs` 是否引用另一 Evidence observation，不允许按 Anchor ID 写特殊分支；
4. 当前已知不兼容项 `starter.o8` 继续以原 bytes/hash 保存为 legacy migration/replay artifact，不直接进入 active starter scheme；
5. TPX concept 创建新的并行 compliant EvidenceVersion，从 raw/task sources 或 provenance 闭合到 raw/task sources 的 typed derived artifact 计算；该版本不要求与旧 O8 provisional 数值等价；
6. 其余通过 compatibility 检查的 starter recipes 与新的 TPX version 组成 starter scheme 的 Evidence 部分；
7. M5 新增全局 component library、BN versions、Evidence binding、scheme composition 和 atomic publish；
8. 旧 whole-Anchor plugins 继续仅用于历史重放/迁移比较；
9. 不要求新版本维持 provisional starter 数值等价。

## 15. 轻量验证策略

M5 测试只证明平台不变量和小型工作流，不证明评估科学有效：

- Concept/version identity 与 immutable publish；
- copy-on-write 后旧 scheme/version/hash 不改变；
- 同一 concept 的多个并行 versions 可被不同 schemes 选择；
- scheme reference closure 和 exact pinning；
- 两种 edge DTO/operation/validator 不可互换；
- 小型手算离散 BN 的 posterior；
- hard/soft/missing/Unacceptable observation 行为；
- BN DAG、state/CPT shape/probability 校验；
- draft autosave、undo/redo、preview、atomic publish、replay；
- 一个极轻流程：从 Hover starter 派生另一任务方案，替换“轨迹偏差”版本，旧 Hover scheme 结果仍锁定原版本。
- 一个 O8 migration compatibility smoke：旧 `anchor.O1-score`/`anchor.O5-score` recipe 被保留但不能进入 active scheme；新的 raw/task-derived TPX version 可以被选择和执行。

不建立每种模态约一万行数据的重型 fixture，不把 18 个 starter 的精确输出当成 M5 completion gate，也不要求每次专家参数修改运行开发测试。

## 16. M5 验收标准

书面设计和后续实现必须满足：

1. 全局库可保存任意数量 Evidence/BN concepts 与并行 immutable versions；
2. 方案选择 exact component versions，不依赖“latest”；
3. 从任意方案派生时 copy-on-write，旧方案和历史 run 不改变；
4. 一个任务可有多套方案，多个任务可共享或选择不同组件版本；
5. 高层画布明确显示三类节点、两类边；
6. Raw Input 不进入 BN，Evidence extraction 与 BN probabilistic parents 不混义；
7. Starter canonical BN arrows 与实际 posterior inference flow 均被正确显示；
8. Expert-defined alternative DAG 是新模型版本，不是 UI 反转；
9. Evidence Inspector 同时暴露提取方法与 BN interpretation；
10. BN node/edge/state/CPT、Evidence recipe/parameter/scorer 均可通过 canonical backend operations 修改；
11. publish 只做最小技术校验并原子创建新版本；
12. Starter Hover/18/11/4 不成为通用引擎硬编码；
13. 小型 exact inference、version pinning 和 publish/replay 测试通过；
14. 文档、schema、前端和后端对 BN arrow、data edge 和 inference overlay 使用一致术语。
15. M4R migration 不把 Evidence-to-Evidence extraction 静默带入 M5；旧 O8 与新 compliant TPX version 并列且 lineage 可追溯。

## 17. 延后到后续里程碑

### M6

- project database 与 content-addressed component store；
- 完整 draft/revision/run persistence；
- JSON-RPC operations、progress/cancel/error；
- sidecar 生命周期、artifact management 和 run snapshot。

### M7

- WinUI 3 integrated canvas；
- global library browser、scheme composer、inspectors；
- Evidence operator graph、CPT editor、inference overlay；
- session preview、result trace 和 history UI。

### M8

- 安装包、示例 project、备份/恢复；
- 专家用户手册和 operator extension guide；
- 从导入 session 到设计、发布、运行和解释的完整交付验收。

## 18. 依据

本规格的 BN 语义采用标准 DAG/CPD factorization，并区分生成式图方向与后验推断方向；评估系统的 EvidenceRule 与 probability model 分层参考：

- David Heckerman, *A Tutorial on Learning With Bayesian Networks*, Microsoft Research Technical Report MSR-TR-95-06；
- Stanford CS228, *Probabilistic Graphical Models* course notes；
- Robert Mislevy, Russell Almond, Duanli Yan, Linda Steinberg, *Bayes Nets in Educational Assessment: Where Do the Numbers Come From?*, CSE Technical Report 518。

完整链接和用途见 [REFERENCES.md](../REFERENCES.md)。

## 19. 复核与实施入口

本文已通过用户书面复核。配套的轻量、inline 实施入口为 [M5 Implementation Plan](../plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md)。批准规格和保存计划都不等于 production code 已完成；实施状态与 fresh verification evidence 继续以 [11_IMPLEMENTATION_STATUS.md](../11_IMPLEMENTATION_STATUS.md) 为准。
