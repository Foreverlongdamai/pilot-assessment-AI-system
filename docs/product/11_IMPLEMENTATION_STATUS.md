# Implementation Status — M1/M2/M3/M4R Engineering Verified

| 字段 | 当前值 |
|---|---|
| 状态日期 | 2026-07-16 |
| 产品设计基线 | v0.3 shared-versioned-model architecture（D-031–D-040） |
| 已完成里程碑 | Backend Foundation M1 + M2 Multimodal Synthetic Foundation + M3 Native-Rate Time Synchronization + M4R Editable Evidence Computation Foundation |
| M4 当前状态 | M4R 已完成 canonical EvidenceRecipe/OperatorDefinition schema、trusted registry、only-technical validation、generic compiler/executor、built-in operator library、backend-only draft/preview/apply/replay、18 个 editable starter resources 和轻量 E2E。旧 Task 0–28 的 15 个 whole-Anchor plugins 与三个 providers 保留为 legacy/reference；旧 Task 29–36 已停止。**M4R engineering verified；`formal_run_authorized=false`。** |
| 下一里程碑 | M5 Task 1–9 已完成 generic identity、public contracts/Schema、typed source/M4R preflight、进程内 global component library、exact-pinned validation、scheme draft/atomic publish、通用 CPT 校验/生成/迁移、finite-discrete exact inference/只读 influence trace 与 M4R active import/compliant TPX parallel version；下一执行入口为 Task 10 Hover starter BN component package；不自动把 M6/M7 混入 M5 |
| 软件状态 | `in_progress`（M1/M2/M3/M4R engineering verified；M5 Task 1–9 已完成，但 Hover starter workspace 整体、M6 durable persistence/sidecar、M7 WinUI 与 M8 packaging 尚未完成） |
| 科学状态 | synthetic 数据为 `not_supported`；评估模型仍待领域专家校准与验证 |
| Python package | `pilot-assessment-system 0.1.0` |
| 本地运行边界 | Windows、离线、目录形式 Session Bundle |

## 1. 本轮结论

M1/M2/M3 已实现，并通过 micro fixture 与 simulator 采集格式样例 CSV 两条端到端路径。系统现在可以：

1. 将当前 combined simulator CSV 作为一个通过格式与文件完整性检查的共享物理文件，分别形成 X 与 U 两个逻辑 view；这里的检查不包含任务或表现有效性；
2. 保留 I、G、EEG、ECG、pilot_camera 与 bundle-local task reference 的版本化理想输入合同；
3. 使用采集格式样例 X/U 的技术时间范围与无科学语义的 synthetic driver，生成确定性的多模态软件测试数据；
4. 在同一个 M1 loaded snapshot 上经过 M2 content/adapter gate，并输出严格的 `IngestionReadinessReport` 与内部 `PreparedSession`；
5. 对七个 core modalities、bundle-local task reference 与 annotations 执行版本化 native-rate temporal binding、Decimal round-half-even clock mapping、master-clock X session-window mask，以及 non-gating synchronization/scene-gaze diagnostics；
6. 输出只读 `AlignedSession` 与 public `SynchronizationReport`，使数据可以进入 M4 anchor/evidence availability，但永远不授权正式 assessment run。

本结论证明 M1–M3 的合同、文件不变性与 native-rate 时间计算路径，以及 M4R 对 editable recipe 的保存、技术校验、编译、执行、预览和 revision replay 均按规格运行。Synthetic scene、gaze、EEG、ECG、pilot-camera、annotation、commanded path 与 M4R 小 fixture 都不是航空、生理或训练评估有效性证据。M3 不执行插值、重采样或 analysis/window grid；M4R 只在 recipe 显式放置相应 operator 时执行变换或建立窗口。

其中 repository-external simulator CSV 只是一次随意飞行产生的采集格式样例，没有标准轨迹、任务 ground truth 或能力标签。对它的 E2E 验证只证明 33-column/100 Hz 格式可以被读取、保留和转换；不证明该飞行符合任务要求，也不支持任何表现或能力结论。

2026-07-12 已将 M3 的 D-016–D-020 正式写入决策记录并完成实现：M3 只做 native-rate alignment，使用 scale-only/round-half-even clock mapping 和 master-clock X 技术时间窗口，输出独立 `SynchronizationReport`。§3 记录的完成门已经实测通过；这仍不表示完整 Assessment Core、正式 assessment run 或科学有效性已经成立。

