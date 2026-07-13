# Pilot Assessment Reference Model v0.1

| 字段 | 当前值 |
|---|---|
| 文档状态 | 工程参考模型；M4 完整书面规格与轻量工作流验证修订均已于 2026-07-13 获用户批准 |
| 模型 profile | `reference-model-v0.1`（尚未发布为不可变 ModelBundle） |
| 日期 | 2026-07-13 |
| BN inventory | 4 competencies + 11 sub-skills + O1–O13/H1–H5，合计 33 nodes |
| Anchor 实现状态 | 18/18 已设计，0/18 已实现；原 M4 实施计划已被取代，replacement plan 已于 2026-07-13 批准；Task 0 已获授权但尚未开始 |
| 科学状态 | engineering defaults，未完成航空、人因或医学验证 |

本文件定义 `reference-model-v0.1` 的可实现模型摘要。M4 的精确合同、公式、typed dependencies、artifact、fingerprint、fixtures 和阶段完成门以 [M4 Anchor Calculation and Evidence Availability Design](./specs/2026-07-13-m4-anchor-evidence-availability-design.md) 为唯一详细规格；本文件不得另造一套 M4 语义。

## 1. 模型边界

1. 当前阈值、窗口、滤波、AOI、控制映射、anchor binding 和 CPT 是可编辑工程默认，不是认证限制、医学诊断阈值或最终训练合格标准。
2. 专家可以在前端修改参数、anchor、图和 CPT，但所有语义修改由后端验证，并保存为新的 draft/revision；已发布 revision 不可原地覆盖。
3. D/A/U 只表示一次 session 的可观测表现，不代表飞行员永久能力真值。
4. M4 假定输入已经通过 M1–M3 的文件、schema、字段、有限数值和时间合同。采集质量由仿真采集系统保证，不是 M4 的研究对象。
5. 轨迹再差、控制再剧烈、生理指标再异常、未响应、未恢复、未注视或未稳定悬停，都是有效负面表现，必须形成 `computed + Unacceptable`，不得被过滤为低质量数据。
6. M4 不设置 coverage/noise/gap/residual/artifact/医学范围 quality gate，不做 outlier clipping、winsorization 或基于 artifact label 的删窗。technical diagnostics 只用于审计。
7. 真正缺少流/字段、任务不适用、公式配置缺失、typed dependency 缺失或插件失败，使用互斥的非 computed 状态；系统不为不存在的数据伪造 observation。
8. M4 始终 `formal_run_authorized=false`；M5 负责 BN/CPT/inference，M6 负责正式 run preflight、持久化和导出。

### 1.1 与旧参考稿的取代关系

本修订明确取代 2026-07-10 版本中的以下前向设计：

- `binary_quality_v1 -> invalid_quality -> omit/quality mixing`；
- 以 residual、valid fraction、coverage、采样波动或生理范围拒绝 M4 evidence；
- O13 的 high/baseline 分组比值；
- H1/H3 只以 fixation dwell 为分母并排除 `other_scene`；
- H4/H5 按 artifact/生理范围删窗；
- miss 使用 Infinity、退化比值使用 NaN；
- 把尚未实现的插件伪装为 session `not_computable`。

`anchor-result-0.1.0` 仅作为只读 legacy 合同保留。M4 writer 只产生 breaking `anchor-result-0.2.0`，不得静默修改旧 schema ID，也不得把旧 quality 自动转换为新 evidence。

## 2. 输入、reference 与任务语义

| 符号/流 | 含义 | 典型内容 |
|---|---|---|
| X(t) | Flight state | 位置、速度、姿态、角速度、加速度 |
| U(t) | Control input | cyclic、collective、pedal 等，保留原始单位并提供 full-travel calibration |
| I(t) | VR first-person visual scene | 随飞行员头部转动变化的逐帧实际视野，不是 pilot face image |
| G(t) | Eye tracking | gaze ray/point、head pose、可重建 fixation 的原始眼动数据 |
| EEG(t) | 脑电 | 原始通道、设备时间、channel map、baseline |
| ECG(t) | 心电 | 原始 ECG 或显式提供的 R-peaks、设备时间、baseline |
| pilot_camera(t) | 驾驶员相机 | 独立一等模态；当前 18 anchors 不强制消费 |

