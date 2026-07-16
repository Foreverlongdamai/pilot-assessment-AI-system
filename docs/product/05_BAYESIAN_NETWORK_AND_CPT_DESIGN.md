# 05 贝叶斯网络与 CPT 设计

## 1. 文档状态

- 文档版本：1.1
- 对应模型版本：pilot-assessment-bn v0.1
- 状态：可编辑 starter BN 设计，尚未实现或科学验证；2026-07-16 已按 M5 shared-versioned-model 架构澄清
- Starter template 节点数：33；generic BN engine 不固定数量
  - 4 个 aggregate competency 节点
  - 11 个 latent sub-skill 节点
  - 18 个 observed evidence 节点
- 上下文：Translation、Deceleration、Hover stabilization 三阶段。Phase 是已知上下文，不计入 33 个能力评估节点。

本设计的目标不是声明当前模型已经得到航空专家或实验数据验证，而是先建立一套可运行、可检查、可修改、可扩展的概率计算逻辑。后续专家可以在不修改推理引擎的情况下调整节点、边、anchor 算法、阈值、CPT 和 phase 参数。

> **当前权威补充：** [M5 Shared Versioned Model Library and Bayesian Workspace Design](./specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) 定义全局 component versions、task schemes、三类节点、两类边和 BN/inference 语义。BN observation node 通过 `EvidenceBindingVersion` 指向 exact `EvidenceVersion` output。专家修改节点、边、state、CPT 或 binding 后以 copy-on-write 发布新 component/scheme versions，只受 DAG、引用、shape 和概率等技术校验，不受科学审批或 golden gate。

## 2. 建模原则

### 2.1 生成方向与推理方向

Hover starter 的 canonical 生成方向是：

Competency → Sub-skill → Evidence

含义是：不可直接观测的整体能力影响子技能表现，子技能表现再影响可以观测到的 anchor evidence。对 BN 中所有随机变量 `V`，probabilistic edge 定义 child 的 parents，联合分布按以下方式分解：

`P(V) = ∏ P(v | Parents(v))`

实际评估先由独立的 EvidenceRecipe 从 session 数据形成 observation，再使用贝叶斯后验推断：

Observed evidence → posterior of sub-skill → posterior of competency

前端设计视图中的箭头必须显示该 model version 真正存储的概率方向，不能因为推理从 evidence 返回 competency 就把网络箭头反过来。可另开只读 inference overlay 显示 `Evidence ⇢ Sub-skill ⇢ Competency` 的信息影响；overlay 不是 BN edge。

通用引擎不把 starter 层级写成唯一合法方向。专家可以发布其他满足 DAG 和完整 CPD/CPT 合同的方向，但它必须是新的 BN component/scheme versions。例如 `Evidence -> Skill -> Competency` 需要 `P(Evidence)`、`P(Skill | Evidence)` 和 `P(Competency | Skill)`，与 starter 不是同一个模型，不能只靠 UI 翻转箭头得到。

### 2.2 共享 evidence

同一个 anchor 同时支持多个 sub-skill 时，只建立一个 evidence 节点，并让它拥有多个 sub-skill 父节点。不得复制成多个名称相同但相互独立的节点，否则会重复计算同一观测。

### 2.3 概率输出

每个 competency 和 sub-skill 输出完整后验分布，不只输出一个分数。前端可以同时显示：

- 最可能状态；
- 三状态概率；
- evidence coverage；
- evidence contribution；
- 模型 revision 与参数来源。

Posterior concentration、evidence coverage 和模型科学有效性是三个不同概念，界面和报告不得把它们统一称为“准确率”或“置信度”。

### 2.4 Raw extraction 不属于 BN

系统中的 `X/U/I/G/P -> Evidence` 是 data/extraction relation，回答 EvidenceRecipe 读取哪些 session/task sources。Raw Input node 不属于 BN random variable set，也没有 CPT。Evidence 高层节点同时关联：

