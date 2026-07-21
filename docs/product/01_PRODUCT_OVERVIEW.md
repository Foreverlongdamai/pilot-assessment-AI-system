# eVTOL 飞行员训练评估系统：产品总览

**文档状态：** 产品 v0.8 portable expert-designer 基线。M1–M7、M8A 与 M8B-0 已工程验证；M7 用户手工验收、D-055、M8B-1/M8B-2 与 M8C–M8E 尚未完成；starter/synthetic `formal_run_authorized=false`。
**日期：** 2026-07-21
**适用目录：** `pilot_assessment_system/`

> **当前权威：** M7 交互见 [M7 WinUI Expert Designer and Task Activation Workspace Design](./specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md)，模型 ownership 与 project/run 分层见 [M8B System-Owned Model Library and Editable Backend Provenance Design](./specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md)。M5/M6 的 version/draft/publish 和 project-local current-model 文字只作为 migration/replay 基础。本总览中出现的 Hover、18 Anchor、11 sub-skills、4 competencies 与默认公式/CPT 均指 starter template，不限制任务、方案或节点数量。

## 1. 产品目的

本产品首先是一套面向领域专家的 Windows 本地评估模型设计与运行系统。它接收飞行状态、操纵输入、第一视角 VR 画面、眼动、EEG 和 ECG 等多模态 session，让专家用 Evidence Computation Graph 设计 evidence 计算方法，再用可编辑 BN 设计能力推理关系。Starter template 默认输出四项能力后验：

- Task Control Proficiency（TCP，任务控制熟练度）
- Procedural Compliance（PC，程序符合度）
- Situational Monitoring（SM，态势监控）
- Operational Composure（OC，运行沉着度）

每个输出都必须能够追溯到使用了哪些 session 数据、EvidenceRecipe、operator、参数、模型版本和 CPT。产品不是一个只给出单一分数的黑盒模型，也不把当前初始算法当作标准答案；它为研究人员、教员和领域专家提供透明、直接、可执行且易于修改的设计工作台。

## 2. 产品原则

### 2.1 离线优先

产品 v0 面向实验结束后的 session 导入和分析，不依赖云服务或持续网络连接。大型视频、图像和生理信号保留在本机，Windows 前端通过本地 sidecar 调用 Python Assessment Core。

### 2.2 可解释优先

完整计算链为：

`session bundle → 数据验证与时间同步 → EvidenceRecipe → observed evidence → BN posterior inference → competency posterior + evidence trace`

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
- 创建、复制、停用和共享完整 Evidence/BN 节点；
- 复制、切换和编辑并列 TaskSchemes；
- 比较节点定义，并从历史 RunSnapshots 重放结果。

Starter 节点可在 software-copy system model library 中直接编辑，也可先复制为任务专用节点。所有编辑进入 system-owned staged edit session，并在“保存全部”时提交到后端 canonical objects；只经过最小结构、概率和兼容性验证，不需要 Draft/Published/Apply/Publish。

### 2.4 数据与模型分离

Session bundle 是实验事实；global node library 与 TaskScheme 是解释这些事实的评估模型。修改模型不能改变原始 session。每次运行自动冻结 exact session、scheme closure 与完整节点定义为 RunSnapshot，因此重新编辑不会改变此前结果。Model bundle 只是可移植的导入/导出封装。

### 2.5 软件验证与科学验证分离

“软件正确执行公式和推理”不等于“评估结论已经被科学验证”。产品界面和导出结果必须分别显示这两种状态，不得把通过单元测试描述为评估有效性已经成立。

### 2.6 差表现是证据，不是无效数据

M1–M3 负责文件完整性、schema、类型和时间合同检查，并可以记录 coverage、gap、clock residual 与 artifact 等技术诊断。M4 假定进入本层的 aligned data 已满足这些接口合同；这些技术诊断不得作为 M4 evidence admission gate，也不得改变 D/A/U likelihood。

