# M4 Anchor Calculation and Evidence Availability Design

| 字段 | 当前值 |
|---|---|
| 设计基线 | v0.2 |
| 日期 | 2026-07-13 |
| 设计状态 | 完整书面规格及轻量工作流验证修订均已于 2026-07-13 获用户批准；修订在其取代范围内优先 |
| 实现状态 | 18/18 已设计，0/18 production plugins 已实现；原 M4 实施计划已被轻量修订取代；replacement Task 0–1 已分别由 `bc544bf`、`f56365c` 完成，Task 2 尚未开始；M4 尚未 engineering verified |
| 上游 | M1 Session integrity + M2 Ingestion readiness + M3 native-rate synchronization |
| 下游 | M5 ModelBundle/BN/CPT/inference；M6 formal run/persistence |
| 正式运行授权 | `formal_run_authorized=false` |

## 1. 目标

M4 把同一 M3 snapshot 的 native-rate aligned views、任务语义、reference 和冻结的 anchor execution plan 转换为可审计的 anchor evidence。M4 必须：

1. 以 catalog-driven engine 执行任意数量的版本化 AnchorPlugin；
2. 为 `reference-model-v0.1` 实现 O1–O13、H1–H5 共 18 个 anchor；
3. 为每个 anchor 建立自己的 analysis grid、window、插值、聚合和 scorer；
4. 保存 phase/event/window 明细、内容寻址 artifact 与完整 provenance；
5. 把差表现保留为 `computed + Unacceptable`，不得因数值差而过滤 evidence；
6. 对缺输入、不适用、缺配置、依赖失败和软件异常使用互斥的结构化状态；
7. 对相同 snapshot、plan、插件和参数产生相同结果与 fingerprint；
8. 生成 M5 可以直接消费的单一 session-aggregate D/A/U likelihood；
9. 保持原始 Session Bundle 和 M3 aligned views 不变；
10. 始终保持 `formal_run_authorized=false`。

M4 证明计算软件按本规格运行，不证明算法、阈值、生理解释或能力结论已经通过科学验证、航空认证或医学验证。

### 1.1 Captured format-sample boundary

当前 2,902-row simulator CSV 只用于说明采集接口可能出现的 header、dtype、row、rate 和 source-time 形态。它不是标准轨迹、commanded path、任务 ground truth 或能力标签。M4 不从该轨迹推断任务标准，也不把复制 X 得到的 reference 解释成零 tracking error。

M4 按已接受的 [轻量工作流验证修订](2026-07-13-m4-lightweight-workflow-validation-amendment.md) 建立分层软件验证：18 个 anchor 分别使用定向微型输入，all-Desired/all-Unacceptable/mixed 使用紧凑 aligned raw tables，软件状态使用精确 fault hooks，只有一个 10 秒全模态 physical bundle 贯通 M1→M4。所有 synthetic fixtures 仍必须标记 `scientific_validation_status=not_supported`；90 秒 full-rate bundle 只可作为未来独立性能测试，不是 M4 完成门。

## 2. 明确不进入 M4 的内容

- 不训练黑箱模型；
- 不计算 BN posterior、sub-skill/competency posterior 或 weak-skill diagnosis；
- 不计算依赖 graph relation weights 的 sub-skill/competency/overall coverage；
- 不编辑、发布或持久化 ModelBundle draft/revision；
- 不创建 `AssessmentRun` 或 `RunPreflightReport`；
- 不负责生产 artifact 生命周期、正式导出或 Windows sidecar；
- 不判断原始数据“质量够不够好”；
- 不按轨迹偏差、控制强度、HR/EEG 极值、未响应、未注视或未稳定悬停省略 evidence；
- 不允许前端执行任意 Python；
- 不把 pilot_camera 强行绑定到当前 18 个 anchor。

## 3. 已采用方案

采用“合同优先 + typed dependency DAG + 领域纵向批次”。

~~~text
M4-A 语义、合同与 catalog
  -> M4-B 执行内核、grid/window、artifact、fingerprint
  -> M4-C O1-O7
  -> M4-D O8-O12
  -> M4-E H1-H3
  -> M4-F H4/H5/O13
  -> M4-G 全链 E2E 与 handoff
~~~

未采用：

- 一次性实现 18 个插件后再集成：合同和跨模态问题发现过晚；
- 按 anchor 平铺、各自实现 temporal/scoring：会复制 movement、fixation、window 和状态语义；
- 把 ModelBundle/graph/CPT compiler 提前纳入 M4：会混淆 M4 与 M5。

## 4. 核心不变量

### 4.1 引擎可扩展，reference profile 不可原地篡改

M4 engine 不能写死 18 个 ID；`AnchorExecutionPlan` 的 active catalog cardinality 是可变的。只有 `reference-model-v0.1` 固定为 O1–O13、H1–H5 共 18 个。

- 修改阈值、窗口或滤波参数：创建新 parameter snapshot/execution-plan revision；
- 修改算法：发布新的 `(plugin_id, plugin_version)`；
- 新增 anchor：创建稳定 anchor ID、definition、plugin、parameter schema 和 binding，并发布新 model profile/revision；
- 删除 anchor：在新 revision 中 retire/disable，不删除旧定义和旧插件；
- 历史结果 replay：加载当时的 catalog、plugin、parameter 和 dependency hashes。

`reference-model-v0.1` 的 required ID 或语义变化必须发布新的 major model profile，不能覆盖原 revision。

当前 `reference-model-v0.1` 尚未发布为不可变 ModelBundle；因此本书面规格是其首次 M4 计算语义冻结，而不是修改一个已发布模型。本规格获批并发布后，任何 anchor ID、公式族或状态语义变化都必须使用新的 major model profile。

### 4.2 差表现是证据，不是无效数据

M4 假定进入本层的 aligned data 已满足 M1–M3 的接口、结构和时间合同。对于存在且可解析的输入：

- 轨迹偏差大、控制剧烈、生理数值极端、未响应、未恢复、未注视、未形成稳定悬停都必须继续计算；
- 差表现通常输出 `computed + Unacceptable`；
- `computed + Unacceptable` 的 raw availability 为 1；
- coverage 表示证据是否存在，不表示表现好坏；
- reference M4 不生成 `invalid_quality`，也不使用 quality likelihood mixing。
- M4 不做 outlier clipping、winsorization、基于 artifact label 的删窗、医学正常范围过滤或按采样波动拒绝 observation；仅公式本身声明的有界变换可以 clamp。

接口文件或字段完全不存在、任务不适用、公式配置缺失、上游依赖缺失和软件错误仍必须诚实报告；系统不得为不存在的数据伪造数值。

### 4.3 实现状态不是计算状态

`plugin_unavailable`、`not_implemented` 和 `not_attempted` 只属于 capability/plan/report inventory，不是 `AnchorResult.calculation_status`。

- reference plan 只有在 18 个 required plugin 均已注册且兼容时才可执行；
- 未实现 plugin 使 plan compilation `blocked`；
- blocked report 可以列出 18 个 `not_attempted` inventory entry，但不得伪造 AnchorResult；
- 开发中的单领域测试使用显式 test-only partial plan；不能把未实现算法伪装成 `not_computable`。

三层 inventory 枚举不得混用：

- capability status：`available`、`plugin_unavailable`（目标 ID/version 未安装）、`not_implemented`（packaged definition 存在但无可执行 factory）、`incompatible`；
- plan compilation status：`compiled` 或 `blocked`；reference required entry 不是 `available` 时只能 blocked；
- evaluation inventory status：`executed` 或 `not_attempted`。只有 executed item 引用 AnchorResult；not_attempted 必须带 global block reason，不携带 calculation status。

## 5. 架构与 ownership

~~~text
AlignedSession + SynchronizationReport + SessionSemanticSnapshot
                         +
                AnchorExecutionPlan
                         +
                ResolvedReferenceSet
                         |
                         v
            request/snapshot/plan validator
                         |
                         v
               deterministic scheduler
                         |
          +--------------+---------------+
          |                              |
    AnchorPlugin                    ArtifactSink
          |                              |
    AnchorMeasurement             content-addressed refs
          |
    central scorer
          |
    AnchorResult v0.2 x active catalog
          |
    AnchorEvaluationReport -> M5
