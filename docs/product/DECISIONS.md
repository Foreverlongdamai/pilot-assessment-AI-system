# 设计决策记录

本文件记录会影响多个模块、不能由单一实现文件自行决定的产品级决策。状态“已接受”表示该决策曾经正式进入项目路线，不表示其全部内容在今天仍具有相同适用范围。后续决策可以显式限定、部分取代或完全取代早期决策，但不得删除历史或静默改写其原意。

### 当前适用性索引

| 当前适用性 | 决策 | 解释 |
|---|---|---|
| 当前通用基线 | D-001、D-003、D-005–D-007、D-009–D-014、D-016–D-022、D-024 的 no-quality-mixing 原则、D-027 的 raw-driven 原则、D-028、D-030–D-032、D-034–D-035、D-037–D-044、D-045 的 transaction/idempotency 原则、D-046 的 exact snapshot/recovery 原则、D-047–D-081 | 继续约束通用产品、合同、运行、文档或候选交付语义；其中 D-007 的“后端权威”只指 canonical state/execution，不表示后端决定科学内容 |
| Starter/reference 范围 | D-002、D-004、D-015、D-024 的具体默认权重、D-029 的 fixed resource inventory | 只描述 `reference-model-v0.1` / Hover starter 或已发布 legacy resource，不构成 generic engine 的任务、数量、拓扑或算法限制 |
| 已被部分取代、限定或转为历史实现 | D-008、D-023、D-033、D-036，D-041/D-042/D-048/D-056 中把 current model/edit session 表述为 project-owned 的部分，D-045/D-046 中要求 publish/published scheme 的措辞，D-051/D-053/D-054 的即时 canonical autosave／输入族始终显示细节，以及 D-075 中“最终截图必须先关闭 M7 中间验收”的部分 | 不可变运行历史、typed DAG、最小技术校验、幂等事务、exact snapshot 与截图隐私/可追溯性仍有效；current model ownership 由 D-066–D-070 提升为 software-copy system scope，候选截图状态由 D-080 细化。M5/M6 version/draft/publish 和 legacy project-local model 实现只用于迁移和旧 run replay |
| 历史完成门 | D-025、D-026，以及 D-027 中 fixed-18 测试范围 | 只记录旧 M4 Task 0–28 的工程过程，不再定义 M4R/M5 的完成条件或专家每次修改的测试义务 |

若单条决策正文与该索引或更晚决策冲突，以明确列出的后续决策为准。D-031–D-040 保留专家可设计、三类节点/两类边和 BN 语义基础；D-047–D-059 定义当前完整节点、任务激活、会话暂存、不可变运行快照、五层输入投影、模型内容语言、显示身份与品牌方向；D-060–D-065 定义 raw session 与首个便携交付；D-066–D-071 定义每套软件副本唯一 system model、project/run 边界、legacy 合并和 source identity；D-072–D-081 定义正式文档、current-system packaging、最终候选与验收证据。历史材料继续保留用于迁移、回放和说明路线演进。

## D-001：产品提供可配置参考模型，而非最终航空标准

- 状态：已接受
- 决策：先实现当前理解下完整、合理、透明的算法、阈值、子技能和 CPT；把可编辑性、版本化和审计作为产品能力。
- 理由：这些科学参数仍需领域专家与真实样本校准。等待所有参数最终确定会阻塞软件体系建设。
- 影响：界面和报告必须显示 exact component/scheme versions 与验证状态，不得把默认值描述成监管认证结论。

## D-002：v0.1 使用 18 个逻辑 evidence nodes

- 状态：已接受
- 决策：目录为 O1–O13 + H1–H5。O2 为 Peak Tracking Excursion，O4 为 Sustained Hover Time，H4 为 ECG Fluctuation，H5 为 EEG Fluctuation；旧 H6 删除。
- 理由：这是用户确认的最新版表格和模型口径。
- 影响：旧稿中的 O1–O13 + H1–H6、19 节点或旧 O2 定义仅作历史资料。

## D-003：视觉和 gaze 是正式一等输入

- 状态：已接受
- 决策：I(t) 是飞行员随头部转动在 VR 中实际看到的第一视角场景；G(t) 是映射到该动态场景的 gaze ray、point、fixation/stare 与 AOI。EEG、ECG 同样进入正式 session contract。
- 理由：这些数据已经采集，只是尚未全部导出；CSV-only 架构会造成后续返工。
- 影响：当前缺少导出文件时使用 export_pending，而不是删除接口或伪造证据。

## D-004：BN 使用生成方向

- 状态：已接受
- 决策：Competency → Sub-skill → Evidence。输入 evidence 后执行反向概率推断。
- 理由：方向表达“能力状态导致可观测表现”，更适合解释 CPT 并处理缺失证据。
- 影响：共享 evidence 可以有多个 sub-skill parents；所有图编辑仍必须保持 DAG。

## D-005：Missing 不是第四种能力表现

- 状态：已接受
- 决策：Desired、Adequate、Unacceptable 是 evidence state；missing、invalid、not_applicable、export_pending 是数据/适用性状态。
- 理由：把缺失当作差表现会系统性惩罚未安装或未导出的模态。
- 影响：BN 对缺失 evidence 不提交观测并进行边缘化；覆盖率单独报告。

## D-006：桌面端首选本地 stdio sidecar

- 状态：已接受
- 决策：WinUI 3 管理 Python sidecar，以 JSON-RPC 2.0 / JSONL over stdin/stdout 通信；stdout 只发送协议消息，日志走 stderr 与文件。
- 理由：本地离线产品无需端口、防火墙或服务发现，打包和生命周期边界清晰。
- 影响：FastAPI 仅可作为未来可选 adapter，不能成为核心业务依赖。

## D-007：专家通过前端设计模型，后端维护 canonical 状态与执行一致性

- 状态：已接受
- 当前适用性：当前通用基线；由 D-031–D-040 澄清。“权威”不包括科学内容决定权或固定模型清单。
- 决策：用户可拖拽新增、删除、移动节点和边，并编辑 anchor 参数、state space 与 CPT；所有语义修改以原子 domain operation 发往后端。
- 理由：领域专家必须能直接在产品中优化模型，而不是修改源代码。
- 影响：前端的 pending 图形不是已保存事实；后端负责 cycle、CPT、binding、版本冲突等验证并返回 canonical graph。

## D-008：草稿可变，发布 revision 不可变

- 状态：已接受
- 当前适用性：部分取代。不可变发布、exact snapshot、撤销/重放继续有效；`inference smoke test` 被 D-033/D-034 的最小技术校验取代，单一 whole-model revision 被 D-036 的 component versions + `AssessmentSchemeVersion` 取代。
- 决策：编辑先创建 draft；通过验证和 inference smoke test 后发布新 revision。正式运行锁定 published revision 和内容 hash；non-formal preview 锁定 exact draft_id + graph_version。
- 理由：防止编辑中的图影响正在执行或已经完成的评估，保证结果可重现。
- 影响：撤销/重做基于后端命令日志；发布后修改或“回滚”都必须从选定 revision 建立新 draft。draft_validation_state、revision_lifecycle、scientific_validation_status 和 permitted_use 是独立字段。

## D-009：大数据通过文件合同传递

- 状态：已接受
- 决策：JSON-RPC 只传 session bundle 路径、相对路径、metadata 与 checksum；视频、帧、EEG、ECG 和长时间序列不嵌入 JSON。
- 理由：降低内存、序列化和进程通信风险。
- 影响：session import 必须执行路径、schema、checksum 和访问权限检查。

## D-010：软件验证与科学验证分离

- 状态：已接受
- 决策：“计算按规范执行”与“评分真实有效”分别管理、显示和验收。
- 理由：高测试覆盖率不能证明 anchor 阈值或 CPT 具有真实世界效度。
- 影响：产品必须携带 software_verification_status 与 scientific_validation_status；reference v0.1 的初始 scientific_validation_status 为 engineering_default。

## D-011：X/U 可以共享一个受验证的物理 artifact

- 状态：已接受
- 决策：v0.1 允许 `X` 与 `U` 两个 `present` logical stream view 引用完全相同的 bundle-relative path。两者必须声明相同 checksum、format、schema_id 和 `metadata.shared_source_id`，并分别声明 `metadata.view_id=X/U`；checksum 文件只登记该物理文件一次。其他 stream sharing、大小写不同的路径别名，以及同一路径被两个独立声明赋予 stream/annotation/reference/integrity 跨角色所有权均拒绝。D-014 的 `task_reference` descriptor 是 reference artifact 的唯一 owner，不构成跨角色 sharing。
- 理由：当前 simulator CSV 同时包含 flight state 与 pilot control；强行复制文件既浪费空间，也会制造两个可能漂移的“原始”副本。
- 影响：loader 分别报告 logical reference count 与 unique artifact count，路径安全、读取、hash 和资源预算按 unique artifact 执行；同一物理文件仍只有一个 canonical identity。

## D-012：Synthetic full bundle 只用于软件验证

- 状态：已接受
- 决策：captured-format-sample X/U 加 synthetic I/G/EEG/ECG/pilot_camera 的混合 bundle 必须标记 `synthetic-test-data`、`software-testing-only` 和 `scientific_validation_status=not_supported`；该 X/U 只代表采集格式，不是有效任务 session、标准轨迹、ground truth 或能力证据。所有结果显示 `SYNTHETIC TEST DATA`，不得转换为正式飞行员评估结果。
- 理由：格式正确、可重复的合成信号可以验证软件闭环，但不能证明 anchor、阈值、CPT 或能力结论对真人有效。
- 影响：生成器、报告、前端和导出都必须保留 synthetic provenance；synthetic 生理/相机数据不计为真实人体 biometric data。

## D-013：Ingestion readiness 与 Run preflight 是不同阶段

- 状态：已接受
- 决策：M2 输出 `IngestionReadinessReport`，scope 固定为 `inspect_only_ingestion_content_v1`，只回答 source artifact 能否进入 M3 synchronization；其中 `formal_run_authorized` 永远为 false。完成同步、annotation/reference 语义检查并锁定 exact `AssessmentSchemeVersion` 及其 component hashes 后，`run.preflight` 才输出 `RunPreflightReport` 并决定是否允许创建 AssessmentRun。
- 理由：两种检查共用“preflight”名称会让前端和审计记录误以为通过 ingestion 就已获准评分。
- 影响：M2 raw schemas 不伪造 authoritative `t_ns`；M3 生成 aligned schemas。DTO、协议、术语表和界面必须使用完整名称。

## D-014：Bundle-local task reference 通过可选 stream 间接声明

- 状态：已接受
- 决策：session-local commanded/reference path 的文件位于 `references/`，由可选 `streams.task_reference` descriptor 声明 format、schema、clock、units、paths 和 checksums；`task.reference` 使用 `source=bundle` 与 `stream_id=task_reference` 指向它。`source=model_bundle` 时禁止 `stream_id`，由锁定 `AssessmentSchemeVersion` dependency closure 的 portable model bundle 根据 `reference_id` 解析。
- 理由：reference 是可采样的时序 artifact，复用 StreamDescriptor 可避免第二套路径、checksum 和时钟权威，同时保持它不属于七个 core modalities。
- 影响：bundle reference 必须通过普通路径安全、integrity 和 adapter gate，但在 readiness/coverage 中单独报告，不能伪装成飞行员输入模态。