必需语义由冻结的 `SessionSemanticSnapshot` 提供：phase intervals、event/cue markers、task target、hover/envelope 定义、dynamic AOI taxonomy、control-effect mapping、control calibration、ECG/EEG baseline 和任务适用性。

commanded/reference path 必须来自 bundle-local `task_reference` 或锁定 ModelBundle；实际 X 不能冒充 reference。现有 2,902-row simulator CSV 只说明采集格式，不是标准轨迹、ground truth 或能力标签。

所有流先经 M3 映射为 native-rate aligned views。M4 没有全局 analysis grid；每个 plugin revision 声明自己的 grid/window/interpolation。M3 diagnostics 不构成 M4 scorer 的 admission gate。

## 3. BN 层级与 anchor mapping

生成方向固定为 `Competency -> Sub-skill -> Evidence`。Phase/task context 在 BN 外供插件计算，不计入 33 nodes；O8/O13 不使用 evidence-to-evidence 结构边。

| Competency | Sub-skill | Supporting anchors |
|---|---|---|
| TCP | TCP.1 Trajectory tracking | O1, O2 |
| TCP | TCP.2 Maneuver precision | O3, O4, O2 |
| TCP | TCP.3 Control efficiency | O5, O6, O8 |
| TCP | TCP.4 Control smoothness | O7, O9 |
| PC | PC.1 Envelope discipline | O1, O12 |
| PC | PC.2 Event response | O11, H1 |
| SM | SM.1 Reactive vigilance | O11, O12, H2 |
| SM | SM.2 Attention allocation | H1, H3 |
| OC | OC.1 Disturbance recovery | O10 |
| OC | OC.2 Stress resilience | O7, O13 |
| OC | OC.3 Physio regulation | H4, H5 |

`reference-model-v0.1` 精确使用 O1–O13、H1–H5。Generic M4 engine 的 catalog cardinality 可变：新增/retire anchor 发布新 catalog/model revision，参数修改发布新 parameter snapshot，公式修改发布新 plugin version。旧 published revision 必须可原样 replay。

## 4. AnchorResult v0.2 与 availability

插件只生成 `AnchorMeasurement`；中央 scorer 生成 `AnchorResult` v0.2。示例：

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
computation_trace: {}
diagnostics: []
provenance: {}
result_fingerprint: sha256:...
~~~

### 4.1 表现状态

state order 固定为 `[unacceptable, adequate, desired]`。Reference scorer `hard_threshold_v1` 输出 one-hot likelihood；U/A/D 的 continuous score 分别为 0/0.5/1。未来 soft scorer 必须有新版本、schema、transition parameters 和 golden tests。

### 4.2 计算状态

| 状态 | 唯一语义 | M5 observation |
|---|---|---|
| `computed` | 已得到 D/A/U，包括极差表现和受控 override | 提交 likelihood |
| `missing_input` | 必需模态、流或字段确实不存在/未导出 | omitted |
| `not_applicable` | 可信任务语义明确没有观察机会 | omitted，排除 applicable 分母 |
| `not_computable` | reference、target、AOI、mapping、baseline 定义或必要参数缺失 | omitted |
| `dependency_missing` | 必需上游 result/artifact/profile 未产生 | omitted |
| `extractor_error` | 插件异常、输出违约或 artifact 工程失败 | omitted |

M4 v0.2 不产生 `invalid_quality`。override allowlist 只能确定为 Unacceptable，不能绕过阈值强制 Desired/Adequate；至少包括 capture/recovery/response/correction/fixation miss、no stable hover、no gaze dwell、ECG/EEG degenerate feature。

raw availability 为 `computed_count / applicable_count`。D/A/U 都贡献 1；`not_applicable` 不进分母；applicable count 为 0 时为 null。M5 的 model-weighted coverage 与 assessability 另行计算，不能把表现强弱称为 coverage。

`plugin_unavailable`、`not_implemented`、`not_attempted` 只属于 capability/plan/report inventory。Reference plan 缺 required plugin 时 compilation blocked；blocked report 可列 expected inventory，但不得伪造 AnchorResult。

## 5. 18-anchor 计算基线

所有阈值都是可编辑工程默认。完整算法细节和边界以 M4 规格 §10–§14 为准。

