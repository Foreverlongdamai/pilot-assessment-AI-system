# Runtime Protocol Design

| 字段 | 值 |
|---|---|
| 设计版本 | v0.1 |
| Transport | JSON-RPC 2.0 / JSONL over stdin/stdout |
| 客户端 | Windows WinUI 3 前端 |
| 服务端 | Python Assessment Core sidecar |
| 适用范围 | 本地、单用户、离线评估 |

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

开发人员可以手动启动 backend，并让前端连接其 stdin/stdout host adapter。开发模式允许额外诊断，但协议消息和正式版本必须与安装包模式一致。

### 2.3 生命周期状态

stopped → starting → ready ↔ busy → stopping → stopped

异常状态包括 degraded 和 crashed。degraded 表示后端仍可响应诊断但某项能力不可用；crashed 表示进程已退出。前端不得把进程存在等同于 ready，必须以成功握手和 health response 为准。

## 3. Transport 规则

- stdin：前端发送的 UTF-8 JSON-RPC request/notification，每个消息占一行。
- stdout：后端发送的 UTF-8 JSON-RPC response/notification，每个消息占一行；禁止混入日志。
- stderr：人类可读日志，可由前端收集到诊断面板。
- 文件日志：结构化日志、crash report 和 audit trail。
- 消息必须是单行有效 JSON；字符串内部换行按 JSON 转义。
- request ID 在客户端进程生命周期内唯一；notification 不带 ID。
- 后端可以乱序返回独立请求，因此前端必须按 ID 关联。
- 每个消息设最大尺寸；默认建议 4 MiB，超过时改用文件 artifact。
- 密钥、原始生理信号、完整 gaze 数据和图像不得写入普通日志。

## 4. 握手

前端启动后第一个业务请求必须是 runtime.hello。

~~~json
{"jsonrpc":"2.0","id":"req-0001","method":"runtime.hello","params":{"protocol_version":"1.0","client":{"name":"PilotAssessment.Windows","version":"0.1.0"},"supported_protocols":["1.0"]}}
~~~

成功响应：

~~~json
{"jsonrpc":"2.0","id":"req-0001","result":{"protocol_version":"1.0","runtime_id":"rt-01J...","backend_version":"0.1.0","engine":{"name":"assessment-core","version":"0.1.0"},"capabilities":["session.bundle.v1","graph.edit.v1","cpt.migration.v1","assessment.run.v1"],"state":"ready","trace_id":"trace-hello-01"}}
~~~

若没有共同协议版本，返回 PROTOCOL_VERSION_UNSUPPORTED；前端必须停止发送其他业务命令，并显示兼容性修复说明。

## 5. 通用请求上下文

修改状态的请求必须包含：

- request_id：也可从 JSON-RPC id 派生，用于审计；
- transaction_id：稳定 UUID，兼作 idempotency key；响应丢失后的重试必须复用同一值；
- project_id；
- actor：本地用户或工具标识；
- 与操作对应的 expected_revision_id、expected_graph_version 或 expected_layout_version；
- reason：发布、参数变更和破坏性操作时必填；
- operations 或 command payload。

所有响应应包含 trace_id。改变持久化状态的成功响应还应返回新版本、content hash 与 audit event ID。

## 6. 方法目录

### 6.1 Runtime 与能力

| 方法 | 用途 |
|---|---|
| runtime.hello | 协议握手与能力协商 |
| runtime.status | 健康、状态、活动 job 与资源摘要 |
| runtime.shutdown | 优雅关闭 |
| capabilities.list | 支持的输入、插件、模型和导出能力 |
| schema.get | 获取 manifest、anchor 参数、CPT 或 operation schema |

### 6.2 Project 与 session

| 方法 | 用途 |
|---|---|
| project.create / project.open | 创建或打开托管项目 |
| project.export | 生成可移交、脱敏的项目包 |
| session.inspect | 只读检查外部 bundle，不导入 |
| session.import | 校验后复制/注册到托管项目 |
| session.validate | 重新执行 schema、checksum、同步和质量检查 |
| session.get | 获取 session metadata 与 modality coverage |
| session.artifact.get | 获取可展示 artifact 的受控文件引用 |

### 6.3 Model、graph、anchor 与 CPT

| 方法 | 用途 |
|---|---|
| model.revision.list / model.revision.get | 查询不可变发布版本 |
| model.revision.diff | 比较两个发布版本或 draft 与 base revision |
| model.draft.create / get / discard / publish | 管理可编辑草稿 |
| model.draft.smoke_test | 对 exact draft graph_version 执行发布前固定诊断 |
| graph.snapshot.get | 获取 canonical graph、layout、graph_version 和 layout_version |
| graph.operations.preview | 预览破坏性 batch、影响范围与迁移结果 |
| graph.operations.apply | 原子应用一个或一组 domain operations |
| graph.validate | 图、binding、state space、CPT 与编译检查 |
| graph.undo / graph.redo | 基于后端命令日志撤销或重做 |
| layout.update | 批量提交节点位置；只更新 layout_version |
| node.get / add / update / remove | 查询节点或使用单操作便利入口；修改在内部转换为 graph operation |
| edge.add / remove | 单操作便利入口 |
| binding.get | 查询 evidence node 的 AnchorBinding |
| anchor.parameters.get / validate / update | 读取和修改 anchor 配置 |
| plugin.list / plugin.install | 查询插件；安装仅限受信管理员流程 |
| cpt.get / validate / update | 读取、校验和更新 CPT |
| cpt.migration.preview | 预览增删 parent 或改 state space 后的 CPT 迁移 |
| cpt.generate | 使用已批准 generator 生成候选 CPT |

