# Pilot Assessment System — 产品设计文档中心

| 字段 | 当前值 |
|---|---|
| 设计基线 | 产品 v0.5 complete-node/task-activation expert designer；D-031–D-053 已获用户确认 |
| 基线日期 | 2026-07-17 |
| 产品阶段 | M1/M2/M3、M4R、M5、M6 与 M7A Current Model Runtime 已工程验证；M7B Task 1–13 已完成 WinUI scaffold、强类型合同层、受监督 sidecar、受管 project/session、canonical task-scheme、global active/dim 模型图、图上节点/任务激活编辑、多独立节点浮窗、Raw Input/Evidence/BN/CPT 编辑器、写回 Python canonical state 的持久 autosave/reconciliation，以及不改 canonical 模型的即时中英文切换；Task 14 起实现实际运行、结果、trace 与 diagnostics；M8 packaging 尚未设计；starter/synthetic `formal_run_authorized=false` |
| 运行范围 | Windows 本地、离线 session 评估 |
| 科学状态 | 参考模型待领域专家校准与验证 |
| 权威范围 | pilot_assessment_system 的产品设计与实现约束 |

2026-07-17 M7B Task 12 已完成普通表单字段的 350 ms autosave、同一 canonical 对象的有序写入、独立对象并发、transaction-ID 幂等重试、晚响应 rebase、Reload/Reapply 冲突恢复、编辑器/主窗口保存状态和关闭前 flush。可见验证将 BN 描述写入后端、恢复原文并在重开窗口后读回 revision `2`；因此前文 Task 11 时点的“Task 12 才负责”已由本段取代。离散 activation/edge/copy/archive 与 parent/state/CPT 仍直接使用已有原子后端操作，不经过延迟表单保存。

2026-07-17 M7B Task 13 已完成即时中英文切换：shell、页面、任务侧栏、active/dim 图、对话框以及已打开的 Raw Input/Evidence/BN/CPT 节点窗口均原地刷新；模型翻译缺失时显示明确 fallback 标记。语言只保存为 `%LOCALAPPDATA%` UI preference，不发送模型写操作，也不改变 ID、revision、hash、参数或结果。fresh gate 为 desktop Unit `75/75`、Contract `3/3`、focused localization `8/8`、x64 Debug build `0 warning / 0 error`，`527` 对资源键与 `481` 个实际引用均零缺失。下一项是 Task 14 actual run/results/trace/diagnostics；`model.preview.node` 仍只是 frozen snapshot metadata，不代表已经执行评估。

## 1. 文档用途

本目录是产品交付、开发、审查和后续专家配置的统一入口。它回答五类问题：

1. 产品解决什么问题、明确不解决什么问题；
2. 原始 session 如何进入系统并保持多模态时间一致；
3. 专家如何用全局完整节点、任务激活方案、可编辑 EvidenceRecipe 和 BN 组合任意任务模型；
4. Windows 前端如何展示并修改节点、边、参数和 CPT；
5. 如何验证软件、校准评估模型并把产品交给下一位维护者。

文档中的 Hover、O1–O13、H1–H5 和 33-node BN 是一套**可编辑 starter template**。算法、阈值、拓扑和 CPT 只用于启动系统与给专家提供示例；产品不以证明它们科学正确为目标。专家可以在全局节点库中创建、复制和修改任意 Evidence/BN 节点，再由不同 `TaskScheme` 激活所需节点。每个可见节点只有一个当前完整定义；任务需要不同定义时使用新的节点，而不是在同一个节点中切换版本。书面设计、实施计划、代码实现、工程可运行与科学有效性是不同状态，不能相互替代。

## 2. 推荐阅读顺序

