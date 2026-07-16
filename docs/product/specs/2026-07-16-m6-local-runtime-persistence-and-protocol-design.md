# M6 Local Runtime, Durable Persistence and Sidecar Protocol Design

| 字段 | 值 |
|---|---|
| 状态 | Implemented / engineering verified；Task 1–15 与 completion gate 已关闭 |
| 日期 | 2026-07-16 |
| 上游里程碑 | M1–M3、M4R、M5 engineering verified |
| 下游里程碑 | M7 WinUI Expert Designer；M8 packaging/handoff |
| 决策基线 | D-006、D-007、D-009、D-031–D-046 |
| 实施方式 | INLINE；平台不变量采用轻量 test-first，文件/协议/全流程采用 focused smoke |

## 1. 目的

M6 把 M5 已验证的 transport-neutral、进程内建模后端变成可以被 Windows
前端长期使用的本地运行时。完成后，用户可以创建或打开一个受管项目，把外部
Session Bundle 复制进入项目，关闭并重启软件后继续编辑模型、选择精确方案、
启动运行并读取结果。前端通过本地 stdio sidecar 使用这些能力，不直接读写数据库，
也不复制 Evidence/BN 业务逻辑。

M6 解决的是持久化、事务、进程协议和运行生命周期，不负责证明 starter Evidence、
阈值、CPT 或能力结论科学有效。专家使用已有 operator 修改 EvidenceRecipe、BN、state
或 CPT 时，仍然只经过最小技术校验，不增加人工审批或 per-edit pytest。

## 2. 已比较方案与选择

### 2.1 方案 A：每项目自包含 SQLite + 受管文件目录（采用）

每个项目是一个可整体移动的目录。SQLite 保存 canonical JSON、版本、草稿、事务、
运行和审计元数据；Session Bundle 与大型 artifact 保存在同一项目根下的受管目录。
所有持久化路径均为项目相对路径。

优点是项目数据与应用安装包分离、易于移动、SQLite 可以承载 M5 原子发布语义，且
大文件不进入数据库或 JSON-RPC。代价是 M8 仍需提供受控导出、备份和升级体验。

### 2.2 方案 B：整个应用只有一个全局数据库（不采用）

它能天然跨项目共享组件，但项目搬迁、隔离、恢复和删除都会依赖应用机器上的全局
状态，不符合用户已经确认的“复制到受管项目存储”和后续设备迁移目标。

### 2.3 方案 C：纯 JSON/目录持久化（不采用）

它直观但难以同时保证草稿 optimistic revision、component/scheme 原子发布、幂等重试、
运行状态和 crash recovery；文件锁与多文件提交也会形成第二套事务系统。

## 3. 范围

### 3.1 M6 交付

1. 自包含 project root、SQLite schema/migration、project create/open/close/recovery；
2. M5 component library、scheme draft/history 和 `WorkspaceUnitOfWork` 的 durable adapter；
3. 外部 Session Bundle inspect，以及 byte-preserving、checksum-verified managed import；
4. content-addressed derived/result artifact store、引用关系、保留状态和 orphan cleanup；
5. mutation transaction/idempotency、audit event 和 optimistic revision persistence；
6. published scheme/session exact lock、`RunPreflightReport`、run/result contracts；
7. progress、cooperative cancel、terminal error、sidecar crash 后 interrupted recovery；
8. JSON-RPC 2.0 + JSONL stdio sidecar、握手、capability、方法和稳定错误合同；
9. M7 所需的 project/session/component/scheme/operator/run read/write protocol surface；
10. 一个小型 managed-session → EvidenceRecipe → BN posterior → persisted result vertical slice。

### 3.2 M6 不交付

- WinUI 页面、画布、表单或安装包；
- 应用自动更新、项目备份 UI、跨项目 merge 或云同步；
- 任意 Python/eval 编辑器或未受信 operator 安装；
- 自动学习 Evidence、BN topology 或 CPT；
- 每个专家修改后的测试、科学审批或真实飞行员有效性结论；
- 重型长 session 性能基准；
- 崩溃后从某个 operator 中间点继续计算。v0.1 将活动 run 标记为 `interrupted`，
  用户可在同一 exact lock 上新建一次 run。

