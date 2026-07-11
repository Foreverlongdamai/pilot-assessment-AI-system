# M3 Native-Rate Time Synchronization Design

| 字段 | 当前值 |
|---|---|
| 设计基线 | v0.1 |
| 日期 | 2026-07-12 |
| 范围决策 | 用户已批准 A：native-rate alignment，不插值、不重采样 |
| 实施门 | 等待用户确认本文件忠实记录已批准设计 |
| 上游 | M1 Session integrity + M2 Ingestion readiness |
| 下游 | M4 Anchor/evidence availability |

## 1. 目标

M3 把已经通过 M2 的 source-domain 多模态数据映射到统一 session nanosecond 时间轴，并产生可供 M4 使用的只读 `AlignedSession`。M3 必须：

1. 对 X、U、I、G、EEG、ECG、pilot_camera 与 bundle-local task reference 应用声明的 clock mapping；
2. 使用确定性的 round-half-even 生成 int64 `t_ns`；
3. 保留全部 source rows、source timestamps、稳定 ID 和原始值；
4. 对 point、interval 与 foreign-key-inherited temporal artifacts 使用显式版本化绑定；
5. 标记 session window 内外的 row/interval，而不删除越界原始数据；
6. 验证 phase、event、baseline、reference 与 scene/gaze 的 session-time 结构语义；
7. 输出确定性的 `SynchronizationReport` 和内部 `AlignedSession`；
8. 保持 `formal_run_authorized=false`，不冒充 `RunPreflightReport`。

M3 只证明时间映射和结构关系按当前合同执行。它不证明 annotation、physiology、anchor 或评估模型具有科学有效性。

## 2. 明确不进入 M3 的内容

- 不插值、重采样或滤波任何测量值；
- 不创建固定 100 Hz 或其他全局 analysis grid；
- 不选择 anchor-specific window length、step、partial-window policy 或 valid-fraction threshold；
- 不计算 fixation-v1、EEG/ECG 特征、18 个 anchor、evidence、coverage-to-competency 或 BN posterior；
- 不解析 model-bundle reference artifact；
- 不创建 `RunPreflightReport` 或正式 AssessmentRun；
- 不写回、覆盖或迁移原始 Session Bundle；
- 不把 synthetic annotation 标记升级为 reviewed 或 scientifically validated。

M4 可以使用 M3 的 aligned native-rate views、coverage intervals 和匹配工具建立每个 AnchorPlugin 自己的 analysis/window grid。

## 3. 已采用方案与备选方案

### 3.1 采用：独立 synchronization wrapper

~~~text
M1 LoadedManifest snapshot
          +
M2 PreparedSession + IngestionReadinessReport
          ↓
SynchronizationInput
          ↓
native-rate clock/annotation/reference alignment
          ↓
AlignedSession + SynchronizationReport
          ↓
M4 anchor/evidence availability
~~~

`SynchronizationInput` 组合 M3 所需的 manifest、verified artifact identity、M2 source fingerprint 和内存 normalized tables。它不向 `PreparedSession` 强行加入 bundle root、clock mapping 或 annotation I/O，因此不破坏 M2 的职责和已有构造器。

M2 readiness 将提供一个消费已加载 `LoadedManifest` 的内部入口。`synchronize_bundle()` 只执行一次 M1 load/hash，然后在同一 snapshot 上完成 M2 与 M3，避免为了取得 clock/annotation 信息重复加载整个 bundle。

### 3.2 未采用：直接扩充 PreparedSession

实现较短，但会把 source parsing、文件 snapshot、clock contract 与 annotation I/O 塞入 ingestion container，并破坏已有 adapter/test 构造。该方案不采用。

### 3.3 未采用：立即生成持久化 aligned Parquet

持久 artifact 最终有价值，但 managed storage、cache lifecycle、atomic persistence 与 cleanup 尚未实现。M3 v0.1 先产生不可变的 in-process aligned views；持久 cache 属于后续 persistence/pipeline 里程碑。

## 4. 模块边界

