# Pilot Assessment System — 产品设计文档中心

| 字段 | 当前值 |
|---|---|
| 设计基线 | 产品 v0.4 durable expert-designer runtime；D-031–D-046 已获用户确认 |
| 基线日期 | 2026-07-16 |
| 产品阶段 | M1/M2/M3、M4R、M5 与 M6 Local Runtime/Persistence/Sidecar 已工程验证；M7 WinUI 与 M8 packaging 尚未实现；starter/synthetic `formal_run_authorized=false` |
| 运行范围 | Windows 本地、离线 session 评估 |
| 科学状态 | 参考模型待领域专家校准与验证 |
| 权威范围 | pilot_assessment_system 的产品设计与实现约束 |

## 1. 文档用途

本目录是产品交付、开发、审查和后续专家配置的统一入口。它回答五类问题：

1. 产品解决什么问题、明确不解决什么问题；
2. 原始 session 如何进入系统并保持多模态时间一致；
3. 专家如何用全局不可变组件版本、任务评估方案、可编辑 EvidenceRecipe 和 BN 组合任意任务模型；
4. Windows 前端如何展示并修改节点、边、参数和 CPT；
5. 如何验证软件、校准评估模型并把产品交给下一位维护者。

文档中的 Hover、O1–O13、H1–H5 和 33-node BN 是一套**可编辑 starter template**。算法、阈值、拓扑和 CPT 只用于启动系统与给专家提供示例；产品不以证明它们科学正确为目标。专家可以在全局组件库中新增任意 Evidence/BN concepts 和并行 immutable versions，再由不同 `AssessmentSchemeVersion` 选择 exact versions。书面设计、实施计划、代码实现、工程可运行与科学有效性是不同状态，不能相互替代。

## 2. 推荐阅读顺序