M8 打包系统时只包含应用、后端、starter resources 和文档；任何用户项目、session、
run 或本机数据库都不进入系统安装包。

## 4. 项目与存储边界

### 4.1 Project 的含义

一个 project 是用户可移动的完整工作空间。M5 所称“全局组件库”在 M6 中表示
**该 project 内对全部任务方案共享**的 Evidence/BN/component library；它不被单个
Hover、session 或 scheme 私有化。不同 project 之间默认隔离，跨项目交换属于 M8。

v0.1 一个 sidecar 同时只打开一个 project。前端切换项目时必须先关闭当前 project；
活动 run 存在时只能在其到达 terminal state 后关闭，或明确请求 cooperative cancel。

### 4.2 固定目录

```text
<project-root>/
  project.json
  project.sqlite3
  sessions/
    <session-id>/
      <session-revision-id>/
        bundle/
  artifacts/
    sha256/
      <first-two-hex>/
        <full-sha256>/
          payload
  exports/
  logs/
  staging/
    imports/
    artifacts/
    results/
```

`project.json` 只保存打开项目所需的小型 locator：format version、project ID、显示名称、
数据库相对路径和创建时间。业务状态以 SQLite 为准。数据库、manifest 和 artifact
记录中禁止持久化项目绝对路径；因此项目目录移动后仍可打开。

`sessions/` 保存用户导入的原始 bundle 副本。`artifacts/` 保存派生数据、trace、result
和 export payload。`staging/` 的内容从不被正式记录直接引用，可由 recovery 清理。

### 4.3 SQLite 基线

- 使用 Python 标准库 `sqlite3`，不新增 ORM；
- `PRAGMA foreign_keys=ON`；
- `journal_mode=WAL`，`synchronous=FULL`；
- 显式 `schema_migrations`，不依赖隐式 `PRAGMA user_version` 作为唯一迁移记录；
- DB-only mutation 使用 `BEGIN IMMEDIATE`；
- canonical domain object 存为 UTF-8 RFC 8785 JSON bytes，不使用 pickle；
- 时间统一存为 UTC RFC 3339；
- IDs、kind、concept ID、content hash、lifecycle 等查询字段独立成列并建索引；
- exact object 每次读取后重新通过对应 Pydantic contract 和 content hash 验证。

核心表族为：

| 表族 | 责任 |
|---|---|
| `project_metadata`, `schema_migrations` | 项目身份与 schema 版本 |
| `library_records`, `library_tags`, `library_lifecycle_events` | M5 immutable concepts/versions 与 archive metadata |
| `scheme_drafts`, `draft_snapshots`, `draft_transitions` | autosave、optimistic revisions、undo/redo |
| `sessions`, `session_revisions`, `session_files` | managed bundle identity、root hash、file inventory |
| `managed_artifacts`, `artifact_references` | content-addressed artifact 与 owner 引用 |
| `idempotency_transactions` | mutation request hash、状态和 canonical response |
| `runs`, `run_events`, `run_results` | exact lock、progress、terminal result/error |
| `audit_events` | import、draft mutation、publish、run、export 事件 |

M6 durable repositories 实现现有 M5 protocols；M5 service 不依赖 SQLite，也不增加
`get_latest`。进程内 adapters 继续用于 focused unit tests。

## 5. Durable identity 和 public contracts

M6 新增以下 strict/frozen contracts，并按既有规则发布双目录 Draft 2020-12 schemas：

```text
ProjectDescriptor
  project_id, format_version, name, created_at

SessionRecord
  session_id, project_id, participant_id, lifecycle
  current_session_revision_id, created_at

SessionRevision
  session_revision_id, session_id
  managed_bundle_path, manifest_hash, bundle_root_hash
  file_inventory_hash, source_kind, imported_at, imported_by
  ingestion_readiness_ref, synchronization_ref

ManagedArtifact
  artifact_id, sha256, byte_size, media_type, schema_id
  managed_relative_path, lifecycle, created_at

ArtifactReference
  owner_kind, owner_id, role, artifact_id

TransactionReceipt
  transaction_id, method, request_hash, status
  response_payload, audit_event_id, completed_at

RunPreflightReport
  preflight_id, session_revision_ref, scheme_ref
  technical_disposition, formal_run_authorized
  synthetic_data, locked_component_refs, diagnostics, preflight_hash

RunSnapshot
  run_id, purpose, session_revision_ref, scheme_ref
  exact component/source/operator/engine identities
  runtime_parameters_hash, snapshot_hash

AssessmentRun
  run_id, snapshot, state, stage, progress_sequence
  requested_at, started_at, finished_at, cancellation_requested_at

RunResultEnvelope
  result_id, run_id, snapshot_hash
  evidence result/trace artifact refs
  observation-set, posterior and inference-trace refs
  reporting/coverage refs, scientific status, result_hash
```

