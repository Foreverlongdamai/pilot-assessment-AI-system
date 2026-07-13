# 05 贝叶斯网络与 CPT 设计

## 1. 文档状态

- 文档版本：1.0
- 对应模型版本：pilot-assessment-bn v0.1
- 状态：第一版可实现设计，尚未实现或科学验证；2026-07-13 已与 accepted D-021～D-025 的 M4 evidence 语义对齐
- 核心节点数：33
  - 4 个 aggregate competency 节点
  - 11 个 latent sub-skill 节点
  - 18 个 observed evidence 节点
- 上下文：Translation、Deceleration、Hover stabilization 三阶段。Phase 是已知上下文，不计入 33 个能力评估节点。

本设计的目标不是声明当前模型已经得到航空专家或实验数据验证，而是先建立一套可运行、可检查、可修改、可扩展的概率计算逻辑。后续专家可以在不修改推理引擎的情况下调整节点、边、anchor 算法、阈值、CPT 和 phase 参数。

## 2. 建模原则

### 2.1 生成方向与推理方向

网络的生成方向必须是：

Competency → Sub-skill → Evidence

含义是：不可直接观测的整体能力影响子技能表现，子技能表现再影响可以观测到的 anchor evidence。

实际评估时使用贝叶斯反演：

Observed evidence → posterior of sub-skill → posterior of competency

前端画布中箭头必须显示生成方向，不能因为推理从 evidence 返回 competency 就把网络箭头反过来。

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

以上映射构成 v0.1 的默认语义结构。图编辑器可以在 draft 中修改结构，但每个发布 revision 都必须保存自己的完整节点、边和 CPT。

## 4. Phase context

Translation、Deceleration 和 Hover 是已知任务上下文，不是能力节点，也不是第四种 evidence 状态。v0.1 中它们只用于 AnchorPlugin 内部计算 phase breakdown、applicability 和聚合规则。

默认 BN 严格保持 33 个语义节点，并使用：

P(E_session | parent sub-skills)

每个 anchor 每个 session 只向对应 evidence node 提交一次聚合 observation。AnchorResult v0.2 保存逐 phase 数值、calculation status、override 和 source trace，再按该 anchor 的 aggregation policy 形成单一 D/A/U likelihood。不得把 T/D/H 三条结果重复注入同一个静态 evidence node，否则会覆盖观测或重复计算证据。v0.1 inference 只使用 base/session-aggregate CPT，不选择 translation/deceleration/hover CPT slice。

未来若专家确实需要 phase plate，必须发布新的 model profile：显式 unroll 为具有稳定 instance ID 的节点（例如 O1@translation），定义共享 latent parents、跨 phase 依赖和 fusion 规则，并相应改变节点数与 major model version。它不是 reference-v0.1 的默认推理方式。前端的 phase selector 只查看 AnchorResult breakdown，不改变本版推理图。

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

所有共享 anchor 首版均采用等权和 λ=0.50，作为不预先偏向任一 parent 的透明工程默认。专家可以在前端按内容审查或校准结果调整权重、weakest-link 强度和 σ；修改后必须生成新的 model revision。

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
- revision、author、timestamp、reason。

Guided 编辑模式修改生成器参数，并即时预览物化 CPT。Advanced 编辑模式可以覆盖完整 CPT 或指定行。发生手工覆盖后，系统不得静默重新生成并覆盖专家修改；必须明确执行“恢复生成器结果”操作。

### 5.4 派生 anchor 的相关性保护

O8 使用 O1 和 O5 的信息，O13 使用 O1/O5/O7 与 H4 trace；H1/H3 共享同一 gaze-allocation 时长。若把它们和来源/共享 anchor 当成完全条件独立证据，可能导致后验过度集中。

v0.1 为派生 anchor 保留以下可配置字段：

- derived_from；
- dependence_group；
- likelihood_strength。

默认 O8 和 O13 的 likelihood_strength s 均为 0.50。直接使用 M4 产生的版本化 anchor likelihood `L_anchor`，再向无信息分布 U=(1/3,1/3,1/3) 收缩：

L_model = s × L_anchor + (1-s) × U

