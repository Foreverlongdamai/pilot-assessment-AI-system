# Design Self-Review Report

| 字段 | 值 |
|---|---|
| 设计基线 | 产品 v0.1；M4 已批准设计 v0.2 与已接受轻量验证修订 |
| 审查日期 | 原始审查 2026-07-10；M4 amendment 2026-07-13 |
| 审查范围 | pilot_assessment_system 产品文档、项目入口说明、历史草案状态与 M4 跨文档一致性 |
| 结论 | M1–M3 可作为已验证交接基线；M4 书面设计与轻量验证修订已获批准，replacement Task 0–6 与 M4-A contract/schema slice 已完成，但 M4 仍未工程验证 |
| 软件状态 | 2026-07-10 审查时尚无实现；截至 2026-07-13，M1/M2/M3 已工程验证，M4 Task 0–6 与 14 个 package schema resources 已完成，catalog/canonical identity Task 7–8 尚未完成且 0/18 production plugins 已实现，`formal_run_authorized=false`，完整 Core alpha 与 Gate B 仍未完成，见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) |
| 科学状态 | 参考评估模型为 engineering_default；synthetic fixture 为 not_supported |
| M4 修订 | 2026-07-13 完成 anchor-computation、lightweight-workflow 与 Task 3 candidate-binding amendments 并获批准；D-026–D-028 与 replacement plan 已接受；replacement Task 0–6 已分别由 `bc544bf`、`f56365c`、`928e9a4`、`e054620`、`1528d09`、`b63d38b`、`93c4ddb` 完成，下一步为 Task 7 exact-18 catalog/parameter resources；18/18 specified、0/18 production plugins 已实现，M4 尚未 engineering verified，无科学有效性声明 |

## 1. 结论边界

本文固定记录 2026-07-10 的**产品与计算设计闭环**审查，表格中的审查日期不随实现推进而改写；当前实现状态仅作后续注记。本文不是软件实现验收，也不是航空评估科学有效性证明。后续实现证据以 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) 为准。2026-07-13 M4 amendment 见第 7 节；它重新打开并关闭了旧 reference-v0.1 quality-gate 语义冲突，对 M4 的状态、计算和验收规则具有优先级，但规格获批本身不表示生产代码已经实现。Replacement Task 0–6 的独立实现证据分别以提交 `bc544bf`、`f56365c`、`928e9a4`、`e054620`、`1528d09`、`b63d38b`、`93c4ddb` 为准。

通过本轮自审后，文档已经能够让接手者明确：

- 系统处理哪些 session 数据，特别是 I(t)、G(t)、EEG、ECG 和 pilot camera；
- 18 个 reference anchors 如何计算、聚合、评分和处理缺失；
- 33-node reference BN 如何定义 state、CPT、共享 evidence、coverage 和解释；
- 用户如何在 WinUI 中新增、删除、移动 node/edge，并修改 binding、参数和 CPT；
- 后端如何以 draft transaction、graph_version、layout_version 和 immutable revision 保持一一对应；
- 正式 run、non-formal preview、结果 provenance 和验证状态如何区分。

原始 2026-07-10 的结论只适用于当时产品设计闭环。2026-07-13 的 M4 anchor-computation amendment 已按独立复审修订其 P1 歧义并获得用户批准；其后获批的 lightweight-workflow amendment 又取代了原实施计划中的重 fixture 路线。Replacement plan 与 Task 3 candidate-binding amendment 也已于 2026-07-13 单独获批，D-028 收口了 M3/reference provenance 与三参数 binder；Task 0–6 与 M4-A contract/schema slice 已完成，下一步为 Task 7 exact-18 catalog/parameter resources，canonical identity 仍属 Task 8。默认阈值、拓扑和 CPT 仍等待专家与数据校准。

## 2. 审查方法

执行了三层审查：

1. 主审：逐文档核对产品、数据、anchor、BN、graph editor、runtime、frontend 与验证合同；
2. 独立审查：由不负责最终整合的审查任务检查公式、状态、协议、链接和运行边界；
3. 机器检查：解析 JSON/YAML 示例、检查 Markdown fence/相对链接、统计 model IDs，并搜索旧口径和占位符。

