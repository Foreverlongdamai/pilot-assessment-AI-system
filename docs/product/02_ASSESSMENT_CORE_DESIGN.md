# Python Assessment Core 设计

**文档状态：** 产品 v0.3 后端总体设计；M4R Evidence 计算基础已实现，M5 shared-versioned model 架构已确认并开始实施，当前完成 Task 1–3 generic identity、public contracts/Schema、typed source provenance 与 M4R migration preflight
**日期：** 2026-07-16
**上位文档：** [产品总览](./01_PRODUCT_OVERVIEW.md)

> **当前权威补充：** Evidence 计算以 canonical `EvidenceRecipe`、typed operator graph 和 generic compiler/executor 为唯一新扩展路线。M5 使用全局 `Concept + immutable Version` 组件库和 exact-pinned `AssessmentSchemeVersion`；data/extraction edge 与 probabilistic BN edge 是不同合同。详见 [M5 Shared Versioned Model Library and Bayesian Workspace Design](./specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) 和 [Expert-Editable Evidence and Assessment Model Design](./specs/2026-07-15-expert-editable-evidence-and-model-design.md)。

## 1. 设计目标

Assessment Core 是 eVTOL 飞行员训练评估系统的唯一计算权威。它必须同时支持：

- 作为纯 Python package 被测试、脚本或 notebook 调用；
- 作为本地 sidecar 被 Windows WinUI 应用启动；
- 加载多模态 session bundle；
- 在不改变原始数据的前提下完成同步、recipe-driven evidence 和 BN inference；
- 通过 model workspace/bundle 驱动 EvidenceRecipe、operator graph、BN 拓扑、状态空间和 CPT；
- 允许专家在 integrated workspace 中编辑 Evidence computation、两类 typed edge、BN state/CPT，并组合 exact component versions；
- 为每次运行生成完整 provenance；
- 在合同不可读取、必需输入缺失、任务不适用、配置/依赖不足或软件失败时返回精确结构化状态；对任何有限但再差的表现仍按冻结规则产生 D/A/U，而不是过滤负面 evidence。

核心计算代码不得依赖具体 UI、窗口生命周期或 WinUI 类型。Runtime adapter 只能调用应用层服务，不能复制业务规则。

## 2. 分层与依赖方向

建议 package 边界如下：

    pilot_assessment/
      contracts/
      ingestion/
      synchronization/
      anchors/
      evidence/
      model_library/
      schemes/
      inference/
      pipeline/
      persistence/
      runtime/
      reporting/

依赖只允许从外层指向内层稳定合同：

`runtime/reporting/persistence → pipeline → inference/evidence/anchors/synchronization/ingestion → contracts`

`model_library` 保存全局 immutable component versions，`schemes` 负责 exact version composition/closure；二者为 evidence 和 inference 提供经过验证的定义，但不得反向依赖 runtime 或 UI。`model_bundle` 只作为导入/导出的可移植封装，不再是唯一编辑身份。

## 3. 模块职责

| 模块 | 负责 | 不负责 |
|---|---|---|
| `contracts` | 稳定领域类型、枚举、协议 DTO 和 schema version | 文件解析、计算和数据库访问 |
| `ingestion` | Session manifest 与各模态格式适配、字段和单位规范化 | 跨设备时间对齐和 anchor |
| `synchronization` | 从 `SynchronizationInput` 生成 native-rate `AlignedSession` 与公共 `SynchronizationReport`；执行 clock mapping、统一 t_ns、session window、phase/event/baseline/reference 对齐 | 修改原始 stream；插值、重采样或建立 anchor-specific analysis/window grid |
| `anchors` | 保留旧 Anchor catalog/plan、15 个 whole-Anchor plugins、typed dependency DAG、measurement 与 artifact/source trace，供历史 revision replay 和迁移参考 | 新 Anchor 的默认扩展、BN posterior、采集质量研究 |
| `evidence` | canonical EvidenceRecipe/OperatorDefinition、动态 catalog、only-technical validator、generic compiler/executor、built-in operators、draft/preview/apply/replay，以及后续 AnchorResult v0.2/scorer 集成 | model-weighted coverage/assessability、原始采集质量研究 |
| `model_library` | Evidence/BN concepts、immutable component versions、lineage、content identity 与查询 | 选择当前任务方案、运行 session |
| `schemes` | TaskProfile/AssessmentScheme draft、exact version composition、reference closure、atomic publish 与 portable bundle import/export | 执行 Evidence 算法或 BN posterior |
| `inference` | BN engine port、具体 engine adapter、posterior 推理 | UI 展示和模型文件直接编辑 |
| `pipeline` | 一次 assessment run 的编排、快照和取消 | 持久化实现细节 |
| `persistence` | project、session import、component/scheme versions、run、audit、result repository | 计算规则 |
| `runtime` | JSON-RPC、sidecar 生命周期、command dispatch、progress | 科研计算逻辑 |
| `reporting` | result DTO、证据链、限制、导出和 provenance | 更改计算结果 |