| 顺序 | 文档 | 主要读者 | 内容 |
|---:|---|---|---|
| 1 | [01_PRODUCT_OVERVIEW.md](01_PRODUCT_OVERVIEW.md) | 所有人 | 产品边界、角色、工作流和总架构 |
| 2 | [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) | 专家、产品、前后端 | 当前系统核心：全局组件版本库、任务方案、三类节点、两类边、BN 方向与 publish 语义 |
| 3 | [M5 Implementation Plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) | 开发、审查者 | 已完成：inline 任务、合同冻结、O8 迁移、轻量验证与完成门 |
| 4 | [M6 Local Runtime, Durable Persistence and Sidecar Protocol Design](specs/2026-07-16-m6-local-runtime-persistence-and-protocol-design.md) | 前后端、交付、审查者 | 已实现：受管项目、SQLite、artifact、run lifecycle 与 JSON-RPC sidecar |
| 5 | [M6 Implementation Plan](plans/2026-07-16-m6-local-runtime-persistence-and-sidecar-implementation-plan.md) | 开发、审查者 | 已完成：15 个 INLINE 任务、轻量 test-first、focused smoke 与完成门 |
| 6 | [03_SESSION_BUNDLE_SPEC.md](03_SESSION_BUNDLE_SPEC.md) | 数据与后端 | X/U/VR/gaze/EEG/ECG 数据合同与同步 |
| 7 | [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md) | 领域专家、算法 | 18 个 starter anchor 的算法和初始参数 |
| 8 | [05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md](05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md) | 算法、后端 | BN 拓扑、状态、CPT、缺失证据和解释 |
| 9 | [02_ASSESSMENT_CORE_DESIGN.md](02_ASSESSMENT_CORE_DESIGN.md) | 后端开发 | 模块边界与完整计算流水线 |
| 10 | [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) | 前后端开发 | 三类节点、两类边、拖拽编辑、事务和 CPT 迁移 |
| 11 | [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) | 前后端开发 | sidecar 生命周期与 JSON-RPC 合同 |
| 12 | [08_WINDOWS_FRONTEND_DESIGN.md](08_WINDOWS_FRONTEND_DESIGN.md) | UI/UX、前端 | 页面、交互、可视化和错误恢复 |
| 13 | [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) | 测试、交付 | 验证层级、验收门槛和移交清单 |
| 14 | [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) | 开发、接手者 | 当前代码、验证证据、限制和下一里程碑 |
| 15 | [DECISIONS.md](DECISIONS.md) | 维护者 | 已锁定决策及其理由 |
| 16 | [GLOSSARY.md](GLOSSARY.md) | 所有人 | 术语、ID 和状态语义 |
| 17 | [REFERENCES.md](REFERENCES.md) | 审查者、领域专家 | 公开文献、DOI 与证据用途 |
| 18 | [10_DESIGN_SELF_REVIEW.md](10_DESIGN_SELF_REVIEW.md) | 审查者 | 本轮设计自审、发现和遗留风险 |
| 19 | [后端 M1 实施计划](plans/2026-07-11-backend-foundation-m1-implementation-plan.md) | 开发、审查者 | RED/GREEN 任务、范围和完成定义 |
| 20 | [M2 多模态合成基础规格](specs/2026-07-11-multimodal-synthetic-foundation-design.md) | 开发、数据、审查者 | 已批准：理想 I/G/EEG/ECG/camera 合同、合成 bundle 与 ingestion readiness |
| 21 | [M2 实施计划](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md) | 开发、审查者 | shared X/U、adapter、generator、readiness 与本地 E2E 的 TDD 步骤 |
| 22 | [M3 Native-Rate Time Synchronization 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) | 开发、数据、审查者 | 已批准：native-rate clock mapping、session window、aligned views 与同步报告 |
| 23 | [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) | 开发、审查者 | 已完成：Task 0–14 的实现、实测完成门与 handoff/关闭记录 |
| 24 | [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md) | 专家、产品、前后端 | typed EvidenceRecipe/operator graph、自动参数表单、autosave draft + apply、最小技术校验、M4R–M8 重基线 |
| 25 | [M4R Editable Evidence Computation Foundation Implementation Plan](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md) | 开发、审查者 | 已完成：合同、registry、validator、compiler/executor、recipe 生命周期、18 个 starter resources 与轻量 E2E |
| 26 | [M4 Anchor Calculation and Evidence Availability 规格](specs/2026-07-13-m4-anchor-evidence-availability-design.md) | 开发、算法、审查者 | 历史/迁移规格：Task 0–28 与 15 个插件已实现；固定插件和 completion gate 已由 2026-07-15 新规格取代 |
| 27 | [M4 原实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) | 开发、算法、审查者 | 历史计划，已被取代且不得执行 |
| 28 | [M4 轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md) | 开发、算法、审查者 | 历史 fixed-plugin 验证修订；不再定义 M4R completion gate |
| 29 | [M4 replacement 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) | 开发、算法、审查者 | Task 0–28 已完成；Task 29–36 已停止且不得执行 |
| 30 | [M4 Task 3 Reference Candidate Binding 修订](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md) | 开发、数据、审查者 | 已实现的 session/reference binding 合同，继续保留 |
| 31 | [M4 Task 7 Catalog and Resource Identity 修订](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md) | 开发、算法、审查者 | 已实现的 legacy catalog/resource identity，供迁移与 replay |
| 32 | [M4 Task 8 Canonical Fingerprint and Runtime Identity 修订](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) | 开发、审查者 | 已实现的 legacy canonical/runtime identity，供迁移与 replay |
| 33 | [Autonomous Review Ledger](reviews/2026-07-13-autonomous-review-ledger.md) | 维护者、审查者 | 保存历史复核与关闭证据 |
| 34 | [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md) | 开发、数据、审查者 | 已执行：格式样例 X/U + 合成缺失模态经完整 M6 后端运行；仅证明软件闭环 |
| 35 | [Captured-Format Multimodal Software Demo Plan](plans/2026-07-16-external-multimodal-session-demo-implementation-plan.md) | 开发、接手者 | 已完成：轻量生成、真实故障定位、18/18 Evidence、BN 推理与结果路径 |

### 2.1 文档目录的职责

- `docs/product/` 根目录中的编号文档、`DECISIONS.md` 和 `GLOSSARY.md` 是当前产品基线；
- `docs/product/specs/` 保存单个里程碑或子系统的状态受控设计合同，只有标记为“已批准”的规格才进入实施；
- `docs/product/plans/` 保存从已批准规格派生的实施步骤、选择性测试策略、验证命令和提交边界，计划不能覆盖 `DECISIONS.md` 或已批准规格；完成后继续保留，作为产品如何实现和验证的移交证据。
- `docs/product/reviews/` 保存规格、计划和实现检查点的复核 ledger；它不取代正式决策、测试或 Git 历史。

