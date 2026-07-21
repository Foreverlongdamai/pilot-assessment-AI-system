# M6 Local Runtime, Durable Persistence and Sidecar Implementation Plan

> 状态：Completed / engineering verified（2026-07-16）
> 执行方式：INLINE，严格按任务顺序推进；不启用 subagent
> 工程方式：平台不变量采用轻量 test-first；文件工作流、starter 组装和纵向闭环采用 focused smoke
> 权威规格：[M6 Local Runtime, Durable Persistence and Sidecar Protocol Design](../specs/2026-07-16-m6-local-runtime-persistence-and-protocol-design.md)
> 决策基线：[D-041–D-046](../DECISIONS.md)

## 1. 目标

M6 把 M5 已验证的进程内专家模型工作区变成可供未来 Windows 前端长期使用的本地后端运行时。完成后，系统能够：

1. 创建、关闭、移动并重新打开自包含 project；
2. 把外部 Session Bundle 按原始 bytes 复制到受管项目存储；
3. 持久保存全局 Evidence/BN 组件库、方案草稿、undo/redo 和原子发布状态；
4. 锁定 exact session、scheme、component、operator 和 runtime 身份并运行评估；
5. 把 EvidenceRecipe 结果映射为 BN observations，持久保存 posterior、trace 和结果；
6. 通过本地 stdio JSON-RPC sidecar 暴露 M7 所需的项目、模型、编辑和运行能力；
7. 在进程重启、请求重试和异常退出后维持可解释、可恢复的状态。

本计划验证平台是否忠实保存和执行专家提交的模型，不验证 starter Evidence、阈值、CPT、Hover 拓扑或能力结论的科学有效性。

## 2. 范围约束

- 不实现 WinUI、installer、自动更新、备份 UI、云同步或最终发布包；
- 不引入 ORM、网络端口、任意 Python/eval 编辑器或 RPC 传入的模块路径；
- 不把 Hover、18 个 Evidence、11 个子技能或 4 个聚合能力写成通用引擎上限；
- 不按轨迹差、控制剧烈、生理数值异常或 coverage 低过滤合法 Evidence；
- 不生成四套万行数据，不为 starter 算法建立 scientific golden；
- 每项平台测试使用临时目录、小型 DTO 或现有 micro bundle；每个任务只运行相关测试；
- M6 收尾时才运行一次 M4R/M5 回归、一次完整测试和一次构建门。

## 3. 固定模块布局

| 路径 | 职责 |
|---|---|
| `src/pilot_assessment/contracts/project.py` | project、session revision、artifact、transaction 与 audit DTO |
| `src/pilot_assessment/contracts/run.py` | preflight、snapshot、run、event、result 与状态 DTO |
| `src/pilot_assessment/persistence/database.py` | SQLite connection、transaction 与 canonical JSON primitives |
| `src/pilot_assessment/persistence/migrations.py` | 显式 schema migration registry 与 v1 DDL |
| `src/pilot_assessment/persistence/project.py` | project create/open/close/recovery |
| `src/pilot_assessment/persistence/model_repository.py` | M5 `ComponentLibraryRepository` durable adapter |
| `src/pilot_assessment/persistence/draft_repository.py` | M5 draft repository 与 `WorkspaceUnitOfWork` durable adapter |
| `src/pilot_assessment/persistence/transactions.py` | mutation idempotency 与 canonical receipt |
| `src/pilot_assessment/persistence/audit.py` | append-only audit event repository |
| `src/pilot_assessment/persistence/artifacts.py` | content-addressed managed artifact store |
| `src/pilot_assessment/persistence/sessions.py` | external inspect 与 managed Session Bundle import |
| `src/pilot_assessment/runtime/application.py` | project-scoped service composition 与 starter seed |
| `src/pilot_assessment/runtime/repository.py` | run、event、snapshot 和 result persistence |
| `src/pilot_assessment/runtime/preflight.py` | exact technical preflight 与 frozen execution plan |
| `src/pilot_assessment/runtime/sources.py` | stable source-provider registry 与 per-run source resolution |
| `src/pilot_assessment/runtime/pipeline.py` | ingestion → synchronization → Evidence → Observation → BN |
| `src/pilot_assessment/runtime/coordinator.py` | single-worker run queue、progress、cancel 和 recovery |
| `src/pilot_assessment/sidecar/framing.py` | JSONL framing、4 MiB limit 与 stdout serializer |
| `src/pilot_assessment/sidecar/dispatcher.py` | JSON-RPC validation、dispatch、hello gate 与 error mapping |
| `src/pilot_assessment/sidecar/methods.py` | protocol method 到 application/domain service 的薄适配 |
| `src/pilot_assessment/sidecar/server.py` | stdio server loop、notifications、stderr logging 与 shutdown |

