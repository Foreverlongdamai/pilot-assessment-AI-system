# M4 Lightweight Workflow Validation Amendment

| 字段 | 当前值 |
|---|---|
| 文档类型 | M4 已批准规格的已接受测试策略修订 |
| 日期 | 2026-07-13 |
| 方向状态 | 用户已确认并批准采用轻量测试方向 |
| 书面状态 | 已于 2026-07-13 获用户批准并生效 |
| 实现状态 | Replacement Task 0–22 已完成；M4-C stage gate 已关闭、M4-D 已开始；O1–O9 capability 与 `movement-events-v1` provider 均为 `available`，下一步为 Task 23 O10；18/18 specified、9/18 production plugins implemented；M4 整体尚未 engineering verified |
| 取代范围 | 立即取代 M4 主规格 §1.1 的完整 fixture 表述、§14.2–§14.4 的“四套 90 秒 full bundle + frozen full-workflow oracle”要求、§15 的 M4-G full-fixture 口径及 §17 的原计划执行授权；replacement plan 已于 2026-07-13 单独批准 |
| 不变范围 | 18 个 anchor、AnchorResult v0.2、DAG、算法、阈值、状态语义、no-quality-gate、M1/M2/M3 已发布合同 |
| 科学状态 | 所有 synthetic 数据继续为 `not_supported`，只验证软件工作流 |

## 1. 修订原因

原 M4 Task 0 按四种场景分别生成 90 秒 dense multimodal bundle。每套临时 bundle 约声明 10,820 个路径，其中包含 8,101 张 VR scene PNG 和 2,701 张 pilot-camera PNG；四套合计约 43,000 个文件，一次 focused fixture test 实测约 160 秒。

这超过当前里程碑的真实需要。M4 当前需要证明的是：

```text
multimodal Session Bundle
  -> M1 integrity
  -> M2 ingestion/adaptation
  -> M3 native-rate alignment
  -> M4 real AnchorPlugin extraction
  -> AnchorResult v0.2 / report
```

它不是图像吞吐、长 session 性能或采集规模测试。更重要的是，首次 provisional oracle 把部分 mixed anchor 结果保存为 recipe 输入，因此即使合同测试通过，也不能证明原始数据真正驱动了 evidence。当时的 provisional Task 0 产物不是冻结基线，现已移除且未进入提交历史。

## 2. 修订目标

修订后的测试必须同时做到：

1. 用一次真实、公开 API 的 M1→M4 流程证明所有模态和 18 个 anchor 能贯通；
2. 用短小、可手算的输入分别证明每个 anchor 的 D/A/U、边界、override 和依赖语义；
3. 证明轨迹差、控制剧烈、未恢复、未注视或生理值极端仍产生 `computed + Unacceptable`，不被质量门过滤；
4. 证明 mixed、missing、not-applicable、not-computable、dependency 和 extractor-error 行为；
5. 严格分离输入、独立 expected values 和 production results，禁止“答案回灌”；
6. 让默认 focused test 可以频繁运行，不生成或追踪大规模 dense assets。

本修订不承担：

- 90 秒或更长 session 的性能、内存和吞吐验证；
- 大分辨率图像、视频编解码或真实设备 exporter 验证；
- 专家阈值校准、飞行任务有效性或科学有效性验证；
- BN/CPT、正式 assessment run、sidecar 或 WinUI 验证。

## 3. 采用的测试金字塔

### 3.1 层 A：合同与纯框架测试

合同、catalog、schema、scorer、DAG、artifact transaction、fingerprint 和 fake-plugin scheduling 使用纯内存对象或极小 JSON。除明确的临时 artifact sink 外，不生成 dense modality 文件。

### 3.2 层 B：18 个 anchor 的定向微型测试

每个 production AnchorPlugin 使用只包含其必需输入的紧凑 `AlignedSession`/`AnchorEvaluationContext`：

