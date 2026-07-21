+++
document_id = "PAS-PROTOCOL-CSHARP-001"
language = "zh-CN"
title = "Sidecar 协议与 C# 开发手册"
short_title = "Sidecar 与 C# 开发"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "说明本地 JSON-RPC sidecar 生命周期、typed protocol 规则与 WinUI/C# 维护边界。"
prerequisites = ["掌握 C# 与 .NET", "了解 JSON-RPC", "理解 Python domain boundary"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-CORE-001", "PAS-RELEASE-001", "PAS-PORTABILITY-001"]
support = "记录 UI action、protocol/method version、transaction ID、trace ID、stderr diagnostic 与可复现状态。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Sidecar 协议与 C# 开发手册

## 1. 进程拓扑

WinUI desktop application 自动启动且只启动一个 private Python sidecar child process：

```text
WinUI/C# process
    stdin  -> JSON-RPC 2.0 request，每行一个 JSON object
    stdout <- JSON-RPC 2.0 response/event，每行一个 JSON object
    stderr <- 仅 backend logs 与 diagnostics
Python sidecar process
```

产品不监听 TCP/HTTP port，也没有需要单独启动的 SQLite service。Stdout 是协议通道，普通日志写到 stdout 属于 framing defect。大型图片、视频、时序文件与 artifacts 留在磁盘，协议只传 stable project/Session/run/artifact identities 和紧凑 DTOs。

## 2. 启动 handshake 与关闭

Desktop 根据 product root 解析 private runtime 与 active source，使用 isolated Python invocation 启动 sidecar，并在启用后端操作前完成 version/capability handshake。

Handshake 识别 protocol versions、product/backend identity、method catalog、schemas 与 capabilities。不能只根据 frontend build number 猜后端支持。正常关闭时，先处理 pending model-edit choice，再关闭协议和 child process。Crash/timeout 应明确出现在 Diagnostics，不能静默启动第二个 writer 同时访问相同 roots。

## 3. JSON-RPC framing 与 errors

每个物理行是一个 UTF-8 JSON object，并遵循 JSON-RPC 2.0。Request 包含 ID、method 和 object `params`；notification 无 request ID；response 对 matching ID 只含一个 `result` 或 `error`。

Domain failures 使用稳定 machine-readable error codes，再由 UI 本地化显示。Traceback 与详细 backend context 进入 stderr/diagnostic payload，协议行之间不能插入任意 log text。Oversize/malformed message 应确定性拒绝，并在安全时继续处理下一 valid frame。

UI 不能解析英文错误句子来决定行为，应把 typed status/error fields 映射到 localized resources。

## 4. Mutation contract

每个外部 write 都携带：

- 用于 idempotent retry 的 unique transaction ID；
- 目标 aggregate/edit session 的 expected optimistic revision；
- typed intent payload；
- audit 所需 caller/protocol metadata。

Python domain service 只验证和 commit 一次。重试相同 transaction 返回 canonical prior outcome；用同一 ID 发送不同 intent 会被拒绝。Revision conflict 要求 reload/rebase，不使用 last-writer-wins。

协议只传递 edit intent，不复制 Evidence recipe、activation closure、DAG validation、CPT semantics 或 BN inference 的第二套实现。

## 5. Read 与 run boundaries

Project/system summaries、lists、node details、task schemes、edit-session state、preflight、run status、results、diagnostics 与 provenance 使用紧凑 query methods。Stable IDs 供 selection 使用，但普通 UI cards 只展示简洁 names。

Run methods 请求 backend preflight/start/cancel/recovery。C# client 不建立本地 shadow RunSnapshot，也不靠猜测计算 progress。Polling/reconciliation 服从 durable backend state，以保持 restart/interrupted-run behaviour 一致。

## 6. C# solution map

| Location | 职责 |
|---|---|
| `src/PilotAssessment.Desktop.Core/Contracts/` | typed JSON DTOs 与 source-generation context |
| `src/PilotAssessment.Desktop.Core/State/` | graph projections、drafts、undo/redo-facing state 与 display resolution |
| `src/PilotAssessment.Desktop.Core/ViewModels/` | UI-independent view models/projections |
| `src/PilotAssessment.Desktop/Services/Backend/` | sidecar process/client composition 与 RPC mapping |
| `src/PilotAssessment.Desktop/ViewModels/` | WinUI screen/editor behaviour |
| `src/PilotAssessment.Desktop/Controls/` | graph、editors、task-scheme/sidebar components |
| `src/PilotAssessment.Desktop/Strings/` | 只保存 localized UI resources |
| `tests/PilotAssessment.Desktop.UnitTests/` | 快速 C# behaviour/serialization tests |
| `tests/PilotAssessment.Desktop.ContractTests/` | real-sidecar protocol compatibility tests |

Model names/descriptions 是 canonical English data；UI labels、prompts 与 validation messages 才是 localized resources。切换语言绝不能重写 model content。

## 7. 新增或修改 protocol method

1. Serialized meaning 变化时定义或升级 Python contract 与 JSON Schema；
2. 在不依赖 sidecar 的情况下实现 domain service operation；
3. 在 `sidecar/methods.py` 暴露 thin method，并注册到 negotiated method catalog；
4. 增加 matching C# records、明确 JSON property names 和 source-generation registration；
5. 在 backend client 增加一个 method，用 typed domain errors 映射，不能解析 prose；
6. 增加 focused Python dispatcher/method tests、C# serialization tests 与 real-sidecar contract test；
7. 更新 Diagnostics/capability documentation。

不能为了隐藏 backend drift 把 C# DTO 改成任意 permissive object。应主动 version，并在 historical payload 需要阅读时保留 explicit legacy DTOs。

## 8. 从源码仓库构建和测试

常用命令：

```powershell
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj `
  -c Debug -p:Platform=x64 --nologo

dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj `
  -c Debug --nologo

dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj `
  -c Debug -p:Platform=x64 --nologo
```

Portable release 对最终用户是 self-contained；Visual Studio 与 SDK 只是 build-machine requirements。XAML/process lifecycle 有实质修改后应执行一次 visible smoke，并正常关闭，确保无 sidecar/SQLite lock 残留。

## 9. UI interaction rules

- 五层图是 backend complete nodes、typed edges 与 scheme activation 的 projection；
- node editors 生成 staged commands，不直接写 database files；
- 可同时打开多个 floating editors，但“保存全部”只有一次 system-level commit；
- `Ctrl+Z`/redo 操作 staged command history；
- 启用 child 请求 backend ancestor closure，停用 parent 先请求 impact preview；
- copy 创建新 node identity，默认保留 original fixed parents；
- long IDs/hashes 只在 Diagnostics/provenance 展示。

## 10. Security 与 privacy boundary

不能仅为调试方便增加 TCP。UI 传入 execution 的 filesystem path 必须由 backend 检查 containment。Logs 不能回显 Session rows、gaze、physiology 或 images。Project/system roots 要明确，并在 whole-directory copy 前关闭 handles。

## 11. Developer 检查单

- [ ] 一个 sidecar child、零 listeners；
- [ ] stdout 只含 protocol JSON；
- [ ] request/response DTOs typed/versioned；
- [ ] writes 携带 transaction ID 与 expected revision；
- [ ] C# 只发送 intent，不复制 domain computation；
- [ ] large data 留在 managed files；
- [ ] language switch 只影响 resources，不影响 canonical content；
- [ ] unit 与 real-sidecar contract tests 覆盖 changed method；
- [ ] visible desktop smoke 关闭后无 process/lock 残留。