## D-015：Reference-model-v0.1 固定为 33 节点三层 BN

- 状态：已接受
- 当前适用性：仅 `reference-model-v0.1` / Hover starter；不得解释为 generic BN engine 约束。当前通用语义见 D-036–D-040。
- 决策：reference-model-v0.1 的 Guided palette 只包含 competency、subskill 和 evidence，结构边只允许 competency→subskill 与 subskill→evidence。Phase/task context 保留在 BN 外供 AnchorPlugin 使用；O8/O13 通过 `derived_from`、`dependence_group` 和 `likelihood_strength` 处理相关性，不创建 evidence→derived_evidence 结构边。
- 理由：当前 CPT 和推理语义只定义了四 competency、十一 sub-skill、十八 evidence 的三层网络；允许未定义的 context 或派生结构边会产生无法解释的 CPT。
- 影响：context node 或 structural derived evidence 只能在明确声明其语义、CPT、编译和 golden tests 的新 model profile 中启用；从 reference-v0.1 切换必须使用新的 major model profile，不能只改 draft/revision 标识。

## D-016：M3 只产生 native-rate aligned views

- 状态：已接受
- 决策：M3 只映射原生采样行并追加 aligned time/flags；不插值、不重采样、不建立 anchor-specific analysis/window grid。
- 理由：插值和窗口参数依赖 AnchorPlugin/model revision，提前全局冻结会制造未经专家批准的信号值。
- 影响：M3 报告 interpolated_rows=0；M4 按 anchor 定义建立 grid/window。

## D-017：Clock scale 是唯一映射权威

- 状态：已接受
- 决策：唯一公式为 round-half-even(source_s × scale × 1e9 + offset_ns)；drift_ppm 只与 scale 做一致性审计，不再次参与计算。同 clock_id 必须共享 method/scale/offset/drift mapping；per-stream residual 可以不同。
- 理由：同时施加 scale 和 drift 会重复校正并破坏可复现性。
- 影响：M3 对 scale/drift、residual 顺序、same-clock mapping 和 int64 overflow 执行结构门。D-021 已随 2026-07-13 完整 M4 规格批准而取代原先“task/anchor-specific residual tolerance 留给后续 gate”的影响说明；M4 不得把 residual、coverage 或所谓采集质量变成表现 evidence 的过滤门。

## D-018：v0.1 session window 由 master-clock X 推导

- 状态：已接受
- 决策：v0.1 只支持 origin=session_start；window 为 [0,max(mapped X primary t_ns)]，source=master-clock-x-mapped-coverage-v1。
- 理由：manifest 0.1 没有独立 duration/end；X 仅是 v0.1 session-end 的技术时间边界来源，不是 commanded trajectory、任务标准或表现权威。
- 影响：synthetic duration_s 仅作 golden cross-check；未来显式 window 必须走新的 schema/decision。

## D-019：Annotation 与 reference 在 M3 分流

- 状态：已接受
- 决策：synthetic annotation 的 *_s 是 session-relative seconds；正式 session-time annotation 直接声明 t_ns。Bundle reference 在 M3 对齐；model-bundle reference 返回 deferred_model_bundle_resolution。
- 理由：annotation 没有 device clock，而 model reference 只有锁定 revision 后才能解析。
- 影响：M3 不猜 annotation clock/response semantics，也不把 deferred model reference 误报 missing。

## D-020：M3 使用独立 snapshot input 和 report

- 状态：已接受
- 决策：内部 SynchronizationInput 组合同一次 LoadedManifest、PreparedSession 和 IngestionReadinessReport；输出内部 AlignedSession 与公共 SynchronizationReport。
- 理由：PreparedSession 不应吸收 bundle I/O/clock/annotation 责任，M1 也不应重复 load/hash。
- 影响：SynchronizationReport 与 IngestionReadinessReport/RunPreflightReport 分离，始终 formal_run_authorized=false，并绑定 source/policy/catalog/alignment fingerprints。

## D-021：M4 不承担原始数据质量研究

- 状态：已接受
- 决策：M4 假定其输入已经通过 M1–M3 的文件、schema、有限数值、字段和时间合同；M4 不再设置 coverage、noise、gap、residual、artifact、幅值或生理范围 quality gate，也不因这些 diagnostics 省略表现 evidence。M1–M3 的结构检查继续存在，但它们不是 M4 的评分门。
- 理由：仿真采集系统负责交付有效数据；本产品负责按冻结规则评价飞行表现。把表现异常或数值极端重新解释为“低质量数据”会系统性掩盖真正的差表现，并把项目扩展成另一项采集质量研究。
- 影响：`SessionQualityReport`、`IngestionReadinessReport` 和 `SynchronizationReport` 可以保留技术 diagnostics，但 M4 scorer 不读取它们形成 quality score，不做 outlier clipping、winsorization、artifact-based window deletion 或医学范围过滤；历史 M1–M3 合同仅作上游完整性边界。

## D-022：差表现必须产生 Unacceptable evidence

- 状态：已接受
- 决策：输入、公式配置和任务适用条件存在时，极大轨迹误差、剧烈控制、极端但有限的生理指标、未捕获、未稳定悬停、未恢复、未响应和未注视均必须输出 `computed + Unacceptable`。无法用有限主值表达的观察使用受控 `classification_override`，不得使用 Infinity 或 NaN。
- 理由：这些现象就是系统需要客观反映的负面表现，不是缺失证据。
- 影响：`computed + Unacceptable` 与 Desired/Adequate 一样具有 raw availability 1 并提交给 M5；missing、not applicable、缺配置/依赖和软件错误使用单独状态，不能与差表现合并。

## D-023：M4 使用可扩展 catalog、typed DAG 与 AnchorResult v0.2

- 状态：已接受
- 当前适用性：部分取代。AnchorResult v0.2、typed dependency 和 legacy replay 保留；普通新 Evidence/公式不再要求 whole-Anchor plugin 或 whole-model catalog revision，见 D-032/D-036。
- 决策：M4 engine 按版本化 `AnchorCatalog` 与编译后的 `AnchorExecutionPlan` 运行可变数量插件；只有 `reference-model-v0.1` profile 精确包含 O1–O13、H1–H5。插件先产生 `AnchorMeasurement`，中央 scorer 生成 breaking contract `anchor-result-0.2.0`；其计算状态只允许 `computed`、`missing_input`、`not_applicable`、`not_computable`、`dependency_missing`、`extractor_error`。执行通过 typed dependency DAG、受控 artifact sink 和 canonical inventory 完成。
- 理由：前端未来增、删、改 anchor 和算法时，orchestrator 不应写死 18 个分支；同时必须保留可验证、可重放的依赖与合同边界。
- 影响：`anchor-result-0.1.0` 仅保留为只读 legacy 合同，M4 不写它，也不静默改写 schema ID。新增/retire anchor 发布新 catalog/model revision；参数变更产生新 parameter snapshot；公式变更必须发布新 plugin version。`plugin_unavailable`、`not_implemented`、`not_attempted` 只属于 capability/plan/report inventory，不冒充 session calculation status。

## D-024：M5 不按所谓数据质量衰减 evidence

- 状态：已接受
- 当前适用性：no-quality-mixing 原则继续有效；O8/O13/H1/H3 的具体 strength 只属于 starter engineering defaults，专家版本不受这些数值限制。
- 决策：M5 直接消费 M4 的版本化 D/A/U likelihood，不使用 quality score 向均匀分布收缩。O8/O13 的默认 `likelihood_strength=0.50`，以及 H1/H3 `gaze_allocation` dependence group 的 reference strength `0.50 each`，只用于相关性和重复计数保护，不表示数据质量。
- 理由：quality mixing 会把最差但有效的表现重新拉回无信息分布，违背 D-022。
- 影响：coverage 衡量适用 evidence 是否成功产生：`computed` 的 D/A/U 都贡献完整 availability，`not_applicable` 不进入分母；模型影响强度可以另作 diagnostic，但不能命名为 coverage 或 quality。

## D-025：M4 工程完成必须同时证明全好、全差与可扩展重放

- 状态：已接受
- 当前适用性：历史完成门；不再定义 M4R/M5 completion gate，也不约束专家通过前端发布新版本，见 D-034。
- 决策：M4-G 只有在逐 anchor 手算 golden、精确边界、状态矩阵、18/18 computed Desired、18/18 computed Unacceptable、扩展/retire/version replay、确定性 fingerprint、source immutability、完整测试、构建和隔离 wheel 全部通过后，才可声称 M4 engineering-verified。
- 理由：只证明理想信号能运行不能发现“差表现被过滤”的核心失效模式，也不能证明专家未来修改 anchor 后仍可重放。
- 影响：全 Unacceptable fixture 的 raw availability 必须为 1，M4 输出不得出现 `invalid_quality`；synthetic fixture 继续标记 `scientific_validation_status=not_supported`。M4-A 至 M4-F 的局部完成状态必须如实报告，不能冒充 M4 整体实现。

## D-026：M4 默认采用轻量分层验证

- 状态：已接受
- 当前适用性：历史 fixed-plugin 验证方案；“保持测试轻量”继续作为工程偏好，但 exact-18 场景不再是当前平台完成条件。
- 决策：M4 的默认验证由合同/纯框架测试、18 个 per-anchor 定向微型测试、紧凑 all-Desired/all-Unacceptable/mixed aligned-input 场景、fault-hook state matrix，以及唯一一个 10 秒全模态 M1→M4 physical bundle smoke 组成。90 秒或更长的 full-rate bundle 不属于 Task 0、默认 pytest、isolated-wheel smoke 或 M4 engineering-verified 的必要条件；未来如需长 session 性能、内存或吞吐验证，必须作为独立且手动触发的 performance milestone。
- 理由：原四套 90 秒 dense fixture 每次临时生成约 43,000 个文件且 focused gate 约需 160 秒，却没有比小型定向输入和单个物理工作流 smoke 提供更多 data-to-anchor 语义保证。验证规模不应阻塞 AnchorPlugin 的实现与频繁回归。
- 影响：D-025 的 18/18 Desired、18/18 Unacceptable、状态矩阵、扩展重放、确定性和隔离 wheel 义务全部保留，但由正确层级分别证明；“完整”表示 exact-18 inventory、依赖、状态和结果完整，不表示每个场景都必须是 90 秒 physical Session Bundle。除唯一 workflow bundle 外，默认 M4 测试不得生成 dense image/file assets。

## D-027：Expected evidence 必须由 raw/aligned inputs 机械驱动

