# eVTOL 飞行员训练评估系统：产品总览

**文档状态：** 产品 v0 设计基线（M4 完整书面规格、轻量工作流验证、Task 3/7/8 定向修订与 replacement plan 均已获明确或授权默认批准；D-026–D-030 已接受；原实施计划已被取代；replacement Task 0–22 已完成，M4-A/M4-B framework 与 M4-C stage gate、O1/O2/O3/O4/O5/O6/O7/O8/O9 production plugins、`movement-events-v1` provider 已实现，O1–O9 capability 均为 `available`；M4-D 已开始，下一步为 Task 23 O10；18/18 specified、9/18 production plugins 已实现；M4 整体尚未 engineering verified，`formal_run_authorized=false`，无科学有效性声明）
**日期：** 2026-07-13
**适用目录：** `pilot_assessment_system/`

## 1. 产品目的

本产品用于对 eVTOL／飞行模拟器训练 session 进行离线、可解释、可复现的飞行员能力评估。系统接收飞行状态、操纵输入、第一视角 VR 画面、眼动、EEG 和 ECG 等多模态数据，通过确定性 anchor 计算、证据离散化和贝叶斯网络推理，输出四项能力的后验分布：

- Task Control Proficiency（TCP，任务控制熟练度）
- Procedural Compliance（PC，程序符合度）
- Situational Monitoring（SM，态势监控）
- Operational Composure（OC，运行沉着度）

每个输出都必须能够追溯到使用了哪些 session 数据、anchor 算法、阈值、模型版本和 CPT。产品不是一个只给出单一分数的黑盒模型，而是一套能够被研究人员、教员和领域专家检查、解释和修订的评估工具。

## 2. 产品原则

### 2.1 离线优先

产品 v0 面向实验结束后的 session 导入和分析，不依赖云服务或持续网络连接。大型视频、图像和生理信号保留在本机，Windows 前端通过本地 sidecar 调用 Python Assessment Core。

### 2.2 可解释优先

完整计算链为：

`session bundle → 数据验证与时间同步 → anchor 计算 → evidence rating → BN inference → competency posterior + evidence trace`

任何 posterior 都必须关联：

- 输入 stream 和有效时间窗口；
- anchor 值、单位、`calculation_status`、raw metrics、`classification_override` 和 evidence state；
- BN graph、CPT 和 anchor 参数的模型 revision；
- 缺失或尚未导出的模态；
- 软件版本、插件版本和配置 hash。

### 2.3 专家可配置

领域专家可以在 Windows 前端中：

- 查看和编辑 BN 图拓扑；
- 查看节点名称、类型、状态空间、父子关系和支持的数据接口；
- 编辑 CPT；
- 编辑 anchor 阈值和允许公开配置的算法参数；
- 保存为新的 model revision；
- 比较、回滚和导出 model revision。

安装包中的默认模型始终只读。所有编辑发生在 project 的运行时副本中，并经过后端结构、概率和兼容性验证。

### 2.4 数据与模型分离

Session bundle 是实验事实；model bundle 是解释这些事实的评估模型。修改模型不能改变原始 session，重新运行也必须保留此前结果和其所绑定的 model revision。

### 2.5 软件验证与科学验证分离

“软件正确执行公式和推理”不等于“评估结论已经被科学验证”。产品界面和导出结果必须分别显示这两种状态，不得把通过单元测试描述为评估有效性已经成立。

### 2.6 差表现是证据，不是无效数据

M1–M3 负责文件完整性、schema、类型和时间合同检查，并可以记录 coverage、gap、clock residual 与 artifact 等技术诊断。M4 假定进入本层的 aligned data 已满足这些接口合同；这些技术诊断不得作为 M4 evidence admission gate，也不得改变 D/A/U likelihood。

只要锚点所需输入存在、任务适用、公式配置完整且依赖可用，M4 就必须按规则计算。轨迹偏差大、控制剧烈、生理数值极端、未响应、未注视或未形成稳定悬停通常产生 `computed + Unacceptable`；这是有效负面 evidence，raw availability 为 1。M4 使用 `AnchorResult v0.2`，不生成 `invalid_quality`。输入缺失、任务不适用、配置不足、依赖缺失或提取器错误分别使用明确的非表现状态，不能与 Unacceptable 混为一谈。