- `EvidenceVersion.recipe.inputs`（extraction source bindings）与内部 typed operator graph；
- `EvidenceBindingVersion` 中的 observation state mapping、probabilistic parents 和 CPD/likelihood。

这两类关系使用不同 DTO、operation、视觉样式和 validator。禁止用一个无类型 `parents` 或 `edge` 字段混装。

## 3. 节点与状态

### 3.1 Competency 节点

| ID | 名称 |
|---|---|
| TCP | Task Control Proficiency |
| PC | Procedural Compliance |
| SM | Situational Monitoring |
| OC | Operational Composure |

Competency 使用三状态：

| 内部 rank | 状态 ID | 中文显示 |
|---:|---|---|
| 0 | at_risk | At Risk / 风险 |
| 1 | developing | Developing / 发展中 |
| 2 | proficient | Proficient / 熟练 |

v0.1 的默认先验统一为：

P(at_risk, developing, proficient) = (1/3, 1/3, 1/3)

该 uniform prior 表示系统在没有 session evidence 时不预设飞行员好或差。专家可以修改先验，但修改必须产生新的参数 revision。

### 3.2 Sub-skill 节点

| Competency 父节点 | Sub-skill ID | 名称 |
|---|---|---|
| TCP | TCP.1 | Trajectory tracking |
| TCP | TCP.2 | Maneuver precision |
| TCP | TCP.3 | Control efficiency |
| TCP | TCP.4 | Control smoothness |
| PC | PC.1 | Envelope discipline |
| PC | PC.2 | Event response |
| SM | SM.1 | Reactive vigilance |
| SM | SM.2 | Attention allocation |
| OC | OC.1 | Disturbance recovery |
| OC | OC.2 | Stress resilience |
| OC | OC.3 | Physio regulation |

Sub-skill 同样使用 at_risk、developing、proficient 三状态和 rank 0、1、2。

### 3.3 Evidence 节点

Evidence 使用三状态：

| 内部 rank | 状态 ID | 中文显示 |
|---:|---|---|
| 0 | unacceptable | 不可接受 |
| 1 | adequate | 可接受 |
| 2 | desired | 理想 |

O2 的正式定义在 v0.1 中为 Peak tracking excursion，替代旧设计中的 Deceleration profile fidelity。

| Evidence ID | 名称 | 生成父节点 | 是否共享 |
|---|---|---|---|
| O1 | Phase-state precision (T/D/H) | TCP.1, PC.1 | 是 |
| O2 | Peak tracking excursion | TCP.1, TCP.2 | 是 |
| O3 | Terminal capture quality | TCP.2 | 否 |
| O4 | Sustained hover time | TCP.2 | 否 |
| O5 | Workload rate | TCP.3 | 否 |
| O6 | Control magnitude RMS | TCP.3 | 否 |
| O7 | Control reversal rate | TCP.4, OC.2 | 是 |
| O8 | TPX composite | TCP.3 | 否 |
| O9 | Dead-band activity | TCP.4 | 否 |
| O10 | Recovery time | OC.1 | 否 |
| O11 | Disturbance latency | PC.2, SM.1 | 是 |
| O12 | Envelope-drift latency | PC.1, SM.1 | 是 |
| O13 | Physio-control coupling | OC.2 | 否 |
| H1 | AOI dwell | PC.2, SM.2 | 是 |
| H2 | First fixation latency | SM.1 | 否 |
| H3 | Off-task dwell | SM.2 | 否 |
| H4 | ECG fluctuation | OC.3 | 否 |
| H5 | EEG fluctuation | OC.3 | 否 |

以上映射构成 v0.1 starter 的默认语义结构。图编辑器可以在 scheme draft 中修改结构；apply 时为改动的 BN nodes/bindings/CPTs 创建新 immutable versions，并创建新的 exact-pinned scheme version。旧 scheme 不改变。

## 4. Phase context

