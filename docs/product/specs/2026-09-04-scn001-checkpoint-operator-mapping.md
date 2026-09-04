# SCN-001 可实现检查点算子映射设计

| 字段 | 当前值 |
|---|---|
| 日期 | 2026-09-04 |
| 状态 | **待评审；未授权落成 recipe** |
| 场景 | `SCN-001` eVTOL 加速减速与急停 |
| 范围 | `implementable_now: true` 的 17 个检查点 |
| 结构基线 | D-092 的“实施裁定（2026-09-04 复核后收敛）” |
| 当前算子目录 | 46 个，已包含 `signal.sample-at-event` |
| 明确不做 | 不生成场景包、不修改合同/schema、不开始 WinUI 外壳改造 |

## 1. 设计输入与可追溯性

本设计逐条读取以下研究文件，不把自然语言步骤冒充成已经存在的可执行图：

- `checkpoints_v0.2.json`
  - SHA-256：`1758464df1f4beaa37191a282ffb9148652d81124d416b1ab01594eed4178158`
- `item_task_scoring_cpt_v0.2.json`
  - SHA-256：`92aa555c0ceb56380d27575de2439c9e3df4c81650dd8d1dfadff4b6cc26c2dd`
- `ITEM_TASK_SCORING_CN.md`
- D-092 的实施裁定段

研究侧计数以 JSON 为准：25 个检查点中 17 个当前可实现、8 个被数据缺口阻塞；16 个三档、9 个二档。本文只设计 17 个可实现检查点的测量 DAG，不重算 31 张 CPT。

## 2. 结论与推荐方案

### 2.1 只靠现有 46 个算子不能忠实落成

17 个检查点中，只有 `CP-S1-07-01` 可以完整使用现有算子表达。其余 16 个至少缺少下列一项：

- 按动态相位区间裁剪 `SignalSeries`；
- 将 timeless 场景参考量与整条信号逐样本运算；
- 统一、可复用的场景事件和相位时间线；
- 空事件安全地转成 `UNACCEPTABLE`、`NOT_EVALUATED` 或 `NOT_APPLICABLE`，而不是算子异常；
- 与二档 `emits` 精确一致的 scorer；
- 走廊坐标投影、事件时间提取或漂移纠正方向匹配。

因此，本文不会把“勉强可拼接”写成“现有能力已支持”。

### 2.2 三种实现路径

#### 方案 A：共享场景时间线 + 通用算子（推荐）

由随 SCN-001 profile 声明、随软件实现发布的共享场景上下文一次性生成：

- 规范化运动学：`s(t)`、`d(t)`、`h(t)`、`V(t)`、`a_s(t)`、`theta(t)`、`psi(t)`；
- 点事件：`t_entry`、`t_marker`、`t_capture`、`t_onset`、`t_stop`；
- 相位区间：`G0`、`G1`、`P1`、`P2`、`P4`、`P5`。

每个 checkpoint recipe 消费同一时间线，再用可见的通用算子完成指标和分档。这样 `t_stop`、`t_onset` 等不会因复制参数而在不同检查点中产生不同答案。

当前合同可以承载额外的 `DERIVED_ARTIFACT` SourceDescriptor。为了让现有 resolver 能在具体相位缺失时于 recipe 执行前安全 OMIT，推荐的物理表示不是一个无法选择的“大 phases collection”，而是在原定的 X/U + 10 个参考量 + 4 个构型量之外增加 8 个 descriptor：

- `derived.scn001.kinematics`；
- `semantic.scn001.events`；
- `semantic.scn001.phase.G0/G1/P1/P2/P4/P5` 六个独立 interval source。

`kinematics` 是 `signal_bundle`，recipe 用 `[E] signal.channel-select` 取 `s/d/h/V/...`；`events` 是 POINT `event_collection`，用修正端口 metadata 后的 `[E] temporal.event-select(event_types=[...])` 取单个事件；每个 phase descriptor 直接返回一个 `interval_collection`，缺边界时 provider 以带原因的 OMITTED 返回，因此不依赖当前尚未执行的 `RecipeInputBinding.selector`，也不需要不存在的 interval-select。后文的 `[S] t_stop`、`[S] P4` 都是这些展开操作的简写。

仅把定义写入 `TaskProfile.task_semantics` 不会自动执行：当前 runtime resolver 按 `source_id` 找 provider，且不会解释 `task_semantics` 或 `RecipeInputBinding.selector`。所以这些逻辑来源必须有已注册 provider，或以后新增 task-level reusable graph 合同。本文推荐前者，并要求把固定算法定义展示为 Task 节点的只读“场景时间线”，不能成为不可见黑盒。

这里的 checksum 只绑定 profile 内的 descriptor、TaskProfile 与其他资源，**当前并不绑定 Python provider 的实现字节**。现有 `RuntimeSourceProvider` 只有 `source_id`，没有实现哈希或版本。短期真实追溯边界是“exact-pinned profile + 创建 run 的软件 build”；建议同时把 provider implementation ID/version 写入 descriptor metadata 与 runtime trace，并在注册时核对。若要求脱离原软件 build 仍能密码学重放 provider，实现身份还需单独设计，不能声称现合同已经做到。

同理，10 个 REF 与 4 个 CFG 即使已经有 SourceDescriptor，也不会自动从 TaskProfile 变成 recipe input；每个稳定 `source_id` 仍需 provider 从当前 task profile/runtime configuration 取值。descriptor 只声明类型与依赖，不负责取值。

#### 方案 B：把时间线子图复制进每个 recipe

生成脚本可以机械复制相同子图，但编辑 `v_stop_threshold`、`t_stop_hold`、onset 参数后，多个 recipe 可能各自得到不同 `t_stop`/`t_onset`。现有合同也没有跨 recipe 参数引用，故不推荐。

#### 方案 C：每个 checkpoint 一个专用 Python 算子

代码量最少，但计算规则会从 DAG 退化成黑盒，难以复用、评审和显示，不符合场景页“计算规则只读可见”的目标，不推荐。

## 3. 共用运行语义

### 3.1 图例

- `[E]`：当前 46 个内置算子中已经存在；
- `[N]`：建议新增的通用能力；
- `[S]`：profile-versioned 声明、由当前软件 build provider 实现的共享 SCN-001 场景上下文；
- `REF`：10 个场景参考量；
- `CFG`：4 个航空器构型量；
- `TOL`：checkpoint 容差槽；
- `DET`：检测器参数槽。
- `LOCKED`：随场景包发布、用户不可编辑的结构参数或算法常量。

