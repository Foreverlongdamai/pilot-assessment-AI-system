# Validation and Handoff

| 字段 | 值 |
|---|---|
| 设计版本 | v0.8 portable/documentation engineering baseline |
| 当前软件状态 | in_progress（M1–M8B、M8C-0 与 M8D engineering verified；M7 user acceptance pending；D-055、M8C-1/M8E 未完成；starter/synthetic `formal_run_authorized=false`） |
| 当前科学状态 | 参考评估模型为 engineering_default；synthetic fixture 为 not_supported |
| 目的 | 定义验证门槛、证据、交付物和接手方式 |

> **当前权威补充：** M5/M6/M7 工程测试只证明已实现平台、built-in operators、recipe/inference executor、persistence/protocol、current-node/task-activation 和 WinUI 映射按合同工作；它不评判专家 recipe、Anchor、阈值或 CPT 是否科学合理，也不能替代用户亲自验收 M7。M7 编辑先进入后端持久 edit session，不设业务发布门；主窗口关闭时统一保存或放弃。dirty 草稿禁止 preview/preflight/run，clean canonical workspace 的 run preflight 只执行最小技术校验并自动冻结 RunSnapshot。继续使用小型平台不变量和手算 BN，不建立重型多模态 fixtures。M8A/M8B 已提供 portable runtime、system-owned model library、editable Python/source identity 与 operator handoff；M8C-0 已提供受控文档 pipeline；M8D 已提供 current-system packaging、project portability 与 compatibility Diagnostics。正常模型编辑继续走前端，现有方法不足时才直接修改发布目录中的全局 Python backend source。D-077 已取消专用 backup/restore；M8E 与 M7 用户验收仍未关闭。详见 [M8D 规格](./specs/2026-07-21-m8d-current-system-packaging-project-portability-and-diagnostics-design.md)、[M8B 规格](./specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md)、[M8C 规格](./specs/2026-07-21-m8c-documentation-system-design.md) 与 [Implementation Status](./11_IMPLEMENTATION_STATUS.md)。

M5 的 D-040 migration smoke 已对全部 M4R recipe source bindings 执行 generic provenance closure：旧 `starter.o8` 因 Evidence observation input 被保留但拒绝 active import，新 raw/session/task-derived TPX parallel version 可执行。该 smoke 不比较两版 provisional 数值，也没有按 O8 ID 写特判。

## 1. 两条独立的验证轴

系统必须同时报告但绝不能混淆：

### 1.1 Software verification

回答“软件是否按声明的合同正确计算”。它覆盖 schema、同步、算法实现、概率计算、事务、协议、UI 和可重现性。

建议状态：

- not_started；
- in_progress；
- verified_for_reference_v0_1；
- failed；
- superseded。

### 1.2 Scientific validation

回答“这些 anchor、阈值、技能映射、CPT 和后验是否真实、可靠、可推广地反映飞行员表现”。它需要领域专家、真实样本和统计研究。

建议状态：

- engineering_default；
- expert_reviewed；
- calibrated；
- internally_validated；
- externally_validated；
- not_supported。

一个 component/scheme version 可以软件已验证而科学状态仍是 engineering_default。UI、导出和报告必须同时携带两种状态。

## 2. 验证层级

### 2.1 静态合同

- JSON Schema / typed contract 可解析；
- ID 唯一、引用可解析、版本字段完整；
- 单位、坐标系、time base 和 state order 明确；
- model bundle content hash 可重建；
- 文档链接、文件路径和示例一致；
- 未使用旧 H6、旧 O2 或 19-node 口径。

### 2.2 Unit 与 property tests