Translation、Deceleration 和 Hover 是 starter task 中的已知上下文，不是能力节点，也不是第四种 evidence 状态。Starter recipes 用它们计算 phase breakdown、applicability 和聚合；专家也可在 BN draft 中显式建模 context，只要提供完整状态/CPT 语义。

默认 BN 严格保持 33 个语义节点，并使用：

P(E_session | parent sub-skills)

每个 anchor 每个 session 只向对应 evidence node 提交一次聚合 observation。AnchorResult v0.2 保存逐 phase 数值、calculation status、override 和 source trace，再按该 anchor 的 aggregation policy 形成单一 D/A/U likelihood。不得把 T/D/H 三条结果重复注入同一个静态 evidence node，否则会覆盖观测或重复计算证据。v0.1 inference 只使用 base/session-aggregate CPT，不选择 translation/deceleration/hover CPT slice。

若专家需要 phase plate，可在 draft 中显式 unroll 为具有稳定 instance ID 的节点（例如 O1@translation），定义 shared parents、跨 phase 依赖和 fusion/CPT 规则。Apply 自动创建新的 BN component/scheme versions；不要求手工发布 major profile。它不是 starter snapshot 的默认推理方式。

## 5. CPT 默认设计

### 5.1 单父节点的有序 CPT

Competency → Sub-skill 和单父 Sub-skill → Evidence 首版均使用同一套保守、有序的默认表。列顺序始终是 At Risk、Developing、Proficient；对于 evidence，列显示为 unacceptable、adequate、desired。

| 父节点状态 | 子节点低 / Unacceptable | 子节点中 / Adequate | 子节点高 / Desired |
|---|---:|---:|---:|
| at_risk / unacceptable | 0.79 | 0.20 | 0.01 |
| developing / adequate | 0.17 | 0.66 | 0.17 |
| proficient / desired | 0.01 | 0.20 | 0.79 |

这张表表达三条默认假设：

1. 父节点和子节点通常同等级；
2. 相邻等级仍有可见概率；
3. 从最低直接跳到最高的概率很小但不为零。

该表是可运行初值，不是经实验验证的真值。

### 5.2 多父 evidence 的 ranked-node 生成器

共享 evidence 的完整 CPT 会随父节点数指数增长。v0.1 不要求专家逐行手填，而是先用参数化 ranked-node 生成器自动产生完整 CPT，再允许专家覆盖任意行。

所有父节点状态映射到 rank：

- at_risk = 0；
- developing = 1；
- proficient = 2。

对父节点状态组合 x1...xn，先计算中心值：

μ = clip((1 - λ) × Σ(wi × xi) + λ × min(xi), 0, 2)

其中：

- wi ≥ 0，且 Σwi = 1；
- λ ∈ [0, 1]，表示 weakest-link 强度；
- clip 把结果限制在 0 到 2。

再把中心值转换成三状态概率：

P(child = k) = exp(-(k - μ)² / (2σ²)) / Σj exp(-(j - μ)² / (2σ²))

默认 σ = 0.60。σ 越小，CPT 越确定；σ 越大，CPT 越保守。

默认多父参数如下：

| Evidence | 父节点权重 | λ | σ |
|---|---|---:|---:|
| O1 | TCP.1=0.50, PC.1=0.50 | 0.50 | 0.60 |
| O2 | TCP.1=0.50, TCP.2=0.50 | 0.50 | 0.60 |
| O7 | TCP.4=0.50, OC.2=0.50 | 0.50 | 0.60 |
| O11 | PC.2=0.50, SM.1=0.50 | 0.50 | 0.60 |
| O12 | PC.1=0.50, SM.1=0.50 | 0.50 | 0.60 |
| H1 | PC.2=0.50, SM.2=0.50 | 0.50 | 0.60 |

所有共享 anchor 首版均采用等权和 λ=0.50，作为不预先偏向任一 parent 的透明工程默认。专家可以在前端按内容审查或校准结果调整权重、weakest-link 强度和 σ；修改后为该 CPT/BN node 生成新 component version，并发布选择它的新 scheme version。