~~~

### 5.1 M4 owns

- compiled execution-plan consumption；
- packaged trusted plugin registry；
- typed dependency DAG；
- anchor-specific grids/windows/preprocessing；
- raw metrics、phase/event breakdown、classification override；
- one-hot D/A/U raw likelihood 和 continuous score；
- per-anchor availability 与 non-gating diagnostics；
- derived artifact、result/report fingerprints。

### 5.2 M5 owns

- editable AnchorBinding、ModelBundle draft/revision/publish；
- 把 published revision 或 exact preview snapshot 编译为 M4 execution plan；
- 33-node graph、CPT、BN observation 和 inference；
- O8/O13 `likelihood_strength=0.50` 与 H1/H3 `gaze_allocation` group 的 reference `likelihood_strength=0.50 each` dependence protection；
- model-weighted sub-skill/competency/modality/overall coverage；
- posterior、assessability 和 explanation。

### 5.3 M6 owns

- published model/session lock；
- `RunPreflightReport` 和正式运行授权；
- AssessmentRun orchestration、progress、cancel、cache；
- managed artifact root、原子持久化、结果导出和 replay。

M4 定义 `DerivedArtifactSink` port，并在测试中使用 in-memory 或临时受管实现；临时产物不冒充 M6 persistence。

## 6. 输入合同

### 6.1 AnchorEvaluationRequest

~~~text
AnchorEvaluationRequest
  aligned_session: AlignedSession
  synchronization_report: SynchronizationReport
  session_semantic_snapshot: SessionSemanticSnapshot
  execution_plan: AnchorExecutionPlan
  resolved_references: ResolvedReferenceSet
~~~

`DerivedArtifactSink` 作为 service dependency 注入，不进入可序列化 request。

强制不变量：

- session ID 一致；
- source snapshot fingerprint 一致；
- synchronization fingerprint 一致；
- M3 disposition 不是 blocked，且 `AlignedSession` 存在；
- semantic snapshot、annotation、reference、plan、plugin、parameter hashes 已冻结；
- execution plan 已通过 ID、schema、unit、plugin compatibility、DAG 和 artifact recipe 校验；
- plugin/provider 只能看到其分别声明的 streams、runtime context、semantic paths、reference、parameters 与 upstream results/artifacts；runtime context 和 semantic projection 使用不同字段，不做隐式路径分流。

`AlignedSession` 不能单独作为 M4 输入，因为它不保留完整 stream lifecycle、units/source classification、reference validity 和任务语义。

### 6.2 核心合同族

M4-A 必须分别定义并版本化以下合同，不能把它们折叠为一个自由格式字典：

- `AnchorPluginDefinition`：插件身份、兼容 API、输入/依赖声明、measurement/artifact schema 与 parameter schema；
- `AnchorCatalog`：profile 内 anchor definition、lifecycle、canonical order 和 required/optional policy；
- `AnchorExecutionPlan`：对同一 snapshot 冻结后的可执行 catalog、插件、参数、DAG 和 artifact recipe；
- `SessionSemanticSnapshot`：phase/event/AOI/control mapping/baseline 与 applicability 语义；
- `AnchorEvaluationRequest`：不可变输入引用；
- `AnchorMeasurement`：插件输出的原始数值、breakdown、override candidate 与 trace；
- `AnchorResult` v0.2：中央 scorer 的 evidence 输出；
- `AnchorInventoryItem`：expected/executed/not_attempted capability inventory；
- `AnchorEvaluationReport`：canonical inventory、disposition、availability 和 fingerprints；
- `AnchorArtifactRef`：typed content-addressed derived artifact 引用。

### 6.3 AnchorExecutionPlan

每个 active entry 至少锁定：

- anchor ID、definition version 和 lifecycle；
- plugin ID/version/API compatibility/implementation digest；
- parameter schema ID、parameter snapshot 和 hash；
- required inputs、applicability、phase/event scope；
- typed dependencies；
- measurement/output/artifact schemas；
- temporal/grid/window recipe；
- scorer ID/version/thresholds；
- canonical report order。

M4 首次实现只加载 packaged trusted plugins；不扫描目录、不动态 import 用户代码、不执行 `eval`。

## 7. AnchorResult v0.2

M4 必须发布新的 per-contract schema `anchor-result-0.2.0`，不能静默改变 `anchor-result-0.1.0`。

~~~yaml
contract_id: anchor-result
contract_version: 0.2.0
anchor_id: O11
calculation_status: computed
evidence_state: unacceptable
evidence_likelihood:
  state_order: [unacceptable, adequate, desired]
  values: [1.0, 0.0, 0.0]
continuous_score: 0.0
primary_value: null
classification_override:
  code: response_missed
raw_metrics:
  miss_count: 1
phase_results: {}
event_results: []
derived_artifacts: []
diagnostics: []
provenance: {}
result_fingerprint: sha256:...
~~~

v0.2 规则：

- active calculation status 只有 `computed`、`missing_input`、`not_applicable`、`not_computable`、`dependency_missing`、`extractor_error`；
- `invalid_quality` 只存在于 legacy v0.1 reader，不由 M4 产生；
- `computed` 必须提供 D/A/U likelihood；
- 非 computed 结果不得携带 evidence state、likelihood 或 continuous score；
- `primary_value` 在 missed/no-stable/no-gaze/degenerate physiology override，或 O3 等固有多指标 conjunction 没有诚实单一标量时允许为 null；此时必须提供枚举 `primary_value_reason` 和完整 typed `raw_metrics`；
- 所有 JSON 数字必须有限；miss 不使用 Infinity，退化比值不使用 NaN；
- phase/event breakdown 必须有自己的 calculation status、raw metrics、override 和 observation；
- coverage、gap、sample count、artifact flags 和 sync metrics 只进入 diagnostics/provenance，不参与 scorer；
- v0.2 删除强制 `AnchorQuality`、`quality_transform` 和 quality likelihood mixing；
- `classification_override` 是一等字段，不藏在自由格式 extensions 中。
- override allowlist 只能把已观察到的失败模式确定为 Unacceptable；插件不得用 override 绕过阈值把 observation 强制改为 Desired 或 Adequate。

`ComputationTrace` 是独立的 typed trace，记录实际 sample count、source/aligned time range、window/grid ID、匹配/插值方法和同步 diagnostics。它用于审计，不生成 quality score、不修改 likelihood、不阻止计算，也不得在 UI 中称为“质量门”。

已知 override 至少包括：

- `capture_missed`；
- `no_stable_hover`；
- `recovery_missed`；
- `response_missed`；
- `correction_missed`；
- `no_gaze_dwell`；
- `fixation_missed`；
- `ecg_rr_unavailable`；
- `ecg_baseline_nonpositive`；
- `physio_trace_unavailable`；
- `eeg_spectrum_degenerate`；
- `eeg_baseline_degenerate`。

这些 override 表示观察到的差表现或退化计算结果，统一生成 `computed + Unacceptable`。

`anchor-result-0.1.0` 与其 reader/schema 在 M4 过渡期只读保留，以支持历史 M1 合同和显式迁移检查；M4 writer 永远不产生 v0.1，也不提供把 v0.1 quality 自动翻译成 v0.2 evidence 的隐式 adapter。移除 legacy 合同必须另行决策。

## 8. 状态与错误边界

### 8.1 Request/plan level

以下情况使 evaluation `blocked`，且不运行插件：

- snapshot/session/synchronization fingerprints 不一致；
- unknown/incompatible plugin、scorer 或 schema；
- duplicate ID、missing dependency、DAG cycle；
- parameter/unit/reference contract 无效；
- artifact root/recipe 越界；
- reference-model-v0.1 不是精确 18-entry catalog；
- plugin 宣称根据表现数值或所谓数据质量丢弃 observation。

