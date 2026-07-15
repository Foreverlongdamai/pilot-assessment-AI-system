# M4 Task 3 Reference Candidate Binding Amendment

| 字段 | 当前值 |
|---|---|
| 文档类型 | M4 已批准规格与 replacement plan 的 Task 3 正式定向修订 |
| 日期 | 2026-07-13 |
| 方向状态 | 用户已批准方案 A：新增独立 `ReferenceViewCandidate`，不修改 M3 |
| 书面状态 | 已于 2026-07-13 获用户明确批准；本文现为 Task 3 权威修订 |
| 实现状态 | 已由提交 `e054620` 完成；后续 replacement Task 4–28 亦已完成，M4-C/M4-D/M4-E 已关闭，当前下一步为 Task 29 H4；18/18 specified、15/18 production plugins implemented，这不代表 M4 整体完成 |
| 取代范围 | 取代 replacement plan Task 3 原两参数 binder、未展开的 semantic/reference 字段口径和 `ResolvedReferenceSet` 缺失的 session identity；并为 Task 8、32、34、35 补充该端口的既有职责落点 |
| 不变范围 | M1/M2/M3 合同、18 个 anchor 算法/阈值、AnchorResult v0.2、DAG、轻量测试策略及 M4 完成门均不变 |

## 1. 修订原因

原 Task 3 要求：

```python
def bind_resolved_reference_snapshot(
    snapshot: ResolvedReferenceSetSnapshot,
    aligned_session: AlignedSession,
) -> ResolvedReferenceSet:
    ...
```

同时又要求 binder 精确校验 reference 的 table/schema/frame/unit/source identity，并支持 bundle-local 与 ModelBundle 两种 reference。当前 M3 `AlignedStreamView` 只保存 modality、source/aligned schema、clock、tables、artifacts 和 source checksums，不保存权威 coordinate-frame/unit 合同；`AlignedSession` 也只有一个 bundle-local `task_reference` 槽位，M3 对 `source=model_bundle` 明确保持 deferred。

因此原两参数签名无法同时诚实满足两项要求：

1. 它不能独立判断 frame/unit 是否匹配；
2. 它不能接收已由 ModelBundle 解析并映射到 session time 的 present reference view。

方案 A 在 upstream preflight 与 M4 之间增加一个内部、受信的 candidate 边界：candidate 携带 runtime view，以及由源 profile/manifest 或已验证 ModelBundle resource 产生的 table/frame/unit/resource/session-mapping 合同。Descriptor 的期望合同来自冻结配置，session-specific identity 由 preflight 冻结。binder 只在两边精确一致时绑定，不根据列名、列数或数据形状猜测。

## 2. 权威性与适用范围

本文获批并生效后：

- 本文优先于 [replacement M4 实施计划](../plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) Task 3 原 binder 小节；
- M4 主规格和轻量工作流修订继续是其余 M4 设计的权威来源；
- replacement plan 必须修改 Task 3，并只对 Task 4/8/13/32/34/35 补充本文明确列出的 identity/producer 职责和测试；不得改变 anchor 公式、阈值或其他 task ownership；
- 不修改 `AlignedStreamView`、`AlignedSession`、M3 schema 或 M3 golden 数字；
- D-028 只授权 M5/M6 在 M3 之外使用相同 immutable container shape 承载已映射 ModelBundle reference；M3 本身继续 deferred；
- 不在 Task 3 实现 reference source resolver、ModelBundle loader、JSON Schema export、catalog/plan/request、fingerprint 计算、插件或 anchor 公式。

## 3. 设计原则

1. **序列化与 runtime 分离。** `SessionSemanticSnapshot`、reference descriptor 和 `ResolvedReferenceSetSnapshot` 是 strict/frozen Pydantic 合同；含 Polars view 的对象只使用内部 frozen dataclass。
2. **配置与来源双边绑定。** descriptor 的期望 table/frame/unit 来自冻结配置；candidate 的同名合同与 resource/session-mapping identity 来自受信 source resolver。candidate 不能由 UI 或任意请求 JSON 直接构造后视为可信；dataclass 本身不是信任证明。
3. **精确绑定。** binder 不按相同列数、相同列名、相同 shape 或相似 modality 回退。
4. **缺失不等于损坏。** 合法 `absent` descriptor 保留为 `aligned_view=None`；present descriptor 缺 candidate 或任一 identity 错配是 binding error，不能降级成 absent。
5. **不复制 source。** 成功绑定后保留 `AlignedStreamView` 和其中 DataFrame 的对象身份；输入 session 不变。
6. **不引入质量门。** 本任务只验证合同和来源身份，不依据轨迹、控制、生理数值或 coverage 好坏过滤 evidence。

## 4. 公共基础类型与枚举

`src/pilot_assessment/contracts/anchor_execution.py` 复用 `contracts/common.py` 的 `StableId`、`Sha256Digest`、`FiniteFloat`、`PositiveFiniteFloat`、`NonNegativeFiniteFloat`、`Int64`、`NonNegativeInt64`、`NonNegativeInt`、`UnitInterval` 和 `StrictContractModel`，并复用 M3 的 `MAX_SESSION_END_NS_V0_1`。

新增 `UnitName`：1–64 个 ASCII 字符，精确匹配 `[A-Za-z0-9%*/^._-]+`；允许 `m/s`、`deg/s`、`uV`，禁止空白和控制字符，大小写有语义。它不是 `StableId`，因为单位合法字符集不同。

新增 `AuditText`：1–512 个字符的严格非空字符串，仅用于原样保留上游审计说明，不作为 scorer 输入。

新增 `ResourceRelativePath`：相对于当前 reference resource owner root 的 canonical POSIX 文件路径；拒绝绝对路径、URI、反斜杠、空/`.`/`..` segment、Windows 尾点/尾空格和大小写折叠重复。它与 `BundleRelativePath` 使用同等级的安全规则，但名称不把 ModelBundle resource 误称为 Session Bundle 路径。

