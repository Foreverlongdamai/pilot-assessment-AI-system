# Runtime Protocol Design

| 字段 | 值 |
|---|---|
| 设计版本 | v0.5 implemented M6 protocol overview |
| Transport | JSON-RPC 2.0 / JSONL over stdin/stdout |
| 客户端 | Windows WinUI 3 前端 |
| 服务端 | Python Assessment Core sidecar |
| 适用范围 | 本地、单用户、离线评估 |

> **当前权威补充：** M6 的已实现冻结边界以 [M6 Local Runtime, Durable Persistence and Sidecar Protocol Design](./specs/2026-07-16-m6-local-runtime-persistence-and-protocol-design.md) 为准；M7 的 current ModelNode/TaskScheme/autosave/RunSnapshot 目标以 [M7 WinUI Expert Designer and Task Activation Workspace Design](./specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) 为准。M6 已于 2026-07-16 工程验证；当前入口为 `python -m pilot_assessment.sidecar`，但仍暴露 legacy draft/publish surface。M7 必须扩展 current-object methods，method adapters 继续只调用同一组 application/domain services，不复制 Evidence 或 BN 逻辑。M7 .NET client 与 M8 安装包仍未实现。

## 1. 目标与边界

Runtime adapter 把桌面软件与 Assessment Core 隔离开。它负责进程生命周期、协议版本、命令调度、进度、取消、错误和诊断，但不拥有 anchor 算法或 BN 业务逻辑。

v0.1 不启动 localhost HTTP 服务，不开放网络端口，也不通过 JSON 传输视频、图像或长时间序列。未来增加 HTTP adapter 时，必须复用相同的 application services 和 domain contracts。

## 2. 部署模式

### 2.1 安装包模式

1. 用户启动 Windows 软件；
2. 前端定位安装包内兼容的 backend runtime；
3. 前端以隐藏子进程启动 sidecar，并设置项目数据根目录；
4. 进行 runtime.hello 握手；
5. sidecar 报告 capabilities、协议版本、engine 版本和健康状态；
6. 前端在退出时请求 runtime.shutdown；超时后才执行受控终止。

用户无需手动打开命令行或配置 Python 环境。

### 2.2 开发模式

开发人员可以运行 `python -m pilot_assessment.sidecar`，由 host 连接其 stdin/stdout。开发模式允许额外 stderr 诊断，但 stdout 协议消息和正式版本必须与未来安装包模式一致。

### 2.3 生命周期状态

stopped → starting → ready ↔ busy → stopping → stopped

异常状态包括 degraded 和 crashed。degraded 表示后端仍可响应诊断但某项能力不可用；crashed 表示进程已退出。前端不得把进程存在等同于 ready，必须以成功握手和 health response 为准。

## 3. Transport 规则

- stdin：前端发送的 UTF-8 JSON-RPC request/notification，每个消息占一行。
- stdout：后端发送的 UTF-8 JSON-RPC response/notification，每个消息占一行；禁止混入日志。
- stderr：人类可读日志，可由前端收集到诊断面板。
- 文件日志/crash bundle 由未来 M7/M8 host 管理；M6 自身把人类日志写 stderr，把持久业务审计写 project SQLite。
- 消息必须是单行有效 JSON；字符串内部换行按 JSON 转义。
- request ID 在客户端进程生命周期内唯一；notification 不带 ID。
- response 与异步 run notification 共用一个加锁 writer，前端必须按 ID 区分 response，并按 method 区分 notification；v0.1 server 的 request dispatch 为串行。
- 每个消息设最大尺寸；默认建议 4 MiB，超过时改用文件 artifact。
- 密钥、原始生理信号、完整 gaze 数据和图像不得写入普通日志。

## 4. 握手

前端启动后第一个业务请求必须是 runtime.hello。

~~~json
{"jsonrpc":"2.0","id":"req-0001","method":"runtime.hello","params":{"protocol_version":"1.0","client":{"name":"PilotAssessment.Windows","version":"0.1.0"},"supported_protocols":["1.0"]}}
~~~

成功响应：

