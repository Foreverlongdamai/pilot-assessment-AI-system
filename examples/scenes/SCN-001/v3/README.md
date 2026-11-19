# 加速减速任务 v3 当前模板

2026-10-11：本任务删除 A-S2-23 正常进近至悬停，当前为起飞前检查、空中滑行（加速与保速）、快速减速／快速停止，共3 item、12检查点、17输入量。阶段为 preflight → acceleration → hold → deceleration → stop；确认结束不单独计分。旧文件须明确整理，不自动丢弃用户数据。

更新：2026-10-11。用于当前双场景桌面开发版，schema_version 为 3.0。

空中滑行的 `A-S2-05-01` 现为“加速与保速速度控制”，使用 `air_taxi_airspeed_mps` 和共享时间参考曲线，同时评价加速与保速。旧 `speed_hold_airspeed_mps`、`speed_hold_duration_s`、`hold_end` 不属于当前合同；请一起更新配置与输入，不只改字段名称。

| 文件 | 功能 |
|---|---|
| [configuration-template.json](configuration-template.json) | 空白规则与CPT草稿。无依据的目标和容差留空。 |
| [input-template.json](input-template.json) | item.frames 结构，每个阶段有一帧占位。复制持续阶段帧并填写精确时刻和原始值。 |
| [engineering-demo-configuration.json](engineering-demo-configuration.json) | 人工构造的算术验证参数，不是权威阈值，不用于实际训练结论。 |
| [engineering-demo-input.json](engineering-demo-input.json) | 合成的好表现—短暂失误—恢复输入，未取自实际飞行记录。 |
| [engineering-demo-report.json](engineering-demo-report.json) | 同一计算器生成的完整报告；保留失误与Fail，没有虚构贝叶斯分数。 |

在软件左侧选择本场景，加载工程演示配置，再导入工程演示帧数据，点击开始评估即可浏览。实际训练请使用空白模板自行配置，不直接采用示例数字。

所有 item 使用同一个场景仿真时钟，timestamp_s 为非负相对秒；每个 item 内递增，不能每次重复阶段重新归零。无 start_s/end_s；没有从样例日志切片或自动识别阶段。

空速参考配置为 `expected: null`、`reference_profile: [{"elapsed_s": ..., "expected": ...}, ...]`；这是单一列表，不是按阶段分组的 `reference_profiles`。在 item 编辑器中填写“加速开始后 / s”和“期望空速 / m/s”，至少两个完整节点，首节点 0 秒，后续严格递增；空列表及未填完的节点可保存草稿，不能完整评估。D/A 允许低于／高于的数值围绕每帧期望空速应用。

共享起点 `t0` 是 acceleration 的第一帧时间，每帧用 `timestamp_s − t0` 对齐参考曲线，进入 hold 不归零。例：首帧 28.3 s，实际帧 30.7 s，对齐曲线 2.4 s；若节点为 2 s → 4 m/s、6 s → 10 m/s，该帧期望值线性插值为 4.6 m/s。系统只插值参考目标，不改变原始帧和采样间隔。每个实际帧产生一次 D/A/U，参考节点数量不增加贝叶斯证据数量；报告该指标逐帧保留 `reference_elapsed_s` 和原始 `timestamp_s`。

缺少 acceleration 起点阶段时，不以 hold 首帧补位；记录早于曲线末端结束时提示覆盖不足；实际帧超出曲线范围时不外推或延用端点。以上情况不能给出完整 Pass 或最终分数，已有 U 仍保留。输入方负责提供真实加速开始帧；仅凭剩余帧不能识别实际早期帧是否漏录。上述数字只说明算术，曲线形状、持续时间和 D/A 容差是项目训练设置，不是官方规定的统一速度时刻表。

stop 已允许连续多帧，每帧分别评价终点位置和该阶段适用的过程指标，再保留最差档。本次没有新增最少帧数或停留时长；导师演示的 5 秒、51 帧只是合成示例。**目前终点位置检查不证明地速为零**：输入的 stop 标签不是自动检测结果，软件也不从位置差分补出地速。stop 的停止高度和过程实际高度来自同一原始量，须保持一致。

控制输入可作为可选 controls 对象保留 Pilot Lon、Pilot Lat、Pilot Yaw、Pilot Heave，不能代替实际位置/速度/航向，也不按动杆多少打分。

需要重新生成这些验证文件时，从仓库运行已有环境：

```powershell
.\.venv\Scripts\python.exe tools/Generate-SceneFrameExamples.py
```

完整说明：[场景评估与 Model Studio 使用指南](../../../../docs/product/SCENE_CALCULATOR_GUIDE_CN.md)。