- 状态：已接受
- 当前适用性：raw-driven、禁止答案回灌的原则继续有效；O1–O13/H1–H5 的固定测试 inventory 只属于旧 M4 历史范围。
- 决策：M4 测试 input recipe 只能包含 source data、semantic/config bindings、reference、events 和 fault controls；expected vectors 必须存放在独立文件或模块，并由不 import `pilot_assessment.anchors` 的小型 oracle 或手算公式产生。Production plugin 不得读取 expected vectors，production result/artifact 也不得回写为后续测试输入。测试必须通过有针对性的输入扰动证明相关 anchor 随输入改变、无关 anchor 保持不变。
- 理由：provisional heavy fixture 曾把部分 mixed anchor 结果保存为 recipe 输入；这种 builder/oracle 自洽即使通过 hash 和合同测试，也不能证明原始或 aligned data 真正驱动了 evidence。
- 影响：recipe/schema 必须拒绝序列化 AnchorResult/AnchorMeasurement、result-like `anchor_id + primary_value/state/likelihood` 结构、预计算 `q_control` 或 O8/O13 composite，以及以 O1–O13/H1–H5 为键的 expected-result map。文件 checksum 只证明输入不可变，不能替代 data-to-anchor 语义断言；违反本决定的 provisional `8 passed` 不构成 M4 实现证据。

## D-028：M4 reference 通过 session-bound candidate 精确绑定

- 状态：已接受
- 当前适用性：技术绑定原则继续有效；文中的 ModelBundle 在 M5 后解释为一个 exact `AssessmentSchemeVersion` 及其 dependency closure 的可移植封装。
- 决策：M4 v0.1 使用可序列化 `ResolvedReferenceSetSnapshot` 与独立、受信的 runtime `ReferenceViewCandidate`。`bind_resolved_reference_snapshot(snapshot, aligned_session, candidates)` 只绑定 session/source/synchronization/window、reference/source、schema、clock mapping、table/frame/unit、resource/content/alignment fingerprint 全部精确一致的 candidate；不按列名、列数、shape 或相似 modality 猜测。v0.1 snapshot 总计最多一个 task reference，`bundle` 与 `model_bundle` 二选一。M3 合同、golden 和 `AlignedSession` 不变；bundle reference 的 M3 provenance 在 M4 request 构造前逐字段绑定 `SynchronizationReport.task_reference_result`。ModelBundle 必须先有同 reference ID 的 M3 `deferred_model_bundle_resolution` record；M5 验证并冻结不可变 reference resource，M6 在 model/session lock 后执行 session-time mapping 并在 M3 外构造同形的 immutable view container/candidate。
- 理由：原两参数 binder 无法诚实证明 frame/unit 或接收 M3 明确 deferred 的 ModelBundle reference；只让 descriptor 与 runtime view 相互自证又可能绕过 D-019 的真实同步 provenance。独立 candidate port 保留 M3 边界，同时让 configuration expectation、source resolver 事实和 M3 report 可以机械交叉验证。
- 影响：合法 `absent` reference 保留为 `aligned_view=None`，使依赖它的 anchor 产生 `not_computable`；present candidate 缺失、inventory/identity/contract 错配在有效 `AnchorEvaluationRequest` 之前失败，不生成 M4 evaluation report，也不能降级为 absent。Task 8 负责 canonical reference fingerprints，Task 13/35 在 evaluator 前重算；未来多 reference 支持必须版本化 M3 provenance 与本合同，不能只放宽 tuple cardinality。

## D-029：M4 reference catalog 与可编辑参数使用唯一机器资源身份

- 状态：已接受
- 当前适用性：只冻结 legacy `reference-model-v0.1` 资源和回放身份；不得作为全局组件库的数量、ID 或算法限制。
- 决策：`reference-model-v0.1` 的 Task 7 资源严格冻结为 18 个有序 catalog entries、18 个公开 anchor artifact descriptors、6 个 preprocessing provider/output descriptors、24 个 canonical parameter-schema JSON resources 和真实零项 runtime registry。Parameter schema 使用排序键、两空格缩进、UTF-8 无 BOM、单 LF 的唯一权威字节，`parameter_schema_sha256` 是这些原始字节的 SHA-256；scorer annotation、O6 applicability-scoped channel weights 与 O13 的 O1/O5/O7 七键 algorithm-profile closure 均采用 [Task 7 amendment](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md) 的精确形状。所有 plan-time JSON 参数/temporal/scorer surfaces 在合同构造时递归复制并冻结。
- 理由：可编辑和可扩展不等于允许 loader、测试、编译器和插件各自猜测 ID、schema、默认值、通道集合或 profile 内容。只有唯一资源字节、显式 ownership 与深度不可变 snapshot 才能让专家后续修改形成可审计的新 revision，而不是静默改变旧结果。
- 影响：Task 7 发布资源但不伪造 executable plugins；Task 8 计算 canonical identities；Task 12 编译/执行 scorer；Task 13 使用 runtime Draft 2020-12 validator 完成实例、O6 与 profile closure 校验。O13 通过被各 implementation digest 覆盖的共享纯 O1/O5/O7/movement/scorer kernels 逐窗重算，不在插件内部调用 source factories、复制算法或发布 source artifacts。任何 ID、字段顺序、constraint、默认值、dependency、profile shape 或公式实现变化都必须产生新资源、参数 snapshot 或 plugin/model revision。

## D-030：M4 canonical fingerprint 与 Python runtime identity 使用单一字节合同

- 状态：已接受
- 当前适用性：M4 identity 合同继续有效；M5 必须为 component/scheme contracts 单独冻结新 type IDs、canonical projections 与 hashes，不能把 legacy catalog fingerprint 冒充新身份。
- 决策：M4 typed identity 使用 RFC 8785 JCS、固定 NUL/uint64 framing 和 `[-(2^53-1), 2^53-1]` safe-integer domain；logical table 以完整 descriptor、声明字段顺序、已严格排序的 row arrays 和逻辑值计算，与 storage path/bytes 分离。Scorer policy 使用 `scorer-policy/0.1.0`，algorithm-profile parameters 复用 `parameter-snapshot/0.1.0`。自 fingerprint 字段只从自身 projection 排除，并由命名 trust boundary 重算拒绝 stale claim。Python identity 优先 `SOABI`，仅 Windows 缺失时严格解析 `EXT_SUFFIX`；numeric distribution identity 验证 wheel `RECORD` 中稳定成员的声明与实际 SHA-256/size，并排除安装根相关 launcher/mutable metadata。
- 理由：同一逻辑 session/plan/result 必须跨 TEMP、venv 根和进程产生同一 identity，同时必须让任一真正的 schema、参数、算法、输入、依赖或结果变化改变下游 identity。路径、压缩或自报 hash 不应制造伪差异或自证循环。
- 影响：[Task 8 amendment](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) 是 Task 8/9/11/13/32/34/35 的字节与验证 ownership 权威；Task 8 只在 catalog/runtime/artifact 三个自有边界声明 mismatch rejection，后续 owner 的拒绝测试不得被提前冒充完成。修改 type ID、payload、整数域、ABI precedence、logical ordering 或 RECORD inclusion rule 必须发布新 identity version 或正式 amendment。

## D-031：产品首先是专家可自由设计评估模型的工具

- 状态：已接受
- 决策：O1–O13、H1–H5、11 个 sub-skill、4 个 competency、默认阈值、CPT 和连接均为 starter templates，不是产品不可修改的科学标准。系统的核心交付是让领域专家可视化增删改 Evidence、计算方法、BN 节点/边/state/CPT，并将修改直接用于后续评估。
- 理由：当前方法由非领域专家为打通软件框架而提出，科学合理性、证据设计和能力映射必须由后续专家研究与修改。把 provisional model 当作固定产品会偏离项目目标。
- 影响：通用 engine 不得要求 exact-18；expert model cardinality 可变。Starter template 保留用于演示和起步，但其软件测试不构成科学有效性声明。D-015 继续描述历史 `reference-model-v0.1` 模板，不再限制新 expert model 的结构。

## D-032：EvidenceRecipe 是前端显示和后端执行的唯一计算方法来源

- 状态：已接受
- 决策：每个 Anchor 使用 typed Evidence Computation Graph/EvidenceRecipe 声明 inputs、operator nodes/edges、parameters、outputs、aggregation、scorer、documentation 和 UI metadata。前端根据该对象生成计算图与表单，后端通用执行器直接执行同一对象。不得在前端和 Anchor-specific Python 中维护两份计算逻辑。
- 理由：只有一份 canonical recipe 才能保证专家看到、修改和真正运行的是同一算法，并使普通修改无需开发人员介入。
- 影响：当前 primitives 迁移为通用 operators；whole-Anchor plugin 仅保留 legacy/replay 路线。H4/H5/O13 不再按旧固定插件任务实现。D-023 中“公式变化必须发布新 whole-Anchor plugin version”的影响说明被本决策取代；只有增加 operator library 尚不具备的新能力时才需要新 trusted operator plugin。

## D-033：专家修改自动保存草稿，一键应用到后续评估

- 状态：已接受
- 当前适用性：被 D-051 部分取代。自动保存、允许 incomplete、撤销/重做与最小技术校验继续有效；“草稿”“应用到后续评估”和只有 applied/published scheme 才能运行的交互不再适用。
- 决策：模型修改自动保存到可撤销 draft；incomplete draft 可以继续编辑。用户点击“应用到后续评估”后，后端只做最小技术可运行检查，通过即创建 immutable applied revision 并供后续新 run 使用。正在运行和历史 run 不改变。Apply 不要求人工审批、pytest、build、wheel 或科学验证。
- 理由：版本与历史的作用是撤销、比较和重放，不应变成专家修改参数、公式或网络的阻力。
- 影响：technical validation 只覆盖 schema、dangling reference、DAG、operator/type/unit/parameter、safe formula、output 和 CPT 可执行性。未校准、无文献支持或偏离 starter template 只显示 metadata/warning，不阻止保存或 apply。

## D-034：严格测试属于平台与新算子，不属于每次专家模型修改

- 状态：已接受
- 决策：built-in operators、recipe compiler/executor、draft/revision/replay、BN inference、protocol 和 frontend/backend contract 需要工程测试；新 operator plugin 需要 focused implementation test。专家使用已有 operators 修改参数、公式、连接、Anchor inventory 或 CPT 时不生成或运行新的工程测试。
- 理由：工程测试可以证明平台按 recipe 执行，不能证明 provisional evidence 或 BN 科学正确。要求每次专家修改重新走固定算法 golden 会抵消 free-to-modify 目标。
- 影响：D-025/D-026/D-027 对旧固定 18-plugin M4 completion gate 的要求保留为历史设计与已完成任务证据，但不再定义 M4R 完成条件。Starter templates 只需轻量 executable/trace smoke；用户编辑通过 continuous technical validation 和可选 preview 获得即时反馈。

## D-035：M4 及后续里程碑按专家设计系统重基线