## 4. 核心领域合同

### 4.1 Session 合同

- `SessionManifest`：session 身份、task profile、stream inventory、时间基准和完整性。
- `StreamDescriptor`：模态、格式、状态、schema、单位、clock 和文件位置。
- `RawStream`：保留 source timestamp 和原始值。
- `SynchronizationInput`：组合同一次 `LoadedManifest`、`PreparedSession` 和 `IngestionReadinessReport` 的内部不可变同步输入；blocked readiness 不能构造该对象。
- `AlignedStreamView`：保留原生 source rows/values、在末尾追加 aligned time/flags 的只读派生视图，schema ID 使用 `*-aligned-v0.1`。
- `AlignedSession`：内部不可变 native-rate aligned streams、session window、annotations、task reference 与同步 fingerprint 的集合。
- `SynchronizationReport`：公共同步报告；与 `IngestionReadinessReport`、`RunPreflightReport` 分离，始终 `formal_run_authorized=false`。
- `PhaseInterval`、`EventMarker`、`BaselineInterval`：任务和生理分析上下文。
- `SessionQualityReport`：M1–M3 的结构、同步、覆盖、gap 和 modality technical diagnostics；它不构成 M4 scorer 的质量门，也不衰减 D/A/U likelihood。

### 4.2 Anchor 与 evidence 合同

- `EvidenceRecipe` 与 `OperatorDefinition`：新路线的 canonical computation definition 和可复用算子合同；详见 §4.3/§5。
- `AnchorCatalog` 与 `EvidenceExecutionPlan`：分别描述可变 profile inventory，以及对同一 snapshot 冻结并通过 recipe/operator DAG/compatibility 校验的可执行计划。
- `AnchorPluginDefinition` 与旧 `AnchorExecutionPlan`：只用于 Task 0–28 legacy revision replay 和迁移比较。
- `AnchorMeasurement`：recipe executor（或 legacy plugin）生成的 raw/primary value、phase/event breakdown、classification override candidate、source windows、typed derived artifacts 与 `ComputationTrace`。
- `AnchorResult` v0.2：中央 scorer 生成的 calculation status、D/A/U likelihood/state、continuous score、受控 `classification_override`、diagnostics、provenance 与 fingerprint；不含 M4 quality gate。
- `AnchorEvaluationReport`：与 catalog 等长的 inventory、`ready/ready_partial/blocked`、raw availability 和 evaluation fingerprint，始终 `formal_run_authorized=false`。
- `EvidenceDefinition`：Desired/Adequate/Unacceptable 的版本化 scorer 规则。D/A/U 是表现状态；missing/config/dependency/error 是互斥计算状态。

### 4.3 Model 与 inference 合同

