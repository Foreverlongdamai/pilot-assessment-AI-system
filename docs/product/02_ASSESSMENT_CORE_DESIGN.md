# Python Assessment Core 设计

**文档状态：** 产品 v0 后端设计基线
**日期：** 2026-07-13
**上位文档：** [产品总览](./01_PRODUCT_OVERVIEW.md)

## 1. 设计目标

Assessment Core 是 eVTOL 飞行员训练评估系统的唯一计算权威。它必须同时支持：

- 作为纯 Python package 被测试、脚本或 notebook 调用；
- 作为本地 sidecar 被 Windows WinUI 应用启动；
- 加载多模态 session bundle；
- 在不改变原始数据的前提下完成同步、anchor、evidence 和 BN inference；
- 通过 model bundle 驱动 anchor、图拓扑、状态空间和 CPT；
- 允许专家从前端编辑图拓扑、CPT 和 anchor 参数；
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
      model_bundle/
      inference/
      pipeline/
      persistence/
      runtime/
      reporting/

依赖只允许从外层指向内层稳定合同：

`runtime/reporting/persistence → pipeline → inference/evidence/anchors/synchronization/ingestion → contracts`

`model_bundle` 为 anchors、evidence 和 inference 提供经过验证的模型定义，但不得反向依赖 runtime 或 UI。

## 3. 模块职责

| 模块 | 负责 | 不负责 |
|---|---|---|
| `contracts` | 稳定领域类型、枚举、协议 DTO 和 schema version | 文件解析、计算和数据库访问 |
| `ingestion` | Session manifest 与各模态格式适配、字段和单位规范化 | 跨设备时间对齐和 anchor |
| `synchronization` | 从 `SynchronizationInput` 生成 native-rate `AlignedSession` 与公共 `SynchronizationReport`；执行 clock mapping、统一 t_ns、session window、phase/event/baseline/reference 对齐 | 修改原始 stream；插值、重采样或建立 anchor-specific analysis/window grid |
| `anchors` | Anchor catalog/plan、插件注册、typed dependency DAG、确定性 measurement、artifact/source trace | BN posterior、采集质量研究 |
| `evidence` | 中央版本化 scorer、AnchorResult v0.2 和 raw evidence availability | 原始信号处理、model-weighted coverage/assessability |
| `model_bundle` | 模型加载、schema、graph/CPT/参数验证、revision 和 hash | 运行 session |
| `inference` | BN engine port、具体 engine adapter、posterior 推理 | UI 展示和模型文件直接编辑 |
| `pipeline` | 一次 assessment run 的编排、快照和取消 | 持久化实现细节 |
| `persistence` | project、session import、model revision、run、audit、result repository | 计算规则 |
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

- `AnchorPluginDefinition`：ID、版本、算法插件、单位、声明的输入/typed dependencies、适用 task/phase、measurement/artifact schema 和参数 schema。
- `AnchorCatalog` 与 `AnchorExecutionPlan`：分别描述 profile inventory，以及对同一 snapshot 冻结并通过 DAG/compatibility 校验的可执行计划。
- `AnchorMeasurement`：插件生成的 raw/primary value、phase/event breakdown、classification override candidate、source windows、typed derived artifacts 与 `ComputationTrace`。
- `AnchorResult` v0.2：中央 scorer 生成的 calculation status、D/A/U likelihood/state、continuous score、受控 `classification_override`、diagnostics、provenance 与 fingerprint；不含 M4 quality gate。
- `AnchorEvaluationReport`：与 catalog 等长的 inventory、`ready/ready_partial/blocked`、raw availability 和 evaluation fingerprint，始终 `formal_run_authorized=false`。
- `EvidenceDefinition`：Desired/Adequate/Unacceptable 的版本化 scorer 规则。D/A/U 是表现状态；missing/config/dependency/error 是互斥计算状态。

### 4.3 Model 与 inference 合同

- `ModelBundleManifest`：bundle 版本、anchor catalog、兼容性、draft/lifecycle/verification/scientific/permitted-use 独立状态字段和 hash。
- `GraphDefinition`：节点、边、层级、状态空间和显示元数据。
- `CptDefinition`：节点、父节点顺序、父状态组合和概率行。
- `ModelRevision`：不可变 revision、parent、diff、审计信息和 validation report。
- `InferenceRequest`：run snapshot、每 anchor 单一聚合 evidence、phase/event breakdown metadata 和固定 published revision。
- `CompetencyPosterior`：状态概率、assessability、coverage 和限制。

### 4.4 Run 与结果合同

- `AssessmentRun`：run ID、session snapshot、model snapshot、状态、进度和取消标记。
- `AssessmentResult`：posterior、evidence trace、missing report、diagnostics 和 provenance。