### 8.2 Anchor level

| 状态 | 唯一语义 | M5 observation |
|---|---|---|
| computed | 已按公式得到 D/A/U，包括极差表现和 override | 提交 likelihood |
| missing_input | 必需模态、流或字段确实不存在/未导出 | omitted |
| not_applicable | 可信任务语义明确没有该 phase/event/观察机会 | omitted，不进入 applicable 分母 |
| not_computable | reference、target、AOI、mapping、baseline 定义或必要公式参数缺失 | omitted |
| dependency_missing | 必需上游 result/artifact/profile 未产生 | omitted |
| extractor_error | 插件异常、输出违约或 artifact 工程失败 | omitted |

数值大、控制剧烈、HR/EEG 极端、达到公式最小数学基数后的采样稀疏、未响应、未恢复和未注视不属于上述非 computed 状态。

### 8.3 Blocked 与 per-anchor 状态的唯一分界

| 情况 | 唯一结果 |
|---|---|
| request/catalog/plan/schema 文档本身不可解析，fingerprint 不一致，parameter 值不通过已声明 schema/unit，reference descriptor/hash 违约，unknown dependency/plugin/scorer，DAG cycle | 整次 `blocked`；零插件执行 |
| 合法 plan 声明了 required stream，但当前 session inventory 为 missing/export_pending，或适用 span 内完全没有该 direct stream 的 temporal support | 该 anchor `missing_input`，reason 精确到 stream/span |
| 合法 plan 和 schema 已通过，但当前 session 没有解析出所需 target/reference/AOI/control mapping/baseline 定义；或者非空输入不足公式最小数学基数 | 该 anchor `not_computable`；不得称为 quality failure |
| plan 引用的 dependency ID/type 不存在 | plan compile `blocked` |
| dependency 合法存在，但执行后没有 required result/artifact/profile（包括其 missing/config/error 结果） | 下游 `dependency_missing`，记录 upstream status/fingerprint |
| plugin 抛异常、measurement/result schema 违约、单插件 staging artifact 失败 | 该 anchor `extractor_error`；独立节点继续 |
| 全局 report inventory 或最终原子提交失败 | 整次 `blocked`；丢弃 staging result refs，报告只保留 expected/not_attempted inventory 与 failure diagnostics |

`ResolvedReferenceSet` 可以包含结构合法但 resolution status 为 absent 的 entry；它导致需要该 entry 的 anchor `not_computable`。Reference descriptor、checksum 或坐标合同本身无效则属于 request/plan `blocked`。由此避免“缺一个 session reference”和“提交了损坏的 reference contract”共用一个状态。

## 9. Typed dependency DAG

依赖类型固定为：

1. `result_dependency`：读取上游 session result；
2. `artifact_dependency`：读取 mask/window/event trace；
3. `algorithm_profile_dependency`：复用算法版本和参数，在当前窗口重算；
4. `preprocessing_dependency`：读取 fixation、movement、R-peak 等共享预处理产物。

reference catalog：

| Anchor | 直接输入 | typed dependency | 主要 artifact |
|---|---|---|---|
| O1 | X、phase、envelope | 无 | desired-envelope mask |
| O2 | X、task reference、phase | 无 | tracking-error trace |
| O3 | X、target、D→H、envelope | 无 | capture trace |
| O4 | X、hover envelope/limits | 无 | stable-hover mask |
| O5 | U、active channels、W_min | movement profile | movement events |
| O6 | U、trim/endpoints/weights | 无 | RMS contribution trace |
| O7 | U、active channels | movement profile | reversal events |
| O8 | 无新 raw stream | O1/O5 results | component trace |
| O9 | U | O1/O4 masks + movement profile | micro-movement events |
| O10 | X、event/envelope | event primitive | recovery events |
| O11 | U、disturbance mapping | event primitive | response events |
| O12 | X/U、effect mapping | event primitive | correction events |
| O13 | X/U/ECG、phase | O1/O5/O7 profiles + H4 trace | joined coupling windows |
| H1 | I/G、AOI、phase | gaze-AOI intervals | phase dwell |
| H2 | I/G、critical event/AOI | fixation-v1 | event fixation trace |
| H3 | I/G、AOI、phase | gaze-AOI intervals | phase off-task dwell |
| H4 | ECG、baseline、phase | R-peak preprocessing | control-physio trace |
| H5 | EEG、baseline/channel map、phase | EEG preprocessing | engagement trace |

`pilot_camera` 保持独立一等模态，但不是当前 18-anchor 的必需输入。未来插件可以先从 pilot_camera 生成 canonical head pose/G(t) 或新的 anchor。

## 10. Temporal、grid 与数值规则

- M3 `SessionWindow` point domain 保持闭区间 `[start_t_ns,end_t_ns]`；
- M4 phase/analysis/window span 使用半开区间 `[start_t_ns,end_t_ns)`；
- 最后一个 span 可显式 `include_session_terminal_point=true`，terminal point 对时间积分新增权重为 0；
- 没有全局 analysis grid；每个 plugin revision 声明 native/resampled/window policy；
- 时间转换使用 Decimal + round-half-even；
- nearest tie 固定选择较早 timestamp，再按 stable source row ID；
- native-rate 布尔 mask 的持续时间积分使用 left-hold：样本 `i` 的状态作用于 `[t_i,t_{i+1})` 与 phase 的交集；segment 最后样本只有在 semantic span 明确给出 end 时才延伸到该 end，否则不增加持续时间；
- 不 extrapolate；插值、滤波和匹配是算法定义，不是数据 admission gate；
- quantile method、boundary inclusion、partial-window policy 和 phase aggregation 必须显式版本化，不能依赖库默认；
- raw metrics 不因极端值裁剪；只有公式本身声明的 bounded output（例如 TPX）可以 clamp；
- DSP 数值依赖和实现 digest 必须进入 plugin provenance。

Grid/window hash 至少覆盖 schema/version、ID、plugin version、rate、length、step、alignment、partial policy、interpolation/matching、boundary policy 和 parameter hash；排除绝对路径、host、wall time 和 object identity。

### 10.1 Temporal support 与 gap

M4 不用 coverage fraction 决定“数据够不够好”，但也不能跨没有 observation 的时间伪造样本。统一规则如下：

1. `support_interval_v1` 不要求 M3 另造 gap-interval DTO。M4 对每个 point/inherit artifact 只取 in-session aligned rows，按 `(t_ns,stable_source_row_id)` 排序，并读取同一 `SynchronizationReport` artifact metrics 的 `gap_threshold_ns`。相邻排序行的 positive delta 严格 `> gap_threshold_ns` 时，在后一行之前切开新 segment；等于 threshold 不切分，duplicate timestamp 不产生时长。`gap_threshold_ns=null` 表示没有可用于切分的 positive delta。M4 必须用同一规则重算 `gap_count/max_gap_ns` 并与 M3 report 对照；不一致属于 snapshot/report contract mismatch，使 request blocked。threshold、重建 segment 边界和 M3 metrics 都进入 trace/fingerprint。
2. 同一重建 segment 内样本 `i` 的 left-hold support 为 `[t_i,t_{i+1})`；gap 前最后一行不延伸到 gap 后，segment 最后一行只延伸到该 segment 明确的 semantic end（若无 end，则不产生额外时长）。
3. M3 gap diagnostic 只定义“这里没有 support”，不使整个 anchor invalid；M4 不跨 gap 插值、计 movement、形成 fixation/RR/PSD 窗或延长 stable run。
4. 必需 direct stream descriptor/file/field 缺失，或 present stream 在整个适用 span 零 support，通常为 `missing_input + no_temporal_support`。唯一例外是插件已从独立 task/scene opportunity 明确观察到“没有行为事件”的受控 override，例如 I/cue/phase 存在且 G stream present 但没有 gaze/fixation dwell；这按 H1/H2/H3 规则为 computed U。存在非空 support 就按已观察 support 计算，不设置最小 coverage 百分比。
5. 公式需要的最小数学基数不足时使用 `not_computable + insufficient_mathematical_support`，例如导数没有两个时间点、PSD 没有两个样本或两个 stream 没有任何可 join support；这不是对数值好坏的判断。
6. 已观察到的行为失败仍是 computed U：stable mask 全 false、没有 qualifying movement、没有 response/recovery/fixation、gaze 全落 `other_scene`，都不是数学 support 缺失。
7. 每个 metric 的 denominator 必须在插件 schema 中固定为 phase wall-clock duration、observed support duration 或 event count之一；不得在运行时根据结果挑选最有利分母。