- O1–O4、O10、O12：少量 X/reference/envelope/event rows；
- O5–O7、O9、O11：短 U turning/step arrays；
- O8、O13：真实上游 plugin/result/artifact 或版本化 preprocessing provider；
- H1–H3：少量 scene keyframes、AOI 和 raw gaze samples；
- H4：足够形成 baseline/task RR 的 R-peaks；
- H5：至少 4 秒 baseline 与 4 秒 task EEG，使用真实 NumPy/SciPy DSP，而不是预填 engagement 值。

每个 anchor 至少覆盖：

1. Desired、Adequate、Unacceptable；
2. 精确阈值两侧与边界包含关系；
3. 关键 missed/degenerate/no-stable 等 override；
4. missing/config/dependency 行为；
5. 参数或依赖输入改变时，相应 measurement/result/evaluation fingerprint 与依赖它的结果改变；无关 anchor 保持不变；
6. plugin/provider version 或 implementation digest 改变时，implementation/result/evaluation fingerprint 必须改变，即使构造出的 raw measurement 数值恰好相同；
7. 有限但极差的表现仍为 `computed + U`。

这些测试调用真实 `AnchorEvaluator`/公开 `evaluate()` 边界，不允许只调用公式 helper 后伪装成插件通过。

### 3.3 层 C：轻量真实插件场景

四类场景保留其验证目的，但不再各自生成 physical Session Bundle：

| 场景 | 表示方式 | 必须证明 |
|---|---|---|
| all-desired | 内存中的紧凑 aligned raw tables | 18/18 production plugins executed/computed，结果为 D |
| all-unacceptable | 内存中的紧凑 aligned raw tables | 18/18 production plugins executed/computed + U；raw availability=1；没有 quality filtering |
| mixed | 内存中的紧凑 aligned raw tables | 同一 report 中存在固定且可复算的 D/A/U 组合；O8/O9/O13 使用真实依赖 |
| state-matrix | `AnchorEvaluator.for_testing` + 精确 fault hooks | O1=`missing_input`；O2=`not_computable`；O3=`not_applicable`；O4=`extractor_error`；O5=`dependency_missing`；O8 由 O1/O5、O9 由 O1/O4 传播为 `dependency_missing`；其余 11 项 computed；report=`ready_partial` |

all-desired、all-unacceptable 和 mixed 的输入仍是原始/对齐后的数值表，不是 AnchorMeasurement、AnchorResult、state 或 likelihood。state-matrix 可以使用 fake/fault capability 验证框架状态，但不能替代真实插件的缺输入和 override 单测。

state-matrix 的 inventory/count 继续冻结为 expected=18、executed=18、not_applicable=1、applicable=17、computed=11、raw availability=`11/17`。O5 只故障其 `movement-events-v1` provider dependency；其他 anchor/provider 必须继续执行，不能用全局异常伪造该向量。

### 3.4 层 D：轻量 extension/replay 测试

原 M4 `m4-extension-v0.1` 的目的完整保留，但改用纯内存 catalog、极小输入表和 fake/real plugin 组合，不生成 Session Bundle 或图片。它必须覆盖：

- 新增 X1 anchor 后 canonical inventory 增加且旧 revision 不变；
- retire 只影响新 revision，旧 revision replay 仍产生原结果/fingerprint；
- 参数 revision 改变相应 parameter/result/evaluation fingerprint；
- plugin/provider version 或 implementation digest 改变会产生新的实现身份；
- unknown/untrusted implementation 在 factory compute 前 blocked；
- extension 不要求修改中央 O1–H5 switch，因为中央 switch 不存在。

### 3.5 层 E：唯一一个 10 秒全模态 workflow smoke

唯一 physical bundle ID 固定为 `m4-workflow-smoke-v0.1`。它只复用已经实现并验证的 M2/M3 schema、profile、rate 和 identity clock-mapping 机制，不复用 M2 generator 的 35/35/30 phase 比例或无评估语义的 signal recipe，也不新增一套 90/500/30 Hz fixture profile：