所有 integer 字段都拒绝 bool 和 float。`session_start_t_ns: Literal[0]` 与 `correct_sign: Literal[-1,1]` 必须各自使用 `mode="before"` validator 并要求 `type(value) is int`；不能依赖 Pydantic `Literal` 的相等比较。

枚举值精确冻结为：

| 枚举 | 值 |
|---|---|
| `SemanticApplicabilityStatus` | `applicable`, `not_applicable` |
| `AoiGeometryKind` | `dynamic_2d`, `dynamic_3d`, `polygon_2d`, `box_3d`, `catch_all` |
| `BaselineModality` | `ECG`, `EEG` |
| `ReferenceResolutionStatus` | `present`, `absent` |
| `ReferenceSourceKind` | `bundle`, `model_bundle` |

## 5. `SessionSemanticSnapshot` 字段族

所有下列模型继承 `StrictContractModel`，拒绝额外字段、拒绝 NaN/Infinity、冻结字段赋值。所有集合使用 tuple；同一 namespace 内 ID 唯一，不强迫不同 namespace 共用一个全局 ID 空间。

### 5.1 几何、target 与 envelope

```text
SemanticVector
  coordinate_frame_id: StableId
  unit: UnitName
  values: tuple[FiniteFloat, ...]       # 精确 2D 或 3D

TaskTargetDefinition
  target_id: StableId
  position: SemanticVector             # 精确 3D
  arrival_axis: SemanticVector | None  # 若存在：精确 3D、非零、同 frame、unit=dimensionless

EnvelopeAxisLimit
  metric_id: StableId
  desired_abs_max: NonNegativeFiniteFloat
  adequate_abs_max: NonNegativeFiniteFloat
  unit: UnitName

EnvelopeDefinition
  envelope_id: StableId
  target_id: StableId
  axis_limits: tuple[EnvelopeAxisLimit, ...]
```

约束：

- `adequate_abs_max >= desired_abs_max`；同一 envelope 内 `metric_id` 唯一且至少一项；
- `EnvelopeDefinition.target_id` 必须解析到同 snapshot 的 target；
- arrival axis 由插件归一化，零向量在合同层拒绝；
- 本任务不定义任意 frame transform 或 unit conversion 公式。转换由后续 execution-plan/plugin 参数合同版本化；Task 3 只确保 frame/unit identity 明确且可精确比较。

### 5.2 phase、event 与 observation opportunity

```text
SemanticPhase
  phase_id: StableId
  phase_type: StableId
  start_t_ns: NonNegativeInt64
  end_t_ns: NonNegativeInt64
  include_session_terminal_point: StrictBool = false
  target_id: StableId | None
  envelope_id: StableId | None

SemanticEvent
  event_id: StableId
  event_type: StableId
  t_ns: NonNegativeInt64
  duration_ns: NonNegativeInt64 | None
  opportunity_end_t_ns: NonNegativeInt64 | None
  phase_id: StableId | None
  target_id: StableId | None
  envelope_id: StableId | None
  relevant_aoi_ids: tuple[StableId, ...]
  control_mapping_ids: tuple[StableId, ...]
```

约束：

- phase 与显式 opportunity 均使用 `[start,end)`，`end > start`；
- phase 按 `(start_t_ns,end_t_ns,phase_id)` canonical order 提交，不能重叠；相邻和 gap 均合法；
- phase、event、event duration 和 opportunity 必须位于 `[0,session_end_t_ns]`；`duration_ns` 若存在必须严格大于 0 且 `t_ns+duration_ns` 不溢出/越过 session，`opportunity_end_t_ns` 若存在必须严格大于 `t_ns`；
- `include_session_terminal_point=true` 只允许 canonical 最后一个 phase，且该 phase 的 `end_t_ns == session_end_t_ns`；它只声明 terminal sample ownership，不把普通 analysis span 改成闭区间；
- event 若声明 `phase_id`，其 `t_ns` 必须位于该 phase 的 `[start_t_ns,end_t_ns)`；唯一例外是 `t_ns=session_end_t_ns` 且该 phase 是显式 terminal-owner 的最后 phase；
- phase-scoped event duration 与 `opportunity_end_t_ns` 均不得越过该 phase end，非 phase-scoped event 不得越过 session end；terminal event 不能再声明正长度 duration/opportunity；
- event 的 phase/target/envelope/AOI/control 引用必须在同 snapshot 内解析；每个 tuple 内 ID 不得重复。

### 5.3 AOI taxonomy

```text
DynamicAoiSource
  stream_role: Literal["I"] = "I"
  table_role: StableId
  aligned_schema_id: StableId              # table-role-level aligned artifact schema
  coordinate_frame_id: StableId
  unit: UnitName
  frame_id_field: StableId
  aoi_id_field: StableId
  geometry_field_ids: tuple[StableId, ...]

AoiDefinition
  aoi_id: StableId
  taxonomy_id: StableId
  role: StableId
  geometry_kind: AoiGeometryKind
  priority: NonNegativeInt
  role_weight: UnitInterval
  off_task: StrictBool
  dynamic_source: DynamicAoiSource | None
  vertices: tuple[SemanticVector, ...]
```

约束：

- `dynamic_2d`/`dynamic_3d` 必须提供 `dynamic_source` 且 `vertices` 为空；source 精确锁定 I stream、table role、aligned schema、coordinate frame/unit、frame/AOI key fields 与非空唯一的 ordered geometry fields，Task 4 request validation 必须证明这些字段存在且合同一致；
- `polygon_2d`、`box_3d` 与 `catch_all` 禁止 `dynamic_source`；
- `polygon_2d` 至少三个 2D vertices，且 frame/unit 完全一致；
- `box_3d` 精确两个 3D corner vectors，且 frame/unit 完全一致；
- polygon 必须具有非零面积；box 的三个轴向 extent 都必须严格为正；退化几何是合同错误，不是采集质量判断；
- `catch_all` 不携带 vertices，`role=other_scene`、`off_task=true`、`role_weight=0.0`；
- 每个非空 taxonomy 精确一个 `catch_all`；这保证 blink、tracking loss 或不可投影 gaze 仍进入 `other_scene` denominator，而不是被质量过滤。