2026-07-13 已新增并批准 [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)，把 AnchorResult v0.2、18 个 anchor、typed dependency DAG、artifact/fingerprint 和状态边界冻结为当时的书面设计；其后 [M4 Lightweight Workflow Validation Amendment](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)、D-026/D-027 与 [replacement M4 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 也获批准。Task 0–28 随后完成：M4-A contracts/catalog/resources、M4-B framework、O1–O12、H1 AOI Dwell、H2 First Fixation Latency、H3 Off-task Dwell、共享 primitives 与三个 reference preprocessing providers 已进入代码；相关测试与 fingerprint 继续作为历史工程证据。

2026-07-15 用户确认此前路线对 provisional Anchor 算法的固定、审核和测试投入过重，并批准 EvidenceRecipe/operator 总体架构与 D-031–D-035。当前产品权威目标是让专家在前端自由设计 Evidence Computation Graph 与 BN；18 个 Anchor/33-node BN 只是 starter templates。普通修改使用 canonical `EvidenceRecipe` 和既有 operators，不要求 Python 发布、人工审批或 per-edit pytest/golden；只有算子库无法表达新能力时才新增 trusted operator plugin。旧 Task 29–36 因而停止，不能再把 H4/H5/O13 固定插件或 exact-18 closure 写成下一步。M4R 现已按 replacement plan 完成，因此准确状态是 **legacy M4 Task 0–28 preserved；15 个 legacy/reference plugins preserved；M4R engineering verified**。

2026-07-16 用户进一步确认 D-036–D-040，并要求固化为核心设计：全局库保存 Evidence/BN concepts 与全部并行 immutable versions；`AssessmentSchemeVersion` 为不同任务/方案锁定 exact versions，编辑和发布采用 copy-on-write，不覆盖旧方案。Integrated workspace 显示 Raw Input、Evidence、BN Node 三类节点，但严格区分 data/extraction edge 与 probabilistic BN edge。Hover starter 的 canonical BN 为 `Competency -> Sub-skill -> Evidence`；实际评估观察 Evidence 后计算能力 posterior，只读 inference overlay 不反转图。D-040 进一步规定 legacy Evidence-to-Evidence extraction 不能静默进入 active scheme：旧 `starter.o8` 保留原 bytes/hash 用于 migration/replay，新的 TPX parallel version 从 raw/session/task sources 计算。该设计已写入 [M5 正式规格](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)，配套 [M5 implementation plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) 已批准保存。M5 Task 1 随后完成：新增 generic canonical JSON projection、RFC 8785 bytes 与 typed content SHA-256，旧 `anchors.fingerprint` API 只作兼容委托；focused gate 为 `67 passed`，扩展 fingerprint regression 为 `118 passed, 1 skipped`（host 不允许创建测试 symlink）。Task 2 进一步实现 model components、Bayesian/inference、task scheme/draft 的 strict/frozen DTO，注册并双目录发布 16 类 Draft 2020-12 schema；Task 2 focused gate 为 `46 passed`，提交前完整 contracts/schema regression 为 `403 passed`，本次生产与测试文件定向 Ruff/format/ty 均通过。Task 3 随后实现只接受显式 active source descriptors 的 registry、窄 legacy Evidence-observation namespace fallback、递归 provenance closure 与只读 migration compatibility report；20 个 Hover starter source descriptors 覆盖 X/U/I/G/EEG/ECG/pilot_camera 及相关 session/task/derived sources。全部 18 个 packaged M4R recipes 经过同一预检，17 个 compatible，旧 `starter.o8` 因两个 `anchor.*` inputs 自然为 legacy-only；focused 为 `11 passed`，model-library 加 starter-catalog regression 为 `29 passed`。Task 4 进一步实现通用 repository protocol、in-memory immutable snapshots、injected Clock/IdFactory、exact get、stable list/filter、parallel versions、lineage 与独立 archive metadata；同 exact ID 不可覆盖，hash-bearing record 入库时重算 semantic hash，且没有 latest resolution。focused 为 `8 passed`，完整 `tests/model_library` 为 `34 passed`，Task 3 SourceDescriptor identity 可原样入库。Task 5 进一步实现 exact scheme pin/hash/source closure、Evidence recipe/operator、task semantic、BN parent/CPT/state、双 DAG cycle、output/connectivity 与 orphan pin 的 generic technical validator；draft 可保存 incomplete diagnostics，科学未校准只产生 warning。focused 为 `15 passed`，与 model-library/recipe-validation 的扩展 regression 为 `58 passed`。Task 6 进一步实现 typed component/extraction/Bayesian/layout operations、全新或 clone candidate、incomplete autosave、独立 graph/layout optimistic revision、branch-aware undo/redo、draft closure diagnostics、copy-on-write materialization 与 staged `WorkspaceUnitOfWork`；failure hook 发生在 commit 前，成功发布只写 changed versions + new scheme 并 rebase draft，exact replay 逐一复核 pins/hashes。focused 为 `8 passed`，与 model-library/scheme/recipe-validation 的扩展 regression 为 `66 passed`。Task 7 进一步实现通用 CPT shape/state/order/cell/probability validation、uniform/single-parent/ranked deterministic materialization、加父独立复制、删父显式边缘化与 state-change invalidation，并把 blocking diagnostics 与 non-blocking manual-monotonicity warning 接入 exact scheme validation；focused 为 `14 passed`，`tests/schemes` 为 `23 passed`。Task 8 进一步实现 immutable NumPy factor algebra、exact pin/CPT/DAG compiler、deterministic min-fill variable elimination、hard/virtual/omitted observation、multi-query posterior、impossible-evidence error、stable result/trace hashes，以及只读 leave-one-observation-out influence overlay；focused 为 `10 passed`，Bayesian/scheme/model-library/contract 扩展 regression 为 `85 passed`，定向 Ruff/format/ty 均通过。Task 9 将 17 个通过 provenance preflight 的 M4R recipes 原样导入 immutable active EvidenceVersions，旧 O8 以原 bytes/hash 保留为 legacy-only，并在同一 concept 下新增只读取 X/U/session sources 的 compliant TPX parallel version；focused 为 `4 passed`，model-library/starter-catalog/legacy regression 为 `44 passed`，定向 Ruff/format/ty、旧 O8 hash 与无 O8 特判检查均通过。M5 其余 Task 10–12 尚未完成。

旧计划的 provisional Task 0 曾证明原 fixture 范围不合适：四套 90 秒 bundle 每次会临时生成约 43,000 个文件，focused gate 约需 160 秒；测试还主要验证 builder/oracle 自洽，未独立证明 dense raw data 可以产生预期 anchors。该 provisional 工作未提交、不得计作 M4 证据。已接受修订把验证收缩为一个 10 秒全模态 workflow bundle、18 个 per-anchor 微型测试、紧凑 all-Desired/all-Unacceptable/mixed 场景和 fault-hook state matrix；replacement Task 0 已安全移除旧 provisional files、观察正确 RED，并提交新的轻量 fixture 基线。

M4 书面设计明确采用 no-quality-gate 边界：进入 M4 的 aligned input 假定已满足 M1–M3 的结构合同，M4 不研究原始采集质量，也不按 coverage、gap、噪声、幅值或生理范围过滤表现 evidence。极差轨迹、剧烈控制、极端生理指标、未响应、未恢复或未注视均应按规则形成 `computed + Unacceptable`；该结果是有效负面 evidence，raw availability 与 computed D/A 一样为 1。

## 2. 已实现能力

### 2.1 M1 Session Bundle 与完整性边界

- 严格 `SessionManifest`、七个 core stream descriptor 与五种 stream status；
- bundle-local `task_reference` 通过 `task.reference.stream_id=task_reference` 唯一拥有，物理路径位于 `references/`；
- `source=model_bundle` 时禁止本地 orphan task-reference descriptor；
- D-011 只允许两个 `present` X/U view 共享一个物理 artifact，其他重复、大小写别名与跨角色 sharing 均拒绝；
- UTF-8 JSON、路径 containment、symlink/junction、防路径穿越、SHA-256、checksum scope 与资源预算；
- `present` 与 `invalid` 文件都必须通过路径和 checksum gate；
- loader 保持 inspect-only，不修改源 bundle，也不授权正式 import/run。

### 2.2 公共合同与跨语言 Schema

- `IngestionReadinessReport`、`StreamReadinessResult`、ready/ready_partial/blocked disposition；
- `formal_run_authorized` 在 M2 固定为 false；
- synthetic report 显式保留 classification、generator、seed、source hash、lock fingerprint 与 `scientific_validation_status=not_supported`；
- 已发布四份 JSON Schema 2020-12：
  - `session-manifest-0.1.0.schema.json`
  - `anchor-result-0.1.0.schema.json`
  - `ingestion-readiness-report-0.1.0.schema.json`
  - `synchronization-report-0.1.0.schema.json`
- 可由 JSON Schema 表达的 status/privacy/task-reference/result ownership/disposition 约束已经与 Pydantic 对称；必须访问文件系统、重算 hash 或比较动态 path/checksum 集合的规则保留为 backend runtime invariant。

其中 `anchor-result-0.1.0.schema.json` 和 Python `AnchorResult` 是 M1 阶段建立的 legacy 0.1 合同，仍包含 quality/`invalid_quality` 语义；它们不是 M4 AnchorResult v0.2 的实现证据。Breaking `AnchorResultV2` 与 `anchor-result-0.2.0.schema.json` 已分别由旧 Task 2/6 显式实现和验证；旧 exact-18 catalog、parameter resources、canonical/runtime framework、O1–O12/H1–H3 plugins、共享 primitives 与三个 providers 也已完成并保留。H4/H5/O13 不再补 whole-Anchor production plugin，而是已在 M4R starter recipes 中直接通过通用 operators 组合；这不是缺项，而是批准后的新扩展路线。

### 2.3 版本化 ingestion profiles

Package resource 中包含 17 个严格 profile：

- 当前 Cranfield combined simulator CSV 的 33 个规范化 header、X/U/context/quality-check 映射；
- 9 个 Parquet table schema；
- RGB8 PNG profile；
- EEG JSON sidecar profile；
- I、G、EEG、ECG、pilot-camera 五个 composite profile。

Profile 固定列顺序、dtype、nullability、unit、sort key、采样率、artifact role 与 matcher。Wheel 隔离安装后可以直接读取这些 package resources。

### 2.4 Adapter 与内容验证

- `ProfiledCsvAdapter`：严格 UTF-8/UTF-8-SIG、row width、header collision、required numeric/finite、时间单调、100 Hz、gap、constant context 与 m/s↔kt 检查；
- profiled Parquet：embedded contract/schema metadata、列顺序、dtype、null/finite/range、sort key、sample rate 与 valid fraction；
- gaze nullable measurement 只有在 `binocular_valid=false` 或 `blink=true` 时才允许为空；
- EEG sidecar：严格 JSON、duplicate-key、channel/unit/rate/clock/generator/seed/synthetic flag；
- PNG：canonical path、RGB8、精确 synthetic 尺寸、index 尺寸一致、禁止 animation/ancillary metadata，并设 16 megapixel 安全上限；
- composite cross-check：scene↔AOI、gaze fixation、EEG samples↔sidecar、ECG samples↔R-peak、camera index↔PNG；
- readiness 还验证 gaze sample 的 scene-frame/AOI assignment；
- adapter 在 eager materialization 前执行 bytes/rows/columns/string-length 上限。

### 2.5 Deterministic synthetic generator

CLI：

```powershell
uv run python -m pilot_assessment.synthetic `
  --xu-csv <combined-simulator.csv> `
  --output <local_data/output-directory> `
  --seed 20260711
```

生成器执行：

- 原始 X/U CSV byte-for-byte copy；
- 30 Hz VR scene + AOI、120 Hz gaze + fixation、256 Hz EEG、250 Hz ECG + R-peak、15 Hz pilot camera；
- `references/commanded_path.parquet` 与三类 annotation JSON；
- 固定 SHA-256 counter PRNG、binary32 量化、source grids 与 device clock truth；
- 将内部名为 `control_activity(t)=min(1, abs(Pilot Lon)/100)` 的无科学语义测试驱动量线性重采样到 EEG/ECG source grid，形成确定性的跨流软件测试耦合；它不代表生理反应、工作负荷、控制质量或 O13 证据；
- canonical manifest、checksum、stable session ID 与 synthetic provenance；
- 生成后自动执行 M1 和 M2 自检；只要任一适用模态未 ready，就拒绝将 bundle 作为完成结果返回。

### 2.6 M3 Native-Rate Time Synchronization

- 公共 `synchronize_bundle()` 复用单一 M1 snapshot，依次执行 M2 readiness 与 M3；`synchronize_session()` 消费显式 `SynchronizationInput`；
- 8 个 temporal stream profiles 为 point、interval、foreign-key inherit 与 untimed roles 提供版本化 source→`*-aligned-v0.1` binding；
- 所有 timed rows 保留 source values、source order 和 source row identity，只追加 int64 `t_ns` 与 window flags；
- session window 固定为 `[0, max(mapped X primary t_ns)]`，clock kernel 只应用一次 scale，并以 Decimal round-half-even 转换；
- quality report 覆盖 coverage、before/inside/after、duplicate、gap、residual、interval overlap 与 scene/gaze presentation association；
- phase/event/baseline/reference 只验证 session-time 合同结构和内部自洽性，不判断专家标签或任务真实性；
- `SynchronizationReport.validation_scope=native_rate_session_time_alignment_v1`，同一 root-independent `synchronization_fingerprint` 写入 report 与非 blocked `AlignedSession`；
- 所有结果保持 `formal_run_authorized=false`，所有 timed artifact 的 `interpolated_rows=0`。

### 2.7 M4R Editable Evidence Computation Foundation

- `EvidenceRecipe` 与 `OperatorDefinition` 使用 strict/frozen Pydantic DTO，并确定性导出前端可消费的 JSON Schema；
- trusted `OperatorRegistry` 按 operator ID/version 绑定 definition 与 implementation，不动态执行 recipe 提供的 Python；
- only-technical validator 检查 binding、DAG、port type/cardinality/time semantics/unit、parameters、outputs 和 scorer，但不判断公式或阈值是否科学；
- generic compiler/executor 不按 Anchor ID 分支，支持 deterministic topological order、显式 binding propagation、selected node trace 和 node/operator-localized diagnostics；
- built-in library 覆盖 input、signal、temporal、event、gaze/AOI、flight geometry、statistics、composition、aggregation 与 D/A/U scoring；所有 smoothing、detrend、window、filter 和 aggregation 都必须由 recipe 显式放置；
- backend-only service 支持 incomplete draft autosave、optimistic revision、clone、active/disabled/retired、preview、apply、immutable snapshot 和 exact replay；
- package 中提供 O1–O13/H1–H5 共 18 个 `starter_template` JSON resources，全部可修改/替换；catalog 不固定数量，第 19 个任意 recipe 已实际通过注册、执行与应用；
- O1–O12/H1–H3 的 15 个旧 Python plugins 保留为 legacy/reference/replay source；O13/H4/H5 仅引用旧参数资源并直接使用 operator composition。

M4R 没有实现 BN、项目级 model workspace、持久化、JSON-RPC sidecar 或 WinUI。这些边界分别属于 M5–M7；当前仍不能创建正式 assessment run。

## 3. 验证证据

### 3.1 环境

| 组件 | 实测版本 |
|---|---:|
| Python | 3.11.15 |
| Polars | 1.42.1 |
| Pillow | 12.3.0 |
| Pydantic | 2.13.4 |

### 3.2 自动化完成门禁

2026-07-12 在当前工作树重新执行：

- 最终显式 captured-format M2/M3 E2E pair：`2 passed in 37.08s`；
- 清除外部 CSV 环境变量后的最终 full suite：`694 passed, 2 skipped in 219.23s`；两个 skip 且仅两个 skip 分别来自 M2/M3 opt-in captured-format tests；
- 四份 JSON Schema 重新生成且 tracked diff 为零；Ruff format 检查 75 files、Ruff lint、`ty check src`、build、whitespace diff 全部通过；
- broader tracked raw-data scan 为零；
- final fresh wheel：127,101 bytes，SHA-256 `bc9476f209c8ee851a58d6de037ddb98fac3356c819957d61c587e253a744342`；
- 隔离安装的 import origin 位于 repository 之外，17 个 M2 profiles、8 个 M3 temporal streams、两项 public service API 与 public DTO 均可用；最终隔离 micro M1→M2→M3 E2E：`1 passed in 4.34s`，TEMP cleanup 已确认。

2026-07-13 在 M4 design-only candidate 收口后再次执行 `.venv\Scripts\pytest.exe -q`：`694 passed, 2 skipped in 124.00s`。两个 skip 仍只对应未配置 repository-external CSV 的 M2/M3 opt-in tests。此结果证明文档变更没有破坏既有 M1–M3 回归基线；因为本轮没有 M4 code/schema/test，它**不是** M4 实现或验证证据。

#### 3.2.1 M4 replacement Task 0 轻量前置门

2026-07-13 的 replacement Task 0 已在提交 `bc544bf` 中完成，证据边界如下：

- 首次聚焦执行先得到预期 RED：缺少轻量 recipe、builder、oracle 与 expected resources；不是 collection 或 dependency import failure；
- 旧 provisional heavy fixture files 已逐项安全移除且未进入 Git 历史；仓库没有 tracked CSV、Parquet 或 PNG，也没有 `src/pilot_assessment/anchors/`；
- 锁定并实测 NumPy `2.3.5`、SciPy `1.17.1`、rfc8785 `0.1.4`；
- 唯一 10 秒临时 bundle 生成 452 PNG、468 个 manifest declared-path references、467 个 unique artifacts、466 个 verified checksum paths 和 9,331 行 physical source tables；
- 公开 M1→M2→M3 路径为 ready，保留独立 commanded reference 与 pilot-camera provenance；`formal_run_authorized=false`，synthetic scientific status 为 `not_supported`；
- 独立 oracle 从 input recipe 机械生成 exact-18 expected vector，定向 recipe 扰动覆盖 trajectory、control、gaze/AOI、RR 与 EEG，且拒绝 AnchorResult/AnchorMeasurement/anchor-keyed answer echo；
- fresh focused gate：`6 passed in 9.36s`；Ruff format/lint、lock check、dense-asset scan 与 `git diff --check` 通过。

这些证据只关闭 Task 0 的 fixture/runtime 前置条件，不表示任何 production AnchorPlugin、AnchorResult v0.2 runtime、DAG、scorer 或 M4 workflow 已实现。

#### 3.2.2 M4 replacement Task 1 数值运行时审计

2026-07-13 的 replacement Task 1 已在提交 `f56365c` 中完成：

- verification-only 首次规定命令直接通过：`11 passed in 28.86s`（冷缓存）；移除一次重复 NumPy `RECORD` 扫描后，最终 fresh focused gate 为 `10 passed in 1.69s`；
- 实测 NumPy `2.3.5`、SciPy `1.17.1`、rfc8785 `0.1.4`，且已发布 package metadata 保留批准的版本范围；
- 三个 distribution 的稳定 `RECORD` rows 均可枚举，并逐项核验声明大小与 SHA-256；canonical identity 只包含相对路径、hash 与 size；
- 绝对安装根只用于 containment 校验，不进入 identity；installer launcher、`RECORD`、`INSTALLER`、`REQUESTED`、`direct_url.json` 与缓存字节码均被排除；
- `uv lock --check`、Ruff format/lint、目标 tests 的 `ty check` 与 `git diff --check` 全部通过；规格复核与代码质量复核最终均 PASS。

Task 1 只验证 Task 0 已锁定的数值/JCS runtime 与 provenance surface；它没有新增 production contract、plugin、scorer 或 M4 execution capability。

#### 3.2.3 M4 replacement Task 2 AnchorResult v0.2 合同

2026-07-13 的 replacement Task 2 已在提交 `928e9a4` 中完成：

- 先观察到严格 RED：legacy v0.1 的 39 项合同测试通过，新 v0.2 的 44 项测试只因生产模块不存在而失败；
- 新增 breaking `AnchorResultV2` typed family，冻结 6 个 active status、computed/non-computed 字段矩阵、hard U/A/D one-hot、0/0.5/1 score、typed metric scalar kind、nullable-primary reason、Unacceptable-only override、breakdown trace、artifact/provenance 和 SHA-256 identity；
- 所有 counts/t_ns 使用 strict JSON integer，连续 metric 使用 finite strict float；NaN/Infinity、legacy `invalid_quality` 与 v0.1 quality-gate 字段均被拒绝；
- `anchor-result-0.1.0` reader/schema 未修改，合同与 schema SHA-256 分别保持 `8e70b3e8adb65dcf87d8de7f4ae853700f40af62470827e7659b983ef7474526`、`c8b6cea319c377b8a61923c5f1122c3e70a79b59f054637ff0334082b2deb5f5`；
- 最终 focused gate 为 `85 passed`，contracts+schema 回归为 `297 passed`；Ruff format/lint、`ty check`、legacy diff 与 whitespace 检查全部通过；规格复核与独立代码质量复核均 PASS。

Task 2 只实现 v0.2 typed contract 和合同 fixture；v0.2 JSON Schema/export 属于 Task 6，semantic/reference snapshots 属于 Task 3。此提交没有新增 production AnchorPlugin，故计数仍为 0/18，M4 仍未 engineering verified。

#### 3.2.4 M4 replacement Task 4 Catalog、Plan 与 Request 合同

2026-07-13 的 replacement Task 4 已在提交 `1528d09` 中完成：

- 新增版本化 catalog、plugin/provider registry、typed dependency、execution-plan、resolved input/preprocessing/scorer 与不可变 `AnchorEvaluationRequest` 合同；request 在执行前闭合 session、semantic/table/AOI/applicability、reference inventory/provenance 与 fingerprint identity；
- focused gate 为 `39 passed`，Task 3+4 related regression 为 `74 passed`，全仓为 `828 passed, 2 skipped`；两个 skip 仍只对应未配置 repository-external CSV 的 M2/M3 opt-in tests；
- Ruff format/lint、`ty check src` 与内部最终复核全部通过，最终 P0/P1 均为 0。

Task 4 只关闭 catalog/plan/request 合同边界；它没有实现 measurement/artifact/inventory/report contracts，也没有新增 production AnchorPlugin、evidence scorer 或正式 M4 workflow。真实计数仍为 0/18，M4 仍未 engineering verified；测试结果不支持科学有效性、飞行员能力或数据质量结论。

#### 3.2.5 M4 replacement Task 5 Measurement、Artifact、Inventory 与 Report 合同

2026-07-13 的 replacement Task 5 已在提交 `b63d38b` 中完成：

- 新增 measurement、artifact producer、dependency projection、canonical inventory 与 evaluation report 合同；运行时 ID/SHA/Literal/tuple 校验、递归 JSON 快照、只读表格投影、wrapper identity 与 source isolation 已收口；
- focused gate 为 `77 passed`，contracts/reference/request related regression 为 `380 passed`，全仓为 `859 passed, 2 skipped`；两个 skip 仍只对应未配置 repository-external CSV 的 M2/M3 opt-in tests；
- Ruff format/lint、`ty check src` 与两路独立终审全部通过，最终 P0/P1 均为 0。

Task 5 只关闭 measurement/artifact/inventory/report 合同边界；它没有新增任何 production AnchorPlugin、evidence scorer、artifact executor 或正式 M4 workflow。真实计数仍为 **18/18 specified、0/18 production plugins implemented**，M4 仍未 engineering verified，`formal_run_authorized=false`；测试结果不支持科学有效性、飞行员能力或数据质量结论。

#### 3.2.6 M4 replacement Task 6 Deterministic Schema Export

2026-07-13 的 replacement Task 6 已在提交 `93c4ddb` 中完成：

- 权威 exporter 从现有 strict Pydantic contracts 确定性生成 root 与 package-resource M4 schemas，并保持两处 bytes 对称；
- focused gate 为 `36 passed`，contracts/schema gate 为 `376 passed`；
- Ruff format/lint、`ty check src`、fresh build 与两路独立终审全部通过；wheel/package 检查确认 14 个 schema resources，最终 P0/P1 均为 0。

Task 6 只关闭 M4-A contract/schema slice；packaged exact-18 catalog 与 parameter resources 属于 Task 7，canonical identity 属于 Task 8。它没有新增 production AnchorPlugin、evidence scorer、artifact executor 或正式 M4 workflow。真实计数仍为 **18/18 specified、0/18 production plugins implemented**，M4 仍未 engineering verified，`formal_run_authorized=false`；测试结果不支持科学有效性、飞行员能力或数据质量结论。

### 3.3 Micro E2E

2 秒、201 行 simulator fixture 的完整 M1→M2→M3 路径通过，session window 为 `0..2_000_000_000 ns`：

| Primary artifact | raw/aligned | in-session |
|---|---:|---:|
| X samples | 201 | 201 |
| U samples | 201 | 201 |
| I frame index | 61 | 60 |
| G gaze samples | 241 | 240 |
| EEG samples | 513 | 509 |
| ECG samples | 501 | 498 |
| pilot-camera frame index | 31 | 30 |
| task reference | 201 | 201 |

Secondary counts 为 AOI `122/120`（total/in-session）、fixations `4/4/3`（total/overlap/full）、R-peaks `3/3`（total/in-session），invalid in-session scene/gaze associations 为 `0`。结果为 `disposition=ready`、`can_continue_to_anchor_availability=true`、`formal_run_authorized=false`；raw bundle bytes 在 synchronization 前后不变。

### 3.4 Repository-external captured format-sample CSV E2E

输入文件不进入 Git：

```text
C:\Users\long\Desktop\CranfieldOffer\proj\data\
S_101500_Time_2026_05_14_16_48_54_P_1.csv
```

冻结 SHA-256：

```text
19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52
```

M3 session window 为 `0..29_010_000_000 ns`。Primary 实测结果：

| Primary artifact | raw/aligned | in-session |
|---|---:|---:|
| X samples | 2,902 | 2,902 |
| U samples | 2,902 | 2,902 |
| I frame index | 871 | 871 |
| G gaze samples | 3,482 | 3,481 |
| EEG samples | 7,427 | 7,423 |
| ECG samples | 7,253 | 7,251 |
| pilot-camera frame index | 436 | 435 |
| task reference | 2,902 | 2,902 |

还验证：

- secondary counts：AOI `1,742/1,742`、fixations `59/59/58`、R-peaks `37/37`，invalid in-session scene/gaze associations 为 `0`；
- 七个 core modalities 与 task reference 全部 ready；
- 外部 CSV 与生成 bundle 的全部文件在 synchronization 前后逐字节不变；
- 所有 timed artifact 的 `interpolated_rows=0`，未建立 resampling 或 window grid；
- `formal_run_authorized=false`，synthetic scientific status 为 `not_supported`。

仓库忽略目录中保留了一份可本地检查的生成结果：

```text
local_data/m2_real_xu_synthetic_full_seed20260711/
```

这是早期遗留目录名，其中 `real_xu` 只表示当时直接复制了 repository-external CSV bytes，不表示有效任务或 ground truth；该 bundle 在 M3 gaze/frame 修复后必须重新生成。该目录不得提交或当作真实多模态采集数据。当前 M3 opt-in E2E 每次从冻结 CSV 新鲜生成临时 bundle，不依赖该遗留目录。

### 3.5 M4R 轻量 Evidence 工作流

M4R 验证采用选择性测试，不再为 provisional 专家算法维护逐 Anchor 重型 golden：

- contracts/schema、registry、validator、compiler/executor、safe formula、revision immutability 与 replay 使用平台不变量测试；
- operator library 使用小型 focused smoke；18 个 starter resources 全部加载并编译，但只对 O2 trajectory、H1 gaze、H4 physiology 做三个代表 migration wiring smoke；
- editable E2E 只使用 1 个 disturbance event 与 3 段 gaze，覆盖 incomplete autosave、补全、preview、AOI/window/scorer 修改、两次 apply、旧 revision replay、clone/new Anchor 和 disable；
- 任何第 19 个 recipe 无需修改 orchestrator 或增加 whole-Anchor plugin；
- 该验证不读取 repository-external CSV、不生成大 bundle，不证明 starter 算法或阈值科学正确。

最终 fresh gate 为 `1472 passed, 3 skipped in 211.72s`；三个 skip 仅来自当前主机不允许测试 symlink，以及两条未配置 repository-external CSV 的 opt-in E2E。Ruff lint、212-file format check、`ty check src/pilot_assessment`、schema regeneration 与 whitespace check 均通过。当前 shell 没有 `uv` CLI，因此通过同一 `uv_build` backend 的标准 PEP 517 `pip wheel` 构建；最终 wheel 为 528,687 bytes，SHA-256 `e71d48e11a6d99efab4c67ba208f2556dc33d4b9248100abba3e07a8b737f700`，其中 18 个 recipe resources、catalog 与两份新 schema 齐全。M4R completion gate 因此关闭。

## 4. 本轮自审与关闭项

本轮跨文档与集成自审未发现残余 P0。已关闭的主要 P1：

1. reference 物理目录、manifest indirection 与唯一 owner 冲突；
2. D-011 shared X/U 的 present-only 与 unique-artifact 语义；
3. stream status、privacy 与 JSON Schema/Pydantic 不对称；
4. readiness report 丢失 synthetic provenance；
5. standalone task-reference 缺少 trusted adapter；
6. adapter 缺少 content resource limits；
7. gaze nullable measurement 缺少 validity/blink guard；
8. synthetic EEG/ECG 未使用时变 `synthetic_control_driver`（仅软件测试驱动量，不是生理/工作负荷/表现证据）；
9. 29.01 s session 的最后 fixation 曾超过最后保留 gaze sample 约 1.67 ms，已由 fractional-duration 回归测试关闭。

## 5. 尚未实现

- M5 剩余：Hover starter package、轻量 workflow 与 completion gate；Task 1–9 identity、public DTO/schema、source/M4R preflight、进程内 global component repository/service、exact-pinned validation、scheme draft/atomic publish、通用 CPT validation/materialization/migration、finite-discrete exact inference/read-only influence trace 与 M4R active import/compliant TPX parallel version 已完成；
- M6：project/session/model/run persistence、受管理 artifact、JSON-RPC sidecar、run orchestration、progress/cancel/error 与 revision lock；
- M7：WinUI 3 专家设计器、Evidence/BN 画布、schema-driven 参数/CPT 表单、preview/result/trace 与版本历史；
- M8：安装包、示例项目、扩展算子指南、备份/恢复与完整交付验收；
- 生产 I/G/EEG/ECG/camera exporter profile（例如 MP4/frame index、真实设备 sidecar）及真实采集适配；
- 领域专家阈值、Anchor、sub-skill、拓扑、CPT 校准与科学有效性研究；这些是系统建成后的专家工作，不是平台实现完成门。

## 6. 下一里程碑

下一步不是旧 Task 29，也不是直接开始 WinUI。M4R 已按 [implementation plan](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md) 完成；M5 [正式规格](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) 与 [轻量 inline implementation plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) 均已批准保存。M5 plan Task 1–9 已完成，当前执行入口是 Task 10 Hover starter BN component package；代码完成状态继续按任务和 fresh tests 逐项更新。该计划覆盖：

1. 定义全局 concept/component-version contracts、lineage、content identity 和查询；
2. 定义 TaskProfile/AssessmentScheme draft、exact version selection、reference closure 与 copy-on-write atomic publish；
3. 实现 Raw Input/Evidence/BN Node 与 extraction/probabilistic 两类 edge 的独立合同、operation 和 validation；
4. 实现 EvidenceBinding、BN node/state/CPT、hard/soft/omitted observation 与 exact inference adapter；
5. 建立 scheme-level diff、undo/redo、preview、publish 与 historical replay；
6. 保持普通 Evidence/BN 修改 free-to-modify，不把人工审批、科学有效性或 per-edit pytest 加回 apply gate；
7. 通用检查 legacy recipe source provenance，保留旧 O8 并创建 D-037-compliant TPX parallel version；
8. M6 persistence/JSON-RPC 和 M7 WinUI 只保留接口边界，不在 M5 中提前宣称完成。

当前权威与历史材料见：

- [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)（已批准的当前 M5 规格）
- [M5 Shared Versioned Model Library and Bayesian Workspace Implementation Plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md)（已批准的当前 inline 实施入口）
- [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md)（M4R–M8 expert-designer 重基线）
- [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)
- [M4 Lightweight Workflow Validation Amendment](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)
- [M4 Task 3 Reference Candidate Binding Amendment](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)
- [M4 Task 7 Catalog and Resource Identity Amendment](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)
- [M4 Task 8 Canonical Fingerprint and Runtime Identity Amendment](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)
- [Autonomous Review Ledger](reviews/2026-07-13-autonomous-review-ledger.md)

两份旧实施计划均只供历史追溯。Replacement Task 0–28 的完成事实保留，但 Task 29–36 已停止且不得执行；M4R plan 已完成并保留为实现记录：

- [M4 Anchor Calculation and Evidence Availability Implementation Plan](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)
- [M4 Anchor Calculation and Evidence Availability Replacement Implementation Plan](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（Task 0–28 历史；Task 29–36 superseded）
- [M4R Editable Evidence Computation Foundation Implementation Plan](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md)（已完成；M4R 实现与验收记录）

M2 的批准规格与逐任务实施证据分别见：

- [M2 Multimodal Synthetic Foundation Design](specs/2026-07-11-multimodal-synthetic-foundation-design.md)
- [M2 Multimodal Synthetic Foundation Implementation Plan](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md)

M3 的批准规格与逐任务实施、完成门及 handoff 证据分别见：

- [M3 Native-Rate Time Synchronization Design](specs/2026-07-12-m3-native-time-synchronization-design.md)
- [M3 Native-Rate Time Synchronization Implementation Plan](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