## 5. AnchorPlugin 设计

每个 anchor 通过插件实现，避免将全部 objective 或 human-factor 算法塞入两个大文件。

插件必须声明：

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

### 5.1 插件规则

1. 同一个 `anchor_id` 在一个 model bundle 中只能绑定一个明确版本。
2. 插件不得读取 UI 状态或运行时可变全局变量。
3. 插件只能读取 plan 声明的 synchronized views、semantic snapshot 和 typed upstream results/artifacts/profiles。
4. 插件必须返回实际 source windows、sample/time trace、参数 hash、typed artifact refs 和 override candidate；technical diagnostics 不得变成 quality score。
5. 真正缺输入/配置/依赖时返回精确结构化状态；miss/no-stable/no-gaze 等已观察失败返回 computed-U override，不以 NaN、Infinity 或异常字符串代替。
6. 派生 anchor 通过依赖 DAG 执行；循环依赖使 model bundle 无效。
7. 算法内部常量必须进入版本化实现或参数 schema，不得散落在代码中。

### 5.2 最新 anchor catalog

安装包内 reference-model-v0.1 的默认/required evidence catalog 为 **18 个节点：O1–O13 + H1–H5**。图编辑器允许在 draft 中增删节点；若改变 reference profile 的 required IDs 或语义，发布时必须使用新的 model_profile_id，并按兼容性规则提升 major model version。

- O2 的正式名称为 **Peak Tracking Excursion**。
- O1 可以输出 Translation、Deceleration、Hover 三个 phase value，但 v0 仍把 O1 作为一个逻辑 BN evidence node；phase 明细保留在 evidence trace 中。
- 如果未来要将 O1 拆为多个 BN 节点，必须发布新的 model bundle major/minor revision，不得在运行时隐式改变节点数。
- O8、O13 等依赖其他 anchor 或跨模态窗口的计算由依赖 DAG 明确表达。
- H1–H5 的数据合同来自 gaze/AOI、ECG 和 EEG 等正式模态；当前未导出的 stream 使用 `export_pending`，不是删除插件。

Anchor 的具体公式、阈值和单位由 model bundle 与插件版本共同定义。代码不能根据显示名称猜测公式。

M4 的完整合同、18-anchor 算法和完成门以 [M4 Anchor Calculation and Evidence Availability Design](./specs/2026-07-13-m4-anchor-evidence-availability-design.md) 为准。引擎 cardinality 可变；只有 `reference-model-v0.1` profile 精确为 18 个。

## 6. 端到端计算流程

### 6.1 Import、ingestion readiness 与 run preflight

1. `persistence` 创建 session import record。
2. `ingestion` 读取 manifest 并验证 schema version、路径和 checksum。
3. 各 adapter 验证列、类型、单位、采样率和 stream status。
4. 返回 `IngestionReadinessReport`；它只决定 source artifact 能否进入 synchronization，`formal_run_authorized=false`。
5. 对 non-blocked readiness，用同一次 M1/M2 snapshot 构造 `SynchronizationInput`；M3 按声明的 scale/offset 以 round-half-even 生成 native-rate aligned `t_ns`，建立 session window、time flags、结构化 annotation/reference 结果与 technical diagnostics，不插值或重采样。
6. M3 输出内部 `AlignedSession` 与公共 `SynchronizationReport`；报告只决定是否存在可供下游使用的 aligned snapshot，仍为 `formal_run_authorized=false`，其 residual/coverage diagnostics 不过滤 M4 表现。
7. 锁定 model revision，解析 model-bundle reference，并把 AnchorBinding、catalog、plugin、参数和 typed dependencies 编译为 `AnchorExecutionPlan`；availability precheck 只检查输入存在、适用性、配置、依赖和 capability，不按表现值或所谓质量判定。
8. M6 的 `run.preflight` 返回独立 `RunPreflightReport`；只有它决定是否可以创建 AssessmentRun。M4 自身始终 `formal_run_authorized=false`。

### 6.2 Run snapshot

启动 run 时固定：

- session manifest 与每个输入文件的 checksum；
- phase/event/baseline annotation revision；
- model revision 和完整 bundle hash；
- AnchorPlugin 版本；
- Assessment Core、BN engine 和协议版本；
- 运行参数和随机种子（如某适配器确实需要）。

运行过程中即使专家保存了新 model revision，也不能改变已启动 run 的结果。

### 6.3 计算