| ID | Primary measurement / aggregation | Desired | Adequate | Unacceptable / override |
|---|---|---:|---:|---:|
| O1 | 各 phase 联合 desired-envelope 内时长占比；session 取最差 phase | `>=90%` | `>=70%` | `<70%` |
| O2 | time-aligned 3D tracking error 的最大值 | `<=2 ft` | `<=5 ft` | `>5 ft` |
| O3 | overshoot 与 settling time 合取 | `<=2 ft` 且 `<=3 s` | `<=5 ft` 且 `<=5 s` | 其他；未捕获为 U/null |
| O4 | 最长连续 stable-hover duration | `>=10 s` | `>=5 s` | `<5 s`；无稳定悬停为 `0 s + U` |
| O5 | configured active channels 的 `W/W_min` 平均 | `<=2` | `<=4` | `>4` |
| O6 | 相对显式 trim/endpoints 的 weighted control RMS | `<=30%` | `<=50%` | `>50%` |
| O7 | configured active channels 的最大 reversal rate | `<2 Hz` | `[2,4) Hz` | `>=4 Hz` |
| O8 | `(P/100)^2 * sqrt(W_min/max(W,W_min))` | `>=0.6` | `>=0.4` | `<0.4` |
| O9 | stable-hover 内最大 micro-movement rate | `<1 Hz` | `[1,2) Hz` | `>=2 Hz`；无 stable interval 为 U/null |
| O10 | 最差 disturbance recovery time | `<=5 s` | `<=10 s` | `>10 s`；任一未恢复为 U/null |
| O11 | 最差正确 disturbance response latency | `<=500 ms` | `<=1000 ms` | `>1000 ms`；错误方向/任一 miss 为 U/null |
| O12 | 最差 correct envelope-drift correction latency | `<=300 ms` | `<=800 ms` | `>800 ms`；任一 miss 为 U/null；无越界 N/A |
| O13 | 最大 continuous physio-control coupling loss | `<5%` | `[5,20)%` | `>=20%` |
| H1 | role-weighted gaze-AOI dwell | `>=85%` | `>=70%` | `<70%`；无 dwell 为 U/null |
| H2 | 最差 relevant-AOI first fixation latency | `<=500 ms` | `<=1000 ms` | `>1000 ms`；任一 miss 为 U/null |
| H3 | off-task gaze dwell | `<5%` | `[5,15)%` | `>=15%`；无 dwell 为 U/null |
| H4 | 最差窗口 `abs(signed_delta_HR_pct)` | `<20%` | `[20,40)%` | `>=40%`；RR/baseline 数值退化为 U/null |
| H5 | 最差窗口 `abs(delta_engagement_pct)` | `<=20%` | `(20,50]%` | `>50%`；spectrum/baseline 数值退化为 U/null |

### 5.1 关键算法冻结

- O1 native-rate mask 用 support-aware left-hold 积分：样本 `i` 作用于 `[t_i,t_{i+1})` 与 phase 的交集；segment terminal 只有 explicit semantic end 才延伸，不跨 gap。
- O5/O7 active channels 来自 task profile，不能因飞行员未操纵而动态删除；movement profile 的 100 Hz grid、Butterworth padding、derivative/sign-run/turning-point 与 observed-support denominator 以 M4 规格固定。缺 `W_min` 是 `not_computable`，高 workload 仍是 computed U。
- O6 对 trim 两侧按各自 endpoint piecewise normalization、left-hold time integration，不 clip 超 endpoint 值；不从本次 pilot performance 自动估计 trim，缺 calibration 是 `not_computable`。
- O8 读取 computed O1/O5；即使上游 U 仍继续计算。其 `likelihood_strength=0.50` 由 M5 做重复计数保护，不是质量衰减。
- O9 使用 O1/O4 mask artifact 与 O5 movement profile；无 stable-hover 不是 missing。
- O10/O11/O12/H2 多事件无 miss 时取 worst，任一 miss 否决 session；miss 保存 finite observed wait，不使用 Infinity。
- O11 首个满足幅值/持续门的错误方向动作直接 U，即使后来正确；短 pre-event baseline 使用全部可用前置样本，再回退到显式 neutral/trim config。
- O12 使用同一 baseline fallback；从未出现可信 envelope exit 才是 `not_applicable`。
- H1/H3 对逐 gaze-AOI interval 做时间积分，不以 fixation-only dwell 作分母；AOI taxonomy 必须有覆盖全 viewport 的 `other_scene`，blink/tracking loss 也不从 denominator 删除。H1/H3 在 M5 属于 `gaze_allocation` dependence group，reference strength 各为 0.50。
- H2 的事件起点固定为 task script 的 `cue_available_t`，不能因 pilot 未转头而延后；fixation-v1 默认 I-VT 100 deg/s、100 ms。
- H4 的 packaged default 固定为 `provided_r_peaks_v1`；recompute 必须是显式新 plugin/profile，不运行时自动切换。RR 归属第二个 peak，用 signed delta 供 O13、absolute delta 供 H4。
- H5 默认 3–35 Hz、theta `[4,8)`/alpha `[8,13)`/beta `[13,30]`、4 s/2 s、Welch 2 s/50% overlap、epsilon `1e-12` 和 baseline-window median；不默认 ICA 或删窗。没有配置 role channels/baseline 是 `not_computable`，配置存在但谱退化是 computed U。