- 状态：已接受
- 当前适用性：重基线继续有效；M5 的详细范围已由 D-036–D-040 和正式 M5 规格具体化。
- 决策：旧 replacement plan Task 29–36 暂停且不再授权执行。M4R 交付 EvidenceRecipe/operator foundation 与 starter migration；M5 交付 linked Evidence/BN model workspace、revision 和 inference；M6 交付 local runtime/persistence/protocol；M7 交付 WinUI expert designer；M8 交付 integration、packaging 和 handoff。
- 理由：继续补完三个固定 AnchorPlugin 会扩大错误路线。Evidence engine、model workspace、runtime 和 Windows UI 又是不同子系统，应分别形成可执行规格和计划。
- 影响：Task 0–28、15 个现有插件和测试保留为历史实现事实与迁移来源，不回滚或删除。新 M4R 计划必须在 [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md) 复核后编写，M5–M8 分别建立正式 spec/plan。

## D-036：全局组件采用 concept + immutable version，方案锁定 exact versions

- 状态：已接受
- 当前适用性：历史 M5/M6 实现与 replay/migration 合同。当前专家工作区不再把同 concept 的并行 versions 作为不同任务的选择机制；由 D-047/D-048/D-051 取代。
- 决策：Evidence、BN node、Evidence-to-BN binding 和 CPT 进入全局版本化组件库。稳定 concept 表示“它是什么”，immutable version 表示一次精确实现；`AssessmentSchemeVersion` 只保存 exact component version references 和 content hashes，不引用可漂移的 `latest`。同一 concept 可以长期并列多个版本，不同任务和同一任务的不同方案可以自由选择。
- 理由：Hover、直线保持和未来任务可能需要同名 Evidence/BN node 的不同算法或概率定义。原地升级会迫使用户在任务之间反复手工改回模型，并破坏历史结果。
- 影响：从任意既有方案编辑都采用 copy-on-write；未改组件继续复用原版本，改动组件与新 scheme 在 publish/apply 时原子创建新版本。旧方案和历史 run 永不被新发布覆盖。完整合同见 [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)。

## D-037：Evidence 提取关系与 BN 概率关系是两种不同的图语义

- 状态：已接受
- 决策：系统高层只显示 Raw Input、Evidence、BN Node 三类节点，但使用两个不同 edge type。`Raw/task source -> Evidence` 是 data/extraction edge，只形成 `EvidenceVersion.recipe.inputs` 和 recipe execution dependency；BN probabilistic edge 表示 child CPD 的 parents 并进入 joint factorization。Raw inputs 不属于 BN random variables，也没有 CPT。
- 理由：Evidence 确实先由 X/U/I/G/P 等 session 数据提取，但这不意味着这些数据源是 BN parents；若混用“父节点”与无类型 edge，前端、CPT 和推理方向都会产生歧义。
- 影响：两类 edge 必须有不同 DTO、operation、视觉样式和 validator。Evidence inspector 同时展示 extraction definition 与 BN interpretation，但不得把两组依赖合并。

## D-038：Starter 使用生成式 BN 方向，后验信息流不反转 canonical edges

- 状态：已接受
- 决策：Hover starter 的 canonical BN 使用 `Competency -> Sub-skill -> Evidence`，其 CPD 分别表达 child 在 parents 条件下的分布；实际评估先提取并观察 Evidence，再计算 sub-skill/competency posterior。前端可用只读 inference overlay 显示 `Evidence ⇢ Sub-skill ⇢ Competency` 的信息影响，但不能把 overlay 保存为反向 BN topology。
- 理由：Bayesian Network 的箭头定义概率分解，不等于程序执行顺序，也不限制 posterior 信息传播方向。把“从证据推断能力”误画成永久反向边会把一个模型变成另一个模型。
- 影响：通用引擎仍允许专家建立满足 DAG、CPD/CPT 和 observation 合同的其他方向；当前产品中这必须通过新的完整节点或明确修改后的节点定义表达，并由 task scheme 激活，而不是同一模型的显示切换。历史 M5 component/scheme versions 继续用于 replay。

## D-039：Hover/18/11/4 只是一套 starter scheme，不是引擎基数或任务锁定

- 状态：已接受
- 决策：当前 Hover 场景、18 个 Evidence、11 个 sub-skills 和 4 个 competencies 用于提供第一个可运行 starter scheme。通用 schema、代码、存储、API、UI 和测试不得硬编码这些任务名、ID、数量或连接。专家可为任意任务创建任意数量方案，并从任意方案继续派生。
- 理由：产品要随专家加入不同任务、Evidence 算法和能力模型而持续扩展；基础示例不应成为系统边界。
- 影响：M5 验收以版本复用、方案组合、可编辑性、技术可运行和历史不变性为准，不以 starter 算法的科学正确性或 exact-18 输出等价为完成门。

## D-040：Legacy Evidence-to-Evidence 提取不能直接进入当前高层模型

- 状态：已接受
- 当前适用性：当前通用基线；明确 D-037 对 legacy/M4R recipe migration 的处理。
- 决策：高层 `EvidenceVersion.recipe.inputs`（即 extraction source bindings）只能引用 raw/session/task sources，不能引用另一条已经评分的 Evidence observation。现有 `starter.o8` 使用 `anchor.O1-score` 与 `anchor.O5-score` 的版本保留为 legacy migration/replay artifact，不得直接成为 D-037-compliant scheme 的 active EvidenceVersion。M5 为 TPX 建立新的并行 EvidenceVersion：其输入必须来自 raw/task sources，或来自 provenance 最终闭合到 raw/task sources 的 typed derived artifact；若专家要表达 Evidence 变量之间的概率关系，则使用 probabilistic edge 和完整 CPD/CPT。
- 理由：把另一 Evidence 的评分当作 extraction input 会混合计算依赖与 BN 概率依赖，并使高层三类节点/两类边失真。静默改写旧 O8 又会破坏 immutable history。
- 影响：M5 migration preflight 必须检测 Evidence-to-Evidence source binding，返回结构化 compatibility diagnostic，并保留旧资源与 lineage；迁移可以为同一 concept 创建新的 compliant version，但不能覆盖旧 recipe。当前已知命中只有 `starter.o8`，实施时仍须对全部导入资源执行通用检查，不能按 O8 ID 写死分支。

## D-041：M6 使用自包含受管项目目录

- 状态：已接受
- 当前适用性：自包含 project、relative managed paths 与用户数据不进产品包继续有效；“后续 M8 备份/导出”由 D-077 的完整目录复制取代，“全局组件库 project-wide”由 D-066 的 software-copy system owner 取代。
- 决策：每个项目使用一个可整体移动的根目录，内部保存 `project.json`、SQLite 数据库、managed sessions、content-addressed artifacts、logs 与 staging。外部 Session Bundle 在 import 时逐字节复制并复核 checksum；导入后运行只引用 exact managed `SessionRevision`。数据库只保存项目相对路径，应用安装包不包含任何用户项目、session 或 run 数据。
- 理由：用户已确认复制到受管项目存储最适合最终 Windows 产品；自包含目录同时满足离线运行、设备迁移、外部源可删除和后续 M8 备份/导出。
- 影响：M5 的“全局组件库”解释为 project-wide、跨任务/方案共享；不同项目默认隔离。跨项目 merge/cloud sync 属于后续版本，不能通过隐式绝对路径关联实现。

## D-042：SQLite 保存 canonical durable state，受管文件保存大型 payload

- 状态：已接受
- 决策：M6 以标准库 SQLite 实现 M5 repository 与 `WorkspaceUnitOfWork` 的 durable adapters；canonical domain object 使用 RFC 8785 JSON bytes 与 exact hash 保存，不使用 pickle。视频、图像、长时序、派生结果和 export payload 进入 managed filesystem，不进入 SQLite BLOB 或 JSON-RPC。
- 理由：SQLite 能在本地单用户环境中提供 component/scheme/draft/run 的原子事务和恢复；大型 payload 由文件合同承载可以避免数据库、内存和协议膨胀。
- 影响：进程内 repositories 继续用于 focused tests；M5 services 和 identities 不因 storage adapter 改变。所有 DB 读取必须重新通过 typed contract/hash 验证。

## D-043：File-backed mutation 使用 staging、content hash 与可恢复 promotion

- 状态：已接受
- 决策：session import、derived artifact 和 result artifact 先写 project-local staging，close 后计算 SHA-256/size/schema，再原子 promote，并在 SQLite 中提交 owner reference、transaction receipt 和 audit event。引用数由引用表推导；无引用 payload 进入保留/清理流程。启动恢复清理没有 durable owner 的 staging/orphan，不把半写结果标为完成。
- 理由：SQLite transaction 不能单独让文件系统写入原子化；显式 intent/staging/promotion/recovery 才能在崩溃点维持确定状态。
- 影响：Evidence/BN 执行不回写原始 Session Bundle。v0.1 crash recovery 恢复到可重试边界，而不是从 operator 中间点继续。

## D-044：M6 冻结本地 stdio JSON-RPC sidecar

- 状态：已接受
- 决策：Windows 前端以隐藏子进程管理 Python sidecar；stdin/stdout 使用 UTF-8 JSON-RPC 2.0 + 单行 JSONL，不监听网络端口。stdout 只允许协议消息，日志写 stderr/文件；单消息默认上限 4 MiB，大数据只传 managed IDs、相对路径、metadata、size 与 checksum。
- 理由：本地离线产品无需 HTTP 端口、服务发现或防火墙配置；stdio 清楚地绑定应用和后端生命周期，并遵守 D-009 的大数据边界。
- 影响：协议层只映射 M5/M6 application services，不复制 Evidence/BN 逻辑。未来 HTTP adapter 必须复用相同 domain services/contracts。

## D-045：所有持久化写操作同时使用幂等 transaction 和 optimistic revision

- 状态：已接受
- 当前适用性：transaction、idempotency、semantic/layout revision 与 audit 原则继续适用；`publish` 作为必经 mutation 类型的要求被 D-051 取代。
- 决策：mutation/import/publish/run.start 必须携带稳定 `transaction_id`，以 canonical method+params hash 作为幂等身份；同 ID 同请求返回首次 response，同 ID 不同请求拒绝。草稿 semantic/layout 修改继续分别携带 expected graph/layout revision；幂等不能绕过 revision，revision 也不能替代幂等。
- 理由：stdio response 丢失或 sidecar 重启会触发安全重试，而前端拖拽/编辑又可能基于过期状态；两类机制解决不同问题。
- 影响：成功 response、audit ID 和新 canonical revisions 必须持久化。便利 RPC 也要转换为同一 typed operation/transaction，不能形成绕过路径。

## D-046：M6 run 锁定 exact snapshot，并以可查询状态恢复长任务