严重度定义：

- P0：会使产品目标、数据安全或模型结论根本错误；
- P1：会让两个合规实现得到不同结果，或使跨组件合同无法闭环；
- P2：不阻断实现，但影响可维护性、体验或后续扩展。

## 3. 已发现并关闭的问题

| ID | 问题 | 处理结果 |
|---|---|---|
| SR-01 | 根说明仍使用 FastAPI、H1–H6、旧目录和 CSV-only 边界 | 更新 CLAUDE.md；历史草案标记 SUPERSEDED |
| SR-02 | 18/19 anchor、O2/O4/H4/H5/H6 口径漂移 | 锁定 O1–O13 + H1–H5；旧 H6 删除 |
| SR-03 | Competency state 与单父 CPT 初值不一致 | 锁定 at_risk/developing/proficient 和 0.79/0.20/0.01 等默认表 |
| SR-04 | 同一 anchor 的 phase observation 可能重复注入 BN | v0.1 每 anchor 每 session 只提交一个聚合 observation；phase 只保留 breakdown |
| SR-05 | stream lifecycle、Anchor calculation status 与 BN state 混用 | 固定三层语义：M1–M3 stream 状态；M4 v0.2 的 computed/missing_input/not_applicable/not_computable/dependency_missing/extractor_error；BN 只接收 computed D/A/U |
| SR-06 | draft、published revision、科学状态和 permitted use 混装 | 拆成 draft_validation_state、revision_lifecycle、verification/scientific status 与 permitted_use |
| SR-07 | graph/CPT/anchor 参数使用不同版本与写路径 | 所有 semantic mutation 共用 graph_version 和 graph.operations.apply；layout_version 独立 |
| SR-08 | mutation 重试可能重复执行 | 所有 mutation 使用 transaction_id 兼作 idempotency key |
| SR-09 | 新增/删除 edge 与 state change 的 CPT 迁移不唯一 | 定义 neutral replication、weighted marginalization、M/R/q state migration 与 preview |
| SR-10 | Advanced DAG 可能造成 CPT 指数爆炸 | 后端硬限制 parent、rows、cells 和 serialized size |
| SR-11 | 新 evidence node 没有后端 binding 闭环 | 增加 AnchorBinding DTO、binding operations、safe formula 和 trusted plugin 流程 |
| SR-12 | 节点拖拽位置与科学模型版本混用 | 定义 layout.update、expected_layout_version、批量 drag-end 提交和 layout hash |
| SR-13 | draft preview 可能被当作正式结果 | run.start 仅接受 published revision；run.preview 固定 draft_id+graph_version 且 non_formal |
| SR-14 | AnchorResult 缺连续分数、likelihood、override、trace 和逐窗 artifact 的确定规则 | 定义 breaking AnchorResult v0.2、hard_threshold_v1、ordinal_expectation_v1、classification_override、typed trace/artifact；删除 M4 quality gate |
| SR-15 | 多 phase/event/window anchor 缺唯一 session 聚合 | 为 O1/O10/O11/O12/O13/H1/H2/H3/H4/H5 明确聚合 |
| SR-16 | O13 使用 session scalar 或 high/base 分组会退化、重叠或没有对照窗 | 锁定 control-physio-grid-v2、逐窗 O1/O5/O7、连续 activation/coupling-loss 和 session max；不设最低窗口/coverage gate |
| SR-17 | O3/O5/O10/O11/O12 数字实现仍有可选起点、baseline 或 detector 歧义 | 锁定 start mode、movement profile、configured active channels、方向 mapping、短 pre-event baseline fallback、worst-event 与任一 miss 否决 |
| SR-18 | H5 通道、频带、PSD、窗口与退化语义不唯一 | 锁定 configured role channels、3–35 Hz、4/2 s、Welch、absolute delta 与 worst window；缺配置 not_computable，配置存在但谱退化 computed U |
| SR-19 | EDF 在 UI 与 session 规范中不一致 | session contract 增加 EDF/EDF+ 与 sidecar metadata |
| SR-20 | 本地绝对论文路径无法随产品交付 | 新增 REFERENCES.md，改用 DOI、出版社、机构仓储和 arXiv 稳定入口 |
| SR-21 | O9 所需 hover masks 没有 producer/schema/grid | O1/O4 输出 typed masks，O9 以声明的 nearest policy join U 并复用 movement profile；无 stable interval 为 computed U override |
| SR-22 | H1–H3 的 gaze/fixation 分工、catch-all 与零分母未定义 | H1/H3 使用逐 gaze interval 时间积分并要求全视野 `other_scene`；H2 单独使用 fixation-v1；无 dwell 为 computed U 而非 0%/invalid |
| SR-23 | H4/H5 baseline 或 spectrum 退化可能产生除零、NaN 或被过滤 | 禁止 NaN/Infinity；配置存在但 RR/HR0/spectrum/E0 数值退化使用受控 computed-U override，缺 baseline/channel 定义则 not_computable |