只要锚点所需输入存在、任务适用、公式配置完整且依赖可用，M4 就必须按规则计算。轨迹偏差大、控制剧烈、生理数值极端、未响应、未注视或未形成稳定悬停通常产生 `computed + Unacceptable`；这是有效负面 evidence，raw availability 为 1。M4 使用 `AnchorResult v0.2`，不生成 `invalid_quality`。输入缺失、任务不适用、配置不足、依赖缺失或提取器错误分别使用明确的非表现状态，不能与 Unacceptable 混为一谈。

### 2.7 完整节点、任务激活与概率语义分离

每个可见 Evidence/BN `ModelNode` 在全局节点库中拥有一个当前完整定义。若不同任务需要不同 recipe、parents、states 或 CPT，专家复制或新建另一个节点；同一节点只有在完整定义相同时才由多个任务共享。`TaskScheme` 只保存 explicit active selection、computed parent closure、outputs、task bindings 与 layout。切换任务只改变亮暗和执行集合，不在同一圆中切换内部版本。

高层工作区有 Raw Input、Evidence、BN Node 三类节点和两类边：`Raw/task source -> Evidence` 是 data/extraction dependency，Raw Input 不属于 BN；probabilistic edge 才定义 `P(child | parents)`。Hover starter 的 canonical BN 使用 `Competency -> Sub-skill -> Evidence`，而实际评估观察 Evidence 后计算能力 posterior。前端可以显示只读 inference overlay，但不能为显示目的反转 canonical BN topology。

## 3. v0 非目标

产品 v0 不包含：

- 实时飞行监控或机载部署；
- 云端数据上传、多人协作服务或远程账户系统；
- 自动训练黑盒模型；
- 根据单个 session 自动学习 CPT；
- 用缺失模态的先验分布生成看似确定的能力诊断；
- 将实验评估结果直接用于执照、医疗或适航认证决定；
- 删除或改写历史 RunSnapshot 和旧 run 结果。

实时流式接入、远程 API、自动参数学习和更复杂的动态贝叶斯网络可作为后续扩展，但不进入 v0 的验收范围。

## 4. 用户角色

| 角色 | 主要任务 | 权限边界 |
|---|---|---|
| 评估员／教员 | 导入 session、检查数据、运行评估、解释 posterior 和证据链 | 可运行和导出；模型编辑作用于当前软件副本的 system model library |
| 领域专家 | 审查 Evidence、能力结构、BN 拓扑和 CPT | 可直接编辑/复制 current nodes 与 TaskSchemes；不能改写历史 RunSnapshot |
| 数据研究人员 | 检查 stream、同步技术诊断、phase/event annotation 和数据 coverage | 可修正 session metadata；原始数据保持只读 |
| 系统开发者 | 维护插件、协议、数据适配器和软件测试 | 代码变更不自动成为科学模型批准 |
| 受训飞行员 | 查看经评估员批准的结果和解释 | 默认不修改模型或原始数据 |

产品 v0 可以先采用本机单用户模式。系统自动记录 model edit/run 的逻辑角色与时间；修改说明可选，不得因为用户未填写理由而阻止 autosave 或 run。

## 5. 完整工作流

