# Implementation Status — Backend Foundation M2

| 字段 | 当前值 |
|---|---|
| 状态日期 | 2026-07-11 |
| 产品设计基线 | v0.1 |
| 已完成里程碑 | Backend Foundation M1 + M2 Multimodal Synthetic Foundation |
| 软件状态 | `in_progress`（M2 verified，不代表完整 Assessment Core alpha） |
| 科学状态 | synthetic 数据为 `not_supported`；评估模型仍待领域专家校准与验证 |
| Python package | `pilot-assessment-system 0.1.0` |
| 本地运行边界 | Windows、离线、目录形式 Session Bundle |

## 1. 本轮结论

M2 已实现并通过 micro fixture 与真实 simulator CSV 两条端到端路径。系统现在可以：

1. 将当前 combined simulator CSV 作为一个受验证的共享物理文件，分别形成 X 与 U 两个逻辑 view；
2. 保留 I、G、EEG、ECG、pilot_camera 与 bundle-local task reference 的版本化理想输入合同；
3. 使用真实 X/U 的时间范围与控制活动，生成确定性的 synthetic 多模态软件测试数据；
4. 重新经过 M1 integrity gate 与 M2 content/adapter gate；
5. 输出严格的 `IngestionReadinessReport` 与内部 `PreparedSession`，允许进入 M3 synchronization，但永远不授权正式 assessment run。

本结论只证明当前合同与计算路径按规格运行。Synthetic scene、gaze、EEG、ECG、pilot-camera、annotation 与 commanded path 均是软件测试 fixture，不是航空、生理或训练评估有效性证据。

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
- 已发布三份 JSON Schema 2020-12：
  - `session-manifest-0.1.0.schema.json`
  - `anchor-result-0.1.0.schema.json`
  - `ingestion-readiness-report-0.1.0.schema.json`
- 可由 JSON Schema 表达的 status/privacy/task-reference/result ownership/disposition 约束已经与 Pydantic 对称；必须访问文件系统、重算 hash 或比较动态 path/checksum 集合的规则保留为 backend runtime invariant。

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
- 将 `control_activity(t)=min(1, abs(Pilot Lon)/100)` 线性重采样到 EEG/ECG source grid，形成可测试的时变 physio-control coupling；
- canonical manifest、checksum、stable session ID 与 synthetic provenance；
- 生成后自动执行 M1 和 M2 自检；只要任一适用模态未 ready，就拒绝将 bundle 作为完成结果返回。

## 3. 验证证据

### 3.1 环境

| 组件 | 实测版本 |
|---|---:|
| Python | 3.11.15 |
| Polars | 1.42.1 |
| Pillow | 12.3.0 |
| Pydantic | 2.13.4 |

### 3.2 自动化完成门禁

2026-07-11 在当前工作树重新执行：

- 默认测试集：`350 passed, 1 skipped`；skip 仅为需要显式外部 CSV 路径的 real-data E2E；
- real CSV opt-in E2E：`1 passed`；
- Ruff format check、Ruff lint、ty：全部通过；
- `uv build`：成功生成 sdist 与 wheel；
- 安装 wheel 的隔离环境可读取 packaged profiles、生成 micro bundle，并返回 `ready / true / false`（disposition / can-continue / formal-authorized）。

### 3.3 Micro E2E

2 秒、201 行 simulator fixture 的完整 M2 路径通过：

| 结果 | 行/帧数 |
|---|---:|
| X / U | 201 / 201 |
| I frame index | 61 |
| G gaze samples | 241 |
| EEG samples | 513 |
| ECG samples | 501 |
| pilot-camera frame index | 31 |
| task reference | 201 |

结果为 `disposition=ready`、`can_continue_to_synchronization=true`、`formal_run_authorized=false`。

### 3.4 Repository-external real CSV E2E

输入文件不进入 Git：

```text
C:\Users\long\Desktop\CranfieldOffer\proj\data\
S_101500_Time_2026_05_14_16_48_54_P_1.csv
```

冻结 SHA-256：

```text
19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52
```

实测结果：

| Artifact | 行/帧数 |
|---|---:|
| X / U | 2,902 / 2,902 |
| I frame index / AOI instances | 871 / 1,742 |
| G gaze samples / fixations | 3,482 / 59 |
| EEG samples | 7,427 |
| ECG samples / R-peaks | 7,253 / 37 |
| pilot-camera frame index | 436 |
| task reference | 2,902 |

还验证：

- source time 0–29.01 s，observed rate 约 100 Hz；
- `Pilot Lon` 范围 -100 至 0；
- context 为 control mode 1、time delay 0.2 s、longitudinal frequency 8 rad/s、damping 0.8；
- 七个 core modalities 与 task reference 全部 ready；
- 生成 bundle 共 1,323 个文件，约 1.60 MB；
- 原始 CSV 在生成前后字节与 hash 不变；
- `formal_run_authorized=false`，synthetic scientific status 为 `not_supported`。

仓库忽略目录中保留了一份可本地检查的生成结果：

```text
local_data/m2_real_xu_synthetic_full_seed20260711/
```

该目录不得提交或当作真实多模态采集数据。

## 4. 本轮自审与关闭项

本轮跨文档与集成自审未发现残余 P0。已关闭的主要 P1：

1. reference 物理目录、manifest indirection 与唯一 owner 冲突；
2. D-011 shared X/U 的 present-only 与 unique-artifact 语义；
3. stream status、privacy 与 JSON Schema/Pydantic 不对称；
4. readiness report 丢失 synthetic provenance；
5. standalone task-reference 缺少 trusted adapter；
6. adapter 缺少 content resource limits；
7. gaze nullable measurement 缺少 validity/blink guard；
8. synthetic EEG/ECG 未使用时变 control activity；
9. 29.01 s session 的最后 fixation 曾超过最后保留 gaze sample 约 1.67 ms，已由 fractional-duration 回归测试关闭。

## 5. 尚未实现

- M3：clock mapping、round-half-even `t_ns`、session-window mask、跨模态同步质量与 annotation/reference 语义校验；
- M4：18 个 AnchorPlugin、window grid、evidence likelihood、coverage 与 O8/O13 派生证据；
- M5：model bundle、33-node reference BN、CPT、missing-evidence inference、draft/revision/publish；
- M6：端到端 assessment runner、artifact/report persistence；
- JSON-RPC sidecar 与受管理存储 importer；
- WinUI 3 前端、图编辑器与 CPT 参数界面；
- 生产 I/G/EEG/ECG/camera exporter profile（例如 MP4/frame index、真实设备 sidecar）及真实采集适配；
- 领域专家阈值、anchor、sub-skill、拓扑、CPT 校准与科学有效性研究。

## 6. 下一里程碑

下一步应进入 M3 synchronization，不应提前跳到 anchor 或 BN：

1. 对每个 RawStream 应用 `clock_sync.scale/offset/drift`；
2. 使用 round-half-even 生成 int64 session `t_ns`；
3. 保留 raw source rows，并显式标记 in-session/out-of-session；
4. 建立 native-rate temporal coverage、gap、duplicate 和越界指标；anchor-specific analysis/window grid 留给 M4；
5. 验证 phase/event/baseline/reference 的 session-time 语义；
6. 输出可供 M4 anchor engine 消费的 aligned session，同时继续保持 `formal_run_authorized=false`。

M2 的批准规格与逐任务实施证据分别见：

- [M2 Multimodal Synthetic Foundation Design](specs/2026-07-11-multimodal-synthetic-foundation-design.md)
- [M2 Multimodal Synthetic Foundation Implementation Plan](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md)
