# Pilot Assessment Reference Model v0.1

> 文档状态：工程参考模型  
> 模型版本：reference-model-v0.1  
> 日期：2026-07-10  
> 当前锚点集合：O1-O13 + H1-H5，共 18 个 evidence nodes  
> 当前任务：Translation 45 deg -> Deceleration -> Hover stabilization

## 1. 状态边界

本文件定义第一版可运行、可展示、可编辑的系统计算参考模型。它的目的不是宣称已经得到航空认证标准，也不是替代试飞员、飞行品质专家、人因专家或医学专家的判断，而是为后端、Windows 前端和后续专家校准提供一套完整且一致的初始参数。

因此，本模型遵循以下边界：

1. 所有 anchor 定义、阈值、阶段权重、滤波参数、AOI 分类、控制效能映射和证据 CPT 均必须配置化，不得硬编码为不可修改常量。
2. 本文给出的默认值是合理的工程 v0，不是认证限制、医学诊断阈值或最终训练合格标准。
3. 专家未确认不会阻塞第一版实现。系统先使用本文默认值运行，之后由专家通过前端修改参数、保存模型版本并比较结果。
4. Desired、Adequate、Unacceptable 仅表示该 anchor 的观测等级。Missing、Invalid Quality、Not Applicable 和 Not Computable 是计算状态，不是第四种表现等级。
5. 贝叶斯网络只接收通过质量门且计算状态为 computed 的证据。其他状态保留在证据追踪中，但不作为一个伪造的观测状态提交给 BN。
6. 本模型评估的是一次 session 中可观测证据对四类能力的支持程度，不将单一 anchor 或单次 posterior 解释为飞行员永久能力真值。

### 1.1 本版本对旧设计的覆盖

本文件采用当前 18-node 设计，并明确覆盖旧记忆中的不一致版本：

- O2 为 **Peak Tracking Excursion**，不再是 Deceleration Profile Fidelity。
- O4 为 **Sustained Hover Time**，不再是 Sustained Hover Drift。
- H4 为 **ECG Fluctuation**。
- H5 为 **EEG Fluctuation**，不再是 HRV anchor。
- 旧 H6 删除；EEG 直接进入 H5。
- O13 Physio-control Coupling 保留。

## 2. 系统输入与上下文

### 2.1 五类正式输入流

| 符号 | 输入流 | 第一版数据合同 |
|---|---|---|
| X(t) | Flight state | 位置、速度、姿态、角速度、加速度，以及参考轨迹或可用于重建参考轨迹的任务参数 |
| U(t) | Control input | longitudinal/lateral cyclic、collective、pedal；统一归一化为 full travel 比例，同时保留原始单位 |
| I(t) | Visual scene | 飞行员在 VR 中随头部运动实际看到的逐帧场景，不是驾驶员面部图像 |
| G(t) | Eye tracking | 与 I(t) 对齐的 gaze ray、二维 point-of-regard、fixation/saccade 或可重建这些事件的原始眼动数据 |
| P(t) | Physiology | 原始 ECG、EEG 及其设备时间戳、通道信息、采样率和质量标志 |

### 2.2 必需的上下文数据

- phase markers：translation、deceleration、hover；
- reference trajectory 或 phase envelope；
- task target 和 hover target；
- disturbance/critical-event markers；
- dynamic AOI taxonomy；
- control-channel-to-state-axis 映射或局部控制效能矩阵；
- subject ECG/EEG baseline；
- 采样率、设备时钟、时间同步误差和缺失段信息；
- 任务协议要求，例如 required hover duration；
- W_min 的理论值或专家参考值。

### 2.3 全局预处理默认值

这些值同样属于配置：

- 内部计算优先使用 SI 单位；界面可显示 ft、kt、deg。
- 所有流转换到统一 session 时钟，但保留原始时间戳。
- X/U 与事件 marker 的最大允许同步误差默认 50 ms。
- I/G 的最大允许同步误差默认一帧或 33 ms，取较大者。
- ECG/EEG 与任务时钟的最大允许同步误差默认 100 ms。
- 相邻缺失不自动插值超过 200 ms；较长缺失形成显式 gap。
- 所有 anchor 都返回所用数据区间、参数版本和源文件引用。

## 3. BN 能力层级与 18-anchor 映射

### 3.1 四项 aggregate competencies

- TCP：Task Control Proficiency
- PC：Procedural Compliance
- SM：Situational Monitoring
- OC：Operational Composure

### 3.2 11 项 latent sub-skills

| Competency | Sub-skill | Supporting anchors |
|---|---|---|
| TCP | TCP.1 Trajectory Tracking | O1 Phase-state Precision；O2 Peak Tracking Excursion |
| TCP | TCP.2 Maneuver Precision | O3 Terminal Capture Quality；O4 Sustained Hover Time；O2 Peak Tracking Excursion |
| TCP | TCP.3 Control Efficiency | O5 Workload Rate；O6 Control Magnitude RMS；O8 TPX Composite |
| TCP | TCP.4 Control Smoothness | O7 Control Reversal Rate；O9 Dead-band Activity |
| PC | PC.1 Envelope Discipline | O1 Phase-state Precision；O12 Envelope-drift Latency |
| PC | PC.2 Event Response | O11 Disturbance Latency；H1 AOI Dwell |
| SM | SM.1 Reactive Vigilance | O11 Disturbance Latency；O12 Envelope-drift Latency；H2 First Fixation Latency |
| SM | SM.2 Attention Allocation | H1 AOI Dwell；H3 Off-task Dwell |
| OC | OC.1 Disturbance Recovery | O10 Recovery Time |
| OC | OC.2 Stress Resilience | O7 Control Reversal Rate；O13 Physio-control Coupling |
| OC | OC.3 Physio Regulation | H4 ECG Fluctuation；H5 EEG Fluctuation |

O1、O2、O7、O11、O12 和 H1 的共享连接是有意设计的：同一个可观测行为可以同时为不同 latent skill 提供证据。不得为了避免重复而复制或删除这些观测。

## 4. 证据等级

本文对 anchor 的来源强度使用三级标记：

| 等级 | 含义 |
|---|---|
| A | 本地核心论文直接定义了同类指标、公式或计算协议；具体 D/A/U 切点仍可能是项目默认 |
| B | 论文直接支持该测量构念或数据处理方法，但本项目的精确公式、聚合方式或阈值是工程 v0 |
| C | 为保证系统闭环而提出的工程参考定义；与现有构念一致，但尚无核心论文直接验证 |