### 5.4 control mapping、baseline 与 applicability

```text
ControlEffectMapping
  control_mapping_id: StableId
  state_axis_id: StableId
  control_channel_id: StableId
  correct_sign: Literal[-1, 1]          # bool 非法
  state_unit: UnitName
  control_unit: UnitName
  lower: FiniteFloat
  trim: FiniteFloat
  upper: FiniteFloat

BaselineChannelBinding
  modality: BaselineModality
  channel_ids: tuple[StableId, ...]

BaselineDefinition
  baseline_id: StableId                 # 精确对应 M3 annotation interval_id
  start_t_ns: NonNegativeInt64
  end_t_ns: NonNegativeInt64
  channel_bindings: tuple[BaselineChannelBinding, ...]
  condition_id: StableId | None
  annotation_valid: StrictBool | None
  annotation_exclusion_reason: AuditText | None

AnchorApplicability
  anchor_id: StableId
  status: SemanticApplicabilityStatus
  phase_ids: tuple[StableId, ...]
  event_ids: tuple[StableId, ...]
  aoi_ids: tuple[StableId, ...]
  control_mapping_ids: tuple[StableId, ...]
  baseline_ids: tuple[StableId, ...]
  target_ids: tuple[StableId, ...]
  envelope_ids: tuple[StableId, ...]
  reason: StableId | None
```

约束：

- control calibration 必须满足 `lower < trim < upper`；
- baseline 使用 `[start_t_ns,end_t_ns)`、`end > start`，必须位于 session 内；ECG 与 EEG baseline 可以互相重叠，也可以与 phase 重叠；
- baseline 的 `channel_bindings` 非空、modality 唯一；每个 binding 的 `channel_ids` 非空、唯一并保留 channel-map 顺序；
- `annotation_valid=false` 必须有 `annotation_exclusion_reason`；这些字段与 M3 baseline 原样一致并只进入 audit/provenance，M4 不把它们变成 coverage/quality scorer 或按此删除有限输入；
- `applicable` 要求 `reason=None`；引用集合允许为空，因为某些 anchor 只依赖 stream/plan；
- `not_applicable` 要求受控 `reason`，且全部语义引用 tuple 为空；
- applicability 中的每个非空引用必须精确解析到相应 namespace；同一 anchor 只能出现一次。

唯一 ownership：AOI `role_weight/off_task`、control calibration 与 task envelope limits 是 session/task 语义，只存在于 semantic snapshot；D/A/U evidence thresholds、DSP/grid 参数和 scorer policy 只存在于 execution plan/parameter snapshot。两边不得复制同名参数形成双重权威。

### 5.5 root snapshot

```text
SessionSemanticSnapshot
  contract_id: Literal["session-semantic-snapshot"] = "session-semantic-snapshot"
  contract_version: Literal["0.1.0"] = "0.1.0"
  session_id: StableId
  task_profile_id: StableId
  scenario_id: StableId
  source_snapshot_fingerprint: Sha256Digest
  synchronization_fingerprint: Sha256Digest
  annotation_revision: StableId
  synthetic_semantics_unvalidated: StrictBool
  session_start_t_ns: Literal[0] = 0
  session_end_t_ns: Annotated[int, Field(strict=True, gt=0, le=MAX_SESSION_END_NS_V0_1)]
  phases: tuple[SemanticPhase, ...]
  events: tuple[SemanticEvent, ...]
  aois: tuple[AoiDefinition, ...]
  control_mappings: tuple[ControlEffectMapping, ...]
  baselines: tuple[BaselineDefinition, ...]
  targets: tuple[TaskTargetDefinition, ...]
  envelopes: tuple[EnvelopeDefinition, ...]
  applicability: tuple[AnchorApplicability, ...]
  semantic_snapshot_fingerprint: Sha256Digest
```

Task 3 只验证 digest 格式并原样保存；RFC 8785 规范化与 fingerprint 计算属于 replacement Task 8，精确 safe-integer domain、typed framing、logical-table/reference payload 与 self-field 规则以 [Task 8 Canonical Fingerprint and Runtime Identity Amendment](2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) 为准。

### 5.6 semantic producer 与 Task 4 闭合校验

`SessionSemanticSnapshot` 不是任意 UI JSON。M5 编译锁定 task/model/config 语义，M6 在 model/session lock 与 Run Preflight 中把它和同一个 `AlignedSession.annotations` 绑定，补充并冻结 target/envelope/AOI/control/channel/applicability snapshot；Task 32 只提供同规则的 test-only assembler。M4 evaluator 不构造 snapshot，也不从 pilot performance 反推这些语义。

Task 4 定义并由 `AnchorExecutionPlan.input_table_contracts` 保存 M5 从锁定 core-stream profile 编译出的 `ResolvedInputTableContract`；它至少冻结 `(modality,table_role)`、stream-level 与 table-role-level aligned schema、coordinate frame 以及物理列顺序中的 field name/dtype/unit/nullability，不从 live 数值反推。其 `dtype_id` 使用与 reference field 相同的 v0.1 primitive allowlist 和固定 Polars mapping。`AnchorExecutionPlan.entries` 只允许 `lifecycle=active`，plan contracts 必须精确覆盖全部 entries/preprocessing recipes 的 required-stream union 中每个 core modality 的完整 profile table inventory。Task 4 request validation 必须在 evaluator、plugin、provider 和 sink 被访问前证明：