### 3.2 推荐的共享运动学图

```text
X.channels
  ├─ [E] signal.channel-select(Xe, Ye)
  │    └─ [E] flight.vector-compose(x, y)
  │         + REF.corridor_centreline
  │         └─ [N] flight.corridor-project
  │              ├─ s(t)
  │              └─ d(t)
  ├─ [E] signal.channel-select(Ze)
  │    └─ [E] signal.unit-convert(scale=-1, offset=0) ── h(t)
  ├─ [E] signal.channel-select(V_ex, V_ey)
  │    ├─ [E] flight.vector-compose(vx, vy) ────────────┐
  │    └─ [E] signal.unit-convert(scale=0) × 2
  │         └─ [E] flight.vector-compose(0, 0) ─────────┤
  │                                                     └─ [E] flight.distance ── V(t)
  ├─ raw theta
  │    └─ [LOCKED source normalization] unit=deg, nose-up-positive ───────────── theta(t)
  ├─ raw psi
  │    └─ [LOCKED source normalization] unit=deg, declared wrap convention ──── psi(t)
  └─ acceleration channels
       + corridor direction
       └─ [N；待裁定定义] flight.corridor-vector-project ── a_s(t)
```

用现有 `flight.distance` 与同网格零向量即可求速度模长，不需要为了 `sqrt(V_ex²+V_ey²)` 单独新增 vector-norm 算子。

`theta` 的“抬头为正”是 source adapter 必须验证或转换的坐标约定，不是无条件乘 `-1`；样例中加速段 theta 为负可以表示真实低头姿态。未经 source metadata/adapter 声明，不能把原始列直接当 canonical theta。psi 同理必须先统一单位与角度约定。

### 3.3 推荐的共享时间线图

```text
s(t) ── [N] event.first-match(s >= 0) ───────────────────────────── t_entry
s(t) + REF.s_marker ── [N] event.first-match(s >= marker) ───────── t_marker

V(t) + REF.V_nom + DET.v_capture_tol + capture-search-window
  └─ [N] signal.scalar-error(mode=absolute)
       └─ [N] event.first-match(error <= tolerance) ──────────────── t_capture

onset_definition = control:
  U.lon - u_lon_baseline + DET.onset_u_threshold/min_duration
    └─ [N] event.sustained-threshold-onset ───────────────────────── candidate t_onset

onset_definition = response:
  a_s(t) + DET.onset_ax_threshold/min_duration
    └─ [N] event.sustained-threshold-onset ───────────────────────── candidate t_onset

V(t) from t_onset + DET.v_stop_threshold/t_stop_hold
  └─ [N] event.sustained-threshold-onset ─────────────────────────── t_stop

events + session bounds + REF.hold_duration
  └─ [S] phase materializer ── G0, G1, P1, P2, P4, P5
```

这里有两个不能靠代码猜测的环：

1. `P1` 的定义以 `t_capture` 结束，但 `t_capture` 又写成“在 P1 内寻找”；必须另定 capture search window 的上界。
2. onset 搜索窗写成“有 capture 则从 capture 开始，否则从 entry 开始”。如果 capture 候选发生在实际 onset 之后，按该规则会漏掉 onset；必须明确事件求解顺序和无效顺序的处置。

### 3.4 参数所有权与固定结构参数

共享事件不能从其他 checkpoint recipe 偷读参数。推荐采用以下单一所有权：

| 参数类别 | 唯一持久化位置 | provider/recipe 如何取得 |
|---|---|---|
| 10 个 REF | `TaskProfile.reference_parameters` | 对应 TASK_SEMANTIC provider 从 exact-pinned TaskProfile 读取 |
| 4 个 CFG | `TaskProfile.task_semantics.aircraft_config`（建议位置） | 对应 TASK_SEMANTIC provider 读取；场景 UI 可在参数页编辑 |
| 共享事件参数 | `TaskProfile.task_semantics.detectors` | events/phase provider 只从这里读取 |
| 仅影响单一 checkpoint 分档的 TOL | 该 EvidenceRecipe 的 node/scoring parameters | recipe 直接使用；不被共享 provider 读取 |
| 记录完整性 | run/session metadata 或 runtime parameter | source resolver 在生成 events/phases 前读取 |
| LOCKED | profile 生成器中的固定 recipe/task-semantics 结构 | 用户界面只读 |

“共享事件参数”包括 `v_capture_tol`、`onset_definition`、`onset_u_threshold`、`onset_ax_threshold`、`onset_min_duration`、`v_stop_threshold`、`t_stop_hold`。其中 capture/stop 参数仍显示在其所属 checkpoint 页面，但保存到上述 canonical detector slot；CP-S2-05-02/CP-S2-30-08 recipe 只消费事件，不保有第二份数值。这样即使下一阶段尚未实现 CP-S2-05-02 recipe，A-S2-30 的共享 timeline 也有 snapshot-pinned 的 capture 参数来源。`drift_trigger_band/correction_u_threshold` 在 CP-S2-02-04 语义补齐前不进入共享 timeline。

关键 LOCKED 参数的来源统一如下；逐项图只重复与该项不同的部分：

| 算子参数 | 来源 |
|---|---|
| `channel_id`、vector `dimensions/series_id/unit` | SCN-001 X/U canonical channel mapping，随 profile 发布 |
| `event_type` | 稳定 ID：`t_entry/t_marker/t_capture/t_onset/t_stop` 或明确的诊断事件 ID |
| `comparison/direction` | 研究步骤中的不等号或分档方向，属于结构，不可编辑 |
| `percentile` | `0` 表示 min、`100` 表示 max，来自研究公式，属于结构 |
| `signal.window` 边界规则 | 评审后锁定；当前建议半开 `[start,end)`、不在边界插值 |
| `sample-at-event.multiple_event_policy` | canonical 单事件一律 `error` |
| `sample-at-event.no_sample_policy` | 有事件却无法采样一律 `error`；无事件由 guard/disposition 处理 |
| `sample-at-event.alignment/max_gap` | 同一 X 网格用 `exact/0`；跨 X/U 按评审后的同步策略锁定 |
| scorer `direction` | 研究 grading rule，属于结构 |
| scorer `likelihood_strength` | HARD 三档统一锁定 `1.0` |
| normalized-q scorer boundaries | 固定 `desired=0, adequate=1`；专家只改原始 TOL |

任何 canonical shared parameter 为 `null` 时，events provider 必须带 `not_evaluated/unconfigured` 原因 OMIT；不得从尚未实现的 recipe、旧 hover 模型或样例数据反推数值。