证据等级不等同于 anchor 在 BN 中的权重。BN 权重由网络结构和 CPT 决定，并由专家单独校准。

## 5. 统一 AnchorResult 契约

所有 extractor 必须返回同一结构。一个 anchor 可以包含多个 raw metrics，但只能产生一个用于当前 18-node BN 的 evidence_state。

~~~yaml
AnchorResult:
  anchor_id: O1
  model_version: reference-model-v0.1
  calculation_status: computed
  evidence_state: adequate
  continuous_score: 0.50
  evidence_likelihood:
    state_order: [unacceptable, adequate, desired]
    values: [0.00, 1.00, 0.00]
  raw_metrics:
    translation_precision_pct: 94.2
    deceleration_precision_pct: 88.1
    hover_precision_pct: 91.0
  primary_value:
    value: 88.1
    unit: percent
  phase_results:
    translation: desired
    deceleration: adequate
    hover: desired
  event_results: []
  source_windows:
    - start_t_ns: 0
      end_t_ns: 29010000000
      phase: session
  derived_artifacts:
    - artifact_id: O1-window-trace
      kind: window_metric_trace
      path: artifacts/anchors/O1_window_trace.parquet
      schema_id: anchor-window-trace-v1
      window_grid_id: control-quality-grid-v1
  quality:
    passed: true
    score: 1.00
    valid_coverage: 0.982
    sync_error_ms: 12
    flags: []
  thresholds_used:
    desired_min: 90
    adequate_min: 70
  parameters_used:
    aggregation: worst_phase
    scoring_transform: hard_threshold_v1
    continuous_score_transform: ordinal_expectation_v1
    quality_transform: binary_quality_v1
    config_version: project-default-v0.1
  dependencies:
    available: [X, phase_markers, phase_envelopes]
    missing: []
  input_status_snapshot:
    X: present
    phase_markers: present
    phase_envelopes: present
  provenance:
    source_files: []
    sample_ranges: []
    extractor_version: 0.1.0
    evidence_grade: B
  diagnostics: []
~~~

computed 结果必须提供 canonical state order 下的 evidence_likelihood。reference-v0.1 默认使用 hard_threshold_v1，按本文件 D/A/U 边界输出 one-hot likelihood；不会由不同开发者自行发明阈值附近插值。若专家启用 soft scorer，必须在 model bundle 中给出独立 schema、算法名、版本、全部 transition 参数和 golden tests。

continuous_score 统一定义为 [0,1] 且越高越理想，便于 O13、排序和可视化；它不能替代带单位的 raw_metrics。默认 ordinal_expectation_v1：

continuous_score = (P(adequate) + 2 × P(desired)) / 2

因此 hard Unacceptable/Adequate/Desired 分别为 0/0.5/1；soft likelihood 得到确定的期望 rank。evidence_state 取 scorer 输出的主类别，reference 默认即 hard threshold 类别。BN 实际使用 likelihood，并再按 quality 向均匀分布收缩。

quality.score 也必须在 [0,1]。reference-v0.1 默认锁定 binary_quality_v1：所有 hard quality gates 通过时 passed=true、score=1；任一 hard gate 失败时 passed=false、calculation_status=invalid_quality 且 observation omitted。若专家以后启用 graded quality scorer，必须在 model bundle 中版本化公式、参数、golden tests 和适用 anchor；此时 passed=true 且 score<1 才按 [05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md](05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md) 的公式生成 virtual evidence。

window_metric_trace 等大型逐窗数据通过相对于 managed run artifact root 的受管路径引用，不内嵌在 RPC，也不回写原始 session bundle。任何 windowed anchor 都必须记录 window_length_s、step_s、alignment、min_valid_fraction、partial_window_policy 和 window_grid_id。

aligned-state-grid-v1 是同步后、按 t_ns 严格递增的有效 X(t) sample grid；不强制改成均匀采样。共享 mask 必须使用完全相同的 t_ns 列和 grid hash，gap/invalid rows 以 sample_valid=false 保留，不能跨 gap 伪造状态。

### 5.1 calculation_status 枚举

| 状态 | 含义 | BN 处理 |
|---|---|---|
| computed | 通过质量门并成功计算 | 提交 evidence_state |
| invalid_quality | 数据存在但质量不足 | 不提交观测 |
| missing_input | 必需流缺失 | 不提交观测 |
| not_applicable | 本 session 没有相关事件或阶段 | 不提交观测 |
| not_computable | 参数、参考曲线或映射不足 | 不提交观测 |
| dependency_missing | 上游 anchor 未计算或质量不足 | 不提交观测 |
| extractor_error | 提取器异常 | 不提交观测并返回结构化错误 |

Session stream 状态与 AnchorResult 的映射固定如下，避免把数据生命周期状态混入 BN：

| Session stream 状态 | AnchorResult 处理 | BN 处理 |
|---|---|---|
| present | 正常计算；仍可能因质量门变为 invalid_quality | computed 时提交 D/A/U |
| export_pending | missing_input，并在 input_status_snapshot/diagnostics 保留 source_export_pending | 不提交观测 |
| missing | missing_input，并记录缺失字段或文件 | 不提交观测 |
| invalid | invalid_quality，并保留 validation issue | 不提交观测 |
| not_applicable | not_applicable | 不提交观测 |

BN 层只接收 computed 的 D/A/U 或由其质量生成的 virtual evidence；其他状态只进入 coverage、diagnostics 和 provenance。

## 6. 18 个 anchor 的 reference v0.1

### 6.1 O1 Phase-state Precision

- **输入**：X(t)、phase markers、每阶段 desired envelope。
- **阶段**：Translation、Deceleration、Hover，分别计算。
- **算法**：

  对阶段 p，定义：

  P_p = 100 × 有效采样时间中 X(t) 位于阶段 p 的多轴 desired envelope 内的时长 / 阶段 p 的有效时长。

  多轴 envelope 可包含位置、速度、航向、姿态和高度约束。每阶段保留 P_T、P_D、P_H。reference-v0.1 的 primary_value 明确取所有有效 phase 的 min(P_p)。18-node BN 中只保留一个 O1 节点，默认聚合方式为 worst_phase：所有可用阶段均为 Desired 才输出 Desired；任一阶段为 Unacceptable 则输出 Unacceptable；其他情况输出 Adequate。

