# Design Self-Review Report

| 字段 | 值 |
|---|---|
| 设计基线 | 产品 v0.3 shared-versioned-model architecture；旧 M4 Task 0–28 作为历史实现保留 |
| 审查日期 | 原始审查 2026-07-10；M4 amendment 2026-07-13；方向重基线与 M4R 收尾 2026-07-15；M5 架构、决策适用性与实施计划自审 2026-07-16 |
| 审查范围 | pilot_assessment_system 产品文档、项目入口说明、M4R 实现边界、M5 component/scheme/BN 语义与跨文档一致性 |
| 结论 | M1–M3、M4R 与 M5 可作为已验证交接基线；M5 全局组件版本库、任务方案、三类节点/两类边、CPT、BN inference、迁移和轻量工作流已按一致书面规格实现并通过完成门 |
| 软件状态 | M1/M2/M3/M4R/M5/M6 已工程验证；15 个 legacy/reference plugins、共享 primitives 与三个 providers 保留；M7 WinUI、M8 packaging 尚未实现，starter/synthetic `formal_run_authorized=false`，见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) |
| 科学状态 | 参考评估模型为 engineering_default；synthetic fixture 为 not_supported |
| M4/M5 修订 | 2026-07-15 接受 D-031–D-035；2026-07-16 接受 D-036–D-040：普通专家编辑不要求 Python/plugin 发布、审批或 per-edit tests；全局 immutable components 由 exact-pinned schemes 组合，BN topology 与 posterior inference flow 分开，legacy Evidence-to-Evidence extraction 非覆盖迁移 |

## 1. 结论边界

本文保留 2026-07-10 与 2026-07-13 的历史审查，同时记录 2026-07-15 的产品方向纠正和 2026-07-16 的 M5 架构收口。它不是软件实现验收，也不是航空评估科学有效性证明。后续实现证据以 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) 为准；当前 M5 架构权威为 [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)。Replacement Task 0–28 的逐任务事实继续以旧 plan、review ledger 与 Git commits 为准，但 Task 29–36 已失去执行授权。

通过本轮自审后，文档已经能够让接手者明确：

- 系统处理哪些 session 数据，特别是 I(t)、G(t)、EEG、ECG 和 pilot camera；
- 18 个 reference anchors 如何计算、聚合、评分和处理缺失；
- 33-node reference BN 如何定义 state、CPT、共享 evidence、coverage 和解释；
- 用户如何在 WinUI 中新增、删除、移动 node/edge，并修改 binding、参数和 CPT；
- 后端如何以 draft transaction、graph_version、layout_version 和 immutable revision 保持一一对应；
- 正式 run、non-formal preview、结果 provenance 和验证状态如何区分。

原始 2026-07-10 的结论只适用于当时产品设计闭环。2026-07-13 的 M4 anchor-computation amendment、lightweight workflow、Task 3/7/8 amendments 与 Task 0–28 构成有效历史；O1–O12/H1–H3、共享 primitives 和三个 providers 已实现。当时计划中的下一步曾是 Task 29 H4，但 2026-07-15 的 D-031–D-035 已明确停止该路线。默认阈值、拓扑和 CPT 仍等待专家修改与研究校准。

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

- M1/M2/M3 已有正式代码、public schemas、版本化 profile/binding catalog、自动化测试和 Git history；
- 旧 M4 Task 0–28 的 runtime、O1–O12/H1–H3 与 primitives 已实现；M4R 已把 starter inventory 迁移为 transparent EvidenceRecipes/operators，并保留旧插件作 reference/replay；
- M4R contract/schema、registry、validator、compiler/executor、built-in operators 与 recipe revision service，M5 项目级 model workspace/linked BN，以及 M6 durable sidecar 均已实现；WinUI 尚未实现；
- WinUI graph control、无障碍和大 CPT 编辑体验需要原型；
- Python/.NET 打包、trusted operator extension、升级和 crash recovery 需要实际验证。

## 6. 下一阶段入口

截至 2026-07-15，backend M1–M3 与 M4R 已完成工程验证；旧 M4 replacement Task 0–28 留下的 15 个 legacy/reference plugins、共享 primitives 和三个 providers继续保留。用户批准 [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md)、D-031–D-035 与 M4R plan，并明确停止 Task 29–36。下一步是在用户复核后正式设计 M5，而不是继续 H4 固定插件或直接跳到 WinUI。