- session/source/synchronization/window identity 与 `AlignedSession` 完全相同；
- `set(AlignedSession.streams)` 精确等于 `SynchronizationReport.stream_results` 中 `synchronization_status=aligned` 的 modality 集合；report=aligned/view 缺失或 report=non-aligned/view 注入均为 `request_session_mismatch`。非 blocked M3 的 optional `not_attempted/unavailable/invalid/unsupported/not_applicable` 均合法表示无 live view；若 plan 需要该 modality，受影响 anchor 后续以原状态 reason 产生 `missing_input`。required-for-import 非 aligned 已由 M3 blocked，不可进入 request；
- `annotation_revision` 与 `synthetic_semantics_unvalidated` 原样等于 M3 `AlignedAnnotations`；
- phase ID/start/end、event ID/type/time/duration，以及 baseline ID/start/end/condition/valid/exclusion 的 annotation identity 与 M3 对齐；`phase_type` 与 terminal ownership 由锁定 task profile 在不改变时间事实的前提下补充；snapshot 还可以补充 M3 没有的 target/AOI/control/channel 绑定，但不能改写 M3 时间或 audit 事实；
- 每个 `BaselineDefinition.baseline_id` 解析到同 ID 的 M3 interval；
- 对每个实际 aligned 的 required core stream，live table-role inventory 与该 modality 的 plan contracts 精确相等；`AlignedStreamView.aligned_schema_id` 等于 contract 的 stream-level schema，`SynchronizationReport.stream_results[modality].artifacts[table_role].aligned_schema_id` 等于 table-role-level schema，live field name/dtype 必须一致，contract 中 non-nullable 的列必须没有 null（nullable 列可以有或没有 null）。上一条允许的 optional non-aligned stream 没有 live exact-match，受影响 anchor 后续产生带原状态 reason 的 `missing_input`；
- dynamic AOI source 无条件精确命中一个 `(I,table_role)` plan input-table contract；其 `aligned_schema_id` 是 table-role-level schema 并与 contract 相等，source frame 等于 contract coordinate frame，frame/AOI key fields 存在，所有 ordered geometry fields 的 contract unit 等于 source unit。只有 I 实际 aligned 时才进一步要求 current I view/report/table 满足上一条 live exact match；合法 optional non-aligned I 不阻断 request。不从列名或数值猜测，也不进行数据质量判断；core stream 数值有限性与值域由 M1–M3 结构合同负责，M4 request gate 不新增 finite/range 扫描；
- applicability anchor IDs 精确等于 `AnchorExecutionPlan.entries` 的 anchor ID 集合；该 tuple 是编译后的 active catalog inventory，catalog fingerprint/plan validation 再证明其 catalog revision，因此 request gate 不依赖另一个未绑定的 catalog 对象。额外、缺失或跨 revision 注入均拒绝；
- resolved-reference descriptor ID 集合必须精确等于所有 `AnchorExecutionEntry.required_reference_ids` 与 `ResolvedPreprocessingRecipe.required_reference_ids` 的并集；execution entries 已由合同保证全为 active。missing/extra descriptor 均阻止 request，只有集合中显式的合法 `absent` descriptor 才能让下游按规则产生 `not_computable`；
- 对每个 `source_kind=bundle` descriptor，`present` 时 `SynchronizationReport.task_reference_result` 必须存在，且其 `reference_id`、`source=bundle`、`synchronization_status=aligned`、clock ID/method/scale/offset/drift、source/aligned schema 与 source checksums 必须逐项等于 descriptor 与已绑定 view；`mapping_policy_id` 必须等于 `SynchronizationReport.policy.policy_id`。candidate 的一致性已由 Task 3 binder 证明，Task 4 不再接收它。`absent` 时 M3 report 可以没有 task-reference record，或只含同一 reference ID 的合法非 aligned bundle record；若 M3 已有任意 aligned bundle view，或 report 指向不同 reference/source，则该 absent snapshot 不得覆盖它；
- 对每个 `source_kind=model_bundle` descriptor，M3 `task_reference_result` 必须先证明同一 `reference_id`、`source=model_bundle` 且 status 精确为 `deferred_model_bundle_resolution`；随后才接受由 M6 resource/session lock 产生、经 Task 3 binder 验证并表示为 descriptor + bound view 的 ModelBundle mapping contract。若 M3 没有该 deferred record、报告了 bundle source 或 reference ID 不同，则在 request 构造前拒绝；
- 上述 M3 report 比对发生在读取 evaluator/plugin/provider/sink 前；Task 3 binder 不新增 `SynchronizationReport` 参数，也不把 descriptor 与 candidate 的相互一致误当成 D-019 provenance 证明。

语义 fingerprint 不一致或上述闭合校验失败会阻止 `AnchorEvaluationRequest` 构造；aligned stream/dynamic AOI/input-table 或 applicability inventory 错配使用 `request_semantic_identity_mismatch`。校验优先级固定为 session identity → semantic/annotation/input-table/applicability relation → reference inventory/provenance → canonical fingerprints；因此同一次篡改既破坏 semantic relation 又留下 stale fingerprint 时稳定返回 semantic code，只有前述关系均成立但 canonical digest 不一致时才返回 `request_fingerprint_mismatch`。合法 optional non-aligned stream 不属于上述 mismatch。它不是某个 anchor 的 `not_computable`，也不生成 M4 evaluation report。

Task 4 为该 request-construction boundary 定义 `AnchorRequestValidationError(ValueError)`；v0.1 stable code allowlist 为 `request_session_mismatch`、`request_semantic_identity_mismatch`、`request_reference_inventory_mismatch`、`request_reference_provenance_mismatch`、`request_fingerprint_mismatch`。错误 details 只记录稳定字段/reason ID，不嵌入绝对路径、DataFrame repr 或其他可变对象表示。

错误分为两个连续且不重叠的阶段：Task 3 binder 接收 candidate，并在失败时只抛 §8.4 的 `ReferenceBindingError`，此时 `ResolvedReferenceSet` 与 `AnchorEvaluationRequest` 都尚未产生；binder 成功后，Task 4 request constructor 只接收已经绑定的 `ResolvedReferenceSet`，不再接收或重新检测 candidate，随后对 session/semantic/plan/M3 provenance/canonical fingerprint 闭合失败抛 `AnchorRequestValidationError`。M6 可以在更外层把两者都记录为 Run Preflight blocked，但不得改写 stable code 或伪造 M4 report。