~~~text
src/pilot_assessment/
  contracts/
    synchronization.py       # 公共 report、interval、policy DTO
  synchronization/
    __init__.py              # 稳定 Python API
    models.py                # internal input/aligned view/outcome
    clock.py                 # 唯一 Decimal/half-even/int64 实现
    bindings.py              # point/interval/inherit temporal binding
    profiles.py              # package-resource binding catalog loader
    annotations.py           # bounded strict JSON + aligned annotations
    quality.py               # coverage/gap/duplicate/association metrics
    service.py               # M1→M2→M3 orchestration
    profile_data/
      m3-temporal-bindings-0.1.json
~~~

`contracts` 不暴露 Polars。`AlignedSession` 和 `AlignedStreamView` 是 Python Core 内部对象；未来 JSON-RPC 只暴露 `SynchronizationReport` 和受管理 artifact handle。

## 5. 输入边界与 snapshot

内部输入固定为：

~~~python
@dataclass(frozen=True, slots=True)
class SynchronizationInput:
    loaded_manifest: LoadedManifest
    readiness_report: IngestionReadinessReport
    prepared_session: PreparedSession
~~~

约束：

- readiness disposition 为 `blocked` 时不能构造 `SynchronizationInput`；
- `readiness_report.source_snapshot_fingerprint` 必须对应同一个 `LoadedManifest`；
- `PreparedSession` 的 streams/reference 必须与 readiness 中的 ready results 一致；
- M3 读取 annotation 前重新对所读取 bytes 计算 SHA-256，并与 M1 snapshot 比较；
- annotation 每文件最多 4 MiB、每类最多 100,000 条记录；读取使用严格 UTF-8、重复 key 拒绝、NaN/Infinity 拒绝；
- M3 使用内存中的 normalized stream tables，不再次从路径读取已适配的测量表；
- 该 snapshot 仍是 inspect-only software boundary，不是 managed-storage formal import authorization。

Top-level `synchronize_bundle()` 在 M2 blocked 时直接构造 `SynchronizationReport(disposition=blocked)`，保留 M2 issues，并返回 `aligned_session=None`；只有 M2 non-blocked 路径才进入 `synchronize_session(SynchronizationInput, policy)`。因此 blocked 输入不会绕过 M2，也不要求伪造一个空 `PreparedSession`。

## 6. Clock contract

### 6.1 唯一映射公式

对 source timestamp `s`：

~~~text
t_ns = round_half_even(Decimal(str(s)) × Decimal(str(scale)) × 1_000_000_000
                       + Decimal(offset_ns))
~~~

- `scale` 是映射的唯一计算权威；
- `drift_ppm` 是冗余审计值，不得再次乘入映射；
- 必须满足 `abs(drift_ppm - (scale - 1) × 10^6) <= 0.000001 ppm`；
- `scale > 0`；
- `residual_max_ms >= residual_rms_ms`；
- source timestamp、scale、offset、结果均必须有限且结果位于 signed int64；
- overflow、inconsistent scale/drift 或 unsupported mapping 产生结构化 blocking issue；
- 计算不得依赖二进制 float 的隐式 rounding mode。

Half-even golden cases至少固定：`0.5 ns→0`、`1.5 ns→2`、`2.5 ns→2`，以及 int64 正负边界和 overflow。

### 6.2 同一 clock_id

同一 `clock_id` 的 present logical streams 必须声明相同 `method`、`scale`、`offset_ns` 和 `drift_ppm`。Residual 可以按 stream 分别报告，但不得改变 mapping。D-011 shared X/U 必须得到逐行完全相同的 `t_ns` 和 `in_session`。

### 6.3 重复 mapped timestamp

正 scale 仍可能因 ns rounding 让多个 source rows 映射到相同 `t_ns`。重复值合法，但 binding 必须声明稳定 ID/index；aligned order 为 `(t_ns, stable_id...)`，不得聚合或丢行。报告记录 duplicate timestamp group 与 row count。

## 7. Session window

v0.1 只支持 `session_timebase.origin=session_start`。Canonical window 为：

