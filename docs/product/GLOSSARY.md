# 术语表

| 术语 | 定义 |
|---|---|
| Assessment Core | 执行 session 载入、同步、anchor 计算、evidence 转换、BN 推理和结果构建的 Python 核心。 |
| Anchor / Evidence anchor | 从原始或派生数据计算的可解释指标，例如 O2 Peak Tracking Excursion。 |
| Starter template | 随产品提供、用于演示和起步的 Anchor/EvidenceRecipe/BN；可复制、修改、停用、删除或替换，不表示科学正确，也不限制通用引擎的节点数量。 |
| EvidenceConcept | 一类可观测 Evidence 的稳定语义身份，例如“轨迹偏差”；不包含某个任务的精确算法。 |
| EvidenceVersion | 某个 EvidenceConcept 的不可变精确实现；锁定 EvidenceRecipe、参数、scorer、source bindings、lineage 和 content hash。Hover 与直线保持可并列选择同一 concept 的不同 versions。 |
| BnNodeConcept | 一类潜在或聚合能力随机变量的稳定语义身份。 |
| BnNodeVersion | 某个 BnNodeConcept 的不可变精确定义；锁定 state space、probabilistic parents、CPD/CPT reference、lineage 和 content hash。 |
| EvidenceBindingVersion | 把一个 exact EvidenceVersion 输出映射为 BN observation 的不可变定义；包含 observation state mapping、probabilistic parents 和 CPD/likelihood table。 |
| CptVersion | 一个 child 在有序 probabilistic parents/states 条件下的不可变概率定义。 |
| TaskProfileVersion | 某类任务的不可变上下文定义；声明期望轨迹/包线、phase/event/AOI 语义和适用输入，不直接等同于评估方案。 |
| AssessmentSchemeVersion | 一套可运行评估方案的不可变发布；选择 exact TaskProfile、Evidence、binding、BN node、CPT、输出和 policy versions，并记录 content hash。 |
| Global component library | 保存全局 Evidence/BN concepts 及全部并行 immutable versions 的组件库；只有被某个 AssessmentSchemeVersion 引用的版本才参与该方案。 |
| Exact version pinning | 方案和 run 显式保存 component version ID 与 content hash，而不使用会随时间变化的 `latest`。 |
| Copy-on-write publication | 从任意历史方案编辑时复用未改版本，只为改动部分创建新 component versions，并原子发布新的 scheme version；旧版本永不覆盖。 |
| Expert-led model design / backend canonical state | Evidence、算法、参数、BN topology/state/CPT 的内容由专家通过前端决定；后端保存同一 canonical object、签发版本、执行最小技术校验并保证运行一致性。“canonical”不表示后端拥有科学内容决定权。 |
| EvidenceRecipe | 前端显示、后端保存和运行时执行某个 Anchor 计算方法的唯一 canonical object；包含 bindings、typed operator graph、outputs、scoring、documentation 与 UI metadata。 |
| EvidenceRecipe catalog | 运行时大小可变的 recipe inventory；安装包当前提供 O1–O13/H1–H5 共 18 个 starter templates，但 catalog 和 executor 不把 18 写成上限。 |
| Recipe draft | 可自动保存的 EvidenceRecipe 工作副本；允许 graph 暂时 incomplete，只有 preview/apply 要求达到相应技术可执行状态。 |
| Recipe preview | 对 exact draft snapshot 和显式 inputs 的临时执行；返回 outputs、scoring、selected node trace 或定位到 node/operator 的 technical diagnostics，不创建 applied revision。 |
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
| Evidence node | 高层工作区中表示可从 session 提取并可被 BN 观察的变量；组合 EvidenceVersion 与 EvidenceBindingVersion。Starter 参考模型有 18 个，但引擎数量不受限。 |
| BN node | BN 中的 latent/derived random variable，例如 sub-skill 或 aggregate competency；其版本定义 states、probabilistic parents 和 CPD/CPT。 |
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
| Run preflight | `run.preflight` 在 aligned session、annotation/reference、exact `AssessmentSchemeVersion` 及其 pinned component IDs/content hashes 上执行的正式运行门；输出 `RunPreflightReport` 并决定能否创建 AssessmentRun。它不同于 M2 ingestion readiness。 |
| BN | Bayesian Network，贝叶斯网络。 |
| CPD | Conditional Probability Distribution，BN child 在给定 probabilistic parents 下的条件分布；有限离散模型通常物化为 CPT。 |
| CPT | Conditional Probability Table，节点在给定 parent state 下的条件概率表。 |
| Generative starter direction | Hover starter 的 canonical BN 方向 `Competency -> Sub-skill -> Evidence`；它定义概率分解，不等于运行时先计算 competency。 |
| Posterior inference | Evidence 被观察后，由完整 BN joint distribution 计算 `P(Sub-skill/Competency | observations)`；信息可逆于部分 canonical arrows 传播。 |
| Virtual evidence | M5 用显式、版本化 soft scorer 或 dependence-strength mixing 表达的 likelihood observation；不得因所谓原始数据质量向均匀分布收缩。 |
| Model bundle | 一个 AssessmentSchemeVersion 及其 exact dependency closure 的可移植导入/导出包；它不是全局组件库，也不是可原地修改的唯一模型身份。 |
| Autosaved draft | 专家正在编辑的模型工作副本；每个用户意图自动保存，允许 incomplete/invalid，并支持 undo/redo 和 preview。 |
| Draft | `Autosaved draft` 的简称；尚未成为后续新 run 的默认模型。 |
| Applied revision | M4R/旧文档的不可变模型术语；M5 后具体化为 copy-on-write 发布的 component versions 与 `AssessmentSchemeVersion`，不表示科学审批或 Python 软件发布。 |
| Scheme draft | 从 starter 或任意 AssessmentSchemeVersion 创建的可自动保存工作副本；允许 incomplete，通过 copy-on-write 形成候选 component versions。 |
| Applied recipe revision | M4R 对单个 EvidenceRecipe 保存的不可变 snapshot、content hash、parent/diff、作者、时间与可选 note；M5 将它保留为 EvidenceVersion migration lineage，不把它冒充 `AssessmentSchemeVersion`。 |
| Published revision | 旧文档/UI 术语；在当前产品中统一解释为 `Applied revision`，不得附加人工审批、golden 或 per-edit test 语义。 |
| Technical validation | 只检查 schema、引用、DAG、operator/type/unit/parameter、formula/scorer 与 BN CPT 是否可执行；不判断算法、Anchor mapping 或 CPT 是否科学合理。 |
| graph_version | 草稿内整个 semantic model（node、edge、state、CPT、binding、anchor parameters、profile）每次原子修改后递增的乐观并发版本。 |
| layout_version | 仅版本化节点位置等显示布局；变化不影响 graph_version 或 scientific model hash。 |
| draft_validation_state | `draft_incomplete`、`draft_invalid` 或 `draft_executable`，表示草稿技术完整性与可运行性；任何状态都可 autosave。 |
| revision_lifecycle | `applied`、`archived` 或 `superseded`，表示不可变 model revision 的生命周期。 |
| observation_mode | M5 的 hard、virtual 或 omitted 绑定方式，表示某条 AnchorResult 如何进入 BN；M4 不按技术诊断把 computed evidence 改为 omitted。 |
| ready / ready_partial / blocked (M4) | `ready` 表示所有适用 anchor 均 computed；`ready_partial` 表示 inventory 完整但有 missing/config/dependency/error；`blocked` 只表示有效 request 之后的 plan/registry/DAG/global inventory/atomic commit 失败。pre-request rejection 不生成 M4 disposition/report。 |
| plugin_unavailable / not_implemented / not_attempted | 旧 M4 whole-Anchor plugin capability/plan/report inventory 状态，不是 AnchorResult calculation status。M4R 对新 recipe 使用 `operator_unavailable`；两者都不得伪造 session result。 |
| DerivedArtifactSink | M4 通过依赖注入写入 typed、content-addressed 临时派生产物的 port；M6 才拥有正式 managed artifact root 和持久化生命周期。 |
| revision_id | M4R/legacy 中标识不可变 recipe/model revision 的稳定 ID；M5 新合同分别使用 component version ID 与 scheme version ID。 |
| Sidecar | 由 Windows 前端启动和管理的本地 Python 后端进程。 |
| JSON-RPC / JSONL | 每行一个 JSON-RPC 2.0 消息的 stdio 进程协议。 |
| TPX | O8 使用的 task performance composite。M4R `starter.o8` 从 O1/O5 score 组合的 recipe 只作 legacy migration/replay；M5 active starter 使用同一 concept 下从 raw/session/task sources 计算的并行 compliant version。两者不要求 provisional 数值等价。 |
| Engineering verified / Software verified | 某个明确里程碑的软件按其设计合同执行，并通过该里程碑规定的 fresh tests、static/schema/build/package gates；它是里程碑范围内的工程结论，不表示完整产品、后续里程碑或科学有效性已经完成。 |
| formal_run_authorized | 是否允许创建正式 AssessmentRun 的显式状态。M1–M5 的 ingestion、alignment、Evidence、scheme preview 和 inference 工程通过都不能自动把它设为 true；durable run preflight/lifecycle 属于 M6，当前始终为 false。 |
| Scientifically validated | 评估指标、阈值、CPT 和输出经过足够样本、专家标注及统计研究证明有效。 |