| 项目 | 冻结值 |
|---|---|
| session | `[0,10 s]` source grid；analysis spans 继续使用半开区间 |
| baseline | `[0,4 s)` |
| Translation | `[4,6 s)` |
| Deceleration | `[6,8 s)` |
| Hover | `[8,10 s)` |
| X/U | 100 Hz，共用一份格式相容 CSV，1,001 physical rows |
| task reference | 100 Hz，1,001 rows，独立于 actual X |
| I | 30 Hz，301 frame-index rows + 301 个极小 deterministic RGB8 PNG |
| G | 120 Hz，1,201 raw gaze rows；H2 从 raw gaze 重算 fixation |
| EEG | 256 Hz，2,561 rows |
| ECG | 250 Hz，2,501 rows + provided R-peaks |
| pilot_camera | 15 Hz，151 frame-index rows + 151 个极小 deterministic RGB8 PNG |

轻量 source-level recipe 同样是合同的一部分：

| 输入族 | 冻结行为 |
|---|---|
| events | disturbance=`4.250 s`；envelope exit=`6.250 s`；visual cue=`6.750 s`；D→H boundary=`8.000 s` |
| X/reference/envelope | commanded reference 独立于 actual X；peak tracking error=`3 ft`；Translation desired mask 仅 `[4.250,4.500)` 为 false，之后到 phase end 只有 1.5 秒连续恢复，故 O10 必须 `recovery_missed`；Deceleration desired mask 仅 `[6.250,6.450)` 为 false；Hover desired/capture/stable span 固定为 `[8.250,9.750)`，故 O1 phase percentages 为 87.5/90/75%、session=A，而 O3 hold 短于 2 秒 |
| U | workload/reversal axis 在每个 2 秒 phase 使用 `10% * sin(2*pi*1Hz*(t-phase_start))`；magnitude axis 固定 `70%`；mapped-correct raw response/correction step 分别从 `4.490/6.390 s` 开始并保持 150 ms，使 trailing-median detector onset 分别为 `4.500/6.400 s`；hover-trim 在 `[8.250,9.750)` 使用 `1% * sin(2*pi*1Hz*(t-8.250))`，让 O9 走正常 detector |
| I/G/AOI | taxonomy/role 固定为 `primary_flight_display` 与全视野 catch-all `other_scene`；每个 2 秒 task phase 的最后 0.300 秒为 other-scene，其余为 on-task，故 pooled support 精确为 85%/15%；cue 后 relevant raw-gaze fixation onset=`7.000 s` 且持续至少 100 ms；H2 必须从 raw G 重算 |
| ECG/R-peaks | R-peaks 固定为 `0,1,2,3,4 s`，随后为 `4 + k*0.869565217 s, k=1..6`；baseline second-peak RR 为 1 s，三个 task phase 均有 finite positive task HR，约形成 `+15%` signed HR；input 只保存 point times，不保存 H4/O13 result |
| EEG | engagement channels 固定为 `Fp1/Fp2/C3/C4`，相位依次为 `0,pi/2,pi,3pi/2`，input unit=`uV`、`scale_to_volts=1e-6`、reference=`common-average`；baseline 使用 6/10/20 Hz recipe 与 beta amplitude 1；task 使用同一 recipe、`A_beta=sqrt(1.35)`；H5 expected raw value由轻量 numerical oracle执行完整 §12.18 DSP 复算，不写回 input |
| semantic/config bindings | X 与 reference 均为 `local_ned_m`/metre，转换到 scorer feet 时固定 `1 ft=0.3048 m`；target=`[30.48,0,0] m`、arrival axis=`[1,0,0]`，task/hover envelope IDs 固定为 `m4-smoke-task-envelope-v0.1`/`m4-smoke-hover-envelope-v0.1`；`W_min=1 Hz`，O5/O7 active channel=`workload_reversal`；O6 只使用 `magnitude` channel、weight=1、trim=0、lower=-1、upper=1；O9 channel=`hover_trim`；O11 disturbance 与 O12 control-effect 均映射到 `event_response`、correct sign=`+1`；H1 primary role weight=1、other-scene weight=0，H2 relevant role=`primary_flight_display` |
| pilot_camera | 只验证 M1–M3 接口、timestamp 与 provenance；当前 18 anchors 不消费 |