binding.create/update/remove 不设绕过事务的独立写入口；它们作为 graph.operations.apply 内的 semantic operations，DTO 见 [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) 的 AnchorBinding 小节。

node/edge/anchor.parameters/cpt 的便利写方法同样必须携带 draft_id、expected_graph_version 和 transaction_id；后端把它们转换为单 operation batch。不存在绕过 canonical transaction 的第二套写路径。

### 6.4 Assessment 与结果

| 方法 | 用途 |
|---|---|
| run.preflight | 检查 session、model revision、证据覆盖和适用性 |
| run.start | 启动锁定 published revision_id 的正式评估 |
| run.preview | 对 runnable draft 的 exact graph_version 执行 non-formal 临时预览 |
| run.status | 查询阶段、进度和诊断 |
| run.cancel | 请求协作式取消 |
| result.get | 获取 posterior、coverage、evidence trace 和 provenance |
| result.export | 生成 JSON、CSV 或报告 artifact |
| diagnostics.bundle.export | 导出脱敏支持包 |
| audit.events.list | 查询模型修改、发布、导入与运行审计事件 |

`run.preflight` 返回 `RunPreflightReport`，它与 M2 的 `IngestionReadinessReport` 不是同一 DTO：后者只允许 source data 进入 synchronization，且 `formal_run_authorized` 固定为 false；前者基于 aligned session 与锁定 model revision 决定是否可以创建 AssessmentRun。

## 7. 大数据与路径合同

session.inspect 可以接收用户选择的绝对 bundle 路径。正式 import 后，后端把文件复制或以明确策略注册到受管理 project storage，并生成 session_id。后续运行只使用 session_id。

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
{"jsonrpc":"2.0","id":"req-1042","method":"graph.operations.apply","params":{"project_id":"prj-01","draft_id":"draft-07","expected_graph_version":12,"transaction_id":"550e8400-e29b-41d4-a716-446655440010","actor":"user@example","reason":"Add expert-proposed evidence relationship","operations":[{"op_id":"550e8400-e29b-41d4-a716-446655440011","type":"edge.add","edge":{"edge_id":"550e8400-e29b-41d4-a716-446655440012","source_node_id":"PC.1","target_node_id":"H3"},"cpt_migration":{"strategy":"neutral_replication"}}]}}
~~~

成功时，整个 batch 一次提交：

~~~json
{"jsonrpc":"2.0","id":"req-1042","result":{"transaction_id":"550e8400-e29b-41d4-a716-446655440010","draft_id":"draft-07","previous_graph_version":12,"graph_version":13,"draft_hash":"sha256:...","canonical_patch":{"nodes":[],"edges":[{"edge_id":"550e8400-e29b-41d4-a716-446655440012","source_node_id":"PC.1","target_node_id":"H3"}]},"validation":{"draft_validation_state":"draft_runnable","warnings":[]},"audit_event_id":"audit-992","trace_id":"trace-a1"}}
~~~

任一 operation 失败时全部回滚。版本不匹配返回 GRAPH_VERSION_CONFLICT，同时提供 current_graph_version；前端重新获取 canonical snapshot，不得覆盖后端状态。

只移动节点时提交 layout.update，改变 layout_version，不改变 scientific model content hash。增删节点/边、state、binding、anchor 参数或 CPT 会改变 semantic model hash。

尽管名称为 graph_version，它覆盖整个 semantic draft，包括 graph、state、CPT、anchor binding、anchor parameters 和 profile；这些修改共享一个乐观并发版本。组件可以有 content hash，但 v0.1 不允许用独立 parameter version 绕过 graph_version。

### 8.1 Layout update

拖动期间前端只做本地预览，在 drag end 时批量提交：

~~~json
{"jsonrpc":"2.0","id":"req-layout-12","method":"layout.update","params":{"project_id":"prj-01","draft_id":"draft-07","expected_layout_version":8,"transaction_id":"550e8400-e29b-41d4-a716-446655440020","actor":"user@example","positions":[{"node_id":"O1","x":680.0,"y":120.0},{"node_id":"TCP.1","x":420.0,"y":180.0}]}}
~~~