普通非派生 evidence 使用 s=1。H1/H3 声明同一 `gaze_allocation` dependence group；`reference-model-v0.1` 的冻结默认是 H1、H3 各自 `likelihood_strength=0.50`，分别对其 M4 likelihood 使用同一凸混合公式，使这对高度相关的 gaze-allocation evidence 合计不按两个完全独立 one-hot 计数。该 strength 对 H1/H3 连接的所有 parent 一致；若专家需要 relation-specific dependence，必须发布支持该语义的新 major profile。上述凸混合只防止相关证据重复计数，不表示数据质量，也不得因表现差而改变 calculation status/availability。Reference-model-v0.1 不允许 evidence-to-derived-evidence 结构边；若未来建立明确 CPT，必须切换到声明 structural dependence 语义的新 major model profile，并提供编译与 golden tests，不能只发布同 profile 的新 revision。

## 6. Evidence 输入、缺失和 observation mode

### 6.1 Missing 不是第四状态

Missing 不得加入 evidence 的 CPT 状态。Evidence 仍然只有 unacceptable、adequate、desired 三状态。

BN 外 metadata 直接保留 AnchorResult v0.2 的 calculation_status：`computed`、`missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`，不再创造第二套近义状态。另设 observation_mode：hard、virtual 或 omitted。

| AnchorResult / 操作 | observation_mode | 说明 |
|---|---|---|
| computed，likelihood 为 one-hot | hard | 注入明确 D/A/U；computed U 与 D/A 同样有效 |
| computed，model revision 显式启用版本化 soft scorer，或应用 dependence strength | virtual | 注入可审计 soft likelihood |
| missing_input、not_applicable、not_computable、dependency_missing、extractor_error | omitted | 不向 BN 注入观测 |
| 用户显式排除 | omitted | calculation_status 不改写；另存 excluded_by_user、reason、actor 与 audit ID |

`export_pending` 保存在 AnchorResult input snapshot/diagnostics 中，并映射为 `missing_input + source_export_pending` reason。推理引擎对 omitted 节点自动边缘化；未观测的叶 evidence 不应改变 competency posterior。M4 不产生 `invalid_quality`，也不提供 quality coefficient。

### 6.2 Hard evidence 与 virtual evidence

确定性阈值可以产生 one-hot hard evidence，例如：

Desired = (0, 0, 1)

reference-v0.1 的 hard_threshold_v1 scorer 返回 one-hot likelihood。只有 model bundle 显式配置并版本化 soft scorer 时，阈值附近才可返回可审计的 soft likelihood，例如：

(Unacceptable=0.10, Adequate=0.65, Desired=0.25)

Soft likelihood 只能来自显式版本化 scorer，或 §5.4 声明的相关性保护。M5 不根据 residual、coverage、噪声、幅值、生理范围或任何 quality coefficient 向均匀分布收缩 M4 evidence。极差但 computed 的 one-hot U 必须保持方向性。

## 7. 推理流程

一次 session 推理按以下顺序执行：

1. 锁定 model revision、graph hash、CPT hash 和 anchor-config hash；
2. 加载每个 anchor 聚合后的单一 evidence observation，并附带 phase/event breakdown metadata；
3. 校验 calculation status、state order、likelihood、适用性、result/plan/model fingerprints；
4. 把 hard/virtual evidence 注入已编译 BN；
5. 使用 exact variable elimination 或 junction-tree inference；
6. 输出 11 个 sub-skill posterior 和 4 个 competency posterior；
7. 按 §9 计算 evidence availability coverage、assessability 和 explainability；
8. 保存可复现的 inference record。

输出必须包含模型 revision。运行中的模型不能因为用户正在编辑新的 draft 而改变。

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

共享 evidence 必须展示全部路径。例如 O1 同时显示：

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

Desired、Adequate 和 Unacceptable 都贡献完整 raw availability；表现越差不能让 coverage 越低。`not_applicable` 不进入分母。用户排除不改写 M4 result 或 raw availability，但由于该 observation 不进入当前模型推理，model coverage 贡献为 0，并必须保存 actor/reason/audit ID。完全均匀 soft likelihood 仍可作为方向性为零的独立 diagnostic，但不改变“该 evidence 已计算”的 raw availability。

聚合层级固定为：

1. per-sub-skill：使用上式和该 sub-skill 内归一化 relation weights；
2. per-competency：对其 child sub-skills 使用 model profile 中的 subskill_coverage_weight；未配置时等权；
3. overall：对适用的四个 competency 等权；profile 可以显式给权重；
4. per-modality：每条 subskill→evidence relation 的 coverage contribution 按目标 evidence 的 `AnchorBinding.modality_attribution_weights` 分摊；该 map 只包含 binding 的 required core modalities，未配置时对 distinct required core modalities 等分，再在目标 modality 内重新归一化；
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

