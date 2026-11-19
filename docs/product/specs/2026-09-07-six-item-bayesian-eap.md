# SCN-001 六 item 当次技能量化

2026-09-07。用户已确认推广地面起飞静态 BN 及 EAP 方法至其余 item。本次在该授权范围内接入当前场景计算器和 WinUI；无学习历史、原始数据提取或场景总分。原三个等级、P/F 与阈值保持原规则。

## 模型

每个 item 各有一个低/中/高的当次技能变量，生成本 item 已定检查点观察。固定先验，每次从本次观察重新计算，不从旧后验累积。默认研究模板 prior=[1/3,1/3,1/3]，state_scores=[0,50,100]；EAP=Σp_h×score_h。完整证据输出分数，部分证据可输出概率但 score=null；无证据、未执行必要动作、非法数据或模型冲突不补分。

18 个三态检查点演示 CPT（行低/中/高、列 D/A/U）：[[.10,.25,.65],[.25,.50,.25],[.65,.25,.10]]。急停禁止事件只允许 D/U，演示表为 [[.35,.65],[.75,.25],[.90,.10]]，相当于本研究模板将可通过的两类概率合为 D；不能产生 A 或把不存在的 A 当观测。所有表均为未校准的项目假设，不是官方数值。给定技能后各检查点条件独立是研究假设；重复原指标、item 等级不得再次作为证据。

| item | 检查点数 | 量化对象 | 适用性上下文 |
|---|---:|---|---|
| A-S1-06 | 6 | 起飞前仪表区域注视覆盖表现 | 无额外动作门控；0秒仍是有效U证据 |
| A-S2-08 | 3 | 起飞与初始悬停操纵表现 | initial_hover_duration_s 正数；0表示未执行初始悬停，不代表必然未离地 |
| A-S2-05 | 3 | 加速与保速操纵表现 | speed_hold_duration_s 正数；0不输出技能推断 |
| A-S2-30 | 4 | 急停执行与过程控制表现 | deceleration_started=true；false不输出推断；stop_achieved=false仍是已观察失败，不能省略其U证据 |
| A-S2-02 | 2 | 末端水平位置与航向控制表现 | terminal_hover_duration_s 正数 |
| A-S2-01 | 1 | 末端高度与垂直稳定控制表现 | 同一 terminal_hover_duration_s 正数 |

上下文缺失返回unknown_action；非法值返回invalid_evidence，不当成未执行。两个末端各自使用其完整检查点一次，时长门控不作为额外似然；共享时长的关联记录在说明中，不将两者再汇总或视为独立的全场景证据。仅有1个检查点的高度item不会人为拆成多个点提高置信度。

## JSON 增量合同（保留 schema_version=1.0）

配置增加可选 skill_models 字典；缺省/null意味着旧配置尚未设置模型，仍可以按原规则计算；不得静默给旧文件补模型。新 catalog.configuration_template 自带六项演示模型。加载旧配置后，每个item编辑器可显式载入本项演示模板。

`configuration.skill_models[item_id]`:

```text
model_version: "scn001-skill-demo-v1"
calibration: "uncalibrated"（本版只接受此值）
parameter_source: "demonstration" | "user_defined"
prior: [number|null × 3]
state_scores: [number|null × 3]（0<=低<中<高<=100；默认为0/50/100）
checkpoint_models: {checkpoint_id: {
  states: ["D","A","U"] 或 ["D","U"]（取决于该检查点规则，不允许更改字母表）,
  probabilities: [三行，每行对应states列]
}}
```

概率必须有限、0–1、每行和为1；先验同样验证。不自动归一化。数组维度、检查点键、模型字段严格验证。自定义有序方向/似然比不符合时报告warning，保留可审查研究结果，不能称提升表现必定提升分数。未知模型item标识报告配置问题。

`catalog.items[]` 增加 `skill_name` 和 `skill_description`，均为只读解释字段，不改变原检查点结构。动作适用性由后端六项映射实现，不由可编辑CPT改变。

`report.items[].skill_quantification`:

```text
status: complete|partial|not_configured|not_performed|unknown_action|no_evidence|invalid_model|invalid_evidence|impossible_evidence
skill_name: string
method: "eap"
model_version: string|null
calibration: string|null
parameter_source: string|null
posterior: [低,中,高]|null
score: number|null
evidence_count: 实际使用checkpoint数量
expected_evidence_count: 该item的checkpoint总数
evidence: [{checkpoint_id, grade: D|A|U|null, used: bool}]
message: string
warnings: [string]
```

配置快照保存实际CPT/先验/状态分值；结果不重复整份模型。部分缺失（包括必需原结果缺失）、非法输入与模型问题不更改已有U/Fail。模型配置问题不能把原本D/A的规则结果改为失败。数值计算使用log-sum-exp；零总似然显示模型冲突，不伪造后验。

## WinUI 和编辑会话

每item弹窗增加可折叠“贝叶斯技能量化”编辑区：量化对象、研究参数说明、三先验/状态分值、各checkpoint CPT；D/U点只显示两列。旧配置未设置时可载入本项演示模型。参数和模型共同采用编辑副本，取消不改任何配置；应用后使旧报告失效，配置和报告JSON保存全部模型字段。

Desktop.Core SceneItemEdit 增加可读写 `SkillModel`（nullable SceneSkillModel）。SceneConfiguration增加nullable `SkillModels`；SceneItem增加 SkillName/SkillDescription；SceneItemResult增加nullable SkillQuantification。Root负责DTO/Workspace及测试；WinUI负责将 edit.SkillModel 纳入候选验证和提交。服务器路径 `/skill_models/{itemId}/...` 与原 `/parameters/...` 同时由弹窗显示。模型编辑不能因其他item缺容差而被阻塞。

每item结果同时展示原grade/PF、当次技能估计分、三概率、证据完整性、参数来源与警告。没有分数显示原因，不给0分。界面明确分数不另设通过线、不代表学习完成率；不生成六item平均分或历史进度条。

## 验证

Python：6项模型覆盖/字母表、地面起飞DDA=约87、DDU仍Fail、全D/全U、所有保持0及unknown、未开始减速/未停止、部分缺证据、共享时长只使用一次、极小/零似然、参数错误、快照与规则回归。

.NET：模型配置JSON往返、取消/应用/旧报告失效、编辑隔离、旧配置无模型兼容、真实Python RPC含六模型与六结果的完整契约。WinUI Debug x64构建及可用的运行检查。交付为本地开发版，不自动发布或迁移历史记录。