~~~text
start_t_ns = 0
end_t_ns   = max(mapped X primary-table t_ns)
source     = master-clock-x-mapped-coverage-v1
~~~

额外约束：

- X 必须通过 M2、存在于 `PreparedSession`，并使用 manifest 声明的 `master_clock_id`；
- `end_t_ns` 必须大于 0；
- window 使用闭区间 `[0, end_t_ns]`；
- synthetic extension 中的 `duration_s` 只用于 golden cross-check，不成为另一套权威；
- 未来 manifest 若显式声明 session window，必须通过新的决策和 bundle minor/major 兼容规则引入，不能静默改变 v0.1 推导规则。

Point row 的 `in_session` 为 `0 <= t_ns <= end_t_ns`。负 offset 或尾端越界 row 保留在 aligned table 中并标记 false。

## 8. Temporal binding catalog

禁止根据列名后缀猜测时间语义。Package resource 按 `stream_schema_id + artifact_role` 显式声明：

- `point`：一个 source timestamp → `t_ns` + `in_session`；
- `interval`：start/end source timestamps → `start_t_ns`、`end_t_ns`、`overlaps_session`、`fully_in_session`；
- `inherit`：通过稳定 foreign key 从已对齐 parent role 继承 `t_ns`/window flag；
- `untimed`：JSON sidecar、图像 bytes 等保持原样，不伪造时间列。

v0.1 至少覆盖：

| Stream/role | 模式 | 结果 |
|---|---|---|
| X/samples | point | `t_ns`, `in_session` |
| U/samples | point | `t_ns`, `in_session` |
| I/frame_index | point | `t_ns`, `in_session` |
| I/aoi_instances | inherit by frame_id | `t_ns`, `in_session` |
| G/gaze_samples | point | `t_ns`, `in_session` |
| G/fixations | interval | start/end ns + overlap/full flags |
| EEG/samples | point | `t_ns`, `in_session` |
| ECG/samples | point | `t_ns`, `in_session` |
| ECG/r_peaks | point | `t_ns`, `in_session` |
| pilot_camera/frame_index | point | `t_ns`, `in_session` |
| task_reference/samples | point | `t_ns`, `in_session` |

每个 binding 声明 aligned schema ID、source/target time columns、stable keys、parent/foreign keys 和 expected raw schema。Unknown present schema/role 不得走猜测 fallback。

Aligned DataFrame：

- 保持 raw column 顺序与值；
- 在末尾追加 binding 声明的 Int64/Boolean columns；
- 保持 row count；
- point table 的 `t_ns` 单调非递减；
- inherit join 保持 child row order，missing/duplicate parent key 使该 artifact invalid；
- 不改变 image、EEG/ECG 数值或任何 source artifact。

## 9. Annotation alignment

### 9.1 支持的输入族

M3 v0.1 使用 schema-ID registry，不按任意 JSON 猜测：

1. 当前 M2 synthetic schemas：`phases-synthetic-v0.1`、`events-synthetic-v0.1`、`baseline-intervals-synthetic-v0.1`；其中 `_s` 字段明确表示相对 session origin 的秒；
2. `phases-session-time-v0.1`：顶层必需 `schema_id`、`annotation_revision`、`timebase={origin:session_start,unit:ns}`、`annotation_source` 和 `phases`；每个 phase 必需 `phase_id`、`label`、`start_t_ns`、`end_t_ns`、`source`、`confidence`；
3. `events-session-time-v0.1`：相同顶层时间合同；每个 event 必需 `event_id`、`event_type`、`t_ns`、`source`、`confidence`，可选严格非负 `duration_ns` 和结构化 `response_mapping`；
4. `baseline-intervals-session-time-v0.1`：相同顶层时间合同；每个 interval 必需 `interval_id`、`start_t_ns`、`end_t_ns`、`condition`、`valid`，`valid=false` 时必须提供 `exclusion_reason`。

正式 session-time schemas 已经位于 canonical session clock，M3 重验 int64、window 和结构语义，不再次应用 device clock。Unknown schema ID 返回 `ANNOTATION_SCHEMA_UNSUPPORTED`；不允许隐式 device clock 或字段名猜测。