## 3. v0 非目标

产品 v0 不包含：

- 实时飞行监控或机载部署；
- 云端数据上传、多人协作服务或远程账户系统；
- 自动训练黑盒模型；
- 根据单个 session 自动学习 CPT；
- 用缺失模态的先验分布生成看似确定的能力诊断；
- 将实验评估结果直接用于执照、医疗或适航认证决定；
- 在未建立新 model revision 的情况下直接覆盖模型默认文件。

实时流式接入、远程 API、自动参数学习和更复杂的动态贝叶斯网络可作为后续扩展，但不进入 v0 的验收范围。

## 4. 用户角色

| 角色 | 主要任务 | 权限边界 |
|---|---|---|
| 评估员／教员 | 导入 session、检查数据、运行评估、解释 posterior 和证据链 | 可运行和导出；是否可编辑模型由 project 权限决定 |
| 领域专家 | 审查 anchor、能力结构、BN 拓扑和 CPT | 可创建 model revision；不能覆盖安装默认模型 |
| 数据研究人员 | 检查 stream、同步技术诊断、phase/event annotation 和数据 coverage | 可修正 session metadata；原始数据保持只读 |
| 系统开发者 | 维护插件、协议、数据适配器和软件测试 | 代码变更不自动成为科学模型批准 |
| 受训飞行员 | 查看经评估员批准的结果和解释 | 默认不修改模型或原始数据 |

产品 v0 可以先采用本机单用户模式，但所有 model edit 和 assessment run 仍必须记录逻辑角色、时间和理由，为后续权限体系保留审计基础。

## 5. 完整工作流

1. 用户从 Windows 应用创建或打开 assessment project。
2. WinUI 应用启动随安装包部署的 Python sidecar，并完成协议、版本和能力握手。
3. 用户选择 session bundle 目录或压缩包。
4. 后端读取 manifest，并依次执行 M1 integrity 与 M2 content/adapter 检查，显示每个 stream 的 `present`、`export_pending`、`missing`、`invalid` 或 `not_applicable` 状态。
5. M2 输出 `IngestionReadinessReport`；它只决定 source artifact 能否进入同步，始终 `formal_run_authorized=false`。
6. M3 用同一文件 snapshot 构造 `SynchronizationInput`，按 native rate 映射原始行并追加 aligned time/flags，不插值或重采样；输出内部 `AlignedSession` 与公共 `SynchronizationReport`。
7. 用户在 Session Explorer 中同步查看 X/U 曲线、随头动的第一视角 VR scene、gaze/AOI、驾驶员图像、EEG 和 ECG。
8. 用户选择一个已发布的 model revision；如需修改，则从该 revision 创建 draft。
9. 领域专家在 BN Graph 和 Node Inspector 中编辑 draft 的图拓扑、CPT 或 anchor 参数。每次操作更新 draft 的 graph_version；验证并 publish 后才产生新的不可变 model revision。
10. 用户为正式运行选择一个 published revision。后端锁定 revision，解析 model-bundle reference，并由 Run Preflight 检查 frozen inputs、任务前提、execution plan、插件和版本兼容性；只有 `RunPreflightReport` 可以决定是否创建 AssessmentRun。preflight 不按飞行表现或原始信号数值过滤 evidence。
11. 用户启动评估。sidecar 按该 published revision 建立 run snapshot；M4 生成 `AnchorResult v0.2`，M5 再执行 BN observation、coverage 与 inference。已经建立的同步结果按 fingerprint 绑定到该 snapshot。
12. Windows 前端显示运行进度，并允许取消。
13. 结果页显示四项 competency posterior、可评估状态、evidence availability coverage、anchor trace、缺失证据和限制说明。
14. 只有达到该 competency 的最低 evidence availability 要求时，系统才生成 weak-skill diagnosis；`computed` 的 D、A、U 都计为已提供 evidence，其中 U 是负面观测而不是低质量或缺失数据。
15. 用户导出结果、模型 revision、同步报告和 provenance；此前 run 保持可复现。