~~~json
{"jsonrpc":"2.0","id":"req-0001","result":{"protocol_version":"1.0","runtime_id":"runtime.01J...","backend_version":"0.1.0","engine":{"name":"assessment-core","version":"0.1.0"},"capabilities":["runtime.protocol.v1","project.persistence.v1","session.managed-import.v1","component.library.v1","scheme.workspace.v1","operator.catalog.v1","assessment.run.v1","artifact.read.v1","audit.read.v1"],"state":"ready","max_message_bytes":4194304,"trace_id":"trace-hello-01"}}
~~~

若没有共同协议版本，返回 PROTOCOL_VERSION_UNSUPPORTED；前端必须停止发送其他业务命令，并显示兼容性修复说明。

## 5. 通用请求上下文

JSON-RPC envelope 使用 `id` 关联请求与响应。修改持久状态的 M6 请求另外必须包含：

- transaction_id：稳定 UUID，兼作 idempotency key；响应丢失后的重试必须复用同一值；
- actor：本地用户或工具标识；
- 与操作对应的 expected_revision_id、expected_graph_version 或 expected_layout_version；
- note：可选的人类说明；系统不因未填写理由阻止 autosave 或 apply；
- operations 或 command payload。

v0.1 一个 sidecar 同时只打开一个 project，因此业务请求不重复携带 `project_id`；`project.get` 返回当前 canonical identity。只读请求不需要 transaction ID。

所有响应包含 `trace_id`。经通用 mutation boundary 的成功响应还包含 `transaction_id`、`audit_event_id` 和 `replayed`；创建新 immutable version 的方法同时返回其 exact ID/content hash。

## 6. 方法目录

### 6.1 Runtime 与能力

| 方法 | 用途 |
|---|---|
| runtime.hello | 协议握手与能力协商 |
| runtime.status | 健康、状态、活动 job 与资源摘要 |
| runtime.shutdown | 优雅关闭 |
| capabilities.list | 支持的输入、operators/extensions、模型和导出能力 |
| schema.get | 获取 manifest、EvidenceRecipe、operator 参数、CPT 或 operation schema |

### 6.2 Project 与 session

| 方法 | 用途 |
|---|---|
| project.create / project.open / project.get / project.close | 创建、打开、读取或关闭当前受管项目 |
| session.inspect | 只读检查外部 bundle，不导入 |
| session.import | 校验后复制/注册到托管项目 |
| session.list / session.get | 获取 session、revision 与 metadata |
| session.artifact.get | 获取可展示 artifact 的受控文件引用 |

Runtime DTO 保持阶段顺序和命名：`IngestionReadinessReport`（source content）→ `SynchronizationReport`（native-rate session-time alignment）→ 锁定 exact `AssessmentSchemeVersion`/component closure 并解析 reference → `RunPreflightReport`（运行门）。M6 不提供把这些阶段压成单一 boolean 的 `session.validate`。

### 6.3 Model、graph、anchor 与 CPT

| 方法 | 用途 |
|---|---|
| component.concept.list / get | 查询全局 Evidence/BN concepts |
| component.version.list / get / diff | 查询指定 concept 的全部并行 immutable versions 或比较 exact versions；不提供 latest resolution |
| operator.catalog.list / operator.definition.get | 获取 operator palette、typed ports、parameter schema、UI metadata 与 implementation identity |
| scheme.version.list / get / diff | 查询、比较 exact `AssessmentSchemeVersion` |
| scheme.draft.create / get / discard | 从任意 scheme version 管理 autosaved scheme draft |
| scheme.draft.publish | 最小技术校验后原子创建 changed component versions 与新的 immutable scheme version |
| graph.snapshot.get | 获取 canonical Evidence/BN graphs、layout、graph_version 和 layout_version |
| graph.operations.apply | 原子应用一个或一组 domain operations |
| graph.validate | recipe/BN graph、binding、type/unit、state space、CPT 与编译检查 |
| graph.undo / graph.redo | 基于后端命令日志撤销或重做 |
| layout.update | 批量提交节点位置；只更新 layout_version |

EvidenceRecipe、binding、node、edge、state、CPT 与 reporting policy 的新增/修改/删除不设绕过事务的独立写入口；它们全部编码为 `graph.operations.apply` 的 typed operations。DTO 语义见 [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md)。