| 顺序 | 文档 | 主要读者 | 内容 |
|---:|---|---|---|
| 1 | [01_PRODUCT_OVERVIEW.md](01_PRODUCT_OVERVIEW.md) | 所有人 | 产品边界、角色、工作流和总架构 |
| 2 | [M7 WinUI Expert Designer and Task Activation Workspace Design](specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) | 专家、产品、前后端 | 当前产品权威：完整节点、任务激活、复制/停用、多浮窗、autosave 与 RunSnapshot |
| 2.1 | [M7 Implementation Roadmap](plans/2026-07-17-m7-winui-expert-designer-implementation-roadmap.md) | 开发、审查者 | 当前实施顺序：M7A 后端 current-model 迁移后再做 M7B WinUI；定义跨阶段门与轻量验证边界 |
| 2.2 | [M7A Current Model Runtime Implementation Plan](plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md) | 后端开发、审查者 | 12 个 INLINE 任务：完整节点、任务激活、SQLite v2、自动快照、sidecar 与 legacy replay |
| 2.3 | [M7B WinUI Expert Designer Implementation Plan](plans/2026-07-17-m7b-winui-expert-designer-implementation-plan.md) | Windows 前端、审查者 | 15 个 INLINE 任务：sidecar client、active/dim 画布、多浮窗、编辑器、双语与 run/results |
| 3 | [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) | 专家、产品、前后端 | 已实现的后端基础与历史 identity/publish 语义；冲突处由 M7 规格取代 |
| 4 | [M5 Implementation Plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) | 开发、审查者 | 已完成：inline 任务、合同冻结、O8 迁移、轻量验证与完成门 |
| 5 | [M6 Local Runtime, Durable Persistence and Sidecar Protocol Design](specs/2026-07-16-m6-local-runtime-persistence-and-protocol-design.md) | 前后端、交付、审查者 | 已实现：受管项目、SQLite、artifact、run lifecycle 与 JSON-RPC sidecar |
| 6 | [M6 Implementation Plan](plans/2026-07-16-m6-local-runtime-persistence-and-sidecar-implementation-plan.md) | 开发、审查者 | 已完成：15 个 INLINE 任务、轻量 test-first、focused smoke 与完成门 |
| 7 | [03_SESSION_BUNDLE_SPEC.md](03_SESSION_BUNDLE_SPEC.md) | 数据与后端 | X/U/VR/gaze/EEG/ECG 数据合同与同步 |
| 8 | [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md) | 领域专家、算法 | 18 个 starter anchor 的算法和初始参数 |
| 9 | [05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md](05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md) | 算法、后端 | BN 拓扑、状态、CPT、缺失证据和解释 |
| 10 | [02_ASSESSMENT_CORE_DESIGN.md](02_ASSESSMENT_CORE_DESIGN.md) | 后端开发 | 模块边界与完整计算流水线 |
| 11 | [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) | 前后端开发 | 历史细节：三类节点、两类边、事务和 CPT 迁移；冲突处由 M7 规格取代 |
| 12 | [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) | 前后端开发 | sidecar 生命周期与 JSON-RPC 合同 |
| 13 | [08_WINDOWS_FRONTEND_DESIGN.md](08_WINDOWS_FRONTEND_DESIGN.md) | UI/UX、前端 | 历史页面细节；当前交互由 M7 规格取代 |
| 14 | [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) | 测试、交付 | 验证层级、验收门槛和移交清单 |
| 15 | [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) | 开发、接手者 | 当前代码、验证证据、限制和下一里程碑 |
| 16 | [DECISIONS.md](DECISIONS.md) | 维护者 | 已锁定决策及其理由 |
| 17 | [GLOSSARY.md](GLOSSARY.md) | 所有人 | 术语、ID 和状态语义 |
| 18 | [REFERENCES.md](REFERENCES.md) | 审查者、领域专家 | 公开文献、DOI 与证据用途 |
| 19 | [10_DESIGN_SELF_REVIEW.md](10_DESIGN_SELF_REVIEW.md) | 审查者 | 本轮设计自审、发现和遗留风险 |
| 20 | [后端 M1 实施计划](plans/2026-07-11-backend-foundation-m1-implementation-plan.md) | 开发、审查者 | RED/GREEN 任务、范围和完成定义 |
| 21 | [M2 多模态合成基础规格](specs/2026-07-11-multimodal-synthetic-foundation-design.md) | 开发、数据、审查者 | 已批准：理想 I/G/EEG/ECG/camera 合同、合成 bundle 与 ingestion readiness |
| 22 | [M2 实施计划](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md) | 开发、审查者 | shared X/U、adapter、generator、readiness 与本地 E2E 的 TDD 步骤 |
| 23 | [M3 Native-Rate Time Synchronization 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) | 开发、数据、审查者 | 已批准：native-rate clock mapping、session window、aligned views 与同步报告 |
| 24 | [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) | 开发、审查者 | 已完成：Task 0–14 的实现、实测完成门与 handoff/关闭记录 |
| 25 | [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md) | 专家、产品、前后端 | typed EvidenceRecipe/operator graph、自动参数表单与最小技术校验；旧 apply 交互由 M7 取代 |
| 26 | [M4R Editable Evidence Computation Foundation Implementation Plan](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md) | 开发、审查者 | 已完成：合同、registry、validator、compiler/executor、recipe 生命周期、18 个 starter resources 与轻量 E2E |
| 27 | [M4 Anchor Calculation and Evidence Availability 规格](specs/2026-07-13-m4-anchor-evidence-availability-design.md) | 开发、算法、审查者 | 历史/迁移规格：Task 0–28 与 15 个插件已实现；固定插件和 completion gate 已由 2026-07-15 新规格取代 |
| 28 | [M4 原实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) | 开发、算法、审查者 | 历史计划，已被取代且不得执行 |
| 29 | [M4 轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md) | 开发、算法、审查者 | 历史 fixed-plugin 验证修订；不再定义 M4R completion gate |
| 30 | [M4 replacement 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) | 开发、算法、审查者 | Task 0–28 已完成；Task 29–36 已停止且不得执行 |
| 31 | [M4 Task 3 Reference Candidate Binding 修订](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md) | 开发、数据、审查者 | 已实现的 session/reference binding 合同，继续保留 |
| 32 | [M4 Task 7 Catalog and Resource Identity 修订](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md) | 开发、算法、审查者 | 已实现的 legacy catalog/resource identity，供迁移与 replay |
| 33 | [M4 Task 8 Canonical Fingerprint and Runtime Identity 修订](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) | 开发、审查者 | 已实现的 legacy canonical/runtime identity，供迁移与 replay |
| 34 | [Autonomous Review Ledger](reviews/2026-07-13-autonomous-review-ledger.md) | 维护者、审查者 | 保存历史复核与关闭证据 |
| 35 | [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md) | 开发、数据、审查者 | 已执行：格式样例 X/U + 合成缺失模态经完整 M6 后端运行；仅证明软件闭环 |
| 36 | [Captured-Format Multimodal Software Demo Plan](plans/2026-07-16-external-multimodal-session-demo-implementation-plan.md) | 开发、接手者 | 已完成：轻量生成、真实故障定位、18/18 Evidence、BN 推理与结果路径 |