- ingestion adapter：正常、缺列、错单位、损坏、gap、duplicate、out-of-order；
- M3 synchronization：Decimal round-half-even、已知 scale/offset、scale/drift 一致性、same-clock mapping、int64 边界/overflow、master-clock X session window、negative/tail rows、duplicate mapped ns、稳定排序和 source-row preservation；
- built-in/trusted operators：typed ports、unit/cardinality/time semantics、parameter schema、代表性正常/边界/error cases；
- EvidenceRecipe compiler/executor：DAG、binding、formula、scorer、trace、deterministic replay 和 error localization；
- no-quality-gate 平台边界：合法 recipe 可以把极差轨迹、剧烈控制、极端生理指标、未响应、未恢复或未注视形成 `computed + Unacceptable`，不得由 engine 自动改成 `invalid_quality`；computed U 的 raw availability 必须为 1；
- evidence scoring operators：按自身 schema 执行 D/A/U 或 soft likelihood；不要求所有 expert scorer 单调；
- CPT：维度、非负、有限数、每行和为 1；
- BN：小型手算网络的 prior/posterior、缺失 evidence 边缘化，以及显式 soft scorer/依赖保护产生的 virtual evidence；不得按原始数据质量衰减 likelihood；
- graph operations：typed-edge semantics、cycle、duplicate、EvidenceBinding、state migration、size caps、atomic rollback、undo/redo；
- layout operations：layout_version conflict、批量位置保存且不改变 semantic hash；
- component/scheme version：exact pinning、content identity、immutability、parent lineage、copy-on-write、atomic apply 和 replay。

对概率和浮点算法使用明确 tolerance；不能用“看起来接近”代替断言。

### 2.3 Component contract tests

- SessionManifest 与每种文件 adapter；
- EvidenceRecipe/OperatorDefinition API、operator registry 与 executor；legacy AnchorPlugin adapter 只做 replay-focused tests；
- model bundle loader 与 BN engine adapter；
- JSON-RPC Python server 与 .NET client；
- backend error_code 与 UI recovery action；
- artifact export/import round trip。

### 2.4 Integration tests

- 已实现的 M6 全栈：多模态 bundle → `IngestionReadinessReport` → `SynchronizationInput` → native-rate `AlignedSession` + `SynchronizationReport` → model lock/reference resolution → `RunPreflightReport`；该链不属于 M4 自身完成门；
- 可变 cardinality expert model：aligned session → recipe executor → AnchorResult inventory → evidence；starter 18 只作迁移示例；
- evidence → BN posterior、coverage、explanation；
- recipe/graph/binding edit → autosave → optional preview → technical validation → apply；
- published scheme + exact components → run → reproducible result；
- cancel、crash、restart 与 interrupted recovery。

### 2.5 End-to-end tests

至少维护以下互不混淆的验证资产；“场景”不等于每项都要生成 physical bundle：

1. format-sample-XU：只有 simulator 采集格式样例 X/U，用于接口、解析、时间与缺失模态处理；该记录不提供标准轨迹、任务 ground truth 或能力标签；
2. synthetic-multimodal-foundation：含可控 offset/drift、VR/gaze、EEG/ECG，用于 M2/M3 合同和同步，不默认声称 18-anchor 答案有效；
3. editable-evidence-vertical-slice：紧凑多模态输入与“扰动期间目标 AOI 关注”recipe，用于创建、修改参数、preview 差异、apply 和旧 revision replay；
4. representative-operator-assets：使用极小输入验证 operator/recipe 合同和 error states，不生成 full bundle；
5. legacy-migration-smoke：少量现有 plugins 与迁移 recipe 做输入/输出接线比较，不要求维持全部 provisional 算法等价；
6. de-identified-reference：如研究团队批准，可用于独立科学研究，不进入公开仓库。

通过 WinUI 执行：创建项目、导入、修复或接受 warning、从全局库选择 exact versions、编辑 integrated three-node/two-edge workspace、preview、apply、运行、查看 trace、导出结果。

### 2.6 M3 engineering verification record（2026-07-12）

M3 完成门在同一工作树上取得以下实测证据：

