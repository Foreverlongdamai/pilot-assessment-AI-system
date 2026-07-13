# Pilot Assessment System — 产品设计文档中心

| 字段 | 当前值 |
|---|---|
| 设计基线 | 产品 v0.1；M4 AnchorResult/计算规格 v0.2 与轻量验证修订均已于 2026-07-13 获用户批准 |
| 基线日期 | 2026-07-13 |
| 产品阶段 | M1/M2/M3 后端里程碑已工程验证；M4 replacement Task 0 已由 `bc544bf` 完成，Task 1 尚未开始；18/18 anchor 已设计，0/18 production plugins 已实现；M4 尚未工程验证 |
| 运行范围 | Windows 本地、离线 session 评估 |
| 科学状态 | 参考模型待领域专家校准与验证 |
| 权威范围 | pilot_assessment_system 的产品设计与实现约束 |

## 1. 文档用途

本目录是产品交付、开发、审查和后续专家配置的统一入口。它回答五类问题：

1. 产品解决什么问题、明确不解决什么问题；
2. 原始 session 如何进入系统并保持多模态时间一致；
3. 18 个 evidence anchors 如何形成，贝叶斯网络如何推理；
4. Windows 前端如何展示并修改节点、边、参数和 CPT；
5. 如何验证软件、校准评估模型并把产品交给下一位维护者。

文档中的 v0.1 是一套**可实现参考设计**。算法、阈值、拓扑和 CPT 的默认值用于启动开发，不代表已经获得航空监管认可，也不应被表述为最终飞行员评估标准。书面设计、实施计划、代码实现和工程验证是四种不同状态，不能相互替代。

## 2. 推荐阅读顺序

| 顺序 | 文档 | 主要读者 | 内容 |
|---:|---|---|---|
| 1 | [01_PRODUCT_OVERVIEW.md](01_PRODUCT_OVERVIEW.md) | 所有人 | 产品边界、角色、工作流和总架构 |
| 2 | [03_SESSION_BUNDLE_SPEC.md](03_SESSION_BUNDLE_SPEC.md) | 数据与后端 | X/U/VR/gaze/EEG/ECG 数据合同与同步 |
| 3 | [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md) | 领域专家、算法 | 18 个 anchor 的算法和初始参数 |
| 4 | [05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md](05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md) | 算法、后端 | BN 拓扑、状态、CPT、缺失证据和解释 |
| 5 | [02_ASSESSMENT_CORE_DESIGN.md](02_ASSESSMENT_CORE_DESIGN.md) | 后端开发 | 模块边界与完整计算流水线 |
| 6 | [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) | 前后端开发 | 拖拽编辑节点/边、事务和 CPT 迁移 |
| 7 | [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) | 前后端开发 | sidecar 生命周期与 JSON-RPC 合同 |
| 8 | [08_WINDOWS_FRONTEND_DESIGN.md](08_WINDOWS_FRONTEND_DESIGN.md) | UI/UX、前端 | 页面、交互、可视化和错误恢复 |
| 9 | [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) | 测试、交付 | 验证层级、验收门槛和移交清单 |
| 10 | [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) | 开发、接手者 | 当前代码、验证证据、限制和下一里程碑 |
| 11 | [DECISIONS.md](DECISIONS.md) | 维护者 | 已锁定决策及其理由 |
| 12 | [GLOSSARY.md](GLOSSARY.md) | 所有人 | 术语、ID 和状态语义 |
| 13 | [REFERENCES.md](REFERENCES.md) | 审查者、领域专家 | 公开文献、DOI 与证据用途 |
| 14 | [10_DESIGN_SELF_REVIEW.md](10_DESIGN_SELF_REVIEW.md) | 审查者 | 本轮设计自审、发现和遗留风险 |
| 15 | [后端 M1 实施计划](plans/2026-07-11-backend-foundation-m1-implementation-plan.md) | 开发、审查者 | RED/GREEN 任务、范围和完成定义 |
| 16 | [M2 多模态合成基础规格](specs/2026-07-11-multimodal-synthetic-foundation-design.md) | 开发、数据、审查者 | 已批准：理想 I/G/EEG/ECG/camera 合同、合成 bundle 与 ingestion readiness |
| 17 | [M2 实施计划](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md) | 开发、审查者 | shared X/U、adapter、generator、readiness 与本地 E2E 的 TDD 步骤 |
| 18 | [M3 Native-Rate Time Synchronization 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) | 开发、数据、审查者 | 已批准：native-rate clock mapping、session window、aligned views 与同步报告 |
| 19 | [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) | 开发、审查者 | 已完成：Task 0–14 的实现、实测完成门与 handoff/关闭记录 |
| 20 | [M4 Anchor Calculation and Evidence Availability 规格](specs/2026-07-13-m4-anchor-evidence-availability-design.md) | 开发、算法、审查者 | 已批准：AnchorResult v0.2、18 个 anchor、no-quality-gate、DAG、artifact/fingerprint 与 fixtures；18/18 已设计、0/18 production plugins 已实现 |
| 21 | [M4 原实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) | 开发、算法、审查者 | 历史上已批准，现已被轻量验证修订取代且不得执行；其 provisional heavy Task 0 未提交且未进入历史 |
| 22 | [M4 轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md) | 开发、算法、审查者 | 已批准：以单个 10 秒全模态 bundle、per-anchor 微型测试和紧凑场景取代四套 90 秒重 fixture |
| 23 | [M4 replacement 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) | 开发、算法、审查者 | 已于 2026-07-13 获用户批准；Task 0 已由 `bc544bf` 完成，Task 1 尚未开始 |

### 2.1 文档目录的职责