- 状态：已接受
- 当前适用性：exact snapshot、progress/cancel/recovery 与 purpose 分离继续适用；snapshot 输入必须是 published scheme 的限制被 D-051 泛化为任意技术可执行的 current TaskScheme revision。
- 决策：recorded run 锁定 exact managed session revision/root hash、published scheme/components、EvidenceRecipe/operators/scorer、BN/runtime 和参数 identities。progress 先持久化再 notification；cancel 为 cooperative；sidecar crash 后非 terminal run 标记 `interrupted`，不伪造 completed。`preview`、`software_test` 和 `assessment` 分开；synthetic/engineering starter 可完成 software test，但不能冒充正式科学评估。
- 理由：前端断开、响应丢失或进程崩溃不应丢失历史或改变模型；同时当前 synthetic 数据和 starter policy 明确不支持正式结论。
- 影响：run preflight 只检查 frozen technical closure、purpose 和 declared provenance，不按飞行/生理表现或所谓数据质量过滤 Evidence。v0.1 interrupted run 通过新 run 重试，不原地续算。

## D-047：每个可见节点是一个完整、独立、只有一个当前定义的节点

- 状态：已接受
- 决策：Raw Input、Evidence 和 BN Node 是三个高层节点类型。每个 Evidence/BN `ModelNode` 拥有稳定 `node_id`，其名称、说明、fixed parents、EvidenceRecipe/parameters/scorer 或 states/CPT/CPD 都属于该节点的完整 current definition。若 task-specific 算法、parent set、CPT 或语义不同，必须复制或新建为另一个节点，例如 `Precise`、`hover.Precise` 与 `straight.Precise`，不能让一个圆形节点在任务切换时替换内部 component version。
- 理由：用户希望专家通过复制基础节点形成直观、并列的任务节点；同 concept 多版本选择会把任务差异隐藏在版本槽位中，并重新引入覆盖/切换歧义。
- 影响：一个节点可被多个任务共享，但共享时全部定义必须相同。内部 revision/change history 只用于 autosave、并发、undo/replay，不作为任务侧可选业务版本。D-036 的 task-specific parallel version UX 被本决策取代。

## D-048：任务方案是全局完整节点上的可编辑激活集合

- 状态：已接受
- 决策：每个 `TaskScheme` 并列存在，保存 explicit active node IDs、由 fixed parents 计算的 active closure、outputs、task/reference bindings 和 layout overrides。切换方案只改变节点/边的亮暗与执行集合，不替换节点内部定义。Edges 从 child 节点的 source bindings 或 probabilistic parent set 投影，不由任务方案另行覆盖。
- 理由：系统会积累大量相似但独立的节点；以 active/dim 展示当前任务使用范围，专家可以直接理解网络，同时保留全局节点以便复制和复用。
- 影响：画布提供 active-only、active+inactive、all-global、搜索/标签/分组视图。共享节点修改会影响所有引用它的方案的未来运行；若需隔离，专家先复制节点。

## D-049：启用递归闭包；停用有下游影响时由用户确认原子级联

- 状态：已接受
- 决策：启用 child 时，后端在一个事务中递归启用全部 fixed data/probabilistic parents，不弹提示。停用仍有 active downstream dependents 的 parent 时，前端列出当前任务内全部递归影响，并提供“继续停用/取消”；继续后原子级联停用，其他任务不变。停用 child 后重算闭包，不再被 explicit selection 或其他 child 需要的 ancestors 自动变暗。
- 理由：自动补齐 parents 符合专家对依赖网络的预期；停用 parent 会扩大影响，必须在执行前可见且可撤销。
- 影响：方案持久化区分 explicit selection 与 computed closure，支持 canonical diff、undo/redo 和 stable transaction receipt。

## D-050：节点复制只复制所选完整节点，并继续引用原 fixed parents

- 状态：已接受
- 决策：默认 copy/paste 深复制所选节点自身的 recipe、parameters、states、CPT、metadata 和布局，为副本创建新 `node_id` 与 `copied_from_node_id`；parent nodes 不复制，fixed parent references 保持原 ID，原 downstream children 也不自动改用副本。粘贴到当前任务后，新节点显式激活并自动启用 parent closure。复制方案只复制 activation/configuration/layout，默认共享全局节点。
- 理由：专家最常见的任务定制是从基础节点复制一个近似定义再修改；复制整条依赖树会产生大量无意义副本，覆盖原节点又会影响其他任务。
- 影响：支持 Ctrl+C/Ctrl+V、右键、多选和项目内跨任务粘贴。修改副本 parents 时，它仍是同一个新节点的完整定义，CPT 必须原子迁移或重建。

## D-051：取消 Draft/Published/Apply/Publish 正常流程；每次运行自动冻结快照

- 状态：已接受
- 当前适用性：取消业务 Draft/Published/Apply/Publish、并列 TaskScheme 和每次运行冻结快照继续有效；“每次 autosave 立即成为 canonical current object”的提交时机被 D-056 取代。
- 决策：所有 TaskSchemes 都是并列、autosaved、freely editable、directly runnable 的 current objects。正常 UI 只显示 saving/saved/save failed/configuration incomplete，不提供 Draft/Published 或 Apply/Publish gate。技术可执行的当前 scheme 可直接 run；`run.start` 先冻结 exact managed session、scheme activation closure、完整 node definitions、recipes/operators/scorers、parents、states、CPTs、runtime parameters 与 hashes 为 immutable `RunSnapshot`。后续编辑只影响未来 runs。
- 理由：任务方案本身就是长期并列的工作对象，额外发布状态没有产品价值，反而妨碍专家自由修改。可重放性真正需要的是每次运行锁定精确输入，而不是强迫用户管理发布版本。
- 影响：D-033、D-036 的 apply/publish 交互以及 D-045/D-046 中 published-scheme 前提被取代。Append-only change journal、undo/redo、optimistic revision、content hash、历史 run snapshot 和旧 published records 继续保留。Incomplete 方案可保存但 run preflight 会阻止技术上不可执行的运行。

## D-052：M7 使用任务侧栏、亮暗全局画布、多浮动节点窗口和即时界面语言切换

- 状态：已接受
- 决策：Model Studio 左侧直接切换/复制任务方案；圆形节点以 type 区分颜色，active 明亮、inactive 变暗且仍可点击/复制；点击节点打开可移动、缩放、最大化的非模态独立窗口，允许多个窗口和多显示器并排编辑。顶部 `中文 | EN` 即时切换，系统 UI 使用 WinUI resources。最初要求后端保存 bilingual model metadata 的部分已被 D-055 取代。
- 理由：专家需要在大量节点和多个任务之间直观比较、复制和修改，固定 Inspector、单窗口或只显示 active 子图都不足以支持该工作流。
- 影响：浮动窗口显示 canonical autosave state、usage、recipe/CPT、preview/trace 和 history；语言切换不得改变 ID、hash 或计算。

## D-053：前端修改必须落到后端 canonical definitions，M7 先迁移 M5/M6 编辑语义

- 状态：已接受
- 当前适用性：typed backend operation、Python execution authority、C# 不复制算法和普通编辑不改 `.py` 继续有效；每次 mutation 立即写 canonical definitions 的提交时机被 D-056 改为先写 backend-managed edit session、关闭时统一提交。
- 决策：所有前端 node/edge/recipe/parameter/state/CPT/scheme edits 都调用 typed backend operations，并以后端 response 作为 canonical state；C# 不复制算法，UI 也不改写 `.py` 源文件。通用 Python engine 执行 persisted EvidenceRecipe/CPT definitions；只有 operator library 缺少新能力时才新增 trusted Python operator。M7 实施先新增 current ModelNode/TaskScheme persistence、activation closure、autosave/current-scheme run API，再开发 WinUI 页面。
- 理由：用户要求前端展示的每个可修改部分都真实改变后端计算，同时普通专家编辑不能变成 Python 发布流程。现有 M5/M6 draft/publish API 无法完整表达 D-047–D-052，必须显式迁移而不是在前端伪装。
- 影响：M1–M4R 数据/recipe/operator、M5 BN inference 和 M6 managed project/artifact/stdio 基础继续复用；旧 component versions、published schemes 和 runs 保持可读/回放，正常 M7 UI 不再调用 publish。权威规格见 [M7 WinUI Expert Designer and Task Activation Workspace Design](specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md)。

## D-054：画布使用五个统一绿色的原始输入族投影节点和只读来源连线

- 状态：已接受
- 当前适用性：五个绿色 projection roots、typed provenance 和非 canonical 语义继续有效；“固定显示”和统一 canonical lane offset 的展示细节被 D-057 取代。
- 决策：Model Studio 在所有 canonical nodes 左侧固定显示 `X(t)`、`U(t)`、`I(t)`、`G(t)`、`P(t)` 五个较大的 Raw Input Family projection nodes。五个节点统一使用 theme-aware 绿色，与其他节点类别区分；`X/U/I/G/P` 符号和当前界面语言下的 UI 标签区分具体输入族。现有细粒度 Raw Input nodes 依据 typed family/raw modality/source dependencies 显示到族节点的只读 provenance links；`pilot_camera` 在画布投影中归入 I，但 backend modality 身份不改变。
- 理由：专家需要从左到右直接看清“原始输入 → 细粒度输入/Evidence → Sub-skill → Aggregate competency”的来源关系，同时不能把概览入口误当成第二套可执行数据定义。
- 影响：族节点和 provenance links 仅属于前端确定性投影，不创建 `ModelNode`/`ModelGraphEdge`，不参与 task activation、graph hash、CPT、RunSnapshot 或推理；canonical layout 只在渲染时整体右移，不写回持久化坐标。

## D-055：界面本地化与专家模型内容分离，模型内容统一保存英文

- 状态：已接受
- 决策：应用菜单、按钮、字段标题、提示、状态、对话框和错误信息由 WinUI resources 随 `中文 | EN` 完整切换。节点、任务方案、Evidence/BN/operator 的名称、描述、help text 等专家定义内容只保存一份英文 canonical value，不再并排保存或编辑中英两份。语言切换不改写模型内容，也不产生 backend mutation、revision 或 hash 变化。
- 理由：中文/英文切换是软件界面能力，不应把同一科学模型拆成两套易失配的数据；统一英文模型内容也更适合跨任务复用、源码扩展和后续交付。
- 影响：当前 contracts/UI 需要迁移到单字段模型，并保留旧 v0.1 bilingual records 的兼容读取或一次性迁移；既有不可变 RunSnapshot 按原合同继续回放。D-052 的 bilingual model metadata 部分被本决策取代。

## D-056：一次应用会话的模型修改先写后端持久草稿，关闭时统一保存或放弃

- 状态：已接受
- 决策：打开项目后，所有 ModelNode、edge、CPT、TaskScheme、activation 和 layout 修改先通过原有 typed operations 写入由 Python backend 管理的独立持久 edit-session SQLite，不实时覆盖 canonical workspace。主窗口关闭时，若有改动只提供“保存全部并关闭／放弃全部并关闭／取消”：保存使用一个原子 canonical transaction；放弃保持 canonical 逐字不变；取消返回应用。节点浮动窗口关闭只 flush 草稿。Ctrl+Z/Ctrl+Y 操作全局 edit-session history。dirty session 下 preview/preflight/run 必须先明确解决草稿。
- 理由：专家需要自由试改并在一次工作完成后统一决定是否保留，不能因为字段离焦、拖拽或 debounce 就永久改动系统；同时草稿仍需由后端持久保存和验证，以支持崩溃恢复、跨窗口一致性和不丢编辑。
- 影响：这不是重新引入业务 Draft/Published/Publish。D-051 的无发布工作流和 RunSnapshot 继续有效；D-053 的 backend operation/Python execution authority 继续有效，但 canonical 提交时机改为明确的 Save all。详细规格见 [M7 Staged Edit Session and Five-Layer Canvas Amendment](specs/2026-07-18-m7-staged-edit-session-and-five-layer-canvas-amendment.md)。