- 显式配置 repository-external CSV 后，最终 M2 与 M3 captured-format E2E：`2 passed in 37.08s`；
- 清除该环境变量后，最终 full suite：`694 passed, 2 skipped in 219.23s`；两个 skip 分别且仅分别属于 M2/M3 opt-in captured-format tests；
- 四份 public JSON Schema 重新生成，tracked schema diff 为零；Ruff format 检查 75 个文件、Ruff lint、`ty check src`、build 与 whitespace diff 全部通过；
- tracked raw-data 扫描结果为零；本地完整 bundle、外部 CSV、EDF、视频、Parquet、图像或其他采集 artifact 未进入 Git；
- final fresh wheel `pilot_assessment_system-0.1.0-py3-none-any.whl` 为 127,101 bytes，SHA-256 为 `bc9476f209c8ee851a58d6de037ddb98fac3356c819957d61c587e253a744342`；
- 隔离环境中的 import origin 位于 repository 之外，wheel 可读取 17 个 M2 profiles、8 个 M3 temporal streams，公开 `synchronize_bundle`、`synchronize_session` 与 synchronization DTO 可导入；最终隔离 micro M1→M2→M3 E2E 为 `1 passed in 4.34s`，TEMP 目录经安全检查后已清理。

Primary golden counts 使用 `raw/aligned rows / in-session rows`：

| Golden | X | U | I | G | EEG | ECG | pilot_camera | task_reference |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 s micro | 201/201 | 201/201 | 61/60 | 241/240 | 513/509 | 501/498 | 31/30 | 201/201 |
| 29.01 s captured-format + synthetic modalities | 2,902/2,902 | 2,902/2,902 | 871/871 | 3,482/3,481 | 7,427/7,423 | 7,253/7,251 | 436/435 | 2,902/2,902 |

Secondary golden counts：

| Golden | AOI total/in-session | Fixations total/overlap/full | R-peaks total/in-session | invalid in-session scene/gaze associations |
|---|---:|---:|---:|---:|
| 2 s micro | 122/120 | 4/4/3 | 3/3 | 0 |
| 29.01 s captured-format + synthetic modalities | 1,742/1,742 | 59/59/58 | 37/37 | 0 |

Captured-format source SHA-256 固定为 `19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52`。测试在 synchronization 前后逐字节比较外部 CSV 与生成 bundle 的全部文件；这些证据只说明格式、接口、时间映射和文件不变性，不支持轨迹精度、phase 正确性、控制质量、工作负荷、生理解释、anchor 值或飞行员能力结论。

Public `SynchronizationReport.validation_scope` 为 `native_rate_session_time_alignment_v1`。同一确定性 `synchronization_fingerprint` 写入 report 与非 blocked `AlignedSession`；fingerprint 覆盖 M2 source snapshot、policy、temporal catalog、aligned time/flags、canonical annotations 与排序后的 status/issues，并排除绝对路径和 host/wall time。M3 不插值、不重采样、不建立 analysis/window grid，所有 timed artifact 的 `interpolated_rows=0`；M4R 只在 EvidenceRecipe 显式选择相应 operator 时建立 recipe-specific grids/windows。所有 M3 路径继续保持 `formal_run_authorized=false`，synthetic scientific status 为 `not_supported`。

### 2.7 Legacy M4 设计与阶段性实现状态（2026-07-13）

[M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md) 与相关 amendments 记录了旧 M4 Task 0–28 的合同和工程历史：O1–O12/H1–H3、共享 primitives 与三个 preprocessing providers 已进入代码，历史测试继续有效。2026-07-15 用户批准 EvidenceRecipe/operator 总体架构、D-031–D-035 与正式合并规格；旧 Task 29–36 已停止，15 个 whole-Anchor plugins 改作 legacy/reference implementations。历史 fixed-plugin tests 不构成新完成门、质量筛选、科学有效性或飞行员能力结论。

M4 的职责边界是按已配置规则提取 evidence，而不是研究原始采集质量。进入 M4 的 aligned input 假定已经满足 M1–M3 的结构合同；coverage、gap、sample count 和 sync metrics 只作 diagnostics/provenance。数值再差仍应形成 D/A/U，特别是 `computed + Unacceptable` 必须作为有效负面 evidence，且 raw availability 与 computed D/A 一样为 1。