Synthetic `start_s/end_s/time_s` 通过同一 Decimal half-even 秒→ns函数转换，但不应用任何 device clock mapping。`synthetic_semantics_unvalidated=true` 原样进入 aligned provenance。

### 9.2 Phase rules

- phase ID 唯一；
- manifest `expected_phases` 中每个 ID 必须出现且顺序一致；
- interval 必须满足 `start_t_ns < end_t_ns`；
- phase 不能重叠或逆序；允许 session 前后存在未标注区间，并在 report 显示；
- phase 必须 fully in session；
- boundary 采用 start-inclusive/end-exclusive，最后一个且 `end_t_ns=session_end` 的 phase 对 session endpoint inclusive。

### 9.3 Event rules

- event ID 唯一；
- point event 必须在闭 session window；
- duration event 必须正值且与 session 相交；
- response mapping、observation horizon 和 expected channel 等 anchor-specific 语义只验证是否声明，不在 M3 猜测或执行；
- synthetic event 保持 semantic-unvalidated 状态。

### 9.4 Baseline rules

- interval ID 唯一；
- `start_t_ns < end_t_ns`；
- baseline 必须 fully in session；
- baseline 可以与 phase 重叠，这是生理 normalization 的正常上下文；
- baseline validity/exclusion metadata 原样保留，M3 不判定 EEG/ECG 科学适用性。

## 10. Task reference

### 10.1 Bundle-local reference

M2 已准备的 `task_reference` 使用自己的 descriptor clock mapping 和 temporal binding，对齐后独立保存在 `AlignedSession.task_reference`。报告记录 reference ID、schema、checksum、total/in-session rows、coverage start/end 和 gap metrics。

Required bundle reference mapping失败、无 in-session rows或 source snapshot 不一致时 M3 blocked。

### 10.2 Model-bundle reference

`source=model_bundle` 在 M3 标记 `deferred_model_bundle_resolution`，不是 missing 或 invalid。M3 可以继续；锁定 model revision 后由 Run Preflight 解析 reference ID、hash 与 task compatibility。

## 11. Scene/gaze time relationship

M2 已验证 gaze foreign key 和 frame-specific AOI membership；M3 增加时间验证：

- 只评估 `in_session=true` 的 gaze rows；
- scene frame presentation interval 为 `[frame_t_ns, next_frame_t_ns)`；最后一个 in-session frame 延伸到 session end；
- gaze row 引用的 frame 必须覆盖该 gaze `t_ns`；
- AOI row 从对应 frame 继承时间；
- report 记录 gaze-to-frame-start delta 的 min/max 和 invalid association count；
- out-of-session gaze/frame rows不伪装为关系错误，但保留在 row counts；
- residual 或 anchor-specific timing tolerance 的可接受性留给锁定 policy/model 后的 gate，M3 仍报告原始 residual 和 association metrics。

## 12. Quality metrics

每个 aligned point artifact 至少报告：

- total、in-session、before-session、after-session rows；
- first/last mapped time；
- in-session temporal span 与 session-span ratio；
- duplicate timestamp groups/rows；
- observed median period、gap threshold、gap count、max gap；
- source descriptor residual RMS/max；
- interpolated rows 固定为 0；
- schema/binding/clock identifiers。

`SynchronizationPolicy` 是严格、可 hash 的版本化 DTO。默认值精确为：

~~~text
contract_version = 0.1.0
policy_id = native-alignment-engineering-v0.1
gap_detection_multiplier = 5.0
clock_consistency_tolerance_ppm = 0.000001
~~~

`gap_detection_multiplier` 只决定 diagnostic gap threshold，不使 optional stream 自动 blocked。Task/anchor-specific residual、overlap和最大时差门槛不硬编码进 M3 disposition。更改默认字段或语义需要新的 policy ID；每次运行在 report 中保存完整 policy 与 fingerprint。

## 13. Internal aligned models

