# Implementation Status — M1/M2/M3 Engineering Verified; M4 Tasks 0–24 Complete, M4-D In Progress

| 字段 | 当前值 |
|---|---|
| 状态日期 | 2026-07-15 |
| 产品设计基线 | v0.1 |
| 已完成里程碑 | Backend Foundation M1 + M2 Multimodal Synthetic Foundation + M3 Native-Rate Time Synchronization |
| M4 当前状态 | Replacement Task 0–24 已完成。O1–O10 的既有实现保持不变；`8672c74` 新增 O11 Disturbance Latency，并扩展共享 `events` primitive 的 gap-aware trailing causal median。Task 24 focused/受控相关 gates 分别为 `18 passed`、`229 passed`；registry verify、Ruff/format（155 files）、ty/diff 均通过。Task 20 的 `1275 passed, 3 skipped` 及 build/isolated-wheel 仍是最新 stage-gate 证据，本单 anchor 未重复重门。按用户节省额度的明确要求全程 INLINE，未走独立审查子代理。packaged registry 现有且仅有 O1–O11，capability count 为 11/18，preprocessor count 为 1（`movement-events-v1`）；registry fingerprint 为 `51af85c150678406cc8d1f83d2e357717b75fc69300363e7015dc478779a7477`，共享 primitive 更新后的 O10 digest 为 `b86a83189cb8ae5e7da965cbab0293ad928a0cefb9155f4c95594e3226854d6f`，O11 digest 为 `8618bb2d9e41e1d346f80abd4ce8d0de2fff57260029005fb7acd776c8a394c6`。因此准确口径是 **M4-B framework engineering-verified；M4-C software-verified；M4-D in progress；18/18 specified、11/18 production plugins；M4 整体尚未 engineering verified；`formal_run_authorized=false`** |
| 下一里程碑 | 执行 replacement Task 25，复用共享 `events` primitive 实现并验证 O12 Envelope-drift Latency，关闭 M4-D stage gate |
| 软件状态 | `in_progress`（M1/M2/M3 engineering verified；M4 Tasks 0–24 complete、M4-C closed、M4-D in progress、O1–O11 与 `movement-events-v1` provider available、Task 25 next；完整 Assessment Core alpha 与 Gate B 尚未完成） |
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

本结论只证明当前合同、文件不变性与 native-rate 时间计算路径按规格运行。Synthetic scene、gaze、EEG、ECG、pilot-camera、annotation 与 commanded path 均是软件测试 fixture，不是航空、生理或训练评估有效性证据。M3 不执行插值、重采样或 analysis/window grid；这些属于 M4 的 AnchorPlugin revision。

其中 repository-external simulator CSV 只是一次随意飞行产生的采集格式样例，没有标准轨迹、任务 ground truth 或能力标签。对它的 E2E 验证只证明 33-column/100 Hz 格式可以被读取、保留和转换；不证明该飞行符合任务要求，也不支持任何表现或能力结论。

2026-07-12 已将 M3 的 D-016–D-020 正式写入决策记录并完成实现：M3 只做 native-rate alignment，使用 scale-only/round-half-even clock mapping 和 master-clock X 技术时间窗口，输出独立 `SynchronizationReport`。§3 记录的完成门已经实测通过；这仍不表示完整 Assessment Core、正式 assessment run 或科学有效性已经成立。

