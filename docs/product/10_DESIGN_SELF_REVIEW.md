# Design Self-Review Report

| 字段 | 值 |
|---|---|
| 设计基线 | v0.1 |
| 审查日期 | 2026-07-10 |
| 审查范围 | pilot_assessment_system 产品文档、项目入口说明、历史草案状态 |
| 结论 | 设计文档可作为实现与交接基线 |
| 软件状态 | 2026-07-10 审查时尚无实现；截至 2026-07-12，M1/M2/M3 后端里程碑已完成工程验证，完整 Core alpha 与 Gate B 仍未完成，见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) |
| 科学状态 | 参考评估模型为 engineering_default；synthetic fixture 为 not_supported |

## 1. 结论边界

本文固定记录 2026-07-10 的**产品与计算设计闭环**审查，表格中的审查日期不随实现推进而改写；当前实现状态仅作后续注记。本文不是软件实现验收，也不是航空评估科学有效性证明。后续实现证据以 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) 为准。

通过本轮自审后，文档已经能够让接手者明确：

- 系统处理哪些 session 数据，特别是 I(t)、G(t)、EEG、ECG 和 pilot camera；
- 18 个 reference anchors 如何计算、聚合、评分和处理缺失；
- 33-node reference BN 如何定义 state、CPT、共享 evidence、coverage 和解释；
- 用户如何在 WinUI 中新增、删除、移动 node/edge，并修改 binding、参数和 CPT；
- 后端如何以 draft transaction、graph_version、layout_version 和 immutable revision 保持一一对应；
- 正式 run、non-formal preview、结果 provenance 和验证状态如何区分。

结论“可作为实现基线”只表示没有已知的 P0/P1 设计矛盾；默认阈值、拓扑和 CPT 仍等待专家与数据校准。

## 2. 审查方法

执行了三层审查：

1. 主审：逐文档核对产品、数据、anchor、BN、graph editor、runtime、frontend 与验证合同；
2. 独立审查：由不负责最终整合的审查任务检查公式、状态、协议、链接和运行边界；
3. 机器检查：解析 JSON/YAML 示例、检查 Markdown fence/相对链接、统计 model IDs，并搜索旧口径和占位符。

严重度定义：

- P0：会使产品目标、数据安全或模型结论根本错误；
- P1：会让两个合规实现得到不同结果，或使跨组件合同无法闭环；
- P2：不阻断实现，但影响可维护性、体验或后续扩展。

## 3. 已发现并关闭的问题

| ID | 问题 | 处理结果 |
|---|---|---|
| SR-01 | 根说明仍使用 FastAPI、H1–H6、旧目录和 CSV-only 边界 | 更新 CLAUDE.md；历史草案标记 SUPERSEDED |
| SR-02 | 18/19 anchor、O2/O4/H4/H5/H6 口径漂移 | 锁定 O1–O13 + H1–H5；旧 H6 删除 |
| SR-03 | Competency state 与单父 CPT 初值不一致 | 锁定 at_risk/developing/proficient 和 0.79/0.20/0.01 等默认表 |
| SR-04 | 同一 anchor 的 phase observation 可能重复注入 BN | v0.1 每 anchor 每 session 只提交一个聚合 observation；phase 只保留 breakdown |
| SR-05 | missing/export_pending/invalid/not_applicable 与 BN state 混用 | 建立 stream → AnchorResult → observation_mode 映射；全部在 BN 外处理 |
| SR-06 | draft、published revision、科学状态和 permitted use 混装 | 拆成 draft_validation_state、revision_lifecycle、verification/scientific status 与 permitted_use |
| SR-07 | graph/CPT/anchor 参数使用不同版本与写路径 | 所有 semantic mutation 共用 graph_version 和 graph.operations.apply；layout_version 独立 |
| SR-08 | mutation 重试可能重复执行 | 所有 mutation 使用 transaction_id 兼作 idempotency key |
| SR-09 | 新增/删除 edge 与 state change 的 CPT 迁移不唯一 | 定义 neutral replication、weighted marginalization、M/R/q state migration 与 preview |
| SR-10 | Advanced DAG 可能造成 CPT 指数爆炸 | 后端硬限制 parent、rows、cells 和 serialized size |
| SR-11 | 新 evidence node 没有后端 binding 闭环 | 增加 AnchorBinding DTO、binding operations、safe formula 和 trusted plugin 流程 |
| SR-12 | 节点拖拽位置与科学模型版本混用 | 定义 layout.update、expected_layout_version、批量 drag-end 提交和 layout hash |
| SR-13 | draft preview 可能被当作正式结果 | run.start 仅接受 published revision；run.preview 固定 draft_id+graph_version 且 non_formal |
| SR-14 | AnchorResult 缺连续分数、likelihood、质量和逐窗 artifact 的确定规则 | 定义 hard_threshold_v1、ordinal_expectation_v1、binary_quality_v1 和统一 artifact contract |
| SR-15 | 多 phase/event/window anchor 缺唯一 session 聚合 | 为 O1/O10/O11/O12/O13/H1/H2/H3/H4/H5 明确聚合 |
| SR-16 | O13 使用 session scalar 会退化，且 high/base 选择可能重叠 | 定义共享 window grid、逐窗 O1/O5/O7、唯一 activation_mode、join 和 denominator gate |
| SR-17 | O3/O5/O10/O11/O12 数字实现仍有可选起点或 detector 歧义 | 锁定 start mode、滤波/导数/zero-point、通道/方向 mapping、deadband 和完整观察窗 |
| SR-18 | H5 通道、频带、PSD 与窗口聚合不唯一 | 锁定 channel selection、median aggregation、Welch、bands 和 phase/session 聚合 |
| SR-19 | EDF 在 UI 与 session 规范中不一致 | session contract 增加 EDF/EDF+ 与 sidecar metadata |
| SR-20 | 本地绝对论文路径无法随产品交付 | 新增 REFERENCES.md，改用 DOI、出版社、机构仓储和 arXiv 稳定入口 |
| SR-21 | O9 所需 hover masks 没有 producer/schema/grid | O1/O4 输出同一 aligned-state-grid-v1 masks，O9 明确 join 和同步门槛 |
| SR-22 | H1–H3 依赖 fixation，但 detector、角度单位、重复时间戳和零分母未定义 | session contract 锁定 fixation-v1 I-VT、rad-to-deg 与 dedup；H1/H3 要求 valid fixation dwell >0 |
| SR-23 | H5 baseline engagement 可能除零 | 增加 band-power epsilon、finite E0 与 engagement_epsilon quality gates |