1. 用户启动 Windows 应用；WinUI 自动启动随安装包部署的 Python sidecar，打开当前软件副本的 system model library，并完成协议、版本和能力握手。
2. 用户可以不打开 project 直接进入 Model Studio；需要导入 Session 或运行评估时，再创建或打开 assessment project。
3. 用户选择 session bundle 目录或压缩包。
4. 后端读取 manifest，并依次执行 M1 integrity 与 M2 content/adapter 检查，显示每个 stream 的 `present`、`export_pending`、`missing`、`invalid` 或 `not_applicable` 状态。
5. M2 输出 `IngestionReadinessReport`；它只决定 source artifact 能否进入同步，始终 `formal_run_authorized=false`。
6. M3 用同一文件 snapshot 构造 `SynchronizationInput`，按 native rate 映射原始行并追加 aligned time/flags，不插值或重采样；输出内部 `AlignedSession` 与公共 `SynchronizationReport`。
7. 用户在 Session Explorer 中同步查看 X/U 曲线、随头动的第一视角 VR scene、gaze/AOI、驾驶员图像、EEG 和 ECG。
8. 用户在左侧选择 Base/Hover/Straight 等 current `TaskScheme`，或复制现有方案创建新的并列方案。
9. 领域专家在 active/dim 全局画布中启用、停用、创建、复制或编辑 software-copy system library 中的完整 Evidence/BN nodes；修改先进入持久 staged edit session，并在关闭前由用户统一保存或放弃。启用 child 自动补齐 fixed parents；停用有 active downstream 的 parent 时先确认级联影响。
10. 用户点击节点打开可同时并排的独立浮动窗口，编辑 extraction bindings、recipe operators/参数/scorer、probabilistic BN parents、states 和 CPT；用户可随时对当前 session preview。
11. 用户直接从当前技术可执行的 TaskScheme 启动评估。Run Preflight 检查 managed inputs、任务前提、active closure、compiled recipe/BN plan 与 operator/engine compatibility；通过后 sidecar 自动冻结 immutable RunSnapshot。它不按飞行表现或原始信号数值过滤 evidence。
12. Windows 前端显示运行进度，并允许取消。
13. 结果页显示四项 competency posterior、可评估状态、evidence availability coverage、anchor trace、缺失证据和限制说明。
14. 只有达到该 competency 的最低 evidence availability 要求时，系统才生成 weak-skill diagnosis；`computed` 的 D、A、U 都计为已提供 evidence，其中 U 是负面观测而不是低质量或缺失数据。
15. 用户导出结果、RunSnapshot、同步报告和 provenance；此前 run 保持可复现。

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
       │ System Model Store    │  │ Project Runtime Store     │
       │ ModelNodes/TaskSchemes│  │ Session/RunSnapshot       │
       │ CPT/edit session      │  │ result/artifacts          │
       └───────────┬──────────┘  └────────▲──────────────────┘
                   │ exact clean closure  │ immutable copy/run
                   └──────────────────────┘

Session Bundle 作为外部输入，经受管导入复制到 Project Runtime Store；它不进入 System Model Store。不同 project 共享同一软件副本的 current system model，但各自保留自己的 Session、运行和不可变历史。

### 6.1 Windows WinUI

WinUI 负责交互、可视化和 sidecar 生命周期，不复制 Assessment Core 的业务规则。前端不直接编辑 YAML/JSON 模型文件；所有模型读取和修改通过后端协议完成。

### 6.2 Python Assessment Core

Assessment Core 是可独立测试的 Python package。其纯 Python API 可用于测试和研究 notebook，runtime adapter 将相同能力暴露给 Windows 应用。同步层的 v0.1 边界是 native-rate alignment：保留 source rows 并生成 `*-aligned-v0.1` 视图；Anchor-specific interpolation、resampling 和 analysis/window grid 只在 EvidenceRecipe 显式选择相应 operators 时建立。

### 6.3 JSON-RPC stdio sidecar

WinUI 通过重定向 stdin/stdout 启动和控制 sidecar：

- 不开放本地端口，不受防火墙端口配置影响；
- stdout 只传一行一个 JSON-RPC 消息；
- 日志写 stderr 或日志文件；
- 视频、图像和时序信号通过 session bundle 路径读取，不嵌入 JSON；
- 长任务通过 progress notification 汇报；
- UI 关闭时负责请求 sidecar 正常退出，异常时保存诊断。

Assessment Core 保留 transport-neutral command service，未来可以增加 localhost HTTP adapter，但不改变核心计算接口。

### 6.4 Global Node Library and TaskSchemes

每套软件副本的 `system/model-library.sqlite3` 保存完整 Raw Input/Evidence/BN ModelNodes，以及 current TaskSchemes 的 explicit selection、computed closure、task bindings、CPT 和 layout；`system/staging/model-edit/` 保存跨 project 生命周期的 staged edit session。每次 run 从 clean system state 锁定 exact closure，并把不可变执行副本和 RunSnapshot 写入目标 project。Project database 不再 seed 或持有可继续编辑的 current model；legacy project-local 模型只读保留并可按确定性、幂等、无覆盖规则导入 system store。

## 7. 前端产品区域