### 5.2 O13 `control-physio-grid-v2`

每个 phase 使用 30 s window、5 s step、phase-start alignment，不跨 phase。短于 30 s 的 phase 整段成一窗；尾部未覆盖时增加 phase-end-aligned 30 s 窗口；相同起止窗口去重。

~~~text
qO1,qO5,qO7 = D/A/U -> 1/0.5/0
Q_control = 0.50*qO1 + 0.25*qO5 + 0.25*qO7
activation = clip((signed_delta_HR_pct - 10) / 10, 0, 1)
coupling_loss = 100 * activation * (1 - Q_control)
O13 = max(coupling_loss)
~~~

不设最低窗口数、valid fraction 或 coverage gate。H4 已因 ECG/RR/baseline 数值退化产生 computed U 且无 trace 时，O13 也以 `physio_trace_unavailable` override 产生 computed U；真正缺失 H4 result/artifact 才是 `dependency_missing`。O13 `likelihood_strength=0.50` 由 M5 使用。

## 6. Typed DAG、artifact 与 fingerprint

~~~text
Level 0:
O1 O2 O3 O4 O5 O6 O7 O10 O11 O12 H1 H2 H3 H4 H5

Level 1:
O8  <- O1/O5 result
O9  <- O1/O4 artifact + movement profile
O13 <- O1/O5/O7 algorithm profile + H4 trace
~~~

同 level 可并行，但报告按 canonical catalog order。插件只能读取声明的 aligned views、semantic context 和 typed dependencies。一个节点失败不停止独立节点；真正下游为 `dependency_missing`。

`AnchorArtifactRef` 使用 content hash、schema、grid hash、producer plugin/version、parameter hash 和 dependency fingerprints。插件在独立 staging 写入，合同通过后原子发布；derived artifacts 不回写 Session Bundle。M4 只定义临时/in-memory `DerivedArtifactSink` port，M6 才拥有正式 artifact root 和持久化生命周期。

fingerprint 覆盖 source/synchronization/semantic snapshot、catalog、registry/plugin、parameter/plan、dependency、artifact content 和 canonical result inventory；排除绝对路径、host、wall-clock、线程完成顺序和临时目录。

## 7. 可编辑配置合同

Anchor 配置必须由 JSON Schema 验证，并足以让后端执行、前端解释和专家修改：

~~~yaml
anchor:
  id: O2
  definition_version: 0.2.0
  lifecycle: active
  plugin:
    id: peak_tracking_excursion
    version: 0.2.0
  required_inputs: [X, task_reference, phase_markers]
  typed_dependencies: []
  parameters:
    reference_mode: time_aligned
    axes: [x, y, z]
    norm: l2
    internal_unit: m
    display_unit: ft
  aggregation:
    across_samples: max
    across_phases: max
  scoring:
    scorer_id: hard_threshold_v1
    state_order: [unacceptable, adequate, desired]
    direction: lower_is_better
    desired_max: {value: 2, unit: ft}
    adequate_max: {value: 5, unit: ft}
  missing_policy:
    missing_stream: missing_input
    missing_context: not_computable
~~~

M4 schema 必须拒绝 `quality_gates`、`min_valid_coverage`、`failed_quality`、`binary_quality_v1` 和 v0.2 `invalid_quality`。还必须拒绝 duplicate ID、未知 dependency、DAG cycle、单位不兼容、阈值方向矛盾、不可用 plugin/scorer/schema、越界 artifact recipe 和未版本化算法常量。

前端新增/删除/修改 anchor 时操作的是 ModelBundle draft：