## 6. 可序列化 reference 合同

### 6.1 table contract

```text
ReferenceSessionIdentity
  session_id: StableId
  source_snapshot_fingerprint: Sha256Digest
  synchronization_fingerprint: Sha256Digest
  session_start_t_ns: Literal[0] = 0
  session_end_t_ns: Annotated[int, Field(strict=True, gt=0, le=MAX_SESSION_END_NS_V0_1)]

ReferenceAlignmentContract
  mapping_method: StableId
  mapping_policy_id: StableId
  source_clock_id: StableId
  target_time_domain: Literal["session_time_ns"] = "session_time_ns"
  scale: PositiveFiniteFloat
  offset_ns: Int64
  declared_drift_ppm: FiniteFloat
  rounding_mode: Literal["decimal_round_half_even"] = "decimal_round_half_even"
  in_session_policy: Literal["m3_closed_source_row_mask_v0.1"] = "m3_closed_source_row_mask_v0.1"

ReferenceFieldContract
  field_name: StableId
  dtype_id: StableId                    # canonical Polars dtype ID，例如 i64/f32/utf8/bool
  unit: UnitName
  nullable: StrictBool

ReferenceTableContract
  table_role: StableId
  coordinate_frame_id: StableId
  session_time_field: Literal["t_ns"] = "t_ns"
  in_session_field: Literal["in_session"] = "in_session"
  stable_row_id_field: StableId
  fields: tuple[ReferenceFieldContract, ...]
  canonical_order_keys: tuple[StableId, ...]
  table_contract_fingerprint: Sha256Digest

ReferenceResourceChecksum
  path: ResourceRelativePath
  checksum: Sha256Digest
```

约束：

- bundle alignment contract 精确复制 M3 reference clock mapping 的 method/clock/scale/offset/drift，并使用 M3 versioned policy ID；ModelBundle contract 由 M6 resolver 以相同字段冻结实际 mapping 与 versioned policy ID，不能只写 `identity` 标签；
- `ReferenceAlignmentContract.source_clock_id` 必须等于 runtime view `clock_id`；scale 严格为有限正数，offset 为 strict Int64，rounding/mask policy 不可由调用方另造；
- Task 3 合同 validator 必须与 M3/D-018 一样先用 `Decimal(str(value))` 表示输入，再验证 `abs(declared_drift_ppm - (scale - 1) * 1_000_000) <= 0.000001 ppm`；`rounding_mode` 和 `in_session_policy` 必须保持上述 Literal 值。该 validator 只能排除内部不一致，不能证明这些值确实来自 M3，来源证明由 §5.6 的 request gate 完成；
- `fields` 非空、field name 唯一，并按物理 DataFrame column order 冻结；
- fields 必须精确包含 non-nullable `t_ns/i64/ns`、`in_session/bool/bool`，以及 non-nullable integer `stable_row_id_field`；`canonical_order_keys` 精确为 `(t_ns,stable_row_id_field)`；
- `stable_row_id_field` 必须与 `t_ns`、`in_session` 是三个不同 field name，不能用时间列或 mask 列冒充稳定 row identity；
- v0.1 dtype allowlist 精确为 `bool/i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/utf8`，并使用固定 Polars primitive mapping；未知或 nested dtype 不按字符串相似度猜测；
- non-nullable field 在 runtime table 中出现 null 时拒绝；nullable field 可以恰好没有 null；
- runtime `stable_row_id_field` 全表唯一；row 的 order-key tuple 必须组合唯一并已按升序排列；binder 只验证，不静默重排 source rows；
- 所有 f32/f64 非 null 值必须有限；NaN/Infinity 是上游结构合同违约，不是表现质量门；
- runtime `in_session` 必须精确等于 `0 <= t_ns <= session_end_t_ns`，与 M3 v0.1 closed source-row mask 一致；anchor analysis span 仍使用半开区间；
- `table_contract_fingerprint` 在 Task 3 只做格式验证/传播。

### 6.2 descriptor 与 snapshot

```text
ResolvedReferenceDescriptor
  reference_id: StableId
  resolution_status: ReferenceResolutionStatus
  source_kind: ReferenceSourceKind
  runtime_view_role: Literal["task_reference"] = "task_reference"
  source_schema_id: StableId
  aligned_schema_id: StableId
  clock_id: StableId
  alignment_contract: ReferenceAlignmentContract
  table_contract: ReferenceTableContract
  resource_checksums: tuple[ReferenceResourceChecksum, ...]
  resource_fingerprint: Sha256Digest | None
  aligned_content_fingerprint: Sha256Digest | None
  alignment_fingerprint: Sha256Digest | None
  absence_reason: StableId | None

ResolvedReferenceSetSnapshot
  contract_id: Literal["resolved-reference-set"] = "resolved-reference-set"
  contract_version: Literal["0.1.0"] = "0.1.0"
  session_identity: ReferenceSessionIdentity
  descriptors: tuple[ResolvedReferenceDescriptor, ...]
  reference_set_fingerprint: Sha256Digest
```

字段矩阵精确为：

| status | resource checksums | resource/content/alignment fingerprints | absence reason |
|---|---|---|---|
| `present` | 至少一项、path 唯一 | 三项全部必填 | 必须为 null |
| `absent` | 必须为空 | 三项全部为 null | 必填 |

`absent` 仍保留 source kind、runtime role、schema/clock/table/frame/unit 期望合同，所以“没有解析到 reference”和“提交了损坏的 reference 合同”不会混为一类。Snapshot 内 `reference_id` 唯一，且不包含 DataFrame、`AlignedStreamView` 或其他 runtime 对象。

`ReferenceResourceChecksum.path` 在 `bundle` 时相对于已验证 Session Bundle root，在 `model_bundle` 时相对于已验证、不可变 ModelBundle resource root。path uniqueness 同时按原字符串和 Windows `casefold()` 检查。`resource_checksums` 按 path 字典序提交，`descriptors` 按 `reference_id` 字典序提交。