`RunPreflightReport.technical_disposition` 只回答当前 frozen session/scheme/runtime 是否可执行。
`formal_run_authorized` 还受 reporting policy 和 synthetic provenance 约束。未校准、无论文或
专家意见不一致只能成为 warning/metadata，不能让技术上合法的 `software_test`/preview 失败。

## 6. Managed Session Import

### 6.1 Inspect 与 import 分离

`session.inspect` 对用户选择的外部目录执行现有 M1/M2 只读检查，不创建 session ID，
不复制文件，也不把外部绝对路径写入数据库。

`session.import` 必须带 `transaction_id`，并执行：

1. 重新加载外部 manifest 和文件 inventory，避免复用过期 inspect 结果；
2. 拒绝路径穿越、symlink/reparse-style external reference、非常规文件和越界资源；
3. 把 bundle 按原相对路径复制到 `staging/imports/<transaction-id>`；
4. 逐文件复核 byte size 与 SHA-256，并重新运行 M1/M2；
5. 计算稳定 `bundle_root_hash` 和 `file_inventory_hash`；
6. 原子 promote 到目标 session revision 目录；
7. 在同一数据库提交中写入 session/revision/file records、transaction receipt 和 audit event；
8. 返回 `session_id + session_revision_id`，以后 run 只接收该 exact revision。

导入后外部源可被删除或修改，不影响 managed copy。运行前必须重新验证 managed root hash；
若用户在项目目录外部手工修改文件，run preflight 返回 `MANAGED_SESSION_CHANGED`，不静默接受。

已有 session 的新数据不得覆盖原 revision，而是创建并行 `SessionRevision`。v0.1 UI 可以只
暴露首次 import，但存储合同从一开始支持 revision。

## 7. Managed Artifact 生命周期

派生 artifact 采用 SHA-256 content address。写入流程固定为：

1. 在 `staging/artifacts/<transaction-id>` 写临时 payload；
2. flush/close 后计算 SHA-256 与 byte size；
3. 验证 schema/media contract；
4. 若相同 digest 已存在，复核现有 bytes 并复用；
5. 否则原子 rename 到 `artifacts/sha256/.../payload`；
6. 数据库提交 `ManagedArtifact + ArtifactReference`；
7. 未被任何 reference 使用的 staging/final orphan 由启动 recovery 清理。

引用计数由 `artifact_references` 查询得出，不维护易漂移的独立整数。删除 owner 只移除引用；
artifact 进入 `unreferenced` 保留状态，默认不立即删除。M8 再提供用户可见的保留/清理策略。

Session 原始 bundle 不与 derived artifacts 混装，也不被 Evidence 执行器回写。Evidence、BN、
result 和 trace 只产生新的 managed artifacts。

## 8. Transaction、optimistic revision 与 recovery

### 8.1 幂等写请求

所有持久化 mutation、session import、scheme publish 和 `run.start` 都携带稳定
`transaction_id`。sidecar 对 canonical method + params 计算 `request_hash`：

- 第一次成功：保存 canonical response；
- 相同 transaction ID + 相同 request hash：返回第一次 response，不重复执行；
- 相同 transaction ID + 不同 request hash：返回 `TRANSACTION_REUSE_MISMATCH`；
- 上次在 file promotion 中断：recovery 先恢复到无正式引用的状态，再允许相同请求重试。

JSON-RPC request ID 只关联一次进程通信，不承担业务幂等；重试可使用新 request ID，必须
复用 transaction ID。

### 8.2 M5 原子发布

Durable `WorkspaceUnitOfWork.publish_atomic` 在一个 SQLite transaction 中完成：