### 2.1 文档目录的职责

- `docs/product/` 根目录中的编号文档、`DECISIONS.md` 和 `GLOSSARY.md` 是当前产品基线；
- `docs/product/specs/` 保存单个里程碑或子系统的状态受控设计合同，只有标记为“已批准”的规格才进入实施；
- `docs/product/plans/` 保存从已批准规格派生的实施步骤、选择性测试策略、验证命令和提交边界，计划不能覆盖 `DECISIONS.md` 或已批准规格；完成后继续保留，作为产品如何实现和验证的移交证据。
- `docs/product/reviews/` 保存规格、计划和实现检查点的复核 ledger；它不取代正式决策、测试或 Git 历史。

## 3. 权威性规则

发生冲突时按以下优先级处理：

1. [M7 WinUI Expert Designer and Task Activation Workspace Design](specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md)、本目录中状态为“当前”的正式产品文档与后续决策；
2. 历史 RunSnapshot、已发布 legacy scheme/component records 及其 exact hashes；
3. 产品代码与自动化测试，用于说明“目前已实现什么”，不能覆盖已确认但尚未实施的新产品目标；
4. 研究阶段的 PPT、讨论稿和历史说明。

历史草案 [2026-07-08-backend-core-runtime-adapter-design.md](../superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md) 仅用于说明设计演进。其 FastAPI、H1–H6、CSV-only 或不可编辑拓扑等旧假设不能覆盖本基线。

