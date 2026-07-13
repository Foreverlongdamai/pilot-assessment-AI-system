# 设计决策记录

本文件记录会影响多个模块、不能由单一实现文件自行决定的产品级决策。状态“已接受”表示 v0.1 必须遵守；后续可以通过新的决策记录替换，但不得静默修改。

## D-001：产品提供可配置参考模型，而非最终航空标准

- 状态：已接受
- 决策：先实现当前理解下完整、合理、透明的算法、阈值、子技能和 CPT；把可编辑性、版本化和审计作为产品能力。
- 理由：这些科学参数仍需领域专家与真实样本校准。等待所有参数最终确定会阻塞软件体系建设。
- 影响：界面和报告必须显示 model revision 与验证状态，不得把默认值描述成监管认证结论。

## D-002：v0.1 使用 18 个逻辑 evidence nodes

- 状态：已接受
- 决策：目录为 O1–O13 + H1–H5。O2 为 Peak Tracking Excursion，O4 为 Sustained Hover Time，H4 为 ECG Fluctuation，H5 为 EEG Fluctuation；旧 H6 删除。
- 理由：这是用户确认的最新版表格和模型口径。
- 影响：旧稿中的 O1–O13 + H1–H6、19 节点或旧 O2 定义仅作历史资料。

## D-003：视觉和 gaze 是正式一等输入

- 状态：已接受
- 决策：I(t) 是飞行员随头部转动在 VR 中实际看到的第一视角场景；G(t) 是映射到该动态场景的 gaze ray、point、fixation/stare 与 AOI。EEG、ECG 同样进入正式 session contract。
- 理由：这些数据已经采集，只是尚未全部导出；CSV-only 架构会造成后续返工。
- 影响：当前缺少导出文件时使用 export_pending，而不是删除接口或伪造证据。

## D-004：BN 使用生成方向

- 状态：已接受
- 决策：Competency → Sub-skill → Evidence。输入 evidence 后执行反向概率推断。
- 理由：方向表达“能力状态导致可观测表现”，更适合解释 CPT 并处理缺失证据。
- 影响：共享 evidence 可以有多个 sub-skill parents；所有图编辑仍必须保持 DAG。

## D-005：Missing 不是第四种能力表现

- 状态：已接受
- 决策：Desired、Adequate、Unacceptable 是 evidence state；missing、invalid、not_applicable、export_pending 是数据/适用性状态。
- 理由：把缺失当作差表现会系统性惩罚未安装或未导出的模态。
- 影响：BN 对缺失 evidence 不提交观测并进行边缘化；覆盖率单独报告。

## D-006：桌面端首选本地 stdio sidecar

- 状态：已接受
- 决策：WinUI 3 管理 Python sidecar，以 JSON-RPC 2.0 / JSONL over stdin/stdout 通信；stdout 只发送协议消息，日志走 stderr 与文件。
- 理由：本地离线产品无需端口、防火墙或服务发现，打包和生命周期边界清晰。
- 影响：FastAPI 仅可作为未来可选 adapter，不能成为核心业务依赖。

## D-007：前端允许可视化修改节点和边，后端保持权威

- 状态：已接受
- 决策：用户可拖拽新增、删除、移动节点和边，并编辑 anchor 参数、state space 与 CPT；所有语义修改以原子 domain operation 发往后端。
- 理由：领域专家必须能直接在产品中优化模型，而不是修改源代码。
- 影响：前端的 pending 图形不是已保存事实；后端负责 cycle、CPT、binding、版本冲突等验证并返回 canonical graph。

## D-008：草稿可变，发布 revision 不可变

- 状态：已接受
- 决策：编辑先创建 draft；通过验证和 inference smoke test 后发布新 revision。正式运行锁定 published revision 和内容 hash；non-formal preview 锁定 exact draft_id + graph_version。
- 理由：防止编辑中的图影响正在执行或已经完成的评估，保证结果可重现。
- 影响：撤销/重做基于后端命令日志；发布后修改或“回滚”都必须从选定 revision 建立新 draft。draft_validation_state、revision_lifecycle、scientific_validation_status 和 permitted_use 是独立字段。

## D-009：大数据通过文件合同传递