生成器必须把每个父状态组合物化成普通离散 CPT。推理引擎只读取物化后的 CPT，因此前端可以完整展示、逐行编辑和审计实际使用的概率。

### 5.3 参数化 CPT 与手工覆盖

每个非根节点的 CPT 配置必须记录：

- mode：generated 或 manual；
- generator_type；
- ordered states 与 parent order；
- weights；
- weakest_link λ；
- sigma；
- materialized_table；
- source：system_default、expert、data_calibrated 或 manual_override；
- revision、author、timestamp 和可选 note。

Guided 编辑模式修改生成器参数，并即时预览物化 CPT。Advanced 编辑模式可以覆盖完整 CPT 或指定行。发生手工覆盖后，系统不得静默重新生成并覆盖专家修改；必须明确执行“恢复生成器结果”操作。

### 5.4 共享来源与 legacy 派生关系的相关性保护

Legacy O8 曾直接组合 O1/O5 score；该 recipe 现按 D-040 只保留为 migration/replay，不进入 active M5 starter scheme。新的 TPX EvidenceVersion 从 raw/session/task sources 自行计算。O13 与其他 evidence 可能复用相同控制/生理信息，H1/H3 共享 gaze-allocation 来源；若把共享来源的 observations 当成完全条件独立证据，仍可能导致后验过度集中。

Starter/legacy metadata 保留下列可配置字段，用于迁移说明或显式 observation-strength policy：

- derived_from；
- dependence_group；
- likelihood_strength。

Legacy reference 中 O8/O13 的 likelihood-strength engineering default 曾为 0.50。若某个新 scheme 明确选择 relation-specific virtual-evidence strength，可把该 EvidenceVersion 产生的 likelihood `L_evidence` 向无信息分布 U=(1/3,1/3,1/3) 收缩：

L_model = s × L_evidence + (1-s) × U

Starter template 中普通 evidence 使用 s=1，H1/H3 可暂以同一 `gaze_allocation` dependence group 和各自 `likelihood_strength=0.50` 做重复计数保护。专家可以在 draft 中修改 strength、选择其他显式 dependence policy，或在 BN 中增加 Evidence variables 之间的 **probabilistic edge** 并提供完整 CPT；后者不是 extraction edge，也不能让一个 EvidenceRecipe 读取另一 Evidence 的 score/state/likelihood。Apply 自动创建改动组件和 scheme 的新 versions，只要求图/CPT 技术可执行，不要求人工审批或 per-edit golden。Dependence strength 不表示数据质量，也不得因表现差而改变 calculation status/availability。

## 6. Evidence 输入、缺失和 observation mode

### 6.1 Missing 不是第四状态

Missing 不得加入 evidence 的 CPT 状态。Evidence 仍然只有 unacceptable、adequate、desired 三状态。

BN 外 metadata 直接保留 AnchorResult v0.2 的 calculation_status：`computed`、`missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`，不再创造第二套近义状态。另设 observation_mode：hard、virtual 或 omitted。

| AnchorResult / 操作 | observation_mode | 说明 |
|---|---|---|
| computed，likelihood 为 one-hot | hard | 注入明确 D/A/U；computed U 与 D/A 同样有效 |
| computed，exact scheme/component versions 显式启用版本化 soft scorer，或应用 dependence strength | virtual | 注入可审计 soft likelihood |
| missing_input、not_applicable、not_computable、dependency_missing、extractor_error | omitted | 不向 BN 注入观测 |
| 用户显式排除 | omitted | calculation_status 不改写；另存 excluded_by_user、actor、timestamp 与可选 note |

`export_pending` 保存在 AnchorResult input snapshot/diagnostics 中，并映射为 `missing_input + source_export_pending` reason。推理引擎对 omitted 节点自动边缘化；未观测的叶 evidence 不应改变 competency posterior。M4 不产生 `invalid_quality`，也不提供 quality coefficient。

