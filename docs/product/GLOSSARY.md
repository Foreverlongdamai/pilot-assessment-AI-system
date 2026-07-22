# 术语表

| 术语 | 定义 |
|---|---|
| Assessment Core | 执行 session 载入、同步、anchor 计算、evidence 转换、BN 推理和结果构建的 Python 核心。 |
| Anchor / Evidence anchor | 从原始或派生数据计算的可解释指标，例如 O2 Peak Tracking Excursion。 |
| Starter template | 随产品提供、用于演示和起步的 Anchor/EvidenceRecipe/BN；可复制、修改、停用、删除或替换，不表示科学正确，也不限制通用引擎的节点数量。 |
| ModelNode | M7 画布上的完整独立节点；一个 `node_id` 只有一个当前功能定义，包含固定 parents 与 EvidenceRecipe/参数/评分或 BN states/CPT。任务需要不同定义时复制或新建另一个节点。 |
| TaskScheme | 并列、自动保存、可直接运行的任务方案；保存 explicit active nodes、computed parent closure、outputs、task bindings 和 layout，不覆盖节点内部定义。 |
| Explicit active selection | 专家在某个 TaskScheme 中主动启用的节点集合。 |
| Computed active closure | 从 explicit selection 沿每个节点的 fixed data/probabilistic parents 递归补齐的实际执行节点集合。 |
| Global node library | 单个解压软件副本的 `system/model-library.sqlite3` 中保存全部 Raw Input、Evidence 与 BN ModelNodes 的全局库；不属于任一 project，节点可被零个、一个或多个 TaskSchemes 共享。 |
| Node copy | 深复制所选节点自身的 recipe/parameters/states/CPT/metadata，创建新 `node_id`，但继续引用原 fixed parents，不复制 parent branch。 |
| RunSnapshot | `run.start` 时自动冻结的不可变计算快照；包含 exact managed session、TaskScheme closure、完整节点定义、edges、recipes/operators、CPT、runtime parameters 与 hashes。历史结果只依赖该快照。 |
| Current-system capture | D-077 的发布过程：builder 从显式选择、已保存、已关闭且无 user-owned rows 的 `system/` 一致复制 canonical model，记录动态 identity/counts；不得在失败时回退 starter seed。它不是用户备份功能。 |
| Project portability | 软件完全关闭后复制完整 project 根目录，并在目标位置通过“打开项目”重新使用；依赖 project-relative managed paths，不使用专用 backup/restore archive。 |
| Change journal | Current node/scheme 每次 autosave 的 append-only operation/history；用于 optimistic concurrency、undo/redo、audit 和恢复，不是任务侧可选择的业务版本。 |
| EvidenceConcept | M5 legacy/replay 术语：一类可观测 Evidence 的稳定语义身份。M7 正常 UI 不用同 concept 多版本来表达不同任务节点。 |
| EvidenceVersion | M5 legacy/replay 术语：某 EvidenceConcept 的不可变实现。M7 若任务定义不同，迁移为不同 ModelNode；历史 version 继续供旧 run replay。 |
| BnNodeConcept | M5 legacy/replay 术语：一类潜在或聚合能力随机变量的稳定语义身份。 |
| BnNodeVersion | M5 legacy/replay 术语：某 BnNodeConcept 的不可变精确定义。M7 current node 直接拥有 states、parents 和 CPT。 |
| EvidenceBindingVersion | M5 legacy/replay 术语：把 exact EvidenceVersion 输出映射为 BN observation 的不可变定义。M7 将 observation mapping 与 probabilistic parents/CPT 纳入完整 Evidence node。 |
| CptVersion | M5 legacy/replay 术语：一个不可变 CPT record。M7 current child node 直接拥有当前 CPT，并在 RunSnapshot 中冻结。 |
| TaskProfileVersion | M5 legacy/replay 术语：某类任务的不可变上下文定义。M7 TaskScheme 仍可绑定 typed reference/phase/event/AOI resources，但正常 UI 不要求 version picker。 |
| AssessmentSchemeVersion | M5/M6 legacy/replay 术语：一套不可变发布方案。M7 正常 UI 使用 current TaskScheme + automatic RunSnapshot。 |
| Global component library | M5 legacy/replay 的 immutable concepts/versions 库；M7 当前产品表面改为 Global node library。 |
| Exact version pinning | M5/M6 方案锁定 component version 的旧实现；M7 的可重放边界改为 run-start exact RunSnapshot。 |
| Copy-on-write publication | M5/M6 历史编辑/发布机制；M7 正常 UI 已取消 Apply/Publish，但旧 records 继续可回放。 |
| Expert-led model design / backend canonical state | Evidence、算法、参数、BN topology/state/CPT 的内容由专家通过前端决定；后端保存并执行同一 canonical objects、执行最小技术校验并保证持久化/运行一致性。“canonical”不表示后端拥有科学内容决定权。 |
| EvidenceRecipe | 前端显示、后端保存和运行时执行某个 Anchor 计算方法的唯一 canonical object；包含 bindings、typed operator graph、outputs、scoring、documentation 与 UI metadata。 |
| EvidenceRecipe catalog | 运行时大小可变的 recipe inventory；安装包当前提供 O1–O13/H1–H5 共 18 个 starter templates，但 catalog 和 executor 不把 18 写成上限。 |
| Recipe draft | M4R/M5 legacy 术语。M7 直接编辑 current Evidence node；允许暂时 incomplete，并通过 change journal 与 RunSnapshot 保留历史。 |
| Recipe preview | 对 current Evidence node 的 exact revision 和显式 inputs 做临时执行；返回 outputs、scoring、trace 或定位到 node/operator 的 technical diagnostics，不要求 publish。 |
| Evidence Computation Graph | EvidenceRecipe 内把 session stream/semantic/reference 通过可复用算子转换成 AnchorMeasurement/AnchorResult 的有向无环图。 |
| Operator / OperatorDefinition | 可复用计算积木及其机器合同；声明 typed input/output ports、unit/cardinality/time semantics、parameter schema、UI metadata 和 implementation identity，不等于一个完整 Anchor。 |
| Trusted operator plugin | 当现有 operator library 无法表达一种全新计算能力时，由开发者安装的受控扩展；它提供可复用 operators，不要求每个新 Anchor 都发布 Python plugin。 |
| AnchorPlugin | Task 0–28 已实现的 legacy whole-Anchor 插件合同；用于旧 revision replay、迁移比较和参考实现。新 Anchor 的默认扩展方式已改为 EvidenceRecipe + operators。 |
| AnchorCatalog | 某 model profile 的版本化 anchor inventory、definition、lifecycle 与 canonical order；generic M4 engine 不固定其数量。 |
| AnchorLifecycle | 旧 Anchor catalog definition 的 `active/deprecated/retired` 状态；legacy M4 可执行 plan 只允许 `active` entry。editable EvidenceRecipe 另用 `active/disabled/retired` 的 RecipeLifecycle。 |
| AnchorExecutionPlan | M5 根据 exact model/session snapshot 编译、M4 消费的冻结计划；锁定 plugin、参数、core-stream input-table contracts、typed dependencies、grid/window、scorer 和 artifact recipe。 |
| ResolvedInputTableContract | M5 从锁定 core-stream profile 编译进 execution plan 的表合同；分别冻结 stream-level/table-role-level aligned schema、坐标系与有序 field name/dtype/unit/nullability。合法 optional non-aligned stream 下沉为 `missing_input`，aligned stream 的合同错配在 request 前拒绝。 |
| ReferenceBindingError | Task 3 在 reference snapshot/candidate 三参数绑定阶段使用的稳定错误；发生时尚无 `ResolvedReferenceSet` 或 M4 request。 |
| AnchorRequestValidationError | Task 4/13 在 binder 成功后对 session/semantic/reference provenance/fingerprint 闭合失败使用的稳定错误；不生成 M4 report。 |
| AnchorMeasurement | recipe executor（或 legacy AnchorPlugin）在中央 scorer 之前产生的 raw metrics、phase/event breakdown、override candidate、typed artifacts 与 computation trace。 |
| AnchorResult v0.2 | M4 的 per-anchor 结果合同（`anchor-result-0.2.0`）；记录 calculation status、raw metrics、D/A/U likelihood、override、artifact、diagnostics、provenance 和 fingerprint。 |
| ComputationTrace | M4 保存的 sample/time range、grid/window、匹配方法和 technical diagnostics；只用于审计，不生成 quality score 或改变 likelihood。 |
| Raw Input node | 高层工作区中表示 X/U/I/G/P、具体物理 stream 或 task source 的数据节点；用于 Evidence extraction，不是 BN random variable，也没有 CPT。 |
| Evidence node | 可从 Raw Input 提取并被 BN 观察的完整 ModelNode；原子包含 source bindings、EvidenceRecipe、parameters/scorer、observation states、probabilistic parents 和 CPT/CPD。Starter 有 18 个，但引擎数量不受限。 |
| BN node | BN 中的 latent/derived random variable，例如 sub-skill 或 aggregate competency；完整节点直接定义 states、fixed probabilistic parents 和 CPD/CPT。 |
| Data / extraction edge | 从 raw/session/task source 到 Evidence 的数据依赖，或 EvidenceRecipe 内 typed operator ports；不进入 BN factorization，也不等于 BN parent。高层不使用 Evidence→Evidence extraction edge。 |
| Source provenance closure | 对 Evidence extraction source 递归证明其最终来自 raw stream、session semantic 或 task semantic 的技术闭包。另一 Evidence 的 score/state/likelihood 属于 `evidence_observation`，不能通过改名冒充 raw/derived source。 |
| Probabilistic BN edge | 从 parent random variable 到 child random variable 的概率边，表示 child CPD 的条件变量并进入 BN joint factorization。 |
| BN parent | 出现在 `P(child | parents)` 中的概率父随机变量；不得用来指 EvidenceRecipe 的 raw source binding。 |
| Inference flow / overlay | 观测 Evidence 后对 sub-skill/competency posterior 的信息影响方向；前端可只读显示 `Evidence ⇢ ability`，但它不是可保存的 BN edge。 |
| Sub-skill | 不可直接观测的中间技能节点。参考模型有 11 个。 |
| Aggregate competency | 顶层能力节点：TCP、PC、SM、OC。 |
| TCP | Task Control Proficiency，任务控制熟练度。 |
| PC | Procedural Compliance，程序遵循。 |
| SM | Situational Monitoring，态势监控。 |
| OC | Operational Composure，运行镇定/稳定性。 |
| X(t) | 随时间变化的飞行器状态和运动学/动力学数据。 |
| U(t) | 随时间变化的驾驶员控制输入。 |
| I(t) | 飞行员在 VR 中随头部姿态变化而实际看到的第一视角视觉场景。 |
| G(t) | 与 I(t) 对齐的 gaze ray/point、fixation/stare、AOI、有效性和置信度。 |
| P(t) | 生理信号族；v0.1 至少包括 EEG 与 ECG，可扩展其他经批准的生理模态。 |
| Pilot camera | 可选的驾驶员脸部/身体画面流；不是 H1–H3 计算 gaze-on-scene 的必要条件。 |
| AOI | Area of Interest，场景中的关注区域；可以随 VR 画面和头部姿态动态变化。 |
| Phase | Translation、Deceleration、Hover 等任务阶段。 |
| Event | 扰动、提示、包线越界等带时间标记的离散事件。 |
| Desired / D | 参考模型中的期望表现 evidence state。 |
| Adequate / A | 参考模型中的可接受表现 evidence state。 |
| Unacceptable / U | 参考模型中的不可接受表现 evidence state；它是有效负面观测，`computed + U` 的 raw availability 为 1。 |
| computed | M4 已执行公式并产生 D/A/U likelihood；D、A、U 都表示 evidence 已存在。 |
| missing_input | M4 公式必需的模态或字段完全不存在，因此没有 D/A/U observation。 |
| missing | 本应存在但文件或字段缺失；不是表现等级。 |
| export_pending | 已知已采集但尚未导出到 session bundle；不是表现等级。 |
| invalid | M1–M3 的上游 stream 状态：数据存在，但接口、schema、类型、完整性或时间合同不成立；不是 M4 calculation status，也不是表现等级。 |
| not_applicable | 当前任务／阶段没有该 anchor 的适用条件，例如没有扰动事件；M4 不生成 D/A/U observation，且该项不进入适用 evidence 的 coverage 分母。 |
| not_computable | 输入存在且任务适用，但 reference、AOI、calibration 或公式必需参数未定义，M4 不能执行公式。 |
| dependency_missing | M4 的已声明上游没有产生 required computed result 或 artifact，因此当前 anchor 没有 observation。 |
| extractor_error | M4 plugin 异常、输出违约或 artifact 发布失败；这是软件错误，不是飞行表现等级。 |
| invalid_quality | 仅供 legacy AnchorResult v0.1 reader 识别的旧状态；reference M4 和 AnchorResult v0.2 永不生成。 |
| Quality / technical diagnostics | M1–M3 可记录 coverage、gap、clock residual、validity 和 artifact 等技术诊断；这些字段只用于排查与 provenance，不控制 M4 evidence admission、D/A/U 或 likelihood。 |
| Raw availability | 对单个适用 anchor，`calculation_status=computed` 时为 1，否则为 0；`computed + Unacceptable` 同样为 1。 |
| Model-used availability coverage | M5 对当前模型实际采用的适用 evidence 做 relation-weighted coverage；computed D/A/U 均贡献 1，但用户显式排除的 observation 对 model coverage 贡献 0，且不改写 M4 raw availability。 |
| Coverage / evidence availability coverage | 本次评估成功产生并被当前模型使用的适用 evidence 相对于模型期望适用 evidence 的覆盖程度；它表示 evidence 是否存在/使用，不表示表现好坏。 |
| classification_override | AnchorResult v0.2 的一等字段；当 missed response、no stable hover、no gaze 或退化生理计算无法用有限主值表达时，明确把结果分类为 U，并记录原因，禁止用 Infinity/NaN。 |
| Poor performance is not invalid data | 轨迹偏差大、控制剧烈、生理数值极端、未响应、未注视或未稳定悬停属于可评价表现，通常必须输出 `computed + Unacceptable`，不能被标为 invalid、missing 或 `invalid_quality`。 |
| Native-rate alignment | M3 保留每个 source artifact 的原生采样行和值，只追加统一 session time 与 window flags 的对齐方式；不插值、不重采样，也不建立 anchor-specific analysis/window grid。 |
| Clock mapping | 把 source seconds 映射到 session `t_ns` 的确定性规则：`round_half_even(source_s × scale × 1e9 + offset_ns)`；scale 是唯一计算权威，drift_ppm 只作一致性审计。 |
| Session window | v0.1 的闭区间 `[0,max(mapped X primary t_ns)]`，source 为 `master-clock-x-mapped-coverage-v1`；X 只提供技术时间边界，不代表 commanded trajectory、任务标准或能力 ground truth。 |
| Ingestion readiness inspection | M2 对 source artifact 内容、schema、完整性、技术诊断和 adapter 可用性的只读检查；输出 `IngestionReadinessReport`，只允许进入 M3，且永不授权正式 run。它不评价 M4 evidence 好坏。 |
| SynchronizationInput | M3 内部不可变输入，组合同一次 `LoadedManifest`、`PreparedSession` 和 `IngestionReadinessReport`；blocked readiness 不构造该对象。 |
| AlignedStreamView | M3 内部只读视图；保留 raw columns、rows 和 values，并按显式 temporal binding 在末尾追加 authoritative int64 `t_ns`/interval ns 与 Boolean window flags；schema ID 使用 `*-aligned-v0.1`。 |
| AlignedSession | M3 内部不可变结果，包含 native-rate aligned streams、session window、aligned annotations、bundle task reference 和同步 fingerprints；不作为公共 JSON-RPC 大数据 DTO。 |
| Compact workflow fixture | M4 默认验证使用的紧凑 raw/aligned input：per-anchor micro fixture 或 all-Desired/all-Unacceptable/mixed real-plugin scenario。它可以覆盖 exact-18 inventory，但不要求每个场景都生成 physical Session Bundle。 |
| Lightweight physical workflow smoke | 唯一的 10 秒全模态 synthetic Session Bundle；通过公开入口验证 M1→M4、source immutability、determinism 与 isolated-wheel packaging，不承担 18 个 anchor 的全部精确阈值 oracle。 |
| Release-scale / performance fixture | 未来可选的长 session、full-rate、吞吐/内存/soak 测试资产；不属于 M4 Task 0、默认 pytest、isolated-wheel smoke 或 engineering-verification 必要门槛。 |
| Answer leakage / 答案回灌 | 把 expected AnchorResult、state、likelihood、预计算 composite 或 production output 写入测试 input recipe，使测试只证明 builder/oracle 自洽而没有证明 raw/aligned data 驱动 evidence；D-027 明确禁止。 |
| SynchronizationReport | M3 公共同步报告，记录七个 core modality、task reference、annotation、clock/coverage/window diagnostics 与 source/policy/catalog/alignment fingerprints；证明结构／时间合同并提供 non-gating diagnostics，始终 `formal_run_authorized=false`。 |
| Run preflight | `run.preflight` 在 managed session、annotation/reference、current TaskScheme exact revision、active closure 与完整 node definitions 上执行技术运行检查；通过后 `run.start` 自动冻结 RunSnapshot。它不同于 M2 ingestion readiness，也不是 publish/scientific approval。 |
| BN | Bayesian Network，贝叶斯网络。 |
| CPD | Conditional Probability Distribution，BN child 在给定 probabilistic parents 下的条件分布；有限离散模型通常物化为 CPT。 |
| CPT | Conditional Probability Table，节点在给定 parent state 下的条件概率表。 |
| Generative starter direction | Hover starter 的 canonical BN 方向 `Competency -> Sub-skill -> Evidence`；它定义概率分解，不等于运行时先计算 competency。 |
| Posterior inference | Evidence 被观察后，由完整 BN joint distribution 计算 `P(Sub-skill/Competency | observations)`；信息可逆于部分 canonical arrows 传播。 |
| Virtual evidence | M5 用显式、版本化 soft scorer 或 dependence-strength mixing 表达的 likelihood observation；不得因所谓原始数据质量向均匀分布收缩。 |
| Model bundle | 历史/导入导出格式：一个可重放模型及 dependency closure。M7 最终可移植格式应保存完整 ModelNodes、TaskSchemes 与兼容 identities，不等于应用安装包。 |
| Model edit session | D-056/D-067 的软件副本 `system/` 级技术事务工作区：一次应用会话内的节点、边、CPT、任务方案和布局修改先持久写入独立 SQLite；它不是可切换、可发布的业务版本，也不属于当前 user project。 |
| Staged change / 暂存修改 | 已由 Python backend 接收、校验并持久保存在 model edit session 中，但尚未通过“保存全部”写入 canonical workspace 的修改。 |
| Save all / 保存全部 | 在主工具栏点击“保存全部”、按 `Ctrl+S`，或关闭时选择“保存全部并关闭”，把 edit session 相对基线的最终差异在一个 canonical transaction 中提交；同一对象的多次会话内修改折叠为一次最终 revision 变化。主动保存不会关闭软件。 |
| Discard all / 放弃全部 | 丢弃当前 edit session，使 canonical workspace 保持不变；不同于删除节点或回滚历史 RunSnapshot。 |
| Five-layer canvas | D-057 的理解型投影：`Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency`；它不改变底层三类 canonical 节点、两类 edge 或 BN 生成方向。 |
| Semantic display name | D-058 的普通界面英文名称：优先读取 canonical English name；缺失时从 typed source、EvidenceRecipe anchor、BN reporting metadata/role 或 task binding 确定性推导。不得使用随机 ID/hash 或“未命名”占位符。 |
| Technical identity | `node_id`、`scheme_id`、run/result/artifact ID、revision 与 hash 等精确身份；继续用于持久化、协议、复现和诊断，但普通工作界面不把它当作对象名称。 |
| Autosaved draft | M4R/M5 legacy UI 术语。M7 没有 Draft/Published 业务双态；D-056/D-088 的 model edit session 是一项可主动保存、并在关闭时兜底保存/放弃的技术事务。 |
| Draft | 历史 UI 术语；不得用于 M7 正常任务侧栏。 |
| Applied revision | M4R/M5 历史术语；M7 不要求 apply，历史不可变运行由 RunSnapshot 保证。 |
| Scheme draft | M5/M6 历史术语；M7 使用 current TaskScheme。 |
| Applied recipe revision | M4R 对单个 EvidenceRecipe 保存的不可变 snapshot、content hash、parent/diff、作者、时间与可选 note；M5 将它保留为 EvidenceVersion migration lineage，不把它冒充 `AssessmentSchemeVersion`。 |
| Published revision | 旧文档/UI 术语；M7 正常 UI 不显示、不要求，也不得附加人工审批、golden 或 per-edit test 语义。 |
| Technical validation | 只检查 schema、引用、DAG、operator/type/unit/parameter、formula/scorer 与 BN CPT 是否可执行；不判断算法、Anchor mapping 或 CPT 是否科学合理。 |
| semantic_revision | Edit session 内每次原子草稿操作可递增其工作 revision；Save all 时同一 canonical ModelNode/TaskScheme 的最终语义差异只递增一次正式 revision。它不是任务可选版本。 |
| layout_revision | 节点位置、缩放、分组等显示布局的乐观 revision；变化不改变 computation hash。 |
| technical_status | Current node/scheme 的 `complete`、`configuration_incomplete` 或 stable technical error 状态；任何状态都可暂存并保存，只有 clean canonical workspace 中技术可执行的方案可 run。 |
| revision_lifecycle | M4R/M5 legacy immutable record 的生命周期；M7 current node 通常使用 active/archived，历史 run 由 RunSnapshot 保持。 |
| observation_mode | M5 的 hard、virtual 或 omitted 绑定方式，表示某条 AnchorResult 如何进入 BN；M4 不按技术诊断把 computed evidence 改为 omitted。 |
| ready / ready_partial / blocked (M4) | `ready` 表示所有适用 anchor 均 computed；`ready_partial` 表示 inventory 完整但有 missing/config/dependency/error；`blocked` 只表示有效 request 之后的 plan/registry/DAG/global inventory/atomic commit 失败。pre-request rejection 不生成 M4 disposition/report。 |
| plugin_unavailable / not_implemented / not_attempted | 旧 M4 whole-Anchor plugin capability/plan/report inventory 状态，不是 AnchorResult calculation status。M4R 对新 recipe 使用 `operator_unavailable`；两者都不得伪造 session result。 |
| DerivedArtifactSink | M4 通过依赖注入写入 typed、content-addressed 派生产物的 port；M6 已提供正式 managed artifact root、staging/promotion/reference 与持久化生命周期。 |
| revision_id | M4R/legacy 中标识不可变 recipe/model revision 的稳定 ID；M5 新合同分别使用 component version ID 与 scheme version ID。 |
| Sidecar | 由 Windows 前端启动和管理的本地 Python 后端进程。 |
| JSON-RPC / JSONL | 每行一个 JSON-RPC 2.0 消息的 stdio 进程协议。 |
| Simulator raw session source | 模拟器直接导出的只读目录，最小只需 `streams/` 与 `annotations/`；它不是 canonical Bundle，导入时由系统在受管 staging 中物化。 |
| Canonical Session Bundle | 含 manifest、七类 modality descriptors、annotation/reference、checksum 与时间合同的项目内部／标准交换单元。raw source 导入后和原生标准 Bundle 都收敛到这一合同。 |
| Undeclared unit pass-through | D-061 的单位处理：source/profile 未声明单位时保持 null/空 object，不询问、不猜测、不换算，原始数值按固定 adapter/Evidence 方法运行，并记录 `unit_handling=undeclared-pass-through-v1`。 |
| TPX | O8 使用的 task performance composite。M4R `starter.o8` 从 O1/O5 score 组合的 recipe 只作 legacy migration/replay；M5 active starter 使用同一 concept 下从 raw/session/task sources 计算的并行 compliant version。两者不要求 provisional 数值等价。 |
| Engineering verified / Software verified | 某个明确里程碑的软件按其设计合同执行，并通过该里程碑规定的 fresh tests、static/schema/build/package gates；它是里程碑范围内的工程结论，不表示完整产品、后续里程碑或科学有效性已经完成。 |
| Release candidate | 带明确 prerelease 标签、源码提交、system identity、文档、checksum、SBOM、限制和验证证据的可验收交付物。candidate 不等于最终版本；`v0.1.0-rc.1` 与 `v0.1.0-rc.2` 均已被用户标记为 `changes-required`，不得改写，当前修订进入 `v0.1.0-rc.3`。 |
| user_acceptance | 用户对一个精确候选进行独立实际操作后的产品验收状态，至少区分 `pending`、`accepted` 与 `changes-required`。构建机自动验证通过时仍保持 `pending`；一个候选的结果不能自动继承给后续候选。 |
| formal_run_authorized | 精确 session/model/reporting policy 是否已经获得正式科学评估授权的 provenance 状态，不是技术执行开关。M1–M5 的工程通过不能自动把它设为 true。按 D-085，`software_test` 与 `assessment` 在 technical disposition ready 时都可运行；Assessment 未获授权时必须显示 `run.assessment_not_authorized` warning，在 run 关联的 frozen preflight provenance 中保持 false，并继续把结果标为 engineering-only。 |
| Scientifically validated | 评估指标、阈值、CPT 和输出经过足够样本、专家标注及统计研究证明有效。 |