- **输出**：每阶段 precision percent、总体 evidence_state，以及 O1_desired_envelope_mask artifact。Mask 使用 aligned-state-grid-v1，字段至少为 t_ns、phase_id、sample_valid、inside_desired_envelope 和 envelope_version。
- **默认阈值**：Desired ≥90%；Adequate ≥70%；Unacceptable <70%。
- **质量门**：每阶段有效覆盖率 ≥95%；阶段持续时间 ≥2 s；envelope 必须有版本号。
- **缺失策略**：task profile 先声明 required 与 optional/applicable phases。required phase 缺失时为 missing_input 并 omit；optional 或 not_applicable phase 不参与 min/worst 聚合。不得把缺失阶段评为 Unacceptable。reference-v0.1 的 binary quality 不使用含糊的“降一点 quality”。
- **证据等级**：B。Perfect 2015 PDF p10 对每个 performance requirement 分别计算 time-in-bound 百分比后再聚合；本设计改为“同一时刻满足多轴联合 envelope”，再按 phase 取 min/worst。time-in-bound 构念有直接依据，但联合包线、phase 拆分和 worst-phase 均是可配置工程改写，不声称为论文原公式。

### 6.2 O2 Peak Tracking Excursion

- **输入**：X(t)、reference trajectory 或 reference path、phase markers。
- **阶段**：T/D/H 均可计算，并保留 phase breakdown。
- **算法**：

  默认 time-aligned 模式：

  e(t) = norm(position(t) - position_ref(t))

  E_peak = max e(t)

  允许专家将 reference_mode 改为 nearest-path，或选择参与计算的轴。所有参与范数的通道必须转换到同一长度单位。默认使用三维位置欧氏距离；若任务只定义水平轨迹，可仅使用水平 cross-track error。

- **输出**：peak excursion，默认显示 ft；同时输出各轴峰值和发生时间。
- **默认阈值**：Desired ≤2 ft；Adequate ≤5 ft；Unacceptable >5 ft。
- **质量门**：reference 与 X 的重叠覆盖率 ≥95%；参考轨迹不可跨越未定义段；坐标系转换已验证。
- **缺失策略**：无 reference trajectory/path 时 not_computable。
- **证据等级**：B。Lu 2016 PDF p12 直接使用速度和位置 tracking deviation；peak 聚合和 2/5 ft 阈值来自当前项目工程设计。

### 6.3 O3 Terminal Capture Quality

- **输入**：X(t)、hover target、D→H 边界、hover desired envelope、settling_start_mode。
- **阶段**：Deceleration 到 Hover 的过渡。
- **算法**：

  1. overshoot_ft：沿到达轴越过 hover target 的最大正向距离；没有越过则为 0。
  2. settling_time_s：reference-v0.1 的 settling_start_mode 固定默认 phase_boundary，即从 annotations 中唯一的 D→H 边界开始，到状态进入 hover desired envelope 并连续保持至少 2 s 的时间。
  3. 专家可以改用 capture_region_entry，但 task profile 必须给出有版本的 terminal capture region 几何定义和首次进入规则；未显式选择时不得自动回退到该模式。
  4. evidence_state 使用两个条件的合取规则。

- **输出**：overshoot_ft、settling_time_s。
- **默认阈值**：
  - Desired：overshoot ≤2 ft 且 settling time ≤3 s；
  - Adequate：overshoot ≤5 ft 且 settling time ≤5 s；
  - 其他为 Unacceptable。
- **质量门**：target、到达轴方向和 D→H 边界已定义；边界前后数据各 ≥2 s。
- **缺失策略**：无 target 或无 D→H 定义时 not_computable。只有 task completion/termination marker 证明一次完整尝试已经结束、且 terminal capture 所需观察窗完整有效时，“未到达/未捕获”才是 computed + Unacceptable；EOF、文件截断、sidecar crash 或尾部 coverage 不足返回 invalid_quality/missing_input，不惩罚为表现差。
- **证据等级**：B。White 2004 PDF p12 明确记录 maximum overshoot 和 stabilisation time；具体合取规则和阈值为工程 v0。

### 6.4 O4 Sustained Hover Time

- **输入**：X(t)、hover desired envelope、hover target、phase markers。
- **阶段**：Hover。
- **算法**：

  从首次满足稳定条件后开始，寻找同时满足以下条件的最长连续区间：

  - 状态位于 hover desired envelope；
  - 速度和角速度低于配置门槛；
  - 数据质量有效。

  默认允许填补最长 0.2 s 的瞬时缺口，但原始 gap 必须保留。

- **输出**：longest_sustained_hover_s，以及 O4_stable_hover_mask artifact。Mask 与 O1 使用同一 aligned-state-grid-v1，字段至少为 t_ns、stable_hover、gap_filled 和 rule_version。
- **默认阈值**：Desired ≥10 s；Adequate ≥5 s；Unacceptable <5 s。
- **协议覆盖**：若任务协议给出 required_hold_s，则 Desired 使用 required_hold_s，Adequate 默认使用其 50%，但不得低于专家规定的最低时长。
- **质量门**：Hover 阶段存在；可用 hover 数据 ≥5 s；envelope 与低速门槛已定义。
- **缺失策略**：任务包含 Hover、完整 hover 观察窗和 completion marker 均存在但未形成持续悬停时为 computed + Unacceptable；Hover 阶段未记录或尾部截断则 missing_input/invalid_quality。
- **证据等级**：B。White 2004 PDF p12 的 bob-up 要求稳定 5 s；Perfect 2015 PDF p11 的 W_min 示例采用 stable hover period。10 s 为工程默认。

### 6.5 O5 Workload Rate