### 6.2 Hard evidence 与 virtual evidence

确定性阈值可以产生 one-hot hard evidence，例如：

Desired = (0, 0, 1)

reference-v0.1 的 hard_threshold_v1 scorer 返回 one-hot likelihood。只有 model bundle 显式配置并版本化 soft scorer 时，阈值附近才可返回可审计的 soft likelihood，例如：

(Unacceptable=0.10, Adequate=0.65, Desired=0.25)

Soft likelihood 只能来自显式版本化 scorer，或 §5.4 声明的相关性保护。M5 不根据 residual、coverage、噪声、幅值、生理范围或任何 quality coefficient 向均匀分布收缩 M4 evidence。极差但 computed 的 one-hot U 必须保持方向性。

## 7. 推理流程

一次 session 推理按以下顺序执行：

1. 锁定 `AssessmentSchemeVersion`、全部 exact component version IDs/hashes、operator/engine identity 和 session snapshot；
2. 加载每个 anchor 聚合后的单一 evidence observation，并附带 phase/event breakdown metadata；
3. 校验 calculation status、state order、likelihood、适用性、result/plan/model fingerprints；
4. 把 hard/virtual evidence 注入已编译 BN；
5. 使用 exact variable elimination 或 junction-tree inference；
6. 输出该 scheme 声明的 query/output node posteriors；Hover starter 默认为 11 个 sub-skill 和 4 个 competency；
7. 按 §9 计算 evidence availability coverage、assessability 和 explainability；
8. 保存可复现的 inference record。

输出必须包含 scheme version 与完整 component identities。运行中的模型不能因为用户正在编辑或发布新的 draft 而改变，也不能自动切换到同 concept 的新版本。

## 8. Explainability

### 8.1 Evidence trace

每条 evidence trace 至少包含：

- evidence ID 与名称；
- 原始 anchor 数值和单位；
- 阈值版本；
- M4 raw likelihood、M5 最终 hard/virtual likelihood，以及相关性保护参数；
- calculation status、classification override、computation trace 与 availability；
- phase；
- 关联 sub-skill 路径；
- 使用的 CPT revision；
- 缺失或排除原因。

共享 evidence 必须展示全部 posterior influence paths。例如 O1 的 inference overlay 同时显示：

- O1 → TCP.1 → TCP；
- O1 → PC.1 → PC。

### 8.2 Leave-one-out contribution

默认局部贡献使用 leave-one-out：

Δe(C=proficient) =
P(C=proficient | all evidence)
-
P(C=proficient | all evidence except e)

同时报告：

- 对 proficient 状态的概率变化；
- 对期望 rank 的变化；
- 正向、负向或近零方向；
- 受影响的 sub-skill 和 competency。

Leave-one-out 是当前模型内的敏感性解释，不是因果效应证明。存在 evidence 交互时，可在后续版本增加 Monte Carlo Shapley，但 v0.1 以 leave-one-out 为默认。

## 9. Evidence availability coverage

Coverage 与 posterior、likelihood strength 和信息熵分开计算。每个 evidence-to-sub-skill relation 具有非负 `coverage_weight`，并在相关 sub-skill 内归一化。

~~~text
raw_available_i = 1  iff AnchorResult.calculation_status == computed
raw_available_i = 0  otherwise

model_available_i = 1  iff raw_available_i == 1 and not excluded_by_user
model_available_i = 0  iff applicable evidence is non-computed or user-excluded

model_coverage =
  Σ(weight_i * model_available_i)
  / Σ(weight_i for applicable evidence)
~~~

Desired、Adequate 和 Unacceptable 都贡献完整 raw availability；表现越差不能让 coverage 越低。`not_applicable` 不进入分母。用户排除不改写 M4 result 或 raw availability，但由于该 observation 不进入当前模型推理，model coverage 贡献为 0；系统自动保存 actor/time，note 可选。完全均匀 soft likelihood 仍可作为方向性为零的独立 diagnostic，但不改变“该 evidence 已计算”的 raw availability。