- `EvidenceRecipe`：一个 Anchor 的 canonical typed computation graph、bindings、outputs、scoring、documentation 与 UI metadata；前端展示和后端执行共用此对象。
- `OperatorDefinition`：可复用算子的 typed ports、unit/cardinality/time semantics、parameter schema、UI metadata 与 implementation identity。
- `EvidenceConcept` / `EvidenceVersion`：稳定 Evidence 语义与其不可变精确 recipe/scorer/source-binding 实现。
- `BnNodeConcept` / `BnNodeVersion`：稳定能力变量语义与其不可变 state/parent/CPD 定义。
- `EvidenceBindingVersion`：把 exact EvidenceVersion 输出映射为 BN observation，并声明概率 parents 与 likelihood/CPT。
- `CptVersion`：锁定 child、ordered parents/states、概率行与 content hash 的不可变定义。
- `TaskProfileVersion`：版本化任务 reference、phase/event/AOI 和适用输入语义。
- `AssessmentSchemeDraft` / `AssessmentSchemeVersion`：前者为可自动保存的组合工作副本，后者为 exact component references 与 content hash 的不可变发布。
- `ExtractionEdgeDefinition`：raw/session/task source 到 Evidence 或 recipe typed ports 的数据依赖；不进入 BN。
- `ProbabilisticEdgeDefinition`：BN child CPD 的 parent relation；进入 DAG/factorization。
- `ModelBundleManifest`：可移植方案包的版本、exact component inventory、operator/engine requirements、兼容性和 checksums；bundle 是 exchange artifact，不替代全局 version identity。
- `InferenceRequest`：run/session snapshot、exact scheme/component versions、Evidence observations 和 query nodes。
- `CompetencyPosterior`：状态概率、assessability、coverage 和限制。

### 4.4 Run 与结果合同

- `AssessmentRun`：run ID、session snapshot、model snapshot、状态、进度和取消标记。
- `AssessmentResult`：posterior、evidence trace、missing report、diagnostics 和 provenance。

## 5. EvidenceRecipe、Operator 与 Legacy AnchorPlugin

新系统中，每个 Anchor 通过 `EvidenceRecipe` 定义，generic executor 组合通用 operators 运行。普通新增/修改 Anchor 不需要 Python plugin。Operator implementation 避免把全部 objective 或 human-factor 算法塞入两个大文件，也避免为每个 Anchor 建一个新模块。

Legacy whole-Anchor plugin 保留以下历史合同，用于旧 revision replay 和 recipe 迁移比较：

    anchor_id
    plugin_version
    supported_task_profiles
    required_modalities
    optional_modalities
    applicable_phases
    upstream_anchor_dependencies
    parameter_schema
    output_schema
    compute(context, parameters, declared_dependencies) -> AnchorMeasurement

### 5.1 Legacy whole-Anchor 插件规则

本节规则只约束当前 legacy/reference `AnchorPlugin` 的重放与迁移。新系统的扩展单元是 `OperatorDefinition`；普通专家编辑保存在 `EvidenceRecipe`，只有现有算子库无法表达全新计算能力时才新增 trusted operator plugin。

1. 同一个 `anchor_id` 在一个 model bundle 中只能绑定一个明确版本。
2. 插件不得读取 UI 状态或运行时可变全局变量。
3. 插件只能读取 plan 声明的 synchronized views、semantic snapshot 和 typed upstream results/artifacts/profiles。
4. 插件必须返回实际 source windows、sample/time trace、参数 hash、typed artifact refs 和 override candidate；technical diagnostics 不得变成 quality score。
5. 真正缺输入/配置/依赖时返回精确结构化状态；miss/no-stable/no-gaze 等已观察失败返回 computed-U override，不以 NaN、Infinity 或异常字符串代替。
6. 派生 anchor 通过依赖 DAG 执行；循环依赖使 model bundle 无效。
7. 算法内部常量必须进入版本化实现或参数 schema，不得散落在代码中。

### 5.2 Starter Anchor catalog

安装包内 `reference-model-v0.1` starter catalog 有 **18 个节点：O1–O13 + H1–H5**。它是可复制、可删除、可替换的示例，不是 generic engine 的 required inventory。图编辑器允许专家在 draft 中自由增删节点；publish 时系统对改动内容创建新的 component versions 和 `AssessmentSchemeVersion`，不要求专家手工提升 major version。

- O2 的正式名称为 **Peak Tracking Excursion**。
- O1 可以输出 Translation、Deceleration、Hover 三个 phase value，但 v0 仍把 O1 作为一个逻辑 BN evidence node；phase 明细保留在 evidence trace 中。
- 如果专家将 O1 拆为多个 BN 节点，binding、recipe output 和 BN graph 必须显式更新；系统在 publish 时自动形成新的 exact component/scheme versions，不得在运行时隐式改变节点数。
- Legacy O8 的 anchor-to-anchor dependency DAG 只用于历史 replay；active M5 `EvidenceVersion` 不能读取另一 Evidence observation。新的 TPX 与 O13 等跨模态计算通过 raw/session/task bindings、operator DAG 和 provenance 闭合的 typed derived artifacts 表达。
- H1–H5 starter recipes 的数据合同来自 gaze/AOI、ECG 和 EEG 等正式模态；当前未导出的 stream 使用 `export_pending`，不是自动删除或停用 recipe。