## 4. 结构与机器检查

最终基线应满足以下检查；本轮已执行：

- product 文档全部 UTF-8 可读，Markdown fence 成对；
- 所有 fenced JSON 示例可由 JSON parser 解析；
- 所有 fenced YAML 示例可由 YAML parser 解析；
- sample manifest 可解析，包含 X、U、I、G、EEG、ECG、pilot_camera 七个 descriptor；
- reference anchor headings 为 18/18 unique；
- sub-skill mapping 为 11/11 unique；
- BN evidence table 为 18/18 unique；
- shared evidence parents 与 O1/O2/O7/O11/O12/H1 设计一致；
- competency prior 和三行默认 CPT 概率和均为 1；
- 产品文档内部相对链接有效；
- 无 TODO、TBD、FIXME 或 PLACEHOLDER；
- 无开发者电脑绝对路径；
- 旧 FastAPI/H1–H6/19-node/只读拓扑只出现在明确的历史否定语境。

## 5. 尚存但不阻断设计交接的风险

### 5.1 科学风险

- 绝大多数阈值、CPT、coverage cutoffs 和部分 anchor 是工程默认；
- 4 competencies、11 sub-skills 与共享 evidence mapping 尚需领域专家内容审查；
- posterior calibration、重复性、known-groups validity 和外部有效性尚未研究；
- default model 只能标记 engineering_default。

### 5.2 数据风险

- I/G/EEG/ECG/pilot_camera 的真实导出文件和设备 metadata 尚未形成最终样本 bundle；
- reference trajectory、phase/event、response mapping 和 baseline 的实际生产流程仍需实验团队确认；
- 生理与图像数据涉及敏感信息，交付前需要项目级同意、脱敏和保留策略。

### 5.3 实现风险

- M1/M2/M3 已有正式代码、四份 public schema、版本化 profile/binding catalog、自动化测试和 Git history；
- M3 的 public report、clock/annotation/reference、deterministic fingerprint 与 golden E2E 已通过工程完成门；M4 的 18 个 AnchorPlugin、evidence availability 与 anchor-specific grids 尚未实现；
- WinUI graph control、无障碍和大 CPT 编辑体验需要原型；
- Python/.NET 打包、插件签名、升级和 crash recovery 需要实际验证。

## 6. 下一阶段入口