### 3.5 建议新增或修正的通用能力

| ID | 能力 | 精确定义摘要 | 首次消费者 |
|---|---|---|---|
| N1 | `signal.window` | `signal_series + interval_collection -> signal_series`；合并重叠区间、保持原采样时刻 | 11 个检查点/共享 detector |
| N2 | `signal.scalar-error` | `signal_series + number -> signal_series`；`signed/absolute/circular_signed` | S2-05、S2-30 |
| N3 | `flight.corridor-project` | 位置向量与走廊几何投影为有符号 `s/d` | S2-05-04 等 |
| N4 | `event.first-match` | 最多一个事件；首样本已满足条件时也必须命中 | `t_entry/t_marker/t_capture` |
| N5 | `event.sustained-threshold-onset` | 在动态搜索窗内找首个持续满足阈值的 run，输出 run onset 点事件 | `t_onset/t_stop` |
| N6 | `temporal.event-duration-window` | 点事件 + runtime duration -> interval | `P5` |
| N7 | `signal.relative-to-event` | 对每个样本减去同一信号在基准事件时刻的值 | CP-S2-02-03 |
| N8 | `event.timestamp` | 单事件转秒值；允许事件先后差为负 | 多个诊断量 |
| N9 | `statistics.named-select-or-default` | 空 named mapping 不抛异常，可显式给 default 与 present flag | CP-S2-30-01 |
| N10 | `statistics.time-in-band` | 按持续时间而非样本数积分，除以有效窗口总时长输出 fraction，并正确处理分段窗口 | 四项诊断量 |
| N11 | `flight.control-full-travel` | 动态 `piloted_axes` 的逐轴 min/max、全行程布尔与覆盖率 | CP-S1-02-01 |
| N12 | `event.directional-correction-match` | trigger 与符合控制方向的 response 一次性配对，输出有限 `latency_max_or_zero`、`unmatched_count` | CP-S2-02-04 |
| N13 | `scoring.binary-du` | 只产出 `unacceptable/desired`；不构造三态 likelihood | 9 个二档检查点 |

另需修正 `[E] temporal.event-select` 的端口 metadata：它当前把所有 event collection 错标为 `INTERVAL`，与事件检测器和 `signal.sample-at-event` 的 `POINT` 端口无法通过 recipe validation。建议将该通用筛选器的输入/输出 temporal semantics 标为 `MIXED`；修 metadata 不改变事件运行值。

### 3.6 缺失、不可适用与参数未配置

D-092 已裁定 `NOT_EVALUATED`/`NOT_APPLICABLE` 不进入 BN 状态，BN 只接收 `OMITTED`。但当前 recipe executor 只有“必需 source 在执行前缺失”能安全生成 `OMITTED`；图中出现空事件后，`named-select`、`event.peak` 或 percentile 往往抛异常并中止整次 run。

因此需要独立于 BN 状态的 evaluation disposition：

```text
computed state ──────────────── HARD observation: D/A/U
NOT_EVALUATED ─┐
NOT_APPLICABLE ├─────────────── OMITTED observation + reporting/trace reason
unconfigured ──┘
```

规则必须是：

- 缺数据、缺相位、参数仍为 `null`：`NOT_EVALUATED`，绝不能把 `null` 替成 0；
- 条件客观不适用，例如 P5 没有 drift trigger：`NOT_APPLICABLE`；
- 数据与参数齐全、记录被声明为完整，但动作没有发生：按 checkpoint 规则输出 `UNACCEPTABLE`；
- 诊断支路缺值不能拖垮主评分支路。

共享 event source 必须区分两种运行值：完整记录中“没有检测到动作”是**可用但为空**的 event collection，供 CP-S2-30-01/08 判 U；partial/unknown 记录导致的“还没观察到后半段”则是**source omitted**，供 reporting 判 N/E。把两者都编码成空 collection 会把截断数据误判为失败；把两者都编码成 omitted 会放过完整记录中的未执行动作。

研究 JSON 的所有 TOL/DET 数值目前均为 `null`，而现有 operator/scorer 参数 schema 要求具体 number。场景包可以保存完整结构，但在专家填写数值前必须在执行前报告“参数未配置/NOT_EVALUATED”；不能生成伪默认值，也不能走到 operator exception。

建议的最小可执行落点不改 BN/RunSnapshot/result 合同：

1. 在 `SourceUnavailableError` 的 runtime-only 路径中区分稳定原因码 `not_evaluated` 与 `not_applicable`；resolver 状态仍是现有 `OMITTED`，BN 仍生成现有 `ObservationKind.OMITTED`。
2. 六个独立 phase source 缺自身边界时，在 recipe 执行前以 `not_evaluated` OMIT。这样 percentile/peak 不会收到空窗口。
3. scene run readiness 在 compile 前检查 recipe 所需 TOL 与共享 DET。任一 required 数值为 `null` 时，直接为该 evidence 生成 OMITTED 和 `scene.parameter_unconfigured` diagnostic；不调用 compiler/scorer。
4. 现有 source trace 已有自由字符串 `code/source_id/message/dependency_path`，用稳定 diagnostic code 携带上述原因；CoverageReportingPolicy 把它呈现为 `NOT_EVALUATED/NOT_APPLICABLE` 并执行 Incomplete 门控。旧 artifact 字节不改，BN 状态也不扩展。
5. 如果实现时发现 final scene report 无法在现有 reporting artifact/free-JSON policy 中保存 domain disposition，按用户约束停下报告，再讨论新合同版本；不能原地扩已发布 result schema。

当前 executor 没有 optional branch，并会执行图中所有节点。因此第一批 A-S2-30 recipe 只放入“其依赖由主指标已保证”的诊断节点；需要额外、可能缺失事件的诊断先在 trace 中标记 unavailable，不把一个非评分诊断变成整项执行失败。以后若要所有 optional diagnostics 同图执行，需增加明确的 optional-output/short-circuit 运行语义。

### 3.7 分档输出的共同约定

- 三档主指标继续用 `[E] scoring.ordered-dau`，`likelihood_strength` 锁定为 `1.0`，因为研究定义是确定性规则；其内部 `adequate` 经 binding 一一映射为场景状态 `acceptable`。
- 二档主指标用 `[N13] scoring.binary-du`，只产出 `unacceptable/desired` 的 HARD state 和 score，不输出固定三态 `EvidenceLikelihood`。
- normalized `q` 只是把非对称区间或两个 AND 判据无损压成一个标量；公式结构锁定，原始容差仍是可编辑数值。
- `NOT_EVALUATED/NOT_APPLICABLE` 不调用 scorer，直接形成带原因的 OMITTED observation。

