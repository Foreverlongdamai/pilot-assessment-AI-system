# Pilot Assessment System — 产品设计文档中心

| 字段 | 当前值 |
|---|---|
| 设计基线 | v0.1 |
| 基线日期 | 2026-07-10 |
| 产品阶段 | 正式设计；后端基础 M1 已实现 |
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

文档中的 v0.1 是一套**可运行参考设计**。算法、阈值、拓扑和 CPT 的默认值用于启动开发，不代表已经获得航空监管认可，也不应被表述为最终飞行员评估标准。

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
| 16 | [M2 多模态合成基础规格](specs/2026-07-11-multimodal-synthetic-foundation-design.md) | 开发、数据、审查者 | Review candidate：理想 I/G/EEG/ECG/camera 合同、合成 bundle 与 ingestion |

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
- 证据等级：Desired、Adequate、Unacceptable。missing、export_pending、invalid 和 not_applicable 是数据/适用性状态，不进入 BN，也不是第四个表现等级。
- BN 生成方向：Competency → Sub-skill → Evidence；评估时由 evidence 反推 competency posterior。
- 前端可以修改图；后端是模型状态、验证、CPT 迁移和发布的唯一权威。
- 已发布 revision 不可变；正式 run 必须锁定 revision ID 与内容 hash。non-formal run.preview 锁定 exact draft_id + graph_version，不能产生正式结果。
- 软件测试通过与科学有效性成立是两个独立结论。

## 5. 当前实现边界

截至 2026-07-11，Python Core 已实现严格 SessionManifest/StreamDescriptor/AnchorResult 合同、inspect-only directory-bundle manifest/integrity loader、结构化错误和确定性 JSON Schema。该 loader 不授权正式 import；受管理存储的同句柄验证与复制仍待实现。真实流 adapter、同步、anchor 算法、evidence scorer、BN、sidecar 和 WinUI 也尚未实现。完整状态与复现命令见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md)。

## 6. 维护规则

- 修改跨文档口径时，先更新 [DECISIONS.md](DECISIONS.md)，再更新受影响文档。
- 每个算法、阈值、拓扑或 CPT 变化都必须进入新的 model revision，并记录理由、作者、时间、差异和验证结果。
- 不在前端执行任意 Python。新算法通过受控 AnchorPlugin 安装；参数和安全公式通过 schema 编辑。
- 示例中的数值必须标注为“默认工程值”“文献直接支持”或“专家校准值”之一。
- 每次设计基线发布前重新执行 [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) 中的文档自检。