- **输入**：U(t)、active channel list、task duration、W_min。
- **阶段**：全程计算，并提供 T/D/H breakdown。
- **算法**：

  对每个 active control channel：

  1. 统一为 fraction of full travel；把 gap >50 ms 切成独立有效 segment，不跨 gap 计 movement。
  2. 每个 segment 线性重采样到 detector_rate_hz=100；只允许跨原始 gap ≤50 ms 插值。
  3. 使用 zero-phase 4th-order Butterworth low-pass，cutoff_hz=5。有效原始采样率 <20 Hz 时 invalid_quality。
  4. 在均匀时间网格上用 central difference 估计 du/dt。rate_deadband=0.5% full travel/s：大于该值记 +1，小于负值记 -1，其余记 0。
  5. 非零 sign run 必须持续 ≥50 ms；更短 run 视为噪声并并入相邻 zero plateau。
  6. 当确认的 +1 与 -1 sign run 交替时，在两者之间选取 filtered u 的唯一极值作为 zero-velocity turning point；并列 plateau 取时间中点。Segment 首尾不作为 turning point。
  7. 相邻确认 turning points 构成一个 candidate movement；只有两点控制位移差 ≥0.5% full travel 才计入 N_c。
  8. W_c=N_c/T_valid,c，其中 T_valid,c 是该通道所有可用 segments 的总时长；W 为 active channels 的 W_c 算术平均。

  当前单轴 longitudinal session 不得把始终不活动的其他轴纳入平均，否则会人为降低 W。

- **输出**：W，单位 s^-1；W_over_Wmin。
- **默认阈值**：Desired W/W_min ≤2；Adequate ≤4；Unacceptable >4。
- **W_min 来源优先级**：
  1. 任务脚本理论最少控制次数 / 任务时长；
  2. 专家确认的 reference session；
  3. 合格专家样本的低分位数；
  4. 均不存在时 not_computable，不得假设 W_min=1。
- **质量门**：至少一个 active channel；U 有效覆盖率 ≥95%；W_min >0。
- **缺失策略**：U 缺失为 missing_input；W_min 缺失为 not_computable。
- **证据等级**：A。Perfect 2015 PDF p10 直接定义 zero-control-velocity points 间的 discrete movement、0.5% 防噪门槛和 W；p11 定义 W_min。上述重采样、滤波、deadband 和去抖是为数字实现唯一性增加的工程参数。

### 6.6 O6 Control Magnitude RMS

- **输入**：U(t)、trim/neutral values、active channel weights。
- **阶段**：全程及 T/D/H。
- **算法**：

  RMS_u = 100 × sqrt(sum over c of w_c × mean((u_c - trim_c)^2))

  其中 u_c 以 neutral=0、任一方向机械端点绝对值=1 归一化（percent full deflection 语义），权重之和为 1；设备若只给 [0,1] 必须先用校准的 neutral/endpoints 转换。

- **输出**：RMS_u，单位 % full travel；各通道 RMS。
- **默认阈值**：Desired ≤30%；Adequate ≤50%；Unacceptable >50%。
- **质量门**：trim/neutral 定义存在；至少一个 active channel；有效覆盖率 ≥95%。
- **缺失策略**：无 trim 时允许使用任务开始前稳定窗估计，但必须标记 estimated_trim；无法估计则 not_computable。
- **证据等级**：B。Lu 2016 PDF p11 直接分析 longitudinal 和 collective RMS；30/50% 为工程默认。

### 6.7 O7 Control Reversal Rate

- **输入**：U(t)、active channel list。
- **阶段**：全程及 T/D/H。
- **算法**：

  复用 O5 的 segment、100 Hz 重采样、5 Hz zero-phase filter、central-difference derivative、rate deadband 和 50 ms sign-run 去抖。对确认 turning points 的方向交替计算有效反转；只有相邻峰谷幅度 ≥2% full travel 且事件间隔 ≥0.15 s 才计数。每通道：

  CRR_c = reversal_count_c / valid_duration

  节点主值默认取 max(CRR_c)，避免某一振荡通道被其他平稳通道平均掩盖。

- **输出**：各通道 CRR 和 max_channel_hz，单位 Hz。
- **默认阈值**：Desired <2 Hz；Adequate <4 Hz；Unacceptable ≥4 Hz。
- **质量门**：U 采样率 ≥20 Hz；有效覆盖率 ≥95%；滤波器不会抹除 4 Hz 附近活动。
- **缺失策略**：U 缺失为 missing_input。
- **证据等级**：B。Perfect 2015 PDF p8 支持 PIO/oscillation 构念；Lu 2016 PDF p11 使用 >2% full travel 的 control attack；反转算法和阈值为工程 v0。

### 6.8 O8 TPX Composite

- **输入**：O1 的 session primary_value P=min(valid P_p)、O5 的同一 task interval W 和 W_min。
- **阶段**：默认 session aggregate；可提供 phase TPX diagnostics。
- **算法**：

  TPX = (P / 100)^2 × sqrt(W_min / max(W, W_min))

  默认限制到 [0,1]，避免由于检测噪声导致 W < W_min 时产生大于 1 的值。

- **输出**：dimensionless TPX。
- **默认阈值**：Desired ≥0.6；Adequate ≥0.4；Unacceptable <0.4。
- **质量门**：O1 与 O5 均为 computed；W_min >0；两者使用相同任务区间。
- **缺失策略**：任一依赖不可用时 dependency_missing，不单独猜测。
- **证据等级**：A。Perfect 2015 PDF p11 Eq. 6 直接给出 TPX，并报告 209 个测试点、13 名参与者中 TPX 与 TLX 的拟合 R²=0.988；0.6/0.4 为项目阈值。

### 6.9 O9 Dead-band Activity

- **输入**：U(t)、O1_desired_envelope_mask、O4_stable_hover_mask；显式 upstream dependencies=[O1,O4]。
- **阶段**：Hover。
- **算法**：

  后端先按 t_ns 在 aligned-state-grid-v1 上对两个 mask 做逻辑交集，再把 U 以 nearest-within-20-ms 对齐；不跨 gap 插值。只在 stable_hover=true、inside_desired_envelope=true、sample_valid=true 的片段中，使用 O5 相同的 movement detector，统计幅度位于 0.5%-5% full travel 的微小修正：

  DBA_c = micro_movement_count_c / valid_stable_hover_duration

  主值默认取 max(DBA_c)。

- **输出**：dead-band activity，Hz。
- **默认阈值**：Desired <1 Hz；Adequate <2 Hz；Unacceptable ≥2 Hz。
- **质量门**：两个 mask schema/grid/version 可解析；有效交集 hover ≥5 s；U 覆盖率 ≥95%；mask-U 最大匹配误差 ≤20 ms。
- **缺失策略**：无稳定 hover 时，只有任务 completion marker 与完整 hover 观察窗证明尝试完整，才是 computed + Unacceptable 并记录 no_stable_hover；Hover 数据缺失或截断则 missing_input/invalid_quality。
- **证据等级**：C。由 Perfect 的 discrete movement 方法派生；微输入范围与阈值为工程参考值。