10 秒 smoke 的 expected status/sentinel vector 与 input recipe 分文件保存。它至少冻结：O1=A、O2=A、O3=`capture_missed U`、O4=`1.5 s U`、O6=`70% U`、O10=`recovery_missed U`、O11=`250 ms D`、O12=`150 ms D`、H1=`85% D`、H2=`250 ms D`、H3=`15% U`、H4=D、H5=A；O5/O7/O8/O9/O13 的 exact raw/state 在修订计划中由各自轻量 per-anchor/scenario oracle机械复算后冻结，不能作为 recipe 输入。

完整 18-anchor smoke expected vector 已在任何 production AnchorPlugin 创建前由 replacement Task 0 冻结；后续实现若与该向量不一致，只能修复实现，或重新走规格复核，不能调 input recipe 迎合 production result。

H5 的 baseline `[0,4)` 含 1,024 个 analysis samples；每个 2 秒 task phase 含 512 个 analysis samples，Nyquist=128 Hz，满足 `>35 Hz`。O13 的每个 2 秒 whole-phase window 必须具有 X/U 与 provided-RR 数学 support。

资产预算是合同的一部分：

- physical PNG 精确为 452 个；
- manifest declared-path references 精确为 468：452 个 PNG 加 16 个 non-image references；共享 X/U 路径按 descriptor reference 预算计两次；
- 所有 physical tabular source rows 合计不得超过 9,500；共享 X/U 文件只按一份 physical table 计数，M2/M3 派生 logical views 不重复计数；recipe 冻结时写入 exact total；
- dense CSV/Parquet/PNG 只生成在测试提供的临时目录，不进入 Git；
- 同一次 pytest session 中只构建一次 bundle，后续 smoke/isolated-wheel preparation 复用它；
- 不提高 M1 默认 10,000-path 预算来迁就测试数据。

三个 task phase 只有 2 秒是有意的。H5 按已批准算法允许 `<4 s` phase 使用整段窗口；O13 对 `<30 s` phase 使用整 phase window。fixture 的 `[8.250,9.750)` stable span 让 O9 走正常 movement detector，同时让 O3/O4 得到明确的 capture-missed/1.5 s U，而不依赖恰好落在 phase end 的边界确认。O10 同样为明确的 recovery-missed U。成功 capture、稳定悬停和成功恢复的精确行为由层 B 的 O3/O4/O10 微型测试负责。不得为了让 smoke 全部 Desired 而扭曲算法语义。

workflow smoke 必须通过公开入口依次执行 M1、M2、M3 和最终 production `evaluate()`，并断言：

1. canonical 18 IDs 全部 executed，且此 fixture 设计为 18/18 computed；
2. report 中至少各有一个 D、A、U；
3. O8、O9、O13 的真实 DAG 依赖已执行；
4. 至少 O2、O6、H1/H3、H4、H5 五类跨模态 sentinel 的 raw value 可从输入独立复算，并与 production result 一致；
5. pilot-camera 虽不被当前 18 anchors 消费，仍通过 M1–M3 并保留 provenance；
6. source files 不变、report/artifact/fingerprint 重放确定；
7. `formal_run_authorized=false`、`scientific_validation_status=not_supported`。

该 smoke 不承担 18 项精确阈值 oracle；这些数值由层 B 负责。这样可以同时避免“只测流程不测算法”和“用一套巨大 fixture 承担所有算法证明”两种错误。