- 状态：已接受
- 决策：JSON-RPC 只传 session bundle 路径、相对路径、metadata 与 checksum；视频、帧、EEG、ECG 和长时间序列不嵌入 JSON。
- 理由：降低内存、序列化和进程通信风险。
- 影响：session import 必须执行路径、schema、checksum 和访问权限检查。

## D-010：软件验证与科学验证分离

- 状态：已接受
- 决策：“计算按规范执行”与“评分真实有效”分别管理、显示和验收。
- 理由：高测试覆盖率不能证明 anchor 阈值或 CPT 具有真实世界效度。
- 影响：产品必须携带 software_verification_status 与 scientific_validation_status；reference v0.1 的初始 scientific_validation_status 为 engineering_default。

## D-011：X/U 可以共享一个受验证的物理 artifact

- 状态：已接受
- 决策：v0.1 允许 `X` 与 `U` 两个 `present` logical stream view 引用完全相同的 bundle-relative path。两者必须声明相同 checksum、format、schema_id 和 `metadata.shared_source_id`，并分别声明 `metadata.view_id=X/U`；checksum 文件只登记该物理文件一次。其他 stream sharing、大小写不同的路径别名，以及同一路径被两个独立声明赋予 stream/annotation/reference/integrity 跨角色所有权均拒绝。D-014 的 `task_reference` descriptor 是 reference artifact 的唯一 owner，不构成跨角色 sharing。
- 理由：当前 simulator CSV 同时包含 flight state 与 pilot control；强行复制文件既浪费空间，也会制造两个可能漂移的“原始”副本。
- 影响：loader 分别报告 logical reference count 与 unique artifact count，路径安全、读取、hash 和资源预算按 unique artifact 执行；同一物理文件仍只有一个 canonical identity。

## D-012：Synthetic full bundle 只用于软件验证

- 状态：已接受
- 决策：captured-format-sample X/U 加 synthetic I/G/EEG/ECG/pilot_camera 的混合 bundle 必须标记 `synthetic-test-data`、`software-testing-only` 和 `scientific_validation_status=not_supported`；该 X/U 只代表采集格式，不是有效任务 session、标准轨迹、ground truth 或能力证据。所有结果显示 `SYNTHETIC TEST DATA`，不得转换为正式飞行员评估结果。
- 理由：格式正确、可重复的合成信号可以验证软件闭环，但不能证明 anchor、阈值、CPT 或能力结论对真人有效。
- 影响：生成器、报告、前端和导出都必须保留 synthetic provenance；synthetic 生理/相机数据不计为真实人体 biometric data。

## D-013：Ingestion readiness 与 Run preflight 是不同阶段

- 状态：已接受
- 决策：M2 输出 `IngestionReadinessReport`，scope 固定为 `inspect_only_ingestion_content_v1`，只回答 source artifact 能否进入 M3 synchronization；其中 `formal_run_authorized` 永远为 false。完成同步、annotation/reference 语义检查并锁定 model revision 后，`run.preflight` 才输出 `RunPreflightReport` 并决定是否允许创建 AssessmentRun。
- 理由：两种检查共用“preflight”名称会让前端和审计记录误以为通过 ingestion 就已获准评分。
- 影响：M2 raw schemas 不伪造 authoritative `t_ns`；M3 生成 aligned schemas。DTO、协议、术语表和界面必须使用完整名称。

## D-014：Bundle-local task reference 通过可选 stream 间接声明

- 状态：已接受
- 决策：session-local commanded/reference path 的文件位于 `references/`，由可选 `streams.task_reference` descriptor 声明 format、schema、clock、units、paths 和 checksums；`task.reference` 使用 `source=bundle` 与 `stream_id=task_reference` 指向它。`source=model_bundle` 时禁止 `stream_id`，由锁定的 model bundle 根据 `reference_id` 解析。
- 理由：reference 是可采样的时序 artifact，复用 StreamDescriptor 可避免第二套路径、checksum 和时钟权威，同时保持它不属于七个 core modalities。
- 影响：bundle reference 必须通过普通路径安全、integrity 和 adapter gate，但在 readiness/coverage 中单独报告，不能伪装成飞行员输入模态。

## D-015：Reference-model-v0.1 固定为 33 节点三层 BN

