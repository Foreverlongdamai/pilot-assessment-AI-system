+++
document_id = "PAS-EXPERT-BN-001"
language = "zh-CN"
title = "BN、父节点、状态与 CPT 专家手册"
short_title = "BN 与 CPT 手册"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["expert", "developer"]
information_types = ["tutorial", "how-to", "reference", "explanation"]
scope = "说明如何在共享 system model 中设计贝叶斯网络拓扑、ordered states 与 conditional probability tables。"
prerequisites = ["理解基础概率概念", "已经形成针对目标评估任务的明确专家假设"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-EXPERT-EVIDENCE-001", "PAS-EVALUATOR-001", "PAS-PYTHON-CORE-001"]
support = "记录 child node 名称、ordered parents、ordered states、出错 CPT row 和稳定 validation error。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.2"
user_acceptance = "pending"
+++

# BN、父节点、状态与 CPT 专家手册

## 1. 区分提取关系与概率关系

产品包含两类有明确类型的图关系：

- **data/extraction dependency** 表示 EvidenceRecipe 读取哪些 raw 或 derived Session resources；
- **probabilistic edge** 表示哪些随机变量用于条件化 child 的 conditional probability distribution。

Raw Input 不是 Bayesian random variable，也没有 CPT。系统先从 Session 数据提取 Evidence observation，再由 BN 使用 observation 条件化潜在能力分布。为了避免歧义，编辑器和合同不会把这两种关系都简单称为“父节点”。

## 2. 使用正确的 BN 方向

Starter model 采用生成式贝叶斯网络：

```text
Competency  ->  Sub-skill  ->  Evidence observation
```

对于每条 `parent -> child` 概率边，child 保存 `P(child | ordered parents)`。实际评估时观察到 Evidence，再通过同一 joint distribution 和 Bayes' rule 更新隐藏的 Sub-skill 与 Competency posterior。因此信息影响会由观察 Evidence 传向能力，但保存的箭头不能反转。

画布从左到右是便于人理解的工作流布局：Raw Input、Extracted Data、Evidence、Sub-skill、Competency。Canonical probabilistic arrows 可能从右指向左。不能只为迎合视觉上的计算顺序而反转网络。

## 3. 完整节点父关系规则

每个 Evidence 或 BN 节点都有一组 ordered probabilistic parents，它属于全局完整定义。任务方案可以启用或停用节点，但不能替换其 parents。

- starter Competency 通常是带 prior CPT 的 root node；
- Sub-skill 通常有一个或多个 Competency parents；
- Evidence observation 通常有一个或多个 Sub-skill parents；
- 引擎也允许满足 typed contract 的其他无环 Evidence/BN 关系，因此 starter hierarchy 不是引擎基数限制。

如果另一任务需要不同父关系，应复制 child、修改副本并在新方案启用。只有节点含义、states、parents 与 CPT 完全相同时，跨方案共享才是安全的。

## 4. 编辑 BN 节点

[[SCREENSHOT:ui-bn-cpt-editor]]

打开节点的可移动、可缩放浮动编辑器，可同时保留多个窗口比较。可修改内容包括：

- canonical English name、short name 与 description；
- role（`Sub-skill` 或 aggregate `Competency`）；
- ordered states 及其简洁英文 labels/descriptions；
- ordered probabilistic parents；
- CPT mode、probabilities 与 generator metadata；
- documentation、reporting metadata、provenance 与 expert help text。

Evidence observation 节点也包含同样的概率解释区域。其 recipe/data bindings 负责算出 observation；其 probabilistic parents 与 CPT 描述 observation 在潜在 BN states 条件下的分布。

## 5. 先定义 states，再设计 CPT

每个变量至少需要两个唯一、稳定的 state IDs。状态顺序具有语义，因为它决定 CPT columns 和每个 parent axis。应使用专家能够区分的小集合，例如 `LOW`、`MEDIUM`、`HIGH`，不要只依赖颜色或显示位置。

修改 states 前：

1. 记录每个 state 的含义；
2. 明确顺序是否代表能力递增或其他轴；
3. 检查所有把该 state axis 用于 CPT 的 downstream children；
4. 在同一 staged change 中更新受影响 CPT。

重命名 display label 不等于改变 state ID 或含义。语义变化通常应复制成新节点，以保持旧任务方案可解释。

## 6. 填写并核验 CPT

对于 child `C` 与 ordered parents `P1 ... Pn`，编辑器会为 parent states 的每个 Cartesian product 建立一行。没有 parent 时只有一行 prior；columns 按 child state order 排列。

每个 complete row 必须：

- 对每个 child state 有一个 finite probability；
- 每个概率在 `[0, 1]`；
- 在引擎 tolerance 内总和为 `1`；
- 与显示的 ordered parent-state combination 对齐。

行数为：

```text
rows = product(number of states for each ordered parent)
```

即使 parent set 相同，改变 parent order 也会改变每一行的解释。应审阅 row headers，不能盲目复制数字块。`INCOMPLETE` mode 可保存未完成设计，但 technical preflight 会阻止任何依赖 non-materialized CPT 的 run。

## 7. 保持 DAG

贝叶斯网络必须是 directed acyclic graph（DAG）：沿概率箭头前进不能回到起点。Self-parenting 与 cycle 会被拒绝，因为它们无法形成当前引擎支持的 joint factorization。

父关系修改产生 cycle 时，应重新设计结构，不能通过反转无关箭头绕过 validation。Extraction dependencies 单独校验，不会把 raw variables 插入 BN。

## 8. Activation 与 missing observations

启用 child 会自动启用全部 fixed probabilistic parents 与执行所需 extraction inputs。停用有 active descendants 的 parent 时必须确认；继续后会停用受影响 downstream closure。

运行时，active Evidence 仍可能因为 Session 缺少模态而 unavailable。这不会产生一张新图。Inference engine 会边缘化未观察 Evidence，并使用全部已有 observations；绝不会把缺失 Evidence 变成 `DESIRED`、`UNACCEPTABLE` 或数值零。

## 9. Validation 能证明什么

软件检查 types、identities、state-axis alignment、probability normalization、acyclicity、activation closure 与 execution readiness。它不能证明 causal assumption 正确、CPT 代表目标人群或 posterior 可用于运行决策。

附带 CPT 都是 starter values。领域专家仍负责 elicitation、data analysis、sensitivity analysis、fairness 与 scientific approval。在本候选阶段之外完成这些工作前，应保持 `formal_run_authorized=false`。

## 10. BN 专家检查单

- [ ] 未混用 extraction dependencies 与 probabilistic parents；
- [ ] canonical arrows 正确编码 `P(child | parents)`；
- [ ] 图保持 acyclic；
- [ ] 每个完整节点只有一组 fixed ordered parents；
- [ ] state IDs、含义和顺序明确；
- [ ] CPT row count 与 axes 匹配声明 states；
- [ ] 每个 materialized row 总和为一；
- [ ] 改 states/parents 后已检查 affected downstream CPTs；
- [ ] missing observation 被解释为缺失而非表现差；
- [ ] scientific claims 与 contract validation 分开。