## 3. 权威性规则

发生冲突时按以下优先级处理：

1. 本目录中状态为“当前”的正式产品文档；
2. 已发布 scheme/component versions 及其 portable bundle manifest、schema 和参数；
3. 产品代码与自动化测试；
4. 研究阶段的 PPT、讨论稿和历史说明。

历史草案 [2026-07-08-backend-core-runtime-adapter-design.md](../superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md) 仅用于说明设计演进。其 FastAPI、H1–H6、CSV-only 或不可编辑拓扑等旧假设不能覆盖本基线。

## 4. 当前锁定口径

- 原始数据族：X(t) 飞行状态、U(t) 控制输入、I(t) 飞行员在 VR 中实际看到的第一视角场景、G(t) 在该动态场景上的 gaze/AOI、P(t) 生理信号（至少 EEG 与 ECG）。
- Starter template：O1–O13 与 H1–H5 共 18 个示例 evidence；通用 engine 和 expert model 不限制数量，专家可新增、复制、disabled、retired 或替换。
- 顶层输出：TCP、PC、SM、OC 四项 aggregate competencies；中间层为 11 个 latent sub-skills。
- 证据等级：Desired、Adequate、Unacceptable。`computed + Unacceptable` 是有效负面 evidence，raw availability 与 computed D/A 一样为 1；coverage/availability 表示证据是否形成，不表示表现好坏。
- `export_pending/missing/invalid/not_applicable` 是 M1–M3 的 stream 生命周期或结构状态；M4 AnchorResult v0.2 的非 computed 状态固定为 `missing_input/not_applicable/not_computable/dependency_missing/extractor_error`，M4 不生成 `invalid_quality`。
- M4 假定进入它的 aligned input 已满足上游结构合同，不判断原始采集“质量够不够好”，也不因 coverage、gap、噪声、幅值、生理范围或差表现过滤 evidence；这些技术统计只进入 diagnostics/provenance。
- 全局模型库使用 `Concept + immutable Version`；方案和 run 锁定 exact version IDs/content hashes，不引用 `latest`，发布采用 copy-on-write 且不覆盖旧方案。
- 高层工作区只显示 Raw Input、Evidence、BN Node 三类节点；`Raw/task source → Evidence` 是 data/extraction edge，Raw Input 不属于 BN；probabilistic edge 才表示 `P(child | parents)`。
- Hover starter 的 canonical BN 生成方向为 Competency → Sub-skill → Evidence；评估时由 observed evidence 计算 competency posterior。只读 inference overlay 可以显示反向信息影响，但不得反转已存 BN edges。
- 通用引擎允许专家发布其他合法 DAG，但它是新的概率模型版本，不是同一图的显示反转。
- 专家通过前端决定模型内容；后端维护模型 canonical 状态、最小技术校验、CPT 迁移、版本签发和执行一致性，但不拥有科学内容决定权。
- 已发布 component/scheme versions 不可变；正式 run 必须锁定 exact version IDs 与内容 hashes。non-formal run.preview 锁定 exact draft_id + graph_version，不能产生正式结果。
- 软件测试通过与科学有效性成立是两个独立结论。
- 当前 repository-external 2,902-row simulator CSV 只是一次随意飞行产生的采集格式样例，仅用于接口、解析、时间和软件 E2E；它不是标准轨迹、任务 ground truth、专家 phase annotation 或能力证据。围绕它生成的 reference/annotations/biometrics 也只是 synthetic fixtures。

## 5. 当前实现边界

截至 2026-07-13，Python Core 已完成 M1、M2 与 M3：严格 SessionManifest/StreamDescriptor/legacy AnchorResult 0.1 合同、inspect-only directory-bundle integrity gate、shared X/U、版本化 profiles/adapters、deterministic multimodal generator、`IngestionReadinessReport`，以及 native-rate `AlignedSession`/`SynchronizationReport`。M3 使用 master-clock X mapped coverage、Decimal round-half-even 与版本化 temporal bindings，保留所有 source rows，并输出确定性的 synchronization fingerprint；它不插值、不重采样，也不建立全局或 anchor window grid。完成门实测仍为 `694 passed, 2 skipped`，配置 repository-external CSV 后 M2/M3 格式样例 E2E 为 `2 passed`，隔离 wheel 的 M3 micro E2E 为 `1 passed`。这些结果不验证样例飞行的任务、表现或科学有效性；M2/M3 report 始终保持 `formal_run_authorized=false`，synthetic fixture 为 `not_supported`。