not_applicable evidence 不进入分母；缺失但本应存在的 evidence 进入分母且贡献为 0。若某个聚合视图的分母为 0，coverage 值为 null、状态为 not_applicable，不能除零或误报 prior_only。`prior_only` 只用于分母>0、没有任何方向性 observation 的 competency/sub-skill。Computed U coverage 必须与 computed D 相同；missing 不能等价于 U。

## 10. CPT 与模型验证

### 10.1 图验证

发布前必须满足：

- node ID 唯一且 stable；
- 4 个 required competency 存在；
- 默认 v0.1 profile 包含 11 个 sub-skill 和 18 个 evidence；
- 无 self-loop、duplicate edge 和 directed cycle；
- Guided Mode 每个节点默认最多 3 个 parents；Advanced DAG Mode 默认最多 6 个 parents；
- 每个 sub-skill 可追溯到至少一个 competency；
- 每个普通 evidence 至少有一个 latent parent；
- 每个 published competency 至少有一个有效 evidence path；
- 每个 anchor 对适用 phase/event/window 的 session 聚合规则完整且唯一。

### 10.2 CPT 验证

每个 CPT 必须满足：

- parent 顺序、维度和 state cardinality 一致；
- 在物化前计算组合规模；默认上限为 4096 rows、16384 probability cells 和 2 MiB serialized CPT；
- 所有值为有限数；
- 0 ≤ p ≤ 1；
- 每一行概率和为 1，容差 1e-9；
- 默认不允许 NaN、Infinity 和负数；
- 若未显式允许 deterministic CPT，每个单元应用最小 epsilon 防止不可恢复的零概率；
- ordered CPT 通过单调性检查：父节点 rank 提高时，子节点期望 rank 不应下降；
- manual override 若违反单调性，draft 可以保存 warning；publish 必须附 monotonicity_waiver（reviewer、reason、affected rows、scientific rationale）。没有 waiver 则阻止 publish，不得静默接受。

这些是 v0.1 的可配置工程安全上限，但不能由单个 draft 临时绕过。提高上限需要新的 model profile、性能/内存测试和审批；超过限制返回 CPT_SIZE_LIMIT_EXCEEDED，避免 Advanced DAG 编辑使验证或推理因指数增长而失控。

### 10.3 生成器参数验证

- wi ≥ 0；
- Σwi = 1，容差 1e-9；
- 0 ≤ λ ≤ 1；
- 0.05 ≤ σ ≤ 2.00；
- likelihood_strength ∈ (0,1]；
- materialized table hash 必须与参数和 override 一致。

### 10.4 Evidence 单调与缺失回归

Reference profile 发布前还必须证明：

- 将任一 computed D/A observation 改为 U，不得提高其相关 sub-skill/competency 的 proficient posterior；
- 多个 U 累积不得被 quality/coverage 机制拉回 prior；
- 18 个 computed U 时，四项 competency 的 proficient posterior 均低于对应 prior/no-evidence 结果；
- missing observation 只被边缘化，不能等价为 U；
- 18 个 computed U 的 raw availability 与 model-weighted availability coverage 均为 100%；
- O8/O13 strength 和 H1/H3 dependence policy 只改变重复计数强度，不改变 calculation status 或 availability。

## 11. Version、审计与可复现性

每个 published model revision 至少保存：

- model_id；
- schema_version；
- revision_id；
- parent_revision_id；
- 发布前 draft_id 与最终 graph_version；
- graph、CPT、anchor config 各自的 content hash；
- revision_lifecycle：published、archived 或 superseded；
- software_verification_status、scientific_validation_status 与 permitted_use；
- created_by、created_at、reason；
- canonical model hash。

每次正式 assessment inference 保存：

- session ID 和输入 hash；
- published revision_id；draft 只允许执行明确标记的 validation/smoke preview，不能生成正式结果；
- graph/CPT/anchor hashes；
- observation、calculation status、override、availability 与 dependence handling；
- AnchorResult phase/event breakdown metadata；
- inference-engine version；
- 输出 posterior、coverage 和 explanation。

Published revision 不可原地修改。任何修改都从已发布 revision 创建新 draft。

## 12. 配置示例

~~~yaml
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