## D-057：主画布只使用五个理解层并固定从左到右投影

- 状态：已接受
- 决策：Model Studio 的唯一顶层层级为 `Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency`。五个 X/U/I/G/P 绿色大圆属于第一层；现有细粒度 Raw Input nodes 属于第二层；Evidence 属于第三层；非 aggregate BN 属于第四层；AggregateCompetency BN 属于第五层。层级筛选只显示“全部”和这五类，选择非 Raw Input Family 层时不强制显示五个根；`evidence.O1` 等技术 tag 不再是主画布顶层分类。
- 理由：专家需要先按计算抽象层理解大量节点，而不是按内部类型或细粒度标签筛选；固定层级也能稳定呈现原始输入到能力结果的完整工作流。
- 影响：物理布局从左到右，但 canonical BN 生成方向仍为 `Competency -> Sub-skill -> Evidence`，概率箭头允许从右指向左，绝不能反转 parent/CPT/DAG。每层使用可逆 render-only offset，筛选不改变保存坐标；operator 仍不进入主画布。

## D-058：普通产品界面只呈现语义英文名称，技术身份按层展示

- 状态：已接受
- 决策：Model Studio、任务侧栏、普通 Runs/Results 列表和节点窗口标题只显示简洁英文模型名称，不拼接 `node_id`、`scheme_id`、UUID 或 hash，也不显示“未命名节点”与 `[EN fallback]` / `[中文回退]` / `[ID fallback]`。英文名称缺失时，前端按 typed source、EvidenceRecipe anchor、BN reporting metadata/role 或 task binding 确定性生成与对象实际作用对应的英文名称。Diagnostics、Provenance、Artifacts、frozen snapshot 和默认折叠的 Technical identity 区域继续保留 exact ID/hash。
- 理由：稳定技术身份对持久化、复现和诊断必不可少，但把随机标识当作普通名称会显著降低产品成熟度和专家可读性；名称解析必须使用已有模型语义，而不是用随机 ID 或模糊占位符掩盖缺失内容。
- 影响：该规则是只读 presentation projection，不改变 canonical identity、revision、hash 或 RunSnapshot。D-055 的单字段 canonical contract 迁移仍需单独完成；本决策先关闭所有可见 fallback marker 和普通界面 ID 泄漏。

## D-059：桌面产品使用统一的原创极简 eVTOL 评估图标

- 状态：已接受
- 决策：Pilot Assessment Desktop 使用深海军蓝圆角底板、白色俯视四旋翼 eVTOL 与中央评估网络节点组成的原创无文字图标。一个项目内 1024 px RGBA master 确定性派生 ICO、Square、Store、Splash、Wide 和 unplated Windows assets。
- 理由：一致且小尺寸可辨识的产品标记能替代模板图标，明确软件的 eVTOL 与评估定位；单一 master 可避免任务栏、窗口、启动和发布资产漂移。
- 影响：图标资产只改变产品品牌呈现，不改变功能、协议、数据、科学模型或发布边界。派生脚本保存在仓库中，M8 打包继续复用同一 master。

## D-060：模拟器原始导出在受管 staging 中物化为 canonical Session Bundle

- 状态：已接受
- 决策：模拟器可以只导出只读的 `streams/` 与 `annotations/`。前端统一选择 session 数据目录，后端自动区分 canonical Bundle 与 simulator raw source；raw source 在项目 staging 中复制原始文件、生成 canonical annotations、`manifest.json` 与 checksums，通过既有 M1/M2 校验后原子提升为受管 `SessionRevision`。已有 canonical Bundle 继续走 byte-preserving exact-copy 分支。缺失模态只记录为 `missing`，不得合成传感器数据。
- 理由：manifest 是系统内部和标准交换合同，不应成为模拟器导出器或普通用户的手工负担；同时受管 materialization 保持项目可迁移、外部源可删除和历史运行可重放。
- 影响：新增统一的 `session.source.inspect/import` 协议与 source fingerprint stale-check；raw source 始终只读，系统生成内容只写入项目 staging/managed storage。运行继续只读取 exact managed revision，不直接依赖外部目录。

## D-061：未声明单位保持未声明并按固定 adapter/Evidence 规则原值透传

- 状态：已接受
- 决策：原始文件和可信 adapter profile 都未声明字段单位时，系统不要求用户输入、不根据数值猜测、也不做隐式换算。生成 manifest 时 stream `units` 保持空 object、字段 `declared_unit` 保持 null；数值仍按已匹配的固定 adapter mapping 进入现有 EvidenceRecipe/operator。provenance 记录 `unit_handling=undeclared-pass-through-v1`。
- 理由：当前目标是接收模拟器实际导出并运行既定 Evidence 提取方法，而不是把单位补录或数据质量研究转嫁给普通用户。虚构单位会比明确留空更危险。
- 影响：缺失单位不进入 `required_user_inputs`、不阻止 inspect/import，也不在 WinUI 中出现单位填写控件。由此产生的结果只证明固定 starter 工作流可执行，不证明单位语义、Evidence 算法或科学结论正确；未来可信 profile 若明确单位，可在新 profile 中声明并执行显式版本化换算。

## D-062：M8 首个交付采用 Windows x64 unpackaged self-contained 便携目录

- 状态：已接受
- 决策：首个产品交付为 Windows x64 ZIP；解压后直接运行 `PilotAssessment.Desktop.exe`。桌面端同时携带 self-contained .NET 与 Windows App SDK 文件，目标机不要求 Visual Studio、.NET SDK 或预装 Windows App Runtime。首阶段不使用 MSIX、安装器、自动更新或 single-file。
- 理由：用户要求把后端运行环境、代码和前端打包为可迁移系统，并让其他 Windows 用户解压后直接使用。
- 影响：发布构建固定 `win-x64`、`WindowsPackageType=None`、`.NET self-contained` 与 `WindowsAppSDKSelfContained=true`；最终干净机器验证保留到 M8E。

## D-063：Portable runtime 优先运行包内 private Python 与唯一活动 backend source

- 状态：已接受
- 决策：产品模式优先从 `AppContext.BaseDirectory` 定位 `runtime/python/python.exe`、`runtime/site-packages` 与 `backend/src/pilot_assessment`；`backend/src/pilot_assessment` 是发布副本唯一活动的第一方 Python tree，不安装隐藏的项目 wheel 或第二份源码。只有 portable layout 不存在时才回退到仓库 `.tools/uv/uv.exe` 开发模式。
- 理由：产品必须离开仓库运行，同时满足专家直接修改发布副本 Python 源码、重启后全局生效的自由度要求。
- 影响：普通 Evidence/BN/CPT/task 参数仍通过前端编辑；新增底层计算机制或 core 修改可直接改 live `.py`。source baseline 用于说明和恢复，不得仅因本地修改阻止启动。

## D-064：通用产品包只包含系统，不包含任何用户或测试 Session 数据

- 状态：已接受
- 决策：产品 ZIP 只包含桌面端、private runtime、完整第一方 backend source、starter resources、必要开发源码、发布工具、文档和清单。用户 project、SQLite、Session、X/U/I/G/EEG/ECG/camera、运行结果、artifact、偏好、日志、repository-external 样例与临时 synthetic 数据全部排除。
- 理由：系统需要可迁移到不同 Windows 设备，而每个使用者应自行选择要评估的 Session；数据不是产品本体。
- 影响：发布 pipeline 必须执行路径、扩展名、缓存、绝对私有路径和内容扫描；用户项目继续保存到用户选择的位置，SQLite 不作为单独服务启动。

## D-065：M8A 工程包可记录 dirty source，M8E 正式候选必须来自 clean tagged source

- 状态：已接受
- 决策：为包含当前尚未提交的 M7 用户返修，M8A engineering build 可以从 dirty working tree 构建，但 `release-manifest.json` 必须明确记录 commit 与 dirty 状态。M8E release candidate 必须来自 clean、可追溯 source，并重新执行完整交付验收。
- 理由：当前优先目标是尽早验证真实打包链，不应因历史工作树尚未分批提交而阻塞 M8A，也不能把不可复现工程包冒充正式发布。
- 影响：M8A ZIP 可以交给用户本机验收，但不得标记为 final release candidate。

## D-066：每套软件副本在 `system/` 中拥有唯一 canonical 模型库

- 状态：已接受
- 决策：一套解压后的 `PilotAssessment/` 只拥有一个 `system/model-library.sqlite3`，其中保存全部 current ModelNode、EvidenceRecipe、BN parent/state/CPT、TaskScheme、activation 和 layout。它不放入用户 project，也不静默迁移到 `%LOCALAPPDATA%`。复制整套软件目录会复制当前 system model，两个副本随后独立演化。
- 理由：用户要求所有 project 共享同一套可自由编辑的 Evidence/BN/任务方案，同时保留“复制整套软件即可形成平行系统分支”的直观迁移方式。
- 影响：D-041、D-042、D-048、D-056 中把 current model 或 edit session 写成 project-owned 的措辞被本决策取代；starter 仍是可修改工程模板，不是科学真值。

## D-067：`SystemApplication` 先于 project 启动，Model Studio 无 project 可用

- 状态：已接受
- 决策：sidecar 启动时先打开 system locator/database、current-model workspace、持久 edit session、operator/source registries 与 starter seed。所有 `model.*`、`operator.*` 和兼容 model-library RPC 绑定 `SystemApplication`。`ProjectApplication` 为可选上下文，只拥有 Session、Run、Result、artifact 与项目恢复。
- 理由：模型设计是产品系统能力，不应要求先创建一个虚假的用户 project；project 的存在只由评估数据和运行历史决定。
- 影响：关闭或切换 project 不关闭 system model，也不清空 dirty model edit session；Session/Run/Result 页面无 project 时禁用，Model Studio 继续工作。

## D-068：run 从 system current state 冻结 exact model 到 project，不再依赖 project-local current model

- 状态：已接受
- 决策：preflight 同时锁定 project 的 exact SessionRevision 与 system 的 clean TaskScheme、active ModelNode closure、operator/source/runtime identities；run start 前执行 stale-check，然后把完整模型执行副本和 RunSnapshot 写入目标 project。pipeline 只读取冻结副本，历史运行不重新解析为当前 system model。
- 理由：全局模型需要随专家修改而立即服务未来运行，但任何后续修改都不能改写已经完成的评估证据和结果。
- 影响：新 project 不 seed editable model；`RunRepository.create_current()` 不再查询 project-local `model_nodes/task_schemes`。project 移动后仍可读取旧 run，而新 run 使用当前软件副本的 system model。

