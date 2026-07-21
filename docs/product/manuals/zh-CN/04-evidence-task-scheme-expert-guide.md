+++
document_id = "PAS-EXPERT-EVIDENCE-001"
language = "zh-CN"
title = "Evidence 与任务方案专家设计手册"
short_title = "Evidence 与任务方案"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["expert", "developer"]
information_types = ["tutorial", "how-to", "reference", "explanation"]
scope = "说明专家如何通过五层模型画布和暂存编辑会话设计全局共享 Evidence 节点与任务方案。"
prerequisites = ["理解目标仿真任务", "具有修改共享 system model 的权限"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-EXPERT-BN-001", "PAS-SESSION-001", "PAS-PYTHON-EXT-001"]
support = "报告编辑器问题前，记录节点名称、节点类型、任务方案、edit-session 状态和稳定错误码。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Evidence 与任务方案专家设计手册

## 1. 设计模型

本系统是供专家设计评估网络的框架。安装时附带的节点只是 starter content，并不是受保护的科学真理。专家可以建立大量全局共享节点，再由每个任务方案启用适合该任务的组合。

每个完整节点只有一个 identity、一个 canonical English name、一份 definition 和一组 fixed parents。同一节点可以被多个方案共享。如果新任务需要不同父节点、参数或含义，应复制节点、重命名副本并修改，而不是让一个节点根据当前方案产生不同内部行为。

例如 `Trajectory Precision`、`Hover Trajectory Precision` 与 `Straight Flight Trajectory Precision` 可以并列存在。它们可能很相似，但系统把它们视为完全不同的对象，从而保存每套任务设计，无需来回覆盖。

## 2. 理解五层画布

[[SCREENSHOT:ui-five-layer-model-studio]]

主画布从左到右排列为：

1. **Raw Input**：五类源数据 `X(t)`、`U(t)`、`I(t)`、`G(t)` 和 `P(t)`；
2. **Extracted Data**：可复用的中间信号或 event/segment 产品；
3. **Evidence**：可观测的任务表现及其 observation mapping；
4. **Sub-skill**：潜在 BN 子技能节点；
5. **Competency**：聚合 BN 能力节点。

Raw Input 节点更大并统一使用绿色，其他节点按各自类别显示。Operator 实现不是主图节点；Evidence 或 Extracted Data 编辑器会展示自己使用的 operator recipe。

类型筛选器只使用上述五类。用户可平移、缩放画布；按住节点并移动至少 4 px 即可调整其持久化位置，普通点击仍用于选择。布局属于展示元数据，移动节点不会改变 fixed parents。

## 3. 新增、复制与删除节点

点击“新建节点”并选择层级，填写简洁的 canonical English name、short name 和 description。技术 ID 由后端生成，只用于 diagnostics/provenance，不在普通标签中展示。

复制粘贴是定制 starter content 的首选路径：

1. 选择来源节点并复制；
2. 切换到目标任务方案；
3. 粘贴并创建一个新的完整节点；
4. 重命名并修改新 definition；
5. 在该方案启用副本、停用旧节点。

默认情况下，复制节点继续引用原来的 fixed parents。只有当它确实成为另一完整节点时才修改父节点。删除全局节点比在方案中停用更强。选中节点后使用工具栏或右键菜单中的“从系统模型删除节点”；确认后，后端会在一个暂存事务中把该节点和依赖它的下游节点从所有受影响任务方案的 active closure/output 中移出，再归档全局节点。状态栏会报告受影响方案数量。该动作可以 Ctrl+Z 撤销，并且只有“保存全部”才进入 canonical system；“放弃全部”会恢复删除前状态。Historical RunSnapshots 始终不可变。

## 4. 编辑 Evidence 节点

[[SCREENSHOT:ui-evidence-node-editor]]

双击或打开节点会出现可独立移动、缩放的浮动编辑窗口，可同时打开多个窗口并排比较。可修改内容包括：

- canonical English name、short name、description 与 expert help text；
- fixed Raw Input 或 Extracted Data parents；
- EvidenceRecipe operator graph 与 typed parameters；
- time/event/window selectors 和 missing-input policy；
- continuous output definition，以及计算方法明确声明的单位；
- observation states 与 continuous-to-state mapping；
- trace/provenance presentation metadata。

界面标签可以在中英文之间切换，但持久模型内容只有一份 canonical English value。不要在模型中再填写第二套中文节点名。

Evidence 节点只能依赖 Raw Input 和/或 Extracted Data 产品，不能依赖 Sub-skill 或 Competency。计算方向是数据到 Evidence；后续贝叶斯推理再使用这个 observation 条件化潜在能力。

## 5. 理解 recipe 与 operator

EvidenceRecipe 是由已注册 operators 组合出的声明式计算。Operator 是可复用机制，例如选择事件区间、解析 signal、测量 AOI dwell、计算 error 或对窗口聚合。参数属于节点 recipe，通常可直接在前端修改，不需要改 Python。

例如，“发生扰动后是否查看指定仪表区域”的 Evidence 可以按以下步骤计算：

1. 从 annotations 选择 disturbance interval；
2. 解析该区间的 gaze/AOI samples；
3. 判断是否位于 target AOI；
4. 计算 first-fixation latency 或 dwell duration；
5. 把 continuous value 映射为 D/A/U states。

只有现有 operator catalog 无法表达真正的新计算机制时，才按照 [[DOC:PAS-PYTHON-EXT-001]] 增加 Python 源码，重启应用后再在 recipe 中引用新 operator。

## 6. 设计任务方案

任务方案保存名称、描述、activation set、active edges 与展示布局引用；它不私有复制每个节点。所有方案在左侧栏并列存在，可随时切换和编辑，不设置额外的“发布”生命周期。

可复制现有方案或从新选择开始。复制方案只复制 selection 与 layout，不复制全局 node objects。后续修改共享节点会影响所有启用它的方案；历史 runs 因为保存 frozen snapshots 而不受影响。

启用子节点时，全部 fixed ancestors 会无提示自动启用。停用仍有 active descendants 的父节点时，UI 必须列出受影响后代并询问继续或取消；继续则在该方案停用 dependent downstream closure。

边由 complete-node fixed parents 与 scheme activation 推导。方案不能覆盖节点父关系。需要不同关系时，应复制子节点并修改副本的 fixed parents。

## 7. 暂存、撤销与保存

模型修改进入一个 durable system-level edit session，不写入当前 user project，也不会逐字段立即提交。

- `Ctrl+Z` 撤销最新 staged command；条件允许时可 redo；
- “保存全部”以原子方式提交全部暂存模型，供所有 project 的未来 run 使用；
- “放弃全部”恢复到上次已保存模型；
- 有更改时关闭会询问保存并关闭、放弃并关闭或取消。

如果保存遇到 stale optimistic revision，应 reload 或 rebase，不应覆盖并发保存状态。创建 run 前必须保持 clean saved model，使 snapshot 唯一明确。

## 8. 科学审查职责

软件只验证 contracts、acyclicity、parameter types 与 executability；它不会判断 Evidence 是否真正测量目标技能、阈值是否公平、任务方案是否适用于训练决策。

应在节点 description/help text 和项目研究文档中记录目标任务、operational event、population、units、rationale 与 review owner。在本工程候选之外改变 `formal_run_authorized` 前，必须使用受控数据并经过专家科学审查。

## 9. 专家检查单

- [ ] 每个节点只有一个完整含义和一组 fixed parents；
- [ ] canonical model text 使用英文；
- [ ] task-specific variation 使用复制出的独立节点；
- [ ] Evidence parents 只属于 Raw Input 或 Extracted Data；
- [ ] operator parameters 与 observation mapping 明确；
- [ ] scheme ancestor closure 完整；
- [ ] 停用前已检查 downstream impact；
- [ ] staged changes 已检查并原子保存；
- [ ] 科学依据与软件验证结果分开记录。