对 O1/O4 这类状态持续时间，分母是完整 applicable phase duration；无 support interval 不增加 inside/stable numerator。对需要速率/谱估计的 O5/O7/O9/H4/H5，分母/窗口只使用明确 observed support，不跨 gap；任何 partial support 都照常计算并在 trace 中报告，不做 coverage gate。

### 10.2 Breakdown 到 session result 的状态聚合

每个 anchor 先从冻结 semantic snapshot 得到 canonical applicable phase/event/window inventory，再逐项计算 breakdown。Session aggregate 使用唯一规则：

1. inventory 为空时，session 为 `not_applicable`；breakdown 可以为空，但必须保存 applicability reason。
2. `not_applicable` breakdown 不进入该 anchor 的聚合；剩余 applicable breakdown 全部为 `computed` 时，才按 §12 的 anchor-specific worst/conjunction/pooled 规则生成 session D/A/U。
3. 任何 applicable breakdown 为非 computed 时，session 不得只聚合“剩下的好数据”，也不得携带 D/A/U likelihood。Session calculation status 按固定优先级选择：`extractor_error > dependency_missing > missing_input > not_computable`；所有并列/次级原因仍完整保存在 ordered breakdown/diagnostics 中。这个优先级只用于选择单一状态，不是表现等级或 quality gate。
4. `computed + Unacceptable` override 仍是 computed：它按 anchor-specific veto/worst 规则参与 session 聚合，不会触发上述非 computed 优先级。
5. 对 pooled H1/H3，先要求每个 applicable phase 都得到 computed numerator/denominator 或受控 computed-U override，再合并分子分母；对 O1/O10/O11/O12/H2 等 worst/veto anchor，也必须先完成全部 applicable breakdown，不能因先看到一个 U 就跳过后续 trace。

## 11. Scoring

插件先产生 `AnchorMeasurement`，中央 scorer 再产生 evidence。reference 默认 `hard_threshold_v1`：

- one-hot state order 固定为 `[unacceptable, adequate, desired]`；
- higher-is-better 明确使用 `>=`；
- lower-is-better 明确使用 `<=`；
- two-sided band、conjunction 和 classification override 使用版本化 scorer policy；
- 不在阈值附近自行插值。

~~~text
continuous_score = (P(adequate) + 2 * P(desired)) / 2
~~~

hard U/A/D 分别为 0/0.5/1。soft scorer 只能通过带 schema、版本、transition parameters 和 golden tests 的新 model revision 启用。

## 12. Reference anchor algorithms

本节的值是可运行工程默认，不是最终专家标准。参数修改产生新 snapshot；公式族变化产生新 plugin version。

### 12.1 O1 Phase-state Precision

对每个 phase，以 native X sample support 做时间积分：

~~~text
P_phase = 100 * inside_joint_desired_envelope_duration / phase_duration
~~~

保存逐轴和 joint mask；session primary 为适用 phase 的最小值，任一 phase U 则总体 U，全部 D 才总体 D。D `>=90%`，A `>=70%`，否则 U。任一非空适用 phase 都计算，不设覆盖率或最短 2 s gate。

### 12.2 O2 Peak Tracking Excursion

默认 time-aligned 3D L2：

~~~text
e(t) = norm(position(t) - position_reference(t))
E_peak = max(e(t))
~~~

`time-aligned-linear-v1` 以 applicable phase 内的 native X timestamps 为 evaluation grid；reference 先转换到与 X 相同的版本化坐标 frame/unit，再只在同一连续 reference segment 的相邻样本间线性插值。精确 timestamp 重合时取 stable source-row order 的第一行；不 extrapolate，两个流没有任何可 join timestamp 时为 `not_computable + no_reference_overlap`。保存分轴误差和最早峰值时间；对所有 joined points 取 max，不设 overlap fraction gate。D `<=2 ft`，A `<=5 ft`，否则 U。reference 必须是独立任务标准；actual X 不能冒充 commanded path。`nearest-path` 是可编辑的另一个显式 plugin/profile，不是 reference 默认回退。

### 12.3 O3 Terminal Capture Quality

~~~text
overshoot = max(0, max(arrival_axis dot (position - hover_target)))
settling_time = D-to-H boundary 到进入 hover envelope 并连续保持 2 s
~~~

`arrival_axis` 由 task semantic snapshot 以目标坐标 frame 中的有限非零向量声明，插件先归一化；缺 target/frame/axis 为 not_computable。默认 observation span 为 `[D_to_H_boundary, applicable_hover_phase_end)`；若 task profile 显式给出更短 `capture_horizon_s`，取两者较早 end。overshoot 在 boundary 到首次满足 2 s hold 的完成时刻之间取最大；始终未捕获则取到 observation end。settling time 计到该 qualifying hold 的**起点**，但必须观察完整 2 s 才确认。D：overshoot `<=2 ft` 且 settling `<=3 s`；A：`<=5 ft` 且 `<=5 s`；其他 U。观察期结束仍未捕获为 `computed + U + capture_missed`，保存 finite observed span，不使用 Infinity。正常 computed O3 也以 `primary_value=null + primary_value_reason=composite_conjunction` 表达，两个带单位 raw metrics 才是评分输入。

### 12.4 O4 Sustained Hover Time

~~~text
stable = inside_hover_envelope
         AND speed_within_limit
         AND angular_rate_within_limit
primary = longest_continuous_stable_duration
~~~

D `>=10 s`，A `>=5 s`，否则 U；完全没有稳定悬停为 `0 s + U`。默认不填补行为越界；专家若容忍瞬时偏离，使用明确的 `max_behavioral_excursion_s`，不称为数据 gap repair。

### 12.5 O5 Workload Rate

active channels 由 task profile 声明，未操纵的 configured channel 仍保留并得到 0 movement，不能动态删除。每个 applicable phase 和 continuous support segment 独立处理：在 `phase_start + k*10 ms` 且落入该 segment 的 grid 上做同 segment 线性插值；不跨 gap。对归一化 full-travel signal 使用 5 Hz 四阶 Butterworth SOS、`sosfiltfilt(padtype=odd,padlen=min(15,n-1))`；`n<3` 时不平滑并记录 diagnostic。导数在 interior 用 central difference、端点用 one-sided difference；单点 segment 导数为 0。deadband 为 0.5% full-travel/s：导数大于 deadband 标为 `+1`，小于负 deadband 标为 `-1`，其余标为 `0`。最大同号非零 run 的 duration 定义为该 sign-labeled grid samples 的 left-hold intervals `[t_i,t_{i+1})` 在当前 segment 内的时长之和，必须 `>=50 ms` 才 qualifying；不是 sample count，零样本既不贡献这 50 ms，也终止当前同号 run，末个 grid point 没有下一点时不凭空增加时长。两个相邻 qualifying run 若符号相反，则允许中间存在任意长度的零平台，并在前一 run 末点至后一 run 首点的闭区间内取 filtered signal 极值作为 turning point；极值平顶取最早/最晚极值 timestamp 的中点，round-half-even 到 t_ns。leading/trailing 零平台和 segment 首尾不形成 turning point。只有相邻 turning points 位移 `>=0.5%` full travel 才计一个 movement。

~~~text
W_channel = total_movement_count / total_observed_support_duration_s
W = mean(W_channel over configured active channels)
ratio = W / W_min
~~~