- `docs/product/` 根目录中的编号文档、`DECISIONS.md` 和 `GLOSSARY.md` 是当前产品基线；
- `docs/product/specs/` 保存单个里程碑或子系统的状态受控设计合同，只有标记为“已批准”的规格才进入实施；
- `docs/product/plans/` 保存从已批准规格派生的 TDD 实施步骤、验证命令和提交边界，计划不能覆盖 `DECISIONS.md` 或已批准规格；完成后继续保留，作为产品如何实现和验证的移交证据。

## 3. 权威性规则

发生冲突时按以下优先级处理：

1. 本目录中状态为“当前”的正式产品文档；
2. 已发布 model bundle 内的 manifest、schema 和参数；
3. 产品代码与自动化测试；
4. 研究阶段的 PPT、讨论稿和历史说明。

历史草案 [2026-07-08-backend-core-runtime-adapter-design.md](../superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md) 仅用于说明设计演进。其 FastAPI、H1–H6、CSV-only 或不可编辑拓扑等旧假设不能覆盖本基线。

## 4. 当前锁定口径

- 原始数据族：X(t) 飞行状态、U(t) 控制输入、I(t) 飞行员在 VR 中实际看到的第一视角场景、G(t) 在该动态场景上的 gaze/AOI、P(t) 生理信号（至少 EEG 与 ECG）。
- 参考模型：O1–O13 与 H1–H5，共 18 个逻辑 evidence nodes；O1 的 T/D/H 分段值保留在节点内部。
- 顶层输出：TCP、PC、SM、OC 四项 aggregate competencies；中间层为 11 个 latent sub-skills。
- 证据等级：Desired、Adequate、Unacceptable。`computed + Unacceptable` 是有效负面 evidence，raw availability 与 computed D/A 一样为 1；coverage/availability 表示证据是否形成，不表示表现好坏。
- `export_pending/missing/invalid/not_applicable` 是 M1–M3 的 stream 生命周期或结构状态；M4 AnchorResult v0.2 的非 computed 状态固定为 `missing_input/not_applicable/not_computable/dependency_missing/extractor_error`，M4 不生成 `invalid_quality`。
- M4 假定进入它的 aligned input 已满足上游结构合同，不判断原始采集“质量够不够好”，也不因 coverage、gap、噪声、幅值、生理范围或差表现过滤 evidence；这些技术统计只进入 diagnostics/provenance。
- BN 生成方向：Competency → Sub-skill → Evidence；评估时由 evidence 反推 competency posterior。
- 前端可以修改图；后端是模型状态、验证、CPT 迁移和发布的唯一权威。
- 已发布 revision 不可变；正式 run 必须锁定 revision ID 与内容 hash。non-formal run.preview 锁定 exact draft_id + graph_version，不能产生正式结果。
- 软件测试通过与科学有效性成立是两个独立结论。
- 当前 repository-external 2,902-row simulator CSV 只是一次随意飞行产生的采集格式样例，仅用于接口、解析、时间和软件 E2E；它不是标准轨迹、任务 ground truth、专家 phase annotation 或能力证据。围绕它生成的 reference/annotations/biometrics 也只是 synthetic fixtures。

## 5. 当前实现边界

截至 2026-07-13，Python Core 已完成 M1、M2 与 M3：严格 SessionManifest/StreamDescriptor/legacy AnchorResult 0.1 合同、inspect-only directory-bundle integrity gate、shared X/U、版本化 profiles/adapters、deterministic multimodal generator、`IngestionReadinessReport`，以及 native-rate `AlignedSession`/`SynchronizationReport`。M3 使用 master-clock X mapped coverage、Decimal round-half-even 与版本化 temporal bindings，保留所有 source rows，并输出确定性的 synchronization fingerprint；它不插值、不重采样，也不建立全局或 anchor window grid。完成门实测仍为 `694 passed, 2 skipped`，配置 repository-external CSV 后 M2/M3 格式样例 E2E 为 `2 passed`，隔离 wheel 的 M3 micro E2E 为 `1 passed`。这些结果不验证样例飞行的任务、表现或科学有效性；M2/M3 report 始终保持 `formal_run_authorized=false`，synthetic fixture 为 `not_supported`。

M4 正式书面规格、[轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md) 与 [replacement plan](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 均已批准，D-026/D-027 已接受。Replacement Task 0 已由 `bc544bf` 完成：旧 provisional heavy fixture 未进入提交历史；新的 10 秒 input-only fixture 以 452 PNG、468 个 manifest declared-path references 和 9,331 行 physical source tables 通过公开 M1→M2→M3 gate，聚焦测试为 `6 passed in 9.36s`。Task 1 尚未开始，`src/pilot_assessment/anchors/` 仍不存在，因此真实状态是 18/18 anchor 已设计、0/18 production plugins 已实现，M4 尚未 engineering verified。AnchorResult v0.2、AnchorPlugin registry/DAG、anchor-specific grids、evidence scorer、artifact/report 和 fingerprints 尚未进入生产代码；受管理存储 importer、BN、runner、sidecar 和 WinUI 同样尚未实现。完整状态见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md)。

## 6. 维护规则

- 修改跨文档口径时，先更新 [DECISIONS.md](DECISIONS.md)，再更新受影响文档。
- 每个算法、阈值、拓扑或 CPT 变化都必须进入新的 model revision，并记录理由、作者、时间、差异和验证结果。
- 不在前端执行任意 Python。新算法通过受控 AnchorPlugin 安装；参数和安全公式通过 schema 编辑。
- 示例中的数值必须标注为“默认工程值”“文献直接支持”或“专家校准值”之一。
- 每次设计基线发布前重新执行 [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) 中的文档自检。