未来 M7 可以在 client SDK 中提供 node/edge/parameter/CPT 表单便利方法，但必须转换为上述 operation batch，不得形成第二套写路径。`graph.operations.preview`、extension install、project/result export 属于后续里程碑，不在 M6 method set 中。

这些 JSON-RPC adapters 已接入 M5/M6 durable application services。普通 Evidence/BN 修改仍由专家决定内容；后端只维护 canonical state、乐观版本、最小技术可运行校验、copy-on-write 发布和 exact execution。

### 6.4 Assessment 与结果

| 方法 | 用途 |
|---|---|
| run.preflight | M6 检查 frozen session、exact scheme/component closure、任务前提、compiled recipe/BN plan、operator/schema/engine compatibility 和运行授权；不预先按表现或实际 coverage 过滤 evidence |
| run.start | 启动锁定 exact scheme version ID 与全部 pinned component hashes 的评估 |
| run.preview | 对 executable draft 的 exact graph_version 执行不改变历史的临时预览 |
| run.status | 查询阶段、进度和诊断 |
| run.cancel | 请求协作式取消 |
| run.events.list | 从 durable sequence 增量读取运行事件 |
| result.get / result.artifact.get | 获取 result envelope 与受控 artifact reference；不把大 payload 放入 JSON |
| audit.events.list | 查询模型 autosave、apply、导入与运行的自动审计事件 |

`run.preflight` 是 M6 operation，返回 `RunPreflightReport`；它与 M2 的 `IngestionReadinessReport`、M3 的 `SynchronizationReport` 和 M4 的 `AnchorEvaluationReport` 都不是同一 DTO。M2/M3/M4 报告的 `formal_run_authorized` 固定为 false；只有 M6 基于 frozen `AlignedSession`、已解析 reference、锁定 exact `AssessmentSchemeVersion`/component hashes 和已编译 Evidence/BN plan 决定是否可以创建 AssessmentRun。实际 AnchorResult/raw availability 要等 M4 执行后产生，model-weighted coverage 由 M5 计算，不属于 preflight 的伪预测值。

## 7. 大数据与路径合同

session.inspect 可以接收用户选择的绝对 bundle 路径。正式 import 后，后端把文件逐字节复制到受管理 project storage，并生成 exact session/session-revision identity。后续运行只使用 managed session revision，不保留对外部源的运行依赖。

协议只传：

- bundle path 或 managed artifact ID；
- manifest metadata；
- 相对 artifact path；
- MIME/type 与 byte size；
- checksum；
- 受控 read token 或有效期（如实现需要）。

前端不得把 mp4、frame、Parquet、EDF 或数组 base64 编入 RPC。后端应拒绝越过允许根目录的路径、路径穿越、checksum 不匹配和 import 后被静默修改的文件。

## 8. 原子图操作

所有语义图编辑以 graph.operations.apply 为主入口。

~~~json
{"jsonrpc":"2.0","id":"req-1042","method":"graph.operations.apply","params":{"draft_id":"draft-07","transaction_id":"550e8400-e29b-41d4-a716-446655440010","actor":"user@example","operations":[{"type":"clone_component_version","expected_graph_version":12,"source":{"kind":"evidence_version","version_id":"evidence-version.hover.O2.v1"},"candidate_id":"candidate.evidence.O2-task","replace_source":true}]}}
~~~

成功时，整个 batch 一次提交：

~~~json
{"jsonrpc":"2.0","id":"req-1042","result":{"draft_record":{"draft":{"draft_id":"draft-07","graph_version":13,"layout_version":8,"candidate_components":["..."]},"last_diff":{"operation_type":"CloneComponentVersion","changed_paths":["/candidate_components"]}},"transaction_id":"550e8400-e29b-41d4-a716-446655440010","audit_event_id":"audit-992","replayed":false,"trace_id":"trace-a1"}}
~~~

任一 operation 失败时全部回滚。版本不匹配返回 GRAPH_VERSION_CONFLICT，同时提供 current_graph_version；前端重新获取 canonical snapshot，不得覆盖后端状态。

只移动节点时提交 layout.update，改变 layout_version，不改变 scientific model content hash。增删节点/边、state、binding、anchor 参数或 CPT 会改变 semantic model hash。

