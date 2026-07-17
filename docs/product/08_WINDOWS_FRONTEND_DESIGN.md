# Windows Frontend Design（v0.3 历史页面细节）

| 字段 | 值 |
|---|---|
| 设计版本 | v0.3 compatibility reference；当前权威为 M7 v0.1 |
| 平台 | Windows 10/11 |
| 推荐技术 | C#、.NET、WinUI 3 |
| 后端连接 | 本地 JSON-RPC sidecar |
| 核心原则 | 专家主导模型设计、前后端同一 canonical recipe、后端维护状态/版本/执行一致性、离线优先 |

> **当前权威与适用性：** [M7 WinUI Expert Designer and Task Activation Workspace Design](./specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) 已取代本文件的同 concept 多版本选择、Draft/Published/Apply/Publish、固定 Node Inspector 等交互。本文只保留页面、session/result 展示和错误恢复细节作为历史参考；新实施必须使用完整独立节点、task activation、active/dim 全局画布、多浮动节点窗口、autosave current scheme 与 automatic RunSnapshot。

## 1. 产品体验目标

前端不是一个只显示最终分数的 dashboard。它必须让不同用户完成同一条可追溯工作流：

1. 启动并确认后端环境可用；
2. 查看系统支持哪些数据类型和字段；
3. 导入并检查一个多模态 session；
4. 浏览全局 Evidence/BN versions，为当前 task scheme 选择 exact versions，或 copy-on-write 修改 EvidenceRecipe/operator graph、BN topology/state 与 CPT；
5. 应用并选择不可变 `AssessmentSchemeVersion` 运行评估；
6. 从四项 competency 一直追溯到 sub-skill、evidence、原始时间窗和参数版本；
7. 导出可复现结果或诊断支持包。

界面不得掩盖缺失模态、M1–M3 技术诊断、M4 calculation status、未校准参数或模型科学验证状态。界面也不得把差表现伪装成无效数据：`computed + Unacceptable` 必须显示为有效负面 evidence。

## 2. 前端与后端责任

| 前端负责 | 后端负责 |
|---|---|
| 专家模型设计的可视化、交互、表格编辑、输入预检查提示 | session schema、component versions、scheme draft、typed graph、CPT 和参数的 canonical 状态 |
| pending 操作、乐观 UI、冲突提示 | 原子 transaction、并发版本、验证与持久化 |
| 展示 canonical graph 和差异 | CPT 生成/迁移、DAG 编译、BN 推理 |
| 提供可选修改说明、apply 操作和历史入口 | 自动 audit event、provenance、content identity 与 immutable component/scheme versions |
| sidecar 启动、监控和恢复入口 | 计算 job、取消点、结果 artifact |

前端不能直接修改 YAML/JSON model files，也不能在 UI 中执行任意 Python。

这里的责任分工不把模型内容决定权交给后端：Evidence、算法、参数、BN topology/state/CPT 由专家通过前端决定；后端只保存并执行同一 canonical object、签发不可变版本、处理并发，并阻止技术上不可解析或不可执行的状态。科学合理性不属于 backend apply gate。

## 3. 应用外壳

推荐布局：

~~~text
┌──────────────────────────────────────────────────────────────────┐
│ Project / Session / Model revision / Backend health / User       │
├──────────────┬───────────────────────────────────┬───────────────┤
│ Navigation   │ Main workspace                    │ Inspector     │
│              │                                   │ / Properties  │
├──────────────┴───────────────────────────────────┴───────────────┤
│ Validation, progress, warnings, trace ID, recovery actions       │
└──────────────────────────────────────────────────────────────────┘
~~~

顶部状态条持续显示当前 project、session、task profile、published/autosaved scheme、draft technical state 以及 backend health。任何结果页面都必须可见 scheme version、exact component identity 和 run ID。

## 4. 页面信息架构

### 4.1 Project Launcher

- 创建、打开、导入和导出项目；
- 最近使用的项目、session 和 run；
- backend startup 状态、版本兼容性与重启入口；
- 默认 task/scheme version 及其 scientific validation badge；
- 项目数据位置和可用磁盘空间。

安装包模式由前端自动启动 backend。开发模式可显示“连接开发 runtime”，但普通用户不需要配置 Python。

### 4.2 Session Import 与 Ingestion Readiness

输入能力面板按模态展示：

| 模态 | 典型文件 | 核心内容 |
|---|---|---|
| X(t) | CSV/Parquet | 飞行状态、位置、速度、姿态、角速度等 |
| U(t) | CSV/Parquet | longitudinal、lateral、yaw、heave 等控制输入 |
| I(t) | MP4/frames + frame index | 随头部转动的第一视角 VR 场景、frame timestamp、head pose/FOV |
| G(t) | Parquet/CSV | gaze ray/point、fixation/stare、AOI、validity/confidence |
| EEG | EDF/Parquet | channel、采样率、事件、原始/预处理标识 |
| ECG | EDF/Parquet | waveform/R peaks、采样率、baseline interval |
| Pilot camera | MP4/frames，可选 | 驾驶员画面；不替代 I(t) 或 G(t) |