## 4. 当前锁定口径

- 原始数据族：X(t) 飞行状态、U(t) 控制输入、I(t) 飞行员在 VR 中实际看到的第一视角场景、G(t) 在该动态场景上的 gaze/AOI、P(t) 生理信号（至少 EEG 与 ECG）。
- Starter template：O1–O13 与 H1–H5 共 18 个示例 evidence；通用 engine 和 expert model 不限制数量，专家可新增、复制、disabled、retired 或替换。
- 顶层输出：TCP、PC、SM、OC 四项 aggregate competencies；中间层为 11 个 latent sub-skills。
- 证据等级：Desired、Adequate、Unacceptable。`computed + Unacceptable` 是有效负面 evidence，raw availability 与 computed D/A 一样为 1；coverage/availability 表示证据是否形成，不表示表现好坏。
- `export_pending/missing/invalid/not_applicable` 是 M1–M3 的 stream 生命周期或结构状态；M4 AnchorResult v0.2 的非 computed 状态固定为 `missing_input/not_applicable/not_computable/dependency_missing/extractor_error`，M4 不生成 `invalid_quality`。
- M4 假定进入它的 aligned input 已满足上游结构合同，不判断原始采集“质量够不够好”，也不因 coverage、gap、噪声、幅值、生理范围或差表现过滤 evidence；这些技术统计只进入 diagnostics/provenance。
- 全局节点库中的每个可见 Evidence/BN `ModelNode` 只有一个当前完整定义；若算法、parents、states、CPT 或语义不同，就创建另一个节点。内部 revision/history 不作为任务侧可选版本。
- 每个 `TaskScheme` 是并列、自动保存、可直接运行的节点激活集合；切换任务只改变 active/dim 与执行 closure，不替换节点内部定义。
- 高层工作区只显示 Raw Input、Evidence、BN Node 三类节点；`Raw/task source → Evidence` 是 data/extraction edge，Raw Input 不属于 BN；probabilistic edge 才表示 `P(child | parents)`。
- Hover starter 的 canonical BN 生成方向为 Competency → Sub-skill → Evidence；评估时由 observed evidence 计算 competency posterior。只读 inference overlay 可以显示反向信息影响，但不得反转已存 BN edges。
- 通用引擎允许专家建立其他合法 DAG，但必须通过新的完整节点或明确修改后的节点定义表达，不是同一图的显示反转。
- 专家通过前端决定模型内容；后端维护 canonical state、最小技术校验、CPT 原子迁移、持久化和执行一致性，但不拥有科学内容决定权。
- 正常 UI 取消 Draft/Published/Apply/Publish；每次 run 自动冻结 exact managed session、当前 TaskScheme active closure、完整节点定义、recipes/operators、CPT 与 hashes 为 immutable RunSnapshot。
- 软件测试通过与科学有效性成立是两个独立结论。
- 当前 repository-external 2,902-row simulator CSV 只是一次随意飞行产生的采集格式样例，仅用于接口、解析、时间和软件 E2E；它不是标准轨迹、任务 ground truth、专家 phase annotation 或能力证据。围绕它生成的 reference/annotations/biometrics 也只是 synthetic fixtures。

## 5. 当前实现边界

截至 2026-07-13，Python Core 已完成 M1、M2 与 M3：严格 SessionManifest/StreamDescriptor/legacy AnchorResult 0.1 合同、inspect-only directory-bundle integrity gate、shared X/U、版本化 profiles/adapters、deterministic multimodal generator、`IngestionReadinessReport`，以及 native-rate `AlignedSession`/`SynchronizationReport`。M3 使用 master-clock X mapped coverage、Decimal round-half-even 与版本化 temporal bindings，保留所有 source rows，并输出确定性的 synchronization fingerprint；它不插值、不重采样，也不建立全局或 anchor window grid。完成门实测仍为 `694 passed, 2 skipped`，配置 repository-external CSV 后 M2/M3 格式样例 E2E 为 `2 passed`，隔离 wheel 的 M3 micro E2E 为 `1 passed`。这些结果不验证样例飞行的任务、表现或科学有效性；M2/M3 report 始终保持 `formal_run_authorized=false`，synthetic fixture 为 `not_supported`。