## D-069：legacy project-local 模型只读保留并以确定性、事务化、无覆盖规则合并

- 状态：已接受
- 决策：打开 legacy project 时按 canonical fingerprint 幂等导入 system store。相同 ID/hash 复用，缺失 ID 原样导入，相同 ID/不同内容生成确定性 imported ID，并且只改写明确 typed references；任一校验失败整笔回滚。原 project tables/bytes 不删除、不覆盖。
- 理由：旧项目可能包含用户已经修改的节点、CPT、方案或未提交草稿，必须迁移而不能静默丢弃，也不能覆盖另一项目先导入的 system 对象。
- 影响：最多自动恢复一套 legacy dirty edit session；若 system 已有 dirty session，第二套草稿原样保留并返回 recoverable conflict，等待用户显式处理。

## D-070：一套软件副本只有一个 system writer，project 生命周期不改变 system edit session

- 状态：已接受
- 决策：`system/` 使用 software-copy-scoped single-writer lock；一个 WinUI 主进程及其多个节点浮窗共享同一 sidecar/edit session。第二个主进程不得并发写同一 system store。project create/open/close/switch 不自动 Save、Discard 或替换 system 草稿；仍只在主应用关闭时提供“保存全部／放弃全部／取消”。
- 理由：SQLite 串行事务不足以表达两个独立 UI 会话的全局 undo/redo 和关闭决策；单 writer 能保持专家可理解的会话语义，而不引入审批或发布流程。
- 影响：应用目录必须可写；锁冲突和不可写目录必须给出稳定错误，不得静默选择另一套隐藏模型库。

## D-071：源码/模型 baseline 偏离只记录，运行身份对应当前进程真实加载的代码

- 状态：已接受
- 决策：system model 和公开 `backend/src` 都允许用户直接修改；与出厂 baseline 不同只标记 `locally_modified`，不审批、不阻止启动或运行。sidecar 启动冻结 `loaded_source_identity`；若当前进程启动后磁盘源码或 dependency lock 又变化，新 run 以 `runtime_restart_required` 阻止，避免记录的 hash 与已加载实现不一致。语法/import/contract 错误必须真实失败，不得加载隐藏 baseline。
- 理由：产品要为专家自由设计模型和底层算法服务，同时必须能准确回答某次 run 实际使用了哪套代码，而不能用磁盘最新内容冒充进程已加载内容。
- 影响：完整 source/runtime/operator identity、source snapshot artifact 与新增 operator 闭环在 M8B-1/M8B-2 实现；D-063 的唯一活动 source tree 继续有效。

## D-072：Markdown、TOML metadata 与 catalog 是文档权威，DOCX 是版本化生成物

- 状态：已接受
- 决策：每份手册正文只在语言专属 Markdown 中维护，并使用 TOML front matter 保存 document ID、产品/文档版本、状态、读者、信息类型、科学状态和稳定引用。`catalog.json` 管理 12 类 logical documents、语言 source/output、依赖门和聚合顺序。DOCX、静态目录、渲染图与总册全部由固定工具链生成，不手工维护平行正文。
- 理由：用户要求可交付的精细 DOCX，同时需要后续专家和开发者能够长期修改；原稿/生成物分离可以避免 Word 手改、总册复制和多语言文件长期漂移。
- 影响：DOCX 中的手工修改会在下一次构建被覆盖；需要修改内容时必须回到 Markdown/catalog/assets。M8C validator 负责 metadata、catalog 和 output parity。

## D-073：中文与英文独立输出，共享技术身份且不在正文中混排

- 状态：已接受
- 决策：每个 logical manual 具有 `zh-CN` 与 `en-GB` 两份 source/output，二者共享 document ID、product/document version、scientific status、related-doc set 和技术 identity。标题、解释与操作文案本地化；文件路径、RPC、schema、operator/error ID 和代码保持英文原值。
- 理由：符合用户“界面选择一种语言完整呈现”的产品理念，也避免在同一手册段落中堆叠双语而降低可读性。
- 影响：language parity 是构建门；D-055 的 canonical 模型单英文存储仍是独立产品迁移，文档本地化不能替代它。

## D-074：手册统一采用可审计的 compact reference 样式与 headless-safe 静态目录

- 状态：已接受
- 决策：版本化 DOCX 使用 `compact_reference_guide` 的精确页面、字体、spacing、numbering 和 DXA table tokens，并统一使用 `editorial_cover` 首屏。目录和内部引用以 heading bookmark/static hyperlink 为确定性基线，不依赖用户打开 Word 后更新 field 才能可读；可以附加 Word field，但它不是正确性前提。
- 理由：技术手册需要密度、层级和跨机器一致性；默认 Word 样式、假 bullet、百分比 table 和未更新 TOC field 会导致不可重复版面。
- 影响：M8C builder 和 structural audit 共同执行 token map；每个交付 DOCX 仍必须 render 为 PNG 并逐页视觉复核。

## D-075：最终 UI 截图受 M7 用户验收与隐私 manifest 控制

- 状态：已接受
- 决策：每张截图必须有 stable ID、产品版本、语言、主题、hash、隐私复核和状态；最终操作截图只从通过用户验收的对应 build 获取，不能暴露真实 Session、生物数据、用户名或绝对路径。M7 UAT 前可以使用架构图和明确的无敏感 mock/synthetic 画面，但不得标记为 final screenshot。
- 理由：过早截取尚在返修的 UI 会快速过期，真实数据截图又可能泄露隐私；截图必须像代码和合同一样可追溯。
- 影响：M8C-0 不因缺少最终截图而伪造它；M8C-1/M8E 前必须关闭 screenshot manifest 的 pending 项。

## D-076：技术总册只聚合模块，release 只交付依赖门已满足的文档

- 状态：已接受
- 决策：`PAS-TECHREF-001` 按 catalog 顺序从 1–11 类 source body 自动聚合，不维护重复 Markdown 正文。`released` 产品文档只包含 dependency gate 已关闭且 inclusion policy 允许的 outputs；`draft/review` 候选只能进入明确标识的 engineering docs 区域。
- 理由：总册复制会产生第三套权威文本；未完成 M8D/M8E 或尚待 M7 UAT 的操作说明也不能因为已经生成 DOCX 就冒充可用功能。
- 影响：M8C-0 可以验证聚合机制但不关闭最终总册；release verifier 检查 catalog、status、hash 与实际文件一致。

## D-077：取消专用备份产品，正式发布显式捕获当前 system

- 状态：已接受
- 决策：M8D 不建设 `.paprojbackup`、`.pasystembackup`、Backup/Restore UI、自动周期备份或 restore archive。用户 project 在软件完全关闭后通过复制完整 project 目录移动；整套软件目录复制会形成包含当前 `system/` 与 `backend/src/` 的独立工作副本。正式 builder 必须从显式 `--system-source` 捕获已保存、已关闭、无 dirty edit session 且不含 user-owned rows 的 current system，不得在输入缺失或无效时静默重新 seed starter model。发布 manifest 记录实际 model identity 与动态 node/scheme counts；新包不会自动更新已经分发的旧副本。
- 理由：模型编辑属于 software-copy-scoped system state，项目数据属于 project。额外 backup 格式和恢复界面不会改善这套 ownership，反而引入第二套封装、同步歧义和不必要的开发成本。现有 builder 固定重新生成 `53` nodes / `1` scheme 会丢失专家已保存的 current model，必须由 current-system capture 取代。
- 影响：M8D 改为 Current-System Packaging、Project Portability and Diagnostics；M8C 的未发布 `PAS-BACKUP-001` 迁移为 `PAS-PORTABILITY-001`。正式构建要求应用已关闭并明确选择 system source；项目复制要求应用已关闭并复制整个目录。M6 relative-path、M8B system ownership/RunSnapshot/source identity 与现有 Diagnostics 继续有效；不新增云同步、自动更新、项目 merge 或用户数据打包。

## D-078：取消单独 M7 中间用户验收硬门，直接验收完整 M8E 候选

- 状态：已接受
- 决策：M7 engineering verification 之后直接完成 D-055、M8C-1 与 M8E，并构建完整发布候选；用户不再先执行一轮独立 M7 中间验收，而是直接验收完整候选。候选构建完成只表示 engineering candidate ready，不表示用户已经接受，也不得称为 final release。
- 理由：用户希望一次验收完整软件、文档和交付包，避免在未完成产品与最终候选之间重复验收；工程验证与用户主观使用验收仍需保持不同状态。
- 影响：旧 M8 大纲中把 M7 用户验收写成 M8C-1/M8E 构建前 Gate 0 的口径被取代。若用户要求修改，则修订后形成新的候选序号；只有用户接受且对应内容不再变化后，才能从已接受 source 重建正式版本。

## D-079：首个最终验收候选采用独立的 `v0.1.0-rc.1` 身份

- 状态：已接受
- 决策：首个完整候选固定为 clean tagged-source `v0.1.0-rc.1`。release metadata 分别记录 `product_version=0.1.0`、`release_channel=release-candidate`、`candidate=rc.1`、`release_label=v0.1.0-rc.1` 和 `user_acceptance=pending`；不得只靠 ZIP 文件名表达状态。
- 理由：产品语义版本、候选序号和验收状态是不同维度；显式拆分可以避免把尚未验收的候选误当成正式 `v0.1.0`。
- 影响：候选必须由 annotated tag 指向的 clean commit 构建。源码、current system、released documentation 或候选截图 bytes 发生变化时必须产生新的 candidate sequence；用户接受后也必须从对应 source 重建 `v0.1.0`，不能只重命名候选 ZIP。

## D-080：M8C-1 可交付经过隐私复核的 release-candidate screenshots

- 状态：已接受
- 决策：M8C-1 可以从对应候选 build 捕获中英文 UI 截图，并在 screenshot manifest 中标为 `release-candidate`。截图仍必须具备 stable ID、build identity、language、theme、SHA-256 和 privacy review，且不得包含用户数据、真实生物数据、用户名或绝对路径。
- 理由：D-078 把用户验收移动到完整候选之后，因此文档必须能在候选构建时携带真实 UI 画面，同时不能把待验收画面冒充 final。
- 影响：D-075 的隐私、追溯和过期检查继续有效；只有用户接受且 UI 未变化时，同一 image bytes 才能在正式重建中晋升为 final。若 UI 变化，必须重新捕获和复核。

## D-081：自动隔离验证与用户独立验收分别记录

- 状态：已接受
- 决策：构建机上的仓库外 disposable extraction、受限 `PATH` 和自动 vertical-slice verification 形成 engineering evidence；用户在自己的 Windows 环境中打开完整候选并操作形成 independent user-acceptance evidence。两者不能互相冒充，也不能在未实际使用 Windows Sandbox 或独立 clean machine 时写成相应验证已经执行。
- 理由：当前会话无提权权限，无法保证启用 Windows Sandbox；验证记录必须精确说明实际执行环境，而不是用近似隔离条件制造过度声明。
- 影响：`v0.1.0-rc.1` 可在自动隔离验证通过后交付且保持 `user_acceptance=pending`。用户验收记录单独关闭 acceptance；任何未执行的 Sandbox、VM 或独立设备矩阵项继续写为 pending/not executed。