### 6.10 O10 Recovery Time

- **输入**：X(t)、recovery_start_mode、desired envelope，以及所选模式需要的 disturbance marker 或 versioned adequate envelope。
- **阶段**：事件驱动，主要用于 D/H。
- **算法**：

  recovery_start_mode 必须由 task profile 唯一指定：

  - reference 默认 event_marker_v1：t_start 是 scripted disturbance marker 的 onset；marker 缺失时 not_computable，不自动改用 detector；
  - 可选 envelope_exit_v1：task profile 必须提供 versioned adequate envelope；t_start 是状态连续 ≥100 ms 位于 adequate envelope 之外的首次时刻。

  对每个由所选模式产生的事件 e：

  recovery_time_e = 从 t_start 到重新进入 desired envelope并连续保持至少 2 s 的时间。

  保留逐事件结果，节点主值默认取 worst event；可配置为 p90。

- **输出**：recovery time，s；unrecovered event count。
- **默认阈值**：Desired ≤5 s；Adequate ≤10 s；Unacceptable >10 s，或在任务 profile 定义的完整 post-event horizon 内仍未恢复。
- **质量门**：start mode 和所需 marker/envelope 可追溯；事件后的 required_post_event_s 完整有效且有 completion/termination 语义；desired envelope 已定义。
- **缺失策略**：session 中没有设计扰动/有效 excursion 时 not_applicable；不得自动评为 Desired。
- **证据等级**：C。recovery/stabilisation 构念合理，但该事件公式和阈值尚无核心论文直接验证。

### 6.11 O11 Disturbance Latency

- **输入**：U(t)、scripted disturbance marker、event_response_mapping。
- **阶段**：事件驱动。
- **算法**：

  对事件 e，event_response_mapping 必须给出 expected_channels、每通道允许方向（positive/negative/either）和 response_aggregation。reference 默认：

  1. 每通道统一为 percent full deflection，并使用仅依赖当前/过去样本的 20 ms causal median filter；
  2. baseline_c 为 disturbance onset 前完整 1 s 的 filtered control median；
  3. qualifying response 是映射内通道相对 baseline_c 的有符号变化超过 5% full deflection，方向匹配并持续 ≥100 ms；
  4. response_aggregation=earliest_any_mapped：latency_e 为任一映射通道首次 qualifying onset 减 disturbance onset。若专家要求 all_mapped，必须显式更改 profile。

  未映射通道或错误方向变化不计为响应。

  missed response 记为 infinity。节点主值默认取 p90；事件数少于 5 时取 worst event。

- **输出**：latency_ms、miss_count。
- **默认阈值**：Desired ≤500 ms；Adequate ≤1000 ms；Unacceptable >1000 ms，或在完整 response horizon 内确认 miss。
- **质量门**：事件 marker 和 response mapping 有效；marker-U 同步误差 ≤50 ms；事件前有完整 1 s baseline；事件后 response horizon 完整有效。截断窗口返回 invalid_quality，不记 miss。
- **缺失策略**：无扰动事件时 not_applicable；marker 或 response mapping 缺失时 not_computable。
- **证据等级**：C。为事件响应链设计的工程默认。

### 6.12 O12 Envelope-drift Latency

- **输入**：X(t)、U(t)、desired envelope、axis-channel sign map 或 local control-effect matrix。
- **阶段**：T/D/H，事件驱动。
- **算法**：

  1. 检测状态连续 ≥100 ms 离开 desired envelope 的首次时刻 t_exit；
  2. 对 U 使用 O11 相同的 percent-full-deflection 转换和 20 ms causal median filter；每通道 baseline_c 取 t_exit 前完整 1 s 中位数；
  3. 根据有符号状态误差和 axis-channel sign map/control-effect matrix，确定能减小误差的 mapped channels 与 corrective direction；
  4. qualifying corrective input 必须相对 baseline_c 沿 corrective direction 超过 5% full deflection，并持续 ≥100 ms；
  5. reference aggregation=earliest_any_mapped：latency 是首个 qualifying mapped-channel onset 减 t_exit。其他聚合必须在 task profile 显式声明。

  不允许将任意控制反转都当作正确响应。多次有效越界时保留逐事件 latency；事件数少于 5 时节点主值取 worst event，事件数达到 5 时默认取 p90。

- **输出**：latency_ms、逐轴结果、miss_count。
- **默认阈值**：Desired ≤300 ms；Adequate ≤800 ms；Unacceptable >800 ms，或在完整 correction horizon 内确认 miss。
- **质量门**：X/U 同步误差 ≤50 ms；控制效能方向映射存在；t_exit 前有完整 1 s baseline；越界后的 correction horizon 完整有效。截断窗口返回 invalid_quality。
- **缺失策略**：没有 envelope exit 时 not_applicable；缺少效能方向映射时 not_computable。
- **证据等级**：C。工程参考定义。

### 6.13 O13 Physio-control Coupling

- **输入**：X(t)、U(t)、ECG、O1/O5/O7 参数与 H4 window trace、phase context。
- **阶段**：同阶段匹配后跨窗口比较。
- **算法**：

  1. 复用 H4 的 control-physio-grid-v1：window_length_s=30、step_s=5、alignment=phase_start、min_valid_fraction=0.80、partial_window_policy=drop。不得把 session 级 O1/O5/O7 单值复制到每个窗口。
  2. 在每个 window_id 内，用 O1/O5/O7 的同版本算法分别重算 window precision、workload rate 和 reversal rate，并按各自 hard_threshold_v1 + ordinal_expectation_v1 得到 qO1_w、qO5_w、qO7_w。O5 使用同一 task profile 的 W_min。
  3. 默认窗口控制质量：

     Q_w = 0.50 × qO1_w + 0.25 × qO5_w + 0.25 × qO7_w

  4. 按 window_id 和 phase 与 H4 trace 一对一 join。activation_mode 必须唯一选择，不能把绝对阈值与分位数用 OR 混合：
     - reference 默认 absolute_v1：high 为 ECG fluctuation ≥20%，baseline 为 <10%，中间窗口不用；
     - 可选 subject_phase_quantile_v1：在同一 subject、同一 phase 的有效 H4 task windows（至少 20 个）上计算 P50/P80，high 为 >P80，baseline 为 ≤P50；要求 P80-P50 ≥1 percentage point，否则 not_applicable。
     两组 window_id 必须不相交，所用 mode、总体、阈值和样本数写入 provenance。
  5. 只比较相同 phase：

     degradation_pct = 100 × max(0, 1 - median(Q_high) / median(Q_baseline))

  每个 phase 分别计算；节点主值取所有满足质量门 phase 中最大的 degradation_pct，以避免跨 phase 基线差异被平均掩盖。