旧 M4 replacement Task 0–28 已完成并保留为历史迁移资产。2026-07-15 用户确认产品应首先服务专家自由设计 Evidence 和 BN，接受 D-031–D-035 与 EvidenceRecipe/operator architecture，并批准正式规格和 replacement M4R plan。M4R 现已实现 canonical contracts/schema、trusted operator catalog、only-technical validator、generic compiler/executor、backend-only draft/preview/apply/replay、18 个可编辑 starter recipes 和轻量 E2E；任意第 19 个 recipe 无需 Anchor-ID 分支即可注册和运行。15 个旧插件继续作为 legacy/reference，H4/H5/O13 使用 operator composition 而没有新增 whole-Anchor plugin。2026-07-16 用户进一步确认 D-036–D-040：全局 immutable component versions、exact-pinned task schemes、三类节点/两类边、starter canonical BN 与 posterior inference flow 的区分，以及 legacy Evidence-to-Evidence extraction 的非覆盖迁移规则。M5 已完成 generic identity、model/BN/scheme/inference public DTO、16 类双目录 Draft 2020-12 schema、typed source/M4R preflight、global exact-version repository/service、exact-pinned scheme closure/technical validation、typed scheme operations、incomplete autosave、undo/redo、copy-on-write atomic publish、exact replay、generic CPT validation/materialization/migration、finite-discrete exact inference/read-only influence trace、17 个 compatible M4R active imports/同 concept compliant TPX parallel version、checksummed Hover starter BN package，以及 read-only draft preview/posterior/influence/copy-on-write publish/replay workflow。该 starter 物化 4 个 competency、11 个 sub-skill、18 个 Evidence binding 与 33 张工程默认 CPT，全部可由专家另行 clone/修改；这些数量未进入 generic loader。旧 O8 原 bytes/hash 仍作为 legacy/replay 资产保留。

M6 completion gate 也已关闭：受管 project/session/artifact、SQLite component/draft/run persistence、idempotency/audit、exact technical preflight、dynamic Evidence→Observation→BN pipeline、single-worker progress/cancel/recovery，以及无网络端口的 JSON-RPC/JSONL stdio sidecar 均已实现。轻量纵向闭环证明 external bundle 删除后仍可从受管副本运行，整个 project 换目录重开后 exact scheme/result/artifact 仍可回放。