1. M4 从同一不可变 snapshot、semantic snapshot、resolved references 和 compiled plan 构建只读 evaluation context。
2. 按 typed dependency DAG 运行插件，先生成 `AnchorMeasurement` 与 content-addressed artifacts。
3. 中央 scorer 生成 AnchorResult v0.2；`computed + Unacceptable` 与 D/A 一样是有效 evidence，raw availability 为 1。
4. M4 生成 canonical `AnchorEvaluationReport`，保存 source trace、状态、override、artifact 和 fingerprints；不计算 BN 或 competency coverage。
5. M5 按 published/preview-exact revision 应用 dependence protection，计算 model-weighted coverage/assessability，并加载 graph/CPT。
6. `inference` 对 computed D/A/U evidence 做 posterior inference；非 computed evidence 被 omission/边缘化，missing 不等于 U。
7. 对 `prior_only` 或 `insufficient` competency 禁止 weak-skill diagnosis；fatal error 使用 blocked run 状态且不产生 posterior。
8. M6 的 `reporting`/`persistence` 原子保存结果、完整 provenance 并发出完成 notification。

## 7. Model Bundle

建议默认模型目录：

    model_bundle/
      manifest.json
      anchor_catalog.yaml
      tasks/
        hover_deceleration.yaml
      anchor_parameters/
        O1.yaml
        ...
        H5.yaml
      bn/
        graph.yaml
        cpts/
          <node-id>.json
      competencies.yaml
      schemas/
      validation/

### 7.1 Bundle manifest

至少记录：

- `bundle_id`、`bundle_version` 和 `schema_version`；
- `model_profile_id`、active anchor catalog ID、catalog cardinality 和 canonical hash；只有 `reference-model-v0.1` 额外验证 exact O1–O13/H1–H5 共 18 项；
- task profile IDs；
- 插件与 BN engine compatibility；
- draft_validation_state（只在 draft manifest 中）或 revision_lifecycle（只在 published manifest 中）；
- software_verification_status、scientific_validation_status 与 permitted_use，三个字段相互独立；
- author、reviewer、created_at 和 change summary；
- 各文件 checksum 和 bundle root hash。

### 7.2 图拓扑编辑

前端允许新增、删除或连接节点，但保存前必须由后端验证：

- node ID 唯一；
- 所有 edge endpoint 存在；
- graph 为 DAG；
- evidence node 引用有效 anchor ID；
- latent node 有明确状态空间；
- CPT 父节点顺序与 graph 一致；
- 删除或重连节点后不存在孤立、悬空或不兼容 CPT；
- 四个 competency output 仍满足 bundle 声明的完整性约束。

拓扑修改只作用于 draft 并增加 graph_version；通过 publish 后才生成新 revision，且永不修改运行中的 revision。

### 7.3 CPT 与 anchor 参数

CPT 更新必须验证：

- parent set 和固定排序；
- 每个父状态组合都有且只有一行；
- probability 为有限非负数；
- 每行概率和在允许容差内等于 1；
- state IDs 与 graph 定义一致。

Anchor 参数更新必须通过插件的 JSON Schema，并重新计算受影响节点的依赖范围。阈值和公式参数变更应在 revision diff 中单独标识。

## 8. Project 运行时副本与 revision

安装默认 bundle 只读。Project 创建时，将选定 bundle 复制到类似以下位置：

`%LOCALAPPDATA%/CranfieldPilotAssessment/projects/<project-id>/models/<revision-id>/`

可编辑工作副本位于独立 draft 区：

`%LOCALAPPDATA%/CranfieldPilotAssessment/projects/<project-id>/drafts/<draft-id>/`

Draft 内每次编辑采用原子 operation：

1. 客户端提交 `draft_id` 和 `expected_graph_version`。
2. 后端验证 graph_version 未变化。
3. 在内存 candidate 上应用 graph/CPT/anchor parameter 修改和必要迁移。
4. 执行该操作所需的 model validation。
5. 原子写入 draft snapshot、diff、inverse patch 和 audit event。
6. graph_version 加一；不产生 published revision。

只有 publish 才创建不可变 revision：后端再次检查 expected_graph_version，执行完整 validation 与 inference smoke test，生成 content hash，将 candidate 原子写入新的 `models/<revision-id>/`，再更新 project head。

Revision 至少包含 parent ID、author/role、timestamp、reason、structured diff、validation report 和 content hash。回滚必须从历史 revision 创建新 draft，验证后发布新的 revision；不得静默把 project head 直接改回历史版本，也不删除任何历史内容。

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
| Anchor | 输入缺失、任务不适用、配置不足、依赖缺失、插件/产物失败 | 分别返回 `missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`；差表现返回 computed U，不使用笼统 invalid |
| Model | graph cycle、未知 node、CPT 不完整 | candidate draft 标记 invalid/incomplete，不可 preview 或 publish |
| Inference | engine 不兼容、posterior 失败 | 不返回虚假 competency result |
| Revision | stale expected revision、写入冲突 | 返回 conflict 和最新 head |
| Runtime | protocol mismatch、sidecar crash | UI 可重连或生成支持包 |