v0.1 runtime view namespace 只允许 `task_reference`，不能声明 X/U/I/G/EEG/ECG/pilot_camera。一个 snapshot 总计最多一个 descriptor，来源只能在 `bundle` 与 `model_bundle` 中二选一，因为 M3 只有一个 `task_reference_result` provenance record 且 `AlignedSession` 只有一个 dedicated bundle `task_reference` 槽位；多个 ModelBundle descriptor 或 bundle/ModelBundle 混合 inventory 在 v0.1 均拒绝。ModelBundle manifest 继续不声明 SessionManifest `stream_id`，这里的 `runtime_view_role` 只是 M4 内部容器角色，不改变 D-014。未来若确需多 reference，必须另行版本化 M3 provenance 和本合同，不能只放宽 tuple cardinality。

### 6.3 canonical collection order

为避免同一语义只因 tuple 排列不同而得到不同 fingerprint，root snapshot 的非几何集合顺序冻结为：

- phases：`(start_t_ns,end_t_ns,phase_id)`；
- events：`(t_ns,event_id)`；
- AOI、control mapping、baseline、target、envelope：各自 ID 字典序；
- applicability：`anchor_id` 字典序；
- envelope limits：`metric_id` 字典序；
- baseline channel bindings：`modality` 字典序；
- event/applicability 内作为集合使用的 ID tuples：ID 字典序；
- polygon vertices、dynamic geometry fields、reference fields、canonical order keys、baseline channel IDs 保留声明顺序，因为这些顺序具有几何、物理 schema、tie-break 或 channel-map 语义。

Task 3 validators 拒绝非 canonical collection order，而不是静默重排调用方输入。

### 6.4 fingerprint ownership 与 Task 8 callable

Task 3 只校验/传播 digest；Task 8 必须在现有 `typed_json_sha256` 与 `logical_table_sha256` 之上增加以下固定 callable 和 tamper tests：

```text
session_semantic_snapshot_fingerprint(snapshot) -> Sha256Digest
reference_table_contract_fingerprint(contract) -> Sha256Digest
reference_resource_fingerprint(descriptor) -> Sha256Digest
aligned_reference_content_fingerprint(
  table,
  aligned_schema_id,
  contract,
) -> Sha256Digest
reference_alignment_fingerprint(
  descriptor: ResolvedReferenceDescriptor,
  session_identity: ReferenceSessionIdentity,
) -> Sha256Digest
resolved_reference_set_fingerprint(snapshot) -> Sha256Digest
```

typed identity/version 与 payload 精确为：

| fingerprint | type ID / version | canonical payload |
|---|---|---|
| semantic snapshot | `session-semantic-snapshot` / `0.1.0` | 完整 strict model dump，排除 `semantic_snapshot_fingerprint` 自字段 |
| table contract | `reference-table-contract` / `0.1.0` | 完整 table contract，排除 `table_contract_fingerprint` 自字段 |
| resource | `reference-resource` / `0.1.0` | `[reference_id,source_kind,runtime_view_role,source_schema_id,table_contract_fingerprint,[[path,checksum],...]]` |
| aligned content | 现有 logical table typed framing | callable 的 `aligned_schema_id` 参数、完整 ordered field descriptor、全部 rows、canonical order keys；不含物理路径/压缩/writer metadata |
| alignment | `reference-alignment` / `0.1.0` | 完整 `ReferenceSessionIdentity`、reference/source/runtime role、完整 `ReferenceAlignmentContract`、clock、source/aligned schema、table/resource/content fingerprints |
| resolved set | `resolved-reference-set` / `0.1.0` | 完整 snapshot dump，排除 `reference_set_fingerprint` 自字段 |

Task 8 tests 必须证明任一 resource checksum、frame/unit/table field、row value/order、session/window、clock/schema、mapping method/policy/scale/offset/drift/rounding/mask 变化会改变相应 fingerprint；仅改变 self-reported digest 必须被拒绝而不是信任。Task 13 request validation 与 Task 35 packaged loader 在 evaluator 前重算并比较这些 digest。由此 Task 3 完成只能证明合同/binder 行为，直到 Task 8/13/35 通过后才证明 canonical identity 与 public smoke 入口。

## 7. Runtime candidate 与绑定结果

`src/pilot_assessment/anchors/models.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class ReferenceViewCandidate:
    reference_id: StableId
    source_kind: ReferenceSourceKind
    session_identity: ReferenceSessionIdentity
    aligned_view: AlignedStreamView
    alignment_contract: ReferenceAlignmentContract
    table_contract: ReferenceTableContract
    resource_fingerprint: Sha256Digest
    aligned_content_fingerprint: Sha256Digest
    alignment_fingerprint: Sha256Digest


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    descriptor: ResolvedReferenceDescriptor
    aligned_view: AlignedStreamView | None


@dataclass(frozen=True, slots=True)
class ResolvedReferenceSet:
    session_identity: ReferenceSessionIdentity
    entries: Mapping[str, ResolvedReference]
    reference_set_fingerprint: Sha256Digest
```

`ReferenceViewCandidate` 与 `ResolvedReferenceSet` 的 runtime integer/digest/ID 同样必须在 `__post_init__` 严格验证。`ResolvedReferenceSet.entries` 复制为 `MappingProxyType`；key 必须等于 value descriptor 的 `reference_id`。`ResolvedReference` 强制 `present <-> aligned_view is not None`、`absent <-> aligned_view is None`。成功绑定使用 snapshot 中同一个 descriptor 对象和 candidate 中同一个 `AlignedStreamView` 对象，不复制 DataFrame。

## 8. 修订后的 binder API

`src/pilot_assessment/anchors/reference_resolution.py` 的唯一 Task 3 public binder 签名改为：