~~~json
{"jsonrpc":"2.0","id":"req-layout-12","result":{"transaction_id":"550e8400-e29b-41d4-a716-446655440020","draft_id":"draft-07","previous_layout_version":8,"layout_version":9,"layout_hash":"sha256:...","graph_version":13,"audit_event_id":"audit-layout-12","trace_id":"trace-layout-12"}}
~~~

layout.update 不改变 graph_version 或 semantic hash。LAYOUT_VERSION_CONFLICT 只要求刷新或明确重新应用位置，不阻断科学模型编辑。

## 9. 长任务、进度和取消

run.start 硬性要求 published revision_id，并生成正式可追溯 AssessmentResult。run.preview 要求 draft_id + graph_version，结果标记 non_formal、不得进入正式 result export。两者成功后均立即返回 run_id，不等待计算结束；进度通过 notification：

~~~json
{"jsonrpc":"2.0","method":"run.progress","params":{"run_id":"run-88","stage":"anchors","completed":7,"total":18,"percent":38.9,"message":"Computed O7 Control Reversal Rate"}}
~~~

`run.preflight` 在创建 run_id 之前完成，若未来异步化，其 stage 名固定为 `run_preflight`，不能与 ingestion readiness 混用。run.start/run.preview 成功后的阶段至少包括 snapshot_validation、ingestion、synchronization、anchors、evidence、inference、reporting。run.cancel 是请求，不保证瞬时停止；结果状态必须区分 cancelling、cancelled、failed 和 completed。完成或失败后，后端发送 run.completed 或 run.failed notification，同时状态仍可通过 run.status 恢复。

## 10. 错误模型

使用 JSON-RPC error，并在 data 中提供稳定机器码。以下独立示例表示尝试新增 H3 → SM.2，而默认图已有 SM.2 → H3：

~~~json
{"jsonrpc":"2.0","id":"req-error-2043","error":{"code":-32020,"message":"Graph operation rejected","data":{"error_code":"GRAPH_CYCLE_DETECTED","transaction_id":"550e8400-e29b-41d4-a716-446655440040","failed_operation_index":0,"severity":"error","recoverable":true,"path":"operations[0]","node_id":"SM.2","remediation":"Remove the edge or reverse it without creating a cycle.","trace_id":"trace-error-2043","diagnostics":{"cycle":["SM.2","H3","SM.2"]}}}}
~~~

最低覆盖：

- PROTOCOL_VERSION_UNSUPPORTED；
- INVALID_MANIFEST、SCHEMA_INCOMPATIBLE、CHECKSUM_MISMATCH；
- STREAM_MISSING、STREAM_INVALID、TIME_ORDER_INVALID、SYNC_QUALITY_INSUFFICIENT；
- PHASE_REQUIRED、EVENT_REQUIRED、ANCHOR_UNAVAILABLE；
- ANCHOR_BINDING_INVALID、PLUGIN_NOT_TRUSTED；
- GRAPH_VERSION_CONFLICT、GRAPH_CYCLE_DETECTED、DUPLICATE_ID、INVALID_EDGE_TYPE；
- CPT_DIMENSION_INVALID、CPT_ROW_SUM_INVALID、CPT_MIGRATION_REQUIRED、CPT_SIZE_LIMIT_EXCEEDED；
- LAYOUT_VERSION_CONFLICT；
- MODEL_REVISION_NOT_FOUND、MODEL_NOT_PUBLISHED；
- EVIDENCE_COVERAGE_INSUFFICIENT、INFERENCE_FAILED；
- RUN_NOT_FOUND、RUN_ALREADY_TERMINAL、CANCEL_FAILED；
- INTERNAL_ERROR、SIDECAR_DEGRADED。

export_pending、missing evidence 和 not_applicable 通常是 preflight/coverage 状态，不应自动升级为进程异常。

## 11. 并发、版本和幂等

- published revision 不允许写。
- 所有 semantic draft mutation 必须携带 expected_graph_version；layout mutation 携带 expected_layout_version。
- 同一 draft 的写入在后端串行化；读请求可并发。
- 所有 mutation、import、publish 和 run.start 都必须携带 transaction_id；同一 transaction_id 重试返回第一次结果，不得重复执行。
- run.start 锁定 model revision ID、bundle hash、session revision 和参数 hash。
- v0.1 默认每个 runtime 只运行一个重计算 job；具体上限由 capabilities 报告。
- 前端断开不会改变已发布模型；活动 run 是否继续由启动参数 detach_policy 决定并记录。

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
- AnchorPlugin 必须由受信安装流程注册；
- 日志实行字段级脱敏和保留期配置。

## 14. 协议验收

发布前至少通过：

1. Python server 与 .NET client 的 hello/版本协商 contract test；
2. 多请求乱序、消息大小、Unicode 与非法 JSON 测试；
3. progress、cancel、崩溃、重启和 interrupted run 测试；
4. graph operation 原子回滚与 version conflict 测试；
5. import 路径穿越、checksum 和修改检测测试；
6. error_code 到前端恢复动作的映射测试；
7. stdout 无日志污染测试。