## 4. 结构与机器检查

最终基线应满足以下检查；本轮已执行：

- product 文档全部 UTF-8 可读，Markdown fence 成对；
- 所有 fenced JSON 示例可由 JSON parser 解析；
- 所有 fenced YAML 示例可由 YAML parser 解析；
- sample manifest 可解析，包含 X、U、I、G、EEG、ECG、pilot_camera 七个 descriptor；
- reference anchor headings 为 18/18 unique；
- sub-skill mapping 为 11/11 unique；
- BN evidence table 为 18/18 unique；
- shared evidence parents 与 O1/O2/O7/O11/O12/H1 设计一致；
- competency prior 和三行默认 CPT 概率和均为 1；
- 产品文档内部相对链接有效；
- 无 TODO、TBD、FIXME 或 PLACEHOLDER；
- 无开发者电脑绝对路径；
- 旧 FastAPI/H1–H6/19-node/只读拓扑只出现在明确的历史否定语境。

## 5. 尚存但不阻断设计交接的风险

### 5.1 科学风险

- 绝大多数阈值、CPT、coverage cutoffs 和部分 anchor 是工程默认；
- 4 competencies、11 sub-skills 与共享 evidence mapping 尚需领域专家内容审查；
- posterior calibration、重复性、known-groups validity 和外部有效性尚未研究；
- default model 只能标记 engineering_default。

### 5.2 数据风险

- I/G/EEG/ECG/pilot_camera 的真实导出文件和设备 metadata 尚未形成最终样本 bundle；
- reference trajectory、phase/event、response mapping 和 baseline 的实际生产流程仍需实验团队确认；
- 生理与图像数据涉及敏感信息，交付前需要项目级同意、脱敏和保留策略。

### 5.3 实现风险

- M1/M2/M3 已有正式代码、四份 public schema、版本化 profile/binding catalog、自动化测试和 Git history；
- M3 的 public report、clock/annotation/reference、deterministic fingerprint 与 golden E2E 已通过工程完成门；M4 的 18 个 AnchorPlugin、evidence availability 与 anchor-specific grids 尚未实现；
- WinUI graph control、无障碍和大 CPT 编辑体验需要原型；
- Python/.NET 打包、插件签名、升级和 crash recovery 需要实际验证。

## 6. 下一阶段入口

截至 2026-07-12，backend M1 contracts/integrity、M2 multimodal ingestion foundation 与 M3 native-rate synchronization 已完成工程验证；[M3 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) 和 [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) 保留完整设计与实测证据。下一阶段是 M4 Anchor/evidence availability：实现 18 个 AnchorPlugin、各自的 analysis/window grid、插值/重采样 policy 和 availability/quality gate，之后再进入 BN adapter、runtime 与 WinUI。前端可以用 fake backend 并行开发，但不能另建一套模型状态。

任何专家修改都通过新 draft/revision 完成；不需要重新修改本设计中的 Python 业务结构。