1. 检查 draft graph/layout expected versions；
2. 插入全部 changed immutable component versions；
3. 插入新 exact-pinned `AssessmentSchemeVersion`；
4. rebase draft 并重置其 history；
5. 写 transaction receipt 与 audit event；
6. commit。

任一错误都不产生可见 component/scheme/draft 半状态。普通参数、operator graph、BN 和 CPT
修改仍然 free-to-modify；SQLite 只保证保存的是用户提交的 canonical 内容。

### 8.3 启动恢复

`project.open` 在提供业务 capability 前执行：

- SQLite integrity/foreign-key/schema version 检查；
- 删除无 durable intent 的 staging 目录；
- 处理 prepared-but-uncommitted file operations；
- 验证 DB 引用的 managed path 仍在项目根内；
- 把 `running` 或 `cancelling` run 原子标记为 `interrupted`；
- WAL checkpoint 状态和上一次 clean shutdown 进入 diagnostics。

恢复不得把不完整结果标记为 completed，也不得重新解释旧 scheme/session identity。

## 9. Run preflight、snapshot 与执行

### 9.1 Run purpose

M6 v0.1 支持：

- `preview`：锁定 exact draft hash/revisions，结果为 non-formal，可选择不进入长期历史；
- `software_test`：锁定 published scheme 和 managed session，持久化完整结果，但明确标记
  engineering/synthetic status；
- `assessment`：只有 `formal_run_authorized=true` 才可启动。

当前 Hover starter reporting policy 为 `formal_run_authorized=false`，synthetic bundle 也不能
成为正式飞行员评估；它们仍可完整执行 `software_test`，用于验证系统工作流。

### 9.2 Preflight

`run.preflight` 必须重新检查：

1. managed session revision 和 root hash；
2. ingestion readiness 与 native-rate synchronization 是否可构造；
3. task reference/annotation/AOI 等 required sources；
4. scheme exact pin/hash/source closure；
5. EvidenceRecipe compile 和 operator availability；
6. Evidence-to-BN observation binding、BN/CPT 和 inference compile；
7. runtime/schema/engine compatibility；
8. reporting policy、synthetic provenance 与 requested purpose。

它不根据轨迹误差大、控制剧烈、生理数值异常、coverage 或性能好坏拒绝 Evidence。
这些值应按专家 recipe 形成 D/A/U 或执行结果。

### 9.3 Exact snapshot

`run.start` 只接受一次未过期的 preflight identity，并在创建 run 时冻结：

- exact session revision/root hash；
- exact scheme ID/hash 和全部 pinned component IDs/hashes；
- source descriptor closure；
- EvidenceRecipe/operator/scorer identities；
- BN engine、Python/numeric runtime identity；
- execution/reporting parameters；
- preflight hash。

绝对 project path、hostname、进程 ID 和 wall-clock completion order 不进入 snapshot hash。

### 9.4 Pipeline

记录的标准阶段为：

```text
queued
  -> snapshot_validation
  -> ingestion
  -> synchronization
  -> evidence
  -> inference
  -> reporting
  -> completed
```

`evidence` 阶段对 locked scheme 的 active EvidenceVersions 按稳定顺序执行 canonical
EvidenceRecipe，并通过 source resolver 从同一 AlignedSession/task semantics 构造 binding
values。每个 Evidence 的 state/likelihood 经 exact EvidenceBindingVersion 形成 BN Observation；
缺失/不适用按合同 omitted，不把 missing 变成 Unacceptable。BN 使用 M5 exact inference engine
生成 posterior 和只读 influence trace。

M6 不按 Hover ID 或固定 18 个 Evidence 分支。starter vertical slice 可以很小，但 production
resolver、executor 和 run inventory 必须从 locked scheme 动态读取。

## 10. Progress、cancel、失败与 crash

Run state：

```text
queued -> running -> completed
                  -> failed
                  -> cancelling -> cancelled
                  -> interrupted
```

每次 progress 都有单调递增 `sequence`，先写 `run_events` 再发 notification。前端错过消息后
可以通过 `run.status`/`run.events.list` 恢复。percent 是显示值；正确性依赖 stage + completed/total，
total 从 frozen execution plan 读取，不写死 18。