- **输出**：degradation_pct、joined window trace artifact、high/base window counts、unique coverage 和各 phase degradation。
- **默认阈值**：Desired <5%；Adequate <20%；Unacceptable ≥20%。
- **质量门**：同一 phase 的 high 和 baseline 各至少 3 个有效 joined windows，且各自 unique temporal coverage ≥30 s；median(Q_baseline) ≥0.05；O1/O5/O7/H4 window algorithms 和 W_min 均可用。
- **缺失策略**：没有形成 high-activation 对照条件时 not_applicable，不评为 Desired；存在对照但覆盖不足时 invalid_quality；median(Q_baseline)<0.05 时 not_computable，因为“从已接近零的控制质量继续退化”无稳定比率；依赖或 trace 缺失时 dependency_missing。
- **证据等级**：C。构成指标分别有文献支持，但该显式跨模态耦合公式为本项目工程 v0。

### 6.14 H1 AOI Dwell

- **输入**：I(t)、G(t) raw gaze、fixation-v1 artifact、head pose、dynamic AOI map、phase context。
- **阶段**：T/D/H，分别计算并聚合。
- **算法**：

  每帧将 gaze ray 或 point-of-regard 投影到飞行员当时看到的 VR scene。根据阶段和任务状态，将 fixation 分配到 Primary、Secondary、Off-task 或 Unmapped：

  R_AOI = 100 × (Primary + Secondary fixation dwell) / valid fixation dwell

  默认 Primary 和 Secondary 等权；专家可配置 AOI 权重。Session 节点主值通过所有适用 phase 的有效 fixation 时长先合并分子与分母后计算，不平均各 phase 百分比；phase breakdown 单独保留。

- **输出**：R_AOI percent、各 AOI dwell、各 phase breakdown。
- **默认阈值**：Desired ≥85%；Adequate ≥70%；Unacceptable <70%。
- **质量门**：fixation detector/version 与 fixation-v1 schema 可解析；valid gaze coverage ≥70%；total valid fixation dwell >0；scene-gaze 对齐通过；AOI map 覆盖有效场景；Unmapped 与 tracking loss 不计为 Off-task。分母为 0 时 invalid_quality，不执行除法。
- **缺失策略**：I 或 G 缺失为 missing_input；AOI taxonomy 缺失为 not_computable。
- **证据等级**：B。White 2004 PDF pp.2-3 支持 calibrated scene point-of-regard 与 gaze-overlay；Park VTOL 工作 PDF pp.4-5 支持 gaze-to-scene semantic mapping；阈值为项目 v0。

### 6.15 H2 First Fixation Latency

- **输入**：I(t)、G(t) raw gaze、fixation-v1 artifact、critical-event marker、event-relevant AOI。
- **阶段**：事件驱动。
- **算法**：

  latency_e = event/cue 首次对飞行员可见，到 relevant AOI 上第一个持续 ≥100 ms fixation onset 的时间。

  missed fixation 记为 infinity。节点默认取 p90；事件数少于 5 时取 worst event。

- **输出**：latency_ms、miss_count、逐事件 AOI。
- **默认阈值**：Desired ≤500 ms；Adequate ≤1000 ms；Unacceptable >1000 ms，或在完整 fixation horizon 内确认 miss。
- **质量门**：fixation detector/version 与 fixation-v1 schema 可解析；事件可见时刻已定义；完整 fixation horizon 的 gaze coverage ≥70%；I/G 同步误差在允许范围。截断窗口返回 invalid_quality。
- **缺失策略**：没有 critical event 时 not_applicable；事件存在但 AOI 未定义时 not_computable。
- **证据等级**：B。眼动和动态 scene mapping 有方法支持；fixation duration 与阈值为工程 v0。

### 6.16 H3 Off-task Dwell

- **输入**：I(t)、G(t) raw gaze、fixation-v1 artifact、dynamic AOI taxonomy。
- **阶段**：T/D/H。
- **算法**：

  OffTaskDwell = 100 × off-task fixation dwell / valid fixation dwell

  Off-task 必须由阶段化 AOI taxonomy 明确定义。tracking loss、blink 和 Unmapped 单独进入质量指标，不自动计为 off-task。Session 节点主值通过所有适用 phase 的有效 fixation 时长先合并分子与分母后计算，不平均各 phase 百分比；phase breakdown 单独保留。

- **输出**：off_task_dwell_pct、各 phase/AOI breakdown。
- **默认阈值**：Desired <5%；Adequate <15%；Unacceptable ≥15%。
- **质量门**：fixation detector/version 与 fixation-v1 schema 可解析；valid gaze coverage ≥70%；total valid fixation dwell >0；AOI taxonomy 版本存在；I/G 对齐通过。分母为 0 时 invalid_quality，不执行除法。
- **缺失策略**：I/G 缺失为 missing_input；AOI taxonomy 缺失为 not_computable。
- **证据等级**：B。scene-aware gaze 处理有直接方法支持；off-task 分类和阈值为工程 v0。

### 6.17 H4 ECG Fluctuation

- **输入**：raw ECG、subject baseline、phase markers。
- **阶段**：T/D/H，并计算 session aggregate。
- **算法**：

  1. ECG 去噪、R-peak 检测、异常 beat 与 artifact 标记；
  2. 使用 control-physio-grid-v1：window_length_s=30、step_s=5、alignment=phase_start、min_valid_fraction=0.80、partial_window_policy=drop；
  3. baseline HR0 取基线期有效 HR 中位数；
  4. 每窗：

     delta_HR_pct = 100 × max(0, median(HR_window) / HR0 - 1)

  5. 节点主值默认取有效窗口的 p90。

  同时输出 RMSSD、SDNN、pNN20、LF/HF、SD2/SD1 等 diagnostics，但 reference v0.1 不将它们混入 D/A/U 主评分，以免在没有专家权重时制造不可解释复合指标。