### 3.8 参数 preflight

在任何 operator 执行前至少校验：

- 所有 required REF/CFG/TOL/DET 已配置、类型正确且为有限值；
- 绝对偏差、距离、时延等非负 metric 的 lower-is-better 阈值满足 `0 <= desired < acceptable`；`theta_peak` 只强制有限且 `desired < acceptable`，不擅自增加非负约束；
- margin 类 higher-is-better 阈值满足 `desired > acceptable >= 0`；
- CP-S2-30-01 四阈值分别满足 `0 <= early_D < early_A`、`0 <= late_D < late_A`；
- CP-S2-30-04 满足 `0 <= drop_D < drop_A`、`0 <= gain_D < gain_A`；
- CP-S2-02-01 满足 `0 <= undershoot_D < undershoot_A`、`0 <= overrun_D < overrun_A`；
- `s_gate_near <= s_gate_far`，宽度、检测器 minimum duration 与 max-gap 非负；定义 P5 长度的 `hold_duration` 必须大于 0；
- 研究侧已有的跨参数约束，例如 `lat_stop_acceptable <= w_gate`、`V_peak_margin_acceptable >= 0`，在保存和 run preflight 两处校验。

这里的严格不等号是 normalized-q 不除零的前提，属于本设计提案，仍需第 6 节确认；若产品必须允许相等边界，就改用直接规则 scorer，而不是放松 preflight 后继续执行 q。

## 4. 17 个 checkpoint 的逐项映射

下图中的 `[S]` 节点是共享图的引用，不表示每个 recipe 再算一遍。为逐条对应研究散文，CP-S2-05-02 与 CP-S2-30-08 同时展示了 canonical event 在 S 内部的展开定义；实际 checkpoint recipe 只消费该共享事件并判定其存在性。

### 4.1 A-S1-02

#### CP-S1-02-01 操纵全行程检查已执行（二档）

```text
U.channels + [S] G0 + CFG.piloted_axes + CFG.control_travel_limits
  └─ [N11] flight.control-full-travel
       parameters: TOL.travel_low_threshold, TOL.travel_high_threshold
       outputs: axes_full_travel, coverage_per_axis
       └─ [N13] scoring.binary-du(true => desired, false => unacceptable)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. 取 G0 内 U 各轴，仅保留 `piloted_axes` | N11 的 bundle、G0 与动态轴集合输入 |
| 2. 每轴求 min/max | N11 的逐轴 extrema |
| 3. `max >= high && min <= low` | N11 的含等号判定 |
| 4. 全部轴成立 | N11 汇总布尔；空轴集合必须报配置错误 |

参数来源：`piloted_axes/control_travel_limits` 来自 CFG；两个 threshold 来自本 checkpoint TOL；G0 来自共享时间线。

不能直接落成之处：现有算子不能按 runtime `piloted_axes` 动态遍历 signal bundle。若轴集合随发布固定，可展开 `channel-select -> window -> percentile(0/100) -> safe-formula`，但这会违反“构型量可调”。研究文件也没有给出 liftoff/G0 结束检测器，且未说明 threshold 是绝对 `%stick` 还是相对 `control_travel_limits` 的比例。声明轴缺通道时应为 `NOT_EVALUATED`，不能当作 U。

### 4.2 A-S1-07

#### CP-S1-07-01 目标速度对空速限制的余度（三档）

```text
REF.V_nom + CFG.V_limit
  └─ [E] composition.safe-formula("V_limit - V_nom")
       └─ [E] scoring.ordered-dau(
            higher_is_better,
            desired=TOL.V_nom_margin_desired,
            adequate=TOL.V_nom_margin_acceptable)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `margin = V_limit - V_nom` | 一一对应 `safe-formula` |

这是 17 项中唯一完全由现有算子表达的主指标。binding 将 scorer 内部的 `adequate` 映射为场景词汇 `acceptable`；本轮不做全局词汇改名。配置保存时校验 `V_nom_margin_acceptable >= 0`。

待确认的测量语义：研究文件把 `V` 定义为 earth-frame ground speed，但本项比较对象叫 airspeed limit。必须确认 SCN-001 是否明确假设零风，或以后改用 air-relative speed。按共同约定，本项是 HARD observation，`likelihood_strength` 锁定为 1.0，不自行引入研究文件未给出的软强度。

#### CP-S1-07-02 实际峰值速度对空速限制的余度（三档）

```text
[S] V(t) + [S] (P1 ∪ P2 ∪ P4)
  └─ [N1] signal.window
       ├─ [E] statistics.percentile(100) ── V_peak
       │    + CFG.V_limit
       │    └─ [E] safe-formula("V_limit - V_peak")
       │         └─ [E] scoring.ordered-dau(higher_is_better, TOL boundaries)
       └─ [E] event.peak(mode=maximum, event_type=t_v_peak [LOCKED])
            └─ [N8] event.timestamp ── diagnostic t_V_peak
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. 在 P1∪P2∪P4 求 `max V(t)` | N1 裁剪后 percentile 100；peak 支路保留时刻 |
| 2. `margin = V_limit - V_peak` | `safe-formula` |

参数来源：phase 为 S；`V_limit` 为 CFG；两条 margin 边界为 TOL。缺口是 N1。还需裁定：P4 缺失时整项 `NOT_EVALUATED`（推荐），还是只在已有 P1/P2 求峰值；后者可能漏掉真正峰值却给出 Desired。ground speed/airspeed 问题同上一项。

### 4.3 A-S2-05

#### CP-S2-05-01 指定高度保持（加速与保持段，三档）

```text
[S] h(t) + REF.h_nom
  └─ [N2] signal.scalar-error(mode=absolute)
       + [S] (P1 ∪ P2)
       └─ [N1] signal.window
            ├─ [E] statistics.percentile(100) ── max |h-h_nom|
            │    └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
            └─ [N10] statistics.time-in-band ── diagnostic time_in_desired_band
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `h=-Ze` | 共享运动学中的 `unit-convert(scale=-1)` |
| 2. `e=h-h_nom` over P1∪P2 | N2 + N1 |
| 3. `max |e|` | percentile 100 |

参数来源：`h_nom` 为 REF；phase 为 S；`alt_dev_desired/acceptable` 为 TOL。现有 `flight.target-error` 不能替代 N2，因为它要求 reference 也是 SignalSeries。若 P2 缺失，建议整项 `NOT_EVALUATED`，不以 P1 的部分数据给 Pass。