Anchor 的具体公式、阈值、单位、窗口、聚合和 scorer 由 canonical EvidenceRecipe 定义。代码不能根据显示名称或 Anchor ID 猜测公式。

截至 2026-07-15，M4R 已实现两份跨语言 schema、trusted operator registry、only-technical validator、generic compiler/executor、可复用 signal/event/temporal/gaze/flight/statistics/composition/scoring operators、进程内 draft/preview/apply/replay service，以及 O1–O13/H1–H5 共 18 份 `starter_template` recipe resources。catalog 的实现不固定数量；测试已直接加入并运行任意第 19 个 recipe。O1–O12/H1–H3 的 15 个旧插件继续保留，O13/H4/H5 则直接使用 operator composition，仓库没有为它们伪造旧插件。

这一完成状态只覆盖 M4R 的进程内 Evidence 计算基础。把 recipe output 映射成完整 AnchorResult/report、连接 BN、持久化 project/model workspace、暴露 JSON-RPC sidecar 以及 WinUI 图编辑器分别仍属于后续 M5–M7；`formal_run_authorized` 仍为 false。

M4R 的当前合同与完成门以 [Expert-Editable Evidence and Assessment Model Design](./specs/2026-07-15-expert-editable-evidence-and-model-design.md) 为准。旧 [M4 Anchor Design](./specs/2026-07-13-m4-anchor-evidence-availability-design.md) 只继续描述 Task 0–28 历史实现与迁移输入。

## 6. 端到端计算流程

### 6.1 Import、ingestion readiness 与 run preflight

1. `persistence` 创建 session import record。
2. `ingestion` 读取 manifest 并验证 schema version、路径和 checksum。
3. 各 adapter 验证列、类型、单位、采样率和 stream status。
4. 返回 `IngestionReadinessReport`；它只决定 source artifact 能否进入 synchronization，`formal_run_authorized=false`。
5. 对 non-blocked readiness，用同一次 M1/M2 snapshot 构造 `SynchronizationInput`；M3 按声明的 scale/offset 以 round-half-even 生成 native-rate aligned `t_ns`，建立 session window、time flags、结构化 annotation/reference 结果与 technical diagnostics，不插值或重采样。
6. M3 输出内部 `AlignedSession` 与公共 `SynchronizationReport`；报告只决定是否存在可供下游使用的 aligned snapshot，仍为 `formal_run_authorized=false`，其 residual/coverage diagnostics 不过滤 M4 表现。
7. 锁定 exact `AssessmentSchemeVersion` 与全部 component versions/hashes，解析 model-bundle reference，并把 EvidenceBindings、EvidenceRecipes、operator versions、typed extraction dependencies 与 BN 编译为 executable plan；availability precheck 只检查输入存在、适用性、配置、依赖和 capability，不按表现值或所谓质量判定。
8. M6 的 `run.preflight` 返回独立 `RunPreflightReport`；只有它决定是否可以创建 AssessmentRun。M4 自身始终 `formal_run_authorized=false`。

### 6.2 Run snapshot

启动 run 时固定：

- session manifest 与每个输入文件的 checksum；
- phase/event/baseline annotation revision；
- scheme version、全部 exact component identities 和完整 portable bundle hash（如由 bundle 导入）；
- EvidenceRecipe/operator/BnNode/CPT/EvidenceBinding versions；legacy replay 时另记 AnchorPlugin version；
- Assessment Core、BN engine 和协议版本；
- 运行参数和随机种子（如某适配器确实需要）。

运行过程中即使专家保存或发布了新 component/scheme versions，也不能改变已启动 run 的结果。

### 6.3 计算