取消是 cooperative：在 stage、每条 EvidenceRecipe 和持久 artifact commit 边界检查 token；
不会强行中断一个正在运行的 NumPy/Polars/operator 调用。`run.cancel` 重试幂等，terminal run
返回当前 terminal state。

Sidecar 异常退出后，已提交的 event/result 保留；非 terminal run 在下次 `project.open` 标记
`interrupted`。v0.1 不原地续算，用户以同一 session/scheme snapshot 新建 run，旧 run 保留。

## 11. Sidecar 与 JSON-RPC

### 11.1 Transport

- WinUI 启动隐藏 Python sidecar；不监听网络端口；
- stdin/stdout 使用 UTF-8 JSON-RPC 2.0，每行一个完整 JSON object；
- stdout 只能写 protocol message；日志只写 stderr 和 project log；
- 单条消息默认最大 4 MiB；大数据只传 ID、相对路径、size、media type 和 checksum；
- 所有 stdout write 经一个 serializer/lock，notification 与 response 不会字节交叉；
- 第一个业务请求必须是 `runtime.hello`；无共同协议版本则拒绝后续业务方法。

### 11.2 v1 capability

最小 capability IDs：

```text
runtime.protocol.v1
project.persistence.v1
session.managed-import.v1
component.library.v1
scheme.workspace.v1
operator.catalog.v1
assessment.run.v1
artifact.read.v1
audit.read.v1
```

### 11.3 M6 方法集

| 领域 | 方法 |
|---|---|
| Runtime | `runtime.hello`, `runtime.status`, `runtime.shutdown`, `capabilities.list`, `schema.get` |
| Project | `project.create`, `project.open`, `project.get`, `project.close` |
| Session | `session.inspect`, `session.import`, `session.list`, `session.get`, `session.artifact.get` |
| Component | `component.concept.list/get`, `component.version.list/get/diff` |
| Operator | `operator.catalog.list`, `operator.definition.get` |
| Scheme | `scheme.version.list/get/diff`, `scheme.draft.create/get/discard/publish` |
| Editing | `graph.snapshot.get`, `graph.operations.apply`, `graph.undo`, `graph.redo`, `layout.update`, `graph.validate` |
| Run | `run.preflight`, `run.start`, `run.preview`, `run.status`, `run.events.list`, `run.cancel` |
| Result | `result.get`, `result.artifact.get` |
| Audit | `audit.events.list` |

便利方法不得形成第二套写路径；node/edge/CPT/Evidence 修改最终都转换为 M5 typed scheme operation。
协议层只验证 framing/context 并调用 domain/application service，不复制 Evidence/BN 计算。

### 11.4 稳定错误

JSON-RPC 标准错误保留 `-32700/-32600/-32601/-32602/-32603`。Domain error 使用
`-32000..-32099`，并在 `error.data` 固定包含：

```text
error_code, message, recoverable, trace_id,
transaction_id?, path?, current_revision?, diagnostics?
```

M6 最低机器码：

```text
PROTOCOL_VERSION_UNSUPPORTED
PROJECT_NOT_OPEN, PROJECT_FORMAT_UNSUPPORTED, PROJECT_RECOVERY_FAILED
TRANSACTION_REUSE_MISMATCH
SESSION_IMPORT_INVALID, MANAGED_SESSION_CHANGED, CHECKSUM_MISMATCH
ARTIFACT_NOT_FOUND, ARTIFACT_INTEGRITY_FAILED
GRAPH_VERSION_CONFLICT, LAYOUT_VERSION_CONFLICT
DRAFT_NOT_FOUND, SCHEME_NOT_FOUND, COMPONENT_NOT_FOUND
RUN_PREFLIGHT_FAILED, RUN_NOT_FOUND, RUN_ALREADY_TERMINAL
RUN_CANCEL_REJECTED, RUN_INTERRUPTED
INFERENCE_FAILED, INTERNAL_ERROR
```

错误消息可供人阅读，但前端恢复逻辑只能依赖 `error_code` 和 typed data。

## 12. Security、privacy 与日志