- **输出**：ECG fluctuation percent、window trace、HR/HRV diagnostics。
- **默认阈值**：Desired <20%；Adequate <40%；Unacceptable ≥40%。
- **质量门**：
  - 最低 baseline 60 s，推荐 300 s；
  - 有效 R-peak/beat 比例 ≥90%；
  - HR 生理范围默认 35-220 bpm，超出只作为质量警报，不做医学诊断；
  - 有效 task window coverage ≥70%。
- **缺失策略**：无 ECG 或 baseline 为 missing_input；质量不足为 invalid_quality。
- **证据等级**：B。Wang 2025 PDF pp.7-9 支持 R-wave 检测、HR/HRV 特征和 5 min subject baseline；20/40% 是项目初始阈值。

### 6.18 H5 EEG Fluctuation

- **输入**：raw multichannel EEG、subject baseline、channel map、phase markers。
- **阶段**：T/D/H，并计算 session aggregate。
- **算法**：

  1. 默认 band-pass 3-35 Hz、50 Hz notch、ICA/等效 artifact rejection；
  2. 使用 eeg-engagement-grid-v1：window_length_s=4、step_s=2、alignment=phase_start、min_valid_fraction=0.80、partial_window_policy=drop；
  3. 每窗每通道使用 Welch PSD：Hann、segment_length_s=2、overlap=50%。cold-start 频带固定为 theta=[4,8) Hz、alpha=[8,13) Hz、beta=[13,30] Hz；若使用 individual alpha frequency，必须发布新的 band profile 和边界。
  4. channel_selection_mode 默认 task_profile_then_all_eeg：优先使用 task profile 的 engagement_channels；未提供时使用 metadata.role=eeg 且不属于 reference/EOG/auxiliary 的全部通道。
  5. 每个有效通道计算 E_c=beta_c/(alpha_c+theta_c)；每窗 E_window 取所有有效 selected channels 的 median，不按通道任意挑选或平均。
  6. 对 subject baseline 使用同一 channel set、PSD 和聚合规则得到 E0；
  7. 每窗计算：

     delta_E_pct = 100 × (E_window / E0 - 1)

  8. 每个 phase 的主值取有效 window 的 median(delta_E_pct)，并保留 window/channel trace；session 主值默认取各有效 phase 中 absolute deviation 最大者。
  9. 默认先在专家正确完成任务的 cohort 中，为上述 phase-level 主值建立 phase-specific reference band：
     - Desired：P30-P80；
     - Adequate：P10-P90；
     - 其外为 Unacceptable。

  Cohort 模式对每个有效 phase 分类，session evidence 取 worst valid phase。若还没有 cohort，cold-start 对 session 主值的 absolute delta 使用：
  - Desired：|delta_E| ≤20%；
  - Adequate：|delta_E| ≤50%；
  - Unacceptable：>50%。

- **输出**：engagement ratio、delta_E_pct、band powers、channel/phase breakdown。
- **质量门**：
  - 最低 baseline 60 s；
  - 有效 EEG window coverage ≥70%；
  - artifact rejection 后每窗有效通道比例 ≥70%；
  - 每通道 alpha+theta ≥ band_power_epsilon（默认 1e-12，使用实际 PSD power units）；
  - baseline E0 必须 finite 且 > engagement_epsilon=1e-6；
  - VR 头动和眼动伪迹必须进入 quality flags。
- **缺失策略**：无 EEG 或 baseline 为 missing_input；artifact 过多、band-power denominator 不稳定、E0 非有限或 ≤engagement_epsilon 时为 invalid_quality，不执行比值。
- **证据等级**：B。van Weelden 等本地 VR flight EEG 文献 PDF p2 直接采用 beta/(alpha+theta)，p8 强调 pilot-specific calibration/individual alpha frequency；分位区间与 cold-start 阈值为工程 v0。

## 7. 参数配置 schema

每个 anchor 的配置必须足以让后端执行、前端解释并允许专家修改。建议 schema：

~~~yaml
anchor:
  id: O2
  version: 0.1.0
  label: Peak Tracking Excursion
  category: objective
  enabled: true
  editable: true

  input_streams: [X]
  contexts: [phase_markers, reference_trajectory]
  phase_scope: [translation, deceleration, hover]
  dependencies: []

  extractor:
    type: peak_tracking_excursion
    parameters:
      reference_mode: time_aligned
      axes: [x, y, z]
      norm: l2
      internal_unit: m
      display_unit: ft

  aggregation:
    across_samples: max
    across_phases: max
    across_events: worst

  quality_gates:
    transform: binary_quality_v1
    min_valid_coverage: 0.95
    max_sync_error_ms: 50
    require_reference: true

  scoring:
    states: [unacceptable, adequate, desired]
    evaluation_priority: [desired, adequate, unacceptable]
    transform: hard_threshold_v1
    continuous_score_transform: ordinal_expectation_v1
    direction: lower_is_better
    desired:
      operator: less_than_or_equal
      value: 2
      unit: ft
    adequate:
      operator: less_than_or_equal
      value: 5
      unit: ft

  missing_policy:
    missing_stream: missing_input
    missing_context: not_computable
    failed_quality: invalid_quality
    bn_observation: omit

  provenance:
    evidence_grade: B
    source_ids: [S2, S4]
    rationale: Tracking-deviation construct with project peak threshold.
~~~

### 7.1 配置校验

后端必须拒绝以下修改：

- Desired/Adequate 区间方向矛盾；
- 单位不兼容；
- 权重不归一且没有显式允许；
- 依赖形成环；
- 引用不存在的 phase、stream、AOI 或 control channel；
- lower-is-better 的 Desired 阈值比 Adequate 更宽；
- higher-is-better 的 Desired 阈值比 Adequate 更低；
- CPT 概率不在 [0,1]，或每个 parent-state combination 对应的 child-state 概率行和不为 1。

阈值编辑与 CPT 编辑应分别版本化。修改 anchor 阈值不应静默重写 CPT；前端需要提示模型已发生语义变更并建议重新校准。

## 8. 专家校准机制