| 区域 | 核心职责 |
|---|---|
| Project Launcher | 创建/打开只承载 Session、run、result 和 artifacts 的 project |
| Session Import | bundle 导入、接口发现、stream 状态和修复建议 |
| Session Explorer | 多模态同步播放、phase/event 和上游技术诊断检查 |
| Model Library | 浏览完整 Evidence/BN nodes、lineage、tags、archive 和被哪些 schemes 使用 |
| Task Scheme Sidebar | 切换/复制 current schemes，查看 active selection 与 parent closure |
| Integrated Graph Editor | 查看三类节点、两类边与 active/dim 全局图；复制/停用节点并编辑 canonical topology |
| Floating Node Windows | 多窗口分别编辑 Evidence extraction/BN interpretation 或 BN states/parents/CPT |
| Assessment Run | preflight、automatic RunSnapshot、进度和取消 |
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

模型不用一个 status 混装保存、技术完整性、生命周期和科学证据：

- `autosave_state`：saving、saved 或 save_failed；
- `technical_status`：complete、configuration_incomplete 或 stable technical error；
- `node/scheme lifecycle`：active 或 archived；历史运行状态由 RunSnapshot 固定；
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
4. 可通过 canonical EvidenceRecipe 和 operators 计算当前 model workspace 声明的 Anchor。
5. 可在 integrated workspace 查看三类节点和两类边，切换/复制任务方案，以 active/dim 显示全局图，并通过多个浮动窗口编辑 Evidence recipe/参数/scorer 与 BN topology/state/CPT。
6. Current nodes/schemes 由 software-copy system library 持有，staged edits 可统一保存/放弃且无需 publish；每次离线推理把 exact model closure 冻结到目标 project 的 RunSnapshot 并输出可追溯结果。
7. 证据不足时不会产生虚假确定性评分或诊断。
8. 软件验证状态与科学验证状态在 UI 和导出文件中明确分开。

## 12. 配套设计文档

- [Assessment Core 设计](./02_ASSESSMENT_CORE_DESIGN.md)
- [Session Bundle 规范](./03_SESSION_BUNDLE_SPEC.md)
- [M3 Native-Rate Time Synchronization 规格](./specs/2026-07-12-m3-native-time-synchronization-design.md)
- [M3 实施计划](./plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
- [Expert-Editable Evidence and Assessment Model Design](./specs/2026-07-15-expert-editable-evidence-and-model-design.md)（EvidenceRecipe/operator 与 expert-designer 原则；旧 apply 交互已被 M7 取代）
- [M7 WinUI Expert Designer and Task Activation Workspace Design](./specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md)（当前完整节点/任务激活/RunSnapshot 权威）
- [M8B System-Owned Model Library and Editable Backend Provenance Design](./specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md)（当前 system model ownership、project/run 边界与 editable backend provenance 权威）
- [M5 Shared Versioned Model Library and Bayesian Workspace Design](./specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)（已实现后端基础与历史 identity/publish 语义）
- [M4 Anchor Calculation and Evidence Availability 规格](./specs/2026-07-13-m4-anchor-evidence-availability-design.md)（Task 0–28 历史/迁移规格）
- [M4 Anchor Calculation and Evidence Availability 原实施计划](./plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)（历史上已批准，现已被取代且不得执行）
- [M4 Lightweight Workflow Validation Amendment](./specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)（已批准）
- [M4 Task 3 Reference Candidate Binding Amendment](./specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)（已于 2026-07-13 批准；D-028）
- [M4 Task 7 Catalog/Resource Identity Amendment](./specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)（已于 2026-07-13 按授权默认批准；D-029；由提交 `583a1e7` 完成）
- [M4 Task 8 Canonical Fingerprint/Runtime Identity Amendment](./specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)（已于 2026-07-13 按授权默认批准；D-030；canonical identity/runtime code 已完成）
- [M4 Anchor Calculation and Evidence Availability Replacement Implementation Plan](./plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（Task 0–28 历史；Task 29–36 已暂停）
- [M4 Autonomous Review Ledger](./reviews/2026-07-13-autonomous-review-ledger.md)（保存默认批准期间的独立复核证据与工具边界）
- 既有后端方向稿：`docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md`