```python
def bind_resolved_reference_snapshot(
    snapshot: ResolvedReferenceSetSnapshot,
    aligned_session: AlignedSession,
    candidates: Mapping[str, ReferenceViewCandidate],
) -> ResolvedReferenceSet:
    """Bind only exact, independently described reference candidates."""
```

### 8.1 session-level gate

在读取 candidate table 前必须确认：

- snapshot `session_identity` 的 session/source/synchronization/window 分别等于 aligned session identity/window；
- candidate mapping key 集合精确等于所有 `present` descriptor ID：不允许 missing、extra，也不允许为 `absent` descriptor 提供 candidate；
- mapping key 等于 `candidate.reference_id`；
- 每个 candidate 的完整 `session_identity` 分别精确等于 snapshot 与 aligned session，禁止跨 session、跨 mapping replay。

### 8.2 per-reference exact match

每个 present descriptor 必须逐项匹配：

- `reference_id`、`source_kind`、完整 `alignment_contract`、`resource_fingerprint`、`aligned_content_fingerprint`、`alignment_fingerprint`；
- view `modality == descriptor.runtime_view_role == "task_reference"`；
- view source schema、aligned schema、clock；view clock 还必须等于 alignment contract `source_clock_id`；
- view `source_checksums` 与 descriptor resource path/digest 集合精确相等，不能缺少、多出或 case-fold alias path；
- v0.1 view 的 table inventory 必须精确为 descriptor 的单一 `table_role`，不允许 missing 或 extra table role；
- v0.1 reference view 的 `json_artifacts` 与 `file_artifacts` 必须为空；插件不能通过未声明 artifact side channel 读取 descriptor/fingerprint 之外的内容；
- descriptor 与 candidate 的完整 `ReferenceTableContract` 对象值相等；
- runtime DataFrame column order、allowlisted dtype、finite/null、unique sorted order-key、`t_ns` 和 `in_session` mask 满足该 table contract 与当前 session window。

frame/unit 的判断来自 descriptor 与 candidate 两份独立 table contract 的精确相等，不从 column name、数值范围或 DataFrame shape 推断。

### 8.3 source-kind ownership

- `source_kind=bundle`：在 §6.2 的“全部来源总计最多一个 descriptor”约束下，candidate view 必须与 `aligned_session.task_reference` 为同一对象；M3 view 不存在时 present 绑定失败。若 descriptor 明确为 absent 但该 dedicated M3 view 实际存在，也视为 snapshot mismatch；snapshot 完全不声明 descriptor 时允许忽略 session 中未被当前 model 使用的 reference。
- `source_kind=model_bundle`：M3 仍只报告 deferred，不创建该 view。M5 验证不可变 ModelBundle resource；M6 在锁定 model/session 的 Run Preflight 边界执行 session-time mapping并构造 source-neutral-shaped `AlignedStreamView` 容器。该容器可以不在 `AlignedSession` 内，但不得与 `aligned_session.task_reference`、任一 core stream view 或其中任一 DataFrame 共享对象身份。
- 无论 source kind，实际 X 或其他 core stream 都不能因为列形状相同而满足 commanded reference。

Task 3 只定义 candidate port 和 exact binder。Task 32 的 compact scenarios 直接从同一个 test-only in-memory `AlignedSession`/reference view 构造 candidate，不声称经过 M1–M3；Task 32 的 smoke assembler 则只从同一次真实 M1–M3 输出构造 bundle candidate，Task 34 用后者验证 public workflow。Task 35 的 packaged verification loader 实现唯一当前 M4 production-like bundle producer，并在调用 binder 前重算冻结 fingerprint。通用 bundle 与 ModelBundle producer 属于后续 M5/M6 compiler、resource resolver 和 Run Preflight，不属于 M4 evaluator。所有 producer 都不接受 UI 直接提交的 frame/unit/resource/session identity。

### 8.4 输出与错误语义

`ReferenceBindingError.code` 的 v0.1 allowlist 精确为：`reference_session_mismatch`、`reference_candidate_inventory_mismatch`、`reference_source_ownership_mismatch`、`reference_identity_mismatch`、`reference_table_contract_mismatch`。

- `present` 成功时输出原 descriptor + 原 view；
- `absent` 无条件输出原 descriptor + `aligned_view=None`；
- output set 原样传播 snapshot 的 session/source/synchronization/window identity；entries 使用 snapshot descriptor canonical order 构造并冻结；
- `reference_set_fingerprint` 原样传播，不在 Task 3 重算；
- 任一 mismatch 抛出带稳定 code 的 `ReferenceBindingError(ValueError)`；binding 发生在有效 `AnchorEvaluationRequest` 之前，因此错误会阻止 request 构造且 evaluator/plugin/provider/sink 调用数均为零，不生成 M4 evaluation report。未来 M6 可以把它记录为 Run Preflight blocked，但不能伪装成一次 M4 evaluation；
- structurally valid `absent` 不报错，后续需要它的 anchor 产生 `not_computable`；
- mismatch 永不自动修复、猜测、改写 descriptor 或降级为 absent。

## 9. 轻量 TDD 验证矩阵

Task 3 只使用纯内存 DTO、一个两行 Polars reference table 和手工构造的最小 `AlignedSession`。不生成 Session Bundle、CSV、Parquet、PNG，不运行 18 个 anchor。

`tests/contracts/test_anchor_execution.py`：

1. semantic snapshot 精确 public surface、JSON round-trip、frozen、extra-forbid；
2. `[start,end)`、相邻/gap、event-phase containment、terminal-point、M3 session bound；
3. 每个 namespace 的 duplicate ID 与 dangling reference；
4. finite vector、2D/3D、非零 arrival axis、unit/frame、dynamic AOI source 与 static degenerate geometry；
5. control calibration、baseline、applicability 状态矩阵；
6. reference descriptor present/absent 字段矩阵、唯一 ID、总计零或一个 descriptor、拒绝多个 ModelBundle 或 bundle/ModelBundle 混合 inventory，并证明 snapshot 无 runtime 对象。