聚合层级固定为：

1. per-sub-skill：使用上式和该 sub-skill 内归一化 relation weights；
2. per-competency：对其 child sub-skills 使用 model profile 中的 subskill_coverage_weight；未配置时等权；
3. overall：对适用的四个 competency 等权；profile 可以显式给权重；
4. per-modality：每条 subskill→evidence relation 的 coverage contribution 按目标 evidence 的 `EvidenceBindingVersion.modality_attribution_weights` 分摊；该 map 只包含 EvidenceVersion source bindings 中的 required core modalities，未配置时对 distinct required core modalities 等分，再在目标 modality 内重新归一化；
5. per-phase：从 AnchorResult.phase_results 的 applicable/available 状态计算数据准备度诊断，不重复注入 BN，也不改变 competency assessability。

系统至少输出：

- overall coverage；
- per-competency coverage；
- per-sub-skill coverage；
- per-phase coverage；
- per-modality coverage；
- raw availability coverage 与 model-used availability coverage；
- model influence/information diagnostic（单独命名，不作为 coverage 或质量）。

默认评估状态：

| Availability coverage | 状态 |
|---:|---|
| ≥ 0.70 | assessable |
| ≥ 0.35 且 < 0.70 | partial |
| > 0 且 < 0.35 | insufficient |
| = 0 | prior_only |

这些 coverage thresholds 是 starter model 的可编辑参数，不是通用 engine 常量或 apply gate。

not_applicable evidence 不进入分母；缺失但本应存在的 evidence 进入分母且贡献为 0。若某个聚合视图的分母为 0，coverage 值为 null、状态为 not_applicable，不能除零或误报 prior_only。`prior_only` 只用于分母>0、没有任何方向性 observation 的 competency/sub-skill。Computed U coverage 必须与 computed D 相同；missing 不能等价于 U。

## 10. CPT 与模型验证

### 10.1 图验证

Apply 前只需满足技术可执行性：

- node ID 唯一且 stable；
- 无 self-loop、duplicate edge 和 directed cycle；
- Guided Mode 每个节点默认最多 3 个 parents；Advanced DAG Mode 默认最多 6 个 parents；
- 每个 active output node 至少有一条可执行 inference path；
- 每个 active evidence node 的 EvidenceRecipe output binding 可解析；
- 每个 active recipe 与 selected BN 可以编译。

4 competencies、11 sub-skills 和 18 evidence 只属于 starter snapshot，不是 generic BN apply gate。Isolated nodes 或不同层级关系可以作为 warning，只要用户选定的输出仍可执行。

### 10.2 CPT 验证

每个 CPT 必须满足：

- parent 顺序、维度和 state cardinality 一致；
- 在物化前计算组合规模；M5 v0 默认上限为 `250_000` probability cells；该上限按部署可配置，不另设与之冲突的固定 row/serialized-size 门；
- 所有值为有限数；
- 0 ≤ p ≤ 1；
- 每一行概率和为 1，容差 1e-9；
- 默认不允许 NaN、Infinity 和负数；
- 若未显式允许 deterministic CPT，每个单元应用最小 epsilon 防止不可恢复的零概率；
- ordered CPT generator 若声明 monotonic contract，则其生成结果必须满足该 operator contract；
- manual non-monotonic CPT 可以 apply，系统只显示非阻断 warning，不要求 reviewer waiver。

这是本地 runtime 的可配置技术资源上限，不是科学限制。超过当前上限返回稳定的 cell-limit diagnostic 并说明所需单元格数；调整部署级上限不需要改变模型科学状态，但应先确认本机能够执行，避免 Advanced DAG 使内存失控。

### 10.3 生成器参数验证