### 2.8 M4R Evidence Computation Foundation 验证状态（2026-07-15）

M4R 已按 [实施计划](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md) 完成进程内 Evidence 计算基础：canonical DTO/schema、trusted operator registry、only-technical validator、generic compiler/executor、可复用 built-ins、draft optimistic revision、preview/apply/replay，以及动态 starter recipe catalog。O1–O13/H1–H5 共 18 个 resources 全部标记为 `starter_template`；第 19 个任意 ID recipe 已实际注册、执行和应用，证明 18 不是引擎上限。

轻量迁移 smoke 只选择 O2、H1、H4 三个代表 wiring；editable workflow 只使用 1 个 event 和 3 段 gaze，覆盖 incomplete autosave、补全、preview、AOI/window/scorer 修改、两次 immutable apply、旧 revision replay、clone 和 disable。它证明平台忠实执行 recipe，不证明这些初始算法、阈值或 AOI 具有科学有效性。完整 managed orchestration 与持久化/sidecar 已由独立 M6 vertical slice 验证，不能反向扩张 M4 的完成门。

### 2.9 M5 Shared Model Library / Bayesian Workspace 验证状态（2026-07-16）

M5 已按 [实施计划](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) 关闭工程完成门。focused model-library/scheme/BN/workflow 为 `91 passed in 4.25s`，M4R Evidence regression 为 `59 passed in 2.12s`；fresh full repository gate 为 `1579 passed, 3 skipped in 251.26s`。三个 skip 仅来自主机不允许创建测试 symlink，以及两条未配置 repository-external captured-format CSV 的 opt-in E2E。

Ruff lint、264-file format check、`ty check src`、32 份双目录 Schema 再生成与 `git diff --check` 均通过。Task 12 将计划中的裸 `ty check` 修正为仓库自 M2 起统一采用的 production-source boundary `ty check src`；测试目录包含刻意构造的动态 JSON/Polars 负例，不属于静态类型交付合同。

fresh `uv build` 生成 652,665-byte wheel（SHA-256 `91992f5e7b741a1e50f5dd2366c9b008f7756f845f7ae9d76a70c05e35235c96`）和 481,987-byte sdist（SHA-256 `e70f593c331e629cf0bb5c02afb1f23244a7ad4f0d42a5f5f2ce56284d663ee9`）。仓库外 `uv pip --target` 安装后的 import origin 位于临时安装目录；wheel manifest 精确枚举 13 个 Hover JSON resources，加载结果为 15 个 BN concepts/versions、18 个 Evidence versions/bindings、33 个 CPT，并成功编译 33-variable inference plan。该段是 M5 当时的完成门；M6 persistence/sidecar 与 M7 WinUI 现已另行工程验证，M7 用户验收、M8 产品化与科学有效性仍未完成。

### 2.10 M6 Local Runtime / Persistence / Sidecar 验证状态（2026-07-16）

M6 已按 [实施计划](plans/2026-07-16-m6-local-runtime-persistence-and-sidecar-implementation-plan.md) 关闭 15 个 INLINE 任务。M4R/M5/M6 focused regression 为 `151 passed in 17.99s`，fresh full repository 为 `1632 passed, 3 skipped in 337.27s`；skip 原因与 M5 相同。44 种 Schema 在 root/package 双目录间零漂移，Ruff lint、313-file format check、`ty check src` 与 build 全通过。

fresh wheel 已在仓库外临时目录安装，并通过 packaged schema、project create/close/open 与 sidecar hello/shutdown。轻量 vertical slice 在 external bundle 删除后从 managed copy 完成动态 O1 scheme run；project 整体 rename/reopen 后 exact scheme/result/artifact replay 保持一致。该证据只验证软件框架，不验证 O1、Hover 或任何能力含义。