D ratio `<=2`，A `<=4`，否则 U。duration 是各 applicable phase 内 eligible support segment 的 wall-clock span 之和，不是 task 全长或 grid point count；小于两个时间点且总 support duration 为 0 时为 not_computable。`W_min` 是 task profile 固定的同单位 rate，不按当前 window/session 重估；缺失为 not_computable。控制再剧烈仍照常计算。

### 12.6 O6 Control Magnitude RMS

使用显式 trim/lower/upper endpoints 和非负、和为 1 的 channel weights。每通道先做不裁剪的 piecewise normalization：

~~~text
u_norm = (u-trim)/(upper-trim),  u >= trim
u_norm = (u-trim)/(trim-lower),  u < trim
RMS_channel = sqrt(integral(u_norm^2 dt) / observed_support_duration)
RMS_total = 100 * sqrt(sum(weight * RMS_channel^2))
~~~

D `<=30%`，A `<=50%`，否则 U。积分在每个 support segment 使用 left-hold 后求和，不跨 gap；超出 calibration endpoints 的有限值不 clip，因此可以产生 `>100%` 的有效负面结果。lower < trim < upper 和 weights 在 plan compile 校验；reference 默认不从 pilot performance 自动估计 trim，这种模式若需要必须显式发布。

### 12.7 O7 Control Reversal Rate

复用 O5 完全相同的 grid/filter/sign-run/turning-point profile；有效反转要求相邻峰谷幅值 `>=2% full travel`、间隔 `>=0.15 s`。每通道 rate 的 denominator 与 O5 是同一 total observed support duration；session primary 取 configured channels 最大值。D `<2 Hz`，A `2 <= CRR < 4 Hz`，U `>=4 Hz`。

### 12.8 O8 TPX Composite

~~~text
TPX = (P / 100)^2 * sqrt(W_min / max(W, W_min))
TPX = clip(TPX, 0, 1)
~~~

读取 computed O1/O5 数值；上游即使 U 仍继续计算。D `>=0.6`，A `>=0.4`，否则 U。默认 `likelihood_strength=0.50` 由 M5 应用。

### 12.9 O9 Dead-band Activity

在 O1 desired mask 与 O4 stable-hover mask 交集内，以默认 nearest-within-20-ms 对齐 U，复用 movement detector，仅计 `[0.5%,5%]` full-travel micro movements：

~~~text
DBA_channel = micro_movement_count / stable_hover_duration
DBA = max(DBA_channel)
~~~

D `<1 Hz`，A `1 <= DBA < 2 Hz`，U `>=2 Hz`。Mask intersection 全 false 时不伪造 0 Hz，返回 `computed + U + no_stable_hover`，primary null。存在 stable mask 但 U 在全部 stable spans 内都没有 within-20-ms match 时为 `missing_input + no_temporal_support_U`；只要存在 matched support，就在 matched contiguous spans 内复用 O5 detector，denominator 为这些 spans 的总时长，不设置 match coverage threshold。

### 12.10 O10 Recovery Time

起点由 task profile 固定为 disturbance marker，或一次后来满足持续条件的 adequate-envelope exit run 的首个越界 timestamp；不能用 100 ms confirmation time 延后起点。默认 `recovery_horizon_s=15`，实际 end 为 event+15 s、phase end、session end 三者最早者。恢复定义为重新进入 desired envelope 并连续保持 2 s，latency 计到 qualifying hold 的起点。D `<=5 s`，A `<=10 s`，否则 U；到 observation end 未恢复为 `computed + U + recovery_missed`，无论实际可观察 wait 是否小于 15 s都保存 finite wait 并判 U。多事件无 miss 时取 worst，任一 miss 否决 session。

### 12.11 O11 Disturbance Latency

对 U 使用 20 ms trailing causal median；事件前 1 s 中位数为 baseline。若事件距 phase 起点不足 1 s，则使用该 phase 内事件前全部非空样本；若一个前置样本都没有，则使用 task profile 明确提供的 neutral/trim baseline，两者都不存在才是 `not_computable`。默认 `response_horizon_s=2`。Event mapping 明确 channel 与正确 sign；reference aggregation 为 `earliest_any_mapped_correct`：任一 mapped channel 沿正确方向变化 `>5% full travel` 且持续 `>=100 ms` 的首个 onset 为响应。任一 mapped channel 先出现同幅值/持续的错误方向动作，即使后来正确，也判为 `computed + U + response_missed`；低于 detector threshold 的噪声不算错误响应。D `<=500 ms`，A `<=1000 ms`，否则 U。多事件无 miss 时取 worst，任一错误方向、无响应或到 horizon/session end 超时否决 session并保存 finite wait。

### 12.12 O12 Envelope-drift Latency

状态连续 `>=100 ms` 离开 desired envelope 后，把该 run 的首个越界 timestamp 定义为 `t_exit`；latency 不从确认时刻起算。根据 signed state error 和 control-effect mapping 确定 mapped channels/正确 sign；默认 aggregation 同 O11 为 `earliest_any_mapped_correct`。control baseline 使用与 O11 相同的“事件前至多 1 s、非空短窗、显式 neutral/trim fallback”规则，默认 `correction_horizon_s=2`。正确输入相对 baseline `>5% full travel` 且持续 `>=100 ms`；先出现 qualifying 错误方向动作也直接 `computed + U + correction_missed`。D `<=300 ms`，A `<=800 ms`，否则 U；多事件无 miss 时取 worst，任一 miss 否决 session；从未越界为 not_applicable，O1 已负责评价保持包线。

### 12.13 O13 Physio-control Coupling

reference 使用连续逐窗 coupling，不使用旧 high/baseline 分组比值。`control-physio-grid-v2` 默认 30 s/5 s、phase-start、不跨 phase：phase `<30 s` 时整段形成一个窗口；`>=30 s` 时先从 phase start 按 5 s step 建立完整窗口，若最后一个窗口未覆盖 phase end，再增加一个 phase-end-aligned 30 s 窗口；相同 `[start,end)` 去重。`window_id` 固定为 `cpw-` 加 RFC 8785 canonical array `["control-physio-grid-v2",phase_id,start_t_ns,end_t_ns]` 的 SHA-256 前 24 个小写 hex；完整 hash 也进入 artifact。不设最低窗口数、valid fraction 或 coverage gate。

以 phase start=0 s 为 golden：长度 10 s -> `[0,10)`；30 s -> `[0,30)`；31 s -> `[0,30),[1,31)`；35 s -> `[0,30),[5,35)`；36 s -> `[0,30),[5,35),[6,36)`。这些列表必须 exact，防止尾窗重复或跨 phase。

每窗重算 O1/O5/O7：

~~~text
qO1,qO5,qO7 = D/A/U -> 1/0.5/0
Q_control = 0.50*qO1 + 0.25*qO5 + 0.25*qO7
activation = clip((signed_delta_HR_pct - 10) / (20 - 10), 0, 1)
coupling_loss = 100 * activation * (1 - Q_control)
O13 = max(coupling_loss over windows)
~~~

D `<5%`，A `5 <= value < 20%`，U `>=20%`。每窗 O5 使用 task profile 同一个固定 `W_min`，不能按窗口重估；O1/O5/O7 使用各自同版本算法和该 window 的 support。任一 control component 在某窗没有数学 support 时，该窗为 `dependency_missing`，并使 session O13 为 dependency_missing，不把缺值映射成 q=0。它表示生理激活与控制损失共同出现，不证明因果或医学状态。M5 对 O13 使用默认 `likelihood_strength=0.50`。

若 H4 已以 ECG/RR 或 baseline 退化 override 产生 `computed + U` 但无法提供 signed-HR window trace，O13 也产生 `computed + U + physio_trace_unavailable`，不得误报 `dependency_missing`；只有 H4 result/artifact 因真正的 missing/config/error 未产生时才使用 `dependency_missing`。

### 12.14 H1 AOI Dwell