### 8.1 校准优先级

1. 任务协议或安全边界；
2. 试飞员/教员明确给出的 Desired/Adequate 标准；
3. 成功完成任务的专家 reference sessions；
4. 本文件的 cold-start 工程默认值。

### 8.2 从专家数据生成阈值

在有足够专家成功 session 后，可生成建议值，但不能自动覆盖人工确认值：

- lower-is-better：
  - Desired 候选 = 专家成功样本 P75；
  - Adequate 候选 = P95。
- higher-is-better：
  - Desired 候选 = P25；
  - Adequate 候选 = P05。
- two-sided/band 指标：
  - Desired 候选 = P30-P80；
  - Adequate 候选 = P10-P90。

所有经验阈值应按 task、phase、vehicle configuration、sensor configuration 和必要的 subject normalization 分层。样本量不足时不生成伪精确分位数。

### 8.3 校准审计

每次专家修改至少记录：

- 参数旧值和新值；
- 修改者、时间和理由；
- 引用的论文、任务协议或 reference dataset；
- 受影响的 anchor、sub-skill、competency 和 CPT；
- 新旧模型在固定 golden sessions 上的差异；
- 是否通过 schema、单元测试和回归测试；
- 模型版本号和可回滚快照。

### 8.4 CPT 与 anchor 的职责边界

- Anchor extractor：把原始 session 转换为透明、可复算的观测和 D/A/U evidence。
- Anchor thresholds：定义观测如何量化为 evidence state。
- BN topology：定义哪些 latent skills 可能生成哪些 evidence。
- CPT：定义在给定 latent state 下观察到各 evidence state 的概率。

专家可以独立修改这四层，但每次修改都必须生成新版本，不能覆盖 packaged defaults。

## 9. 前端展示要求

每个 anchor 节点的详情页至少显示：

- 名称、说明、输入流和适用阶段；
- 当前 extractor 和参数；
- 原始公式或算法说明；
- D/A/U 阈值；
- 质量门和本 session 质量结果；
- raw metrics、phase/event breakdown 和时间定位；
- calculation_status 与缺失原因；
- evidence grade、来源和模型版本；
- 当前节点连接的 sub-skills；
- 编辑、校验、另存为新模型版本和恢复默认值操作。

O1、O3、O13、H4 和 H5 是多指标或分阶段 anchor，前端不能只显示一个颜色标签；必须允许展开查看内部指标。

## 10. 本地来源

### S1：当前 18-node 拓扑

- 由项目负责人于 2026-07-10 确认的最新 mapping，已完整固化在本文件第 3 节。
- 旧 PPT/slide 16 仅是演进记录，不是产品运行时依赖。

### S2：项目初始阈值

- 项目负责人提供并确认的初始阈值表，已逐项固化在本文件第 6 节。
- 该 slide 直接给出 O1、O2、O7、O8、H1、H2、H4 的初始阈值，并将 H5 标为 in-band ideal。

### S3：P、W、W_min 和 TPX

- [R1：Perfect, Jump and White, 2015](REFERENCES.md#r1-perfect-et-al-2015)。
- PDF p5：MTE 和部分任务边界。
- PDF p8：PIO susceptibility 构念。
- PDF p10：各 performance requirement 的 time-in-bound 百分比及其聚合、discrete movement、0.5% 防噪门槛和 W；本设计的 O1 联合多轴/worst-phase 是工程适配。
- PDF p11：W_min、TPX Eq. 6 及 TPX-TLX 关系。

### S4：控制 RMS、attack rate 和 tracking deviation

- [R2：Lu, Jump, White and Perfect, 2016](REFERENCES.md#r2-lu-et-al-2016)。
- PDF p11：longitudinal/collective RMS 和 >2% full travel control attack、ANPS。
- PDF p12：Vx 和 z-position guidance-following deviation。

### S5：eye tracking、stabilisation 和 overshoot

- [R3：White and Padfield, 2004, Flight Simulation in Academia: Progress with HELIFLIGHT at the University of Liverpool](REFERENCES.md#r3-white-and-padfield-2004)。
- PDF pp2-3：calibrated scene plane 上的 point-of-regard 和 gaze-overlay video。
- PDF p12：5 s stabilisation、control activity、stabilisation time 和 maximum overshoot。

### S6：动态 scene-aware gaze

- [R4：Park et al., 2024, How is the Pilot Doing](REFERENCES.md#r4-park-et-al-2024)。
- PDF pp4-5：fixation/saccade、gaze coordinates 到 scene recording 的映射和 semantic gaze annotation。

### S7：ECG baseline 和 HR/HRV features

- [R5：Wang et al., 2025](REFERENCES.md#r5-wang-et-al-2025)。
- PDF pp7-8：R-peak、HR、SDNN、RMSSD、pNN20、LF/HF、SD1、SD2。
- PDF p9：5 min subject baseline correction 及 workload-sensitive ECG features。

### S8：EEG engagement 与个体校准

- [R6：van Weelden et al., 2026](REFERENCES.md#r6-van-weelden-et-al-2026)。
- PDF p2：alpha、beta、theta band power 和 beta/(alpha+theta) engagement index。
- PDF p8：pilot-specific calibration 和 individual alpha frequency 的必要性。
- 该来源为 2026 年已发表 IEEE AIxVR 会议论文，支持 H5 的工程方法，但仍不构成航空认证阈值来源。

## 11. 实现验收条件

reference-model-v0.1 可被认为已正确实现，至少需要满足：

1. 18 个 anchor 均能从配置加载，并与本文件 ID、名称和 mapping 一致。
2. 所有 extractor 均返回统一 AnchorResult。
3. Missing/Invalid/Not Applicable 不会变成 BN 的第四种观测状态。
4. O2、O4、H4、H5 使用本版本定义，旧 O2/O4/H5/H6 不会混入。
5. 单位转换、阈值方向、依赖和质量门均有自动校验。
6. 每个 anchor 至少有边界值、缺失输入、质量失败和正常计算测试。
7. O8 和 O13 有依赖失败测试，不会在依赖缺失时输出伪分数。
8. 前端可查询节点公式、参数、阈值、来源、质量门和连接关系。
9. 专家修改会保存为项目模型的新版本，packaged defaults 保持不变。
10. 固定 golden sessions 可以复现相同 raw metrics、evidence states 和 provenance。