M4R 已建立 canonical EvidenceRecipe/OperatorDefinition、generic compiler/executor、operator registry 与 autosave/preview/apply/replay；M5 linked Evidence/BN workspace 与 M6 durable runtime 已继续完成。下一步依次为 M7 WinUI 和 M8 packaging/handoff。普通专家修改不需要改 Python 业务结构、发布 whole-Anchor plugin、运行测试或等待审批。

## 7. 2026-07-13 M4 amendment 自审（历史快照）

> 本节保留 2026-07-13 fixed-plugin 路线当时的审查结论，不再定义当前 M4R 完成门。凡涉及“Task 29 下一步”“18-plugin closure”“per-anchor golden”的条款，自 2026-07-15 起均由第 8 节与 expert-editable 规格取代。

### 7.1 状态与优先级

本 amendment 只关闭 M4 设计冲突，不构成实现或工程验证。当前状态严格为：

- reference M4 anchors：**18/18 已设计，15/18 production plugins 已实现，M4-C/M4-D/M4-E software-verified，M4-F not started**；
- M4 original implementation plan：**历史上已获用户批准，现已被轻量修订取代且不再授权执行；replacement plan 与 Task 3 candidate-binding amendment 已于 2026-07-13 批准，Task 0–28 已完成，M4-C/M4-D/M4-E 已关闭，下一步为 Task 29 H4**；
- Task 0–13 的 fixture/contracts/catalog/canonical identity/runtime framework、Task 14 O1、Task 15 O2、Task 16 O3、Task 17 O4、Task 18 O5/`movement-events-v1` provider、Task 19 O6、Task 20 O7、Task 21 O8、Task 22 O9、Task 23 O10、Task 24 O11/共享 `events` primitive 与 Task 25 O12 已实现；Task 25 focused/受控相关 gate 分别为 `21 passed`、`269 passed`，registry/Ruff/format（157 files）/ty/diff gates 通过；最新 full-repository/build/isolated-wheel 完成门仍为 Task 20 证据；其余 6 个 production plugins、完整 M1→M4 workflow 和 final M4 wheel smoke 尚未完成，M4 整体尚未 engineering verified、`formal_run_authorized=false`；
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
| M4-SR-11 | 分段确认曾被误写成完整书面批准 | 2026-07-13 的批准链与 Task 0–28 历史成立；2026-07-15 D-031–D-035 已进一步停止 Task 29–36，因此本行不再指向 H4 fixed plugin |
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
7. **扩展性**：18 个 starter recipes 和版本化配置从 registry/package resources 加载，不使用中央按 ID 分支；新增 recipe、参数 revision 或 soft scorer 不修改 packaged defaults；dependency DAG、fingerprint/cache-key material、schema compatibility、unknown-operator failure 与 M6 per-run source/preflight cache 均有测试。跨 run 的通用性能缓存不是当前完成条件。
8. **隔离 wheel**：fresh wheel 在 repository 外隔离安装，import origin 不得指向源码树；必须能加载 AnchorResult v0.2、18 个插件/配置资源，并复用同一个 10 秒 bundle 完成 public smoke。全 D、全 U 精确结果由紧凑 real-plugin workflows 证明。最终记录实测 test count、wheel size 和 SHA-256，但不在实现前预设结果。

所有 synthetic fixtures 继续标记 `synthetic_semantics_unvalidated=true` 与 `scientific_validation_status=not_supported`。repository-external captured-format CSV 只允许验证格式、同步接口和 source immutability；不得在 M4 完成门中从该 CSV 断言 trajectory、control、physiology、anchor 或 pilot ability。

## 8. 2026-07-15 Expert-Editable 重基线自审

### 8.1 审查结论

本次方向修订通过，解决了“系统声称专家可修改，但公式仍锁在 whole-Anchor Python plugins、普通修改仍被发布/测试/审批流程阻挡”的根本冲突。当前权威结构为：

```text
Canonical EvidenceRecipe -> Generic Operator Executor -> AnchorResult
                |                                  |
                +---------- Windows UI ------------+

AnchorResult -> Editable BN Graph/CPT -> Posterior
```

前端和后端不再各维护一套算法描述。现有 15 个 plugins 不删除，而是作为 legacy replay、迁移比较和 operator implementation 来源。H4/H5/O13 不再按旧 Task 29–31 实现。