每张模态卡显示 present、export_pending、missing、invalid 或 not_applicable；同时显示时间范围、采样率、单位、checksum、同步 diagnostics 和修复建议。这里的 `invalid` 只表示 M1–M3 接口、结构或时间合同不成立，不能用来表示轨迹、控制或生理表现很差。导入前可展开 schema，看到后端接受的数据类型、必填字段、可选字段和示例。

### 4.3 Session Explorer

所有视图共享一条 session-relative 时间轴：

- VR 第一视角视频；
- gaze point/ray、fixation 与动态 AOI overlay；
- 可选 pilot camera；
- X(t)、U(t) 多通道曲线；
- EEG/ECG waveform 与派生 diagnostics；
- Translation / Deceleration / Hover phase；
- disturbance、提示、包线越界等 event；
- anchor source window、`calculation_status`、`classification_override` 与 non-gating diagnostics。

用户拖动时间轴、播放或选择区间时，各视图同步更新。原始与重采样视图必须有清晰标记，不能让派生曲线看起来像原始采样。

### 4.4 Evidence Designer

这是 integrated model workspace 中展开某个 Evidence 后的内部计算页面。它直接编辑后端 canonical `EvidenceVersion` candidate / `EvidenceRecipe`，至少包含：

- 左侧 operator palette：Input、Temporal、Signal、Event、Gaze/Vision、Flight Geometry、Statistics、Composition、Aggregation、Scoring；
- 中央 typed computation canvas：node、input/output port、edge、unit、cardinality 与中间结果入口；
- 右侧 schema-driven Inspector：名称、说明、stream/field/channel/AOI/event/reference binding、窗口、阈值、滤波、聚合、safe formula、scorer 和文档；
- 底部 Preview/Trace：对选定 session 执行当前 draft，查看各 node 的输入摘要、输出、时间窗、raw metric、D/A/U likelihood 与错误定位；
- 顶部 Evidence concept/version、clone、disable/retire、undo/redo、版本 diff 与“应用到后续评估”。

表单完全由 `OperatorDefinition.parameter_schema` 与 UI metadata 生成；新增 built-in/trusted operator 后无需为每个 Anchor 手写 WinUI 页面。专家可在不写 Python 的情况下新增、复制、重连或删除 recipe nodes，并修改已有 Anchor 的整个计算流程。

典型“扰动期间是否关注目标仪表区域”recipe 在画布中显示为 `EventSelect → EventWindow` 与 `GazeAoiIntervals → IntervalIntersect → AoiFilter → FirstMatchLatency/Duration/DwellRatio → EventAggregate → Scorer`。如果输入已有逐帧 AOI label，专家选择 label-to-interval mode；如果只有 gaze ray 与场景 AOI，则选择 geometry-association mode。

Draft 每次用户意图自动保存；incomplete recipe 可以继续编辑。Preview 不要求 apply。只有点击“应用到后续评估”时才检查 dangling port、DAG、operator/type/unit/parameter、formula 与 scorer 是否可执行。

### 4.5 Integrated Model / BN Graph Editor

这是 v0.1 的核心高层页面，不是只读图。它在同一画布中显示 Raw Input、Evidence、BN Node，但不会混用 extraction 与 probabilistic edge。

基本布局：

- 左侧 palette/library：Raw Input、Evidence concepts/versions、BN concepts/versions；Advanced Mode 可增加 context/random-variable templates；
- 中央无限画布：节点、连接 handle、缩放、框选、搜索、自动布局；
- 右侧 Node/Edge Inspector；
- 底部 Validation Console、operation history 和 pending 状态；
- 顶部 Guided Mode / Advanced DAG Mode、autosaved draft、preview、apply、undo/redo。

支持：

- 从 palette 拖入新节点；
- 拖动节点位置；
- 从 typed handle 拉线新增 data/extraction 或 probabilistic BN edge；
- 选择并删除 node 或 edge；
- 多选移动和对齐；
- 编辑 label、description、state space、parent order、binding；
- 分开查看 Evidence source bindings 与 probabilistic parents；
- 打开 CPT editor，或跳转到该 evidence 的 EvidenceRecipe；
- 预览任何破坏性操作和 CPT migration；
- 开启只读 inference overlay，显示 observed Evidence 对 posterior 的影响，不反转 canonical BN arrows；
- scheme/component version diff，并从任意版本创建新 draft。

详细事务和迁移规则以 [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) 为准。