#### CP-S2-05-02 目标速度已达成（二档）

```text
[S 内部] V(t) + REF.V_nom
  └─ [N2] signal.scalar-error(mode=absolute)
       + [S] capture-search-window
       └─ [N1] signal.window
            └─ [N4] event.first-match(error <= DET.v_capture_tol)
                 ├─ event t_capture
                 │    └─ checkpoint recipe input: [S] t_capture
                 ├─ [E] statistics.count
                 │    └─ [N13] scoring.binary-du(count >= 1)
                 └─ [N8] event.timestamp ── diagnostic t_capture_elapsed
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. 在 P1 找首个 `|V-V_nom| <= tol` | N2、N1、N4；N4 必须检查窗口首样本 |
| 2. 存在则事件成立并记为 `t_capture` | 0/1 事件 collection + count + binary scorer |

参数来源：`V_nom` 为 REF；`v_capture_tol` 在研究 JSON 中列于本项 grading parameters，但实现中提升为共享 timeline 的唯一 canonical DET slot，checkpoint 页面仍负责显示和编辑；搜索窗来自 S。不存在 recipe 内第二份 tolerance。

不能用 `[E] event.threshold-crossing`，因为窗口首样本若已在容差内不会发生 crossing；也不能用 `[E] flight.capture`，因为它不输出事件，且 start/end/tolerance 都是字面参数。`t_capture_elapsed` 的基准应为 `t_entry`。诊断 note 表明 `V_overshoot` 是“捕获后相对 V_nom 的最大超调”，可推得候选形式 `max(0,max(V-V_nom))`，但没有给捕获后的结束时刻；在研究侧裁定窗口前不落成该诊断。

最关键歧义是 P1/t_capture 循环：必须为 capture search 单独规定上界。

#### CP-S2-05-03 目标速度保持（三档）

```text
[S] V(t) + REF.V_nom
  └─ [N2] signal.scalar-error(mode=absolute)
       + [S] P2
       └─ [N1] signal.window
            ├─ [E] statistics.percentile(100) ── max |V-V_nom|
            │    └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
            └─ [N10] statistics.time-in-band
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `e=V-V_nom` over P2 | N2 + N1 |
| 2. `max |e|` | percentile 100 |

参数来源：`V_nom` 为 REF；P2 为 S；`v_dev_desired/acceptable` 为 TOL。JSON 已明确 `t_capture=null` 时本项 `NOT_EVALUATED`。还需裁定：已经 capture 但没有 onset 时，P2 是否延伸到 session end，还是因缺完整 P2 而 `NOT_EVALUATED`。

#### CP-S2-05-04 航迹保持（横向，三档）

```text
[S] d(t) + [S] (P1 ∪ P2)
  └─ [N1] signal.window
       + [E] constant.number(value=0 [LOCKED])
       └─ [N2] signal.scalar-error(reference=0, mode=absolute)
            └─ [E] statistics.percentile(100) ── max |d|
                 └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. 点到走廊中心线的有符号垂距 `d(t)` | 共享 N3 `corridor-project` |
| 2. P1∪P2 内 `max |d|` | N1 + N2 + percentile 100 |

参数来源：`corridor_centreline` 为 REF；phase 为 S；`lat_dev_desired/acceptable` 为 TOL；`w_corridor` 只参与保存时约束 `acceptable <= w_corridor`。

走廊几何合同尚未定义直线/折线/样条、端点外投影、等距投影和“右为正”的方向。样例 CSV 的 `Ye` 恒为 0，JSON 仍把本项列为可实现但注明无区分力；需确认受约束横向轴是照常产生 0 偏差，还是因无测量区分力而 `NOT_EVALUATED`。

### 4.4 A-S2-30

#### CP-S2-30-01 减速起动位置（三档）

```text
[S] t_onset ── [E] statistics.count ────────────────────────────── onset_present
      │
      └────────────────────────────────────┐
[S] s(t) ──────────────────────────────────┴─ [E] signal.sample-at-event
                                               alignment=<待裁定>
                                               max_gap=<待裁定>
                                               no_sample=error
                                               multiple_event=error
                                                └─ [N9] named-select-or-default(
                                                     key=t_onset,
                                                     default=0 [LOCKED, guard-only]) ── s_onset

s_onset + REF.s_marker
  └─ [E] safe-formula("d_onset = s_onset - s_marker")

d_onset + onset_present + 四个 TOL
  └─ [E] safe-formula：
       q = max(
         2 * (1-onset_present),
         (d_onset-late_D)/(late_A-late_D),
         ((-d_onset)-early_D)/(early_A-early_D))
       └─ [E] scoring.ordered-dau(lower_is_better, desired=0, adequate=1)
```

该 `q` 在 `0 <= early_D < early_A`、`0 <= late_D < late_A` 时与研究侧非对称四阈值规则严格等价；`onset_present=0` 强制 U。

| 研究步骤 | DAG 对应 |
|---|---|
| 1. detector 求 `t_onset` | 共享 S 时间线 |
| 2. `t_onset=null -> U` | event count + N9 + `q` 的 onset-present guard |
| 3. `d_onset=s(t_onset)-s_marker` | 新算子 `sample-at-event` + `safe-formula` |

参数来源：`s_marker` 为 REF；四个 early/late 边界为本项 TOL；`onset_definition/onset_u_threshold/onset_ax_threshold/onset_min_duration` 为共享 DET。

诊断支路：`V(t)+t_onset -> sample-at-event(alignment/max_gap=与主支路相同, no_sample=error, multiple=error) -> named-select(key=t_onset) -> V_at_onset`；`event.timestamp(t_onset)-event.timestamp(t_marker) -> dt_onset`。不能用现有 `event.latency` 计算 `dt_onset`，因为提前减速需要负数。

必须评审：control onset 的 `u_lon_baseline`、减速操纵正负方向均未定义；control/response 切换没有现成图算子；若 onset 来自 U 网格，`s(t_onset)` 未必能 exact 命中 X 网格。推荐在跨流时用 `linear + 有上限的 max_gap`，但 max gap 不能凭空填数；若共享 materializer 保证事件吸附到 X 网格，才可锁定 `exact/0`。`onset_present` 必须数原始 event，而不是数成功采到的 s 值：有 onset 但采样对齐失败是数据/同步问题，不能伪装成“未减速”并判 U。

#### CP-S2-30-03 全程航向保持（三档）

```text
[S] psi(t) + REF.psi_nom
  └─ [N2] signal.scalar-error(mode=circular_signed, period=360, range=[-180,180])
       + [S] (P1 ∪ P2 ∪ P4 ∪ P5)
       └─ [N1] signal.window
            + [E] constant.number(value=0 [LOCKED])
            ├─ [N2] signal.scalar-error(reference=0, mode=absolute)
            │    └─ [E] statistics.percentile(100) ── max |psi_err|
            │         └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
            └─ [N10] statistics.time-in-band
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `wrap(psi-psi_nom)` 到 `[-180,180]` | N2 circular mode |
| 2. 四相位并集求最大绝对值 | N1 + absolute scalar-error + percentile 100 |