旧 M4 replacement Task 0–28 已完成并保留为历史迁移资产。2026-07-15 用户确认产品应首先服务专家自由设计 Evidence 和 BN，接受 D-031–D-035 与 EvidenceRecipe/operator architecture，并批准正式规格和 replacement M4R plan。M4R 现已实现 canonical contracts/schema、trusted operator catalog、only-technical validator、generic compiler/executor、backend-only draft/preview/apply/replay、18 个可编辑 starter recipes 和轻量 E2E；任意第 19 个 recipe 无需 Anchor-ID 分支即可注册和运行。15 个旧插件继续作为 legacy/reference，H4/H5/O13 使用 operator composition 而没有新增 whole-Anchor plugin。2026-07-16 用户进一步确认 D-036–D-040：全局 immutable component versions、exact-pinned task schemes、三类节点/两类边、starter canonical BN 与 posterior inference flow 的区分，以及 legacy Evidence-to-Evidence extraction 的非覆盖迁移规则。M5 已完成 generic identity、model/BN/scheme/inference public DTO、16 类双目录 Draft 2020-12 schema、typed source/M4R preflight、global exact-version repository/service、exact-pinned scheme closure/technical validation、typed scheme operations、incomplete autosave、undo/redo、copy-on-write atomic publish、exact replay、generic CPT validation/materialization/migration、finite-discrete exact inference/read-only influence trace、17 个 compatible M4R active imports/同 concept compliant TPX parallel version、checksummed Hover starter BN package，以及 read-only draft preview/posterior/influence/copy-on-write publish/replay workflow。该 starter 物化 4 个 competency、11 个 sub-skill、18 个 Evidence binding 与 33 张工程默认 CPT，全部可由专家另行 clone/修改；这些数量未进入 generic loader。旧 O8 原 bytes/hash 仍作为 legacy/replay 资产保留。

M6 completion gate 也已关闭：受管 project/session/artifact、SQLite component/draft/run persistence、idempotency/audit、exact technical preflight、dynamic Evidence→Observation→BN pipeline、single-worker progress/cancel/recovery，以及无网络端口的 JSON-RPC/JSONL stdio sidecar 均已实现。轻量纵向闭环证明 external bundle 删除后仍可从受管副本运行，整个 project 换目录重开后 exact scheme/result/artifact 仍可回放。下一里程碑是 M7 WinUI Expert Designer；M8 最终打包与科学验证仍未完成，starter/synthetic `formal_run_authorized=false`。完整状态见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md)。

2026-07-16 另以 repository-external 的 2,902-row 格式样例 X/U 和工程合成 I/G/EEG/ECG/pilot-camera 跑通一次完整 M6 software-test：ingestion/preflight ready、18/18 Evidence computed、exact BN inference completed、39 个结果/追踪工件成功回读且 sidecar stderr 为空。该运行继续标记 `scientific_status=not_supported`；它验证真实产品接口与计算流水线，不验证样例飞行、starter algorithms、阈值或 CPT 的科学正确性。详见 [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md)。

## 6. 维护规则

- 修改跨文档口径时，先更新 [DECISIONS.md](DECISIONS.md)，再更新受影响文档。
- 任何方案、run 或导出结果必须保存 exact component version IDs 与 content hashes；不得用 `latest` 代替可重放身份。
- 参数、公式、计算图、拓扑或 CPT 修改自动保存到 draft；点击 apply 后 copy-on-write 创建新 component/scheme versions。无需人工审批或 per-edit 工程测试。
- 不在前端执行任意 Python。普通新 Anchor 使用 existing operators/EvidenceRecipe；只有新增 operator library 不具备的能力才安装受控 operator plugin。
- 示例中的数值必须标注为“默认工程值”“文献直接支持”或“专家校准值”之一。
- 每次设计基线发布前重新执行 [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) 中的文档自检。