2026-07-17 用户确认 D-047–D-053：M7 改用完整独立节点、全局节点库、任务激活集合、默认只复制节点且复用 fixed parents、启用 parent closure、停用 parent 前级联确认、多浮动节点窗口、双语模型元数据，以及“autosave current scheme + automatic immutable RunSnapshot”。M7A 现已实现 global current nodes、TaskScheme activation/copy/cascade、atomic edge/state/CPT edits、autosave history/undo/redo、current preflight/run snapshot、legacy replay 和完整 `model.*` sidecar surface。fresh gate 为 current focused `42 passed`、compatibility `151 passed`、full repository `1684 passed, 3 skipped`；51 类 schema 零漂移，Ruff/format/ty/build 与仓库外 wheel smoke 通过。M7B Task 1–5 已建立正式 WinUI 工程与应用 shell，完成 M7A canonical DTO 的 C# 强类型映射、4 MiB JSONL、并发 JSON-RPC client、隐藏 sidecar 监管、Project Launcher、recent-project shortcuts、folder picker、只读 Session inspect、受管 exact-copy import、session/revision/report/artifact-reference 浏览，以及七类 canonical modality 状态卡。新 `session.report.get` 仅内联受管、校验通过且不超过 1 MiB 的 JSON 报告；图像和时序仍只传引用。Task 6 又实现 `model.scheme.*` typed client、项目打开/关闭联动、搜索/标签/分组/排序/archived 过滤、Create/Copy/Rename/Archive、stable-ID selection restore、stale project-response suppression，以及 canonical revision/hash/status reconciliation；普通 UI 没有 Draft/Published/Apply/Publish。Task 7 进一步消费单一后端 `ModelGraphSnapshot`，实现 global active/dim/archived 三种视图、双语搜索及 kind/group/tag/activation 过滤、圆形 Raw/Evidence/BN 节点、extraction/probabilistic 规范边、缩放/Fit/minimap、虚拟化、键盘/automation、单选/多选与上下文菜单；真实 sidecar 项目显示 `53` 节点、`67` 边、`52` active。Task 8 又完成三类节点新建、backend closure 激活、impact-hash 级联停用、Delete/current-task 语义、project-scoped typed clipboard、只复制节点并保留 fixed parents、拖拽 autosave，以及 extraction/probabilistic typed edge 迁移。新建 Evidence 可在保持 `incomplete` 和精确诊断的同时逐步增加 Raw Input binding，不会被伪装为 executable。Task 9 进一步提供按 `(project, task, node)` 键控的非模态独立节点窗口、同键聚焦复用、跨节点并排比较、canonical 更新路由、未来脏编辑冲突入口，以及按显示器工作区校正的窗口位置/大小/最大化持久化。Task 10 进一步实现 schema/operator 驱动的 Raw Input 与 Evidence 编辑器：Raw Input 暴露 X/U/I/G/P family、source/schema/adapter/profile、字段/单位/时钟和 session availability；Evidence 暴露完整 typed recipe/operator graph、参数表单、bindings、窗口/聚合/评分/D-A-U、states、BN parent/CPT 摘要、preview/trace、used-by 与 history。C# 只构造 typed intent，不执行 Evidence 算法；不支持的 JSON 字段只读保留，缺失 operator 显式阻塞运行。完整桌面 Unit `57/57`、Contract `3/3`、Python node-service `4/4`、x64 Debug build `0 warning / 0 error`；可见验证证明文本输入不会触发图快捷键、双击可直接打开独立节点窗口，Raw Input 初始为 `Canonical · rev 0` 而非伪 dirty。Task 11 又实现 BN General/fixed parents/children/states/CPT generator/posterior-influence/used-by/history tabs、虚拟化 CPT 网格、矩形粘贴、技术诊断、expand/collapse、完整行保存、后端 materialization，以及原子 parent/state/CPT 事务。C# 只执行输入层技术检查与 typed request composition，CPT materialization、迁移、canonical persistence 和 BN inference 仍只在 Python 后端。完整桌面 Unit `61/61`、Contract `3/3`、x64 Debug build `0 warning / 0 error`；可见验证打开 `Task Control Proficiency` 独立窗口并显示 canonical `1`-row / `3`-state CPT。Task 12 才负责普通表单字段的持久 autosave/reconciliation，Task 14 才负责实际运行与 posterior/result 展示。M8 最终打包与科学验证仍未完成，starter/synthetic `formal_run_authorized=false`。完整状态见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md)。

2026-07-16 另以 repository-external 的 2,902-row 格式样例 X/U 和工程合成 I/G/EEG/ECG/pilot-camera 跑通一次完整 M6 software-test：ingestion/preflight ready、18/18 Evidence computed、exact BN inference completed、39 个结果/追踪工件成功回读且 sidecar stderr 为空。该运行继续标记 `scientific_status=not_supported`；它验证真实产品接口与计算流水线，不验证样例飞行、starter algorithms、阈值或 CPT 的科学正确性。详见 [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md)。

## 6. 维护规则

- 修改跨文档口径时，先更新 [DECISIONS.md](DECISIONS.md)，再更新受影响文档。
- 任何 run 或导出结果必须保存 exact immutable RunSnapshot 与 content hashes；不得依赖会继续变化的 current scheme/node 状态来重放历史。
- 参数、公式、计算图、拓扑、激活集合或 CPT 修改直接自动保存到 current node/scheme；无需 Draft/Published/Apply/Publish、人工审批或 per-edit 工程测试。
- 不在前端执行任意 Python。普通新 Anchor 使用 existing operators/EvidenceRecipe；只有新增 operator library 不具备的能力才安装受控 operator plugin。
- 示例中的数值必须标注为“默认工程值”“文献直接支持”或“专家校准值”之一。
- 每次设计基线发布前重新执行 [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) 中的文档自检。