I(t) 是随 head pose 变化的实际第一视角 VR scene。G samples 按 stable `(t_ns,source_row_id)` 排序；sample `i` 的 AOI label 对其 support interval `[t_i,t_{i+1})` 生效并裁到 phase，segment terminal 遵循 §10.1。gaze ray 与当时 scene frame、FOV 和 dynamic AOI 相交；多个 3D AOI 命中时先取最近正 depth，再按配置 priority、stable AOI ID；2D overlap 先按 priority，再按 stable AOI ID。taxonomy 必须有覆盖全视野的 `other_scene` catch-all，默认归为 off-task；stream 已存在但 blink、tracking-loss 或不可投影的 interval 也映射到 `other_scene`，不从 denominator 删除。

~~~text
R_AOI = 100 * sum(role_weight * gaze_dwell_role) / total_gaze_dwell
~~~

Primary/Secondary 默认权重 1，Off-task/other_scene 为 0。H1/H3 使用逐 gaze interval 时间积分，不以 fixation dwell 作分母；session 将所有 applicable phases 的分子和分母先分别求和再相除，不平均 phase 百分比，也不取最差 phase。D `>=85%`，A `>=70%`，否则 U；G stream 存在但所有 applicable phases 都没有非零 gaze support 时为 `computed + U + no_gaze_dwell`。

### 12.15 H2 First Fixation Latency

fixation-v1 默认 I-VT angular velocity threshold 100 deg/s、minimum duration 100 ms；相邻 G samples 用最短球面角/时间计算速度，等 timestamp 按 stable row 去重保留第一行。起点是 task script 的 `cue_available_t`，不能因 pilot 未转头而延后；默认 `fixation_horizon_s=2`。D `<=500 ms`，A `<=1000 ms`，否则 U；到 horizon/session end 始终未注视 relevant AOI 为 `computed + U + fixation_missed`，latency null、保存 finite observed wait。多事件无 miss 时取 worst，任一 miss 否决 session。

### 12.16 H3 Off-task Dwell

~~~text
OffTaskDwell = 100 * off_task_gaze_dwell / total_gaze_dwell
~~~

与 H1 共用完全相同的 gaze-AOI intervals、tie-break、blink/tracking-loss 和 pooled-phase denominator；`other_scene` 默认计入 off-task。D `<5%`，A `5 <= value < 15%`，U `>=15%`；没有可计 gaze dwell 为 `computed + U + no_gaze_dwell`，不能把零分母伪造成 `0% + Desired`。H1/H3 在 M5 声明同一 `gaze_allocation` dependence group。

### 12.17 H4 ECG Fluctuation

Reference 默认且唯一的 packaged mode 是 `provided_r_peaks_v1`；只有新 plugin/profile 才可显式选择版本化 `recompute_from_raw_v1`，不能运行时自动切换。RR interval 定义为相邻 R-peaks 之差，归属到第二个 peak 的 timestamp；允许第一个 peak 位于 window/baseline 起点之前，禁止把同一 RR 重复归属。instantaneous HR 为 `60 / RR_seconds`。baseline 存在即使用，不设 60/300 s admission threshold；HR0 是 second-peak timestamp 落在 baseline interval 内的全部 finite positive HR 的 median。

~~~text
HR0 = median(HR_baseline)
signed_delta_HR = 100 * (median(HR_window) / HR0 - 1)
fluctuation = abs(signed_delta_HR)
~~~

每个 task window 使用 second-peak timestamp 落在 `[start,end)` 的 HR median；与 O13 共用 `control-physio-grid-v2`，session 取 absolute fluctuation 最大的 window，最早 window 解决并列。D `<20%`，A `20 <= value < 40%`，U `>=40%`。极高/极低 HR 不过滤；ECG/R-peak stream 与 baseline 定义存在但无法形成 RR、HR0 非正或窗口 HR 退化时为 computed U override。RMSSD/SDNN 等只作 diagnostics。

### 12.18 H5 EEG Fluctuation

默认 `eeg-engagement-v1` pipeline：unit conversion；先把每个 continuous support segment 裁到 baseline 或单个 applicable phase，所得 processing segment/channel 分别做 constant demean + linear detrend，再在**切窗前**预处理；滤波、detrend 和窗口都不跨 baseline/phase boundary。Plan compile 要求 EEG Nyquist 严格大于 35 Hz。processing segment `n>=4` 时使用四阶 zero-phase Butterworth 3–35 Hz band-pass，显式 `sosfiltfilt(padtype=odd,padlen=min(27,n-1))`；随后按 task mains profile 使用 50 或 60 Hz 二阶 IIR notch、Q=30，若 notch 低于 Nyquist 则显式 `filtfilt(padtype=odd,padlen=min(6,n-1))`，否则跳过并记录。processing segment 只有 2 或 3 个 samples 时明确跳过 band-pass/notch、记录 `short_segment_filter_bypass`，但仍继续 PSD/degeneracy 规则；少于 2 个 samples 才是 `not_computable + insufficient_mathematical_support`。之后应用 versioned common-average montage/reference，并按 4 s window、2 s step、phase-start、不跨 phase 切窗。Reference 不执行 ICA，也不按 artifact/幅值/医学范围删窗。

Welch PSD 固定为 one-sided、`scaling=density`、periodic Hann (`fftbins=true`)、`nperseg=min(round_half_even(2*fs), window_sample_count)`、`noverlap=floor(nperseg/2)`、`nfft=next_power_of_two(nperseg)`、`detrend=false`。window 少于 2 个 samples 是 `not_computable + insufficient_mathematical_support`；2 s 以下的短 phase 仍以整个 phase 成窗并按上述缩短 nperseg，不丢弃。频带和积分固定为 theta `[4,8)` Hz、alpha `[8,13)` Hz、beta `[13,30]` Hz；使用 trapezoidal integration，lower endpoint included、upper excluded，仅 beta 的 30 Hz included。每个 band 必须至少有 2 个 finite PSD bins；任一 configured channel/window 缺 band bins、band power 非有限或 `alpha+theta<=epsilon` 时，该 breakdown 为 `computed + U + eeg_spectrum_degenerate`，不得动态删除通道、返回 extractor_error 或把空 band 当作 0 后继续评分。`epsilon=1e-12`，单位与集成 band power 一致。

~~~text
E_channel = beta / (alpha + theta + epsilon)
E_window = median(E_channel over selected channels)
E0 = median(E_window over all baseline windows built with the same 4 s / 2 s recipe, baseline-start aligned)
delta_E = 100 * ((E_window + epsilon) / (E0 + epsilon) - 1)
fluctuation = abs(delta_E)
~~~

4 s 以下 phase 整段成窗；`>=4 s` 从 phase start 每 2 s 建完整窗，尾部未覆盖时增加 phase-end-aligned 4 s 窗并去重。selected channels **只**来自 task profile 的明确 `engagement_channels`，逐窗对这些通道取 median；session 取 `abs(delta_E)` 最大的 window，最早 window 解决并列。Baseline 若没有 computed window、任一 configured channel 触发 spectrum degeneracy，或 `E0<=epsilon`，则为 `computed + U + eeg_baseline_degenerate`；task window 的 spectrum degeneracy 则为 `computed + U + eeg_spectrum_degenerate`，并按 §10.2 聚合。D `<=20%`，A `<=50%`，U `>50%`。若 task/profile 根本没有配置 EEG role channels 或 baseline 定义，则为 `not_computable`；配置存在且 EEG stream 存在、但实际 spectrum/baseline 数值退化时产生 computed U override。极端 ratio 不截断；cohort/phase-specific bands 只能作为显式新 profile。

## 13. Execution、artifact 与 fingerprint

### 13.1 Topological levels

~~~text
Level 0:
O1 O2 O3 O4 O5 O6 O7 O10 O11 O12 H1 H2 H3 H4 H5

Level 1:
O8  <- O1/O5 result
O9  <- O1/O4 artifact
O13 <- O1/O5/O7 algorithm profile + H4 artifact
~~~