`export_pending` 和合法的 `missing` 是数据状态，不是未捕获异常。

## 11. 并发与一致性边界

产品 v0 采用以下保守规则：

- 一个 WinUI 实例持有一个 sidecar 进程。
- Sidecar 可并发处理只读查询，但每个 project 同时只允许一个 model write transaction。
- Draft write 使用 `expected_graph_version` 的乐观并发控制；创建 draft 和 publish 同时校验 base revision_id。
- 一个 sidecar 同时只执行一个资源密集型 assessment pipeline；其他 run 排队。
- Runtime 线程必须继续响应 `run.status` 和 `run.cancel`。
- Run 启动后使用不可变 session/model snapshot；模型编辑不影响进行中的 run。
- M6 可以让同一 frozen session/model snapshot 的重复 run 复用已验证的同步/anchor cache；M4 只提供覆盖所有输入、参数、插件、依赖和产物的 fingerprint/cache-key material，cache lifecycle、命中策略和失效由 M6 管理。
- 结果写入采用临时文件/事务后原子提交；中断 run 不产生 completed result。
- UI 不能直接持有模型文件写锁或数据库连接。

未来可以扩展为多个 worker，但不能改变 run snapshot 和 revision 不可变原则。

## 12. Runtime command surface

Runtime adapter 的唯一 canonical 方法注册表和 DTO 以 [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) 为准；本节只作后端模块摘要：

- `runtime.hello`、`runtime.status`、`runtime.shutdown`
- `capabilities.list`、`schema.get`
- `project.create`、`project.open`、`project.export`
- `session.inspect`、`session.import`、`session.validate`、`session.get`、`session.artifact.get`
- `model.revision.list`、`model.revision.get`、`model.revision.diff`
- `model.draft.create`、`model.draft.get`、`model.draft.discard`、`model.draft.publish`、`model.draft.smoke_test`
- `graph.snapshot.get`、`graph.operations.preview`、`graph.operations.apply`
- `graph.validate`、`graph.undo`、`graph.redo`
- `layout.update`
- `node.get`、`node.add`、`node.update`、`node.remove`
- `edge.add`、`edge.remove`
- `binding.get`
- `cpt.get`、`cpt.migration.preview`、`cpt.generate`、`cpt.validate`、`cpt.update`
- `anchor.parameters.get`、`anchor.parameters.validate`、`anchor.parameters.update`
- `plugin.list`、`plugin.install`（受信管理员权限）
- `run.preflight`、`run.start`、`run.preview`、`run.status`、`run.cancel`
- `result.get`、`result.export`
- `audit.events.list`、`diagnostics.bundle.export`

Draft 修改命令返回新的 `graph_version` 或 structured validation error；只有 publish 返回新的不可变 `revision_id`。大型数据只通过受验证的本地路径引用。

## 13. 验证策略

### 13.1 软件验证

- Contracts 与 JSON Schema tests；
- 每种 ingestion adapter 的正常和损坏 fixture；
- 已知 scale/offset 的 synthetic native-rate synchronization tests，包括 Decimal round-half-even、int64 overflow、same-clock、session window、duplicate mapped ns 和 source-row preservation；
- M4 对每个 AnchorPlugin 的 interpolation/resampling、analysis/window grid 与 sampling-rate invariance tests；
- 每个 AnchorPlugin 的手算 D/A/U、精确边界、aggregation 和 classification-override golden tests；
- 插件依赖 DAG 与 M4 fingerprint/cache-key material tests；真正的 cache lifecycle/hit/invalidation tests 属于 M6；
- 18/18 computed Desired 与 18/18 computed Unacceptable 两套完整 workflow；后者 raw availability 必须为 100%，且 M4 不得生成 `invalid_quality`；
- missing/config/dependency/not-applicable 状态矩阵，证明 missing 不等于 Unacceptable；
- catalog 扩展、retire、参数 snapshot、plugin version 与旧 revision deterministic replay tests；
- graph、state 和 CPT 完整性 tests；
- 小型可手算 BN posterior tests；
- missing evidence 和 prior-only tests；
- model revision、冲突、原子保存和回滚 tests；
- Python sidecar 与 .NET client 的协议 contract tests；
- golden session bundle 的端到端 result/provenance tests。

### 13.2 科学验证

- 多 pilot、多 session 和任务条件；
- 与专家评分、TLX、HQR 或批准的外部标准比较；
- posterior calibration、敏感性、重复性和跨 session 稳定性；
- 缺失模态、同步误差、采样率和噪声 ablation；
- anchor 阈值和 CPT 的专家审查记录；
- 明确 model revision 的适用范围和不适用范围。

科学验证结论属于 model bundle，而不是 Python package 的全局属性。
