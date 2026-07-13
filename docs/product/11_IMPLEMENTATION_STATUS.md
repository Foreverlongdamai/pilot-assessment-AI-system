# Implementation Status — M1/M2/M3 Engineering Verified; M4 Written Design Only

| 字段 | 当前值 |
|---|---|
| 状态日期 | 2026-07-13 |
| 产品设计基线 | v0.1 |
| 已完成里程碑 | Backend Foundation M1 + M2 Multimodal Synthetic Foundation + M3 Native-Rate Time Synchronization |
| M4 当前状态 | O1–O13、H1–H5 共 18/18 完整书面设计已获批准；0/18 已实现；实施计划正在生成 |
| 下一里程碑 | 编写、复核并批准 M4 实施计划；之后才可按 M4-A–M4-G 开始 TDD，当前不得把书面设计计作实现 |
| 软件状态 | `in_progress`（M1/M2/M3 engineering verified；M4 written design only；完整 Assessment Core alpha 与 Gate B 尚未完成） |
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

2026-07-13 已新增并批准 [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)，把 AnchorResult v0.2、18 个 anchor、typed dependency DAG、artifact/fingerprint、状态边界与 fixtures 冻结为书面设计。当前仓库仍没有 `src/pilot_assessment/anchors/`，没有任何 AnchorPlugin 实现，实施计划正在生成；因此真实计数是 **18/18 specified、0/18 implemented**，M4 尚未 engineering verified。

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

其中 `anchor-result-0.1.0.schema.json` 和当前 Python `AnchorResult` 是 M1 阶段建立的 legacy 0.1 合同，仍包含 quality/`invalid_quality` 语义；它们不是 M4 AnchorResult v0.2 的实现证据。v0.2 必须在后续获批实施计划中作为显式 breaking contract 实现和验证，不能把 0.1 的存在误计为已完成 M4-A。

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

- M4：18 个 AnchorPlugin、AnchorResult v0.2、catalog/plan/report contracts、window grid、evidence likelihood、raw availability、artifact/fingerprint 与 O8/O13 派生证据；当前 18/18 已设计、0/18 已实现；
- M4 实施计划：尚未生成，也尚未批准；不得从书面规格直接跳过计划进入代码；
- M5：model bundle、33-node reference BN、CPT、missing-evidence inference、draft/revision/publish；
- M6：端到端 assessment runner、artifact/report persistence；
- JSON-RPC sidecar 与受管理存储 importer；
- WinUI 3 前端、图编辑器与 CPT 参数界面；
- 生产 I/G/EEG/ECG/camera exporter profile（例如 MP4/frame index、真实设备 sidecar）及真实采集适配；
- 领域专家阈值、anchor、sub-skill、拓扑、CPT 校准与科学有效性研究。

## 6. 下一里程碑

下一步不是直接写 AnchorPlugin，而是先完成 M4 书面规格复核，再从获批规格派生、审查并批准实施计划；在该计划存在前，不应提前跳到 M4 代码、BN、runner 或 WinUI。计划后续至少需要覆盖：

1. M4-A：AnchorResult v0.2、catalog、execution-plan、inventory/report schemas；
2. M4-B：registry、typed DAG、temporal kernel、artifact sink、fingerprint 和 fake-plugin tests；
3. M4-C–M4-F：依次实现 O1–O7、O8–O12、H1–H3、H4/H5/O13；
4. M4-G：18-anchor E2E、扩展性、确定性、fresh-wheel 和文档关闭；
5. 贯穿所有阶段的 no-quality-gate 回归：差表现必须 `computed + Unacceptable`，M4 不生成 `invalid_quality`，computed U 的 raw availability=1；
6. 保留 source/report/fingerprint/anchor revision 的 traceability，并继续保持 `formal_run_authorized=false`；
7. 使用独立的完整 all-D/all-U software fixtures 验证 18-anchor 闭环，不从 captured-format CSV 推断任务、表现、生理状态或飞行员能力。

M4 当前已批准的书面规格见：

- [M4 Anchor Calculation and Evidence Availability Design](specs/2026-07-13-m4-anchor-evidence-availability-design.md)

此处有意不链接 M4 实施计划，因为截至本状态日期该文件不存在。

M2 的批准规格与逐任务实施证据分别见：

- [M2 Multimodal Synthetic Foundation Design](specs/2026-07-11-multimodal-synthetic-foundation-design.md)
- [M2 Multimodal Synthetic Foundation Implementation Plan](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md)

M3 的批准规格与逐任务实施、完成门及 handoff 证据分别见：

- [M3 Native-Rate Time Synchronization Design](specs/2026-07-12-m3-native-time-synchronization-design.md)
- [M3 Native-Rate Time Synchronization Implementation Plan](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