同 level 可并行；报告按 canonical anchor order，而不是完成顺序。一个 plugin 失败不停止独立节点；其真正下游为 dependency_missing。

### 13.2 Artifact

`AnchorArtifactRef` 至少包含 artifact ID/kind/schema、logical content SHA-256、可选 storage-file SHA-256、row count、time range、grid hash、producer plugin/version、parameter hash 和 dependency fingerprints。Mask 使用独立 `sample_mask` kind；window trace 不能冒充 sample mask。

插件在独立 staging 写入，合同通过后原子发布；任何 artifact 都不写回 Session Bundle。

### 13.3 Report

- `ready`：所有 applicable anchors computed；not_applicable 不降低 disposition；
- `ready_partial`：非 blocked 且 inventory 完整，但存在 missing/not-computable/dependency/error；
- `blocked`：request/plan/global inventory/atomic commit 失败。

非 blocked reference execution 必须有 18 个终态 AnchorResult。blocked report 只列 expected inventory/not_attempted，不伪造结果。

`AnchorEvaluationReport` 始终携带 `formal_run_authorized=false`。raw availability 定义为 `computed_count / applicable_count`：D/A/U 都计入 computed，`not_applicable` 不进分母；当 applicable count 为 0 时 ratio 为 null，不能伪造 100%。inventory 始终与 catalog 等长，只有 executed item 才引用 AnchorResult。

### 13.4 Fingerprints

至少生成：

- anchor catalog fingerprint；
- plugin registry fingerprint；
- parameter fingerprint；
- execution-plan fingerprint；
- artifact content hash；
- anchor-result fingerprint；
- anchor-evaluation fingerprint。

使用带类型标签和长度 framing 的 canonical SHA-256。绝对路径、host、wall time、request ID、线程顺序不进入 fingerprint。改变任一输入、参数、plugin、dependency、artifact 或 result 必须改变最终 fingerprint。

### 13.5 Canonical bytes

JSON-compatible contract/plan/result 对象使用 RFC 8785 JSON Canonicalization Scheme（JCS）UTF-8 bytes：不含 BOM/多余空白，map key 和 number serialization 服从 JCS，Unicode 保持 JSON 定义，NaN/Infinity 被 schema 拒绝。Typed hash 统一为：

~~~text
payload = JCS(value)
digest = SHA256(
  ASCII(type_id) + 0x00 + ASCII(schema_version) + 0x00
  + uint64_big_endian(len(payload)) + payload
)
~~~

Tabular artifact 的 `logical_content_sha256` 对 `[typed_schema_descriptor, canonical_rows_in_declared_order]` 使用同一 JCS/framing 计算；row order 必须由 `(t_ns, stable_source_row_id, stable_secondary_id)` 或 artifact schema 明确声明。Parquet/Arrow writer metadata、compression、文件路径和 library version 不进入 logical hash；`storage_file_sha256` 只做当前文件完整性检查。Cross-process determinism 要求 logical content/result/evaluation hashes 相同，不要求不同 Parquet library 产生逐字节相同文件。Opaque blob artifact 则以原始 bytes 同时作为 logical/storage content。所有 float golden 明确 tolerance；fingerprint 始终哈希 canonical 计算结果的实际有限数，不做容差量化。

### 13.6 Packaged plugin registry

首次实现使用 package resource `pilot_assessment/anchors/registry-v1.json`，每个 entry 至少包含 `anchor_id`、`definition_version`、`plugin_id`、exact `plugin_version`、`api_version`、`factory_module`、`factory_symbol`、sorted `implementation_members`、sorted `numeric_runtime_dependencies`、`implementation_digest`、parameter/measurement/artifact schema IDs 和 allowed package namespace。规则固定为：

1. plan 只引用 exact version，不做 semver range 自动选择；
2. duplicate `(plugin_id,plugin_version)`、同 key 不同 digest、duplicate anchor binding 或 resource/schema hash 不一致均 blocked；
3. anchor factory 必须实现 `definition() -> AnchorPluginDefinition`；其 plugin 必须实现 `compute(context, parameters, temporal_recipe, dependencies, artifacts) -> AnchorMeasurement`。其中 `temporal_recipe` 只能是当前 execution entry 的不可变投影，`artifacts` 只能暴露 staging，不能暴露 commit/abort/resolve 或存储路径；
4. loader 只 import registry 明确列出的 `pilot_assessment.anchors.plugins.*`/受信任 packaged namespace，不扫描目录或 entry-point 环境；
5. orchestrator 只按 registry/DAG 调 factory，禁止 O1/O2/... 中央 switch；
6. `implementation_members` 是该 plugin 的完整本地行为闭包：factory module、所有直接/间接 imported shared preprocessing/scoring helper 和读取的 package resource。Build verifier 从 factory 做静态本地 import closure 并与声明集合精确比较；漏声明、多声明、dynamic local import 或 namespace 越界均阻断 build/plan。每个 member 以规范 package-relative path 与原始 bytes SHA-256 进入 digest。
7. `numeric_runtime_dependencies` 至少锁定 Python implementation/major.minor.micro/ABI，以及 NumPy、SciPy、Polars/PyArrow 等该 plugin 实际使用的 distribution normalized name、exact version 和 installed `RECORD`/wheel content digest；声明集合必须与受控 import allowlist 一致。任何版本或 build digest 变化都改变 plugin build identity，即使 plugin source 未变。
8. registry entry JCS、implementation member hashes、declared schema/resource hashes和 numeric-runtime lock JCS 共同形成 `implementation_digest`；registry fingerprint 再覆盖所有 entry/digest。Wheel 重建后任何行为闭包 bytes 变化都必须产生新 digest/plugin build identity，禁止在同一 identity 下漂移 DSP 数值实现；
9. 同一 registry resource 使用独立 `preprocessors` map 注册共享预处理 provider；provider 遵守相同的 exact-version、namespace、closure、schema/resource hash 和 runtime identity 规则，实现 `definition() -> PreprocessingProviderDefinition` 与 `compute(context, recipe, scope, dependencies) -> TabularArtifactPayload | BlobArtifactPayload`，并且只接收其声明的正投影、当前 `PreprocessingScope` 与已解析的 provider dependencies。Provider entry 不计入 reference 18-anchor cardinality。

## 14. Fixtures 与验证

### 14.1 Per-anchor hand-calculated golden

每个 anchor 至少测试：

- normal D/A/U；
- 精确阈值边界；
- phase/event/session aggregation；
- missed/no-stable/no-gaze/degenerate override；
- missing/config/not-applicable/dependency；
- parameter hash 与 result change；
- sampling-rate invariance（适用时）；
- source/aligned views 不变；
- deterministic artifact/result replay。
- O13 对 phase 长度 10、30、31、35、36 s 的 window golden，验证短窗、尾窗、去重和不跨 phase；
- O11 的“先错误方向后正确方向”、O11/O12 的短 pre-event baseline fallback；
- H3 零分母、H5 缺 channel config 与退化 spectrum 的状态差异；
- M4 parameter/catalog schema 拒绝 `quality_gates`、`min_valid_coverage`、`failed_quality` 和 `binary_quality_v1`，AnchorResult v0.2 schema 拒绝 `invalid_quality`。

### 14.2 分层轻量 workflow fixtures

当前唯一权威 fixture 策略是已接受的 [M4 Lightweight Workflow Validation Amendment](2026-07-13-m4-lightweight-workflow-validation-amendment.md)：

1. per-anchor 定向微型测试分别证明 18 个插件的 D/A/U、边界、override、依赖与有限极差值语义；
2. all-Desired、all-Unacceptable 和 mixed 使用内存中的紧凑 aligned raw tables 执行真实 production plugins；其中 all-Unacceptable 必须得到 18/18 `computed + Unacceptable`、raw availability=1 且无 quality filtering；
3. state-matrix 使用 `AnchorEvaluator.for_testing` 与精确 fault hooks 证明 missing/config/not-applicable/dependency/error，不生成 physical bundle；
4. extension/replay 使用轻量 catalog、极小输入表和 fake/real plugin 组合，不生成图片或 Session Bundle；
5. 唯一 physical `m4-workflow-smoke-v0.1` 为 10 秒全模态 bundle，使用公开入口贯通 M1→M2→M3→M4，并产生 exact-18 computed inventory 与至少一个 D/A/U。