- 状态：已接受
- 决策：reference-model-v0.1 的 Guided palette 只包含 competency、subskill 和 evidence，结构边只允许 competency→subskill 与 subskill→evidence。Phase/task context 保留在 BN 外供 AnchorPlugin 使用；O8/O13 通过 `derived_from`、`dependence_group` 和 `likelihood_strength` 处理相关性，不创建 evidence→derived_evidence 结构边。
- 理由：当前 CPT 和推理语义只定义了四 competency、十一 sub-skill、十八 evidence 的三层网络；允许未定义的 context 或派生结构边会产生无法解释的 CPT。
- 影响：context node 或 structural derived evidence 只能在明确声明其语义、CPT、编译和 golden tests 的新 model profile 中启用；从 reference-v0.1 切换必须使用新的 major model profile，不能只改 draft/revision 标识。

## D-016：M3 只产生 native-rate aligned views

- 状态：已接受
- 决策：M3 只映射原生采样行并追加 aligned time/flags；不插值、不重采样、不建立 anchor-specific analysis/window grid。
- 理由：插值和窗口参数依赖 AnchorPlugin/model revision，提前全局冻结会制造未经专家批准的信号值。
- 影响：M3 报告 interpolated_rows=0；M4 按 anchor 定义建立 grid/window。

## D-017：Clock scale 是唯一映射权威

- 状态：已接受
- 决策：唯一公式为 round-half-even(source_s × scale × 1e9 + offset_ns)；drift_ppm 只与 scale 做一致性审计，不再次参与计算。同 clock_id 必须共享 method/scale/offset/drift mapping；per-stream residual 可以不同。
- 理由：同时施加 scale 和 drift 会重复校正并破坏可复现性。
- 影响：M3 对 scale/drift、residual 顺序、same-clock mapping 和 int64 overflow 执行结构门。M4 书面候选规格提议由 D-021 取代原先“task/anchor-specific residual tolerance 留给后续 gate”的影响说明；D-021 随完整 M4 规格获批后生效，届时 M4 不得把 residual、coverage 或所谓采集质量变成表现 evidence 的过滤门。

## D-018：v0.1 session window 由 master-clock X 推导

- 状态：已接受
- 决策：v0.1 只支持 origin=session_start；window 为 [0,max(mapped X primary t_ns)]，source=master-clock-x-mapped-coverage-v1。
- 理由：manifest 0.1 没有独立 duration/end；X 仅是 v0.1 session-end 的技术时间边界来源，不是 commanded trajectory、任务标准或表现权威。
- 影响：synthetic duration_s 仅作 golden cross-check；未来显式 window 必须走新的 schema/decision。

## D-019：Annotation 与 reference 在 M3 分流

- 状态：已接受
- 决策：synthetic annotation 的 *_s 是 session-relative seconds；正式 session-time annotation 直接声明 t_ns。Bundle reference 在 M3 对齐；model-bundle reference 返回 deferred_model_bundle_resolution。
- 理由：annotation 没有 device clock，而 model reference 只有锁定 revision 后才能解析。
- 影响：M3 不猜 annotation clock/response semantics，也不把 deferred model reference 误报 missing。

## D-020：M3 使用独立 snapshot input 和 report

- 状态：已接受
- 决策：内部 SynchronizationInput 组合同一次 LoadedManifest、PreparedSession 和 IngestionReadinessReport；输出内部 AlignedSession 与公共 SynchronizationReport。
- 理由：PreparedSession 不应吸收 bundle I/O/clock/annotation 责任，M1 也不应重复 load/hash。
- 影响：SynchronizationReport 与 IngestionReadinessReport/RunPreflightReport 分离，始终 formal_run_authorized=false，并绑定 source/policy/catalog/alignment fingerprints。

## D-021：M4 不承担原始数据质量研究

- 状态：提议（设计方向已分段确认；待 M4 完整书面规格批准）
- 决策：M4 假定其输入已经通过 M1–M3 的文件、schema、有限数值、字段和时间合同；M4 不再设置 coverage、noise、gap、residual、artifact、幅值或生理范围 quality gate，也不因这些 diagnostics 省略表现 evidence。M1–M3 的结构检查继续存在，但它们不是 M4 的评分门。
- 理由：仿真采集系统负责交付有效数据；本产品负责按冻结规则评价飞行表现。把表现异常或数值极端重新解释为“低质量数据”会系统性掩盖真正的差表现，并把项目扩展成另一项采集质量研究。
- 影响：`SessionQualityReport`、`IngestionReadinessReport` 和 `SynchronizationReport` 可以保留技术 diagnostics，但 M4 scorer 不读取它们形成 quality score，不做 outlier clipping、winsorization、artifact-based window deletion 或医学范围过滤；历史 M1–M3 合同仅作上游完整性边界。