~~~python
@dataclass(frozen=True, slots=True)
class AlignedStreamView:
    modality: str
    source_schema_id: str
    aligned_schema_id: str
    clock_id: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_checksums: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AlignedSession:
    session_id: str
    window: SessionWindow
    streams: Mapping[str, AlignedStreamView]
    context: Mapping[str, JsonValue]
    annotations: AlignedAnnotations
    task_reference: AlignedStreamView | None
    source_snapshot_fingerprint: str
    synchronization_fingerprint: str
~~~

所有 mappings 复制后用 immutable proxy 包装。M3 不向 public contracts 暴露 Polars。

## 14. Public SynchronizationReport

`SynchronizationReport` 使用 JSON Schema 2020-12，至少包含：

~~~text
contract_version = 0.1.0
validation_scope = native_rate_session_time_alignment_v1
session_id
source_readiness_fingerprint
policy_id / policy_fingerprint / binding_catalog_fingerprint
session_window
disposition = ready | ready_partial | blocked
can_continue_to_anchor_availability
formal_run_authorized = false
stream_results[exact seven core modalities]
task_reference_result
annotation_result
global_issues
synchronization_fingerprint
~~~

Per-stream result 包含输入 readiness/status、clock summary、primary/secondary artifact temporal metrics、aligned schema IDs、issues。Task reference 继续单独报告，不能混入 core modality coverage。

### 14.1 Disposition

- `blocked`：M2 blocked；X/master session window不能建立；required stream/reference无法对齐；clock declaration冲突/overflow；required temporal binding缺失；phase/annotation结构无效；或 snapshot改变；
- `ready_partial`：required synchronization prerequisites成功，但 optional stream在 M2 不可用或其 M3 alignment invalid/unsupported；
- `ready`：所有 applicable M2-ready streams成功对齐，annotations有效，bundle reference已对齐或合法 model-bundle reference已明确 deferred。

只有非 blocked report 才有 `AlignedSession`，并设置 `can_continue_to_anchor_availability=true`。所有 disposition 下 `formal_run_authorized=false`。

## 15. Determinism and fingerprints

`synchronization_fingerprint` 由以下 canonical facts 计算：

- M2 source snapshot fingerprint；
- manifest session/timebase/clock facts；
- policy canonical JSON 与版本；
- temporal binding catalog bytes/hash；
- 每个 artifact 的 aligned time columns 和 flags，以固定 little-endian int64/boolean bytes编码；
- aligned annotation canonical JSON；
- sorted issues/statuses。

绝对路径、wall-clock time、host、Python object ID 和 DataFrame internal representation 不进入 fingerprint。Raw measurement identity由 M2 source checksums覆盖，不重复序列化全部 signal values。

## 16. Error model

错误继续使用 `DomainErrorData`。M3 至少稳定定义：

| Code | 条件 |
|---|---|
| `SYNCHRONIZATION_INPUT_BLOCKED` | M2 不允许进入同步 |
| `SESSION_WINDOW_UNAVAILABLE` | X/master window 无法确定 |
| `CLOCK_DECLARATION_INCONSISTENT` | scale/drift 或同 clock mapping 冲突 |
| `TIMESTAMP_OUT_OF_INT64_RANGE` | mapped ns overflow |
| `TEMPORAL_BINDING_NOT_FOUND` | 无受信 schema/role binding |
| `TEMPORAL_ORDER_INVALID` | mapped order 与稳定 ID 规则不满足 |
| `TEMPORAL_PARENT_KEY_INVALID` | inherit relation 缺失或重复 parent key |
| `ANNOTATION_SCHEMA_UNSUPPORTED` | annotation schema 未注册 |
| `ANNOTATION_SEMANTICS_INVALID` | phase/event/baseline 结构违反合同 |
| `REFERENCE_ALIGNMENT_FAILED` | required bundle reference 无法使用 |
| `SCENE_GAZE_TIME_MISMATCH` | in-session gaze 不在声明 frame interval |
| `SOURCE_CHANGED_DURING_SYNCHRONIZATION` | annotation/snapshot digest 变化 |