所有输入都必须独立于 expected output；captured-format X 不能冒充 commanded reference。所有 synthetic 结果继续标记 software-test-only/`not_supported`。

### 14.3 Lightweight oracle 与答案隔离

精确数值证明由 per-anchor/scenario micro oracle 负责，完整规则以已接受修订 §3–§4 为准。Input recipe 只能包含 raw/aligned data、semantic/config bindings、reference、events 和 fault controls；expected vectors 必须存放在独立资源中。Oracle 不 import `pilot_assessment.anchors`，production plugins 不读取 expected values，也不得把 production result/artifact 回写到输入。

默认 gate 必须拒绝序列化 AnchorResult/AnchorMeasurement、result-like `anchor_id + primary_value/state/likelihood` 结构、预计算 `q_control` 或 O8/O13 composite，以及以 O1–O13/H1–H5 为键的 expected-result map。除独立手算/oracle 比较外，还必须通过 X/reference、U、gaze/AOI、R-peaks 和 EEG beta component 的定向扰动证明 data-to-anchor 因果关系，并断言至少一个无关 anchor 保持不变。Checksum 只证明输入不可变，不能代替这些语义断言。

唯一 physical smoke 使用 amendment 冻结的 `m4-workflow-smoke-v0.1`：session `[0,10 s]`，baseline `[0,4 s)`，Translation `[4,6 s)`，Deceleration `[6,8 s)`，Hover `[8,10 s)`；它复用 M2/M3 已发布的 rate/profile，不另造高频 fixture profile。该 bundle 必须满足 amendment 的路径、PNG、行数和单次构建预算，且只在测试临时目录生成。它证明 public M1→M4、exact-18 execution、真实 O8/O9/O13 DAG、多模态 sentinel、source immutability 与确定性 replay；18 项精确阈值证明仍归 per-anchor tests。

All-Desired、all-Unacceptable 和 mixed 的 expected vectors 由紧凑 aligned raw inputs 机械产生。All-Unacceptable 继续要求 18 executed/18 computed、raw availability=1；state-matrix 继续要求 expected=18、executed=18、not_applicable=1、applicable=17、computed=11、raw availability=`11/17`。任何 fixture/expected revision 都必须产生新版本/hash，不能调输入迎合 production result。

### 14.4 Completion commands

Replacement implementation plan 必须给出并实测：

- focused contract/plugin/per-anchor/scenario tests；
- 唯一 10 秒 physical bundle 的 public M1→M2→M3→M4 smoke；
- all-Desired/all-Unacceptable/mixed real-plugin aligned workflows 与 fault-hook state matrix；
- input/expected 隔离、定向扰动、source immutability 与 cross-process deterministic fingerprints；
- extension/retire/version replay；
- full pytest suite、JSON Schema regeneration/symmetry、Ruff/formatter、strict type check 和 build/wheel install；
- repository-external format-sample interface test，但不从该数据断言 anchor 或能力；
- repository 外、清空 project-root `PYTHONPATH` 的 isolated-wheel smoke。

Isolated-wheel public entry 仍固定为 `python -m pilot_assessment.verification.m4_smoke --fixture <bundle>`，内部只调用公开 `pilot_assessment.anchors.api.evaluate(request, sink)`。Wheel 必须包含 v0.2 contracts/schemas、registry、18 plugin factories、parameter schemas 和 smoke runner；它复用同一个 10 秒 bundle，不生成第二套 full fixture。90 秒 full-rate bundle 不属于默认命令或 engineering-verification 门。

## 15. M4-A 至 M4-G 完成门

| 阶段 | 范围 | 可声称状态 |
|---|---|---|
| M4-A | 本规格、轻量验证修订、D-021–D-027、AnchorResult v0.2、catalog/plan/report schema | 18/18 specified，0/18 implemented |
| M4-B | registry、DAG、temporal kernel、artifact sink、fingerprint、fake-plugin tests | framework engineering-verified，0/18 plugins |
| M4-C | O1–O7 | 7/18 software-verified |
| M4-D | O8–O12 | 12/18 software-verified |
| M4-E | H1–H3 | 15/18 software-verified |
| M4-F | H4、H5、O13 | 18/18 individual plugins software-verified |
| M4-G | lightweight exact-18 workflows、唯一 10 秒 bundle E2E、extension、determinism、wheel、docs/handoff | M4 engineering-verified |

任何阶段都不能用 session calculation status 掩盖尚未实现的 capability。只有 M4-G 的新鲜实测证据完成后才能修改产品状态为 M4 engineering-verified。

## 16. Documentation migration

本节首先保留原 M4 规格在批准前执行 candidate alignment 的历史记录；当时只涉及 D-021–D-025，且不构成实现。2026-07-13 后续获批的轻量工作流验证修订又触发了第二次迁移：D-026/D-027、§1.1、§14.2–§14.4、§15/§17 和当前状态文档以轻量口径为准，原实施计划被取代；replacement plan 随后于同日单独获批，Task 0–1 已完成，Task 2 尚未开始。

本轮 candidate alignment 覆盖：

- `DECISIONS.md`：M4 extensibility、negative evidence/no-quality-gate、compiled plan/DAG、O13 continuous coupling、M4/M5/M6 ownership；
- `01_PRODUCT_OVERVIEW.md`：M4 输入假设、negative evidence 与里程碑状态；
- `02_ASSESSMENT_CORE_DESIGN.md`：measurement/scorer、plan、artifact sink、M4/M5/M6 数据流；
- `03_SESSION_BUNDLE_SPEC.md`：M1–M3 structural validation 与 M4 performance scoring 分离；
- `04_REFERENCE_MODEL_V0_1.md`：AnchorResult v0.2、删除 quality gates、18 个算法新语义；
- `05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md`：删除 quality mixing，保留 derived/dependence mixing；
- `08_WINDOWS_FRONTEND_DESIGN.md`：不把差表现展示为 invalid data；
- `09_VALIDATION_AND_HANDOFF.md`：all-bad、override、extension 和 no-filtering tests；
- `10_DESIGN_SELF_REVIEW.md`：记录旧 quality/O13/gaze/physiology 冲突的关闭；
- `11_IMPLEMENTATION_STATUS.md`：只记录设计/计划/实现的真实状态；
- `GLOSSARY.md`、`README.md` 和 `docs/product/README.md`：阅读顺序、术语和 handoff。

## 17. 书面规格完成门

本规格进入实施计划前必须满足：

1. 用户复核并明确批准本书面文件；
2. D-021–D-027 已写入并在独立 Git 轨迹中更新为“已接受”；
3. 所有列出的跨文档冲突已消除或明确标注 supersession；
4. 无 TBD/TODO/placeholder；
5. 18 个 anchor、阈值、boundary、override、dependency 和 artifact 均无歧义；
6. `reference-model-v0.1` exact-18 与 generic engine cardinality 不冲突；
7. M4 不生成 `invalid_quality`，且 poor performance 必须 computed U；
8. blocked/not-implemented/not-attempted 不冒充 AnchorResult；
9. M4/M5/M6 ownership 与 coverage 公式不冲突；
10. Git commit 只声称 design/documentation，不声称 M4 implemented。

原书面规格、轻量工作流验证修订与 [replacement plan](../plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 均已通过用户复核，D-026/D-027 已接受。原 `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md` 虽曾获批准，但其四套 90 秒 fixture 路线已被本修订取代，不再提供执行授权。Replacement Task 0–1 已分别由 `bc544bf`、`f56365c` 完成，Task 2 尚未开始；M4 当前保持 18/18 specified、0/18 production plugins implemented，在相应完成门通过前不得声称 M4 已 engineering verified。