## 6. 总体架构

    ┌─────────────────────────────────────────────────────────┐
    │ Windows WinUI Desktop                                  │
    │ Project / Import / Session Explorer / BN Editor / Run  │
    │ Results / Diagnostics                                  │
    └───────────────────────┬─────────────────────────────────┘
                            │ JSON-RPC 2.0 over stdio
                            │ 大型数据仅传本机路径与 checksum
    ┌───────────────────────▼─────────────────────────────────┐
    │ Python Assessment Core Sidecar                         │
    │ contracts → ingestion → synchronization → anchors      │
    │ → evidence → model_bundle → inference → reporting      │
    └──────────────┬──────────────────────┬───────────────────┘
                   │                      │
       ┌───────────▼──────────┐  ┌────────▼──────────────────┐
       │ Session Bundles       │  │ Project Runtime Store     │
       │ 原始/派生多模态数据   │  │ model revisions / runs    │
       │ manifest + checksums  │  │ audit / results / logs    │
       └──────────────────────┘  └───────────────────────────┘

### 6.1 Windows WinUI

WinUI 负责交互、可视化和 sidecar 生命周期，不复制 Assessment Core 的业务规则。前端不直接编辑 YAML/JSON 模型文件；所有模型读取和修改通过后端协议完成。

### 6.2 Python Assessment Core

Assessment Core 是可独立测试的 Python package。其纯 Python API 可用于测试和研究 notebook，runtime adapter 将相同能力暴露给 Windows 应用。同步层的 v0.1 边界是 native-rate alignment：保留 source rows 并生成 `*-aligned-v0.1` 视图；anchor-specific interpolation、resampling 和 analysis/window grid 属于后续 AnchorPlugin/model revision。

### 6.3 JSON-RPC stdio sidecar

WinUI 通过重定向 stdin/stdout 启动和控制 sidecar：

- 不开放本地端口，不受防火墙端口配置影响；
- stdout 只传一行一个 JSON-RPC 消息；
- 日志写 stderr 或日志文件；
- 视频、图像和时序信号通过 session bundle 路径读取，不嵌入 JSON；
- 长任务通过 progress notification 汇报；
- UI 关闭时负责请求 sidecar 正常退出，异常时保存诊断。

Assessment Core 保留 transport-neutral command service，未来可以增加 localhost HTTP adapter，但不改变核心计算接口。

## 7. 前端产品区域

| 区域 | 核心职责 |
|---|---|
| Project Launcher | project、model revision、最近 session/run |
| Session Import | bundle 导入、接口发现、stream 状态和修复建议 |
| Session Explorer | 多模态同步播放、phase/event 和上游技术诊断检查 |
| BN Graph Editor | 查看并编辑 draft 的节点、边和层级；发布后生成新 revision |
| Node Inspector | 编辑 anchor 参数、状态空间和 CPT |
| Assessment Run | preflight、revision 锁定、进度和取消 |
| Results | posterior、evidence availability coverage、evidence trace、诊断和限制 |
| Diagnostics | backend/model/protocol 版本、日志和支持包 |

## 8. 模态边界

正式 session contract 包含：

- X(t)：飞行状态；
- U(t)：飞行员操纵输入；
- I(t)：随飞行员头部转动而变化的第一视角 VR scene；
- G(t)：定义在动态 I(t) 画面上的 gaze ray、gaze point、fixation/stare 和 AOI；
- P(t)：生理信号族的概念接口；manifest 中拆成 EEG(t)、ECG(t) 等独立 stream；
- EEG(t)：脑电原始或经声明处理的通道数据；
- ECG(t)：心电原始或经声明处理的通道数据；
- pilot_camera(t)：可选的飞行员脸部／上半身图像，不等同于 I(t)。

当前视觉、gaze、EEG 和 ECG 已在实验中采集但尚未导出，应使用 `export_pending` 表达，而不是从产品合同中删除。