## D-022：差表现必须产生 Unacceptable evidence

- 状态：提议（设计方向已分段确认；待 M4 完整书面规格批准）
- 决策：输入、公式配置和任务适用条件存在时，极大轨迹误差、剧烈控制、极端但有限的生理指标、未捕获、未稳定悬停、未恢复、未响应和未注视均必须输出 `computed + Unacceptable`。无法用有限主值表达的观察使用受控 `classification_override`，不得使用 Infinity 或 NaN。
- 理由：这些现象就是系统需要客观反映的负面表现，不是缺失证据。
- 影响：`computed + Unacceptable` 与 Desired/Adequate 一样具有 raw availability 1 并提交给 M5；missing、not applicable、缺配置/依赖和软件错误使用单独状态，不能与差表现合并。

## D-023：M4 使用可扩展 catalog、typed DAG 与 AnchorResult v0.2

- 状态：提议（设计方向已分段确认；待 M4 完整书面规格批准）
- 决策：M4 engine 按版本化 `AnchorCatalog` 与编译后的 `AnchorExecutionPlan` 运行可变数量插件；只有 `reference-model-v0.1` profile 精确包含 O1–O13、H1–H5。插件先产生 `AnchorMeasurement`，中央 scorer 生成 breaking contract `anchor-result-0.2.0`；其计算状态只允许 `computed`、`missing_input`、`not_applicable`、`not_computable`、`dependency_missing`、`extractor_error`。执行通过 typed dependency DAG、受控 artifact sink 和 canonical inventory 完成。
- 理由：前端未来增、删、改 anchor 和算法时，orchestrator 不应写死 18 个分支；同时必须保留可验证、可重放的依赖与合同边界。
- 影响：`anchor-result-0.1.0` 仅保留为只读 legacy 合同，M4 不写它，也不静默改写 schema ID。新增/retire anchor 发布新 catalog/model revision；参数变更产生新 parameter snapshot；公式变更必须发布新 plugin version。`plugin_unavailable`、`not_implemented`、`not_attempted` 只属于 capability/plan/report inventory，不冒充 session calculation status。

## D-024：M5 不按所谓数据质量衰减 evidence

- 状态：提议（设计方向已分段确认；待 M4 完整书面规格批准）
- 决策：M5 直接消费 M4 的版本化 D/A/U likelihood，不使用 quality score 向均匀分布收缩。O8/O13 的默认 `likelihood_strength=0.50`，以及 H1/H3 `gaze_allocation` dependence group 的 reference strength `0.50 each`，只用于相关性和重复计数保护，不表示数据质量。
- 理由：quality mixing 会把最差但有效的表现重新拉回无信息分布，违背 D-022。
- 影响：coverage 衡量适用 evidence 是否成功产生：`computed` 的 D/A/U 都贡献完整 availability，`not_applicable` 不进入分母；模型影响强度可以另作 diagnostic，但不能命名为 coverage 或 quality。

## D-025：M4 工程完成必须同时证明全好、全差与可扩展重放

- 状态：提议（设计方向已分段确认；待 M4 完整书面规格批准）
- 决策：M4-G 只有在逐 anchor 手算 golden、精确边界、状态矩阵、18/18 computed Desired、18/18 computed Unacceptable、扩展/retire/version replay、确定性 fingerprint、source immutability、完整测试、构建和隔离 wheel 全部通过后，才可声称 M4 engineering-verified。
- 理由：只证明理想信号能运行不能发现“差表现被过滤”的核心失效模式，也不能证明专家未来修改 anchor 后仍可重放。
- 影响：全 Unacceptable fixture 的 raw availability 必须为 1，M4 输出不得出现 `invalid_quality`；synthetic fixture 继续标记 `scientific_validation_status=not_supported`。M4-A 至 M4-F 的局部完成状态必须如实报告，不能冒充 M4 整体实现。