## 4. 实施纪律

每个 test-first 任务使用以下顺序：

1. 只添加能表达一个平台不变量的最小测试；
2. 运行该测试并观察预期失败；
3. 添加使该测试通过的最小 production implementation；
4. 运行本任务 focused tests；
5. 执行 `ruff check` 和 `ruff format --check` 于本任务涉及的文件；
6. 独立提交，不在同一提交混入下一个任务。

文件复制、sidecar 子进程和完整 pipeline 先实现最小路径，再运行 focused smoke。若 smoke 暴露平台缺陷，先补一个最小 failing regression 再修复。所有命令从仓库根目录执行，统一使用：

```powershell
& .\.tools\uv\uv.exe run pytest <focused-path> -q
& .\.tools\uv\uv.exe run ruff check <changed-paths>
& .\.tools\uv\uv.exe run ruff format --check <changed-paths>
```

## 5. 任务分解

### Task 1：冻结 M6 contracts 并发布双目录 JSON Schema

**Files**

- Create: `src/pilot_assessment/contracts/project.py`
- Create: `src/pilot_assessment/contracts/run.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `tests/contracts/test_project_contracts.py`
- Create: `tests/contracts/test_run_contracts.py`
- Modify: `tests/schemas/test_schema_export.py`
- Generate: `schemas/*-0.1.0.schema.json`
- Generate: `src/pilot_assessment/schema_resources/*-0.1.0.schema.json`

**RED**

先测试 strict/frozen、稳定 ID、SHA-256、UTC aware 时间、枚举状态、跨字段约束和 schema 文件名。运行：

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_project_contracts.py tests/contracts/test_run_contracts.py tests/schemas/test_schema_export.py -q
```

预期首先因 M6 contract modules/models 尚不存在而失败。

**GREEN**

实现 `ProjectDescriptor`、`SessionRecord`、`SessionRevision`、`ManagedArtifact`、`ArtifactReference`、`TransactionReceipt`、`AuditEvent`、`RunPreflightReport`、`RunSnapshot`、`AssessmentRun`、`RunEvent` 和 `RunResultEnvelope`。所有 DTO 继承 `StrictContractModel`，使用现有 `StableId`、`Sha256Digest` 和受约束 JSON 类型；所有运行状态转换仍由 service/repository 控制，不在 DTO 中隐藏 I/O。

把 M6 models 加入 `_M6_SCHEMA_MODELS`，并保持根 `schemas/` 与 package resources byte-identical。运行 schema exporter 后再执行 focused tests。

**Commit**

```text
feat: add M6 project and run contracts
```

### Task 2：建立自包含 project 与 SQLite v1 foundation

**Files**

- Create: `src/pilot_assessment/persistence/__init__.py`
- Create: `src/pilot_assessment/persistence/database.py`
- Create: `src/pilot_assessment/persistence/migrations.py`
- Create: `src/pilot_assessment/persistence/project.py`
- Create: `tests/persistence/test_project_database.py`
- Create: `tests/persistence/test_project_lifecycle.py`

**RED**

测试 create/open/close、固定目录、`foreign_keys=ON`、WAL、`synchronous=FULL`、显式 migration、嵌套事务拒绝、项目移动后 reopen，以及数据库业务字段中不出现项目绝对路径。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_project_database.py tests/persistence/test_project_lifecycle.py -q
```

**GREEN**

实现 `ProjectDatabase.connect()`、`transaction(immediate=True)`、canonical JSON bytes 编解码、migration registry 和 `ProjectStore.create/open/close`。`project.json` 仅含 locator 字段；业务路径使用 POSIX project-relative form。`project.open` 在开放业务 capability 前执行 integrity、foreign key、migration、path containment 和 unfinished run recovery hooks。

**Commit**

```text
feat: add portable project database foundation
```

### Task 3：实现 durable component library adapter

**Files**

- Create: `src/pilot_assessment/persistence/model_repository.py`
- Create: `tests/persistence/test_model_repository.py`

**RED**

复用 M5 contracts 构造极小 concept/version 样本，测试 `add/get_exact/get_record/list_records/set_lifecycle/get_lineage`、immutable duplicate rejection、content-hash revalidation、稳定排序和 close/reopen exact equality。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_model_repository.py -q
```

**GREEN**

实现现有 `ComponentLibraryRepository` protocol，不修改 M5 service。canonical model JSON 存为 bytes；kind、record ID、concept ID、lifecycle、created time 和 tags 独立索引。读取时按 kind 路由到已冻结 Pydantic model 并重算 content hash；不增加 `get_latest`。

**Commit**

```text
feat: persist exact model library records
```

### Task 4：实现 durable draft history 与 atomic workspace publication

**Files**

- Create: `src/pilot_assessment/persistence/draft_repository.py`
- Create: `tests/persistence/test_draft_repository.py`
- Create: `tests/persistence/test_workspace_unit_of_work.py`

**RED**

测试 create/save/undo/redo、branch 后截断 redo、graph/layout optimistic conflicts、重启后 cursor 和 snapshots 保留，以及 publication 中途失败时 component/scheme/draft 均无半状态。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_draft_repository.py tests/persistence/test_workspace_unit_of_work.py -q
```

**GREEN**

实现现有 `SchemeDraftRepository` 和 `WorkspaceUnitOfWork` protocols。每次 save 在一个 `BEGIN IMMEDIATE` 中写 canonical draft snapshot、transition 和 cursor；publish 在同一 SQLite transaction 中写 changed immutable versions、scheme、rebased draft 和重置后的 history。保持 M5 `SchemeWorkspaceService` 不感知 SQLite。

**Commit**

```text
feat: persist drafts and atomic scheme publication
```

### Task 5：实现 mutation idempotency 与 append-only audit

**Files**

- Create: `src/pilot_assessment/persistence/transactions.py`
- Create: `src/pilot_assessment/persistence/audit.py`
- Create: `tests/persistence/test_transactions.py`
- Create: `tests/persistence/test_audit.py`

**RED**

测试 canonical method+params request hash、首次执行、相同 transaction replay、不同 payload 复用同一 ID 时拒绝、失败事务不伪造 completed receipt，以及 audit 的稳定分页顺序和 reopen。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_transactions.py tests/persistence/test_audit.py -q
```

**GREEN**

实现 `IdempotencyStore.execute(transaction_id, method, params, mutation)` 和 `AuditRepository.append/list_events`。mutation 与 receipt/audit 使用调用方提供的同一数据库 transaction；缓存 response 使用 canonical JSON bytes。JSON-RPC request ID 不进入业务 identity。

**Commit**

```text
feat: add durable idempotency and audit log
```

### Task 6：实现 content-addressed managed artifact store

**Files**

- Create: `src/pilot_assessment/persistence/artifacts.py`
- Create: `tests/persistence/test_artifact_store.py`

**RED**

测试 staging write、SHA-256/size、atomic promotion、相同 bytes dedup、owner reference、通过 references 推导使用状态、篡改检测、无正式引用的 staging/final orphan recovery 和 path containment。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_artifact_store.py -q
```

**GREEN**

实现 `ManagedArtifactStore.put_bytes/put_file/open_verified/add_reference/remove_reference/recover`。正式路径只由 digest 推导；数据库只写 project-relative path。文件 promotion 和数据库引用遵循 prepared intent，使异常后能确定性清理或重试。

**Commit**

```text
feat: add managed content-addressed artifacts
```

### Task 7：实现 external inspect 与 managed Session Bundle import

**Files**

- Create: `src/pilot_assessment/persistence/sessions.py`
- Create: `tests/persistence/test_session_import.py`

**RED**

使用现有 micro bundle 测试：inspect 不写数据库；import 重新检查源、拒绝 traversal/reparse-style escape、复制原 bytes、逐文件复核 SHA-256、计算 stable inventory/root hashes、创建 exact revision、幂等重试，以及删除外部源后 managed copy 仍可读取。

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_session_import.py -q
```

**GREEN**

实现 `SessionImportService.inspect/import_bundle/get/list`。inspect 调现有 M1/M2 只读 API；import 使用 `staging/imports/<transaction-id>`，复制完成后重新加载 manifest/readiness，再 promote 到 `sessions/<session>/<revision>/bundle` 并在一个 DB transaction 中写 revision、file inventory、receipt 和 audit。旧 revision 永不覆盖。

**Commit**

```text
feat: import session bundles into managed storage
```

### Task 8：组装 project application 并幂等 seed Hover starter

**Files**

- Create: `src/pilot_assessment/runtime/__init__.py`
- Create: `src/pilot_assessment/runtime/application.py`
- Create: `tests/runtime/test_application.py`

**Smoke**

创建 project，组装 durable repositories、M5 services、operator registry、source catalog 和 session/artifact services；调用初始化两次后 starter package 每个 exact record 仍只有一份。关闭、移动并 reopen 后旧 draft 和旧 scheme 仍可 exact 读取。

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_application.py -q
```

**Implementation**

`ProjectApplication.open/create` 是 sidecar 唯一 composition root。它调用 `load_hover_starter_package()` 并以 stable seed marker 在新 project 中恰好写入一次；starter 只是可修改基础内容，不成为 runtime 特判。业务 service 依赖 repository protocols，不依赖 sidecar。

**Commit**

```text
feat: compose durable project application services
```

### Task 9：实现 run repository、exact snapshot 与 technical preflight

**Files**

- Create: `src/pilot_assessment/runtime/repository.py`
- Create: `src/pilot_assessment/runtime/preflight.py`
- Create: `tests/runtime/test_run_repository.py`
- Create: `tests/runtime/test_preflight.py`

**RED**

测试合法状态转换、terminal immutable、monotonic event sequence、snapshot hash 不含绝对路径/hostname/PID、managed session root 复核、scheme pin/source/operator/BN closure、purpose policy，以及差表现数值不造成 technical block。

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_run_repository.py tests/runtime/test_preflight.py -q
```

**GREEN**

实现 `RunRepository` 与 `RunPreflightService.prepare(...)`。preflight 从 exact session revision 和 exact published scheme 动态构造 frozen execution plan；锁定 component/content hashes、operator definitions、source descriptors、engine/runtime identity 和 policy。此处历史实现曾要求 `assessment` 必须 `formal_run_authorized=true`；该技术阻断口径现由 D-085 取代：ready 的 Assessment 可执行，未授权状态以 warning 和 frozen false provenance 表达。

**Commit**

```text
feat: persist exact run plans and technical preflight
```

### Task 10：实现通用 source-provider registry 与 run source resolver

**Files**

- Create: `src/pilot_assessment/runtime/sources.py`
- Create: `tests/runtime/test_sources.py`

**RED**

测试 provider 按 stable `source_id` 注册、重复拒绝、依赖闭包拓扑执行、per-run cache、未知/缺失 source 结构化诊断，以及 resolver 不按 Evidence/Anchor ID 分支。

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_sources.py -q
```

**GREEN**

定义 transport-neutral `RuntimeSourceProvider` protocol 和 `RuntimeSourceProviderRegistry`。provider 从 `AlignedSession`、task semantics、annotations 或已声明 derived dependencies 生成 Evidence binding values；Hover 所需 20 个 source descriptors 通过注册表组装，不进入通用 executor 的 `if/elif`。缺失可选 source 形成 omitted evidence，不映射为 Unacceptable。

**Commit**

```text
feat: resolve versioned evidence sources at runtime
```

### Task 11：实现 Evidence → Observation → BN assessment pipeline

**Files**

- Create: `src/pilot_assessment/runtime/pipeline.py`
- Create: `tests/runtime/test_pipeline.py`

**Smoke**

构造只包含极少 active Evidence/BN 节点的 published scheme，使用 micro managed session 完成 ingestion、synchronization、source resolution、recipe compilation/execution、EvidenceBinding mapping 和 exact BN inference。验证至少一个 observation、posterior 和 trace 可序列化；不要求 18 个 Evidence 数值 golden。

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_pipeline.py -q
```

**Implementation**

`AssessmentPipeline.execute(snapshot, cancellation, progress)` 只从 frozen plan 遍历 active EvidenceVersions。每个 recipe 复用 M4R compiler/executor；scorer state/likelihood 通过 exact `EvidenceBindingVersion` 形成 M5 `ObservationSet`；BN 复用 `InferenceEngine`。合法的差表现完整进入推理；只有 source 不适用/缺失才 omitted。结果和 trace 以 managed artifacts 保存，原始 bundle 永不回写。

**Commit**

```text
feat: execute managed evidence and Bayesian pipeline
```

### Task 12：实现 single-worker run coordinator、progress、cancel 与 recovery

**Files**

- Create: `src/pilot_assessment/runtime/coordinator.py`
- Create: `tests/runtime/test_coordinator.py`

**RED**

测试 queued→running→completed/failed、event 先持久化后通知、single-worker 顺序、重复 cancel 幂等、stage/Evidence/artifact 边界 cooperative cancel，以及 reopen 把 running/cancelling 标成 interrupted 而不伪造结果。

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_coordinator.py -q
```

**GREEN**

使用单个受控 worker 和 project-scoped cancellation tokens。coordinator 不强杀 NumPy/Polars/operator 调用；percent 只作展示，正确性来自 frozen completed/total。terminal transition、result envelope、transaction receipt 和 audit 使用明确 transaction boundary。

**Commit**

```text
feat: coordinate durable assessment runs
```

### Task 13：实现 JSONL framing 与 JSON-RPC dispatcher

**Files**

- Create: `src/pilot_assessment/sidecar/__init__.py`
- Create: `src/pilot_assessment/sidecar/errors.py`
- Create: `src/pilot_assessment/sidecar/framing.py`
- Create: `src/pilot_assessment/sidecar/dispatcher.py`
- Create: `tests/sidecar/test_framing.py`
- Create: `tests/sidecar/test_dispatcher.py`

**RED**

测试 UTF-8 JSONL、非 object/invalid JSON、4 MiB limit、标准 error codes、domain error data、request/notification 区分、第一项业务请求必须 hello、协议版本协商和并发 notification/response 不发生字节交叉。

```powershell
& .\.tools\uv\uv.exe run pytest tests/sidecar/test_framing.py tests/sidecar/test_dispatcher.py -q
```

**GREEN**

实现单一 stdout serializer，所有日志只走注入 logger/stderr。dispatcher 只验证 framing、method params 和 runtime context，再调用注册 method handler；Evidence/BN 逻辑不复制到协议层。稳定 domain errors 使用 `-32000..-32099` 与机器 `error_code`。

**Commit**

```text
feat: add local JSON-RPC sidecar core
```

### Task 14：实现 M6 method adapters 与 stdio sidecar entrypoint

**Files**

- Create: `src/pilot_assessment/sidecar/methods.py`
- Create: `src/pilot_assessment/sidecar/server.py`
- Create: `src/pilot_assessment/sidecar/__main__.py`
- Create: `tests/sidecar/test_methods.py`
- Create: `tests/sidecar/test_server_subprocess.py`

**Smoke**

通过真实 subprocess 完成 `runtime.hello`、`project.create/open/get/close`、`component.version.list/get`、`operator.catalog.list`、`scheme.version.list/get`、draft edit、`run.preflight/start/status/events/cancel`、result read 和 `runtime.shutdown` 的最小闭环。断言 stdout 每行均为合法 JSON-RPC object，stderr 日志不污染 stdout，大 payload 只返回 artifact reference。

```powershell
& .\.tools\uv\uv.exe run pytest tests/sidecar/test_methods.py tests/sidecar/test_server_subprocess.py -q
```

**Implementation**

实现规格 §11 的方法表。所有 mutation 统一走 transaction ID/idempotency；graph convenience methods 转换为现有 M5 typed operations；`run.start` 返回持久 run ID，不把时序/图像 bytes 写入 JSON。入口为 `python -m pilot_assessment.sidecar`，stdio 默认无网络端口。

**Commit**

```text
feat: expose M6 application through stdio sidecar
```

### Task 15：完成轻量 managed vertical slice 与 M6 收尾

**Files**

- Create: `tests/integration/test_m6_managed_assessment.py`
- Modify: `README.md`
- Modify: `docs/product/07_RUNTIME_PROTOCOL_DESIGN.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Modify: this plan status and task checkmarks

**Integrated smoke**

在一个临时 project 中完成：create → import micro bundle → seed/read model library → 从基础方案派生并发布一个小方案 → software-test run → persisted result → close → move project directory → reopen → exact result/model replay。外部 bundle 在 import 后删除，以证明评估只依赖 managed copy。

```powershell
& .\.tools\uv\uv.exe run pytest tests/integration/test_m6_managed_assessment.py -q
```

**Regression and build gate**

```powershell
& .\.tools\uv\uv.exe run pytest tests/evidence tests/model_library tests/schemes tests/bayesian tests/integration/test_m5_lightweight_workflow.py -q
& .\.tools\uv\uv.exe run pytest -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
& .\.tools\uv\uv.exe run ruff check .
& .\.tools\uv\uv.exe run ruff format --check .
& .\.tools\uv\uv.exe run ty check src
& .\.tools\uv\uv.exe build
```

随后从 repository 外临时目录安装 wheel，执行 import、schema-resource read、project create/open 与 sidecar hello smoke。更新状态文档时必须明确：M6 仅 engineering verified；M7 UI、M8 packaging/handoff 和科学验证仍未完成。

**Commit**

```text
docs: close M6 local runtime milestone
```

## 6. 完成判定

只有同时满足以下条件才把本计划状态改为 `Completed / engineering verified`：

1. Task 1–15 均有独立可追踪提交；
2. project 可移动并 reopen，数据库没有持久绝对 project path；
3. external session 被完整复制且后续执行不依赖外部源；
4. M5 component/draft/publish exact identity 在重启后保持；
5. retry、revision conflict、file promotion 和 crash recovery 不制造重复或半状态；
6. pipeline 动态读取 locked scheme，而非固定 Hover/18/11/4；
7. 差表现数据不会被所谓质量门过滤；
8. run progress、cancel、failed、interrupted、completed 与 result 可持久查询；
9. sidecar 协议闭环通过且 stdout 无日志污染；
10. focused、regression、full suite、schema zero-drift、lint、format、type check、build 和 external-wheel smoke 全部通过。

M6 完成只说明系统框架可持久、可运行、可供前端调用；不代表任何 starter Evidence、BN 或飞行员能力评分已获专家认可。

## 7. 实施关闭记录

Task 1–14 已按顺序形成独立提交：

| Task | Commit | 结果 |
|---:|---|---|
| 1 | `339ca98` | project/run contracts 与双目录 schema |
| 2 | `4af8bcd` | portable project 与 SQLite foundation |
| 3 | `39be69f` | durable exact component library |
| 4 | `41d862e` | durable draft/history 与 atomic publication |
| 5 | `7895bf0` | transaction idempotency 与 audit |
| 6 | `5b590cb` | content-addressed managed artifacts |
| 7 | `e0d107a` | managed Session Bundle import |
| 8 | `698294e` | project application composition 与 starter seed |
| 9 | `1169e5f` | exact run plan 与 technical preflight |
| 10 | `bb7df13` | versioned runtime source resolution |
| 11 | `c4e8913` | Evidence → Observation → BN pipeline |
| 12 | `5c6e54a` | durable coordinator、progress/cancel/recovery |
| 13 | `6bb24ba` | JSONL framing 与 JSON-RPC dispatcher |
| 14 | `43e87d6` | method adapters 与 stdio sidecar |
| 15 | 本计划关闭提交 | managed vertical slice、完成门与文档收口 |

Task 15 使用单个轻量全模态 fixture 和仅包含 O1 及其 BN ancestor closure 的测试方案完成：external bundle 导入后删除原目录，评估仍从 managed copy 完成；project 整体换目录并 reopen 后，session revision、published scheme、component hashes、result 和 artifacts 均可 exact replay。

2026-07-16 fresh completion gate：

- M4R/M5/M6 focused regression：`151 passed in 17.99s`；
- full repository：`1632 passed, 3 skipped in 337.27s`；三个 skip 仅为 host symlink 限制和两条未配置 repository-external CSV 的 opt-in E2E；
- 44 种 Schema 在 root/package 双目录间重生成后 tracked drift 为零；Ruff lint、313-file format check 与 `ty check src` 通过；
- fresh build 成功生成 wheel 与 sdist；
- repository 外临时安装的 wheel 已通过 module-origin、schema-resource、project create/close/open 与 `python -m pilot_assessment.sidecar` hello/shutdown smoke。

因此 Task 1–15 与 §6 完成条件均已满足，M6 状态为 **engineering verified**。M7 WinUI、M8 packaging/handoff 和领域专家科学校准仍不属于本结论。