### 8.2 已关闭的方向问题

| ID | 问题 | 收口结果 |
|---|---|---|
| ER-SR-01 | 参数可改，但完整计算逻辑仍隐藏在 Python | EvidenceRecipe 是前端显示与后端执行的同一 canonical object |
| ER-SR-02 | 新增 Anchor 可能仍要求一个新 plugin | 只要现有 operators 可组合，新增/复制/修改 Anchor 不写 Python；plugin 只增加缺失的新 operator capability |
| ER-SR-03 | 专家编辑可能触发审核、测试和发布负担 | 每次操作 autosave；one-click apply 只做最小 technical validation，无人工审批、per-edit pytest 或 golden |
| ER-SR-04 | 只画 BN，看不到 evidence 从原始数据如何形成 | 新增并联动 Evidence Computation Graph；BN evidence node 可直接打开对应 recipe |
| ER-SR-05 | 18 Anchor/33 nodes 被误当产品固定边界 | 明确为 starter template；generic Evidence/BN engines cardinality 可变 |
| ER-SR-06 | 旧插件代码可能被推翻或浪费 | 保留历史和测试；primitives 包装为 operators，plugins 用作 recipe 迁移与 replay reference |
| ER-SR-07 | 用户给出的随意飞行 CSV 可能被当任务/能力 golden | 继续只把它用于格式、接口和时间路径；不从其推断任务、表现或能力 |

### 8.3 最小技术校验边界

Apply 可以因 schema、dangling reference、DAG cycle、operator/version、port/type/unit/cardinality、required parameter、safe formula、scorer output 或 CPT executable 问题被阻止。文献支持、参数校准、专家共识、单调性偏好、starter-template 等价和 preview 表现只能作为 metadata/warning，不能阻止 autosave 或 apply。

### 8.4 状态诚实性

- 已实现：M1–M3；旧 M4 Task 0–28；M4R EvidenceRecipe/OperatorDefinition、generic compiler/executor、operator registry、built-ins、starter recipes 与 backend-only revision service；M5 global component library、exact-pinned scheme workspace、CPT、finite-discrete inference、migration 与 lightweight preview/publish/replay workflow；15 个 legacy/reference plugins、共享 primitives、三个 providers继续保留。
- 已设计并获用户确认：expert-editable 总体架构、M4R–M8 milestone rebaseline、D-031–D-035；M4R 已进一步完成实施。
- 已实现：durable project/session/model/run persistence、managed artifact lifecycle、JSON-RPC sidecar 与 run orchestration；尚未实现 WinUI 和最终 packaging，它们分别属于 M7–M8。
- 已停止：旧 replacement Task 29–36 与 fixed exact-18 completion gate。
- 方向重基线本身不是科学验证；M4R 的工程完成证据以实施计划和 fresh commands 为准。

### 8.5 后续门槛

M4R、M5 与 M6 implementation plan 均已完成。下一步基于 M6 protocol 设计 M7 WinUI；M8 packaging 仍放在最后。旧 fixed-plugin 计划不得被继续执行或机械改名复用。

## 9. 2026-07-16 M5 Shared-Versioned Model 自审

### 9.1 审查方式

本轮按用户的低额度要求完全 inline 完成，没有启动 subagent。自审逐项核对新 M5 规格与 README、产品总览、Assessment Core、BN/CPT、图编辑器、术语、决策和 implementation status；随后执行 Markdown 相对链接、fence、旧口径关键词、whitespace 和 Git diff 检查。

### 9.2 已关闭的设计歧义