尽管名称为 graph_version，它覆盖整个 semantic draft，包括 graph、state、CPT、anchor binding、anchor parameters 和 profile；这些修改共享一个乐观并发版本。组件可以有 content hash，但 v0.1 不允许用独立 parameter version 绕过 graph_version。

### 8.1 Layout update

拖动期间前端只做本地预览，在 drag end 时批量提交：

~~~json
{"jsonrpc":"2.0","id":"req-layout-12","method":"layout.update","params":{"draft_id":"draft-07","candidate_id":"candidate.layout","expected_layout_version":8,"transaction_id":"550e8400-e29b-41d4-a716-446655440020","actor":"user@example","positions":[{"node_id":"evidence-binding-version.hover.O1.v1","x":680.0,"y":120.0},{"node_id":"bn-node-version.hover.TCP.1.v1","x":420.0,"y":180.0}]}}
~~~

~~~json
{"jsonrpc":"2.0","id":"req-layout-12","result":{"draft_record":{"draft":{"draft_id":"draft-07","graph_version":13,"layout_version":9}},"transaction_id":"550e8400-e29b-41d4-a716-446655440020","audit_event_id":"audit-layout-12","replayed":false,"trace_id":"trace-layout-12"}}
~~~

layout.update 不改变 graph_version 或 semantic hash。LAYOUT_VERSION_CONFLICT 只要求刷新或明确重新应用位置，不阻断科学模型编辑。

## 9. 长任务、进度和取消

`run.preflight` 先锁定 exact session revision、scheme/component hashes、source/operator/runtime identities。`run.start` 使用该 preflight 创建 durable run，立即返回 run ID，再由 single worker 执行。`run.preview` 则对 exact draft graph/layout revision 和调用方 observations 做同步只读 BN 预览，不创建正式 run/result history。正式 run 的进度通过 notification：

~~~json
{"jsonrpc":"2.0","method":"run.progress","params":{"contract_id":"run-event","contract_version":"0.1.0","event_id":"run-event.run-88.8","run_id":"run-88","sequence":8,"state":"running","stage":"evidence","completed_units":7,"total_units":23,"message":"Computed Evidence 2 of 18","occurred_at":"2026-07-16T22:00:00Z","details":{}}}
~~~

上例的 `total_units=23` 来自 18 个 locked Evidence 加 5 个非 Evidence pipeline 单元；通用 runtime 从 frozen scheme 动态计算。只含 1 个 Evidence 的轻量方案使用 `total_units=6`，引擎没有写死 18/23。

`run.preflight` 在创建 run_id 之前完成，不能与 ingestion readiness 混用。`run.start` 的阶段为 snapshot_validation、ingestion、synchronization、evidence、inference、reporting；terminal completed 使用独立状态。`run.cancel` 是协作式请求，在 stage、Evidence 与 artifact 边界检查；结果状态区分 cancelling、cancelled、failed、interrupted 和 completed。terminal notification 只是加速 UI，canonical 状态始终可通过 `run.status`/`run.events.list` 恢复。

## 10. 错误模型

使用 JSON-RPC 标准错误 `-32700/-32600/-32601/-32602/-32603`，domain error 使用 `-32000..-32099`，并在 data 中提供稳定机器码。以下示例表示同一 transaction ID 被用于不同请求：

~~~json
{"jsonrpc":"2.0","id":"req-error-2043","error":{"code":-32002,"message":"transaction ID was already used for a different canonical request","data":{"error_code":"TRANSACTION_REUSE_MISMATCH","message":"transaction ID was already used for a different canonical request","recoverable":false,"trace_id":"trace-error-2043","transaction_id":"550e8400-e29b-41d4-a716-446655440040"}}}
~~~

M6 已实现的机器码组包括：