## 9. 模型与结果状态

### 9.1 模型状态字段

模型不用一个 status 混装编辑、生命周期和科学证据：

- `draft_validation_state`：draft_incomplete、draft_invalid、draft_runnable 或 draft_publishable；
- `revision_lifecycle`：published、archived 或 superseded；只适用于不可变 revision；
- `scientific_validation_status`：engineering_default、expert_reviewed、calibrated、internally_validated、externally_validated 或 not_supported；
- `permitted_use`：由项目治理单独声明，例如 research_only；它不是科学有效性等级。

### 9.2 结果可评估状态

- `assessable`：满足该 competency 的最低 evidence availability 要求；
- `partial`：可显示有限 posterior，但必须同时显示限制；
- `insufficient`：存在少量证据但低于最低解释门，不得生成 weak-skill diagnosis；
- `prior_only`：适用分母大于 0，但没有任何 directional session observation（例如全部适用 evidence 均未计算），仅能看到模型先验，不得诊断；
- `blocked`：fatal preflight/model error 阻止推理，因此不产生 posterior result。

## 10. 两类验证状态

| 状态 | 回答的问题 | 最低证据 |
|---|---|---|
| Software Verification | 软件是否正确加载、同步、计算、推理和保存 | schema tests、synthetic golden tests、协议 tests、E2E tests |
| Scientific Validation | posterior 和诊断是否反映真实训练能力 | 多 pilot/session、专家标签、TLX/HQR 或其他外部标准、校准与重复性 |

每个导出结果应分别记录 `software_verification_status` 和 `scientific_validation_status`。

## 11. 产品 v0 完成标准

v0 完成必须同时满足：

1. WinUI 可启动 sidecar 并完成版本握手。
2. 可导入符合规范的 session bundle，并正确显示所有正式模态及其状态。
3. 可验证时间同步、phase/event 和 baseline。
4. 可通过插件计算当前 model bundle 声明的 anchor。
5. 可查看和编辑 BN 拓扑、CPT 与 anchor 参数，并生成可回滚 revision。
6. 可运行固定 revision 的离线推理并输出可追溯结果。
7. 证据不足时不会产生虚假确定性评分或诊断。
8. 软件验证状态与科学验证状态在 UI 和导出文件中明确分开。

## 12. 配套设计文档

- [Assessment Core 设计](./02_ASSESSMENT_CORE_DESIGN.md)
- [Session Bundle 规范](./03_SESSION_BUNDLE_SPEC.md)
- [M3 Native-Rate Time Synchronization 规格](./specs/2026-07-12-m3-native-time-synchronization-design.md)
- [M3 实施计划](./plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
- [M4 Anchor Calculation and Evidence Availability 规格](./specs/2026-07-13-m4-anchor-evidence-availability-design.md)（已批准；18/18 已设计、9/18 production plugins 已实现，M4-C stage gate 已关闭、M4-D 正在执行）
- [M4 Anchor Calculation and Evidence Availability 原实施计划](./plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)（历史上已批准，现已被取代且不得执行）
- [M4 Lightweight Workflow Validation Amendment](./specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)（已批准）
- [M4 Task 3 Reference Candidate Binding Amendment](./specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)（已于 2026-07-13 批准；D-028）
- [M4 Task 7 Catalog/Resource Identity Amendment](./specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)（已于 2026-07-13 按授权默认批准；D-029；由提交 `583a1e7` 完成）
- [M4 Task 8 Canonical Fingerprint/Runtime Identity Amendment](./specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)（已于 2026-07-13 按授权默认批准；D-030；canonical identity/runtime code 已完成）
- [M4 Anchor Calculation and Evidence Availability Replacement Implementation Plan](./plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（已于 2026-07-13 批准并修订；Task 0–22 已完成，M4-D 已开始，下一步为 Task 23 O10）
- [M4 Autonomous Review Ledger](./reviews/2026-07-13-autonomous-review-ledger.md)（保存默认批准期间的独立复核证据与工具边界）
- 既有后端方向稿：`docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md`