截至 2026-07-13，backend M1 contracts/integrity、M2 multimodal ingestion foundation 与 M3 native-rate synchronization 已完成工程验证；[M3 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) 和 [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) 保留完整设计与实测证据。[M4 书面规格](specs/2026-07-13-m4-anchor-evidence-availability-design.md)、[轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)、[Task 3 Reference Candidate Binding 修订](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)、D-026–D-028 与 [replacement plan](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 均已获用户批准；[M4 原 TDD 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) 已被取代。Replacement Task 0–6 与 M4-A contract/schema slice 已完成；Task 6 focused `36 passed`、contracts/schema `376 passed`，Ruff/ty clean，fresh build 含 14 个 package schema resources，两路终审 P0/P1 均为 0。下一步为 Task 7 exact-18 catalog/parameter resources，canonical identity 仍属 Task 8；18/18 production plugins 仍为 0/18，M4 尚未 engineering verified，`formal_run_authorized=false`。M4 不设置基于表现好坏或异常数值的 quality gate；Task 6 测试也不构成科学有效性或能力结论。之后再进入 M5 BN adapter、M6 runtime 与 WinUI。前端可以用 fake backend 并行开发，但不能另建一套模型状态。

任何专家修改都通过新 draft/revision 完成；不需要重新修改本设计中的 Python 业务结构。

## 7. 2026-07-13 M4 amendment 自审

### 7.1 状态与优先级

本 amendment 只关闭 M4 设计冲突，不构成实现或工程验证。当前状态严格为：

- reference M4 anchors：**18/18 已设计，0/18 production plugins 已实现**；
- M4 original implementation plan：**历史上已获用户批准，现已被轻量修订取代且不再授权执行；replacement plan 与 Task 3 candidate-binding amendment 已于 2026-07-13 批准，Task 0–6 已完成，下一步为 Task 7 exact-18 catalog/parameter resources**；
- Task 0 的 input-only 10 秒 fixture 与独立 exact-18 expected vector、Task 1 的 numeric/JCS runtime provenance 审计、Task 2 的 breaking `AnchorResultV2` typed contract、Task 3 的 semantic/reference binding、Task 4 的 catalog/dependency/execution-plan/immutable-request contracts、Task 5 的 measurement/artifact/inventory/report contracts 和 Task 6 的 deterministic schema export 已实现；Task 6 focused `36 passed`、contracts/schema `376 passed`，Ruff/ty clean，fresh build 含 14 个 package schema resources，两路终审 P0/P1 均为 0；M4-A contract/schema slice 已完成，但 catalog/canonical identity Task 7–8、18 个 production plugins、配置资源、完整 M1→M4 workflow 和 wheel smoke 均尚未完成，M4 尚未 engineering verified、`formal_run_authorized=false`；
- M1/M2/M3 的既有工程验证结论不受影响；Gate B 仍未通过；
- 本节不得被解释为真实数据科学验证、飞行员能力结论或医学诊断能力。

本轮已把 SR-05、SR-14、SR-16～SR-18、SR-21～SR-23 和相关产品文档迁移到本节口径。`binary_quality_v1`、`min_valid_coverage`、M4 `invalid_quality`、旧 O13 high/base、fixation-only H1/H3、窗口数量门槛和异常生理范围过滤，只允许出现在显式 legacy/否定语境，不能作为 extractor 行为依据。

### 7.2 重开并关闭的设计问题

| ID | 重开的问题 | 2026-07-13 收口结论 |
|---|---|---|
| M4-SR-01 | 旧 quality gate 会把差表现或极端数值当作无效数据，从而不向 BN 提交负面证据 | reference M4 采用 **no-quality-gate**：必需输入存在且必需配置有效时必须计算 D/A/U；表现越差只会形成更差证据，不会被过滤 |
| M4-SR-02 | `invalid_quality`、missing 和 Unacceptable 的边界不清 | 差轨迹、剧烈控制、未捕获、未响应、无稳定悬停、无有效 gaze dwell、异常 ECG/EEG 均按各 anchor 规则返回 `computed + Unacceptable`；缺流、缺配置、无适用阶段/事件、上游依赖缺失仍分别保留非观测状态，missing 绝不等于 U |
| M4-SR-03 | 旧 AnchorResult 无法表达“已观察到失败，但主值不存在” | 发布 **AnchorResult v0.2**：computed U 可令 `primary_value=null`，但必须给出版本化 `classification_override`、有限的 `observed_wait`/诊断、完整 source trace 和 one-hot U likelihood；禁止 NaN、Infinity 和伪造超大值。coverage 只描述证据范围，不决定表现等级 |
| M4-SR-04 | O13 high/baseline 分组可能无窗口、分母退化且重复计数语义不稳定 | 发布 **O13 v2**，使用 **control-physio-grid-v2** 的连续逐窗耦合：`Q_control=0.50*qO1+0.25*qO5+0.25*qO7`，`activation=clip((delta_HR_pct-10)/10,0,1)`，`coupling_loss=100*activation*(1-Q_control)`，session 取最大值；短 phase 使用整个 phase，不设最低窗口数或 coverage gate |
| M4-SR-05 | fixation-only 分母和 Unmapped 可能隐藏长期离题注视 | H1/H3 使用 **gaze-aoi-interval-v1** 对逐帧 gaze interval 做时间积分；H2 单独使用 raw gaze 重算的 `fixation-v1`。AOI taxonomy 必须有覆盖全视野的 `other_scene` catch-all，reference 默认计为 Off-task |
| M4-SR-06 | ECG/EEG 极端或退化结果可能被 quality gate 丢弃 | ECG 配置/stream 存在但无法形成 R-R interval、HR0 非正或结果退化时返回 `computed + U` 与 ECG override；EEG role channels/baseline 定义根本缺失为 `not_computable`，配置与 stream 存在但谱/分母数值退化时返回 `computed + U` 与 EEG override。极端有限数值不截断，且不作医学诊断 |
| M4-SR-07 | pre-request rejection、plan-level blocked 与 per-anchor missing/config/dependency/error 重叠 | M3/semantic/reference/session/request fingerprint 闭合失败抛稳定 pre-request error 且不生成 M4 report；只有有效 request 之后的 plan/registry/DAG/global inventory/atomic commit 失败使用 `blocked` report；合法 plan 在本 session 缺 stream/context 为精确 anchor status；上游执行后缺 result/artifact 为 dependency_missing；plugin staging failure 与 global atomic failure 分开 |
| M4-SR-08 | 零 support、长 gap 与 terminal sample 可被不同实现解释为 hold、omit 或 invalid | 定义 support_interval_v1、segment-aware left-hold、零 support/最小数学基数状态、不得跨 gap，以及每类 metric 的固定 denominator；不重新引入 coverage fraction gate |
| M4-SR-09 | O2/O3、control detector、event horizon、gaze/ECG/EEG DSP 参数不足以唯一实现 | 冻结 reference join、arrival axis/horizon/composite primary、O5 filter/padding/turning-point/duration、O6 normalization/integration、O10–O12 horizons/channel policy、gaze interval/tie/pooled aggregation、R-peak assignment 与完整 Welch/band/epsilon 参数 |
| M4-SR-10 | artifact/fingerprint、registry 和 fixture verification 可由实现者各自定义 | 保留 RFC 8785 JCS + typed framing、logical-vs-storage hash、registry resource/factory/digest policy；验证改为 per-anchor micro oracle、紧凑 all-D/all-U/mixed real-plugin scenarios、fault-hook state matrix 和唯一 10 秒 physical bundle/isolated-wheel entrypoint。90 秒 full-rate bundle 只属未来性能测试 |
| M4-SR-11 | 分段确认曾被误写成完整书面批准 | 候选阶段明确区分两者；用户于 2026-07-13 依次批准完整 M4 规格、轻量验证修订、replacement plan 与 Task 3 candidate-binding amendment，D-021～D-028 分别在受控迁移中转为 accepted；Task 0–6 已完成，下一步为 Task 7 |
| M4-SR-12 | phase/event 中 computed 与 non-computed 混合时，session result 可能静默忽略缺项 | 冻结 canonical applicable inventory、全项执行和 `extractor_error > dependency_missing > missing_input > not_computable` 的 session 状态优先级；任何 applicable 非 computed 都不生成 session D/A/U |
| M4-SR-13 | M4 曾假定 M3 提供 gap intervals，O5 零平台与 H5 极短段也可能由不同实现自由解释 | M4 从 aligned rows + M3 `gap_threshold_ns` 精确重建/核对 segments；O5 run 使用 left-hold support duration 且零平台不计时；H5 固定短段 filter bypass、padlen、empty-band 与 baseline-degenerate computed-U 语义 |
| M4-SR-14 | provisional full oracle 存在 recipe/expected 回灌、数值闭合和重 fixture 范围问题，plugin digest 也必须覆盖 helper/DSP runtime | 由 D-026/D-027 取代 full oracle：每个 anchor 用独立 micro oracle，真实插件场景只接收 raw/aligned inputs，定向扰动证明 data-to-anchor；implementation digest 继续覆盖本地 import closure、resources、schemas 和 exact numeric-runtime build identity |

no-quality-gate 不取消 M1/M2/M3 的格式、checksum、schema、timestamp、单位和同步合同。结构损坏的数据应在进入 M4 前被明确阻断；它也不允许 extractor 把结构错误猜测成表现差。M4 取消的是以“数值太差、行为太差、coverage 太低、没有成功响应”为理由删除已观察到的负面表现。

### 7.3 M4 机器与 fixture 验收

M4 进入 engineering verified 前必须新增并通过以下验收；当前均为设计要求，不是已取得的测试结果：

1. **机器扫描**：reference catalog 必须恰为 O1–O13 + H1–H5，18/18 unique；扫描旧 H6、19-node、旧 O13、fixation-only H1/H3、缺少 `other_scene`、以及把极端表现映射到 `invalid_quality` 的活跃配置或代码。历史否定语境只能进入显式 allowlist。
2. **合同与手算 golden**：AnchorResult v0.2 schema、canonical D/A/U likelihood、nullable-primary override、有限数、单位、阈值包含方向和非观测状态均有合同测试；18/18 anchor 各自至少有一个不调用 production extractor 生成期望值的手算 golden。
3. **全 D workflow**：紧凑 aligned raw tables 必须经真实 production plugins 得到 `18/18 computed + Desired`，所有依赖、窗口、事件、source trace 和 parameter/plugin hash 完整。
4. **全 U workflow**：同一任务结构的紧凑差表现 aligned fixture 必须得到 `18/18 computed + Unacceptable`、raw availability `100%`；其中 missed/no-stable/no-gaze/ECG/EEG override 不得变成 missing 或 invalid quality。该场景是 no-quality-gate 的阻断级回归门，但不要求 physical Session Bundle。
5. **状态矩阵**：required stream 缺失、配置/reference/mapping 缺失、无适用 phase/event、O8/O9/O13 上游缺失和受控 extractor exception 分别产生规定状态，并断言 non-computed 结果不携带 BN observation。
6. **轻量物理链与确定性**：唯一 10 秒全模态 bundle 通过公开 M1→M4；同一 aligned session、model/plugin revision 和参数重复执行时，AnchorResult JCS bytes、artifact logical content、result/evaluation hash 与 provenance 完全一致，更换 TEMP/绝对根路径不改变 root-independent fingerprint。运行前后该 source bundle 逐字节不变；Parquet/Arrow storage bytes 不进入 logical fingerprint。M4 只写注入的临时/in-memory artifact sink。
7. **扩展性**：18 个插件和版本化配置必须从 registry/package resources 加载，不使用中央按 ID 分支；新增插件、参数 revision 或 soft scorer 不修改 packaged defaults；dependency DAG、M4 fingerprint/cache-key material、schema compatibility 和 unknown-plugin failure 均有测试。真正的 cache lifecycle/hit policy 属于 M6。
8. **隔离 wheel**：fresh wheel 在 repository 外隔离安装，import origin 不得指向源码树；必须能加载 AnchorResult v0.2、18 个插件/配置资源，并复用同一个 10 秒 bundle 完成 public smoke。全 D、全 U 精确结果由紧凑 real-plugin workflows 证明。最终记录实测 test count、wheel size 和 SHA-256，但不在实现前预设结果。

所有 synthetic fixtures 继续标记 `synthetic_semantics_unvalidated=true` 与 `scientific_validation_status=not_supported`。repository-external captured-format CSV 只允许验证格式、同步接口和 source immutability；不得在 M4 完成门中从该 CSV 断言 trajectory、control、physiology、anchor 或 pilot ability。
