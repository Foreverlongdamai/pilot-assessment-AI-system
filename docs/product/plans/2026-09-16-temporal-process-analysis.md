# 时序过程分析实施合同

**Goal:** 在两个场景的飞行 item 和全部飞行检查点增加逐帧时序证据推断、曲线、参数编辑与报告导出。用户已批准上一轮方法作为过程分析加法；不替换现行累计分、最终分或 P/F。

**Architecture:** Python 统一计算，C# DTO 严格回读，原生结果窗口显示独立过程图。固定能力 S，首个观察使用 CPT，此后使用给定 S 的时间依赖类别转移；同时显示每帧新增证据，避免把后验饱和误当无操作变化。

**Tech Stack:** 当前 Python 环境、现有 WinUI/.NET 10；不新增依赖。

## 模型与界限

对检查点 j，给定能力状态 s，CPT 行 θ(j,s) 同时用作起始类别分布与转移稳态分布。这是新增的工程模型约束。相关时间 τ(j,s)>0，可编辑，演示统一 5 秒（三种能力相同），不是标定数值，也不是平均恢复耗时。独立探测显示短τ仍易饱和；5秒是明确标注的演示起点，不证明实际最优。

`T_s(a,b,dt) = exp(-dt/tau_s) * I(a=b) + (1-exp(-dt/tau_s)) * theta_s[b]`。

CP 日志后验=原先验日志+全部新条件似然日志。item 日志后验=原先验日志+各CP条件似然日志之和；给定S后CP独立是显式演示假设，不复用最终评分的κ或等权。任何CP的后验不再作为item证据相乘，避免重复先验。归一化后按配置状态分值求期望。

每个点保存本帧 `log_bayes_factor_high_low = logL(H)-logL(L)`。它表示新证据倾向，0中性，正偏高、负偏低，单位自然对数，不是能力分。新增过程图显示0–100后验期望及证据增量。模型描述“认识如何随过程证据改变”，不保证每次失误都使分数明显波动。

阶段改变或本CP经历不适用帧：下一次适用观测用该CP起始分布，不跨不可比较阶段连转移；此前累计后验不重置。相同phase内不同时间间隔直接进入T，无补帧/事件截取。缺失适用观测后本CP后验、item后验不再完整，后续点不输出数值；其他完整CP仍可分析。输入/时间/本item规则参数结构阻断时不生成似然。缺失完整阶段可显示已提供过程，但分析标partial，不伪称完整。

检查单保持之前已定的完成性记录，无连续操纵能力CPT；其统一过程分析返回not_applicable与明确说明，不伪造连续曲线。适用飞行CP包括禁止事件的二态D/U。

## JSON 增量合同（schema3向后兼容可选字段）

每个飞行 `skill_models[item_id]` 增可选：

```json
"process_model": {
  "method": "fixed_skill_markov_v1",
  "checkpoint_time_constants_s": { "CHECKPOINT_ID": [5.0, 5.0, 5.0] }
}
```

必须准确覆盖该item所有CP。三值对应低/中/高，有限且正；过程启用要求完整严格正先验/CPT及完整状态分值。方法未知/参数无效只阻断过程模型，不能污染既定规则或原累计评分；配置验证仍报告错误。旧配置省略时不自动填值，可通过编辑器启用演示参数。新版演示配置显式启用。

`skill_quantification.temporal_analysis`：

```text
status: complete | partial | not_configured | invalid_model | not_applicable | blocked
method: fixed_skill_markov_v1
model_version: string|null
message: string
warnings: string[]
checkpoint_traces: trace[]
item_trace: trace|null

trace:
 checkpoint_id: string|null (item为null)
 method: fixed_skill_markov_v1
 status: complete|partial|no_evidence
 message: string
 timeline: point[]

point:
 frame_index: int
 timestamp_s: number
 phase_id: string
 grade: string|null (item同帧规则等级)
 status: calculated|insufficient_evidence|no_evidence
 posterior: number[3]|null
 score: number|null
 log_bayes_factor_high_low: number|null
 update_kind: initial|transition|phase_initial|mixed|missing|none
 evidence_count: int (本帧有效证据数量)
 observed_checkpoint_count: int (截至当前见到的有效CP数)
 expected_checkpoint_count: int
```

无过程配置仍返回not_configured，检查单返回not_applicable。导出保留完整帧，图按真实时间画完整范围，缺测断线，tooltip给时刻、阶段、D/A/U、三态概率、期望分与证据增量。标明“时序证据推断（累计判断）”，其末端不等于当前整段质量分。最终分卡及原累计图保留。

检查点过程timeline与item全部输入帧对齐；该CP不适用的真实item帧标no_evidence、概率/分数为空。这些是已有时间点的适用性标记，不补造观测，并用于在跨不适用片段时断线。

## 实施与验证分工

- [x] Python：新增独立 `temporal_analysis.py` 与验证模块；扩展series_models/frame_calculator但不让过程参数错误阻断原评分。先写失败测试，覆盖两帧手算、转移非边际重复、先验只一次、binary、Δt、phase/不适用、missing、旧配置、无效配置隔离、两场景全部飞行CP。
- [x] Desktop：新增DTO/源生成、参数克隆与相等、过程参数编辑器、结果窗口item/CP过程图、导出快照；回读与编辑单测先行，绘图验证边界/完整时间轴与断线。
- [x] 演示与文档：生成器显式配置过程参数，重跑六份报告并核对旧分数/PF严格不变，更新演示包及说明。所有过程参数标未标定。
- [x] 集成：Python场景测试、Desktop单测/合同/绘图、原生build；核对快捷方式目标并同步原exe。构建时目标进程未运行，不需要关闭用户应用。
- [x] 复核数学/缺测/序列正确性，记录真正执行的验证，不把合成演示写成实测有效性。
- [ ] 原生结果窗口最终视觉验收：主界面已启动并读取；进一步操作检测到用户同时使用窗口，已暂停，未声称完成。浏览器新双图实际查看与桌面真实报告合同均已完成。详见[验证记录](../reviews/2026-09-16-temporal-process-verification.md)。

现有工作区包含大量未提交业务变更，本轮沿用工作区，不创建丢失当前文件的另一个checkout，不自动提交。