## 3. 子系统验证矩阵

| 子系统 | 必须证明 | 主要证据 |
|---|---|---|
| Session bundle | 格式、checksum、单位、状态语义正确 | schema tests、corrupt fixtures |
| 时间同步 | native-rate rows 按唯一 clock mapping 对齐、window/越界/重复/误差可见且不改 source 值 | half-even、scale/offset、overflow、same-clock、window、duplicate 和 row-preservation synthetic tests |
| Evidence operators | built-in/trusted operators 按公开 port/type/unit/parameter 合同执行，不使用原始数据质量门丢弃表现 evidence | 每个 operator 的 focused contract tests |
| EvidenceRecipe engine | 任意合法 recipe 可 compile/execute/trace，非法连接精确定位；差表现仍可形成 computed U | representative recipe tests + 一个轻量 editable vertical-slice smoke |
| Expert recipes | 系统忠实保存和执行专家定义；不判断其科学合理性 | preview 与用户检查，不设 per-edit pytest/golden gate |
| BN/CPT | 图合法、概率正确、缺失可边缘化 | hand-computable BN tests |
| Graph editor | 五层投影正确，前后端一一对应，草稿 mutation 和最终 commit 失败均原子回滚 | .NET/Python contract + UI tests |
| Current model + history | edit session 可恢复、全局 undo/redo 正确、Save all 折叠 revision、Discard 不改 canonical、activation closure 正确、RunSnapshot 不可变且历史 run 可重现 | staged-edit/undo/copy/cascade/run-snapshot replay tests |
| Runtime | framing、取消、错误、崩溃恢复 | protocol fault-injection |
| Results | posterior、coverage、trace 和版本完整 | golden result snapshots |
| Privacy | 导出和日志默认脱敏 | privacy inspection tests |

## 4. Recipe、Graph 与 CPT 保存/运行技术门槛

Current ModelNode/TaskScheme 始终可以暂存到后端 edit session，即使 `configuration_incomplete`。每个草稿原子 operation 只校验它自身必须保持的结构不变量；Save all 原子更新 canonical workspace。只有 clean canonical workspace 的 preview/run preflight 才要求所选 active closure 整体技术可执行：

- recipe/node/edge/port/output/Anchor binding 唯一且可解析；
- 无 self-loop、duplicate edge 或 directed cycle；
- operator input/output type、cardinality 和 unit 可连接；
- required parameter 存在、类型正确且数值有限；safe formula 可编译；
- 每个节点 state space 非空、名称唯一且顺序固定；
- parent order 与 CPT dimension 一致；
- 所有 CPT 数值有限、非负、每行和为 1；
- 每个 active evidence node 都有唯一、有效且可解析的 EvidenceRecipe output binding；unbound node 可存在于 incomplete current scheme；
- parent count 与 CPT cell count 不超过项目安全上限；
- operator implementation、recipe graph、BN graph 和 engine 兼容；
- scorer 能产生合同规定的 evidence output，selected model 可以编译为 executable plan；
- semantic/layout revision、diff、作者、时间和 content identity 可自动生成；run.start 可冻结完整 RunSnapshot。

以下内容不是 staging/Save all/preview/run gate：文献支持、专家共识、参数校准、单调性偏好、starter-template 等价、preview 表现，以及任何人工 reviewer/waiver。系统可以显示 warning，但不能以此阻止专家保存或运行技术上可执行的方案；dirty edit session 本身是明确的运行事务 blocker，用户必须先保存全部或放弃全部。

## 5. 科学校准路线

### Stage S0：专家内容审查

- 审查 18 个 anchor 的构念、公式、方向、适用阶段、配置前提和 classification override；不把原始数据质量研究重新引入 M4；
- 审查 11 个 sub-skill、4 个 competency 及共享 evidence 连接；
- 确认 task profile、reference path、phase/event 与安全边界；
- 对每条意见记录 accept/reject/defer 和理由。