1. M4 从同一不可变 snapshot、semantic snapshot、resolved references 和 compiled plan 构建只读 evaluation context。
2. 按 typed recipe/dependency DAG 运行 generic operator executor，生成 `AnchorMeasurement` 与 content-addressed artifacts；只有旧 revision replay 进入 legacy plugin adapter。
3. 中央 scorer 生成 AnchorResult v0.2；`computed + Unacceptable` 与 D/A 一样是有效 evidence，raw availability 为 1。
4. M4 生成 canonical `AnchorEvaluationReport`，保存 source trace、状态、override、artifact 和 fingerprints；不计算 BN 或 competency coverage。
5. M5 按 applied/preview-exact revision 应用 dependence protection，计算 model-weighted coverage/assessability，并加载 graph/CPT。
6. `inference` 对 computed D/A/U evidence 做 posterior inference；非 computed evidence 被 omission/边缘化，missing 不等于 U。
7. 对 `prior_only` 或 `insufficient` competency 禁止 weak-skill diagnosis；fatal error 使用 blocked run 状态且不产生 posterior。
8. M6 的 `reporting`/`persistence` 原子保存结果、完整 provenance 并发出完成 notification。

## 7. Global Model Library、Assessment Scheme 与 Portable Bundle

### 7.1 全局库

全局库保存所有 Evidence/BN concepts 和并行 immutable versions。它不是“当前生效模型”，也不因为新版本出现而自动升级任何方案。每个 version 至少记录 stable ID、concept ID、parent lineage、canonical content、content hash、author/time 和独立的 lifecycle/scientific metadata。

### 7.2 Assessment Scheme

`AssessmentSchemeVersion` 是可运行模型的唯一组合入口，至少锁定：

- exact `TaskProfileVersion`；
- exact `EvidenceVersion` 与 `EvidenceBindingVersion` inventory；
- exact `BnNodeVersion` 与 `CptVersion` inventory；
- output、coverage/reporting policy 与 layout version；
- scheme content hash 和所有 component hashes。

编译器必须验证引用闭包，绝不静默选择同 concept 的 `latest`。Hover/18/11/4 只属于 starter scheme；generic engine 不验证这些固定 ID 或数量。

### 7.3 两类图关系

前端新增、删除或连接节点时必须提交带类型 operation：

- extraction operation 只修改 raw/task source bindings 或 EvidenceRecipe typed operator graph；
- BN operation 只修改 probabilistic random variables、parents、states 与 CPD/CPT；
- Raw Input 不是 BN node；
- 两类 edge 不能互换或共享一个无类型 DTO；
- BN graph 必须为 DAG，所有 endpoint/version 存在；
- child CPT 的 ordered parents 和 state spaces 必须与 graph 一致；
- Evidence observation mapping 必须与 recipe output/BN states 兼容；
- 用户选定的 output nodes 必须形成 executable query；TCP/PC/SM/OC 只对 starter scheme 默认存在。

### 7.4 CPT 与 EvidenceRecipe 参数

CPT 更新必须验证 parent set/order、每个父状态组合、有限非负概率、行归一化和 state IDs。Recipe/operator 参数更新必须通过 `OperatorDefinition`/`EvidenceRecipe` JSON Schema，并重新计算受影响的 extraction dependency range。所有阈值、公式、scorer、state、parent 或 CPT 变化进入 structured diff，并在 publish 时形成新 component version。

### 7.5 Portable Model Bundle

Model bundle 是一个方案及其完整 exact dependency closure 的导入/导出封装，建议包含：

    model_bundle/
      manifest.json
      task_profiles/
      evidence_concepts/
      evidence_versions/
      evidence_bindings/
      bn_node_concepts/
      bn_node_versions/
      cpt_versions/
      assessment_schemes/
      operator_requirements.json
      schemas/
      checksums.sha256

Manifest 记录 bundle/schema 版本、exact component IDs/hashes、operator/BN engine compatibility、software/scientific/permitted-use 独立状态以及 root hash。导入已有 version ID 时内容 hash 必须相同，否则拒绝 ID collision；bundle 不能覆盖本地历史版本。

## 8. Project Draft、Publish 与 Run Lock

M6 将全局库和 project runtime store 持久化；M5 先定义领域语义。Scheme draft 保存 base scheme version、exact reused references、候选 component drafts、operation history、`graph_version` 和独立 `layout_version`。