`tests/anchors/test_reference_resolution.py`：

7. present 保持 view/DataFrame identity，absent 保留 None，output session identity 与 mapping 不可变；
8. present 必须有唯一 exact candidate，拒绝 missing/extra/absent candidate、跨 session/mapping replay、非法 source-kind ownership 和 shape-based guessing；alignment contract validator 还须拒绝按 M3 Decimal 口径计算后 scale/drift 超过 `0.000001 ppm` 的不一致；
9. 分别突变 runtime role/table/source schema/aligned schema/clock/frame/unit/resource/content/alignment contract/fingerprint，逐项拒绝；
10. checksum path/digest/case-fold alias、extra JSON/file artifact、column order、dtype、null/NaN/Infinity、order-key duplicate/unsorted、`t_ns/in_session` mask 不一致时拒绝。

RED 必须首先因为 Task 3 合同/模块尚不存在或行为尚未实现而失败；随后写最小 production code 得到 GREEN。Task 3 不测试 schema export、JCS fingerprint 计算、catalog/plan/plugin、真实 bundle 或 M1→M4 E2E。

Task 4 在其既有 request-contract focused tests 中另加最小 `SynchronizationReport` provenance cases：bundle reference ID/source/status/clock method-scale-offset-drift/schema/checksum/policy 任一错配均在 request 前拒绝；bundle absent 可接受无 record 或同 ID 的合法非 aligned record，但不能覆盖 aligned/different-source record；ModelBundle 只有在 M3 存在同 ID 的 `deferred_model_bundle_resolution` record 后才接受 M6 mapping。该组测试复用最小 DTO，不生成物理 bundle，也不运行 anchor。

## 10. 实施计划迁移

本文获批后，先完成文档迁移：

1. 在 `DECISIONS.md` 新增 D-028：M4 reference binding 使用 session-bound `ReferenceViewCandidate`；M3 对 ModelBundle 保持 deferred，M5/M6 可在 M3 外构造相同 immutable view container 并负责 resource/session lock；
2. 把本文状态改为已批准，并在 M4 主规格、`docs/product/README.md` 与 `11_IMPLEMENTATION_STATUS.md` 建立可发现链接和当前口径；M4 主规格 §6、§8.1、§8.3 必须明确 semantic/reference binding mismatch 发生在 request 前、无 M4 report，而 valid request 之后的 plan/registry/DAG/transaction failure 才产生 M4 `blocked` report；
3. 在 replacement plan sources of truth 中加入本文并记录批准日期。

随后修订 replacement plan 的受影响文字，所有未实施 task 仍保持 pending：

1. 用三参数 binder 签名取代原两参数签名；
2. 在 Task 3 files 中保留原四个 production files 与两个 test files，不扩大代码提交边界；
3. 把 Step 1 明确为本文件 §9 的轻量 RED；
4. 把 Step 2 明确为本文 §§4–8 的最小实现；
5. Task 4 增加 plan-level `ResolvedInputFieldContract`/`ResolvedInputTableContract`、semantic/reference/output session identity 的 request-construction gate，并逐字段绑定所有 aligned required core views/report artifacts/plan input contracts、dynamic AOI/plan contract 与条件 aligned 的 live I view、完整 active applicability inventory 与 `SynchronizationReport.task_reference_result`；合法 optional `not_attempted/unavailable/invalid/unsupported/not_applicable` core stream 下沉为带原状态 reason 的 per-anchor `missing_input`。bundle 校验同 reference 的 status/clock/schema/checksum/policy provenance，ModelBundle 校验同 reference 的 D-019 deferred record 后才接受 M6 mapping；
6. Task 8 增加 §6.4 callable、canonical payload 和 tamper tests；Task 13 在 evaluator 前重算验证；
7. Task 32 明确区分 compact in-memory candidate 与 smoke M1–M3 candidate，Task 34 只使用后者；Task 35 明确 packaged verification bundle producer，并把“returns the precompiled request unchanged”改为“plan/sidecar bytes 保持不变，但 runtime request 必须由 live M1–M3 + candidate + binder 新建”；通用 bundle/ModelBundle producer 继续归 M5/M6；
8. 更新 specification-to-task matrix，继续使用原 Task 3 code/test commit 边界，不提前执行 Task 4/8/13/32/34/35。

计划修订通过文档一致性检查后，才开始 Task 3 RED/GREEN。

## 11. 自审结论

| 检查项 | 结论 |
|---|---|
| 是否重新打开 M3 | 否；M3 runtime DTO/schema/golden 全部不变 |
| 是否支持 bundle 与 ModelBundle | 合同可表达两类来源；bundle Task 35 链路与未来 M5/M6 ModelBundle 链路通过各自 task 后才能声称已实现 |
| 是否可能按 shape 把 X 当 reference | binder 明确拒绝；完整来源防伪还依赖尚未实现的受信 producer/preflight，不在 Task 3 后过度声称 |
| frame/unit 是否仍由 descriptor 自证 | 否；期望配置与 candidate source contract 双边精确匹配，来源真实性由受信 producer 负责 |
| absent 是否与损坏混淆 | 否；合法 absent 是显式状态，present mismatch 是 binding error |
| 是否序列化 Polars | 否；Polars 只存在于 frozen runtime dataclass |
| 是否提前实现 anchor/plugin/fingerprint | 否；只冻结 Task 8 fingerprint callable/payload，不在 Task 3 实现 |
| 测试是否轻量 | 是；两个文件、约 10 个测试函数、单个两行内存表 |
| 是否引入数据质量过滤 | 否；只判断合同身份，不判断表现或采集数值好坏 |

剩余边界是刻意保留的：Task 3 定义 candidate port 和 binder，但不实现上游 candidate producer 或 canonical fingerprint。Task 35 完成前不能声称 M4 packaged bundle reference 入口完成；未来 M5/M6 producer/preflight 完成前不能声称完整 ModelBundle 导入链路或来源防伪已经实现。