### 4.6 Node Inspector

Evidence node 显示两个明确分区：

- `Extraction`：concept/version ID、recipe/operator dependencies、source bindings、输入模态、phase/event applicability、公式、参数、阈值和 scorer；
- `BN interpretation`：EvidenceBindingVersion candidate、observation mapping、probabilistic parents、states、CPT/likelihood 和 downstream query paths；
- `executable/incomplete/operator_unavailable` capability；
- 当前 session 的 raw metrics、continuous score、D/A/U evidence、`calculation_status`、`classification_override` 和 raw availability；
- source windows、non-gating diagnostics、non-computed reason 和 provenance；
- “展开 EvidenceRecipe”与“回到高层模型”入口。

Latent/Competency/Context node 显示：

- states 与顺序；
- parents/children；
- CPT grid、维度、row sum 和 generator metadata；
- 当前 posterior；
- CPT 修改前后差异、影响行数和 validation warnings。

Edge Inspector 显示 parent/child、语义影响、CPT migration 状态和删除预览。

M4 `AnchorResult v0.2` 不生成 `invalid_quality`。Node Inspector 必须把 `computed + Unacceptable` 显示为 raw availability = 1 的负面观测，不得降级成 invalid、missing 或灰掉的 evidence；`missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 与 `extractor_error` 才是没有 D/A/U observation 的非 computed 状态。

Draft 新增 Anchor 但引用的 operator 尚不可用时，Node Inspector 显示 `operator_unavailable` 并阻止 apply/run；它是模型 capability 问题，不能显示成当前 session `not_computable`。只有新增算子库尚不具备的能力才需要开发 trusted operator plugin。

### 4.7 Global Library 与 Scheme Versions

- Evidence/BN concepts、全部并行 component versions、lineage 和被哪些 schemes 使用；
- published scheme version 列表、parent、作者、时间、可选说明、exact references 与 content identity；
- draft 与 base scheme version；
- component selection、topology、state、CPT、Evidence parameters、binding 和 metadata diff；
- technical validation 与 preview 摘要；
- 从任意 published scheme version 创建新 draft；
- copy-on-write apply 结果、created/reused component versions 和不可变性提示。

不能直接“修改已发布版本”。所谓 rollback 是从旧 scheme version 建立新 draft，通过技术校验后 apply 为新的 component/scheme versions。新版本出现后不得自动替换旧方案中的 exact reference。

### 4.8 Assessment Run

用户选择 session 与 published `AssessmentSchemeVersion` 后先执行 run preflight：

- 模态接口状态与同步 diagnostics；
- anchor applicability 和预计输入 availability；
- reference path、event、baseline 等任务必需信息；
- model compilation、operator/extension 和 engine compatibility；
- 会阻断运行的结构／计划 error 与 non-gating diagnostic warning。

run 页面显示阶段进度、已完成 Evidence、取消按钮、日志摘要和 trace ID。run.start 只接受 published scheme version 并锁定全部 exact components。Executable draft 可通过 preview 直接试算；preview 结果标记 draft/non-applied，不改变历史 run。

Preflight 不得依据 residual、gap、artifact flag、轨迹偏差、控制强度或生理数值判断 evidence 是否“质量合格”。这些字段可供用户诊断和溯源，但 M4 在输入、适用性、配置和依赖前提成立时必须计算。

### 4.9 Results

第一层显示 TCP、PC、SM、OC posterior 分布和各自 evidence availability coverage，不把 posterior 简化成无置信度的单一总分。coverage 表示 evidence 是否存在，不表示飞行表现好坏；computed D、A、U 均贡献 availability。

向下钻取：

1. competency posterior；
2. 相关 11 sub-skills posterior；
3. 支撑/反对的 evidence states；
4. leave-one-out evidence contribution；
5. anchor continuous value、`calculation_status`、`classification_override`、raw availability 和 phase/event breakdown；
6. 原始 source window、session artifact 和参数版本。

必须单独展示：

- 上游 stream 的 missing/export_pending/invalid/not_applicable 与 M4 的 missing_input/not_applicable/not_computable/dependency_missing/extractor_error，且两组状态不得混用；
- evidence availability coverage 不足提示；
- `computed + Unacceptable` 的负面 evidence，并明确 raw availability = 1；
- scheme version、exact component IDs/hashes、portable bundle hash（如适用）、run ID 和算法版本；
- scientific validation status；
- “此结果用于研究/训练支持，不是认证决定”的产品声明。

### 4.10 Diagnostics 与支持包

- frontend/backend/protocol/engine/model 版本；
- sidecar 状态、最近错误、trace ID 和日志位置；
- schema、插件与 model compatibility；
- restart backend、重新握手、重新获取 canonical graph；
- 导出默认脱敏的 support bundle；
- 用户明确勾选时才包含原始数据，并提示隐私影响。

## 5. 图编辑交互状态

图形元素必须区分：

| 状态 | 表现 | 含义 |
|---|---|---|
| canonical | 实线、正常颜色 | 已被后端确认 |
| pending | 虚线/轻量动画 | 请求已发出，尚未确认 |
| rejected | 短暂错误高亮 | 后端拒绝，随后恢复 canonical |
| warning | 警告徽标 | 可保存 draft，但不能发布或需确认 |
| invalid | 错误边框 | 当前 draft 未通过验证 |
| selected | 高对比描边 | 当前 inspector 对象 |

不得只用红绿区分状态。颜色之外同时使用图标、线型和文字。

### 5.1 新增节点

放下节点后前端生成 transaction/op ID 和新的 UUIDv4 node_id 并显示 pending。后端验证该 ID，成功时在 canonical response 中确认同一 node_id 和 defaults；失败则移除 pending node。Semantic commit 成功后再以独立 expected_layout_version 提交 drop position；位置冲突不回滚已创建 node，只刷新并重试 layout。Evidence 节点必须完成 binding；未绑定时可留在 draft，但 preview/apply 被阻断。

### 5.2 新增边

拉线时先做轻量客户端提示，但后端验证才是结论。若新增 parent 需要扩展 child CPT，前端必须展示 neutral replication、generated influence 或 manual 三种迁移选择及预览。

### 5.3 删除边或节点

删除前显示影响面板：边、children、CPT 行数、anchor dependencies、competencies 和运行结果影响。用户选择 detach/cascade/cancel；后端再次验证。删除不允许靠键盘误触立即不可逆完成。

### 5.4 修改 state space

这是高影响操作。界面显示原 state、新 state、受影响 CPT、迁移策略和未完成行。只有预览确认后才提交。发布前所有 CPT 必须完整、非负且每行和为 1。

### 5.5 Undo、Redo 与冲突

Undo/redo 请求后端命令日志，不能只撤销本地图形。遇到 graph_version conflict：

1. 停止继续发送依赖旧版本的操作；
2. 获取 canonical snapshot；
3. 显示本地意图与后端差异；
4. 允许用户重新应用仍合法的操作。

## 6. 表格和 CPT 编辑

- 支持 keyboard navigation、复制/粘贴和行级 validation；
- 显示 parent state 的稳定顺序；
- 概率可输入小数或百分比，但保存前统一规范化表示；
- 默认不静默归一化错误行；可以提供显式“归一化此行”动作并记录变更；
- 大 CPT 显示组合数警告、筛选和分组；
- generator 参数与 materialized CPT 都要可查看，避免黑箱生成；
- 每次保存显示 old/new diff 和修改理由。

## 7. 错误与恢复体验

每个错误映射到：

- 一句话说明发生了什么；
- 受影响对象；
- 当前操作是否已回滚；
- 用户可执行的恢复动作；
- 可复制 trace ID 和技术详情。

sidecar crash 时保留前端页面状态，但将所有修改控件置为只读，直到重启、握手并重新获取 canonical draft。不得假装 pending 操作已经保存。

## 8. 可访问性与本地化

- 满足键盘全流程操作，图编辑提供可访问的 node/edge 列表替代视图；
- 控件具备 AutomationProperties.Name 和 screen-reader 说明；
- 支持 100%–200% 缩放、Windows 高对比度和 reduced motion；
- 图、posterior、stream 状态和 M4 calculation status 不只依赖颜色；
- v0.1 可先提供英文 UI，但字符串必须资源化，以支持中文；
- 单位、日期和小数显示遵循项目 profile，存储仍使用 canonical units。

## 9. 前端验收标准

1. 普通用户从启动到完成 sample session 评估无需命令行；
2. 支持的六类核心输入在 UI 中有 schema、状态和示例；
3. VR、gaze、X/U、EEG/ECG 能在统一时间轴同步查看；
4. 可新增、删除、移动三类高层 node 和两类 typed edge，并与后端 canonical graph 一一对应；
5. rejected operation 能视觉回滚且不污染 draft；
6. CPT migration preview、technical validation、undo/redo、apply 完整可用；
7. run.start 始终锁定 published scheme 与 exact component versions 并显示 provenance；run.preview 锁定 exact draft_id + graph_version；
8. 结果可从 competency 追溯到 source window；
9. 缺失 evidence 与低 availability coverage 不显示成正常高置信度评分；`computed + Unacceptable` 必须显示为完整 availability 的负面 evidence，而不是 invalid/missing；
10. backend crash、版本冲突和损坏 session 都有可执行恢复路径；
11. design view 显示 canonical BN arrows；inference overlay 只读且不能写回 topology；
12. 从一个方案发布新方案不会改变旧方案或历史 run。