Draft 内每次编辑采用原子 operation：

1. 客户端提交 `draft_id`、`expected_graph_version` 和明确 operation type。
2. 后端验证 graph version 未变化。
3. 在内存 candidate 上执行 copy-on-write 修改和必要的 CPT migration preview。
4. 执行该 operation 所需的最小 technical validation。
5. 原子保存 canonical draft snapshot、diff、inverse patch 和 audit event。
6. `graph_version` 加一；不创建 published component/scheme version。

只有 apply/publish 才创建不可变版本：后端冻结 candidate，验证 exact reference closure，编译 recipe/BN plan，为改动组件分配新 IDs/hashes，保留未改 exact references，并在单一事务中写入全部新 component versions 与新的 `AssessmentSchemeVersion`。任一写入失败必须整体回滚。Apply 不运行 per-model pytest/golden，也不要求人工审批。

回滚从历史 scheme version 创建新 draft；不得删除或改写历史。Preview 锁定 exact draft snapshot，正式 run 锁定 exact scheme/component versions、hashes、operator/engine identities 和 session snapshot。

## 9. Provenance

每个 AssessmentResult 必须包含：

- session ID、manifest version、stream checksums；
- annotation revision、`source_snapshot_fingerprint`、完整同步 policy、`policy_fingerprint`、`binding_catalog_fingerprint` 和 `synchronization_fingerprint`；
- `SynchronizationReport` hash 与 session-window source；
- model bundle/revision/hash；
- graph 和 CPT hashes；
- anchor catalog、插件和参数 hashes；
- Assessment Core、BN engine、runtime protocol 版本；
- 每个 anchor 的 calculation status、source windows、trace、override、artifact/result fingerprint 和 evidence；
- competency coverage 和 assessability；
- software verification status；
- scientific validation status；
- run start/end、host 与 cancellation/error 状态。

结果导出不得只保留四个分数。

## 10. 错误边界

错误统一为：

    code
    severity
    recoverable
    message
    field_or_path
    node_or_anchor_id
    remediation
    request_id
    trace_id
    diagnostics

| 类别 | 示例 | 行为 |
|---|---|---|
| Session contract | manifest/schema 不兼容、checksum 错误 | 阻止 import 或 run |
| Stream | 列、单位、格式、timestamp 不合法 | 标记具体 stream；按 task requirement 决定 fatal/partial |
| Synchronization | scale/drift 声明冲突、same-clock mapping 冲突、int64 overflow 或 temporal binding/annotation/reference 结构错误 | M3 blocked 或 optional stream invalid；residual 原值进入 technical diagnostics，但不成为 M4 表现过滤门 |
| Evidence | 输入缺失、任务不适用、配置不足、依赖缺失、operator/recipe/产物失败 | 分别返回 `missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`；差表现返回 computed U，不使用笼统 invalid |
| Model | graph cycle、未知 node/operator、port/type/unit 不兼容、CPT 不完整 | candidate draft 标记 invalid/incomplete；仍可保存，但不可 preview 或 apply |
| Inference | engine 不兼容、posterior 失败 | 不返回虚假 competency result |
| Versioning | stale expected graph/base scheme version、写入冲突 | 返回 conflict 和最新 canonical draft/scheme head |
| Runtime | protocol mismatch、sidecar crash | UI 可重连或生成支持包 |

`export_pending` 和合法的 `missing` 是数据状态，不是未捕获异常。

## 11. 并发与一致性边界

产品 v0 采用以下保守规则：

- 一个 WinUI 实例持有一个 sidecar 进程。
- Sidecar 可并发处理只读查询，但每个 project 同时只允许一个 model write transaction。
- Draft write 使用 `expected_graph_version` 的乐观并发控制；创建 draft 和 apply 同时校验 base scheme version ID。
- 一个 sidecar 同时只执行一个资源密集型 assessment pipeline；其他 run 排队。
- Runtime 线程必须继续响应 `run.status` 和 `run.cancel`。
- Run 启动后使用不可变 session/model snapshot；模型编辑不影响进行中的 run。
- M6 可以让同一 frozen session/model snapshot 的重复 run 复用已验证的同步/anchor cache；M4 只提供覆盖所有输入、参数、插件、依赖和产物的 fingerprint/cache-key material，cache lifecycle、命中策略和失效由 M6 管理。
- 结果写入采用临时文件/事务后原子提交；中断 run 不产生 completed result。
- UI 不能直接持有模型文件写锁或数据库连接。