- 新增节点要提供稳定 ID、definition、plugin、parameter schema、binding 和 graph/CPT changes；plugin 未提供时 UI 显示 `plugin_unavailable`，不能伪装成 session 数据问题；
- 删除使用 retire/disable 并发布新 revision，历史定义、插件和结果不物理删除；
- 修改参数创建新 parameter snapshot；
- 修改公式发布新 plugin version；
- 后端原子验证 graph、DAG、schema、CPT 和 version compatibility，再返回 canonical draft。

## 8. 前端展示要求

Anchor 详情页至少显示：

- 名称、说明、lifecycle、plugin/scorer/schema version；
- 声明输入、task/phase applicability 和 typed dependencies；
- 公式、参数、window/grid 和 D/A/U 阈值；
- calculation status、evidence state/likelihood、classification override；
- raw metrics、phase/event breakdown、source windows、computation trace 和 artifact refs；
- model/catalog/parameter/result fingerprints 与 evidence grade；
- 当前连接的 sub-skills，以及编辑/校验/另存 revision/恢复默认操作。

UI 必须把 computed U 显示为有效负面 evidence，不能标成 invalid/missing。Technical diagnostics 可以展开查看，但不得命名为评分质量门。

## 9. 专家校准与科学边界

建议校准顺序：任务/phase/AOI/control 语义 -> anchor 公式与参数 -> D/A/U 阈值 -> graph binding/dependence -> CPT -> assessability threshold。每次修改保存 author、reason、parent revision、structured diff、validation report 和 content hash。

Synthetic multimodal fixtures 只验证软件闭环，始终 `scientific_validation_status=not_supported`。后续真实研究应单独评价 inter-rater agreement、test-retest、criterion validity、posterior calibration、阈值敏感性和跨 pilot/session generalization；这些研究不倒推 M4 过滤极差表现。

## 10. 参考来源边界

- [R1 Perfect et al. 2015](./REFERENCES.md#r1-perfect-et-al-2015)：time-in-bound、discrete movement、W/W_min、TPX 构念。
- [R2 Lu et al. 2016](./REFERENCES.md#r2-lu-et-al-2016)：control RMS、control attack 与 tracking deviation。
- [R3 White and Padfield 2004](./REFERENCES.md#r3-white-and-padfield-2004)：scene point-of-regard、stabilisation、overshoot。
- [R4 Park et al. 2024](./REFERENCES.md#r4-park-et-al-2024)：scene-aware gaze mapping。
- [R5 Wang et al. 2025](./REFERENCES.md#r5-wang-et-al-2025)：R-peaks、HR/HRV 与 subject baseline。
- [R6 van Weelden et al. 2026](./REFERENCES.md#r6-van-weelden-et-al-2026)：EEG band power、engagement ratio 与个体校准。

这些来源支持构念或处理方法，不自动支持本文的工程阈值、O13 组合公式、CPT 或训练合格结论。

## 11. 实现与验收边界

当前只可声称 **18/18 anchors specified，0/18 implemented**。Reference M4 完成至少需要：

1. `AnchorResult` v0.2、catalog/plan/report schemas 和 typed DAG 通过合同测试；
2. 每个 anchor 的手算 D/A/U、精确边界、aggregation、override 和状态 golden；
3. 18/18 computed Desired 紧凑 aligned-input real-plugin workflow；
4. 18/18 computed Unacceptable 紧凑 aligned-input real-plugin workflow，raw availability=100%，M4 无 `invalid_quality`；
5. missing/config/dependency/not-applicable 与 U 不等价；
6. O13 10/30/31/35/36 s 窗口、H1/H3 catch-all、H4/H5 degenerate override 回归；
7. 新增/retire/参数/plugin-version/旧 revision replay 不修改 orchestrator；
8. source/aligned views 不变，artifact/result/evaluation fingerprint 跨进程确定；
9. full tests、schema symmetry、lint/type、build，以及复用唯一 10 秒全模态 bundle 的 fresh-wheel isolated M1→M4 smoke 全部通过；
10. 只有新鲜证据完成 M4-G 后才能把状态改为 M4 engineering-verified。

M4 书面规格、轻量工作流验证修订与 [replacement plan](./plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) 均已批准，D-026/D-027 已接受；原实施计划已被取代且不再提供执行授权。Replacement plan 已从 Task 0 获得实施授权，但 Task 0 尚未开始；在相应完成门通过前仍保持 0/18 implemented。