输出：标记为 expert_reviewed 的 current nodes/TaskSchemes 与对应 review records；运行时由 RunSnapshot 固定，不等同于统计验证。

### Stage S1：参数校准

- 使用匿名真实 session 和可说明的专家评分；
- 按 task、phase、设备和 pilot cohort 检查分布；
- 优先使用任务/安全界限，其次采用专家成功样本分位数；
- 拟合或 elicitation CPT 时保留样本数、不确定度和 regularization；
- 通过交叉验证或留一 pilot 评估过拟合；
- 冻结 calibrated revision 后再测试，避免数据泄漏。

### Stage S2：内部有效性

建议至少评估：

- known-groups validity：专家/新手或成功/失败组；
- convergent validity：与独立专家评分、HQR、TLX 或其他已批准量表的关联；
- discriminant validity：不同技能维度不应全部退化为同一 workload 指标；
- reliability：重复 session、不同分段或不同 scorer 的稳定性；
- calibration：posterior 与真实/专家标签的匹配；
- decision utility：弱项诊断对训练反馈是否有用；
- sensitivity/specificity 或 ordinal metrics，取决于预注册研究问题。

### Stage S3：稳健性与推广

- leave-one-modality-out 与 missingness ablation；
- threshold、CPT 和同步误差敏感性；若未来研究采集质量或噪声鲁棒性，应作为独立科学研究，不得静默改成 M4 evidence omission 或 likelihood 衰减；
- 不同 pilot、场景、任务难度、设备和日期的外部验证；
- subgroup performance 和潜在偏差；
- distribution shift 与 out-of-scope 检测；
- 新 scheme/component versions 与旧 versions 的纵向可比性。

科学研究若要用某个 revision 支撑结论，应自行判断并记录该 revision 的验证范围；这不是专家在产品内修改或 apply 的前置条件。

## 6. v0.2 平台交付 Gate

### Gate A：设计就绪

- 本目录文档完成并通过一致性自审；
- 所有跨模块决策有 DECISIONS 记录；
- schema、示例和验收标准可实现；
- 未解决问题有 owner 和阻断级别。

### Gate B：Core alpha

- minimal-XU 与 synthetic-multimodal bundle 可运行；
- EvidenceRecipe/OperatorDefinition、compiler/executor、registry、technical validation、preview/apply/replay 可运行；
- 专家无需新增 Python AnchorPlugin 即可创建、修改、复制、disable/retire 一个示例 evidence；一个轻量“扰动期间目标 AOI 关注”vertical slice 验证前后端合同和参数修改会改变 preview；
- 代表性 built-in operators、非固定 Anchor cardinality 与 no-quality-gate 边界通过工程测试；不要求 18 个 starter algorithms 的 all-D/all-U golden；
- BN、missing evidence、coverage 和 provenance 可验证；
- CLI/test harness 可在无 UI 情况运行。

### Gate C：Desktop beta

- WinUI 自动管理 sidecar；
- session explorer、Evidence Designer、BN Designer、schema-driven forms、revision、run、results 和 diagnostics 完整；
- contract/E2E/crash tests 通过；
- 安装、升级、卸载和项目保留策略验证。

### Gate D：Research release

- 专家确认产品边界和报告措辞；
- 至少有一个 expert_reviewed 或 calibrated assessment scheme version；
- 数据保护、脱敏、同意和保留策略获项目批准；
- 已知限制与 scientific status 随产品交付。

Research release 不自动意味着 operational certification。

## 7. 可追溯性要求

每次 AssessmentResult 必须能回答：

- 哪个 session 与 session revision；
- 哪个 published scheme、exact component versions 与 content identities；
- 使用了哪些 engine、EvidenceRecipe、operator implementation、parameter/scorer version；legacy replay 时另记 plugin identity；
- 哪些原始文件、phase/event 和 source window 支撑每个 anchor；
- continuous value 如何转为 D/A/U；
- 哪些 evidence 为 `missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`；
- 哪些 `computed + Unacceptable` 是有效负面 evidence，以及它们为何仍计入 availability；
- 每项 competency 的 coverage；
- 哪些 evidence 对 posterior 贡献最大；
- 谁在何时 apply 模型，经过哪些 technical validation。