参数来源：`psi_nom` 为 REF；四相位为 S；`hdg_dev_desired/acceptable` 为 TOL。需裁定缺 onset/stop 时四相位并集是截到 session end，还是本项 `NOT_EVALUATED`。`time_in_desired_band` 应按持续时间还是样本比例也尚未定义。

#### CP-S2-30-04 减速段高度保持（三档）

```text
[S] h(t) + REF.h_nom
  └─ [N2] signal.scalar-error(mode=signed)
       + [S] P4
       └─ [N1] signal.window
            ├─ [E] percentile(0)   ── e_min ── [E] safe-formula max(0,-e_min) ── drop
            └─ [E] percentile(100) ── e_max ── [E] safe-formula max(0, e_max) ── gain

drop + gain + 四个 TOL
  └─ [E] safe-formula：
       q=max((drop-drop_D)/(drop_A-drop_D),
             (gain-gain_D)/(gain_A-gain_D))
       └─ [E] scoring.ordered-dau(lower_is_better, desired=0, adequate=1)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `e=h-h_nom` over P4 | N2 + N1 |
| 2. `drop=max(0,-min e)` | percentile 0 + formula |
| 3. `gain=max(0,max e)` | percentile 100 + formula |

参数来源：`h_nom` 为 REF；P4 为 S；四个 drop/gain 边界为 TOL。`q` 在 `drop_D<drop_A`、`gain_D<gain_A` 时与两个 AND 判据严格等价。

诊断 `h_at_stop` 用 `h+t_stop -> sample-at-event(exact, max_gap=0, no_sample=error, multiple=error) -> named-select(key=t_stop)`。当前 executor 会执行所有诊断节点，所以 t_stop 缺失时诊断分支不能抛异常。还需裁定 t_stop 缺失时 P4 是到 session end，还是本项 `NOT_EVALUATED`，以及 P4 是否包含 t_stop 样本。

#### CP-S2-30-05 峰值抬头姿态不过大（三档）

```text
[S] theta(t) + [S] P4
  └─ [N1] signal.window
       ├─ [E] statistics.percentile(100) ── theta_peak
       │    └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
       └─ [E] event.peak(mode=maximum, event_type=t_theta_peak [LOCKED])
            └─ [N8] event.timestamp ── diagnostic t_theta_peak
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `theta` 抬头为正 | X source adapter/共享运动学必须保证符号 |
| 2. P4 内 `max theta` | N1 + percentile 100；peak 只保留诊断时刻 |

参数来源：P4 为 S；`theta_peak_desired/acceptable` 为 TOL。现有 peak 对相同峰值选择最早时刻，符合可复现要求。

诊断：peak event 经 N8 得 `t_theta_peak`；`event.timestamp(t_stop)-event.timestamp(t_theta_peak)` 得 lead。不能用 `event.latency`，因为它会把负时差当成无匹配。JSON 已明确依据 `PL.VI.A.R2` 采用 lower-is-better，不需再裁定方向；仍需裁定无 t_stop 时的 P4 截尾。

#### CP-S2-30-08 完全停住（二档）

```text
[S] t_stop
  └─ [E] statistics.count
       └─ [N13] scoring.binary-du(count >= 1 => desired, else unacceptable)
```

共享 detector 的目标图：

```text
[S] V(t) + search=[t_onset, session_end]
  └─ [N5] event.sustained-threshold-onset(
       comparison=lt,
       threshold=DET.v_stop_threshold,
       minimum_duration=DET.t_stop_hold)
       └─ first run onset = t_stop
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. 首个 `V<threshold` 且持续 hold 的时刻 | N5，输出 run onset 而非确认时刻 |
| 2. `t_stop` 存在则事件成立 | count + binary scorer |

现有 `event.hold-run` 只能近似：它要求把 threshold、hold、session end 都写成静态参数，不能接动态搜索窗，且输出所有 interval 而不是首个 point event。

尚需裁定 `t_onset=null` 时 stop detector 是否回退到 `[t_entry,session_end]` 搜索，还是因为减速阶段未建立而不运行；不能反过来以 P4/P5 作为 t_stop 搜索窗，因为它们本身以 t_stop 为边界。

诊断：N8 求 `t_stop-t_onset`；以 `sample-at-event(exact, max_gap=0, no_sample=error, multiple=error)` 分别读取 `s(t_stop)` 与 `s(t_onset)` 后相减得 stopping distance。这里的 onset 必须已由共享 materializer 吸附到 X 网格，否则 s(t_onset) 使用 CP-30-01 评审后的跨流 alignment。无 stop 时诊断必须省略，不能拖垮主结论。

二档不能用 `scoring.ordered-dau` 伪装。它固定产生 U/A/D 三态 likelihood，而 pipeline 要求 scorer state 集与 binding 的两态集合精确覆盖且不重复。N13 应只输出 U/D 状态（HARD observation）和 score，不改三态 `EvidenceLikelihood` 合同。

#### CP-S2-30-09 减速过程中不越过门远边（三档）

```text
[S] s(t) + [S] (P4 ∪ P5)
  └─ [N1] signal.window
       └─ [E] statistics.percentile(100) ── s_max
            + REF.s_gate_far
            └─ [E] safe-formula("max(0, s_max-s_gate_far)") ── overshoot
                 └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. P4∪P5 瞬时 `max(0,max s-s_gate_far)` | N1 + percentile 100 + formula |

参数来源：`s_gate_far` 为 REF；P4/P5 为 S；`overshoot_desired/acceptable` 为 TOL。除 N1 外主指标均为现有算子，并保留“即使后来退回，瞬时越界也算”的语义。

需裁定无 t_stop 时是否用 `[t_onset,session_end]` 继续测 overshoot，还是 `NOT_EVALUATED`；无 t_onset 时是随 onset detector note 判 U，还是因无 P4 判 `NOT_EVALUATED`。

### 4.5 A-S2-02

#### CP-S2-02-01 停止点纵向落点（三档）