未来可以扩展为多个 worker，但不能改变 run snapshot 和 component/scheme version 不可变原则。

## 12. Runtime command surface

Runtime adapter 的唯一 canonical 方法注册表和 DTO 以 [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) 为准；本节只作后端模块摘要：

- `runtime.hello`、`runtime.status`、`runtime.shutdown`
- `capabilities.list`、`schema.get`
- `project.create`、`project.open`、`project.export`
- `session.inspect`、`session.import`、`session.validate`、`session.get`、`session.artifact.get`
- `component.concept.list/get/create`、`component.version.list/get`
- `scheme.version.list/get/diff`、`scheme.create_from_version`
- `scheme.draft.create/get/discard/apply`
- `evidence.recipe.get/create/clone/update/disable/retire/preview`
- `operator.catalog.list`、`operator.definition.get`、`extension.operator.list/install`
- `graph.snapshot.get`、`graph.operations.preview`、`graph.operations.apply`
- `graph.validate`、`graph.undo`、`graph.redo`
- `layout.update`
- `node.get`、`node.add`、`node.update`、`node.remove`
- `extraction.edge.add/remove`、`extraction.binding.get/update`
- `bn.edge.add/remove`、`bn.binding.get/update`
- `cpt.get`、`cpt.migration.preview`、`cpt.generate`、`cpt.validate`、`cpt.update`
- `run.preflight`、`run.start`、`run.preview`、`run.status`、`run.cancel`
- `result.get`、`result.export`
- `audit.events.list`、`diagnostics.bundle.export`

Draft 修改命令返回新的 `graph_version` 或 structured validation error；只有 apply 返回新 component version IDs 和不可变 `scheme_version_id`。确切 M6 JSON-RPC 命名仍以未来 runtime protocol revision 为准。大型数据只通过受验证的本地路径引用。

## 13. 验证策略

### 13.1 软件验证

- Contracts 与 JSON Schema tests；
- 每种 ingestion adapter 的正常和损坏 fixture；
- 已知 scale/offset 的 synthetic native-rate synchronization tests，包括 Decimal round-half-even、int64 overflow、same-clock、session window、duplicate mapped ns 和 source-row preservation；
- built-in/trusted operators 的 port/type/unit/parameter/time semantics focused tests；
- EvidenceRecipe compile/execute/trace/error-localization tests，以及代表性 computation/scorer checks；
- recipe/operator DAG 与 fingerprint/cache-key material tests；真正的 cache lifecycle/hit/invalidation tests 属于 M6；
- 一个轻量可编辑 vertical slice：创建“扰动期间目标 AOI 关注”Anchor、修改参数、preview 变化、apply/replay；
- missing/config/dependency/not-applicable 状态矩阵，证明 missing 不等于 Unacceptable；
- catalog 扩展、clone/disable/retire、参数修改、operator extension 与旧 recipe/scheme deterministic replay tests；
- graph、state 和 CPT 完整性 tests；
- 小型可手算 BN posterior tests；
- missing evidence 和 prior-only tests；
- exact version pinning、copy-on-write component/scheme publish、冲突、原子保存和回滚 tests；
- Python sidecar 与 .NET client 的协议 contract tests；
- M4R 使用极小的规范化 event/gaze binding 验证 editable recipe 的 draft→preview→apply→replay；完整 M1→M3 aligned session→M4 result/provenance 编排留给 M6 run orchestration，不为每个专家 recipe 创建独立 golden，也不生成重型 fixture。

### 13.2 科学验证

- 多 pilot、多 session 和任务条件；
- 与专家评分、TLX、HQR 或批准的外部标准比较；
- posterior calibration、敏感性、重复性和跨 session 稳定性；
- 缺失模态、同步误差、采样率和噪声 ablation；
- anchor 阈值和 CPT 的专家审查记录；
- 明确 AssessmentSchemeVersion 的适用范围和不适用范围。

科学验证结论属于具体 component/scheme versions，而不是 Python package 或全局 concept 的属性。