没有这些信息的结果不能称为可重现正式结果。

## 8. 产品交付包

建议交付结构：

~~~text
PilotAssessment/
  app/                         # signed Windows frontend
  runtime/                     # packaged Python sidecar
  models/reference-v0.1/       # read-only reference model bundle
  docs/product/                # 本设计文档中心
  samples/
    minimal-xu/
    synthetic-multimodal/
  schemas/
  licenses/
  THIRD_PARTY_NOTICES
  VERSION
  CHECKSUMS
  INSTALL.md
  USER_GUIDE.md
  RELEASE_NOTES.md
~~~

研究原始数据、身份映射、内部论文库和未获许可材料不进入通用交付包。

## 9. 接手清单

### 产品/项目负责人

- 阅读 01、DECISIONS 和本文件；
- 确认产品用途、用户群、数据责任和 scientific status；
- 指定数据保护责任人；产品不要求模型发布审批角色。

### 后端开发

- 阅读 02、03、04、05、06、07；
- 从 contract、schema 与 synthetic fixtures 开始；
- 不把 reference model 写死在 Python；
- 保持 BN engine adapter 可替换。

### 前端开发

- 阅读 06、07、08；
- 以 fake backend 建 UI，再执行 .NET/Python contract tests；
- 始终以 canonical graph 和 version 为准。

### 领域专家

- 从 04 和 05 开始；
- 在产品中修改参数、mapping、edge 和 CPT；
- 可按需要填写科学理由、依据和适用范围；未填写不阻止 autosave/apply；
- 不需要修改源代码。

### 测试/审查人员

- 使用本文件的验证矩阵和发布 Gate；
- 复核原始 evidence trace，而不是只看 UI 截图；
- 分开签署 software verification 与 scientific validation。

## 10. 文档自审流程

每次设计版本变更至少执行：

1. 列出所有 Markdown 文件并验证相对链接；
2. 搜索旧口径：H6、19 anchors、O2 旧名称、FastAPI required、topology read-only；
3. 核对 18 anchors、11 sub-skills、4 competencies 和共享 evidence mapping；
4. 核对 I(t)/G(t)、EEG/ECG 和模态状态语义；
5. 核对 frontend、runtime 与 backend 方法名；
6. 核对新增/删除 edge 的 CPT migration；
7. 核对 AnchorResult v0.2 calculation status、computed-U availability、missing evidence、coverage 和 validation status；确认 M4 正式文档未重新引入 `quality_gates`、`min_valid_coverage`、`binary_quality_v1` 或主动产生的 `invalid_quality`；
8. 由未参与起草的人进行一次独立审查；
9. 把发现、修复和遗留风险写入 10_DESIGN_SELF_REVIEW.md。

## 11. 当前已知风险

- reference anchor threshold 与多数 CPT 仍是工程默认，需专家和样本校准；
- EEG/ECG、VR/gaze 的实际导出格式尚未冻结；
- reference trajectory、phase/event annotation 的生产方式需与实验团队确认；
- shared-evidence 多 parent CPT 会指数增长；v0.1 已设 parent/row/cell/size 硬上限，但数值仍需性能基准和专家审查后才能提高；
- WinUI 图编辑控件选型和无障碍支持需原型验证；
- M1–M8B、M8C-0 与 M8D 的合同、ingestion/synchronization、editable Evidence、BN、受管项目、sidecar、WinUI、portable runtime、editable Python/source identity、文档 pipeline、current-system packaging 和 project portability 均已通过各自工程门；M7 用户手工验收仍待完成。M8C-1 最终文档和 M8E clean-machine handoff 尚未实施；专用 backup/restore 已取消。starter/synthetic `formal_run_authorized=false`；现有证据不构成科学有效性声明。