- wi ≥ 0；
- Σwi = 1，容差 1e-9；
- 0 ≤ λ ≤ 1；
- 0.05 ≤ σ ≤ 2.00；
- likelihood_strength ∈ (0,1]；
- materialized table hash 必须与参数和 override 一致。

### 10.4 Evidence 单调与缺失回归

以下检查只适用于研究团队希望验证 starter profile 的科学/行为属性时，不是普通 edit/apply 或平台发布门：

- 将任一 computed D/A observation 改为 U，不得提高其相关 sub-skill/competency 的 proficient posterior；
- 多个 U 累积不得被 quality/coverage 机制拉回 prior；
- 18 个 computed U 时，四项 competency 的 proficient posterior 均低于对应 prior/no-evidence 结果；
- missing observation 只被边缘化，不能等价为 U；
- 18 个 computed U 的 raw availability 与 model-weighted availability coverage 均为 100%；
- O8/O13 strength 和 H1/H3 dependence policy 只改变重复计数强度，不改变 calculation status 或 availability。

## 11. Version、自动审计与可复现性

每个 applied `AssessmentSchemeVersion` 至少保存：

- scheme ID/version ID 与 schema version；
- parent scheme version、apply 前 draft ID 与最终 graph version；
- exact TaskProfile、EvidenceVersion、EvidenceBindingVersion、BnNodeVersion、CptVersion IDs 与 content hashes；
- operator/engine requirements；
- scheme lifecycle、software verification、scientific validation 与 permitted use；
- created_by、created_at、可选 note、structured diff；
- canonical scheme hash。

每次正式 assessment inference 保存：

- session ID 和输入 hash；
- applied scheme version ID；executable draft 可以 preview，但不能覆盖 published scheme 的历史结果；
- recipe/operator/BN node/CPT/binding exact version identities；
- observation、calculation status、override、availability 与 dependence handling；
- AnchorResult phase/event breakdown metadata；
- inference-engine version；
- 输出 posterior、coverage 和 explanation。

Published component/scheme versions 不可原地修改。任何修改都从任意历史 scheme 创建或恢复 autosaved draft；apply 采用 copy-on-write，原子形成改动组件的新 versions 和新的 immutable scheme version。未改组件继续引用原 exact versions。

## 12. 配置示例

~~~yaml
scheme_version_id: hover-starter-scheme-v0.1.0
task_profile_version_id: hover-profile-v0.1.0
model_id: pilot_assessment_bn
model_version: 0.1.0
state_sets:
  latent: [at_risk, developing, proficient]
  evidence: [unacceptable, adequate, desired]
competency_priors:
  TCP: [0.3333333333, 0.3333333333, 0.3333333334]
  PC:  [0.3333333333, 0.3333333333, 0.3333333334]
  SM:  [0.3333333333, 0.3333333333, 0.3333333334]
  OC:  [0.3333333333, 0.3333333333, 0.3333333334]
evidence:
  - id: O1
    parents: [TCP.1, PC.1]
    phase_applicability: [translation, deceleration, hover_stabilization]
    cpt:
      mode: generated
      generator_type: ranked_gaussian
      weights:
        TCP.1: 0.50
        PC.1: 0.50
      weakest_link: 0.50
      sigma: 0.60
~~~

## 13. 非科学验证声明

pilot-assessment-bn v0.1 是一套工程上可执行、概率上自洽、便于专家修改的初始计算模型，不是已经验证的航空人员评估标准。

当前默认结构、anchor 定义、阈值、先验和 CPT：

- 尚未经过足量专家一致性评审；
- 尚未用足量受试者数据完成 calibration、discrimination 和 external validation；
- 不得单独用于执照、适航、人员淘汰或安全关键决策；
- 不能把 posterior probability 解释为现实世界“正确概率”；
- 不能把 coverage 解释为模型准确率。

系统的职责是把所有假设显式化、版本化、可审计化，并为后续专家优化和实验验证提供稳定平台。