## 4. 防止答案回灌

输入 recipe 中的专用 `production_output`/`expected_anchor_results` namespace 必须被 schema 拒绝；semantic/plan 合同中合法的 phase `state` 或 anchor-keyed parameter binding 不受影响。输入资源不得包含以下 production-output 结构：

- 同一 anchor-result-like object 中同时出现 `anchor_id` 与 `primary_value/state/likelihood`；
- 序列化 `AnchorResult` 或 `AnchorMeasurement` object；
- 预先计算的 `q_control`、O8/O13 composite 值；
- 以 O1–O13/H1–H5 为 key、值含 `primary_value/state/likelihood` 的 expected result map；
- 任何由 production plugin 生成后再写回输入的 artifact。

Expected vectors 与 input fixtures 存放在不同文件/模块。轻量 per-anchor/scenario oracle 不 import `pilot_assessment.anchors`；production plugins 不读取 expected vectors。这里的 oracle 只处理单 anchor primitive 或紧凑场景，不得重新扩张成 full-bundle 逐文件 oracle。

至少增加以下扰动证明：

- 改变 X/reference error，只改变依赖该数据的 sentinel；
- 改变 U turning/step signal，使对应 control anchor 改变；
- 改变 gaze/AOI allocation，使 H1/H3 改变；
- 改变 R-peaks，使 H4/O13 改变；
- 改变 EEG beta component，使 H5 改变；
- 每次扰动至少证明一个无关 anchor 保持不变。

文件 checksum 只证明输入不可变，不能代替这些 data-to-anchor 语义断言。

## 5. 性能与执行边界

默认 M4 focused suite 的目标是：

- workflow smoke 在当前 Windows 开发环境实测低于 30 秒；
- focused M4 suite 实测低于 60 秒；
- 除唯一 workflow bundle 外，层 A–D 不进行 dense image/file generation。

运行时间作为实测 handoff 指标记录，不写成依赖机器速度的脆弱单元断言；文件数、路径数、行数和“不追踪 dense assets”是确定性自动门。

90 秒 full-rate bundle 不再是 M4 Task 0、默认 pytest、isolated-wheel smoke 或 M4 engineering-verified 的必要条件。将来若需要长 session 性能/soak test，应建立独立、手动触发的 performance milestone，不能重新阻塞 anchor 功能实现。

## 6. 对当前实施计划的约束

依本已接受修订，已使用 writing-plans 流程形成并于 2026-07-13 单独批准 [replacement M4 实施计划](../plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)；原实施计划保留为已被取代的历史文件，不再执行。Replacement plan 从 Task 0 获得实施授权，并必须满足：

1. Task 0 改为依赖锁、轻量 fixture 合同、防答案回灌 RED 和一次 10 秒 bundle gate；
2. 删除四套 90 秒 physical bundle、逐帧 90/30 Hz 扩展资产、43,000-file manifest 和 full-workflow frozen oracle；
3. 保留 NumPy、SciPy、RFC 8785 锁，因为它们是 production DSP/JCS 依赖，不是重 fixture 专属成本；
4. per-anchor tasks 承担自己的精确 D/A/U golden，不把它们推给全流程 fixture；
5. all-desired/all-unacceptable/mixed 改为真实 plugin 的紧凑内存场景；
6. state-matrix 只生成软件状态，不生成全模态 bundle；
7. M4-G、determinism 和 isolated-wheel smoke 复用同一个 10 秒 bundle；
8. 计划的 specification-to-task matrix、Definition of Done、测试命令和 task count 必须同步更新。