## D-082：RC.1 用户验收结论为 `changes-required`，不得改写原候选

- 状态：已接受
- 决策：`v0.1.0-rc.1` 的独立用户验收记录为 `changes-required`。其 annotated tag、commit、ZIP、checksum 和自动验证记录保持不可变；全部修订进入新的 `v0.1.0-rc.2` candidate，且 RC.2 的 `user_acceptance` 重新从 `pending` 开始。
- 理由：RC.1 根目录暴露 94 个文件夹与 374 个文件，大量 WinUI/.NET runtime payload 淹没产品语义入口。修订历史候选会破坏验收对象与工程证据的一一对应。
- 影响：任何“RC.1 已通过用户验收”或直接把 RC.1 重命名为 final 的口径均无效；发布状态、README、验收记录和后续 tag 必须反映新的 candidate sequence。

## D-083：桌面运行载荷收纳到 `app/`，产品根目录只有一个启动器

- 状态：已接受
- 决策：portable product 根目录只允许 `PilotAssessment.exe`、`README.txt` 以及 `app/`、`backend/`、`system/`、`runtime/`、`developer/`、`docs/`、`licenses/`、`manifest/`。完整 WinUI/.NET/Windows App SDK publish 位于 `app/`；用户只启动根 `PilotAssessment.exe`，不得把内部 `app/PilotAssessment.Desktop.exe` 作为第二个根入口。
- 理由：产品结构应先呈现可理解、可编辑和可维护的语义边界，而不是暴露框架部署细节。单一根入口也能避免用户误移动某个 DLL 或直接绕开产品根定位。
- 影响：本决策只取代 D-064 与 M8A/M8E 中关于根 EXE 和 desktop payload 位置的旧口径；unpackaged self-contained、无需预装 .NET/Python/SQLite 服务、活动 Python 源码与 software-owned `system/` 的其他边界继续有效。release manifest、runtime locator、manuals 与 verifier 必须共同执行该布局。

## D-084：RC.2 用户验收为 `changes-required`，修订进入 RC.3

- 状态：已接受
- 决策：`v0.1.0-rc.2` 的独立用户验收记录为 `changes-required`。RC.2 tag、commit、ZIP、checksum 与工程验证证据保持不可变；评估用途、任务栏图标、全局删除节点和长按拖动四项修订统一进入 `v0.1.0-rc.3`，其 `user_acceptance` 从 `pending` 重新开始。
- 理由：工程自动验证不能替代用户对真实 Windows 交互的验收；修改已被测试对象必须产生新的候选身份。
- 影响：任何“RC.2 已通过用户验收”的当前状态均无效。RC.3 必须重新生成受影响的可执行文件、文档、截图身份、manifest 与外部验证证据。

## D-085：Assessment 用途可执行，科学授权状态与技术 readiness 分离

- 状态：已接受
- 决策：`purpose=assessment` 是写入 RunSnapshot 的评估用途标签，不再要求 `formal_run_authorized=true` 才能技术执行。只要 preflight 的结构、依赖、source、runtime 和模型合同 ready，Assessment run 可以创建并运行；未获正式授权时返回 `run.assessment_not_authorized` warning，保留 `formal_run_authorized=false` 的精确 preflight provenance，并把结果继续标为 engineering-only。
- 理由：用户需要用当前工程模型完成真实的评估工作流，同时明确知道该模型尚未经过专家校准。把科学声明误作技术开关会阻止产品的核心用途。
- 影响：D-046、M6 规格/计划与 glossary 中“Assessment 必须 formal true”的旧口径由本决策取代。`formal_run_authorized=false` 仍禁止把结果宣称为科学验证、资格认证或运行决策依据；真正的技术错误和 dirty/stale model/source 仍然阻止 run。

## D-086：全局删除节点采用暂存归档并原子级联任务方案

- 状态：已接受
- 决策：Model Studio 的“删除节点”调用 backend `model.node.archive`。确认后，同一 edit-session 事务先把该节点及其 downstream 依赖从所有受影响 TaskScheme 的 active closure/output 中移出，再归档 current global node。操作可 Undo/Redo，并在关闭时随 Save All/Discard All 一并提交或放弃。
- 理由：专家需要直接删除不再需要的当前节点；仅提供“从当前任务停用”不能表达全局移除。物理抹除又会破坏审计与历史重放。
- 影响：历史 RunSnapshot、run、result 和 artifact 永不改变。一个仍被多个任务使用的节点删除时会影响这些任务，因此 UI 必须先明确确认；后端返回 affected schemes，不能由 C# 猜测或局部模拟。

## D-087：发布图标和节点拖动必须以实际 WinUI 运行坐标为准

- 状态：已接受
- 决策：窗口图标从 `AppContext.BaseDirectory/Assets/AppIcon.ico` 解析绝对路径，资产同时复制到 build/publish。节点通过 handled-events-too 接收 Button 已处理的 pointer 事件；按住主键并移动至少 4 px 即在稳定坐标系中跟随指针，不再依赖容易失效的驻留计时器，release 时只提交一次 layout delta。
- 理由：相对路径会在根 launcher + `app/` 的发布布局下随工作目录漂移；WinUI Button 会处理 pointer 事件，且以移动元素自身为坐标原点会抵消可见位移。
- 影响：release verifier 必须检查发布图标资产；drag 只修改 staged layout，不改变 node semantic hash、parents、EvidenceRecipe 或 CPT。

## D-088：系统模型支持保持软件打开的主动“保存全部”

- 状态：已接受
- 决策：主窗口工具栏提供“保存全部”，并提供 `Ctrl+S`。操作先 flush 全部浮动节点窗口、参数/CPT 表单、画布 pending layout 与窗口 placement，再检查 software-owned model edit session；dirty 时调用既有 `model.edit.commit` 原子提交，随后重新加载系统任务方案和当前网络图，软件及浮动编辑窗口保持打开。任何成功写入 edit session 的节点、边、CPT、任务方案或布局操作都把状态显示为“有待确认的暂存修改”；commit 完成后显示“已保存到系统模型”。clean 时不产生空提交；提交失败保留暂存内容并允许重试。关闭时原有“保存全部并关闭／放弃全部并关闭／取消”继续作为兜底，主动保存与关闭事务互斥，不能并发提交。
- 理由：专家会长时间连续编辑 Evidence、BN、CPT 与任务方案，不应为了让模型正式落盘而反复关闭软件；复用同一个后端 commit 事务可以增加便利性而不产生第二套保存语义。
- 影响：本决策扩展 D-056/D-057 的提交入口，不恢复业务 Draft/Publish 状态，也不把模型保存到 user project。保存后的模型对该软件副本的全部项目和未来 run 生效；历史 immutable RunSnapshot、result 与 artifact 不受影响。

## D-089：拖拽在按下时锁定目标；五个 Raw Input Family 根保存为任务方案展示布局

- 状态：已接受
- 决策：所有可拖拽图节点使用不随节点移动的 XamlRoot 坐标，并在主键按下时锁定本次拖拽的 projection 对象；正常 release 与 WinUI pointer-cancel 共用一次性完成路径，不能在 `ItemsRepeater` 虚拟化清空绑定后重新取目标。五个绿色 Raw Input Family 根 `raw-family.X/U/I/G/P` 同样可拖动，其坐标作为当前 TaskScheme 的 display-only `layout_overrides` 暂存、保存和复制；它们不是 ModelNode、不能成为 Evidence/BN 父节点，也不进入计算闭包。
- 理由：真实 WinUI 复现证明普通节点的视觉位移会在松手时回弹，因为移动中的元素被当作坐标系且虚拟化会令 release 时的 `Node` 绑定变为 null；五个 family 根原先只是固定 Canvas 展示控件，没有 pointer handler 或后端布局目标。仅保留临时 RenderTransform 不能形成可保存的专家画布。
- 影响：普通节点与绿色 family 根在松手后立即停留于新位置，350 ms debounce 后写入 software-owned edit session，主动“保存全部”后进入 system model；切换/复制任务方案各自保留布局。变更只递增 scheme layout revision，不改变 node semantic hash、EvidenceRecipe、BN/CPT、激活闭包或历史 immutable RunSnapshot。

## D-090：RC.3 用户验收为 `changes-required`；D-088/D-089 进入 RC.4

- 状态：已接受
- 决策：`v0.1.0-rc.3` 的独立用户验收记录为 `changes-required`。其 annotated tag、commit、历史验证记录和候选身份保持不可变；运行中主动“保存全部”、普通节点松手不回弹以及五个绿色 Raw Input Family 根可拖动并持久化统一进入新的 `v0.1.0-rc.4`，且 RC.4 的 `user_acceptance` 从 `pending` 开始。本机 `dist/releases` 仅作为可再生发布缓存，可以按用户要求删除旧二进制产物并只保留最新 RC.4；该清理不得删除或移动历史 Git 标签与审查记录。
- 理由：RC.3 的自动工程 gate 不能替代真实桌面验收。把 tag 后的 D-088/D-089 源码修复混入同名 ZIP 会破坏候选身份和验收对象的一一对应；同时保留多个约 300 MB 的本地旧包没有产品价值，历史身份已经由 Git 和审查记录保存。
- 影响：RC.4 必须重新生成候选文档、manifest、ZIP、checksum、delivery record 与外部验证证据，并实际验证根启动器、Save All、canonical node 和 Raw Input Family layout persistence。RC.1–RC.3 的历史结论仍可追溯，但不再作为当前可交付二进制留在本机 `dist/releases`。

## D-091：Model Studio 工具栏只保留直接动作，并显式本地化 Tooltip

- 状态：已接受
- 决策：Model Studio 折叠式工具栏隐藏祖先级 `KeyboardAccelerator` 的自动 placement，并为新建、详情、启用、停用、删除、复制和粘贴七个保留动作分别绑定与当前界面语言一致的显式 Tooltip。移除反馈不明确的“多选模式”和“清除选择”两个末尾工具栏按钮；复制/粘贴、节点右键菜单的“加入/移出当前选择”以及底层多节点选择能力继续保留。
- 理由：真实 UI 中 Page 级首个快捷键 `Ctrl+C` 被 WinUI 的折叠按钮 Tooltip 机制错误显示在全部工具栏按钮上；末尾两个仅在特定选择状态下产生效果的图标没有清晰反馈，增加了学习成本。复制与粘贴是用户明确要求的核心操作，不能随末尾选择控件一起删除。
- 影响：鼠标悬停只显示实际动作名称，不再把无关按钮描述成 `Ctrl+C`；工具栏更简洁，但不改变 Python 后端、ModelNode/TaskScheme、剪贴板语义、Evidence/BN/CPT 或历史 RunSnapshot。