```text
[S] s(t) + [S] t_stop
  └─ [E] signal.sample-at-event(exact, max_gap=0, no_sample=error, multiple=error)
       └─ [E] statistics.named-select(t_stop) ── s_stop

s_stop + REF.s_gate_near ── [E] safe-formula max(0, near-s_stop) ── undershoot
s_stop + REF.s_gate_far  ── [E] safe-formula max(0, s_stop-far)  ── overrun

undershoot + overrun + 四个 TOL
  └─ [E] safe-formula：
       q=max((undershoot-undershoot_D)/(undershoot_A-undershoot_D),
             (overrun-overrun_D)/(overrun_A-overrun_D))
       └─ [E] scoring.ordered-dau(lower_is_better, desired=0, adequate=1)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `t_stop=null -> NOT_EVALUATED` | t_stop source 的 evaluation disposition，执行前 OMIT |
| 2. `s_stop=s(t_stop)` | sample-at-event + named-select |
| 3. 求 undershoot | first formula |
| 4. 求 overrun | second formula |

参数来源：near/far 为 REF；四条边界为 TOL。normalized `q` 使用与 CP-S2-30-04 相同的双量 AND 等价变换。t_stop 由 X 上的 V 样本生成，s 也来自同一 X 网格，故这里锁定 `exact/0`；若事件存在却没有同时间的 s sample，应报告数据/同步错误，不应静默插值。

#### CP-S2-02-02 停止点横向落点（三档）

```text
[S] d(t) + [S] t_stop
  └─ [E] signal.sample-at-event(exact, max_gap=0, no_sample=error, multiple=error)
       └─ [E] statistics.named-select(t_stop)
            └─ [E] safe-formula(abs(d_stop)) ── lat_stop_error
                 └─ [E] scoring.ordered-dau(lower_is_better, TOL boundaries)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `t_stop=null -> NOT_EVALUATED` | t_stop disposition/OMITTED |
| 2. `|d(t_stop)|` | sample + select + abs |

参数来源：`d` 的几何来自 REF.corridor_centreline；两条边界为 TOL；`w_gate` 用于保存时约束 `lat_stop_acceptable <= w_gate`。该跨 reference/TOL 约束不能只留在文档中，需要场景参数 preflight。

#### CP-S2-02-03 保持期内的位置漂移（三档）

```text
[S] t_stop + REF.hold_duration
  └─ [N6] temporal.event-duration-window ── P5

[S] s(t) + t_stop ── [N7] signal.relative-to-event ── ds(t) ─┐
[S] d(t) + t_stop ── [N7] signal.relative-to-event ── dd(t) ─┤
P5 ─────────────────────────── [N1] signal.window on both ─────┤
                                                               ├─ [E] vector-compose(ds,dd)
zero copies via [E] unit-convert(scale=0) + vector-compose ─────┤
                                                               └─ [E] flight.distance
                                                                    └─ drift_distance(t)
                                                                         └─ [E] percentile(100)
                                                                              └─ ordered-dau
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. `t_stop=null -> NOT_EVALUATED` | t_stop disposition/OMITTED |
| 2. `P5=[t_stop,t_stop+hold_duration]` | N6 |
| 3. 最大二维相对位移 | N7×2 + N1 + vector-compose + distance + percentile 100 |

参数来源：`hold_duration` 为 REF；两条 drift 边界为 TOL。

不能自行决定的歧义：“漂出门 -> UNACCEPTABLE”没有定义门的几何判据，本 checkpoint 的 requires 也没有列出 `s_gate_near/s_gate_far/w_gate`。若含义是 P5 内任一点必须满足 `near <= s <= far && |d| <= w_gate`，需补三项依赖和独立硬门控。`drift_direction` 诊断需要 `atan2(dd,ds)`，现有 safe-formula 不支持；可先不输出，或新增通用 bearing 算子。若记录早于 `t_stop+hold_duration` 结束，建议 `NOT_EVALUATED`，不能用短窗口给伪 Pass。

#### CP-S2-02-04 漂移修正的及时性（三档）

```text
[future S] derived.scn001.drift-correction provider（第 9 个 derived source）
  └─ 从 [S] s/d、t_stop、P5 展开 CP-S2-02-03 同一固定 displacement 子图
       └─ [E] event.threshold-crossing(rising, DET.drift_trigger_band)
            └─ triggers ── [E] statistics.count ── trigger_count
                 ├─ count=0 ── SourceNotApplicable / OMIT
                 └─ count>0
                      + displacement direction + U.channels + control-effect mapping
                      └─ [N12] event.directional-correction-match(
                           threshold=DET.correction_u_threshold)
                           ├─ latency_max_or_zero
                           ├─ unmatched_count
                           └─ trigger_count

checkpoint recipe consumes the returned named mapping
  ├─ named-select(latency_max_or_zero)
  ├─ named-select(unmatched_count)
  └─ named-select(trigger_count) ── diagnostic trigger_count

latency_max_or_zero + unmatched_count + TOL
  └─ [E] safe-formula：
       q=max(2*min(1,unmatched_count),
             (latency_max_or_zero-latency_D)/(latency_A-latency_D))
       └─ [E] scoring.ordered-dau(lower_is_better, desired=0, adequate=1)
