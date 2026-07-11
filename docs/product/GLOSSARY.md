# 术语表

| 术语 | 定义 |
|---|---|
| Assessment Core | 执行 session 载入、同步、anchor 计算、evidence 转换、BN 推理和结果构建的 Python 核心。 |
| Anchor / Evidence anchor | 从原始或派生数据计算的可解释指标，例如 O2 Peak Tracking Excursion。 |
| AnchorPlugin | 实现某个 anchor 算法、参数 schema、依赖声明和质量门的受控后端插件。 |
| Evidence node | BN 中接收 Desired / Adequate / Unacceptable 观测的节点。参考模型有 18 个。 |
| Sub-skill | 不可直接观测的中间技能节点。参考模型有 11 个。 |
| Aggregate competency | 顶层能力节点：TCP、PC、SM、OC。 |
| TCP | Task Control Proficiency，任务控制熟练度。 |
| PC | Procedural Compliance，程序遵循。 |
| SM | Situational Monitoring，态势监控。 |
| OC | Operational Composure，运行镇定/稳定性。 |
| X(t) | 随时间变化的飞行器状态和运动学/动力学数据。 |
| U(t) | 随时间变化的驾驶员控制输入。 |
| I(t) | 飞行员在 VR 中随头部姿态变化而实际看到的第一视角视觉场景。 |
| G(t) | 与 I(t) 对齐的 gaze ray/point、fixation/stare、AOI、有效性和置信度。 |
| P(t) | 生理信号族；v0.1 至少包括 EEG 与 ECG，可扩展其他经批准的生理模态。 |
| Pilot camera | 可选的驾驶员脸部/身体画面流；不是 H1–H3 计算 gaze-on-scene 的必要条件。 |
| AOI | Area of Interest，场景中的关注区域；可以随 VR 画面和头部姿态动态变化。 |
| Phase | Translation、Deceleration、Hover 等任务阶段。 |
| Event | 扰动、提示、包线越界等带时间标记的离散事件。 |
| Desired / D | 参考模型中的期望表现 evidence state。 |
| Adequate / A | 参考模型中的可接受表现 evidence state。 |
| Unacceptable / U | 参考模型中的不可接受表现 evidence state。 |
| missing | 本应存在但文件或字段缺失；不是表现等级。 |
| export_pending | 已知已采集但尚未导出到 session bundle；不是表现等级。 |
| invalid | 数据存在但未通过格式、同步或质量检查；不是表现等级。 |
| not_applicable | 当前任务/阶段没有该证据适用条件，例如没有扰动事件；不是表现等级。 |
| Quality | evidence 对应数据的可用性与置信度，和 evidence state 分开记录。 |
| Coverage | 本次评估实际可用证据相对于模型期望证据的覆盖程度。 |
| Ingestion readiness inspection | M2 对 source artifact 内容、schema、质量和 adapter 可用性的只读检查；输出 `IngestionReadinessReport`，只允许进入 M3，且永不授权正式 run。 |
| Run preflight | `run.preflight` 在 aligned session、annotation/reference 和锁定 model revision 上执行的正式运行门；输出 `RunPreflightReport` 并决定能否创建 AssessmentRun。 |
| BN | Bayesian Network，贝叶斯网络。 |
| CPT | Conditional Probability Table，节点在给定 parent state 下的条件概率表。 |
| Virtual evidence | 用似然权重而非硬状态表达不确定 evidence；低质量时向均匀分布收缩。 |
| Model bundle | anchor catalog、任务 profile、图、CPT、schema、版本和 provenance 的可发布模型包。 |
| Draft | 可编辑、尚未用于正式运行的模型工作副本。 |
| Published revision | 验证并发布后不可变的模型版本。 |
| graph_version | 草稿内整个 semantic model（node、edge、state、CPT、binding、anchor parameters、profile）每次原子修改后递增的乐观并发版本。 |
| layout_version | 仅版本化节点位置等显示布局；变化不影响 graph_version 或 scientific model hash。 |
| draft_validation_state | draft_incomplete、draft_invalid、draft_runnable 或 draft_publishable，表示草稿完整性与可运行性。 |
| revision_lifecycle | published、archived 或 superseded，表示不可变 model revision 的生命周期。 |
| observation_mode | hard、virtual 或 omitted，表示某条 AnchorResult 是否以及如何进入 BN。 |
| revision_id | 标识不可变发布模型或其父版本的稳定 ID。 |
| Sidecar | 由 Windows 前端启动和管理的本地 Python 后端进程。 |
| JSON-RPC / JSONL | 每行一个 JSON-RPC 2.0 消息的 stdio 进程协议。 |
| TPX | O8 使用的 task performance composite，由 phase-state precision 与 workload rate 组合。 |
| Software verified | 软件按设计合同执行且通过规定测试。 |
| Scientifically validated | 评估指标、阈值、CPT 和输出经过足够样本、专家标注及统计研究证明有效。 |