错误排序必须确定，diagnostics 有大小上限，不包含原始图像、EEG/ECG signals 或参与者身份信息。

## 17. TDD and validation matrix

生产实现按以下顺序逐项经历 RED→GREEN：

1. public DTO、disposition invariant 与 JSON Schema parity；
2. Decimal half-even、int64 boundary/overflow；
3. scale/drift、residual 与 same-clock declaration；
4. point binding：追加列、raw rows/values不变；
5. session boundary mask、negative/tail offsets；
6. duplicate mapped ns + stable key；
7. fixation interval、R-peak point、AOI inherit；
8. strict annotation reader 与 phase/event/baseline semantics；
9. bundle/model reference status；
10. gaze-to-scene presentation interval；
11. per-stream quality metrics、partial/blocked orchestration；
12. deterministic fingerprint replay；
13. micro full M2→M3 E2E；
14. opt-in repository-external real CSV M2→M3 E2E；
15. wheel resource smoke、full tests、Ruff、ty、build。

Micro 2 s golden primary counts：

| Modality | raw/aligned rows | in-session rows |
|---|---:|---:|
| X | 201 | 201 |
| U | 201 | 201 |
| I | 61 | 60 |
| G | 241 | 240 |
| EEG | 513 | 509 |
| ECG | 501 | 498 |
| pilot_camera | 31 | 30 |
| task_reference | 201 | 201 |

29.01 s real-X/U + synthetic modalities golden primary counts：

| Modality | raw/aligned rows | in-session rows |
|---|---:|---:|
| X | 2,902 | 2,902 |
| U | 2,902 | 2,902 |
| I | 871 | 871 |
| G | 3,482 | 3,481 |
| EEG | 7,427 | 7,423 |
| ECG | 7,253 | 7,251 |
| pilot_camera | 436 | 435 |
| task_reference | 2,902 | 2,902 |

E2E 还必须确认原 CSV bytes/hash、raw Parquet 和 PNG bytes 均未改变。Synthetic output仍标记 `not_supported`，不能成为正式 assessment result。

## 18. Cross-document decisions to ratify with implementation

实施前正式写入 `DECISIONS.md`：

- D-016：M3 只产生 native-rate aligned views，不插值/重采样；
- D-017：`scale` 是 clock mapping 权威，drift_ppm 只校验一次；
- D-018：v0.1 session window 由 master-clock X mapped coverage 推导；
- D-019：synthetic annotations 是 session-relative seconds，model-bundle reference 在 M3 deferred；
- D-020：M3 使用独立 `SynchronizationInput` snapshot 和 public `SynchronizationReport`。

同步修正文档：

- `03_SESSION_BUNDLE_SPEC.md` 中 raw schema 必须携带 `t_ns` 的冲突描述；
- `09_VALIDATION_AND_HANDOFF.md` 中把 M3 native mapping 与 M4 interpolation/window tests 分开；
- `10_DESIGN_SELF_REVIEW.md` 和 `11_IMPLEMENTATION_STATUS.md` 的旧实施状态；
- `GLOSSARY.md` 增加 SynchronizationInput、AlignedSession、SynchronizationReport；
- `README.md` 收录本规格和后续实施计划。

## 19. Completion definition

M3 只有在以下条件全部满足时才能标记 engineering verified：

- D-016–D-020 已接受且产品文档无相反口径；
- public report schema、temporal binding catalog 和 annotation profiles 已版本化；
- micro 与 real-CSV opt-in E2E 得到冻结的 raw/in-session counts；
- 所有 raw source bytes/checksums保持不变；
- partial/blocked、overflow、clock conflict、annotation/reference failure 有回归测试；
- full pytest、Ruff format/lint、ty、schema regeneration、build 和 isolated-wheel smoke通过；
- Git 不跟踪 local full bundle；
- 状态文档明确 M4/M5/M6、managed importer、Run Preflight、sidecar 与 WinUI 仍未实现；
- `formal_run_authorized=false` 和 synthetic scientific status 在所有报告路径保持不变。