- protocol：`PROTOCOL_HANDSHAKE_REQUIRED`、`PROTOCOL_VERSION_UNSUPPORTED`；
- project/transaction：`PROJECT_NOT_OPEN`、`PROJECT_ALREADY_OPEN`、`PROJECT_ALREADY_EXISTS`、`PROJECT_FORMAT_UNSUPPORTED`、`PROJECT_RECOVERY_FAILED`、`TRANSACTION_REUSE_MISMATCH`；
- session/artifact：`SESSION_IMPORT_INVALID`、`SESSION_NOT_FOUND`、`MANAGED_SESSION_CHANGED`、`CHECKSUM_MISMATCH`、`ARTIFACT_NOT_FOUND`、`ARTIFACT_INTEGRITY_FAILED`；
- model workspace：`GRAPH_VERSION_CONFLICT`、`LAYOUT_VERSION_CONFLICT`、`DRAFT_NOT_FOUND`、`DRAFT_ALREADY_EXISTS`、`SCHEME_NOT_FOUND`、`SCHEME_VALIDATION_FAILED`、`COMPONENT_NOT_FOUND`、`OPERATOR_NOT_FOUND`；
- run：`RUN_PREFLIGHT_FAILED`、`RUN_NOT_FOUND`、`RUN_ALREADY_TERMINAL`、`RUN_CANCEL_REJECTED`、`RUN_INTERRUPTED`、`INFERENCE_FAILED`；
- fallback：`INTERNAL_ERROR`。

更细的 cycle、CPT migration、extension trust 与前端 remediation 码可以在保持上述兼容组的前提下于 M7 增加；当前客户端不能依赖尚未实现的细粒度码。

`export_pending`、missing evidence 和 `not_applicable` 是结构化 domain/readiness/coverage 状态，不应自动升级为进程异常；preflight 只报告它在执行前可知的输入/适用性，实际 AnchorResult 状态由 M4 产生。

## 11. 并发、版本和幂等

- published component/scheme versions 不允许写。
- 所有 semantic draft mutation 必须携带 expected_graph_version；layout mutation 携带 expected_layout_version。
- 同一 draft 的写入在后端串行化；读请求可并发。
- 所有 mutation、import、apply 和 run.start 都必须携带 transaction_id；同一 transaction_id 重试返回第一次结果，不得重复执行。
- run.start 锁定 scheme version ID、全部 component hashes、bundle hash、session revision 和运行参数 hash。
- v0.1 默认每个 runtime 只运行一个重计算 job；具体上限由 capabilities 报告。
- 前端断开不会改变已发布模型；M6 在 stdin EOF 或 shutdown 时关闭 coordinator，并对活动 run 发出协作式取消。可配置 detach policy 尚未实现。

## 12. 日志、崩溃与恢复

- stdout framing 错误视为 protocol fault，前端保存原始行到受控诊断文件。
- sidecar 非正常退出时，前端显示 exit code、最后 trace ID 和日志位置。
- 未提交 transaction 必须回滚；已原子提交的 draft operation 保留。
- 启动时后端检查未完成 run，并标记 interrupted，不伪造 completed。
- 前端可以重启 sidecar、重新握手并通过 project.open 恢复。
- diagnostics bundle 默认脱敏，不包含原始 VR、gaze、EEG、ECG，除非用户明确选择。

## 13. 安全与隐私

v0.1 是本地单用户系统，但仍要防止误用：

- 不监听网络端口；
- project storage 使用当前 Windows 用户权限；
- participant 使用匿名 ID，身份映射不进入普通项目导出；
- 所有导入、模型发布和结果导出写 audit event；
- safe composite formula 使用白名单表达式，不执行任意代码；
- trusted operator extension 必须由受信安装流程注册；普通 EvidenceRecipe 不需要安装流程；
- 日志实行字段级脱敏和保留期配置。

## 14. 协议验收

M6 engineering gate 已覆盖：

1. Python JSONL framing、4 MiB limit、Unicode、duplicate key、非法 JSON 与标准/domain errors；
2. mandatory hello、协议协商、capabilities、request/notification 区分和单 writer；
3. 真实 subprocess 中的 project/component/operator/scheme/draft/session/run/result/shutdown 闭环，stdout 每行均为 JSON-RPC object；
4. graph/layout atomic operation、optimistic revision、transaction retry 与 audit；
5. managed import 的路径、checksum、修改检测、失败恢复，以及 external source 删除后的独立运行；
6. progress、cancel、failed/interrupted/completed 持久状态与重开恢复；
7. repository 外 wheel 安装后的 sidecar hello/shutdown smoke。

M7 仍需增加 .NET client 对这些已实现合同的兼容测试、前端 error-code 恢复动作测试和 UI 生命周期测试；它们不是 M6 Python backend 已完成事实的前置替代品。