- 只接受当前 Windows 用户可访问的本地路径；
- 所有 managed path resolve 后必须仍在 project root；
- import 不跟随 symlink/junction/reparse external references；
- `session.artifact.get` 返回的是运行时验证后的只读文件引用；DB 只存相对路径；
- 普通日志不记录 participant identity、原始 EEG/ECG/gaze、图像内容或整条 recipe payload；
- audit 保存 actor、operation、IDs、hashes 和 diff，不保存原始生理数据；
- diagnostic export 默认脱敏，完整 support bundle 属于 M8；
- sidecar 不执行 RPC 传入的 Python、module path 或 shell command。

## 13. Lightweight verification strategy

M6 严格测试平台不变量，而不是 starter 科学内容：

### 13.1 轻量 test-first

- SQLite immutable exact record、hash verification 和 reopen；
- durable draft optimistic revision、undo/redo 和 atomic publish rollback；
- transaction replay/mismatch；
- managed import staging/promotion/checksum 和 recovery；
- artifact dedup/reference/orphan cleanup；
- run state transition、exact lock、progress sequence、cancel/interrupted recovery；
- JSONL framing、hello、stdout purity、payload limit 和 error mapping。

### 13.2 Focused smoke

- 小型 project create → close → reopen；
- 一份 micro Session Bundle managed import；
- Hover starter seed 到 durable library；
- 一次极小 software-test run，从 managed session 产生至少一个 Evidence observation、BN posterior
  和 persisted result；
- sidecar subprocess hello、project.open、读取 operator/scheme、运行状态和 shutdown；
- M5 copy-on-write 修改在重启后仍保留，旧 scheme 可 exact replay。

不生成四套万行数据，不要求 18 个 starter Evidence 的科学 golden，也不在每个 RPC task 后跑
full repository。发现平台 bug 时先增加最小 failing regression。

## 14. 实施分解

M6 按下列可独立提交的层次实现：

1. contracts/schema 与 project SQLite foundation；
2. durable M5 component/draft repositories 和 atomic UoW；
3. managed session/artifact/transaction/audit services；
4. run contracts、preflight、repository、job coordinator 和 recovery；
5. aligned source resolver、Evidence → Observation → BN execution bridge；
6. JSON-RPC framing/dispatcher、method adapters 和 sidecar entrypoint；
7. lightweight vertical slice、reopen/crash tests、docs/status/build gate。

每层只测试其平台不变量。任何 task 都不得重新固定 Hover/18/11/4 为通用引擎上限。

## 15. 完成条件

M6 只有同时满足以下条件才可标记 engineering verified：

1. 新项目可创建、关闭、移动目录并重新打开；
2. 外部 bundle 被复制到 managed storage，后续运行不依赖外部源；
3. M5 model library/draft/publish/replay 在进程重启后保持 exact identity；
4. DB-only publish 原子；file-backed operation 中断后可确定性清理/重试；
5. mutation retry 不重复执行，revision conflict 不覆盖 canonical state；
6. run 锁定 exact session/scheme/components/operators/runtime，结果可按 snapshot replay；
7. progress/cancel/failed/interrupted/completed 可查询且 crash 后不伪造完成；
8. stdio sidecar 完成 hello、项目、模型、session、run、result 的最小协议闭环；
9. stdout 无日志污染，大 payload 不进入 JSON；
10. focused M6 tests、M4R/M5 regression、Ruff/format、`ty check src`、schema zero-drift、build 和
    repository-external wheel smoke 通过；
11. 状态文档明确 M7/M8 和科学验证仍未完成。

完成 M6 不会自动把 Hover starter 或 synthetic session 变成正式科学评估。

## 16. 自审结果

- **无 placeholder：** project layout、数据库边界、file transaction、run state、方法和错误均有
  明确 v0.1 口径；M8 范围被显式排除，而不是用 TBD 代替。
- **与 M5 一致：** durable adapters 实现现有 repository/UoW protocols；不改变 component
  identity、copy-on-write、两类 edge、BN 方向或 expert free-to-modify 语义。
- **与用户存储要求一致：** session 复制到自包含 project root；系统安装包永不携带用户数据。
- **无科学门回流：** run preflight 只检查技术可执行性、用途和已声明 provenance，不按表现值
  或所谓原始数据质量过滤 Evidence。
- **范围风险已处理：** M6 分层实施，只有一个 micro vertical slice；WinUI、packaging、backup
  和重型性能验证不混入本里程碑。