| ID | 风险 | 收口结果 |
|---|---|---|
| M5-SR-01 | 同名 Evidence 在不同任务中原地升级，导致 Hover/直线保持互相覆盖 | `EvidenceConcept + immutable EvidenceVersion`；方案锁定 exact versions，长期并列 |
| M5-SR-02 | 每个新任务复制整套模型，复用和来源不清 | 全局 component library + `AssessmentSchemeVersion` references；只 copy-on-write 改动部分 |
| M5-SR-03 | “Evidence 的父节点是原始输入”与“BN 中 Evidence 的父节点是 sub-skill”概念冲突 | 分成 extraction `source_bindings` 与 probabilistic BN parents，两类 edge/DTO/validator |
| M5-SR-04 | 把程序计算顺序 `Evidence -> ability` 误画成 BN topology | Starter canonical BN 固定显示 `Competency -> Sub-skill -> Evidence`；反向只作只读 inference overlay |
| M5-SR-05 | 通用引擎被锁死为 Hover、18/11/4 或固定三层方向 | Starter 只是一套 scheme；generic engine 只强制 DAG/CPD/CPT/closure，可发布其他方向的新模型版本 |
| M5-SR-06 | 发布方案时一部分组件成功、一部分失败 | component versions 与 scheme version 原子发布，任一失败整体回滚 |
| M5-SR-07 | 新版本出现后历史方案自动跟随 `latest` | Scheme/run 同时锁定 exact IDs 和 content hashes，禁止隐式升级 |
| M5-SR-08 | 前端集成显示使 operator nodes 变成第四类高层节点 | 高层仍只有 Raw Input、Evidence、BN Node；operator graph 仅作为 Evidence 展开细节 |
| M5-SR-09 | 用户误以为局部任务完成等于里程碑完成 | 实施期间按 Task 逐项记录；Task 12 仅在 focused、M4R、full repository、static、Schema 与 wheel gates fresh 通过后关闭 M5 |
| M5-SR-10 | M4R O8 把 O1/O5 score 当 extraction input，违反两类 edge 边界 | D-040：旧 bytes/hash 仅 legacy migration/replay；generic source-provenance preflight 拒绝 active import；新 TPX version 从 raw/session/task sources 计算 |
| M5-SR-11 | 早期“后端权威”被误解为后端决定科学模型 | D-007 标题和适用性已修订：专家决定模型内容，后端仅维护 canonical state、版本、技术校验和执行一致性 |

### 9.3 已在实施计划冻结的细节

[M5 implementation plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) 已结合现有代码冻结：

- 三个 public contract modules、generic identity、新 type IDs 与 JSON Schema 路径；
- global component repository、scheme repository 与 M6 可复用的 `WorkspaceUnitOfWork` port；
- NumPy finite-discrete variable elimination、deterministic min-fill 和手算小 BN 验证；
- staged batch + single atomic commit，不采用失败后删除的补偿式发布；
- M4R source-provenance migration、旧 O8 legacy preservation 与 compliant TPX parallel version；
- `ExtractionEdge`、`BayesianDependencyEdge`、`InferenceInfluenceEdge` 分离，以及 typed domain operation 范围。

M6 JSON-RPC 方法名已由 M6 规格冻结并实现；M5 plan 只冻结 transport-neutral domain contracts，不单独冒充协议实现。

### 9.4 自审结论

未发现会迫使专家覆盖旧任务模型、混淆 BN 概率方向或重新引入科学审批门的 P0/P1 设计冲突。仓库路线已按 D-036–D-040 收口；M5 Task 1–8 分别完成 identity、public contracts/schema、source-provenance migration、global library、exact-pinned validation、draft/atomic publication、CPT 与 exact inference；Task 9–11 完成 M4R active import/compliant TPX parallel version、checksummed Hover starter package 和 lightweight preview/posterior/publish/replay workflow。Task 12 fresh gate 为 `91 passed` focused、`59 passed` M4R Evidence regression、`1579 passed, 3 skipped` full repository，Ruff/format、`ty check src`、Schema zero-drift、fresh build 与仓库外 wheel smoke 全部通过，M5 因此可标记为 engineering verified。

### 9.5 完成门自审说明

- 计划中单处裸 `ty check` 与仓库自 M2 起统一使用的 `ty check src` 不一致；裸命令会把动态 JSON/Polars 负例测试目录纳入静态合同并产生 380 个历史诊断。Task 12 已把命令修正为 production-source boundary，`ty check src` fresh 通过，没有用 ignore 配置掩盖生产代码错误。
- wheel smoke 最初手写少算 migration/source/concept/TPX support resources；最终核验改为读取 package manifest 的 exact inventory，确认 13 个 JSON 全部在 wheel 内且由 checksummed loader 接受，避免门禁再维护第二份易漂移清单。
- M5 的完成结论只适用于当时的 transport-neutral/in-memory backend；SQLite/managed artifact/JSON-RPC/run lifecycle 现由 M6 独立完成。WinUI 属于 M7，科学有效性仍待专家研究；starter/synthetic `formal_run_authorized=false` 保持不变。