```

| 研究步骤 | DAG 对应 |
|---|---|
| 1. detector 求各 trigger/response | threshold crossing + N12 |
| 2. 无 trigger -> NOT_APPLICABLE | 显式 disposition；不能把空集合送进 aggregation |
| 3. 求最大 latency | N12 在有 trigger 的集合内求最大值；unmatched guard 强制 U |

现有 `event.latency` 不能判断 response 是否朝纠正方向、不能阻止一个 response 被多个 trigger 重用、也不能把 unmatched 直接判 U，所以不能勉强套用。N12 必须在“有 trigger 但零个 matched response”时仍返回有限的 `latency_max_or_zero=0` 和正的 `unmatched_count`，使 safe-formula 在进入任何空集合 aggregation 前判 U。

本项不能读取 CP-S2-02-03 的 recipe 中间值；上图的 provider 从同一锁定模板独立展开 displacement 逻辑。当前 executor 无法让 recipe 图内的 `count=0` 反向触发 source omission，所以要忠实表达 N/A，必须采用这个第 9 个 derived descriptor，或将来新增图内条件 omission 语义；本文推荐前者，并要求单独批准。

本项研究语义尚不完整：detector 写“首次超过”，checkpoint 却写“各次 trigger”；多次触发时的 re-arm、滞回和最短持续时间未定义。四个现有 CFG 也没有说明 U channel 到走廊 s/d 方向的映射、正负极性、trim/baseline、单位归一化或多轴响应规则。补齐前，本项虽被 JSON 标记为 `implementable_now: true`，实际仍应视为语义阻塞，不能自行从旧 O12 算法移植默认值。

## 5. 样例 CSV 与 `INCOMPLETE` 的关键判别

指定样例 CSV 只有加速段，没有减速、停止和 P5。用户要求整次结果为 `INCOMPLETE`，缺失项报告 `NOT_EVALUATED`，不能给 Pass。

但研究 JSON 同时明确：

- `t_onset=null` 时 CP-S2-30-01 直接 `UNACCEPTABLE`；
- 找不到 `t_stop` 时 CP-S2-30-08 为 `UNACCEPTABLE`；
- D-092 门控规定任一 U 则 item/task Fail，Fail 优先于 Incomplete。

同一条“记录在加速段结束”的时序数据，单靠样本本身无法区分：

1. 文件被截断/本来只导出了部分任务，应为 `NOT_EVALUATED`；
2. 完整考核记录中飞行员一直没有减速，应为 `UNACCEPTABLE`。

因此必须新增一个独立的记录完整性事实，例如 run/session 元数据 `recording_scope = full | partial | unknown` 或显式 task-complete marker。推荐规则：

- `full` 且输入、参数、搜索窗齐全：未检出 onset/stop 才按 JSON 判 U；
- `partial/unknown`：依赖缺失后半段的检查点为 `NOT_EVALUATED`，Task 为 Incomplete；
- 任何情况下都不得用“文件自然结束”自动推断 full。

如果没有这个事实，就无法同时满足“未减速是失败”和“给定截断 CSV 是 Incomplete”。这不是算子选择问题，而是输入语义缺一项。

## 6. 请评审的裁定项

### 6.1 在 A-S2-30 六个样板 recipe 前必须回答

1. **共享来源**：是否批准在原 16 个 SourceDescriptor 之外增加 `kinematics/events` 加六个独立 phase、共 8 个 `DERIVED_ARTIFACT` descriptor？profile 锁 descriptor，provider 实现由软件 build/显式 implementation version 追溯；本文推荐批准。
2. **共享参数所有权**：是否批准把 capture/onset/stop 的 canonical 参数放进 `TaskProfile.task_semantics.detectors`，即使它们仍显示在所属 checkpoint 页？这样 provider 不读取别的 recipe，本文推荐批准。
3. **缺失落点**：是否批准“resolver 仍产现有 OMITTED、稳定 diagnostic code 区分 N/E 与 N/A、reporting policy 显示领域状态”的无合同改动方案？同时批准第一批不放入可能单独缺失的 optional diagnostic 分支；本文推荐批准。
4. **记录完整性**：用什么字段或事件区分 partial CSV 与完整但未减速的失败任务？本文推荐显式 `recording_scope/task_complete`，未知一律不冒充 full。
5. **onset control 语义**：`u_lon_baseline` 取哪个窗口、哪种统计量；哪个 U 通道；什么符号代表减速；输入怎样归一到 `%stick`？
6. **`a_s` 定义**：用 earth-frame 加速度向量投影到走廊切向，还是用 `dV/dt`？二者在转向/横移时不同。本文倾向前者，但需确认原始 `ax/ay` 的坐标系。
7. **capture/onset 求解顺序**：capture search 的上界是什么，如何消除 P1/t_capture 循环和 capture/onset 相互依赖？候选为 `[t_entry,t_onset)`，但 onset 必须先从不依赖 capture 的窗口检测。
8. **缺结束事件时的相位**：有 onset 无 stop 时 P4 是 `[onset,session_end]` 还是“不完整”；无 onset 时 CP-30-03/04/05/09 各自 U 还是 N/E？建议除 30-01/30-08 的显式失败规则外，缺完整规定窗口的指标均 N/E。
9. **相位边界**：建议统一半开区间 `[start,end)`，终点采样通过 `sample-at-event` 单独读取；P5 需确认是否包含 `t_stop+hold_duration` 的恰好一个样本。
10. **event 采样对齐**：若 X/U 不是同网格，是否批准 `linear + 可配置 max_gap`；`max_gap` 的依据是同步后 nominal cadence 的多少倍？
11. **复合阈值是否允许相等**：本文的 normalized `q` 要求 desired 与 acceptable 边界严格分开。若允许两者相等形成“零宽度 ACCEPTABLE 区”，就应新增直接执行嵌套规则的通用 scorer，不能除以零。本文推荐保存时强制严格排序。

### 6.2 可在铺开其余 item 前回答

12. **G0/liftoff**：liftoff 的检测量、阈值和持续时间是什么？
13. **速度物理量**：SCN-001 是否以“零风，ground speed 视为空速”作为明确假设？
14. **走廊几何**：centreline 是有方向的无限直线、有限线段、折线还是样条；端点外、等距与自交投影怎样处理？
15. **time-in-desired-band**：按持续时间占比（推荐）还是样本数占比？
16. **受约束横向轴**：Ye 恒定的构型下，横向项照常输出 0 偏差，还是因无区分力 N/E？
17. **CP-S2-02-03 漂出门**：是否指 P5 内矩形门约束 `near <= s <= far && |d| <= w_gate`？若是，批准补充三项 reference dependency。
18. **CP-S2-02-04 漂移纠正**：触发次数/re-arm/滞回、控制轴映射与极性、baseline、最小响应持续时间、unmatched horizon 和“超界”的含义均需补齐。未补齐前建议把该项改判为 blocked。
19. **CP-S2-05-02 `V_overshoot` 诊断**：请给出计算窗口和公式；它不参与分档，可以晚于主指标实现。

## 7. 评审通过后的实施边界

收到上述裁定后，下一阶段才会：

1. 按已授权方案给 `BnNodeRole` 增量增加 `ITEM/TASK`，重导出受影响的 10 份当前 schema，并逐字节验证历史 frozen schema 未变；
2. 生成 `scn001_accel_decel/` 完整骨架：Task 1 + Item 6 + Checkpoint 25 + binding 25 + CPT 31 + sources/task profile/reporting policy；
3. 只落成 A-S2-30 的 6 个已批准 recipe，其余节点保留完整接口但不伪造算法；
4. 对指定 CSV 跑一次，依据“记录完整性”裁定验证 `INCOMPLETE/NOT_EVALUATED`，并明确断言不能为 Pass；
5. 完成相关测试和全量基线后单独 commit。

在本设计获批前，不开始上述实现，也不开始任务 B 的 WinUI 外壳改造。