Replacement Task 0 已完成批准的安全检查：provisional heavy fixture files 已逐项移除且未进入提交历史，随后首先观察到缺少轻量能力的正确 RED，再实现新的 input-only fixture。提交 `bc544bf` 冻结了 10 秒 recipe、独立 exact-18 expected vector 与 source hashes；Task 1 `f56365c` 完成 numeric/JCS runtime 审计；Task 2 `928e9a4` 完成 breaking `AnchorResultV2`；Task 3 `e054620` 完成 session-bound candidate/三参数 binder；Task 4 `1528d09`、Task 5 `b63d38b` 与 Task 6 `93c4ddb` 完成 catalog/plan/request、measurement/report/runtime contracts 和 deterministic schema publication；Task 7 `583a1e7` 发布 exact-18 catalog、24 个 canonical parameter resources 与 zero registry。此后 Task 8–13 完成 canonical/runtime framework，Task 14 `b1d1fc9`、Task 15 `b1a8743`、Task 16 `f7d5261`、Task 17 `056d9d5`、Task 18 `1a119af`、Task 19 `2ca3540`、Task 20 `eb9cca6`、Task 21 `15da2ea` 与 Task 22 `db2b5da`/`a76abde` 分别完成 O1–O9；Task 18 同时注册首个 `movement-events-v1` preprocessing provider，Task 22 follow-up 明确 O9 信任 provider-owned movement 下幅值阈值。Task 22 focused/受控相关 gate 分别为 `10 passed`、`237 passed`；最新 full-repository/build/isolated-wheel stage 证据仍为 Task 20 的 `1275 passed, 3 skipped` 及其完成门，不得把旧 provisional `8 passed` 记入 M4 完成证据。M4-C stage gate 已关闭、M4-D 已开始；下一步为 Task 23 O10，当前为 9/18 production plugins。

## 7. 决策与文档迁移

本文获批已触发以下迁移：

1. 在 `DECISIONS.md` 新增 D-026“默认 M4 验证采用轻量测试金字塔；长 session 属于独立性能验证”；
2. 新增 D-027“raw/aligned inputs 必须机械驱动 expected anchors，禁止答案回灌”；
3. 修改 M4 主规格 §1.1、§14.2–§14.4、§15、§17；
4. 把原 M4 实施计划标记为 superseded，并另行编写、复核和批准 replacement plan；
5. 更新 `README.md`、`docs/product/README.md`、`09_VALIDATION_AND_HANDOFF.md`、`10_DESIGN_SELF_REVIEW.md` 和 `11_IMPLEMENTATION_STATUS.md`；
6. 保留 M2/M3 已完成计划与历史实测数字，不回写或伪造其完成证据。

## 8. 验收标准

本修订的设计批准已经完成；其实施仍只有在以下条件同时满足后才可称为落实：

- [x] 用户复核并批准本文；
- [x] 修订后的 M4 实施计划另行获批；
- [x] provisional heavy fixture 未进入提交历史；
- [x] 新 Task 0 首先观察到缺少轻量能力的 RED；
- [x] 唯一 10 秒 bundle 满足 468 declared-path references、452 PNG 和 9,331（`<=9,500`）physical source-table rows 预算；
- [ ] 18 个真实 plugins 的 per-anchor D/A/U 微型测试全部通过；
- [ ] all-unacceptable 证明 18/18 `computed + U` 且无质量过滤；
- [ ] mixed、精确 state matrix、extension/replay、扰动、防输出字段和轻量 per-anchor/scenario oracle 门全部通过；
- [ ] 同一个 bundle 完成 public M1→M4 与 isolated-wheel smoke；
- [ ] 实测时长、依赖版本、test counts、fingerprints 和工作树状态写入 handoff；
- [ ] 只有完成 M4-G 全部门后才可宣称 M4 engineering-verified。

## 9. 自审结论

本修订没有改变 anchor 算法、阈值、状态、BN ownership 或科学边界。它只把验证职责拆回正确层级：算法由小型精确输入证明，负面表现由真实 plugin 场景证明，软件状态由 fault hooks 证明，多模态物理链路由一个轻量 bundle 证明。该分层覆盖原目标，同时移除了四套 90 秒 fixture 对开发节奏的非必要阻塞。