2026-07-13 已新增并批准 [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)，把 AnchorResult v0.2、18 个 anchor、typed dependency DAG、artifact/fingerprint 和状态边界冻结为书面设计；其后 [M4 Lightweight Workflow Validation Amendment](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)、D-026/D-027 与 [replacement M4 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 也已获用户批准。2026-07-13 同日又批准 [Task 3 Reference Candidate Binding 修订](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md) 与 D-028：M3 保持不变，M4 使用 session-bound candidate 和三参数 exact binder，并在 request 前绑定 M3 reference provenance。用户休息期间按其明确默认批准授权，又形成并经两路独立 P0/P1 终审通过 [Task 7 Catalog/Resource Identity 修订](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)、[Task 8 Canonical Fingerprint/Runtime Identity 修订](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) 与 D-029/D-030；它们只关闭机器资源、深度不可变性和 canonical bytes，不改公式、阈值或 golden。原 [M4 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) 的四套 90 秒 fixture 路线已被取代且不再授权执行。Replacement Task 0–24 已完成：M4-A contracts/catalog/resources、M4-B framework、O1 Phase-state Precision、O2 Peak Tracking Excursion、O3 Terminal Capture Quality、O4 Sustained Hover Time、O5 Workload Rate、O6 Control Magnitude RMS、O7 Control Reversal Rate、O8 TPX Composite、O9 Dead-band Activity、O10 Recovery Time、O11 Disturbance Latency、共享 `events` primitive 与 `movement-events-v1` provider 已进入代码。Task 24 focused/受控相关 gate 分别为 `18 passed`、`229 passed`，registry/Ruff/format/ty/diff 均通过。M4-B framework 与 M4-C stage gate 已关闭，M4-D 正在执行，O1–O11 capability 与 `movement-events-v1` provider 均为 `available`，因此真实计数是 **18/18 specified、11/18 production plugins implemented**；M4 整体尚未 engineering verified，所有 M4 路径保持 `formal_run_authorized=false`；这些资源与测试不构成 quality gate、科学有效性或飞行员能力证明。

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

其中 `anchor-result-0.1.0.schema.json` 和 Python `AnchorResult` 是 M1 阶段建立的 legacy 0.1 合同，仍包含 quality/`invalid_quality` 语义；它们不是 M4 AnchorResult v0.2 的实现证据。Breaking `AnchorResultV2` 与 `anchor-result-0.2.0.schema.json` 已分别由 Task 2/6 显式实现和验证；Task 7 的 exact-18 catalog 与 24 个 parameter resources、Task 8–13 的 canonical/runtime framework 以及 Task 14–24 的 O1–O11 plugins、共享 event primitive 与首个 preprocessing provider 也已完成。但其余 7 个 production plugins 与完整 M4 workflow 尚未完成，不能把这些分段成果误计为 M4 全部完成。

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

- M4：O1–O11 已实现；其余 7 个 production AnchorPlugin、plugin-specific window materialization 与 raw availability 仍待实现；`AnchorResultV2`、catalog/dependency/execution-plan/immutable-request、measurement/artifact/inventory/report contracts、v0.2/M4 schema export、packaged exact-18 catalog/24 parameter resources、canonical fingerprints/runtime identity、trusted registry closure、通用 temporal/event primitives、transactional artifact sink、central scorer、typed DAG、preprocessing resolver、evaluator、public API、O1–O11 shared kernels/plugins 与 `movement-events-v1` provider 已实现，当前为 18/18 specified、11/18 production plugins 已实现；
- M4 replacement plan：Task 0–24 已完成；M4-C 已关闭、M4-D 正在执行。O1 由 `b1d1fc9` 实现，O2 由 `b1a8743` 实现，O3 由 `f7d5261` 实现，O4 由 `056d9d5` 实现，O5 与 `movement-events-v1` provider 由 `1a119af` 实现，O6 由 `2ca3540` 实现，O7 由 `eb9cca6` 实现，O8 由 `15da2ea` 实现，O9 由 `db2b5da` 实现，O10 与共享 causal boolean primitive 由 `87aed10` 实现，O11 与共享 trailing causal median 由 `8672c74` 实现，下一步执行 Task 25 O12 并关闭 M4-D；不得把 M4-D 分段进展误计为 M4 整体 engineering verification；
- M5：model bundle、33-node reference BN、CPT、missing-evidence inference、draft/revision/publish；
- M6：端到端 assessment runner、artifact/report persistence；
- JSON-RPC sidecar 与受管理存储 importer；
- WinUI 3 前端、图编辑器与 CPT 参数界面；
- 生产 I/G/EEG/ECG/camera exporter profile（例如 MP4/frame index、真实设备 sidecar）及真实采集适配；
- 领域专家阈值、anchor、sub-skill、拓扑、CPT 校准与科学有效性研究。

## 6. 下一里程碑

下一步是依据已批准的 replacement implementation plan 执行 Task 25：复用共享 `events` primitive 实现并验证 O12 Envelope-drift Latency，关闭 M4-D。Tasks 8–13 已依次关闭 canonical identity、trusted packaged registry/implementation closure、segment-aware temporal primitives、transactional artifact publication、central scoring，以及 typed DAG/preprocessing/evaluator/public API；Task 14–24 已完成 O1–O11、共享 event primitive 与首个 preprocessing provider，M4-B framework 与 M4-C stage gate 已关闭，M4-D 正在执行。Production AnchorPlugin 当前为 11/18，M4 整体尚未 engineering verified，更不能提前进入 BN、runner 或 WinUI。Replacement plan 后续覆盖：

1. M4-A：AnchorResult v0.2、catalog、execution-plan、inventory/report schemas；
2. M4-B：registry、typed DAG、temporal kernel、artifact sink、fingerprint 和 fake-plugin tests；
3. M4-C–M4-F：依次实现 O1–O7、O8–O12、H1–H3、H4/H5/O13；
4. M4-G：紧凑 exact-18 real-plugin workflows、唯一 10 秒 physical bundle E2E、扩展性、确定性、fresh-wheel 和文档关闭；
5. 贯穿所有阶段的 no-quality-gate 回归：差表现必须 `computed + Unacceptable`，M4 不生成 `invalid_quality`，computed U 的 raw availability=1；
6. 保留 source/report/fingerprint/anchor revision 的 traceability，并继续保持 `formal_run_authorized=false`；
7. 使用紧凑 all-D/all-U aligned raw inputs 验证 18-anchor 闭环，并用唯一 10 秒全模态 bundle 验证 public M1→M4；不从 captured-format CSV 推断任务、表现、生理状态或飞行员能力。

M4 当前已批准的书面规格与验证修订见：

- [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)
- [M4 Lightweight Workflow Validation Amendment](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)
- [M4 Task 3 Reference Candidate Binding Amendment](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)
- [M4 Task 7 Catalog and Resource Identity Amendment](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)
- [M4 Task 8 Canonical Fingerprint and Runtime Identity Amendment](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)
- [Autonomous Review Ledger](reviews/2026-07-13-autonomous-review-ledger.md)

原逐任务实施计划已被取代、仅供历史追溯；replacement plan 与 Task 3/7/8 amendments 已于 2026-07-13 获明确或授权默认批准，Task 0–24 已完成，M4-C 已关闭、M4-D 正在执行，下一步为 Task 25：

- [M4 Anchor Calculation and Evidence Availability Implementation Plan](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)
- [M4 Anchor Calculation and Evidence Availability Replacement Implementation Plan](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（已批准并按方案 A 修订；Task 0–24 已完成，M4-B/M4-C gate 已关闭、M4-D 正在执行，O1–O11、共享 `events` primitive 与 `movement-events-v1` provider available，下一步为 Task 25 O12）

M2 的批准规格与逐任务实施证据分别见：

- [M2 Multimodal Synthetic Foundation Design](specs/2026-07-11-multimodal-synthetic-foundation-design.md)
- [M2 Multimodal Synthetic Foundation Implementation Plan](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md)

M3 的批准规格与逐任务实施、完成门及 handoff 证据分别见：

- [M3 Native-Rate Time Synchronization Design](specs/2026-07-12-m3-native-time-synchronization-design.md)
- [M3 Native-Rate Time Synchronization Implementation Plan](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
